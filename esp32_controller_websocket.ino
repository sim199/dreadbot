#include <WiFi.h>
#include <esp_now.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

// ✅ WiFi Configuration - UPDATE THESE WITH YOUR NETWORK
const char* ssid = "brandi";
const char* password = "1715190000b";

// ✅ Dashboard Server Configuration - UPDATE WITH YOUR SERVER IP
const char* websocket_server = "https://dreadbot.onrender.com/;  // Replace with your dashboard server IP
const int websocket_port = 8001;                 // Backend port
const char* websocket_path = "/ws/esp32";        // ESP32 WebSocket endpoint

// ✅ MAC do ESP Executor (ESP2) - Your existing MAC
uint8_t receiverMAC[] = { 0xBC, 0xDD, 0xC2, 0xCD, 0x12, 0x34 };

// Servo command structure (same as before)
typedef struct {
  uint8_t servoIndex; // 0-5 for 6 servos
  uint8_t angle;      // Angle between 0 and 180
  uint8_t speed;      // Movement speed 1-10
} ServoCommand;

// WebSocket client
WebSocketsClient webSocket;

// Connection status
bool wifiConnected = false;
bool websocketConnected = false;
unsigned long lastHeartbeat = 0;
const unsigned long heartbeatInterval = 30000; // 30 seconds

// Status tracking
struct {
  uint8_t lastAngles[6] = {90, 90, 90, 90, 90, 90}; // Track last known positions
  bool servoEnabled[6] = {true, true, true, true, true, true};
  float batteryVoltage = 3.7;
  float temperature = 25.0;
} robotStatus;

void setup() {
  Serial.begin(115200);
  Serial.println("🤖 DREADNOUGHT ESP32 CONTROLLER STARTING...");
  
  // Initialize ESP-NOW (same as before)
  initializeESPNow();
  
  // Connect to WiFi
  connectToWiFi();
  
  // Initialize WebSocket connection
  initializeWebSocket();
  
  Serial.println("✅ Dreadnought Controller ready for WebSocket commands!");
}

void loop() {
  webSocket.loop();
  
  // Send periodic status updates
  if (websocketConnected && millis() - lastHeartbeat > heartbeatInterval) {
    sendStatusUpdate();
    lastHeartbeat = millis();
  }
  
  // Handle WiFi reconnection
  if (WiFi.status() != WL_CONNECTED && wifiConnected) {
    wifiConnected = false;
    websocketConnected = false;
    Serial.println("📡 WiFi disconnected, attempting reconnection...");
    connectToWiFi();
  }
  
  delay(10);
}

void initializeESPNow() {
  WiFi.mode(WIFI_STA);
  
  if (esp_now_init() != ESP_OK) {
    Serial.println("❌ Error initializing ESP-NOW");
    return;
  }
  
  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, receiverMAC, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;
  
  if (!esp_now_is_peer_exist(receiverMAC)) {
    if (esp_now_add_peer(&peerInfo) != ESP_OK) {
      Serial.println("❌ Error adding ESP-NOW peer");
      return;
    }
  }
  
  Serial.println("✅ ESP-NOW initialized");
}

void connectToWiFi() {
  WiFi.begin(ssid, password);
  Serial.print("📡 Connecting to WiFi");
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println();
    Serial.print("✅ WiFi connected! IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("❌ WiFi connection failed");
  }
}

void initializeWebSocket() {
  if (!wifiConnected) return;
  
  webSocket.begin(websocket_server, websocket_port, websocket_path);
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
  
  Serial.println("🔌 WebSocket client initialized");
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      websocketConnected = false;
      Serial.println("🔴 WebSocket Disconnected");
      break;
      
    case WStype_CONNECTED:
      websocketConnected = true;
      Serial.printf("🟢 WebSocket Connected to: %s\n", payload);
      
      // Send initial status
      sendStatusUpdate();
      break;
      
    case WStype_TEXT:
      handleWebSocketMessage((char*)payload);
      break;
      
    case WStype_ERROR:
      Serial.printf("❌ WebSocket Error: %s\n", payload);
      break;
      
    default:
      break;
  }
}

void handleWebSocketMessage(const char* message) {
  Serial.printf("📨 Received: %s\n", message);
  
  // Parse JSON message
  DynamicJsonDocument doc(1024);
  deserializeJson(doc, message);
  
  String messageType = doc["type"];
  
  if (messageType == "servo_command") {
    handleServoCommand(doc);
  } else if (messageType == "status_request") {
    sendStatusUpdate();
  } else if (messageType == "calibrate") {
    handleCalibration(doc);
  } else if (messageType == "emergency_stop") {
    handleEmergencyStop();
  }
}

