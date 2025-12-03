# main_pipeline.py
import os
import subprocess
import time
from queue import Queue
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Shared folder
CAPTURE_FOLDER = "/tmp/capture"
FILE_PREFIX = "sample_"

# --- Thread-safe queue ---
file_queue = Queue()

# --- Watchdog handler for new files ---
class FileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and os.path.basename(event.src_path).startswith(FILE_PREFIX):
            print(f"[Watcher] New file: {event.src_path}")
            file_queue.put(event.src_path)

# --- Analyzer thread ---
def analyzer():
    while True:
        file_path = file_queue.get()  # blocks until a file is available
        print(f"[Analyzer] Processing: {file_path}")
        # Call your Measure_ROS.py logic here or import its functions
        subprocess.run(["python3", "Measure_ROS_test.py", file_path])
        file_queue.task_done()

# --- Capture function ---
def capture(num_frames=1, prefix=FILE_PREFIX):
    cmd = ["lepton_data_collector", "-3", "-c", str(num_frames), "-o", os.path.join(CAPTURE_FOLDER, prefix)]
    print(f"[Capture] Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"[Capture] Done: {num_frames} frames saved with prefix '{prefix}'")

# --- Setup tmpfs ---
def setup():
    os.makedirs(CAPTURE_FOLDER, exist_ok=True)
    mounts = subprocess.run(["mount"], capture_output=True, text=True)
    if CAPTURE_FOLDER not in mounts.stdout:
        subprocess.run(["mount", "-t", "tmpfs", "tmpfs", CAPTURE_FOLDER], check=True)
        print("[Setup] Mounted tmpfs")
    else:
        print("[Setup] tmpfs already mounted")

# --- Main loop ---
def main():
    setup()

    # Start analyzer thread
    threading.Thread(target=analyzer, daemon=True).start()

    # Start watchdog observer
    observer = Observer()
    observer.schedule(FileHandler(), path=CAPTURE_FOLDER, recursive=False)
    observer.start()

    try:
        while True:
            capture(num_frames=1)  # capture one frame at a time
            time.sleep(0.1)        # small delay between captures
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()

