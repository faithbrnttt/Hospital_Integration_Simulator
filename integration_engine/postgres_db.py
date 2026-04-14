import psycopg2
import psycopg2.extras
from .logger import log_error

class PostgresDB:

    def __init__(self, host="localhost", db="integration_engine", user="postgres", password="1234"):
        self.host = host
        self.db = db
        self.user = user
        self.password = password

        self.conn = self._connect()
        self._create_tables()

    def _connect(self):
        try:
            conn = psycopg2.connect(
                host=self.host,
                database=self.db,
                user=self.user,
                password=self.password
            )
            return conn
        except Exception as e:
            log_error(f"PostgreSQL connection failed: {e}")
            raise

    def _create_tables(self):
        cur = self.conn.cursor()

        # Specimens
        cur.execute("""
            CREATE TABLE IF NOT EXISTS specimens (
                id SERIAL PRIMARY KEY,
                specimen_barcode TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_status TEXT
            );
        """)

        # Scan events
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scan_events (
                id SERIAL PRIMARY KEY,
                scanner_id TEXT,
                barcode TEXT,
                event_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Analyzer results
        cur.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id SERIAL PRIMARY KEY,
                analyzer_id TEXT,
                specimen_barcode TEXT,
                test_type TEXT,
                result_json JSONB,
                result_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Print jobs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS print_jobs (
                id SERIAL PRIMARY KEY,
                printer_id TEXT,
                specimen_barcode TEXT,
                label_type TEXT,
                zpl TEXT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # CBC normalization
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cbc_results (
                id SERIAL PRIMARY KEY,
                specimen_barcode TEXT,
                analyzer_id TEXT,
                wbc NUMERIC,
                hgb NUMERIC,
                hct NUMERIC,
                plt NUMERIC,
                result_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

        self.conn.commit()
        cur.close()

    # ------------------------------------------
    # DATABASE INSERT OPERATIONS
    # ------------------------------------------

    def insert_cbc_result(self, specimen_barcode, analyzer_id, result_json, result_time):
        cur = self.conn.cursor()

        cur.execute("""
            INSERT INTO cbc_results (
                specimen_barcode,
                analyzer_id,
                wbc,
                hgb,
                hct,
                plt,
                result_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (
            specimen_barcode,
            analyzer_id,
            result_json.get("WBC"),
            result_json.get("HGB"),
            result_json.get("HCT"),
            result_json.get("PLT"),
            result_time
        ))

        self.conn.commit()
        cur.close()


    def ensure_specimen_exists(self, barcode):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO specimens (specimen_barcode, last_status)
            VALUES (%s, %s)
            ON CONFLICT (specimen_barcode) DO NOTHING;
        """, (barcode, "SCANNED"))
        self.conn.commit()
        cur.close()

    def update_specimen_status(self, barcode, status):
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE specimens SET last_status = %s
            WHERE specimen_barcode = %s;
        """, (status, barcode))
        self.conn.commit()
        cur.close()

    def log_scan_event(self, scanner_id, barcode):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO scan_events (scanner_id, barcode)
            VALUES (%s, %s);
        """, (scanner_id, barcode))
        self.conn.commit()
        cur.close()

    def log_test_result(self, analyzer_id, specimen_barcode, test_type, result_dict):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO test_results (analyzer_id, specimen_barcode, test_type, result_json)
            VALUES (%s, %s, %s, %s);
        """, (
            analyzer_id,
            specimen_barcode,
            test_type,
            psycopg2.extras.Json(result_dict)   # <-- FIXED
        ))

        # Update specimen status
        self.update_specimen_status(specimen_barcode, f"{test_type}_RESULT")

        self.conn.commit()
        cur.close()


    def log_print_job(self, printer_id, specimen_barcode, label_type, zpl, status):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO print_jobs (printer_id, specimen_barcode, label_type, zpl, status)
            VALUES (%s, %s, %s, %s, %s);
        """, (printer_id, specimen_barcode, label_type, zpl, status))

        if specimen_barcode and status == "SUCCESS":
            self.update_specimen_status(specimen_barcode, f"{label_type}_PRINTED")

        self.conn.commit()
        cur.close()

    def close(self):
        self.conn.close()
