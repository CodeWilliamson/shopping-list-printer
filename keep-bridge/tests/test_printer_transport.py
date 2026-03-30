from __future__ import annotations

import unittest

from src.config import PrinterConfig
from src.printer_transport import BlePrinterTransport, Esp32HttpPrinterTransport, create_printer_transport


class PrinterTransportTests(unittest.TestCase):
    def test_factory_returns_esp32_transport(self) -> None:
        config = PrinterConfig(
            transport="esp32_http",
            esp32_print_url="http://printer.local/print",
            esp32_api_token="token",
            ble_device_name="",
            ble_device_address="",
            ble_scan_timeout_seconds=8,
            ble_connect_timeout_seconds=10,
            write_chunk_size=180,
            job_feed_lines=6,
            auto_cut=True,
            connect_per_job=True,
        )

        transport = create_printer_transport(config)

        self.assertIsInstance(transport, Esp32HttpPrinterTransport)

    def test_factory_returns_ble_transport(self) -> None:
        config = PrinterConfig(
            transport="bluetooth_ble",
            esp32_print_url="http://printer.local/print",
            esp32_api_token="token",
            ble_device_name="ReceiptPrinter",
            ble_device_address="",
            ble_scan_timeout_seconds=8,
            ble_connect_timeout_seconds=10,
            write_chunk_size=180,
            job_feed_lines=6,
            auto_cut=True,
            connect_per_job=True,
        )

        transport = create_printer_transport(config)

        self.assertIsInstance(transport, BlePrinterTransport)


if __name__ == "__main__":
    unittest.main()