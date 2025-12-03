#!/usr/bin/env python3
# main.py
# Main orchestrator for FIRE burn chamber analysis system

import sys
import os
import time
import threading
import queue
from queue import Queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import config
from uart_controller import UARTController, SystemState
from capture_manager import CaptureManager
from burn_analyzer import BurnAnalyzer


FIRE_IS_ACTIVE = False


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
                
                # Process frame
                result = self.analyzer.process_frame(file_path)
                self.frame_counter += 1
                self.frame_queue.task_done()
                
            except queue.Empty:
                # Timeout waiting for frame - normal when idle
                continue
            except Exception as e:
                if self.running:
                    print(f"[Processor] Error processing frame: {e}")
                    import traceback
                    traceback.print_exc()
                self.frame_queue.task_done()
                continue
    
    def add_frame(self, file_path):
        """Add frame to queue."""
        self.frame_queue.put(file_path)
    
    def wait_for_completion(self):
        """Wait for all queued frames to be processed."""
        self.frame_queue.join()
    
    def stop(self):
        """Stop worker threads."""
        self.running = False
        for worker in self.workers:
            worker.join(timeout=2)


class FrameWatcher(FileSystemEventHandler):
    """Watches for new .gray files and queues them for processing."""
    
    def __init__(self, processor, file_prefix=None):
        self.processor = processor
        self.file_prefix = file_prefix or config.FILE_PREFIX
    
    def on_created(self, event):
        """Queue new .gray files for processing."""
        if event.is_directory:
            return
        
        filename = os.path.basename(event.src_path)
        if filename.startswith(self.file_prefix) and filename.endswith(config.FILE_EXTENSION):
            print(f"[Watcher] New frame: {filename}")
            self.processor.add_frame(event.src_path)


class BurnChamberSystem:
    """Main system orchestrator - integrates UART, capture, and analysis."""
    
    def __init__(self):
        self.uart = UARTController()
        self.capture_manager = CaptureManager()
        self.analyzer = BurnAnalyzer()
        self.analyzer.auto_stop_callback = self._auto_stop_capture
        self.processor = FrameProcessor(self.analyzer, self.uart)
        self.observer = None
        
        # State
        self.current_capture_duration = None

    def _auto_stop_capture(self):
        """Called by BurnAnalyzer when fire has truly stopped"""
        print("[System] AUTO-STOP triggered by low ROS")

        # 1. Stop the camera (exactly like a real STOP command)
        self.capture_manager.stop_capture()

        # 2. Wait a moment for final frames to be processed
        time.sleep(1)
        self.processor.wait_for_completion()

        # 3. Generate and send final results
        summary = self.analyzer.get_summary_statistics()

        avg_ros = summary['avg_ros_cm2_per_sec']
        peak_ros = summary['max_ros_cm2_per_sec']
        burn_pct = summary['final_burn_percentage']

        final_line = f"FINAL,{avg_ros:.2f},{peak_ros:.2f},{burn_pct:.1f}"
        self.uart.send_response(final_line)
        print(f"[UART] AUTO-SENT → {final_line}")

        # 4. Go back to IDLE
        self.uart.update_state(SystemState.IDLE)
        self.analyzer.print_summary()



    
    def initialize(self):
        """Initialize all system components."""
        print("="*60)
        print("FIRE Burn Chamber Analysis System")
        print("="*60)
        config.print_config()
        
        # Verify camera is available
        print("[System] Verifying camera...")
        if not self.capture_manager.verify_camera():
            print("[System] WARNING: Camera not detected!")
            print("[System] Check if:")
            print("  - Lepton module is loaded: lsmod | grep lepton")
            print("  - Device exists: ls /dev/video*")
        else:
            print("[System] Camera verified OK")
        
        # Setup capture folder
        print("[System] Setting up capture folder...")
        self.capture_manager.setup_tmpfs()
        self.capture_manager.cleanup_old_frames()
        
        # Connect UART
        print("[System] Connecting to Arduino...")
        if not self.uart.connect():
            print("[System] WARNING: UART not connected, running in standalone mode")
        
        # Start frame processor
        self.processor.start_workers()
        
        # Start file watcher
        self.observer = Observer()
        handler = FrameWatcher(self.processor)
        self.observer.schedule(handler, path=config.CAPTURE_FOLDER, recursive=False)
        self.observer.start()
        
        print("[System] Initialization complete\n")

        self.uart.send_response("1")

    
    def shutdown(self):
        """Gracefully shutdown all components."""
        print("\n[System] Shutting down...")
        
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        self.processor.stop()
        self.uart.disconnect()
        
        print("[System] Shutdown complete")
    
    # Callback functions for UART commands
    
    def _start_capture(self, duration_sec, temp_threshold):
        """UART callback - start capture."""
        print(f"[System] Starting capture: {duration_sec}s, threshold: {temp_threshold}°C")
        
        # Update analyzer threshold
        self.analyzer.reset()
        self.analyzer.temp_threshold_delta = temp_threshold

        self.analyzer.auto_stop_callback = self._auto_stop_capture

        
        # Cleanup old frames
        self.capture_manager.cleanup_old_frames()
        
        # Start capture
        success = self.capture_manager.start_capture(duration_sec=duration_sec)
        
        if success:
            self.current_capture_duration = duration_sec
            self.uart.update_state(SystemState.BUSY)
            
            # Start monitoring thread
            threading.Thread(target=self._monitor_capture, daemon=True).start()
        
        return success
    
    def _monitor_capture(self):
        """Background thread - monitor capture progress."""
        import json
        
        # Wait for capture to complete
        success = self.capture_manager.wait_for_completion()
        
        if not success:
            self.uart.update_state(SystemState.ERROR)
            self.uart.send_response({
                "status": "error",
                "message": "Capture failed"
            })
            return
        
        # Wait for all frames to be processed
        print("[System] Capture complete, waiting for analysis...")
        
        # Save intermediate results every 10 seconds during processing
        while not self.processor.frame_queue.empty():
            time.sleep(10)
            partial_summary = self.analyzer.get_summary_statistics()
            with open(config.PARTIAL_RESULTS_PATH, "w") as f:
                json.dump(partial_summary, f)
        
        self.processor.wait_for_completion()
        
        # Generate final results
        print("[System] Analysis complete, generating results...")
        summary = self.analyzer.get_summary_statistics()
        
        # Store and send results
        self.uart.store_results(summary)
        self.uart.send_response({
            "status": "complete",
            "type": "final_results",
            **summary
        })
        
        # Print summary
        self.analyzer.print_summary()
    
    def _stop_capture(self):
        """UART callback - emergency stop."""
        print("[System] Emergency stop requested")
        self.capture_manager.stop_capture()
        self.uart.update_state(SystemState.IDLE)
    
    def _get_status(self):
        """UART callback - get live status."""
        capture_status = self.capture_manager.get_capture_status()
        
        if self.uart.state == SystemState.BUSY:
            # Return live analysis update
            live_update = self.analyzer.get_live_update()
            return {
                **capture_status,
                **live_update
            }
        else:
            return capture_status
    
    def _reset_system(self):
        """UART callback - reset system."""
        print("[System] Resetting system...")
        self.analyzer.reset()
        self.capture_manager.cleanup_old_frames()
        self.processor.frame_counter = 0
    
    def run(self):
        """Main event loop - wait for UART commands."""
        self.initialize()
        
        # Setup callbacks
        callbacks = {
            'start': self._start_capture,
            'stop': self._stop_capture,
            'status': self._get_status,
            'reset': self._reset_system
        }
        
        try:
            print("[System] Ready! Waiting for Arduino commands...\n")
            
            while True:
                # Check for UART commands
                cmd_str = self.uart.read_command()
                
                if cmd_str:
                    command, args = self.uart.parse_command(cmd_str)
                    response = self.uart.handle_command(command, args, callbacks)
                    self.uart.send_response(response)
                
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            print("\n[System] Interrupted by user")
        
        finally:
            self.shutdown()


