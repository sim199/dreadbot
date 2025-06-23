# 🤖 Dreadnought Servo Control System Setup

## ESP32 Hardware Setup

### Controller ESP32 (WebSocket Client)
- **Purpose**: Connects to dashboard via WiFi WebSocket, sends commands via ESP-NOW
- **Connections**: None required (WiFi + ESP-NOW only)
- **Libraries needed**: 
  ```
  WebSocketsClient by Markus Sattler
  ArduinoJson by Benoit Blanchon
  ```

### Executor ESP32 (6-Servo Driver)
- **Purpose**: Receives ESP-NOW commands, controls 6 servos
- **Servo Connections**:
  - Servo 0 (Left Hip): GPIO 13
  - Servo 1 (Left Knee): GPIO 14  
  - Servo 2 (Left Ankle): GPIO 27
  - Servo 3 (Right Hip): GPIO 26
  - Servo 4 (Right Knee): GPIO 25
  - Servo 5 (Right Ankle): GPIO 33
- **Power**: 5V external supply for servos (ESP32 3.3V logic)

## WiFi Configuration

1. Update `esp32_controller_websocket.ino`:
   ```cpp
   const char* ssid = "YOUR_WIFI_SSID";
   const char* password = "YOUR_WIFI_PASSWORD";
   const char* websocket_server = "192.168.1.100";  // Your dashboard server IP
   ```

2. Find your dashboard server IP:
   ```bash
   hostname -I
   ```

## Installation Steps

1. **Install ESP32 Libraries** (Arduino IDE):
   - Tools → Manage Libraries
   - Search and install:
     - "WebSocketsClient" by Markus Sattler
     - "ArduinoJson" by Benoit Blanchon
     - "ESP32Servo" by Kevin Harrington

2. **Upload Controller Code**:
   - Open `esp32_controller_websocket.ino`
   - Select your ESP32 board
   - Update WiFi credentials and server IP
   - Upload

3. **Upload Executor Code**:
   - Open `esp32_executor_6servo.ino` 
   - Select your second ESP32 board
   - Upload

4. **MAC Address Setup**:
   - Get Executor ESP32 MAC address from Serial Monitor
   - Update Controller code with correct MAC address

## Testing Connection

1. **Start Dashboard**: Web interface should show "ESP32: ⚡ STANDBY"
2. **Power Controller ESP32**: Should connect to WiFi and WebSocket
3. **Dashboard Status**: Should change to "ESP32: 🟢 LINKED"
4. **Test Servo**: Use terminal command `servo 0 90` or slider controls

## Terminal Commands

- `servo <index> <angle> [speed]` - Control single servo (0-5, 0-180°)
- `servo all <angle>` - Set all servos to same angle
- `status` - Show connection status and servo positions
- `help` - Display all available commands

## Troubleshooting

### ESP32 Not Connecting:
- Check WiFi credentials
- Ensure dashboard server IP is correct
- Check firewall settings
- Verify ESP32 is on same network

### Servos Not Moving:
- Check ESP-NOW MAC addresses match
- Verify servo power supply (5V, adequate current)
- Check servo wiring to correct GPIO pins
- Use Serial Monitor to see ESP-NOW transmission status

### Dashboard Issues:
- Refresh browser page
- Check backend server is running
- Verify WebSocket port 8001 is accessible
- Check browser console for errors

## Advanced Features Available

1. **Preset Poses**: Pre-programmed robot positions
2. **Movement Recording**: Record and playback sequences  
3. **Speed Control**: Adjust servo movement speed
4. **Real-time Status**: Battery, temperature, connection monitoring
5. **Emergency Stop**: Immediate servo freeze
6. **Calibration**: Auto-center all servos

Your Dreadnought is ready for battle! 🚀