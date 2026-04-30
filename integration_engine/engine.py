import json
from .device_client import DeviceClient
from .logger import log, log_error
import os
from .event_processor import EventProcessor
from .postgres_db import PostgresDB
from .etl_processor import ETLProcessor
import random


class IntegrationEngine:
    # Constructor
    def __init__(self):
        base_path = os.path.dirname(os.path.abspath(__file__))  # this file's directory
        self.registry_file = os.path.join(base_path, "device_registry.json")
        self.devices = {}   # dict instead of list

        self.device_status = {}
        self.db = PostgresDB()
        self.etl = ETLProcessor(self.db)
        self.load_devices()

    # Retrieves all registered devices
    def load_devices(self):
        log("Loading device registry...")

        with open(self.registry_file, "r") as f:
            registry = json.load(f)

        for entry in registry["devices"]:
            device = DeviceClient(entry)
            # Store devices in a DICT keyed by ID
            self.devices[entry["id"]] = device

        log(f"Loaded {len(self.devices)} devices.")


    # Printer helpers

    def get_printers(self):
        return [d for d in self.devices.values() if d.type == "printer"]

    def generate_specimen_barcode(self):
        return f"LAB{random.randint(1000000000, 9999999999)}"

    def get_all_printer_settings(self):
        results = {}

        for printer in self.get_printers():
            data, err = printer.fetch_printer_settings()
            
            # Update status
            self.update_device_status(printer, err)
            
            if err:
                results[printer.id] = {"error": err}
            else:
                results[printer.id] = data

        return results

    def test_print_all_printers(self):
        results = {}

        for printer in self.get_printers():
            log(f"Sending TEST PRINT to {printer.id}...")
            data, err = printer.test_print()
            
            # Update status
            self.update_device_status(printer, err)

            if err:
                results[printer.id] = {"status": "FAILED", "error": err}
            else:
                results[printer.id] = {"status": "SUCCESS", "preview": data["zplPreview"]}

        return results

    def reprint_on_printer(self, printer_id):
        for printer in self.get_printers():
            if printer.id == printer_id:
                log(f"Sending REPRINT to {printer.id}...")
                data, err = printer.reprint_last_label()
                
                # Update status
                self.update_device_status(printer, err)

                if err:
                    return {"status": "FAILED", "error": err}

                return {"status": "SUCCESS", "preview": data["zplPreview"]}

        return {"status": "FAILED", "error": "Printer not found"}
    
    def send_custom_label_to_printers(self, zpl):
        results = {}
        for printer in self.get_printers():
            data, err = printer.test_print(zpl)
            
            # Update status
            self.update_device_status(printer, err)
            if err:
                results[printer.id] = {"status": "FAILED", "error": err}
            else:
                results[printer.id] = {
                "status": "SUCCESS",
                "preview": data.get("message", "Label printed")
            }

        return results


    # Scanner helpers
    def get_scanners(self):
        return [d for d in self.devices.values() if d.type == "scanner"]
    
    def get_all_scanner_settings(self):
        results = {}
        
        for scanner in self.get_scanners():
            data, err = scanner.fetch_scanner_settings()
            
            # Update status
            self.update_device_status(scanner, err)
        
            if err:
                results[scanner.id] = {"error": err}
                
            else:
                results[scanner.id] = data
                
        return results
    
    def test_scan_all_scanners(self):
        results = {}

        for scanner in self.get_scanners():
            log(f"Triggering SCAN on {scanner.id}...")

            data, err = scanner.scan_barcode()

            # Update status tracking
            self.update_device_status(scanner, err)

            # If scanner is offline OR returned no usable data
            if err or data is None or "barcode" not in data:
                results[scanner.id] = {
                    "status": "FAILED",
                    "error": err or "No barcode returned"
                }
                continue

            # Successful scan
            results[scanner.id] = {
                "status": "SUCCESS",
                "barcode": data["barcode"]
            }

        return results

    
    # Analyzer helpers
    def get_analyzers(self):
        return [d for d in self.devices.values() if d.type == "lab_analyzer"]
    
    def get_all_analyzer_settings(self):
        results = {}
        
        for analyzer in self.get_analyzers():
            data, err = analyzer.fetch_analyzer_settings()
            
            # Update status
            self.update_device_status(analyzer, err)
        
            if err:
                results[analyzer.id] = {"error": err}
                
            else:
                results[analyzer.id] = data
                
                
        return results
    
    def run_test_on_all_analyzers(self, specimen_id="UNKNOWN", test_type="CBC"):
        results = {}
        
        for analyzer in self.get_analyzers():
            log(f"Requesting lab result from {analyzer.id} ({test_type})...")
            data, err = analyzer.generate_lab_result(specimen_id, test_type)
            
            # Update status
            self.update_device_status(analyzer, err)
            
            if err:
                results[analyzer.id] = {"status": "FAILED", "error": err}
                
            else:
                results[analyzer.id] = {
                "status": "SUCCESS",
                "specimenId": specimen_id,
                "testType": test_type,
                "result": data["result"]
            }

                
        return results
    
    # Event helper
    def create_event_processor(self):
        return EventProcessor(self)
    
    def update_device_status(self, device_client, error):
        """
        Mark a device ONLINE or OFFLINE based on the error returned.
        """
        if error is None:
            self.device_status[device_client.id] = "ONLINE"
        else:
            self.device_status[device_client.id] = "OFFLINE"

if __name__ == "__main__":
    engine = IntegrationEngine()
    
    # Printer demo

    print("\n=== PRINTER STATUS ===")
    print(engine.get_all_printer_settings())

    print("\n=== TEST PRINT ===")
    print(engine.test_print_all_printers())

    print("\n=== REPRINT ===")
    print(engine.reprint_on_printer("printer01"))
    
    # Scanner demo
    
    print("\n=== SCANNER SETTINGS ===")
    print(engine.get_all_scanner_settings())

    print("\n=== TEST SCANNER READ ===")
    print(engine.test_scan_all_scanners())
    
    # Analyzer demo
    
    print("\n=== ANALYZER SETTINGS ===")
    print(engine.get_all_analyzer_settings())

    print("\n=== SIMULATED LAB RESULT (CBC) ===")
    print(engine.run_test_on_all_analyzers(specimen_id="SPC002938", test_type="CBC"))

    print("\n=== SIMULATED LAB RESULT (CMP) ===")
    print(engine.run_test_on_all_analyzers(specimen_id="SPC002938", test_type="CMP"))
    
    # Event processing demo
    
    print("\n=== STARTING EVENT PROCESSOR DEMO ===")

    processor = engine.create_event_processor()

    # Queue events
    processor.add_event({
        "type": "SCAN_SPECIMEN",
        "payload": {}
    })

    processor.add_event({
        "type": "RUN_TEST",
        "payload": {"specimenId": "SPC556677", "testType": "CBC"}
    })

    processor.add_event({
        "type": "PRINT_LABEL",
        "payload": {"zpl": "^XA^FO50,50^ADN,36,20^FDPatient Label^FS^XZ"}
    })

    # Process events once (not indefinitely)
    # Instead of processor.start(), manually handle the queue:
    while processor.event_queue:
        event = processor.event_queue.pop(0)
        processor._handle_event(event)
        
    # Workflow demo
    
    print("\n=== FULL WORKFLOW DEMO ===")

    processor = engine.create_event_processor()

    # Start full pipeline: SCAN → RUN_TEST → PRINT_LABEL
    processor.add_event({
        "type": "SCAN_SPECIMEN",
        "payload": {}
    })

    # Process all queued events
    while processor.event_queue:
        event = processor.event_queue.pop(0)
        processor._handle_event(event)




