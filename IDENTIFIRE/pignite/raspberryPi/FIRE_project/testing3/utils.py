import numpy as np
import time
import os
from pathlib import Path
import config

def raw_to_celsius(raw_data):
    """Convert Lepton raw values (Kelvin × 100) to Celsius."""
    kelvin = raw_data.astype(np.float32) / 100.0
    celsius = kelvin - 273.15
    return celsius


def celsius_to_raw(celsius):
    """Convert Celsius to raw Lepton values."""
    kelvin = celsius + 273.15
    raw = int(kelvin * 100)
    return np.uint16(raw)


def read_gray_file(file_path):
    """Read .gray file, return (raw_data, celsius_data)."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Read raw data
    with open(file_path, "rb") as f:
        data = f.read()
    
    if len(data) != config.EXPECTED_FILE_SIZE:
        raise ValueError(f"Invalid file size: {len(data)} bytes (expected {config.EXPECTED_FILE_SIZE})")
    
    raw_data = np.frombuffer(data, dtype=config.DTYPE_RAW).copy()
    raw_data = raw_data.reshape((config.IMAGE_HEIGHT, config.IMAGE_WIDTH))
    celsius_data = raw_to_celsius(raw_data)
    
    return raw_data, celsius_data


def extract_frame_number(file_path):
    """Extract frame number from filename (e.g., 'sample_000123.gray' → 123)."""
    filename = os.path.basename(file_path)
    try:
        number_str = filename.replace(config.FILE_PREFIX, "").replace(config.FILE_EXTENSION, "")
        return int(number_str)
    except ValueError:
        return -1

def get_timestamp_from_file(file_path):
    """Get file modification timestamp."""
    return os.path.getmtime(file_path)


def format_duration(seconds):
    """Format seconds as human-readable string (e.g., '2m 34s')."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def normalize_to_uint8(data, min_val=None, max_val=None):
    """Normalize array to 0-255 range."""
    if min_val is None:
        min_val = data.min()
    if max_val is None:
        max_val = data.max()
    
    if max_val == min_val:
        return np.zeros_like(data, dtype=np.uint8)
    
    normalized = (data - min_val) / (max_val - min_val) * 255
    normalized = np.clip(normalized, 0, 255)
    return normalized.astype(np.uint8)


def pixels_to_cm2(pixel_count):
    """Convert pixel count to area in cm²."""
    return pixel_count * config.PIXEL_AREA_CM2

def cm2_to_pixels(area_cm2):
    """Convert area in cm² to pixel count."""
    return int(area_cm2 / config.PIXEL_AREA_CM2)

def ensure_dir(directory):
    """Create directory if it doesn't exist."""
    Path(directory).mkdir(parents=True, exist_ok=True)

