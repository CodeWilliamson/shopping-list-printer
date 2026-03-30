from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


@dataclass(frozen=True)
class AppConfig:
    port: int
    keepalive_poll_seconds: int


@dataclass(frozen=True)
class PrinterConfig:
    transport: str
    esp32_print_url: str
    esp32_api_token: str
    ble_device_name: str
    ble_device_address: str
    ble_scan_timeout_seconds: float
    ble_connect_timeout_seconds: float
    write_chunk_size: int
    job_feed_lines: int
    auto_cut: bool
    connect_per_job: bool


@dataclass(frozen=True)
class Settings:
    app: AppConfig
    printer: PrinterConfig


def load_settings() -> Settings:
    load_dotenv()

    settings = Settings(
        app=AppConfig(
            port=_parse_int(os.getenv("PORT"), 3001),
            keepalive_poll_seconds=_parse_int(os.getenv("KEEP_KEEPALIVE_POLL_SECONDS"), 3600),
        ),
        printer=PrinterConfig(
            transport=os.getenv("PRINTER_TRANSPORT", "esp32_http").strip() or "esp32_http",
            esp32_print_url=os.getenv("ESP32_PRINT_URL", "http://ReceiptPrinter.local/print").strip(),
            esp32_api_token=os.getenv("ESP32_API_TOKEN", "").strip(),
            ble_device_name=os.getenv("PRINTER_BLE_DEVICE_NAME", "").strip(),
            ble_device_address=os.getenv("PRINTER_BLE_DEVICE_ADDRESS", "").strip(),
            ble_scan_timeout_seconds=float(os.getenv("PRINTER_BLE_SCAN_TIMEOUT_SECONDS", "8")),
            ble_connect_timeout_seconds=float(os.getenv("PRINTER_BLE_CONNECT_TIMEOUT_SECONDS", "10")),
            write_chunk_size=_parse_int(os.getenv("PRINTER_WRITE_CHUNK_SIZE"), 180),
            job_feed_lines=_parse_int(os.getenv("PRINTER_JOB_FEED_LINES"), 6),
            auto_cut=_parse_bool(os.getenv("PRINTER_AUTO_CUT"), True),
            connect_per_job=_parse_bool(os.getenv("PRINTER_CONNECT_PER_JOB"), True),
        ),
    )

    _validate_printer_settings(settings.printer)
    return settings


def _validate_printer_settings(config: PrinterConfig) -> None:
    supported_transports = {"esp32_http", "bluetooth_ble"}
    if config.transport not in supported_transports:
        raise RuntimeError(
            f"Unsupported PRINTER_TRANSPORT '{config.transport}'. Supported values: {sorted(supported_transports)}"
        )

    if config.transport == "esp32_http" and not config.esp32_api_token:
        raise RuntimeError("Missing required environment variable: ESP32_API_TOKEN")

    if config.transport == "bluetooth_ble" and not (config.ble_device_name or config.ble_device_address):
        raise RuntimeError(
            "Set PRINTER_BLE_DEVICE_NAME or PRINTER_BLE_DEVICE_ADDRESS when PRINTER_TRANSPORT=bluetooth_ble"
        )

    if config.write_chunk_size <= 0:
        raise RuntimeError("PRINTER_WRITE_CHUNK_SIZE must be greater than zero")

    if config.job_feed_lines < 0 or config.job_feed_lines > 255:
        raise RuntimeError("PRINTER_JOB_FEED_LINES must be between 0 and 255")