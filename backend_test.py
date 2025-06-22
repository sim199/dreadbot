#!/usr/bin/env python3
import asyncio
import json
import os
import pytest
import websockets
import requests
from typing import Dict, Any, List
import uuid

# Get the backend URL from the frontend .env file
with open('/app/frontend/.env', 'r') as f:
    for line in f:
        if line.startswith('REACT_APP_BACKEND_URL='):
            BACKEND_URL = line.strip().split('=')[1].strip('"\'')
            break

# API endpoints
API_URL = f"{BACKEND_URL}/api"
WS_DASHBOARD_URL = f"{BACKEND_URL.replace('http', 'ws')}/ws/dashboard"
WS_ESP32_URL = f"{BACKEND_URL.replace('http', 'ws')}/ws/esp32"

print(f"Testing against backend URL: {BACKEND_URL}")
print(f"WebSocket Dashboard URL: {WS_DASHBOARD_URL}")
print(f"WebSocket ESP32 URL: {WS_ESP32_URL}")

# Test REST API endpoints
def test_api_root():
    """Test the API root endpoint"""
    response = requests.get(f"{API_URL}/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert data["message"] == "Dreadnought Servo Control API"
    print("✅ API root endpoint test passed")

def test_api_status():
    """Test the API status endpoint"""
    response = requests.get(f"{API_URL}/status")
    assert response.status_code == 200
    data = response.json()
    assert "esp32_connected" in data
    assert "dashboard_connections" in data
    assert "servo_count" in data
    assert data["servo_count"] == 6
    print("✅ API status endpoint test passed")

def test_api_servo_control():
    """Test the servo control endpoint"""
    # Test valid servo command
    payload = {
        "servo_index": 2,
        "angle": 90,
        "speed": 5
    }
    response = requests.post(f"{API_URL}/servo", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert "message" in data
    
    # Test invalid servo index
    invalid_payload = {
        "servo_index": 10,  # Invalid index (should be 0-5)
        "angle": 90
    }
    response = requests.post(f"{API_URL}/servo", json=invalid_payload)
    assert response.status_code == 422  # Validation error
    
    # Test invalid angle
    invalid_payload = {
        "servo_index": 2,
        "angle": 200  # Invalid angle (should be 0-180)
    }
    response = requests.post(f"{API_URL}/servo", json=invalid_payload)
    assert response.status_code == 422  # Validation error
    
    print("✅ API servo control endpoint test passed")

def test_api_configurations():
    """Test the configurations endpoints"""
    # Get current configurations
    response = requests.get(f"{API_URL}/configurations")
    assert response.status_code == 200
    initial_configs = response.json()
    
    # Create a new configuration
    new_config = {
        "name": f"Test Config {uuid.uuid4()}",
        "servos": [
            {"servo_index": 0, "angle": 90, "enabled": True},
            {"servo_index": 1, "angle": 45, "enabled": True},
            {"servo_index": 2, "angle": 180, "enabled": True},
            {"servo_index": 3, "angle": 0, "enabled": False},
            {"servo_index": 4, "angle": 120, "enabled": True},
            {"servo_index": 5, "angle": 60, "enabled": True}
        ]
    }
    
    response = requests.post(f"{API_URL}/configurations", json=new_config)
    assert response.status_code == 200
    saved_config = response.json()
    assert "id" in saved_config
    assert saved_config["name"] == new_config["name"]
    assert len(saved_config["servos"]) == 6
    
    # Verify the configuration was saved
    response = requests.get(f"{API_URL}/configurations")
    assert response.status_code == 200
    updated_configs = response.json()
    assert len(updated_configs) >= len(initial_configs) + 1
    
    print("✅ API configurations endpoints test passed")

def test_api_gamepad_buttons():
    """Test the gamepad buttons endpoints"""
    # Get current gamepad buttons
    response = requests.get(f"{API_URL}/gamepad-buttons")
    assert response.status_code == 200
    initial_buttons = response.json()
    
    # Create a new gamepad button mapping
    new_button = {
        "button_name": f"button_{uuid.uuid4().hex[:8]}",
        "command": "servo 2 90",
        "description": "Move servo 2 to 90 degrees"
    }
    
    response = requests.post(f"{API_URL}/gamepad-buttons", json=new_button)
    assert response.status_code == 200
    saved_button = response.json()
    assert "id" in saved_button
    assert saved_button["button_name"] == new_button["button_name"]
    assert saved_button["command"] == new_button["command"]
    
    # Verify the button mapping was saved
    response = requests.get(f"{API_URL}/gamepad-buttons")
    assert response.status_code == 200
    updated_buttons = response.json()
    assert len(updated_buttons) >= len(initial_buttons) + 1
    
    print("✅ API gamepad buttons endpoints test passed")

# WebSocket tests
async def test_dashboard_websocket():
    """Test the dashboard WebSocket connection and message handling"""
    try:
        # Connect to the dashboard WebSocket
        async with websockets.connect(WS_DASHBOARD_URL) as websocket:
            print("Connected to dashboard WebSocket")
            
            # Test servo command
            servo_cmd = {
                "type": "servo_command",
                "servo_index": 3,
                "angle": 120,
                "speed": 7
            }
            await websocket.send(json.dumps(servo_cmd))
            response = await websocket.recv()
            response_data = json.loads(response)
            assert "type" in response_data
            assert response_data["type"] == "command_response"
            
            # Test terminal commands
            terminal_commands = [
                "status",
                "help",
                "servo 1 45",
                "servo all 90",
                "invalid command"
            ]
            
            for cmd in terminal_commands:
                terminal_cmd = {
                    "type": "terminal_command",
                    "command": cmd
                }
                await websocket.send(json.dumps(terminal_cmd))
                response = await websocket.recv()
                response_data = json.loads(response)
                assert "type" in response_data
                assert response_data["type"] == "terminal_response"
                
            print("✅ Dashboard WebSocket test passed")
    except Exception as e:
        print(f"❌ Dashboard WebSocket test failed: {e}")
        raise

async def test_esp32_websocket():
    """Test the ESP32 WebSocket connection and message handling"""
    try:
        # Connect to the ESP32 WebSocket
        async with websockets.connect(WS_ESP32_URL) as esp32_ws:
            print("Connected to ESP32 WebSocket")
            
            # Connect to the dashboard WebSocket to receive broadcasts
            async with websockets.connect(WS_DASHBOARD_URL) as dashboard_ws:
                print("Connected to dashboard WebSocket for ESP32 test")
                
                # Send a message from ESP32 to be broadcasted to dashboards
                esp32_msg = {
                    "type": "status_update",
                    "battery": 85,
                    "temperature": 32.5
                }
                await esp32_ws.send(json.dumps(esp32_msg))
                
                # Receive the broadcasted message on the dashboard
                response = await dashboard_ws.recv()
                response_data = json.loads(response)
                assert "type" in response_data
                assert response_data["type"] == "esp32_message"
                assert "data" in response_data
                
                # Test sending a servo command from dashboard to ESP32
                servo_cmd = {
                    "type": "servo_command",
                    "servo_index": 0,
                    "angle": 180
                }
                await dashboard_ws.send(json.dumps(servo_cmd))
                
                # ESP32 should receive the command
                esp32_response = await esp32_ws.recv()
                esp32_data = json.loads(esp32_response)
                assert "type" in esp32_data
                assert esp32_data["type"] == "servo_command"
                assert esp32_data["servo_index"] == 0
                assert esp32_data["angle"] == 180
                
            print("✅ ESP32 WebSocket test passed")
    except Exception as e:
        print(f"❌ ESP32 WebSocket test failed: {e}")
        raise

async def run_websocket_tests():
    """Run all WebSocket tests"""
    try:
        await test_dashboard_websocket()
        await test_esp32_websocket()
    except Exception as e:
        print(f"WebSocket tests failed: {e}")

# Run all tests
def run_all_tests():
    """Run all API and WebSocket tests"""
    print("\n=== Running Dreadnought Servo Control Backend Tests ===\n")
    
    # Run REST API tests
    try:
        test_api_root()
        test_api_status()
        test_api_servo_control()
        test_api_configurations()
        test_api_gamepad_buttons()
    except Exception as e:
        print(f"❌ REST API tests failed: {e}")
    
    # Run WebSocket tests
    try:
        asyncio.run(run_websocket_tests())
    except Exception as e:
        print(f"❌ WebSocket tests failed: {e}")
    
    print("\n=== All tests completed ===\n")

if __name__ == "__main__":
    run_all_tests()