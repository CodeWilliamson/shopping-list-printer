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
ESP32_PRINT_URL=http://esp32-printer.local/print
ESP32_API_TOKEN=
KEEP_USE_MOCK=false
KEEP_STATE_FILE=keep_state.json
PORT=3001
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
```

`/print-list` behavior:
- Returns `404` if the list title is not found.
- Returns `502` if Keep fetch or ESP32 forwarding fails.
- Returns `200` with `jobId` and `bytesSent` on success.

### 3) openHAB Snippets

Copy files under `openhab-automation/` into your openHAB config folders and adapt hostnames/tokens.

### 4) ESP32 Firmware

Open `esp32-printer/` in PlatformIO, set Wi-Fi/token constants, and upload.
