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
    apileague_api_key: str

@dataclass(frozen=True)
class DailyFunConfig:
    apileague_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from_addr: str
    smtp_to_addr: str

@dataclass(frozen=True)
class PrinterConfig:
    transport: str
    esp32_print_url: str
    esp32_api_token: str
    ble_device_name: str
    ble_device_address: str
    ble_scan_timeout_seconds: float
    ble_connect_timeout_seconds: float
    ble_idle_timeout_seconds: float
    write_chunk_size: int
    job_feed_lines: int
    auto_cut: bool
    connect_per_job: bool


@dataclass(frozen=True)
class OpenAIConfig:
    openai_api_key: str
    openai_model: str
    request_timeout_seconds: float

@dataclass(frozen=True)
class GroceryGroupingConfig:
    enabled: bool
    store_context: str


@dataclass(frozen=True)
class Settings:
    app: AppConfig
    printer: PrinterConfig
    openai: OpenAIConfig
    grouping: GroceryGroupingConfig
    daily_fun: DailyFunConfig


def load_settings() -> Settings:
    load_dotenv()

    settings = Settings(
        app=AppConfig(
            port=_parse_int(os.getenv("PORT"), 3001),
            keepalive_poll_seconds=_parse_int(os.getenv("KEEP_KEEPALIVE_POLL_SECONDS"), 3600),
            apileague_api_key=os.getenv("APILEAGUE_API_KEY", "").strip(),
        ),
        printer=PrinterConfig(
            transport=os.getenv("PRINTER_TRANSPORT", "bluetooth_ble").strip(),
            esp32_print_url=os.getenv("ESP32_PRINT_URL", "http://ReceiptPrinter.local/print").strip(),
            esp32_api_token=os.getenv("ESP32_API_TOKEN", "").strip(),
            ble_device_name=os.getenv("PRINTER_BLE_DEVICE_NAME", "").strip(),
            ble_device_address=os.getenv("PRINTER_BLE_DEVICE_ADDRESS", "").strip(),
            ble_scan_timeout_seconds=float(os.getenv("PRINTER_BLE_SCAN_TIMEOUT_SECONDS", "8")),
            ble_connect_timeout_seconds=float(os.getenv("PRINTER_BLE_CONNECT_TIMEOUT_SECONDS", "10")),
            ble_idle_timeout_seconds=float(os.getenv("PRINTER_BLE_IDLE_TIMEOUT_SECONDS", "300")),
            write_chunk_size=_parse_int(os.getenv("PRINTER_WRITE_CHUNK_SIZE"), 180),
            job_feed_lines=_parse_int(os.getenv("PRINTER_JOB_FEED_LINES"), 6),
            auto_cut=_parse_bool(os.getenv("PRINTER_AUTO_CUT"), True),
            connect_per_job=_parse_bool(os.getenv("PRINTER_CONNECT_PER_JOB"), True),
        ),
        openai=OpenAIConfig(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            request_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "12")),
        ),
        grouping=GroceryGroupingConfig(
            enabled=_parse_bool(os.getenv("GROCERY_GROUPING_ENABLED"), True),
            store_context=os.getenv("GROCERY_STORE_CONTEXT", "No Frills and Metro").strip()
            or "No Frills and Metro",
        ),
        daily_fun=DailyFunConfig(
            apileague_api_key=os.getenv("APILEAGUE_API_KEY", "").strip(),
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
            smtp_port=_parse_int(os.getenv("SMTP_PORT"), 587),
            smtp_user=os.getenv("SMTP_USER", "").strip(),
            smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
            smtp_from_addr=os.getenv("SMTP_FROM_ADDR", "").strip(),
            smtp_to_addr=os.getenv("SMTP_TO_ADDR", "").strip(),
        ),

    )

    _validate_printer_settings(settings.printer)
    return settings


def _validate_printer_settings(config: PrinterConfig) -> None:
    supported_transports = {"esp32_http", "bluetooth_ble", "mock_ble"}
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

    if config.ble_idle_timeout_seconds < 0:
        raise RuntimeError("PRINTER_BLE_IDLE_TIMEOUT_SECONDS must be greater than or equal to zero")