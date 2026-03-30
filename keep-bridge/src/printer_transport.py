from __future__ import annotations

import asyncio
import threading
import time
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

    def get_diagnostics(self, realtime: bool = False) -> PrinterDiagnostics:
        ...

    def warmup_session(self) -> PrintResult:
        ...

    def close_session(self) -> PrintResult:
        ...

    def reopen_session(self) -> PrintResult:
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

    def get_diagnostics(self, realtime: bool = False) -> PrinterDiagnostics:
        del realtime
        return PrinterDiagnostics(
            transport=self.transport_name,
            target=self._config.esp32_print_url,
            connected=None,
            details={
                "mode": "http-forward",
                "sessionControlSupported": False,
            },
        )

    def warmup_session(self) -> PrintResult:
        return PrintResult(ok=True, status_code=200, response="No persistent session required for esp32_http transport")

    def close_session(self) -> PrintResult:
        return PrintResult(ok=True, status_code=200, response="No active BLE session to close for esp32_http transport")

    def reopen_session(self) -> PrintResult:
        return PrintResult(ok=True, status_code=200, response="No BLE session to reopen for esp32_http transport")


class BlePrinterTransport:
    transport_name = "bluetooth_ble"

    def __init__(self, config: PrinterConfig) -> None:
        self._config = config
        self._loop = asyncio.new_event_loop()
        self._loop_lock = threading.Lock()
        self._bleak: Any | None = None
        self._client: Any | None = None
        self._characteristic: Any | None = None
        self._use_response: bool = False
        self._last_connected_address: str | None = None
        self._last_error: str | None = None
        self._connection_started_at: float | None = None
        self._last_activity_at: float | None = None

    def send(self, raw_bytes: bytes, job_id: str) -> PrintResult:
        del job_id
        with self._loop_lock:
            try:
                self._run_on_loop(self._send_async(raw_bytes))
                self._last_error = None
                return PrintResult(ok=True, status_code=None, response="Printed over BLE")
            except Exception as error:  # noqa: BLE001
                self._last_error = str(error) if str(error) else error.__class__.__name__
                return PrintResult(ok=False, status_code=None, response=self._last_error)

    def get_diagnostics(self, realtime: bool = False) -> PrinterDiagnostics:
        with self._loop_lock:
            target = self._last_connected_address or self._config.ble_device_address or self._config.ble_device_name or None
            details: dict[str, Any] = {
                "deviceName": self._config.ble_device_name or None,
                "deviceAddress": self._config.ble_device_address or None,
                "connectPerJob": self._config.connect_per_job,
                "idleTimeoutSeconds": self._config.ble_idle_timeout_seconds,
                "sessionControlSupported": True,
                "lastError": self._last_error,
                "connectionStartedAt": self._connection_started_at,
                "lastActivityAt": self._last_activity_at,
                "connectionAgeSeconds": _seconds_since(self._connection_started_at),
                "idleSeconds": _seconds_since(self._last_activity_at),
            }
            connected: bool | None = self._is_client_connected()

            if realtime:
                try:
                    probe = self._run_on_loop(self._probe_async())
                    target = probe["target"]
                    connected = probe["connected"]
                    details.update(probe["details"])
                    self._last_error = None
                except Exception as error:  # noqa: BLE001
                    message = str(error) if str(error) else error.__class__.__name__
                    connected = False
                    details["realtimeError"] = message
                    self._last_error = message

            return PrinterDiagnostics(
                transport=self.transport_name,
                target=target,
                connected=connected,
                details=details,
            )

    def warmup_session(self) -> PrintResult:
        with self._loop_lock:
            try:
                self._run_on_loop(self._ensure_connected_async())
                self._last_error = None
                response = "BLE session connected"
                if self._config.connect_per_job:
                    self._run_on_loop(self._disconnect_async())
                    response = "BLE session warmup probe succeeded (connect_per_job=true, connection closed)"
                return PrintResult(ok=True, status_code=200, response=response)
            except Exception as error:  # noqa: BLE001
                self._last_error = str(error) if str(error) else error.__class__.__name__
                return PrintResult(ok=False, status_code=None, response=self._last_error)

    def close_session(self) -> PrintResult:
        with self._loop_lock:
            try:
                self._run_on_loop(self._disconnect_async())
                self._last_error = None
                return PrintResult(ok=True, status_code=200, response="BLE session closed")
            except Exception as error:  # noqa: BLE001
                self._last_error = str(error) if str(error) else error.__class__.__name__
                return PrintResult(ok=False, status_code=None, response=self._last_error)

    def reopen_session(self) -> PrintResult:
        with self._loop_lock:
            try:
                self._run_on_loop(self._disconnect_async())
                self._run_on_loop(self._ensure_connected_async())
                self._last_error = None
                response = "BLE session reopened"
                if self._config.connect_per_job:
                    self._run_on_loop(self._disconnect_async())
                    response = "BLE session reopened and closed (connect_per_job=true)"
                return PrintResult(ok=True, status_code=200, response=response)
            except Exception as error:  # noqa: BLE001
                self._last_error = str(error) if str(error) else error.__class__.__name__
                return PrintResult(ok=False, status_code=None, response=self._last_error)

    async def _send_async(self, raw_bytes: bytes) -> None:
        await self._ensure_connected_async()
        if self._client is None or self._characteristic is None:
            raise RuntimeError("BLE connection not initialized")

        framed_payload = _frame_ble_job(
            raw_bytes,
            feed_lines=self._config.job_feed_lines,
            auto_cut=self._config.auto_cut,
        )
        for offset in range(0, len(framed_payload), self._config.write_chunk_size):
            chunk = framed_payload[offset : offset + self._config.write_chunk_size]
            await self._client.write_gatt_char(self._characteristic, chunk, response=self._use_response)
        self._last_activity_at = time.time()

        if self._config.connect_per_job:
            await self._disconnect_async()

    async def _probe_async(self) -> dict[str, Any]:
        await self._ensure_connected_async()
        if self._client is None or self._characteristic is None:
            raise RuntimeError("BLE connection not initialized")

        services = getattr(self._client, "services", None)
        service_count = len(list(services)) if services is not None else 0
        target = self._last_connected_address or self._config.ble_device_address or self._config.ble_device_name
        probe = {
            "target": target,
            "connected": bool(self._client.is_connected),
            "details": {
                "realtimeCheckedAt": time.time(),
                "writableCharacteristic": str(getattr(self._characteristic, "uuid", "unknown")),
                "writeMode": "with-response" if self._use_response else "without-response",
                "servicesDiscovered": service_count,
                "connectionAgeSeconds": _seconds_since(self._connection_started_at),
                "idleSeconds": _seconds_since(self._last_activity_at),
            },
        }

        if self._config.connect_per_job:
            await self._disconnect_async()
        return probe

    async def _ensure_connected_async(self) -> None:
        if self._is_client_connected(): #and not self._should_reset_idle_connection()
            return

        await self._disconnect_async()

        bleak = self._get_bleak()
        device = await self._discover_device(bleak.BleakScanner)
        self._last_connected_address = getattr(device, "address", None)
        self._client = bleak.BleakClient(device, timeout=self._config.ble_connect_timeout_seconds)
        await self._client.connect()
        if not self._client.is_connected:
            raise RuntimeError("Failed to connect to BLE printer")

        characteristic, use_response = await self._find_writable_characteristic(self._client)
        self._characteristic = characteristic
        self._use_response = use_response
        now = time.time()
        self._connection_started_at = now
        self._last_activity_at = now

    async def _disconnect_async(self) -> None:
        if self._client is not None:
            try:
                if self._client.is_connected:
                    await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        self._client = None
        self._characteristic = None
        self._use_response = False

    def _should_reset_idle_connection(self) -> bool:
        if self._config.connect_per_job:
            return True
        timeout = self._config.ble_idle_timeout_seconds
        if timeout <= 0:
            return False
        idle_seconds = _seconds_since(self._last_activity_at)
        return idle_seconds is not None and idle_seconds >= timeout

    def _is_client_connected(self) -> bool:
        return bool(self._client is not None and self._client.is_connected)

    def _run_on_loop(self, coro: Any) -> Any:
        return self._loop.run_until_complete(coro)

    def _get_bleak(self) -> Any:
        if self._bleak is None:
            self._bleak = _import_bleak()
        return self._bleak

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
        import bleak  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "The 'bleak' package is required for PRINTER_TRANSPORT=bluetooth_ble. Install dependencies from requirements.txt."
        ) from error
    return bleak


def _seconds_since(timestamp: float | None) -> float | None:
    if timestamp is None:
        return None
    return max(0.0, time.time() - timestamp)