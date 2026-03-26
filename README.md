# Shopping List Printer MVP

Voice to thermal printer flow:
1. You ask Google Nest Mini to print the shopping list.
2. Google Home triggers an openHAB item/action.
3. openHAB calls the ESP32 `/print` endpoint over Wi-Fi.
4. ESP32 prints to printer over Bluetooth (BLE).

## Repository layout

- `keep-bridge/`: Google Keep polling + openHAB trigger helper service.
- `openhab-automation/`: openHAB items/rules/things snippets.
- `esp32-printer/`: ESP32 firmware skeleton for authenticated print endpoint and printer transport.

## MVP status

This baseline includes:
- Shared print job contract.
- Keep bridge service skeleton with polling loop and endpoints.
- openHAB item/rule templates.
- ESP32 firmware skeleton with `/print` and `/status`.

## Quick start

### 1) Keep bridge

```bash
cd keep-bridge
npm install
cp ../.env.example .env
npm run dev
```

By default `.env.example` starts with `KEEP_USE_MOCK=true`.

To use your real Google Keep list:
1. In Google Cloud, enable Google Keep API and create an OAuth client.
2. Fill `KEEP_GOOGLE_CLIENT_ID`, `KEEP_GOOGLE_CLIENT_SECRET`, `KEEP_GOOGLE_REDIRECT_URI`, and `KEEP_TARGET_NOTE_ID`.
3. Run OAuth bootstrap to get a refresh token:

```bash
npm run oauth:bootstrap
```

4. Put the returned `KEEP_GOOGLE_REFRESH_TOKEN` in `.env`.
5. Set `KEEP_USE_MOCK=false` and restart keep-bridge.

### 2) openHAB snippets

Copy files under `openhab-automation/` into your openHAB config folders and adapt hostnames/tokens.

### 3) ESP32 firmware

Open `esp32-printer/` in PlatformIO, set Wi-Fi/token constants, and upload.
