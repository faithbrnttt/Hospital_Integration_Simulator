from .logger import log, log_error

class ETLProcessor:

    def __init__(self, db):
        self.db = db

    def process_test_result(self, analyzer_id, specimen_barcode, test_type, result_json, result_time):
        test_type = test_type.upper()
        
        if test_type == "CBC":
            try:
                self.db.insert_cbc_result(
                    specimen_barcode=specimen_barcode,
                    analyzer_id=analyzer_id,
                    result_json=result_json,
                    result_time=result_time
                )
                log(f"[ETL] CBC normalized for specimen {specimen_barcode}")
                
            except Exception as e:
                log_error(f"[ETL ERROR] Could not process CBC result: {e}")
        elif test_type == "CMP":
            try:
                log(f"[CMP DEBUG] result_json keys: {result_json.keys()}")
                log(f"[CMP DEBUG] full result_json: {result_json}")
                log(f"[ETL DEBUG] CMP result_json = {result_json}")
                self.db.insert_cmp_result(
                    specimen_barcode=specimen_barcode,
                    analyzer_id=analyzer_id,
                    result_json=result_json,
                    result_time=result_time
                )
                log(f"[ETL] CMP normalized for specimen {specimen_barcode}")
            except Exception as e:
                log_error(f"[ETL ERROR] Could not process CMP result: {e}")
                
        else:
            log_error(f"[ETL ERROR] Unsupported test type: {test_type}")