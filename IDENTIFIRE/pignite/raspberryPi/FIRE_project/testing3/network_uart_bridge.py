#!/usr/bin/env python3
"""
Network bridge for UART testing - runs on Pi.
Accepts TCP connections and forwards to main.py UART logic.
"""

import socket
import threading
import time
import json
import os
import sys
sys.path.insert(0, '/home/fire/Documents/FIRE_project/testing3')

from uart_controller import UARTController, SystemState
from capture_manager import CaptureManager
from burn_analyzer import BurnAnalyzer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from queue import Queue
import queue
import config

# Same FrameProcessor from main.py
class FrameProcessor:
    """Processes frames via queue and worker threads."""
    
    def __init__(self, analyzer, uart_controller=None):
        self.analyzer = analyzer
        self.uart = uart_controller
        self.frame_queue = Queue()
        self.workers = []
        self.running = False
        self.frame_counter = 0
    
    def start_workers(self, num_workers=None):
        """Start worker threads."""
        if num_workers is None:
            num_workers = config.NUM_ANALYZER_THREADS
        
        self.running = True
        for i in range(num_workers):
            worker = threading.Thread(target=self._worker, name=f"Worker-{i}", daemon=True)
            worker.start()
            self.workers.append(worker)
        
        print(f"[Processor] Started {num_workers} worker threads")
    
    def _worker(self):
        """Worker thread - processes frames from queue."""
        while self.running:
            try:
                file_path = self.frame_queue.get(timeout=1)
                result = self.analyzer.process_frame(file_path)
                self.frame_counter += 1
                self.frame_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                if self.running:
                    print(f"[Processor] Error: {e}")
                self.frame_queue.task_done()
                continue
    
    def add_frame(self, file_path):
        self.frame_queue.put(file_path)
    
    def wait_for_completion(self):
        self.frame_queue.join()
    
    def stop(self):
        self.running = False
        for worker in self.workers:
            worker.join(timeout=2)

class FrameWatcher(FileSystemEventHandler):
    def __init__(self, processor, file_prefix=None):
        self.processor = processor
        self.file_prefix = file_prefix or config.FILE_PREFIX
    
    def on_created(self, event):
        if event.is_directory:
            return
        filename = os.path.basename(event.src_path)
        if filename.startswith(self.file_prefix) and filename.endswith(config.FILE_EXTENSION):
            print(f"[Watcher] New frame: {filename}")
            self.processor.add_frame(event.src_path)

class NetworkBridge:
    def __init__(self, port=5000):
        self.port = port
        self.capture_manager = CaptureManager()
        self.analyzer = BurnAnalyzer()
        self.processor = FrameProcessor(self.analyzer, None)
        self.observer = None
        
        self.mock_uart = type('obj', (object,), {
            'state': SystemState.IDLE,
            'last_results': None
        })()
        
    def initialize(self):
        """Initialize system."""
        print("Initializing...")
        self.capture_manager.setup_tmpfs()
        self.capture_manager.cleanup_old_frames()
        self.processor.start_workers()
        
        # Start file watcher
        self.observer = Observer()
        handler = FrameWatcher(self.processor)
        self.observer.schedule(handler, path=config.CAPTURE_FOLDER, recursive=False)
        self.observer.start()
        print("✓ Ready")
    
    def handle_start(self, duration_sec, temp_threshold):
        """Start capture."""
        if self.mock_uart.state != SystemState.IDLE:
            return {"status": "error", "message": f"System busy ({self.mock_uart.state.value})"}
        
        self.analyzer.reset()
        self.analyzer.temp_threshold_delta = temp_threshold
        self.capture_manager.cleanup_old_frames()
        
        success = self.capture_manager.start_capture(duration_sec=duration_sec)
        
        if success:
            self.mock_uart.state = SystemState.BUSY
            threading.Thread(target=self._monitor_capture, daemon=True).start()
            return {
                "status": "started",
                "duration_sec": duration_sec,
                "temp_threshold": temp_threshold
            }
        else:
            self.mock_uart.state = SystemState.ERROR
            return {"status": "error", "message": "Capture failed to start"}
    
    def _monitor_capture(self):
        """Monitor capture and analyze."""
        import json
        success = self.capture_manager.wait_for_completion()
        
        if not success:
            self.mock_uart.state = SystemState.ERROR
            return
        
        print("[Monitor] Capture complete, waiting for analysis...")
        self.processor.wait_for_completion()
        
        summary = self.analyzer.get_summary_statistics()
        self.mock_uart.last_results = summary
        self.mock_uart.state = SystemState.IDLE
        
        print("[Monitor] Analysis complete")
        self.analyzer.print_summary()
    
    def handle_stop(self):
        """Stop capture."""
        self.capture_manager.stop_capture()
        self.mock_uart.state = SystemState.IDLE
        return {"status": "stopped"}
    
    def handle_status(self):
        """Get status."""
        capture_status = self.capture_manager.get_capture_status()
        
        if self.mock_uart.state == SystemState.BUSY:
            live_update = self.analyzer.get_live_update()
            return {
                **capture_status,
                **live_update,
                "state": self.mock_uart.state.value
            }
        else:
            return {
                **capture_status,
                "state": self.mock_uart.state.value
            }
    
    def handle_results(self):
        """Get results."""
        if self.mock_uart.last_results:
            return {
                "status": "complete",
                **self.mock_uart.last_results
            }
        else:
            return {
                "status": self.mock_uart.state.value,
                "message": "No results available"
            }
    
    def handle_reset(self):
        """Reset system."""
        self.analyzer.reset()
        self.capture_manager.cleanup_old_frames()
        self.mock_uart.state = SystemState.IDLE
        self.mock_uart.last_results = None
        return {"status": "reset"}
    
    def parse_command(self, cmd_str):
        """Parse command."""
        parts = cmd_str.split(":")
        command = parts[0].upper()
        
        if command == "START":
            try:
                duration = int(parts[1]) if len(parts) > 1 else 60
                threshold = int(parts[2]) if len(parts) > 2 else 100
                return command, {"duration": duration, "threshold": threshold}
            except:
                return command, {"duration": 60, "threshold": 100}
        
        return command, {}
    
    def handle_client(self, conn, addr):
        """Handle client connection."""
        print(f"[Network] Client connected: {addr}")
        
        try:
            while True:
                data = conn.recv(1024).decode().strip()
                if not data:
                    break
                
                print(f"[Network] Received: {data}")
                command, args = self.parse_command(data)
                
                if command == "START":
                    response = self.handle_start(args["duration"], args["threshold"])
                elif command == "STOP":
                    response = self.handle_stop()
                elif command == "STATUS":
                    response = self.handle_status()
                elif command == "RESULTS":
                    response = self.handle_results()
                elif command == "RESET":
                    response = self.handle_reset()
                else:
                    response = {"status": "error", "message": f"Unknown command: {command}"}
                
                conn.sendall(json.dumps(response).encode() + b'\n')
        
        except Exception as e:
            print(f"[Network] Error: {e}")
        finally:
            conn.close()
            print(f"[Network] Client disconnected: {addr}")
    
    def run(self):
        """Run server."""
        self.initialize()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', self.port))
        sock.listen(1)
        
        print(f"[Network] Listening on port {self.port}...")
        print(f"[Network] Ready for connections!\n")
        
        try:
            while True:
                conn, addr = sock.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            print("\n[Network] Shutting down...")
        finally:
            sock.close()
            self.observer.stop()
            self.observer.join()
            self.processor.stop()

if __name__ == "__main__":
    import os
    bridge = NetworkBridge()
    bridge.run()
