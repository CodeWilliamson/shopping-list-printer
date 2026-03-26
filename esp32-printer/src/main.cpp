#include <Arduino.h>
#include <ArduinoJson.h>
#include <WebServer.h>
#include <WiFi.h>
#include <NimBLEDevice.h>

#define LED_BUILTIN 2

#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI_SSID"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif
#ifndef API_TOKEN
#define API_TOKEN "YOUR_API_TOKEN"
#endif
#ifndef PRINTER_NAME
#define PRINTER_NAME "YOUR_PRINTER_NAME"
#endif

const char* WIFI_SSID_VALUE = WIFI_SSID;
const char* WIFI_PASSWORD_VALUE = WIFI_PASSWORD;
const char* API_TOKEN_VALUE = API_TOKEN;
const char* PRINTER_NAME_VALUE = PRINTER_NAME;
WebServer server(80);
String lastError = "none";
String lastJobId = "none";

// Replace with your printer's service/characteristic UUIDs if known
static NimBLEAdvertisedDevice* printerDevice = nullptr;
NimBLEClient* pClient = nullptr;
NimBLERemoteCharacteristic* pRemoteCharacteristic = nullptr;
bool bleConnected = false;


void printOverBle(const String& payload) {
  if (!bleConnected || !pRemoteCharacteristic) {
    Serial.println("[printer] BLE not connected or characteristic not found");
    return;
  }
  Serial.println("[printer] BLE print payload:");
  Serial.println(payload);
  // Send as plain text (may need to chunk for large payloads)
  String payloadWithLineFeeds = payload + "\n\n\n\n\n\n\n\n\n\n\n\n";
  pRemoteCharacteristic->writeValue((uint8_t*)payloadWithLineFeeds.c_str(), payloadWithLineFeeds.length());
}

// BLE scan callback
class PrinterAdvertisedDeviceCallbacks : public NimBLEScanCallbacks {
public:
  void onResult(const NimBLEAdvertisedDevice* advertisedDevice) {
    if (advertisedDevice->getName() == PRINTER_NAME_VALUE) {
      Serial.print("[BLE] Found printer: ");
      Serial.println(advertisedDevice->toString().c_str());
      printerDevice = new NimBLEAdvertisedDevice(*advertisedDevice);
      NimBLEDevice::getScan()->stop();
    }
  }
};

bool connectToPrinter() {
  if (!printerDevice) return false;
  pClient = NimBLEDevice::createClient();
  Serial.println("[BLE] Connecting to printer...");
  if (!pClient->connect(printerDevice)) {
    Serial.println("[BLE] Failed to connect");
    return false;
  }
  Serial.println("[BLE] Connected!");
  // Discover all services
  const auto& services = pClient->getServices(true);
  for (auto* pService : services) {
    Serial.print("[BLE] Service: ");
    Serial.println(pService->getUUID().toString().c_str());
    // Try to find a writable characteristic
    for (auto* c : pService->getCharacteristics(true)) {
      Serial.print("[BLE] Characteristic: ");
      Serial.print(c->getUUID().toString().c_str());
      Serial.print(" canWrite=");
      Serial.println(c->canWrite());
      if (c->canWrite()) {
        pRemoteCharacteristic = c;
        break;
      }
    }
    if (pRemoteCharacteristic) break;
  }
  if (!pRemoteCharacteristic) {
    Serial.println("[BLE] Writable characteristic not found");
    return false;
  }
  bleConnected = true;
  return true;
}

void handleStatus() {
  JsonDocument doc;
  doc["ok"] = true;
  doc["lastJobId"] = lastJobId;
  doc["lastError"] = lastError;

  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

bool isAuthorized() {
  String auth = server.header("Authorization");
  String expected = String("Bearer ") + API_TOKEN_VALUE;
  return auth == expected;
}

void handlePrint() {
  if (!isAuthorized()) {
    server.send(401, "application/json", "{\"error\":\"Unauthorized\"}");
    return;
  }

  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"error\":\"Missing JSON body\"}");
    return;
  }

  JsonDocument doc;
  const String body = server.arg("plain");
  // const auto error = deserializeJson(doc, body);

  // if (error) {
  //   lastError = String("JSON parse failed: ") + error.c_str();
  //   server.send(400, "application/json", "{\"error\":\"Invalid JSON\"}");
  //   return;
  // }

  const char* jobId = doc["jobId"] | "unknown";
  lastJobId = jobId;

  printOverBle(body);
  server.send(200, "application/json", "{\"ok\":true}");
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT); // Onboard LED pin
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID_VALUE, WIFI_PASSWORD_VALUE);

  Serial.print("[wifi] Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("[wifi] Connected: ");
  Serial.println(WiFi.localIP());

  server.on("/status", HTTP_GET, handleStatus);
  server.on("/print", HTTP_POST, handlePrint);
  server.begin();

  Serial.println("[server] HTTP server started");


  NimBLEDevice::init("");
  NimBLEScan* pScan = NimBLEDevice::getScan();
  pScan->setScanCallbacks(new PrinterAdvertisedDeviceCallbacks());
  pScan->setActiveScan(true);
  Serial.println("[BLE] Scanning for printer...");
  pScan->start(20000, false);
  while (pScan->isScanning()) {
    delay(100);
  }
  if (printerDevice && connectToPrinter()) {
    Serial.println("[BLE] Ready to print!");
    // ESC/POS test print (example)
    String test = String((char)0x1B) + "";
    // blink esp32 onboard LED 3 times in a loop to indicate print job received
    for (int i = 0; i < 3; i++) {
      digitalWrite(LED_BUILTIN, HIGH);
      delay(250);
      digitalWrite(LED_BUILTIN, LOW);
      delay(250);
    }
  } else {
    Serial.println("[BLE] Printer not found or failed to connect");
  }
}

void loop() {
  server.handleClient();
}