# Standalone capture mode (no UART)
def standalone_capture(duration_sec=None, temp_threshold=None):
    """Run capture/analysis without UART (testing mode)."""
    duration_sec = duration_sec or config.DEFAULT_CAPTURE_DURATION
    temp_threshold = temp_threshold or config.BURN_TEMP_DELTA
    
    print("="*60)
    print("FIRE Burn Chamber - Standalone Mode")
    print("="*60)
    config.print_config()
    
    capture_manager = CaptureManager()
    analyzer = BurnAnalyzer(temp_threshold_delta=temp_threshold)
    processor = FrameProcessor(analyzer, uart_controller=None)
    
    # Setup
    capture_manager.setup_tmpfs()
    capture_manager.cleanup_old_frames()
    processor.start_workers()
    
    # Start file watcher
    observer = Observer()
    handler = FrameWatcher(processor)
    observer.schedule(handler, path=config.CAPTURE_FOLDER, recursive=False)
    observer.start()
    
    try:
        # Start capture
        print(f"\n[Standalone] Starting {duration_sec}s capture...")
        if not capture_manager.start_capture(duration_sec=duration_sec):
            print("[Standalone] Failed to start capture")
            return
        
        # Wait for completion
        capture_manager.wait_for_completion()
        
        # Wait for processing
        print("[Standalone] Waiting for analysis...")
        processor.wait_for_completion()
        
        # Print results
        analyzer.print_summary()
        
    except KeyboardInterrupt:
        print("\n[Standalone] Interrupted")
    
    finally:
        observer.stop()
        observer.join()
        processor.stop()


if __name__ == "__main__":
    import os
    import argparse
    
    parser = argparse.ArgumentParser(description="FIRE Burn Chamber Analysis System")
    parser.add_argument("--standalone", action="store_true", help="Run in standalone mode (no UART)")
    parser.add_argument("--duration", type=int, default=None, help="Capture duration in seconds")
    parser.add_argument("--threshold", type=int, default=None, help="Temperature threshold (°C)")
    
    args = parser.parse_args()
    
    if args.standalone:
        standalone_capture(args.duration, args.threshold)
    else:
        system = BurnChamberSystem()
        system.analyzer.ignition_frame = 1
        system.analyzer.ignition_time = 0.0
        system.analyzer.auto_stop_callback = system._auto_stop_capture

        system.run()
