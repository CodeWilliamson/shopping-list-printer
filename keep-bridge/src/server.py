from __future__ import annotations

import hashlib
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from keep_client import create_keep_client


load_dotenv()

app = Flask(__name__)
keep_client = create_keep_client()
keepalive_poll_seconds = int(os.getenv("KEEP_KEEPALIVE_POLL_SECONDS", "3600"))
esp32_print_url = os.getenv("ESP32_PRINT_URL", "http://esp32-printer.local/print").strip()
esp32_api_token = os.getenv("ESP32_API_TOKEN", "").strip()

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


def build_escpos_output(title: str, unchecked_items: list[str]) -> list[int]:
    payload = bytearray()

    # Centered bold title.
    payload.extend(b"\x1b\x61\x01")
    payload.extend(b"\x1b\x45\x01")
    payload.extend(title.encode("utf-8", errors="replace"))
    payload.extend(b"\n")
    payload.extend(b"\x1b\x45\x00")

    # Left align list contents.
    payload.extend(b"\x1b\x61\x00")
    payload.extend(b"\n")

    if unchecked_items:
        for item in unchecked_items:
            payload.extend(f"[ ] {item}\n".encode("utf-8", errors="replace"))
    else:
        payload.extend(b"(empty)\n")

    return list(payload)


def send_escpos_to_esp32(raw_bytes: list[int], job_id: str) -> tuple[bool, int | None, str]:
    if not esp32_api_token:
        return False, None, "Missing ESP32_API_TOKEN"

    payload = bytes(raw_bytes)
    request_url = f"{esp32_print_url}?jobId={urllib.parse.quote(job_id)}"
    req = urllib.request.Request(
        request_url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {esp32_api_token}",
            "Content-Type": "application/octet-stream",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
            return 200 <= status_code < 300, status_code, body
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return False, error.code, body
    except Exception as error:  # noqa: BLE001
        return False, None, str(error)


@app.get("/health")
def health() -> Any:
    with state_lock:
        return jsonify(
            {
                "ok": last_keepalive_error is None,
                "lastKeepaliveError": last_keepalive_error,
                "keepalivePollSeconds": keepalive_poll_seconds,
            }
        )


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

    raw_bytes = build_escpos_output(snapshot.title, snapshot.unchecked_items)
    signature_payload = "|".join(
        [snapshot.note_id, snapshot.updated_at, ",".join(snapshot.unchecked_items), ",".join(snapshot.checked_items)]
    )
    job_id = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()[:16]

    ok, status_code, printer_response = send_escpos_to_esp32(raw_bytes, job_id)
    if not ok:
        return (
            jsonify(
                {
                    "error": "Failed to send ESC/POS payload to ESP32",
                    "esp32Status": status_code,
                    "esp32Response": printer_response,
                    "jobId": job_id,
                }
            ),
            502,
        )

    return jsonify(
        {
            "ok": True,
            "jobId": job_id,
            "title": snapshot.title,
            "uncheckedItems": snapshot.unchecked_items,
            "bytesSent": len(raw_bytes),
            "esp32Status": status_code,
            "esp32Response": printer_response,
        }
    )


def main() -> None:
    port = int(os.getenv("PORT", "3001"))
    print(f"[keep-bridge] Listening on :{port}")

    thread = threading.Thread(target=keepalive_loop, daemon=True)
    thread.start()

    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
