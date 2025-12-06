import numpy as np
import glob
import os
import tifffile
from scipy.ndimage import gaussian_filter, rotate, sobel

# ---------------- CONFIG ----------------
folder = r"C:\fire\timestamped_captures\20251205_141600"
width = 160
height = 120

rotation_angle = 2.2  # degrees, positive = counter-clockwise

apply_threshold = True
threshold_value = 40000  

upper_threshold = True
upper_threshold_value = 47000 

gaussian_blur = True
gaussian_sigma = 1     # recommended if enabling blur

# Temporal median parameters (BEST for flames)
use_temporal_median = True
median_window = 20  

# ---------------- LOAD AND ROTATE 16-BIT BIG-ENDIAN FRAMES ----------------
def load_gray(path, width, height, rotation_angle=0, crop_sample=True):
    with open(path, "rb") as f:
        data = f.read()
    
    arr = np.frombuffer(data, dtype='>u2').reshape((height, width))
    
    # Rotate
    if rotation_angle != 0:
        arr = rotate(arr, rotation_angle, reshape=False, order=1, mode='nearest')
    
    # Crop to 12×12 cm sample
    if crop_sample:
        y_start, y_end = 35, 106
        x_start, x_end = 50, 120
        arr = arr[y_start:y_end, x_start:x_end]
    
    return arr.astype(np.uint16)

# ---------------- COLLECT FILES ----------------
paths = sorted(glob.glob(os.path.join(folder, "*.gray")))
print(f"Found {len(paths)} frames.")

frames_16bit = [load_gray(p, width, height, rotation_angle) for p in paths]

# ---------------- PROCESSING WITH TEMPORAL MEDIAN + SOBEL ----------------
frames_processed = []
buffer = []   # temporal window for flame suppression

for frame in frames_16bit:
    processed = frame.copy()

    if gaussian_blur:
        processed = gaussian_filter(processed, sigma=gaussian_sigma)

    # ---- Thresholding ----
    if apply_threshold:
        processed = (processed > threshold_value).astype(np.uint16) * processed

    if upper_threshold:
        processed = (processed < upper_threshold_value).astype(np.uint16) * processed

    # ---- Optional Gaussian smoothing ----
    if gaussian_blur:
        processed = gaussian_filter(processed, sigma=gaussian_sigma)

    # ---- Temporal median (FIRE FLICKER REDUCTION) ----
    if use_temporal_median:
        buffer.append(processed)
        if len(buffer) > median_window:
            buffer.pop(0)
        processed = np.median(buffer, axis=0).astype(np.uint16)

    # ---- SOBEL EDGE DETECTION ----
    gx = sobel(processed, axis=1)   # horizontal gradients
    gy = sobel(processed, axis=0)   # vertical gradients
    magnitude = np.hypot(gx, gy).astype(np.uint16)

    #processed = magnitude

    frames_processed.append(processed)

# ---------------- SAVE ----------------
tiff_path = os.path.join(folder, "thermal_stack.tiff")
tifffile.imwrite(tiff_path, np.stack(frames_processed), byteorder='>')

print(f"Saved big-endian 16-bit TIFF stack to {tiff_path}")
