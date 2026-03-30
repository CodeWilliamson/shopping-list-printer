from __future__ import annotations

import asyncio
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
import sys
from typing import Any, Protocol

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import PrinterConfig


@dataclass(frozen=True)
class PrintResult:
    ok: bool
    status_code: int | None
    response: str


@dataclass(frozen=True)
class PrinterDiagnostics:
    transport: str
    target: str | None
    connected: bool | None
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PrinterTransport(Protocol):
    transport_name: str

    def send(self, raw_bytes: bytes, job_id: str) -> PrintResult:
        ...

    def get_diagnostics(self) -> PrinterDiagnostics:
        ...


class Esp32HttpPrinterTransport:
    transport_name = "esp32_http"

    def __init__(self, config: PrinterConfig) -> None:
        self._config = config

    def send(self, raw_bytes: bytes, job_id: str) -> PrintResult:
        payload = bytes(raw_bytes)
        request_url = f"{self._config.esp32_print_url}?jobId={urllib.parse.quote(job_id)}"
        req = urllib.request.Request(
            request_url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._config.esp32_api_token}",
                "Content-Type": "application/octet-stream",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                status_code = response.getcode()
                body = response.read().decode("utf-8", errors="replace")
                return PrintResult(ok=200 <= status_code < 300, status_code=status_code, response=body)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            return PrintResult(ok=False, status_code=error.code, response=body)
        except Exception as error:  # noqa: BLE001
            return PrintResult(ok=False, status_code=None, response=str(error))

    def get_diagnostics(self) -> PrinterDiagnostics:
        return PrinterDiagnostics(
            transport=self.transport_name,
            target=self._config.esp32_print_url,
            connected=None,
            details={"mode": "http-forward"},
        )


class BlePrinterTransport:
    transport_name = "bluetooth_ble"

    def __init__(self, config: PrinterConfig) -> None:
        self._config = config
        self._last_connected_address: str | None = None
        self._last_error: str | None = None

    def send(self, raw_bytes: bytes, job_id: str) -> PrintResult:
        del job_id
        try:
            asyncio.run(self._send_async(raw_bytes))
            self._last_error = None
            return PrintResult(ok=True, status_code=None, response="Printed over BLE")
        except Exception as error:  # noqa: BLE001
            self._last_error = str(error) if str(error) else error.__class__.__name__
            return PrintResult(ok=False, status_code=None, response=self._last_error)

    def get_diagnostics(self) -> PrinterDiagnostics:
        target = self._last_connected_address or self._config.ble_device_address or self._config.ble_device_name or None
        return PrinterDiagnostics(
            transport=self.transport_name,
            target=target,
            connected=None,
            details={
                "deviceName": self._config.ble_device_name or None,
                "deviceAddress": self._config.ble_device_address or None,
                "connectPerJob": self._config.connect_per_job,
                "lastError": self._last_error,
            },
        )

    async def _send_async(self, raw_bytes: bytes) -> None:
        bleak = _import_bleak()
        device = await self._discover_device(bleak.BleakScanner)
        self._last_connected_address = getattr(device, "address", None)

        async with bleak.BleakClient(device, timeout=self._config.ble_connect_timeout_seconds) as client:
            characteristic, use_response = await self._find_writable_characteristic(client)
            framed_payload = _frame_ble_job(
                raw_bytes,
                feed_lines=self._config.job_feed_lines,
                auto_cut=self._config.auto_cut,
            )
            for offset in range(0, len(framed_payload), self._config.write_chunk_size):
                chunk = framed_payload[offset : offset + self._config.write_chunk_size]
                await client.write_gatt_char(characteristic, chunk, response=use_response)

    async def _discover_device(self, scanner_cls: Any) -> Any:
        if self._config.ble_device_address:
            devices = await scanner_cls.discover(timeout=self._config.ble_scan_timeout_seconds)
            for device in devices:
                if getattr(device, "address", "").casefold() == self._config.ble_device_address.casefold():
                    return device
            raise RuntimeError(f"BLE printer not found by address: {self._config.ble_device_address}")

        devices = await scanner_cls.discover(timeout=self._config.ble_scan_timeout_seconds)
        for device in devices:
            name = (getattr(device, "name", None) or getattr(device, "local_name", None) or "").strip()
            if name.casefold() == self._config.ble_device_name.casefold():
                return device

        raise RuntimeError(f"BLE printer not found by name: {self._config.ble_device_name}")

    async def _find_writable_characteristic(self, client: Any) -> tuple[Any, bool]:
        services = getattr(client, "services", None)
        if services is None:
            services = await client.get_services()

        for service in services:
            for characteristic in service.characteristics:
                properties = set(getattr(characteristic, "properties", []))
                if "write-without-response" in properties:
                    return characteristic, False
                if "write" in properties:
                    return characteristic, True

        raise RuntimeError("No writable BLE characteristic found on printer")


def create_printer_transport(config: PrinterConfig) -> PrinterTransport:
    if config.transport == "esp32_http":
        return Esp32HttpPrinterTransport(config)
    if config.transport == "bluetooth_ble":
        return BlePrinterTransport(config)
    raise RuntimeError(f"Unsupported PRINTER_TRANSPORT: {config.transport}")


def _frame_ble_job(raw_bytes: bytes, feed_lines: int, auto_cut: bool) -> bytes:
    payload = bytearray()
    payload.extend(b"\x1b\x40")
    payload.extend(raw_bytes)
    payload.extend(b"\x1b\x64")
    payload.append(feed_lines)
    if auto_cut:
        payload.extend(b"\x1d\x56\x00")
    return bytes(payload)


def _import_bleak() -> Any:
    try:
        import bleak
    except ImportError as error:
        raise RuntimeError(
            "The 'bleak' package is required for PRINTER_TRANSPORT=bluetooth_ble. Install dependencies from requirements.txt."
        ) from error
    return bleak