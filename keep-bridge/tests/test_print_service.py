from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.grocery_grouping import GrocerySection
from src.keep_client import KeepSnapshot
from src.print_service import PrintService
from src.printer_transport import PrintResult, PrinterDiagnostics


class _StubTransport:
    transport_name = "stub"

    def send(self, raw_bytes: bytes, job_id: str) -> PrintResult:
        del raw_bytes
        del job_id
        return PrintResult(ok=True, status_code=200, response="ok")

    def get_diagnostics(self, realtime: bool = False) -> PrinterDiagnostics:
        del realtime
        return PrinterDiagnostics(transport="stub", target=None, connected=None, details={})

    def warmup_session(self) -> PrintResult:
        return PrintResult(ok=True, status_code=200, response="warm")

    def close_session(self) -> PrintResult:
        return PrintResult(ok=True, status_code=200, response="closed")

    def reopen_session(self) -> PrintResult:
        return PrintResult(ok=True, status_code=200, response="reopened")


class _StubGrouper:
    def __init__(self, sections: list[GrocerySection] | None) -> None:
        self._sections = sections

    def group_items(self, list_title: str, items: list[str]) -> list[GrocerySection] | None:
        del list_title
        del items
        return self._sections


class PrintServiceTests(unittest.TestCase):
    def test_create_job_uses_grouped_sections_when_available(self) -> None:
        service = PrintService(
            transport=_StubTransport(),
            grouper=_StubGrouper(
                sections=[GrocerySection(title="Dairy", items=["Milk"])],
            ),
        )
        snapshot = KeepSnapshot(
            note_id="note-1",
            title="Shopping List",
            unchecked_items=["Milk"],
            checked_items=[],
            updated_at=datetime.now(tz=timezone.utc).isoformat(),
        )

        job = service.create_job(snapshot)

        self.assertIsNotNone(job.grouped_sections)
        self.assertEqual("Dairy", job.grouped_sections[0].title)
        self.assertIn(b"Dairy\n", job.raw_bytes)
        self.assertIn(b"- Milk\n", job.raw_bytes)

    def test_create_job_falls_back_to_ungrouped_when_grouper_returns_none(self) -> None:
        service = PrintService(
            transport=_StubTransport(),
            grouper=_StubGrouper(sections=None),
        )
        snapshot = KeepSnapshot(
            note_id="note-2",
            title="Shopping List",
            unchecked_items=["Milk"],
            checked_items=[],
            updated_at=datetime.now(tz=timezone.utc).isoformat(),
        )

        job = service.create_job(snapshot)

        self.assertIsNone(job.grouped_sections)
        self.assertIn(b"- Milk\n", job.raw_bytes)


if __name__ == "__main__":
    unittest.main()
