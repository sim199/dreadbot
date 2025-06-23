#include <WiFi.h>
#include <esp_now.h>
#include <ESP32Servo.h>

// ✅ 6 Servo objects for bipedal robot
Servo servo[6];
const int servoPin[6] = {13, 14, 27, 26, 25, 33}; // GPIO pins for 6 servos

// Enhanced servo command structure
typedef struct {
  uint8_t servoIndex; // 0-5 for 6 servos
  uint8_t angle;      // 0-180 degrees
  uint8_t speed;      // 1-10 movement speed
} ServoCommand;

// Servo status tracking
struct {
  uint8_t currentAngle[6] = {90, 90, 90, 90, 90, 90};
  uint8_t targetAngle[6] = {90, 90, 90, 90, 90, 90};
  bool isMoving[6] = {false, false, false, false, false, false};
  unsigned long lastUpdate[6] = {0, 0, 0, 0, 0, 0};
  uint8_t moveSpeed[6] = {5, 5, 5, 5, 5, 5};
} servoStatus;

void onReceiveData(const esp_now_recv_info_t *recvInfo, const uint8_t *incomingData, int len) {
  if (len != sizeof(ServoCommand)) {
    Serial.println("❌ Invalid command size received");
    return;
  }

  ServoCommand cmd;
  memcpy(&cmd, incomingData, sizeof(cmd));

  // Validate servo index
  if (cmd.servoIndex >= 6) {
    Serial.printf("❌ Invalid servo index: %d\n", cmd.servoIndex);
    return;
  }

  // Validate angle
  if (cmd.angle > 180) {
    Serial.printf("❌ Invalid angle: %d\n", cmd.angle);
    return;
  }

  // Set target position and speed
  servoStatus.targetAngle[cmd.servoIndex] = cmd.angle;
  servoStatus.moveSpeed[cmd.servoIndex] = (cmd.speed == 0) ? 5 : cmd.speed;
  servoStatus.isMoving[cmd.servoIndex] = true;

  Serial.printf("✅ Servo %d target: %d° (speed: %d)\n", 
    cmd.servoIndex, cmd.angle, servoStatus.moveSpeed[cmd.servoIndex]);
}

void setup() {
  Serial.begin(115200);
  Serial.println("🦾 DREADNOUGHT EXECUTOR - 6 SERVO SYSTEM");

  // Initialize all 6 servos
  for (int i = 0; i < 6; i++) {
    servo[i].setPeriodHertz(50);
    servo[i].attach(servoPin[i], 500, 2400);
    servo[i].write(90); // Start at center position
    Serial.printf("Servo %d initialized on pin %d\n", i, servoPin[i]);
  }

  // Initialize ESP-NOW
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  if (esp_now_init() != ESP_OK) {
    Serial.println("❌ Error initializing ESP-NOW");
    return;
  }

  esp_now_register_recv_cb(onReceiveData);

  Serial.println("✅ Dreadnought Executor ready - 6 servos active!");
  Serial.println("Servo mapping:");
  Serial.println("  Servo 0 (Pin 13): Left Hip");
  Serial.println("  Servo 1 (Pin 14): Left Knee"); 
  Serial.println("  Servo 2 (Pin 27): Left Ankle");
  Serial.println("  Servo 3 (Pin 26): Right Hip");
  Serial.println("  Servo 4 (Pin 25): Right Knee");
  Serial.println("  Servo 5 (Pin 33): Right Ankle");
}

void loop() {
  updateServoMovements();
  delay(20); // 50Hz update rate for smooth movement
}

void updateServoMovements() {
  unsigned long currentTime = millis();
  
  for (int i = 0; i < 6; i++) {
    if (servoStatus.isMoving[i]) {
      // Calculate time since last update
      unsigned long deltaTime = currentTime - servoStatus.lastUpdate[i];
      
      // Update every 20ms based on speed setting
      if (deltaTime >= (20 / servoStatus.moveSpeed[i]) * 10) {
        
        int currentAngle = servoStatus.currentAngle[i];
        int targetAngle = servoStatus.targetAngle[i];
        
        if (currentAngle != targetAngle) {
          // Move towards target
          if (currentAngle < targetAngle) {
            currentAngle++;
          } else {
            currentAngle--;
          }
          
          // Update servo position
          servo[i].write(currentAngle);
          servoStatus.currentAngle[i] = currentAngle;
          servoStatus.lastUpdate[i] = currentTime;
          
        } else {
          // Target reached
          servoStatus.isMoving[i] = false;
          Serial.printf("✅ Servo %d reached target: %d°\n", i, targetAngle);
        }
      }
    }
  }
}

// Emergency stop function
void emergencyStop() {
  Serial.println("🚨 EMERGENCY STOP - All servos stopped");
  for (int i = 0; i < 6; i++) {
    servoStatus.isMoving[i] = false;
    servoStatus.targetAngle[i] = servoStatus.currentAngle[i];
  }
}

// Calibration function
void calibrateAllServos() {
  Serial.println("🔧 Calibrating all servos to center position...");
  for (int i = 0; i < 6; i++) {
    servoStatus.targetAngle[i] = 90;
    servoStatus.moveSpeed[i] = 2; // Slow calibration
    servoStatus.isMoving[i] = true;
  }
}

// Status report function
void printServoStatus() {
  Serial.println("📊 Current Servo Status:");
  for (int i = 0; i < 6; i++) {
    Serial.printf("  Servo %d: %d° -> %d° %s\n", 
      i, 
      servoStatus.currentAngle[i], 
      servoStatus.targetAngle[i],
      servoStatus.isMoving[i] ? "(moving)" : "(stopped)"
    );
  }
}