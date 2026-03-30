from __future__ import annotations

import threading
import time
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request

from src.config import load_settings
from src.escpos import build_escpos_output
from src.keep_client import create_keep_client
from src.print_service import PrintService
from src.printer_transport import create_printer_transport


settings = load_settings()
app = Flask(__name__)
keep_client = create_keep_client()
print_service = PrintService(create_printer_transport(settings.printer))
keepalive_poll_seconds = settings.app.keepalive_poll_seconds

last_keepalive_error: str | None = None
state_lock = threading.Lock()
client_lock = threading.Lock()


def keepalive_poll_once() -> str | None:
    global last_keepalive_error
    try:
        with client_lock:
            keep_client.keepalive_sync()
        with state_lock:
            last_keepalive_error = None
        return None
    except Exception as error:  # noqa: BLE001
        message = str(error) if str(error) else "Unknown keepalive polling error"
        with state_lock:
            last_keepalive_error = message
        print(f"[keep-bridge] Keepalive poll failed: {message}")
        return message


def keepalive_loop() -> None:
    keepalive_poll_once()
    while True:
        time.sleep(keepalive_poll_seconds)
        keepalive_poll_once()


@app.get("/health")
def health() -> Any:
    with state_lock:
        return jsonify(
            {
                "ok": last_keepalive_error is None,
                "lastKeepaliveError": last_keepalive_error,
                "keepalivePollSeconds": keepalive_poll_seconds,
                "printerTransport": settings.printer.transport,
            }
        )


@app.get("/printer-status")
def printer_status() -> Any:
    return jsonify(print_service.get_status())


@app.get("/list")
def get_list() -> Any:
    list_name = request.args.get("name", "").strip()
    if not list_name:
        return jsonify({"error": "Missing required query parameter: name"}), 400

    try:
        with client_lock:
            snapshot = keep_client.fetch_list(list_name)
    except Exception as error:  # noqa: BLE001
        return jsonify({"error": "Failed to fetch Keep list", "details": str(error)}), 502

    if snapshot is None:
        return jsonify({"error": f"Keep list not found: {list_name}"}), 404

    return jsonify(
        {
            "noteId": snapshot.note_id,
            "title": snapshot.title,
            "uncheckedItems": snapshot.unchecked_items,
            "checkedItems": snapshot.checked_items,
            "updatedAt": snapshot.updated_at,
            "outputEncoding": "byte-array",
            "output": build_escpos_output(snapshot.title, snapshot.unchecked_items),
        }
    )


@app.post("/print-list")
def print_list() -> Any:
    body = request.get_json(silent=True) or {}
    list_name = str(body.get("title", "")).strip()
    if not list_name:
        return jsonify({"error": "Missing required JSON field: title"}), 400

    try:
        with client_lock:
            snapshot = keep_client.fetch_list(list_name)
    except Exception as error:  # noqa: BLE001
        return jsonify({"error": "Failed to fetch Keep list", "details": str(error)}), 502

    if snapshot is None:
        return jsonify({"error": f"Keep list not found: {list_name}"}), 404

    job = print_service.create_job(snapshot)
    result = print_service.send_job(job)
    if not result.ok:
        return (
            jsonify(
                {
                    "error": "Failed to send ESC/POS payload to printer",
                    "printerStatus": result.status_code,
                    "printerResponse": result.response,
                    "jobId": job.job_id,
                    "printerTransport": settings.printer.transport,
                }
            ),
            502,
        )

    return jsonify(
        {
            "ok": True,
            "jobId": job.job_id,
            "title": job.title,
            "uncheckedItems": job.unchecked_items,
            "bytesSent": len(job.raw_bytes),
            "printerStatus": result.status_code,
            "printerResponse": result.response,
            "printerTransport": settings.printer.transport,
        }
    )


def main() -> None:
    port = settings.app.port
    print(f"[keep-bridge] Listening on :{port}")

    thread = threading.Thread(target=keepalive_loop, daemon=True)
    thread.start()

    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
