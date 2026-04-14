from flask import Flask, render_template, request, redirect, url_for, flash
from integration_engine.engine import IntegrationEngine

app = Flask(__name__)
app.secret_key = "dev-secret-key"  # replace later if you want

# Build engine once at startup
engine = IntegrationEngine()


@app.route("/")
def index():
    """
    Main dashboard page.
    Shows device settings/status and optional last action result.
    """
    result_type = request.args.get("result_type")
    message = request.args.get("message")
    specimen_id = request.args.get("specimen_id")
    test_type = request.args.get("test_type")

    try:
        printer_settings = engine.get_all_printer_settings()
    except Exception as e:
        printer_settings = {"error": str(e)}

    try:
        scanner_settings = engine.get_all_scanner_settings()
    except Exception as e:
        scanner_settings = {"error": str(e)}

    try:
        analyzer_settings = engine.get_all_analyzer_settings()
    except Exception as e:
        analyzer_settings = {"error": str(e)}

    device_status = getattr(engine, "device_status", {})

    return render_template(
        "index.html",
        printer_settings=printer_settings,
        scanner_settings=scanner_settings,
        analyzer_settings=analyzer_settings,
        device_status=device_status,
        result_type=result_type,
        message=message,
        specimen_id=specimen_id,
        test_type=test_type,
    )


@app.route("/scan", methods=["POST"])
def scan():
    """
    Trigger barcode scan on all scanners.
    """
    try:
        result = engine.test_scan_all_scanners()
        return render_template("order.html", action="Scan Specimen", result=result)
    except Exception as e:
        flash(f"Scan failed: {e}", "error")
        return redirect(url_for("index"))


@app.route("/run-test", methods=["POST"])
def run_test():
    """
    Run a test on all analyzers for a specimen.
    """
    specimen_id = request.form.get("specimen_id", "").strip() or "UNKNOWN"
    test_type = request.form.get("test_type", "").strip().upper() or "CBC"

    try:
        result = engine.run_test_on_all_analyzers(
            specimen_id=specimen_id,
            test_type=test_type
        )
        return render_template(
            "order.html",
            action=f"Run {test_type}",
            result=result,
            specimen_id=specimen_id,
            test_type=test_type,
        )
    except Exception as e:
        flash(f"Analyzer request failed: {e}", "error")
        return redirect(url_for("index"))


@app.route("/print-label", methods=["POST"])
def print_label():
    """
    Send custom ZPL to all printers.
    """
    zpl = request.form.get("zpl", "").strip()

    if not zpl:
        flash("ZPL is required.", "error")
        return redirect(url_for("index"))

    try:
        result = engine.send_custom_label_to_printers(zpl)
        return render_template("order.html", action="Print Label", result=result, zpl=zpl)
    except Exception as e:
        flash(f"Print failed: {e}", "error")
        return redirect(url_for("index"))


@app.route("/test-print", methods=["POST"])
def test_print():
    """
    Send default test print to all printers.
    """
    try:
        result = engine.test_print_all_printers()
        return render_template("order.html", action="Test Print", result=result)
    except Exception as e:
        flash(f"Test print failed: {e}", "error")
        return redirect(url_for("index"))


@app.route("/workflow", methods=["POST"])
def workflow():
    """
    Full simulated workflow:
    scan -> run CBC -> print label
    """
    try:
        processor = engine.create_event_processor()

        processor.add_event({
            "type": "SCAN_SPECIMEN",
            "payload": {}
        })

        while processor.event_queue:
            event = processor.event_queue.pop(0)
            processor._handle_event(event)

        flash("Workflow completed. Check device status and database logs.", "success")
        return redirect(url_for("index"))
    except Exception as e:
        flash(f"Workflow failed: {e}", "error")
        return redirect(url_for("index"))


@app.route("/refresh", methods=["GET"])
def refresh():
    """
    Simple refresh route for dashboard.
    """
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9004, debug=True)