void handleServoCommand(JsonDocument& doc) {
  uint8_t servoIndex = doc["servo_index"];
  uint8_t angle = doc["angle"];
  uint8_t speed = doc["speed"] | 5;  // Default speed 5 if not specified
  
  // Validate command
  if (servoIndex > 5 || angle > 180) {
    Serial.printf("❌ Invalid servo command: servo=%d, angle=%d\n", servoIndex, angle);
    sendCommandResponse(false, "Invalid servo index or angle");
    return;
  }
  
  // Create servo command
  ServoCommand cmd;
  cmd.servoIndex = servoIndex;
  cmd.angle = angle;
  cmd.speed = speed;
  
  // Send via ESP-NOW to executor
  esp_err_t result = esp_now_send(receiverMAC, (uint8_t *)&cmd, sizeof(cmd));
  
  if (result == ESP_OK) {
    // Update status tracking
    robotStatus.lastAngles[servoIndex] = angle;
    
    Serial.printf("✅ Servo %d -> %d° (speed: %d)\n", servoIndex, angle, speed);
    sendCommandResponse(true, String("Servo ") + servoIndex + " -> " + angle + "°");
    
    // Broadcast servo update to all dashboards
    sendServoUpdate(servoIndex, angle);
    
  } else {
    Serial.printf("❌ Failed to send servo command: %d\n", result);
    sendCommandResponse(false, "ESP-NOW transmission failed");
  }
}

void handleCalibration(JsonDocument& doc) {
  Serial.println("🔧 Starting servo calibration sequence...");
  
  // Move all servos to center position for calibration
  for (int i = 0; i < 6; i++) {
    ServoCommand cmd;
    cmd.servoIndex = i;
    cmd.angle = 90;
    cmd.speed = 2; // Slow speed for calibration
    
    esp_now_send(receiverMAC, (uint8_t *)&cmd, sizeof(cmd));
    robotStatus.lastAngles[i] = 90;
    delay(100);
  }
  
  sendCommandResponse(true, "Calibration complete - all servos at 90°");
}

void handleEmergencyStop() {
  Serial.println("🚨 EMERGENCY STOP ACTIVATED");
  
  // Stop all servos by sending current positions
  for (int i = 0; i < 6; i++) {
    ServoCommand cmd;
    cmd.servoIndex = i;
    cmd.angle = robotStatus.lastAngles[i];
    cmd.speed = 10; // Max speed for immediate stop
    
    esp_now_send(receiverMAC, (uint8_t *)&cmd, sizeof(cmd));
    delay(10);
  }
  
  sendCommandResponse(true, "Emergency stop executed");
}

void sendCommandResponse(bool success, String message) {
  if (!websocketConnected) return;
  
  DynamicJsonDocument doc(256);
  doc["type"] = "command_response";
  doc["success"] = success;
  doc["message"] = message;
  doc["timestamp"] = millis();
  
  String response;
  serializeJson(doc, response);
  webSocket.sendTXT(response);
}

void sendServoUpdate(uint8_t servoIndex, uint8_t angle) {
  if (!websocketConnected) return;
  
  DynamicJsonDocument doc(256);
  doc["type"] = "servo_update";
  doc["servo_index"] = servoIndex;
  doc["angle"] = angle;
  doc["timestamp"] = millis();
  
  String update;
  serializeJson(doc, update);
  webSocket.sendTXT(update);
}

void sendStatusUpdate() {
  if (!websocketConnected) return;
  
  // Update sensor readings (replace with actual sensors if available)
  robotStatus.batteryVoltage = 3.6 + (analogRead(A0) / 4095.0) * 0.6; // Simulated battery reading
  robotStatus.temperature = 20 + random(0, 20); // Simulated temperature
  
  DynamicJsonDocument doc(512);
  doc["type"] = "status_update";
  doc["battery_voltage"] = robotStatus.batteryVoltage;
  doc["temperature"] = robotStatus.temperature;
  doc["wifi_rssi"] = WiFi.RSSI();
  doc["uptime"] = millis();
  doc["free_heap"] = ESP.getFreeHeap();
  
  // Add servo positions
  JsonArray servos = doc.createNestedArray("servo_positions");
  for (int i = 0; i < 6; i++) {
    JsonObject servo = servos.createNestedObject();
    servo["index"] = i;
    servo["angle"] = robotStatus.lastAngles[i];
    servo["enabled"] = robotStatus.servoEnabled[i];
  }
  
  String status;
  serializeJson(doc, status);
  webSocket.sendTXT(status);
  
  Serial.println("📊 Status update sent");
}

// Functions for advanced features support
void executePresetPose(const char* poseName) {
  Serial.printf("🎭 Executing preset pose: %s\n", poseName);
  
  // Define preset poses for bipedal robot
  if (strcmp(poseName, "stand") == 0) {
    uint8_t angles[] = {90, 90, 90, 90, 90, 90};
    sendMultiServoCommand(angles, 6, 3);
  }
  else if (strcmp(poseName, "walk_forward") == 0) {
    uint8_t angles[] = {45, 135, 60, 120, 90, 90};
    sendMultiServoCommand(angles, 6, 5);
  }
  else if (strcmp(poseName, "crouch") == 0) {
    uint8_t angles[] = {30, 150, 30, 150, 45, 135};
    sendMultiServoCommand(angles, 6, 2);
  }
}

void sendMultiServoCommand(uint8_t angles[], int count, uint8_t speed) {
  for (int i = 0; i < count && i < 6; i++) {
    ServoCommand cmd;
    cmd.servoIndex = i;
    cmd.angle = angles[i];
    cmd.speed = speed;
    
    esp_now_send(receiverMAC, (uint8_t *)&cmd, sizeof(cmd));
    robotStatus.lastAngles[i] = angles[i];
    delay(50); // Small delay between commands
  }
  
  sendCommandResponse(true, "Multi-servo command executed");
}
