# capture_manager.py
# Manages thermal image capture from Lepton camera

import os
import subprocess
import time
import glob
from pathlib import Path
import config
import utils


class CaptureManager:
    """Manages Lepton camera capture via lepton_data_collector on tmpfs."""
    
    def __init__(self, capture_folder=None, file_prefix=None):
        """Initialize capture manager with optional folder/prefix override."""
        self.capture_folder = capture_folder or config.CAPTURE_FOLDER
        self.file_prefix = file_prefix or config.FILE_PREFIX
        self.is_capturing = False
        self.capture_process = None
        self.capture_start_time = None
        self.expected_frames = 0
    
    def verify_camera(self):
        """Verify lepton_data_collector and camera are available."""
        # Check if lepton_data_collector exists
        try:
            result = subprocess.run(
                ["which", "lepton_data_collector"],
                capture_output=True,
                timeout=2
            )
            if result.returncode != 0:
                print("[Capture] lepton_data_collector not found in PATH")
                return False
        except subprocess.TimeoutExpired:
            print("[Capture] Timeout checking for lepton_data_collector")
            return False
        except Exception as e:
            print(f"[Capture] Error checking for lepton_data_collector: {e}")
            return False
        
        # Check if video device exists
        video_devices = glob.glob("/dev/video*")
        if not video_devices:
            print("[Capture] No video devices found")
            return False
        
        # Check if lepton module is loaded
        try:
            result = subprocess.run(
                ["lsmod"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if "lepton" not in result.stdout:
                print("[Capture] Lepton kernel module not loaded")
                return False
        except Exception:
            # If lsmod fails, we can't verify but don't fail completely
            pass
        
        return True
        
    def setup_tmpfs(self):
        """Create capture folder and mount tmpfs if needed."""
        # Create folder if it doesn't exist
        utils.ensure_dir(self.capture_folder)
        
        # Check if tmpfs is already mounted
        result = subprocess.run(
            ["mount"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if self.capture_folder not in result.stdout:
            try:
                # Mount tmpfs
                subprocess.run(
                    ["sudo", "mount", "-t", "tmpfs", "tmpfs", self.capture_folder],
                    check=True,
                    timeout=10
                )
                print(f"[Capture] Mounted tmpfs at {self.capture_folder}")
            except subprocess.CalledProcessError as e:
                print(f"[Capture] Warning: Could not mount tmpfs: {e}")
                print(f"[Capture] Using regular filesystem")
            except subprocess.TimeoutExpired:
                print(f"[Capture] Warning: Mount command timed out")
        else:
            print(f"[Capture] tmpfs already mounted at {self.capture_folder}")
        
        # Verify folder is writable
        test_file = os.path.join(self.capture_folder, ".test")
        try:
            Path(test_file).touch()
            os.remove(test_file)
        except Exception as e:
            raise RuntimeError(f"Capture folder not writable: {e}")
    
    def cleanup_old_frames(self):
        """Remove old .gray files from capture folder."""
        pattern = os.path.join(self.capture_folder, "*.gray")
        old_files = glob.glob(pattern)
        
        for file_path in old_files:
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"[Capture] Warning: Could not remove {file_path}: {e}")
        
        if old_files:
            print(f"[Capture] Cleaned up {len(old_files)} old frames")
    
    def start_capture(self, duration_sec=None, num_frames=None):
        """Start Lepton capture subprocess (duration_sec or num_frames)."""
        if self.is_capturing:
            print("[Capture] Already capturing!")
            return False
        
        # Calculate number of frames
        if duration_sec is not None:
            num_frames = int(duration_sec * config.DEFAULT_CAPTURE_FPS)
        elif num_frames is None:
            num_frames = int(config.DEFAULT_CAPTURE_DURATION * config.DEFAULT_CAPTURE_FPS)
        
        self.expected_frames = num_frames
        
        # Build command
        output_prefix = os.path.join(self.capture_folder, self.file_prefix)
        cmd = [
            "lepton_data_collector",
            "-3",  # Lepton 3.x mode
            "-c", str(num_frames),
            "-o", output_prefix
        ]
        
        print(f"[Capture] Starting capture: {num_frames} frames ({num_frames/config.DEFAULT_CAPTURE_FPS:.1f}s)")
        print(f"[Capture] Command: {' '.join(cmd)}")
        
        try:
            # Start capture process
            self.capture_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.is_capturing = True
            self.capture_start_time = time.time()
            
            # Give it a moment to start
            time.sleep(0.5)
            
            # Check if process is still running
            if self.capture_process.poll() is not None:
                # Process terminated immediately - likely an error
                stdout, stderr = self.capture_process.communicate()
                print(f"[Capture] Error: Capture process failed")
                print(f"[Capture] stdout: {stdout}")
                print(f"[Capture] stderr: {stderr}")
                self.is_capturing = False
                return False
            
            return True
            
        except FileNotFoundError:
            print("[Capture] Error: lepton_data_collector not found")
            print("[Capture] Make sure Lepton drivers are installed")
            self.is_capturing = False
            return False
        except Exception as e:
            print(f"[Capture] Error starting capture: {e}")
            self.is_capturing = False
            return False
    
    def wait_for_completion(self, timeout=None):
        """Wait for capture subprocess to complete."""
        if not self.is_capturing or self.capture_process is None:
            return False
        
        if timeout is None:
            # Default timeout: expected duration + 30 seconds buffer
            timeout = (self.expected_frames / config.DEFAULT_CAPTURE_FPS) + 30
        
        try:
            self.capture_process.wait(timeout=timeout)
            self.is_capturing = False
            
            # Check return code
            if self.capture_process.returncode == 0:
                print(f"[Capture] Capture completed successfully")
                return True
            else:
                stdout, stderr = self.capture_process.communicate()
                print(f"[Capture] Capture failed with code {self.capture_process.returncode}")
                print(f"[Capture] stderr: {stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"[Capture] Timeout waiting for capture")
            self.stop_capture()
            return False
    
    def stop_capture(self):
        """Terminate capture subprocess (emergency stop)."""
        if not self.is_capturing or self.capture_process is None:
            return
        
        print("[Capture] Stopping capture...")
        self.capture_process.terminate()
        
        try:
            self.capture_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("[Capture] Force killing capture process")
            self.capture_process.kill()
        
        self.is_capturing = False
    
    def get_captured_frames(self):
        """Get sorted list of captured .gray files."""
        pattern = os.path.join(self.capture_folder, f"{self.file_prefix}*.gray")
        frames = sorted(glob.glob(pattern))
        return frames
    
    def get_capture_status(self):
        """Get current capture progress and frame count."""
        captured_frames = len(self.get_captured_frames())
        
        if not self.is_capturing:
            return {
                'is_capturing': False,
                'frames_captured': captured_frames,
                'expected_frames': self.expected_frames,
            }
        
        elapsed = time.time() - self.capture_start_time if self.capture_start_time else 0
        progress_pct = (captured_frames / self.expected_frames * 100) if self.expected_frames > 0 else 0
        
        return {
            'is_capturing': True,
            'frames_captured': captured_frames,
            'expected_frames': self.expected_frames,
            'elapsed_sec': elapsed,
            'progress_percent': progress_pct,
        }

