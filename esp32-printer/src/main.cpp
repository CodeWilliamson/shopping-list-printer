#include <Arduino.h>
#include <ArduinoJson.h>
#include <WebServer.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <NimBLEDevice.h>
#include <PubSubClient.h>

#define LED_BUILTIN 2

const char* WIFI_SSID_VALUE = WIFI_SSID;
const char* WIFI_PASSWORD_VALUE = WIFI_PASSWORD;
const char* API_TOKEN_VALUE = API_TOKEN;
const char* PRINTER_NAME_VALUE = PRINTER_NAME;
const char* PROTOCOL = PROTOCOL_TYPE;
const char* MQTT_BROKER_VALUE = MQTT_BROKER;
const uint16_t MQTT_PORT_VALUE = strtoul(MQTT_PORT, nullptr, 10);
const char* MQTT_USERNAME_VALUE = MQTT_USERNAME;
const char* MQTT_PASSWORD_VALUE = MQTT_PASSWORD;
const char* MQTT_PRINT_TOPIC_VALUE = MQTT_PRINT_TOPIC;
WebServer server(80);
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
String lastError = "none";
String lastJobId = "none";

// Replace with your printer's service/characteristic UUIDs if known
static NimBLEAdvertisedDevice* printerDevice = nullptr;
NimBLEClient* pClient = nullptr;
NimBLERemoteCharacteristic* pRemoteCharacteristic = nullptr;
bool bleConnected = false;
size_t currentPrintBytes = 0;
bool currentPrintFailed = false;
String currentPrintError = "none";

bool isHttpMode() {
  return String(PROTOCOL).equalsIgnoreCase("http");
}

bool isMqttMode() {
  return String(PROTOCOL).equalsIgnoreCase("mqtt");
}


