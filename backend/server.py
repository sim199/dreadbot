from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime
import asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.esp32_connection: Optional[WebSocket] = None

    async def connect(self, websocket: WebSocket, client_type: str = "dashboard"):
        await websocket.accept()
        if client_type == "esp32":
            self.esp32_connection = websocket
            print("ESP32 connected!")
        else:
            self.active_connections.append(websocket)
            print(f"Dashboard client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, client_type: str = "dashboard"):
        if client_type == "esp32":
            self.esp32_connection = None
            print("ESP32 disconnected!")
        else:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            print(f"Dashboard client disconnected. Total: {len(self.active_connections)}")

    async def send_to_esp32(self, message: dict):
        if self.esp32_connection and self.esp32_connection.client_state == WebSocketState.CONNECTED:
            try:
                await self.esp32_connection.send_text(json.dumps(message))
                return True
            except Exception as e:
                print(f"Error sending to ESP32: {e}")
                return False
        return False

    async def broadcast_to_dashboards(self, message: dict):
        if self.active_connections:
            disconnected = []
            for connection in self.active_connections:
                try:
                    if connection.client_state == WebSocketState.CONNECTED:
                        await connection.send_text(json.dumps(message))
                    else:
                        disconnected.append(connection)
                except Exception as e:
                    print(f"Error broadcasting: {e}")
                    disconnected.append(connection)
            
            # Remove disconnected connections
            for connection in disconnected:
                self.active_connections.remove(connection)

manager = ConnectionManager()

# Pydantic Models
class ServoCommand(BaseModel):
    servo_index: int = Field(..., ge=0, le=5, description="Servo index (0-5)")
    angle: int = Field(..., ge=0, le=180, description="Servo angle (0-180)")
    speed: Optional[int] = Field(None, ge=1, le=10, description="Movement speed (1-10)")

class ServoConfiguration(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    servos: List[Dict[str, Any]]  # List of {servo_index, angle, enabled}
    created_at: datetime = Field(default_factory=datetime.utcnow)

class GamepadButtonConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    button_name: str
    command: str
    description: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

# WebSocket endpoints
@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await manager.connect(websocket, "dashboard")
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message["type"] == "servo_command":
                # Forward servo command to ESP32
                servo_cmd = {
                    "type": "servo_command",
                    "servo_index": message["servo_index"],
                    "angle": message["angle"],
                    "speed": message.get("speed", 5)
                }
                
                success = await manager.send_to_esp32(servo_cmd)
                
                # Send response back to dashboard
                response = {
                    "type": "command_response",
                    "success": success,
                    "message": f"Servo {message['servo_index']} -> {message['angle']}°" if success else "ESP32 not connected"
                }
                await websocket.send_text(json.dumps(response))
                
            elif message["type"] == "preset_pose":
                # Handle preset pose execution
                pose_name = message["pose_name"]
                angles = message["angles"]
                speed = message.get("speed", 5)
                
                success_count = 0
                for i, angle in enumerate(angles):
                    if i < 6:  # Only handle first 6 servos
                        success = await manager.send_to_esp32({
                            "type": "servo_command",
                            "servo_index": i,
                            "angle": angle,
                            "speed": speed
                        })
                        if success:
                            success_count += 1
                            await manager.broadcast_to_dashboards({
                                "type": "servo_update",
                                "servo_index": i,
                                "angle": angle
                            })
                        
                        # Small delay between servo commands for smooth execution
                        await asyncio.sleep(0.05)
                
                response = {
                    "type": "command_response",
                    "success": success_count > 0,
                    "message": f"Executed pose '{pose_name}' ({success_count}/6 servos successful)"
                }
                await websocket.send_text(json.dumps(response))
            
            elif message["type"] == "terminal_command":
                # Parse terminal commands
                command = message["command"].strip().lower()
                response = await process_terminal_command(command, websocket)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, "dashboard")

@app.websocket("/ws/esp32")
async def websocket_esp32(websocket: WebSocket):
    await manager.connect(websocket, "esp32")
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Forward ESP32 messages to all dashboards
            await manager.broadcast_to_dashboards({
                "type": "esp32_message",
                "data": message
            })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, "esp32")

