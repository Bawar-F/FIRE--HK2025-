import os
import subprocess
import threading
from queue import Queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import serial
import time
from Measure_ROS import update  # your frame processor

CAPTURE_FOLDER = "/tmp/capture4"
FILE_PREFIX = "sample_"
file_queue = Queue()
capture_process = None  # to store subprocess of capture
observer = None  # Watchdog observer

# ---------------- Watchdog handler ----------------
class FileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and os.path.basename(event.src_path).endswith(".gray"):
            print(f"[Watcher] New file: {event.src_path}")
            file_queue.put(event.src_path)

# ---------------- Analyzer thread ----------------
def analyzer():
    while True:
        file_path = file_queue.get()
        update(file_path)
        file_queue.task_done()

# ---------------- Setup tmpfs folder ----------------
def setup_tmpfs():
    os.makedirs(CAPTURE_FOLDER, exist_ok=True)
    mounts = subprocess.run(["mount"], capture_output=True, text=True)
    if CAPTURE_FOLDER not in mounts.stdout:
        subprocess.run(["mount", "-t", "tmpfs", "tmpfs", CAPTURE_FOLDER], check=True)
        print("[Setup] Mounted tmpfs")
    else:
        print("[Setup] tmpfs already mounted")

# ---------------- Capture function ----------------
def start_capture(num_frames=200, prefix=FILE_PREFIX):
    global capture_process
    cmd = ["lepton_data_collector", "-3", "-c", str(num_frames),
           "-o", os.path.join(CAPTURE_FOLDER, prefix)]
    print(f"[Capture] Running: {' '.join(cmd)}")
    capture_process = subprocess.Popen(cmd)
    print(f"[Capture] Capture started.")

def stop_capture():
    global capture_process
    if capture_process:
        capture_process.terminate()
        capture_process.wait()
        capture_process = None
        print("[Capture] Capture stopped.")

# ---------------- Main program ----------------
def main():
    global observer
    setup_tmpfs()

    # Start analyzer threads
    for _ in range(2):
        threading.Thread(target=analyzer, daemon=True).start()

    # Start watchdog
    observer = Observer()
    observer.schedule(FileHandler(), path=CAPTURE_FOLDER, recursive=False)
    observer.start()

    # Setup UART (serial0)
    ser = serial.Serial("/dev/serial0", 9600, timeout=1)
    print("[UART] Waiting for commands on /dev/serial0...")

    try:
        while True:
            if ser.in_waiting:
                cmd = ser.readline().decode("utf-8").strip().upper()
                if not cmd:
                    continue

                print(f"[UART] Received command: {cmd}")

                if cmd == "START":
                    start_capture()
                elif cmd == "STOP":
                    stop_capture()
                elif cmd == "RESET":
                    stop_capture()
                    setup_tmpfs()
                    # Clear any queued files
                    while not file_queue.empty():
                        file_queue.get()
                    print("[System] Reset complete.")
                else:
                    print(f"[UART] Unknown command: {cmd}")

            time.sleep(0.05)  # small delay to reduce CPU usage

    except KeyboardInterrupt:
        print("[Main] Interrupted!")

    finally:
        stop_capture()
        if observer:
            observer.stop()
            observer.join()
        ser.close()


if __name__ == "__main__":
    main()

