from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any
from datetime import datetime

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.escpos import build_shopping_list_escpos_payload, build_daily_fun_escpos_payload
from typing import Optional
from src.keep_client import KeepList
from src.printer_transport import PrintResult, PrinterTransport
from src.config import load_settings
from src.grocery_item_grouper import create_grocery_section_grouper, GrocerySection
from src.daily_fun import create_daily_fun


@dataclass(frozen=True)

class PrintJob:
    job_id: str
    raw_bytes: bytes
    title: str


class PrintService:
    def __init__(self, transport: PrinterTransport) -> None:
        self._transport = transport
        self._lock = threading.Lock()
        self._last_error: Optional[str] = None
        self._last_job_id: Optional[str] = None
        self._last_response: Optional[str] = None
        self._last_status_code: Optional[int] = None


    def create_print_keep_list_job(self, keep_list: KeepList) -> PrintJob:
        """
        Print a Google Keep list. If grouped_sections is not provided, group items using OpenAI if enabled.
        """
        print("[DEBUG] create_print_keep_list_job called")

        settings = load_settings()
        grouper = create_grocery_section_grouper(settings.openai, settings.grouping)
        grouped_sections = grouper.group_items(keep_list.title, keep_list.unchecked_items)

        signature_payload = "|".join([
            keep_list.note_id,
            keep_list.updated_at,
            ",".join(keep_list.unchecked_items),
        ])
        job_id = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()[:16]
        now = datetime.now()
        subtitle = now.strftime("%Y-%m-%d %H:%M")
        print(f"[DEBUG] subtitle: {subtitle}")
        raw_bytes = build_shopping_list_escpos_payload(
            keep_list.title,
            subtitle,
            keep_list.unchecked_items,
            grouped_sections=grouped_sections,
        )
        print(f"[DEBUG] raw_bytes length: {len(raw_bytes)}")
        job = PrintJob(
            job_id=job_id,
            raw_bytes=raw_bytes,
            title=keep_list.title,
        )
        print(f"[DEBUG] PrintJob created: job_id={job.job_id}, title={job.title}")
        return job

    def create_print_fun_message_job(self) -> PrintJob:
        """
        Print a daily fun message. Expects fun_data to contain keys like 'title', 'lines', etc.
        """
        print("[DEBUG] create_print_fun_message_job called")
        settings = load_settings()
        daily_fun_generator = create_daily_fun(settings.openai, settings.daily_fun)
        title = "Daily Fun"
        items = daily_fun_generator.generate_daily_fun()
        now = datetime.now()
        subtitle = now.strftime("%Y-%m-%d %H:%M")
        raw_bytes = build_daily_fun_escpos_payload(
            title,
            subtitle,
            items,
        )

        job_id = hashlib.sha256((title + subtitle + ",".join(items[0].content)).encode("utf-8")).hexdigest()[:16]
        return PrintJob(
            job_id=job_id,
            raw_bytes=raw_bytes,
            title=title,
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