bool printOverBle(const uint8_t* payload, size_t payloadLength) {
  if (!bleConnected || !pRemoteCharacteristic) {
    Serial.println("[printer] BLE not connected or characteristic not found");
    return false;
  }

  constexpr size_t kBleChunkSize = 180;
  Serial.print("[printer] Sending raw ESC/POS bytes over BLE: ");
  Serial.println(payloadLength);

  for (size_t offset = 0; offset < payloadLength; offset += kBleChunkSize) {
    const size_t chunkLength = min(kBleChunkSize, payloadLength - offset);
    if (!pRemoteCharacteristic->writeValue(payload + offset, chunkLength)) {
      Serial.println("[printer] BLE write failed");
      return false;
    }
  }

  return true;
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

void handlePrintBody() {
  HTTPRaw& raw = server.raw();

  if (raw.status == RAW_START) {
    currentPrintBytes = 0;
    currentPrintFailed = false;
    currentPrintError = "none";
    const uint8_t initCommand[] = {0x1B, 0x40}; // ESC @ - initialize printer
    if (!printOverBle(initCommand, sizeof(initCommand))) {
      currentPrintFailed = true;
      currentPrintError = "BLE init failed";
    }
    return;
  }

  if (raw.status == RAW_ABORTED) {
    currentPrintFailed = true;
    currentPrintError = "Request aborted";
    return;
  }

  if (raw.status == RAW_WRITE) {
    if (currentPrintFailed || !isAuthorized()) {
      return;
    }

    if (!printOverBle(raw.buf, raw.currentSize)) {
      currentPrintFailed = true;
      currentPrintError = "BLE write failed";
      return;
    }

    currentPrintBytes += raw.currentSize;
  }

  // when done processing bytes
  if (raw.status == RAW_END) {
    if (currentPrintFailed || !isAuthorized()) {
      return;
    }

    // send line feed and cut command to printer (ESC/POS)
    const uint8_t linefeedCommand[] = {0x1B, 0x64, 0x0A}; // ESC d n - print and feed n lines (n=10)
    const uint8_t cutCommand[] = {0x1D, 0x56, 0x00}; // GS V m - cut paper (m=0 for full cut)
    if (!printOverBle(linefeedCommand, sizeof(linefeedCommand)) ||
        !printOverBle(cutCommand, sizeof(cutCommand))) {
      currentPrintFailed = true;
      currentPrintError = "BLE finalize failed";
    }
  }
}

void handlePrint() {
  if (!isAuthorized()) {
    lastError = "Unauthorized";
    server.send(401, "application/json", "{\"error\":\"Unauthorized\"}");
    return;
  }
  
  if (currentPrintFailed) {
    lastError = currentPrintError;
    server.send(503, "application/json", "{\"error\":\"Printer unavailable\"}");
    return;
  }

  if (currentPrintBytes == 0) {
    lastError = "Empty request body";
    server.send(400, "application/json", "{\"error\":\"Empty request body\"}");
    return;
  }

  lastJobId = server.hasArg("jobId") ? server.arg("jobId") : "unknown";
  lastError = "none";
  String response = String("{\"ok\":true,\"bytes\":") + currentPrintBytes + "}";
  server.send(200, "application/json", response);
}

bool finalizeEscPosJob() {
  const uint8_t linefeedCommand[] = {0x1B, 0x64, 0x0A}; // ESC d n - print and feed n lines (n=10)
  const uint8_t cutCommand[] = {0x1D, 0x56, 0x00};      // GS V m - full cut
  return printOverBle(linefeedCommand, sizeof(linefeedCommand)) &&
         printOverBle(cutCommand, sizeof(cutCommand));
}

void mqttCallback(char* topic, uint8_t* payload, unsigned int length) {
  (void)topic;

  if (!isMqttMode()) {
    return;
  }

  if (!bleConnected) {
    lastError = "Printer unavailable";
    return;
  }

  currentPrintBytes = 0;
  currentPrintFailed = false;
  currentPrintError = "none";

  const uint8_t initCommand[] = {0x1B, 0x40}; // ESC @
  if (!printOverBle(initCommand, sizeof(initCommand))) {
    currentPrintFailed = true;
    currentPrintError = "BLE init failed";
  }

  if (!currentPrintFailed && length > 0 && !printOverBle(payload, length)) {
    currentPrintFailed = true;
    currentPrintError = "BLE write failed";
  }

  if (!currentPrintFailed && !finalizeEscPosJob()) {
    currentPrintFailed = true;
    currentPrintError = "BLE finalize failed";
  }

  if (currentPrintFailed) {
    lastError = currentPrintError;
    return;
  }

  currentPrintBytes = length;
  lastJobId = String(millis());
  lastError = "none";
}

bool ensureMqttConnected() {
  if (!isMqttMode()) {
    return false;
  }

  if (strlen(MQTT_BROKER_VALUE) == 0) {
    lastError = "MQTT broker not configured";
    return false;
  }

  if (mqttClient.connected()) {
    return true;
  }

  String clientId = String("esp32-printer-") + String((uint32_t)ESP.getEfuseMac(), HEX);

  bool connected = false;
  if (strlen(MQTT_USERNAME_VALUE) > 0) {
    connected = mqttClient.connect(clientId.c_str(), MQTT_USERNAME_VALUE, MQTT_PASSWORD_VALUE);
  } else {
    connected = mqttClient.connect(clientId.c_str());
  }

  if (!connected) {
    lastError = String("MQTT connect failed: ") + mqttClient.state();
    return false;
  }

  if (!mqttClient.subscribe(MQTT_PRINT_TOPIC_VALUE)) {
    lastError = "MQTT subscribe failed";
    return false;
  }

  Serial.print("[mqtt] Subscribed to ");
  Serial.println(MQTT_PRINT_TOPIC_VALUE);
  lastError = "none";
  return true;
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT); // Onboard LED pin
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.setHostname("ReceiptPrinter");
  delay(10);
  WiFi.begin(WIFI_SSID_VALUE, WIFI_PASSWORD_VALUE);

  Serial.print("[wifi] Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("[wifi] Connected: ");
  Serial.println(WiFi.localIP());

  if (MDNS.begin("ReceiptPrinter")) {
    Serial.println("mDNS responder started");
  }

  if (isHttpMode()) {
    server.on("/status", HTTP_GET, handleStatus);
    server.on("/print", HTTP_POST, handlePrint, handlePrintBody);
    server.begin();
    Serial.println("[server] HTTP server started");
  } else if (isMqttMode()) {
    mqttClient.setServer(MQTT_BROKER_VALUE, MQTT_PORT_VALUE);
    mqttClient.setCallback(mqttCallback);
    ensureMqttConnected();
    Serial.print("[mqtt] Protocol selected, broker=");
    Serial.print(MQTT_BROKER_VALUE);
    Serial.print(":");
    Serial.println(MQTT_PORT_VALUE);
  } else {
    Serial.print("[protocol] Unsupported PROTOCOL value: ");
    Serial.println(PROTOCOL);
  }

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
    // blink esp32 onboard LED 3 times in a loop to indicate print job received
    for (int i = 0; i < 3; i++) {
      digitalWrite(LED_BUILTIN, HIGH);
      delay(250);
      digitalWrite(LED_BUILTIN, LOW);
      delay(250);
    }
    const uint8_t lineFeed[] = {0x0A}; // LF - line feed
    printOverBle(lineFeed, sizeof(lineFeed));
  } else {
    Serial.println("[BLE] Printer not found or failed to connect");
  }
}

void loop() {
  if (isHttpMode()) {
    server.handleClient();
  } else if (isMqttMode()) {
    if (ensureMqttConnected()) {
      mqttClient.loop();
    }
    delay(10);
  }
}
