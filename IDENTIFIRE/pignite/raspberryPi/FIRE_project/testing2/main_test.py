# main.py
import os
import subprocess
import threading
from queue import Queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from Measure_ROS import update  # your frame processor
import time

CAPTURE_FOLDER = "/tmp/capture4"
FILE_PREFIX = "sample_"
file_queue = Queue()

# --- Watchdog handler ---
class FileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and os.path.basename(event.src_path).endswith(".gray"):
            print(f"[Watcher] New file: {event.src_path}")
            file_queue.put(event.src_path)

# --- Analyzer thread ---
def analyzer():
    while True:
        file_path = file_queue.get()
        update(file_path)
        file_queue.task_done()

# --- Setup tmpfs folder ---
def setup():
    os.makedirs(CAPTURE_FOLDER, exist_ok=True)
    mounts = subprocess.run(["mount"], capture_output=True, text=True)
    if CAPTURE_FOLDER not in mounts.stdout:
        subprocess.run(["mount", "-t", "tmpfs", "tmpfs", CAPTURE_FOLDER], check=True)
        print("[Setup] Mounted tmpfs")
        time.sleep(0.1)
    else:
        print("[Setup] tmpfs already mounted")

# --- Capture function ---
def capture(num_frames=200, prefix=FILE_PREFIX):
    cmd = ["lepton_data_collector", "-3", "-c", str(num_frames), "-o", os.path.join(CAPTURE_FOLDER, prefix)]
    print(f"[Capture] Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"[Capture] Done: {num_frames} frames saved.")

# --- Main function ---
def main():
    setup()

    # Start analyzer threads (2 threads for example)
    for _ in range(2):
        threading.Thread(target=analyzer, daemon=True).start()

    # Start watchdog
    observer = Observer()
    observer.schedule(FileHandler(), path=CAPTURE_FOLDER, recursive=False)
    observer.start()

    try:
        # Capture 200 frames in a single batch
        capture(num_frames=200)

        # Wait until all frames are processed
        file_queue.join()
        print("[Analyzer] All frames processed.")

    except KeyboardInterrupt:
        print("[Main] Interrupted!")
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    main()

