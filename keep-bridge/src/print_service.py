from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.escpos import build_escpos_payload
from src.keep_client import KeepSnapshot
from src.printer_transport import PrintResult, PrinterTransport


@dataclass(frozen=True)
class PrintJob:
    job_id: str
    raw_bytes: bytes
    title: str
    unchecked_items: list[str]


class PrintService:
    def __init__(self, transport: PrinterTransport) -> None:
        self._transport = transport
        self._lock = threading.Lock()
        self._last_error: str | None = None
        self._last_job_id: str | None = None
        self._last_response: str | None = None
        self._last_status_code: int | None = None

    def create_job(self, snapshot: KeepSnapshot) -> PrintJob:
        signature_payload = "|".join(
            [
                snapshot.note_id,
                snapshot.updated_at,
                ",".join(snapshot.unchecked_items),
                ",".join(snapshot.checked_items),
            ]
        )
        job_id = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()[:16]
        return PrintJob(
            job_id=job_id,
            raw_bytes=build_escpos_payload(snapshot.title, snapshot.unchecked_items),
            title=snapshot.title,
            unchecked_items=snapshot.unchecked_items,
        )

    def send_job(self, job: PrintJob) -> PrintResult:
        with self._lock:
            result = self._transport.send(job.raw_bytes, job.job_id)
            self._last_job_id = job.job_id
            self._last_status_code = result.status_code
            self._last_response = result.response
            self._last_error = None if result.ok else result.response
            return result

    def get_status(self, realtime: bool = False) -> dict[str, Any]:
        diagnostics = self._transport.get_diagnostics(realtime=realtime).to_dict()
        diagnostics.update(
            {
                "lastJobId": self._last_job_id,
                "lastPrinterError": self._last_error,
                "lastPrinterResponse": self._last_response,
                "lastPrinterStatus": self._last_status_code,
                "realtime": realtime,
            }
        )
        return diagnostics

    def warmup_printer_session(self) -> PrintResult:
        with self._lock:
            return self._transport.warmup_session()

    def close_printer_session(self) -> PrintResult:
        with self._lock:
            return self._transport.close_session()

    def reopen_printer_session(self) -> PrintResult:
        with self._lock:
            return self._transport.reopen_session()