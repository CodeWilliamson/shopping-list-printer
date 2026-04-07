# Shopping List Printer MVP

Voice to thermal printer flow:
1. You ask Google Nest Mini to print the shopping list.
2. Google Home triggers an openHAB item/action.
3. openHAB (or any client) calls keep-bridge.
4. keep-bridge fetches the Google Keep list, builds ESC/POS bytes, and forwards them to the ESP32 `/print` endpoint.
5. ESP32 prints to printer over Bluetooth (BLE).

## Repository Layout

- `keep-bridge/`: Python Flask service for Google Keep access and print forwarding.
- `openhab-automation/`: openHAB items/rules/things snippets.
- `esp32-printer/`: ESP32 firmware skeleton for authenticated print endpoint and printer transport.

## Current Status

This baseline includes:
- Python keep-bridge service with Google Keep integration via `gkeepapi`.
- Keep token keepalive sync loop (default every hour).
- API endpoints to fetch list data and trigger print forwarding.
- ESP32 firmware with `/print` and `/status` endpoints.

## Quick Start

### 1) Keep Bridge (Python)

```bash
cd keep-bridge
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create or update `keep-bridge/.env` with:

```env
KEEP_EMAIL=you@gmail.com
KEEP_MASTER_TOKEN=
KEEP_KEEPALIVE_POLL_SECONDS=3600
KEEP_USE_MOCK=false
KEEP_STATE_FILE=keep_state.json
PORT=3001

PRINTER_TRANSPORT=bluetooth_ble
PRINTER_BLE_DEVICE_NAME=ReceiptPrinter
PRINTER_BLE_DEVICE_ADDRESS=
PRINTER_BLE_SCAN_TIMEOUT_SECONDS=8
PRINTER_BLE_CONNECT_TIMEOUT_SECONDS=10
PRINTER_BLE_IDLE_TIMEOUT_SECONDS=300
PRINTER_WRITE_CHUNK_SIZE=180
PRINTER_JOB_FEED_LINES=6
PRINTER_AUTO_CUT=true
PRINTER_CONNECT_PER_JOB=true

GROCERY_GROUPING_ENABLED=true
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini
GROCERY_STORE_CONTEXT=No Frills and Metro in Ontario, Canada
GROCERY_GROUPING_TIMEOUT_SECONDS=12

ESP32_PRINT_URL=http://esp32-printer.local/print
ESP32_API_TOKEN=
```

Generate `KEEP_MASTER_TOKEN` using the included bootstrap helper:

```bash
cd keep-bridge
.venv/bin/python src/bootstrap_token.py
```

Then start the server:

```bash
cd keep-bridge
.venv/bin/python src/server.py
```

The service listens on `PORT` (default `3001`).

Printer transport options:
- `PRINTER_TRANSPORT=bluetooth_ble`: print directly from Raspberry Pi over BLE.
- `PRINTER_TRANSPORT=esp32_http`: keep forwarding to the ESP32 bridge.

BLE connection behavior:
- `PRINTER_CONNECT_PER_JOB=true`: connect/disconnect every print.
- `PRINTER_CONNECT_PER_JOB=false`: reuse a persistent BLE connection between prints.
- `PRINTER_BLE_IDLE_TIMEOUT_SECONDS`: when using a persistent connection, disconnect after this many idle seconds (`0` disables idle disconnect).

### 2) Keep Bridge API

Health check:

```bash
curl -s "http://127.0.0.1:3001/health"
```

Fetch a Keep list by title:

```bash
curl -s "http://127.0.0.1:3001/list?name=Shopping%20list"
```

Response includes:
- `noteId`, `title`, `uncheckedItems`, `checkedItems`, `updatedAt`
- `outputEncoding` and `output` (ESC/POS byte array for unchecked items)

Print a Keep list by title (forwards ESC/POS raw bytes to ESP32 `/print`):

```bash
curl -s -X POST "http://127.0.0.1:3001/print-list" \
	-H "Content-Type: application/json" \
	-d '{"title":"Shopping list"}'

Printer diagnostics:

```bash
curl -s "http://127.0.0.1:3001/printer-status"
```

`/printer-status` performs a realtime connectivity probe by default for `PRINTER_TRANSPORT=bluetooth_ble`.
Use `realtime=false` to return cached diagnostics without trying to connect:

```bash
curl -s "http://127.0.0.1:3001/printer-status?realtime=false"
```

Manual BLE session controls:

```bash
curl -s -X POST "http://127.0.0.1:3001/printer-session/close"
curl -s -X POST "http://127.0.0.1:3001/printer-session/reopen"
```

On server startup, keep-bridge now performs a printer session warmup attempt and logs the result.
```

`/print-list` behavior:
- Returns `404` if the list title is not found.
- Returns `502` if Keep fetch or ESP32 forwarding fails.
- Returns `200` with `jobId` and `bytesSent` on success.

AI grocery grouping:
- Grouping happens inside `keep-bridge` before print rendering.
- Uses OpenAI Responses API when `GROCERY_GROUPING_ENABLED=true` and `OPENAI_API_KEY` is set.
- Items are preserved exactly as text from Keep; if AI output is invalid or unavailable, printing falls back to the ungrouped list.
- `groupedSections` is included in the `/print-list` response when grouping is used.

### 3) openHAB Snippets

Copy files under `openhab-automation/` into your openHAB config folders and adapt hostnames/tokens.

### 4) ESP32 Firmware

Open `esp32-printer/` in PlatformIO, set Wi-Fi/token constants, and upload.