async def process_terminal_command(command: str, websocket: WebSocket):
    """Process terminal commands and return response"""
    parts = command.split()
    
    if not parts:
        return {"type": "terminal_response", "message": "Empty command"}
    
    cmd = parts[0]
    
    try:
        if cmd == "servo" and len(parts) >= 3:
            # servo <index> <angle> [speed]
            servo_index = int(parts[1])
            angle = int(parts[2])
            speed = int(parts[3]) if len(parts) > 3 else 5
            
            if 0 <= servo_index <= 5 and 0 <= angle <= 180:
                success = await manager.send_to_esp32({
                    "type": "servo_command",
                    "servo_index": servo_index,
                    "angle": angle,
                    "speed": speed
                })
                
                message = f"✅ Servo {servo_index} -> {angle}° (speed: {speed})" if success else "❌ ESP32 not connected"
                
                # Broadcast update
                if success:
                    await manager.broadcast_to_dashboards({
                        "type": "servo_update",
                        "servo_index": servo_index,
                        "angle": angle
                    })
            else:
                message = "❌ Invalid servo index (0-5) or angle (0-180)"
                
        elif cmd == "servo" and len(parts) == 3 and parts[1] == "all":
            # servo all <angle>
            angle = int(parts[2])
            if 0 <= angle <= 180:
                success_count = 0
                for i in range(6):
                    success = await manager.send_to_esp32({
                        "type": "servo_command",
                        "servo_index": i,
                        "angle": angle,
                        "speed": 5
                    })
                    if success:
                        success_count += 1
                        await manager.broadcast_to_dashboards({
                            "type": "servo_update",
                            "servo_index": i,
                            "angle": angle
                        })
                
                message = f"✅ Set all servos to {angle}° ({success_count}/6 successful)"
            else:
                message = "❌ Invalid angle (0-180)"
                
        elif cmd == "status":
            esp32_status = "🟢 Connected" if manager.esp32_connection else "🔴 Disconnected"
            dashboard_count = len(manager.active_connections)
            message = f"📊 Status:\n  ESP32: {esp32_status}\n  Dashboards: {dashboard_count} connected"
            
        elif cmd == "help":
            message = """🤖 Dreadnought Control Commands:
  servo <index> <angle> [speed] - Control single servo (0-5, 0-180°)
  servo all <angle>             - Set all servos to same angle
  status                        - Show connection status
  list configs                  - Show saved configurations
  save config <name>            - Save current servo positions
  load config <name>            - Load saved configuration
  clear                         - Clear terminal
  help                          - Show this help"""
  
        elif cmd == "clear":
            message = {"type": "clear_terminal"}
            
        else:
            message = f"❌ Unknown command: {command}\nType 'help' for available commands"
            
    except (ValueError, IndexError):
        message = f"❌ Invalid command format: {command}\nType 'help' for usage"
    
    # Send response back to the requesting websocket
    await websocket.send_text(json.dumps({
        "type": "terminal_response", 
        "message": message
    }))

# REST API endpoints
@api_router.get("/")
async def root():
    return {"message": "Dreadnought Servo Control API"}

@api_router.get("/status")
async def get_system_status():
    return {
        "esp32_connected": manager.esp32_connection is not None,
        "dashboard_connections": len(manager.active_connections),
        "servo_count": 6
    }

@api_router.post("/servo", response_model=dict)
async def control_servo(command: ServoCommand):
    """REST endpoint for servo control"""
    success = await manager.send_to_esp32({
        "type": "servo_command",
        "servo_index": command.servo_index,
        "angle": command.angle,
        "speed": command.speed or 5
    })
    
    if success:
        # Broadcast update
        await manager.broadcast_to_dashboards({
            "type": "servo_update",
            "servo_index": command.servo_index,
            "angle": command.angle
        })
    
    return {
        "success": success,
        "message": f"Servo {command.servo_index} -> {command.angle}°" if success else "ESP32 not connected"
    }

@api_router.get("/configurations", response_model=List[ServoConfiguration])
async def get_configurations():
    configs = await db.servo_configurations.find().to_list(100)
    return [ServoConfiguration(**config) for config in configs]

@api_router.post("/configurations", response_model=ServoConfiguration)
async def save_configuration(config: ServoConfiguration):
    config_dict = config.dict()
    await db.servo_configurations.insert_one(config_dict)
    return config

@api_router.get("/gamepad-buttons", response_model=List[GamepadButtonConfig])
async def get_gamepad_buttons():
    buttons = await db.gamepad_buttons.find().to_list(100)
    return [GamepadButtonConfig(**button) for button in buttons]

@api_router.post("/gamepad-buttons", response_model=GamepadButtonConfig)
async def save_gamepad_button(button: GamepadButtonConfig):
    button_dict = button.dict()
    await db.gamepad_buttons.insert_one(button_dict)
    return button

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()