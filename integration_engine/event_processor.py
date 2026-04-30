import time
from .logger import log, log_error
import datetime

class EventProcessor:
    # Constructor
    def __init__(self, engine):
        self.engine = engine
        self.db = engine.db               # <-- CRITICAL: Database connection
        self.event_queue = []
        self.running = False

    # Add event
    def add_event(self, event):
        log(f"Event queued: {event['type']}")
        self.event_queue.append(event)

    # Event loop
    def start(self):
        self.running = True
        log("Event Processor started.")

        while self.running:
            if not self.event_queue:
                time.sleep(0.5)
                continue

            event = self.event_queue.pop(0)
            self._handle_event(event)

    def stop(self):
        self.running = False
        log("Event Processor stopped.")

    # Route events to handler methods
    def _handle_event(self, event):
        event_type = event["type"]
        payload = event["payload"]

        log(f"Processing event: {event_type}")

        try:
            if event_type == "SCAN_SPECIMEN":
                self._handle_scan_event(payload)

            elif event_type == "RUN_TEST":
                self._handle_run_test_event(payload)

            elif event_type == "PRINT_LABEL":
                self._handle_print_label_event(payload)

            else:
                log_error(f"Unknown event type: {event_type}")

        except Exception as e:
            log_error(f"Event processing error: {e}")

    # --------------------------
    # EVENT HANDLERS
    # --------------------------

    def _handle_scan_event(self, payload):
        """Scan an existing specimen barcode, then queue analyzer step."""

        test_type = payload.get("testType", "CBC")
        expected_barcode = payload.get("specimenId")

        scan_result = self.engine.test_scan_all_scanners()
        log(f"SCAN RESULT: {scan_result}")

        first_device_id = list(scan_result.keys())[0]
        first_result = scan_result[first_device_id]

        if first_result["status"] != "SUCCESS":
            log_error(f"SCAN FAILED for {first_device_id}: {first_result.get('error')}")
            return scan_result

        scanned_barcode = expected_barcode or first_result["barcode"]

        try:
            self.db.log_scan_event(first_device_id, scanned_barcode)
            self.db.ensure_specimen_exists(scanned_barcode)
        except Exception as e:
            log_error(f"DB scan insert failed: {e}")

        self.add_event({
            "type": "RUN_TEST",
            "payload": {
                "specimenId": scanned_barcode,
                "testType": test_type
            }
        })

        return scan_result



    def _handle_run_test_event(self, payload):
        """Send test order to analyzer, then queue print event."""

        specimen_id = payload.get("specimenId")
        test_type = payload.get("testType")

        log(f"Running test {test_type} for specimen {specimen_id}...")

        result = self.engine.run_test_on_all_analyzers(
            specimen_id=specimen_id,
            test_type=test_type
        )

        log(f"TEST RESULT ({test_type}): {result}")

        # ----- FAILURE HANDLING (Phase 5) -----
        for analyzer_id, info in result.items():
            if info["status"] != "SUCCESS":
                log_error(f"ANALYZER FAILURE on {analyzer_id}: {info.get('error')}")
                log_error("Workflow stopped for this specimen due to analyzer failure.")
                return
        # --------------------------------------

        # SUCCESS → write to DB + ETL
        for analyzer_id, info in result.items():
            if info["status"] == "SUCCESS":
                try:
                    self.db.log_test_result(
                        analyzer_id=analyzer_id,
                        specimen_barcode=specimen_id,
                        test_type=test_type,
                        result_dict=info["result"]
                    )

                    # Trigger ETL normalization
                    self.engine.etl.process_test_result(
                        analyzer_id=analyzer_id,
                        specimen_barcode=specimen_id,
                        test_type=test_type,
                        result_json=info["result"],
                        result_time=None   # Or generate timestamp later
                    )

                except Exception as e:
                    log_error(f"DB/ETL processing error: {e}")

        # Queue printing
        log(f"Queuing PRINT_LABEL for specimen {specimen_id}...")

        label_zpl = (
            f"^XA^FO50,50^ADN,36,20^FDSpecimen: {specimen_id}^FS^XZ"
        )

        # self.add_event({
        #     "type": "PRINT_LABEL",
        #     "payload": {
        #         "zpl": label_zpl,
        #         "specimenId": specimen_id
        #     }
        # })


    def _handle_print_label_event(self, payload):
        """Send label to printers and log results."""

        specimen_id = payload.get("specimenId")
        zpl = payload["zpl"]

        log(f"Sending label to printer for specimen {specimen_id}...")

        result = self.engine.send_custom_label_to_printers(zpl)
        log(f"PRINT RESULT: {result}")

        # ----- FAILURE HANDLING (Phase 5) -----
        for printer_id, info in result.items():
            if info["status"] != "SUCCESS":
                log_error(f"PRINT FAILURE on {printer_id}: {info.get('error')}")
                # Unlike analyzer/scanner, we do NOT stop workflow here
                # because printing failure does NOT invalidate a specimen.
        # --------------------------------------

        # SUCCESS → Write print jobs to DB
        for printer_id, info in result.items():
            try:
                self.db.log_print_job(
                    printer_id=printer_id,
                    specimen_barcode=specimen_id,
                    label_type="SPECIMEN",
                    zpl=zpl,
                    status=info["status"]
                )
            except Exception as e:
                log_error(f"DB print_job insert failed: {e}")
