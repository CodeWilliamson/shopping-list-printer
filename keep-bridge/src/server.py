from __future__ import annotations

import os
import threading
import time
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from keep_client import create_keep_client


load_dotenv()

app = Flask(__name__)
keep_client = create_keep_client()
keepalive_poll_seconds = int(os.getenv("KEEP_KEEPALIVE_POLL_SECONDS", "3600"))

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
