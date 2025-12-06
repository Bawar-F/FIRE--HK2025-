import serial
import time
import json
from enum import Enum
import config


class SystemState(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"


class UARTController:
    """UART communication with Arduino. Commands: START/STOP/STATUS/RESULTS/RESET."""
    
    def __init__(self, port=None, baudrate=None, timeout=None):
        self.port = port or config.UART_PORT
        self.baudrate = baudrate or config.UART_BAUDRATE
        self.timeout = timeout or config.UART_TIMEOUT
        self.serial = None
        self.is_connected = False
        self.state = SystemState.IDLE
        self.last_results = None
        self.last_live_update = None
    
    def connect(self):
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(2)
            self.is_connected = True
            print(f"[UART] Connected to {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"[UART] Failed: {e}")
            self.is_connected = False
            return False
        except Exception as e:
            print(f"[UART] Error: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.is_connected = False
            print("[UART] Disconnected")
    
    def read_command(self):
        if not self.is_connected or not self.serial:
            return None
        
        try:
            if self.serial.in_waiting:
                line = self.serial.readline().decode("utf-8", errors="replace").strip()
                if line:
                    print(f"[UART] Received: {line}")
                    return line
        except Exception as e:
            print(f"[UART] Read error: {e}")
        
        return None
    
    def send_response(self, data):
        """
        Send JSON response to Arduino.
        
        Args:
            data: Dictionary to send as JSON
        """
        if not self.is_connected or not self.serial:
            print("[UART] Not connected, cannot send")
            return False
        
        try:
            json_str = json.dumps(data, separators=(',', ':'))  # Compact JSON
            self.serial.write((json_str + "\n").encode("utf-8"))
            self.serial.flush()
            
            if config.DEBUG_MODE:
                print(f"[UART] Sent: {json_str}")
            
            return True
            
        except Exception as e:
            print(f"[UART] Send error: {e}")
            return False
    
    def parse_command(self, cmd_str):
        """Parse command string into (command, args_dict)."""
        if not cmd_str:
            return None, None
        
        parts = cmd_str.split(":")
        command = parts[0].upper()
        
        if command == "START":
            # START:<duration_sec>:<temp_threshold>
            try:
                duration = int(parts[1]) if len(parts) > 1 else config.DEFAULT_CAPTURE_DURATION
                threshold = int(parts[2]) if len(parts) > 2 else config.BURN_TEMP_DELTA
                
                return "START", {
                    "duration_sec": duration,
                    "temp_threshold": threshold
                }
            except (ValueError, IndexError):
                return "START", {
                    "duration_sec": config.DEFAULT_CAPTURE_DURATION,
                    "temp_threshold": config.BURN_TEMP_DELTA
                }
        
        elif command == "STOP":
            return "STOP", {}
        
        elif command == "STATUS":
            return "STATUS", {}
        
        elif command == "RESULTS":
            return "RESULTS", {}
        
        elif command == "RESET":
            return "RESET", {}
        
        elif command == "FIRESTATUS":
            return "FIRESTATUS", {}
        else:
            return "UNKNOWN", {"original": cmd_str}
    
    def handle_command(self, command, args, callbacks):
        """Execute command via callbacks and return response dict."""
        if command == "START":
            if self.state != SystemState.IDLE:
                return {
                    "status": "error",
                    "message": f"Cannot start: system in {self.state.value} state"
                }
            
            if 'start' in callbacks:
                success = callbacks['start'](args['duration_sec'], args['temp_threshold'])
                if success:
                    self.state = SystemState.BUSY
                    return {
                        "status": "started",
                        "duration_sec": args['duration_sec'],
                        "temp_threshold": args['temp_threshold']
                    }
                else:
                    self.state = SystemState.ERROR
                    return {
                        "status": "error",
                        "message": "Failed to start capture"
                    }
        
        elif command == "STOP":
            if 'stop' in callbacks:
                callbacks['stop']()
            self.state = SystemState.IDLE
            return {"status": "stopped"}
        
        elif command == "STATUS":
            if 'status' in callbacks:
                status_data = callbacks['status']()
                return {
                    "status": self.state.value,
                    **status_data
                }
            else:
                return {"status": self.state.value}
        
        elif command == "RESULTS":
            if self.last_results:
                return {
                    "status": "complete",
                    **self.last_results
                }
            else:
                return {
                    "status": self.state.value,
                    "message": "No results available"
                }
        
        elif command == "RESET":
            if 'reset' in callbacks:
                callbacks['reset']()
            self.state = SystemState.IDLE
            self.last_results = None
            return {"status": "reset", "message": "System reset"}
	
        elif command == "FIRESTATUS":
            fire_lit = False
            if 'status' in callbacks:
                status_data = callbacks['status']()
                fire_lit = status_data.get('avg_ros_cm2_per_sec',0) < 0
            return {
                "status": "true" if fire_lit else "false"}
        else:
            return {
                "status": "error",
                "message": f"Unknown command: {command}"
            }

    def send_live_update(self, update_data):
        """Send live update during capture/analysis."""
        self.last_live_update = update_data
        response = {
            "type": "live_update",
            **update_data
        }
        self.send_response(response)
    
    def update_state(self, new_state):
        """Update system state."""
        if isinstance(new_state, str):
            new_state = SystemState(new_state)
        self.state = new_state
        print(f"[UART] State: {self.state.value}")
    
    def store_results(self, results):
        """Store results for RESULTS command."""
        self.last_results = results
        self.state = SystemState.IDLE  # Return to idle after completion

