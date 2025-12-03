import serial
import time
import subprocess
import os

def setup():
    # Create /tmp/capture if it doesn't exist
    os.makedirs("/tmp/capture", exist_ok=True)

    # Mount tmpfs only if not already mounted
    mounts = subprocess.run(["mount"], capture_output=True, text=True)
    if "/tmp/capture" not in mounts.stdout:
        subprocess.run(["mount", "-t", "tmpfs", "tmpfs", "/tmp/capture"], check=True)
        print("[INFO] Mounted /tmp/capture as tmpfs")
    else:
        print("[INFO] /tmp/capture already mounted")

def capture(num_frames, name="sample"):
    # Run the Lepton data collector
    cmd = [
        "lepton_data_collector",
        "-3",
        "-c", str(num_frames),
        "-o", f"/tmp/capture/{name}_"
    ]
    print(f"[INFO] Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"[INFO] Capture complete: {num_frames} frames saved with prefix '{name}_'")

def process_capture():
    # Placeholder for post-processing captured frames
    cmd = ["python3", "Measure_ROS.py"]
    print(f"[INFO] Running data processing")
    result = subprocess.run(cmd, check=True, capture_output = True, text = True)
    print(f"[INFO] Data is processed")
    return result

def main():
    setup()
    capture(10, name="test")
    result = process_capture()
    print(result.stdout)

if __name__ == "__main__":
    main()

