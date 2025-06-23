import React, { useState, useEffect, useRef } from 'react';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const App = () => {
  const [websocket, setWebsocket] = useState(null);
  const [connected, setConnected] = useState(false);
  const [esp32Connected, setEsp32Connected] = useState(false);
  const [servos, setServos] = useState(Array(6).fill().map((_, i) => ({
    index: i,
    angle: 90,
    enabled: true,
    lastUpdate: null,
    name: ['Left Hip', 'Left Knee', 'Left Ankle', 'Right Hip', 'Right Knee', 'Right Ankle'][i]
  })));
  const [terminal, setTerminal] = useState([
    { type: 'system', message: '🤖 DREADNOUGHT CONTROL TERMINAL INITIALIZED', timestamp: Date.now() },
    { type: 'system', message: 'Type "help" for available commands', timestamp: Date.now() }
  ]);
  const [command, setCommand] = useState('');
  const [gamepadButtons, setGamepadButtons] = useState({
    'button-a': { command: 'pose stand', active: false },
    'button-b': { command: 'pose crouch', active: false },
    'button-x': { command: 'pose walk_left', active: false },
    'button-y': { command: 'pose walk_right', active: false },
    'dpad-up': { command: 'pose walk_forward', active: false },
    'dpad-down': { command: 'pose walk_backward', active: false },
    'dpad-left': { command: 'turn left', active: false },
    'dpad-right': { command: 'turn right', active: false }
  });
  
  // Advanced features state
  const [presetPoses, setPresetPoses] = useState({
    stand: { name: 'Stand', angles: [90, 90, 90, 90, 90, 90], speed: 3 },
    crouch: { name: 'Crouch', angles: [60, 60, 45, 60, 60, 45], speed: 2 },
    walk_forward: { name: 'Walk Forward', angles: [75, 105, 60, 105, 75, 120], speed: 5 },
    walk_backward: { name: 'Walk Back', angles: [105, 75, 120, 75, 105, 60], speed: 5 },
    walk_left: { name: 'Step Left', angles: [45, 90, 90, 135, 90, 90], speed: 4 },
    walk_right: { name: 'Step Right', angles: [135, 90, 90, 45, 90, 90], speed: 4 },
    combat_ready: { name: 'Combat Ready', angles: [80, 80, 70, 100, 100, 110], speed: 3 },
    celebrate: { name: 'Victory Pose', angles: [45, 60, 90, 135, 120, 90], speed: 2 }
  });
  
  const [isRecording, setIsRecording] = useState(false);
  const [recordedSequence, setRecordedSequence] = useState([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [globalSpeed, setGlobalSpeed] = useState(5);
  const [esp32Status, setEsp32Status] = useState({
    battery: 0,
    temperature: 0,
    wifi_rssi: 0,
    uptime: 0
  });
  
  const terminalRef = useRef(null);
  const wsRef = useRef(null);

  // WebSocket connection
  useEffect(() => {
    const connectWebSocket = () => {
      const wsUrl = BACKEND_URL.replace('http', 'ws') + '/ws/dashboard';
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setWebsocket(ws);
        addTerminalMessage('system', '🟢 Connected to control server');
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      };

      ws.onclose = () => {
        setConnected(false);
        setWebsocket(null);
        addTerminalMessage('system', '🔴 Disconnected from control server');
        
        // Reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        addTerminalMessage('error', '❌ Connection error');
      };
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const handleWebSocketMessage = (data) => {
    switch (data.type) {
      case 'command_response':
        addTerminalMessage(data.success ? 'success' : 'error', data.message);
        break;
      case 'servo_update':
        updateServoPosition(data.servo_index, data.angle);
        break;
      case 'terminal_response':
        if (typeof data.message === 'object' && data.message.type === 'clear_terminal') {
          setTerminal([]);
        } else {
          addTerminalMessage('response', data.message);
        }
        break;
      case 'esp32_message':
        setEsp32Connected(true);
        if (data.data.type === 'status_update') {
          setEsp32Status(data.data);
          addTerminalMessage('esp32', `Status: Battery ${data.data.battery_voltage}V, Temp ${data.data.temperature}°C`);
        } else {
          addTerminalMessage('esp32', `ESP32: ${JSON.stringify(data.data)}`);
        }
        break;
    }
  };

  // Advanced control functions
  const executePresetPose = (poseName) => {
    const pose = presetPoses[poseName];
    if (!pose) return;

    if (websocket && connected) {
      // Send pose command to ESP32
      websocket.send(JSON.stringify({
        type: 'preset_pose',
        pose_name: poseName,
        angles: pose.angles,
        speed: pose.speed
      }));

      addTerminalMessage('command', `> Executing pose: ${pose.name}`);

      // Update local servo state
      pose.angles.forEach((angle, index) => {
        updateServoPosition(index, angle);
      });
    }
  };

  const startRecording = () => {
    setIsRecording(true);
    setRecordedSequence([]);
    addTerminalMessage('system', '🔴 Recording movement sequence...');
  };

  const stopRecording = () => {
    setIsRecording(false);
    addTerminalMessage('system', `✅ Recording stopped. ${recordedSequence.length} positions recorded`);
  };

  const playRecordedSequence = async () => {
    if (recordedSequence.length === 0) {
      addTerminalMessage('error', 'No recorded sequence to play');
      return;
    }

    setIsPlaying(true);
    addTerminalMessage('system', `▶️ Playing recorded sequence (${recordedSequence.length} steps)`);

    for (let i = 0; i < recordedSequence.length; i++) {
      const step = recordedSequence[i];
      
      // Send all servo positions for this step
      for (let j = 0; j < step.angles.length; j++) {
        if (websocket && connected) {
          websocket.send(JSON.stringify({
            type: 'servo_command',
            servo_index: j,
            angle: step.angles[j],
            speed: step.speed || globalSpeed
          }));
        }
      }

      // Wait for the specified delay
      await new Promise(resolve => setTimeout(resolve, step.delay || 1000));
    }

    setIsPlaying(false);
    addTerminalMessage('system', '✅ Sequence playback completed');
  };

  const recordCurrentPosition = () => {
    if (!isRecording) return;

    const currentPosition = {
      angles: servos.map(servo => servo.angle),
      speed: globalSpeed,
      delay: 1000,
      timestamp: Date.now()
    };

    setRecordedSequence(prev => [...prev, currentPosition]);
    addTerminalMessage('system', `📍 Position ${recordedSequence.length + 1} recorded`);
  };

  const addTerminalMessage = (type, message) => {
    setTerminal(prev => [...prev, {
      type,
      message,
      timestamp: Date.now()
    }]);
  };

  const updateServoPosition = (index, angle) => {
    setServos(prev => prev.map(servo => 
      servo.index === index 
        ? { ...servo, angle, lastUpdate: Date.now() }
        : servo
    ));
  };

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [terminal]);

  const sendServoCommand = (servoIndex, angle) => {
    if (websocket && connected) {
      websocket.send(JSON.stringify({
        type: 'servo_command',
        servo_index: servoIndex,
        angle: parseInt(angle),
        speed: globalSpeed
      }));

      // Record position if recording
      if (isRecording) {
        recordCurrentPosition();
      }
    }
  };

  const sendTerminalCommand = (cmd) => {
    if (websocket && connected) {
      addTerminalMessage('command', `> ${cmd}`);
      websocket.send(JSON.stringify({
        type: 'terminal_command',
        command: cmd
      }));
    }
  };

  const handleTerminalSubmit = (e) => {
    e.preventDefault();
    if (command.trim()) {
      sendTerminalCommand(command.trim());
      setCommand('');
    }
  };

  const handleGamepadButton = (buttonKey) => {
    const button = gamepadButtons[buttonKey];
    if (button.command) {
      setGamepadButtons(prev => ({
        ...prev,
        [buttonKey]: { ...prev[buttonKey], active: true }
      }));
      
      sendTerminalCommand(button.command);
      
      // Reset button state after animation
      setTimeout(() => {
        setGamepadButtons(prev => ({
          ...prev,
          [buttonKey]: { ...prev[buttonKey], active: false }
        }));
      }, 200);
    }
  };

  const handleServoToggle = (index) => {
    setServos(prev => prev.map(servo =>
      servo.index === index
        ? { ...servo, enabled: !servo.enabled }
        : servo
    ));
  };

  const getTerminalMessageClass = (type) => {
    switch (type) {
      case 'system': return 'text-cyan-400';
      case 'command': return 'text-yellow-300';
      case 'success': return 'text-green-400';
      case 'error': return 'text-red-400';
      case 'esp32': return 'text-purple-400';
      default: return 'text-gray-300';
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-green-400 font-mono">
      {/* Header */}
      <div className="border-b border-green-500 bg-black p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <h1 className="text-2xl font-bold text-green-400">
              🤖 DREADNOUGHT CONTROL CENTER
            </h1>
            <div className="flex space-x-4 text-sm">
              <span className={`px-2 py-1 rounded ${connected ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}`}>
                WS: {connected ? '🟢 ONLINE' : '🔴 OFFLINE'}
              </span>
              <span className={`px-2 py-1 rounded ${esp32Connected ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'}`}>
                ESP32: {esp32Connected ? '🟢 LINKED' : '⚡ STANDBY'}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 p-6 h-[calc(100vh-80px)]">
        {/* Servo Controls */}
        <div className="space-y-4">
          <h2 className="text-xl font-bold text-green-400 border-b border-green-500 pb-2">
            SERVO ACTUATORS
          </h2>
          
          <div className="grid grid-cols-1 gap-4">
            {servos.map((servo) => (
              <div key={servo.index} className={`bg-gray-800 border rounded-lg p-4 transition-all duration-300 ${
                servo.enabled ? 'border-green-500' : 'border-gray-600'
              } ${servo.lastUpdate && Date.now() - servo.lastUpdate < 1000 ? 'bg-green-900 bg-opacity-30' : ''}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    <span className="text-green-300 font-bold">SERVO_{servo.index}</span>
                    <button
                      onClick={() => handleServoToggle(servo.index)}
                      className={`px-2 py-1 text-xs rounded transition-colors ${
                        servo.enabled 
                          ? 'bg-green-700 text-green-100 hover:bg-green-600' 
                          : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                      }`}
                    >
                      {servo.enabled ? 'ACTIVE' : 'DISABLED'}
                    </button>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-cyan-400">{servo.angle}°</div>
                  </div>
                </div>
                
                <div className="space-y-2">
                  <input
                    type="range"
                    min="0"
                    max="180"
                    value={servo.angle}
                    onChange={(e) => updateServoPosition(servo.index, parseInt(e.target.value))}
                    onMouseUp={(e) => servo.enabled && sendServoCommand(servo.index, e.target.value)}
                    disabled={!servo.enabled || !connected}
                    className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider"
                  />
                  
                  <div className="flex space-x-2">
                    <button 
                      onClick={() => servo.enabled && sendServoCommand(servo.index, 0)}
                      disabled={!servo.enabled || !connected}
                      className="flex-1 px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded text-xs"
                    >
                      0°
                    </button>
                    <button 
                      onClick={() => servo.enabled && sendServoCommand(servo.index, 90)}
                      disabled={!servo.enabled || !connected}
                      className="flex-1 px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded text-xs"
                    >
                      90°
                    </button>
                    <button 
                      onClick={() => servo.enabled && sendServoCommand(servo.index, 180)}
                      disabled={!servo.enabled || !connected}
                      className="flex-1 px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded text-xs"
                    >
                      180°
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Terminal */}
        <div className="bg-black border border-green-500 rounded-lg p-4 flex flex-col">
          <h2 className="text-xl font-bold text-green-400 border-b border-green-500 pb-2 mb-4">
            COMMAND TERMINAL
          </h2>
          
          <div 
            ref={terminalRef}
            className="flex-1 overflow-y-auto space-y-1 mb-4 bg-gray-900 p-3 rounded border font-mono text-sm"
            style={{ maxHeight: 'calc(100% - 120px)' }}
          >
            {terminal.map((msg, index) => (
              <div key={index} className={`${getTerminalMessageClass(msg.type)} leading-relaxed`}>
                <span className="text-gray-500 text-xs mr-2">
                  {new Date(msg.timestamp).toLocaleTimeString()}
                </span>
                <span className="whitespace-pre-wrap">{msg.message}</span>
              </div>
            ))}
          </div>
          
          <form onSubmit={handleTerminalSubmit} className="flex">
            <span className="text-green-400 mr-2">$</span>
            <input
              type="text"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="Enter command..."
              disabled={!connected}
              className="flex-1 bg-transparent border-none outline-none text-green-300 placeholder-gray-500"
            />
          </form>
        </div>

        {/* Gamepad */}
        <div className="space-y-4">
          <h2 className="text-xl font-bold text-green-400 border-b border-green-500 pb-2">
            CONTROLLER PAD
          </h2>
          
          <div className="bg-gray-800 border border-green-500 rounded-lg p-6">
            <div className="relative w-full max-w-md mx-auto">
              {/* D-Pad */}
              <div className="absolute left-8 top-16">
                <div className="grid grid-cols-3 gap-1 w-24 h-24">
                  <div></div>
                  <button
                    onMouseDown={() => handleGamepadButton('dpad-up')}
                    className={`w-6 h-6 bg-gray-700 hover:bg-gray-600 rounded transition-all duration-150 ${
                      gamepadButtons['dpad-up'].active ? 'bg-green-500 shadow-lg shadow-green-500/50' : ''
                    }`}
                  >
                    ↑
                  </button>
                  <div></div>
                  <button
                    onMouseDown={() => handleGamepadButton('dpad-left')}
                    className={`w-6 h-6 bg-gray-700 hover:bg-gray-600 rounded transition-all duration-150 ${
                      gamepadButtons['dpad-left'].active ? 'bg-green-500 shadow-lg shadow-green-500/50' : ''
                    }`}
                  >
                    ←
                  </button>
                  <div className="w-6 h-6"></div>
                  <button
                    onMouseDown={() => handleGamepadButton('dpad-right')}
                    className={`w-6 h-6 bg-gray-700 hover:bg-gray-600 rounded transition-all duration-150 ${
                      gamepadButtons['dpad-right'].active ? 'bg-green-500 shadow-lg shadow-green-500/50' : ''
                    }`}
                  >
                    →
                  </button>
                  <div></div>
                  <button
                    onMouseDown={() => handleGamepadButton('dpad-down')}
                    className={`w-6 h-6 bg-gray-700 hover:bg-gray-600 rounded transition-all duration-150 ${
                      gamepadButtons['dpad-down'].active ? 'bg-green-500 shadow-lg shadow-green-500/50' : ''
                    }`}
                  >
                    ↓
                  </button>
                  <div></div>
                </div>
              </div>

              {/* Face Buttons */}
              <div className="absolute right-8 top-16">
                <div className="grid grid-cols-3 gap-2 w-24 h-24">
                  <div></div>
                  <button
                    onMouseDown={() => handleGamepadButton('button-y')}
                    className={`w-8 h-8 bg-yellow-600 hover:bg-yellow-500 rounded-full text-black font-bold transition-all duration-150 ${
                      gamepadButtons['button-y'].active ? 'bg-yellow-400 shadow-lg shadow-yellow-400/50 scale-110' : ''
                    }`}
                  >
                    Y
                  </button>
                  <div></div>
                  <button
                    onMouseDown={() => handleGamepadButton('button-x')}
                    className={`w-8 h-8 bg-blue-600 hover:bg-blue-500 rounded-full text-white font-bold transition-all duration-150 ${
                      gamepadButtons['button-x'].active ? 'bg-blue-400 shadow-lg shadow-blue-400/50 scale-110' : ''
                    }`}
                  >
                    X
                  </button>
                  <div className="w-8 h-8"></div>
                  <button
                    onMouseDown={() => handleGamepadButton('button-b')}
                    className={`w-8 h-8 bg-red-600 hover:bg-red-500 rounded-full text-white font-bold transition-all duration-150 ${
                      gamepadButtons['button-b'].active ? 'bg-red-400 shadow-lg shadow-red-400/50 scale-110' : ''
                    }`}
                  >
                    B
                  </button>
                  <div></div>
                  <button
                    onMouseDown={() => handleGamepadButton('button-a')}
                    className={`w-8 h-8 bg-green-600 hover:bg-green-500 rounded-full text-white font-bold transition-all duration-150 ${
                      gamepadButtons['button-a'].active ? 'bg-green-400 shadow-lg shadow-green-400/50 scale-110' : ''
                    }`}
                  >
                    A
                  </button>
                  <div></div>
                </div>
              </div>

              {/* Controller Body */}
              <div className="w-72 h-32 bg-gray-700 rounded-3xl mx-auto border-2 border-gray-600"></div>
            </div>

            {/* Button Mappings */}
            <div className="mt-6 text-xs space-y-1">
              <div className="text-gray-400 font-bold mb-2">BUTTON MAPPINGS:</div>
              {Object.entries(gamepadButtons).map(([key, button]) => (
                <div key={key} className="flex justify-between text-gray-300">
                  <span className="uppercase">{key.replace('-', ' ')}:</span>
                  <code className="text-cyan-400">{button.command}</code>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;