
import numpy as np
import scipy.ndimage as ndi
import config
import utils
import threading
import importlib

# Optional: Otsu threshold via scikit-image
try:
    from skimage.filters import threshold_otsu
    HAS_SKIMAGE = True
except ImportError:
    HAS_SKIMAGE = False


class BurnAnalyzer:
    """Analyzes thermal sequences to calculate burn propagation and Rate of Spread.
       Stream-processing compatible, includes 16-bit preprocessing pipeline (rotation, crop,
       thresholding, Gaussian blur, temporal median). Outputs match original OpenCV version.
    """

    def __init__(self, temp_threshold_delta=None, baseline_percentile=None):
        self.temp_threshold_delta = temp_threshold_delta or config.BURN_TEMP_DELTA
        self.baseline_percentile = baseline_percentile or 50

        self.baseline_temp = None
        self.cumulative_burn_mask = None
        self.frame_count = 0
        self.first_frame_time = None
        self.frame_data = []

        # Temporal median buffer
        self._median_buffer = []

        self.ignition_frame = None
        self.ignition_time = None
        self.actual_fps = None

        self.ros_zero_streak = 0
        self.ROS_STOP_THRESHOLD = config.ROS_STOP_THRESHOLD
        self.MIN_ZERO_FRAMES = config.MIN_ZERO_FRAMES
        self.has_auto_stopped = False
        self.auto_stop_callback = None

    def reset(self):
        self.__init__(self.temp_threshold_delta, self.baseline_percentile)

    # -------------------------- BASELINE --------------------------
    def _establish_baseline(self, celsius_frame):
        self.baseline_temp = np.percentile(celsius_frame, self.baseline_percentile)
        self.cumulative_burn_mask = np.zeros(celsius_frame.shape, dtype=np.uint8)
        print(f"[Analyzer] Baseline: {self.baseline_temp:.1f}°C")

    # -------------------------- BURN DETECTION --------------------------
    def _detect_burn_temperature_based(self, celsius_frame):
        relative_threshold = self.baseline_temp + self.temp_threshold_delta
        effective_threshold = max(relative_threshold, config.MIN_BURN_TEMP_ABSOLUTE)
        return (celsius_frame > effective_threshold).astype(np.uint8) * 255

    def _detect_burn_otsu(self, celsius_frame):
        if not HAS_SKIMAGE:
            raise RuntimeError("Otsu thresholding requires scikit-image installed.")
        t = threshold_otsu(celsius_frame.astype(np.float32))
        mask = (celsius_frame > t)
        return (mask.astype(np.uint8) * 255)

    # -------------------------- FILTER SMALL REGIONS --------------------------
    def _filter_small_regions(self, burn_mask):
        binary = burn_mask > 0
        labels, num_labels = ndi.label(binary)
        refined = np.zeros_like(burn_mask)
        for label_val in range(1, num_labels + 1):
            component = (labels == label_val)
            if np.sum(component) >= config.MIN_CONTOUR_AREA_PIXELS:
                refined[component] = 255
        return refined

    def _preprocess_celsius_frame(self, celsius_frame):
        """Apply rotation, crop, Gaussian blur, and temporal median — all in Celsius space."""
        frame = celsius_frame.astype(np.float32)  # Work in float32 for safety

        # --- ROTATION ---
        rotation_angle = getattr(config, "ROTATION_ANGLE", 0)
        if rotation_angle != 0:
            frame = ndi.rotate(frame, rotation_angle, reshape=False, order=1, mode='nearest')

        # --- CROPPING ---
        if getattr(config, "CROP_REGION", None):
            y_start, y_end, x_start, x_end = config.CROP_REGION
            frame = frame[y_start:y_end, x_start:x_end]

        # --- GAUSSIAN BLUR (very safe in °C) ---
        if getattr(config, "GAUSSIAN_BLUR", False):
            sigma = getattr(config, "GAUSSIAN_SIGMA", 5)
            frame = ndi.gaussian_filter(frame, sigma=sigma)

        # --- TEMPORAL MEDIAN FILTER (excellent for reducing thermal noise) ---
        if getattr(config, "TEMPORAL_MEDIAN", True):
            self._median_buffer.append(frame.copy())
            median_window = getattr(config, "MEDIAN_WINDOW", 5)
            if len(self._median_buffer) > median_window:
                self._median_buffer.pop(0)
            if len(self._median_buffer) > 1:
                frame = np.median(self._median_buffer, axis=0)

        return frame

    # -------------------------- PREPROCESSING PIPELINE --------------------------
    def _preprocess_frame(self, raw_frame):
        """Apply rotation, crop, thresholding, Gaussian blur, and temporal median."""

        frame = raw_frame.astype(np.uint16)

        # --- ROTATION ---
        rotation_angle = getattr(config, "ROTATION_ANGLE", 0)
        if rotation_angle != 0:
            frame = ndi.rotate(frame, rotation_angle, reshape=False, order=1, mode='nearest')

        # --- CROPPING ---
        if getattr(config, "CROP_REGION", None):
            y_start, y_end, x_start, x_end = config.CROP_REGION
            frame = frame[y_start:y_end, x_start:x_end]

        # --- LOWER THRESHOLD ---
        if getattr(config, "APPLY_THRESHOLD", True):
            threshold_value = getattr(config, "THRESHOLD_VALUE", 10000)
            frame = (frame > threshold_value).astype(np.uint16) * frame

        # --- UPPER THRESHOLD ---
        if getattr(config, "UPPER_THRESHOLD", False):
            upper_value = getattr(config, "UPPER_THRESHOLD_VALUE", 47000)
            frame = (frame < upper_value).astype(np.uint16) * frame

        # --- GAUSSIAN BLUR ---
        if getattr(config, "GAUSSIAN_BLUR", False):
            sigma = getattr(config, "GAUSSIAN_SIGMA", 5)
            frame = ndi.gaussian_filter(frame, sigma=sigma)

        # --- TEMPORAL MEDIAN FILTER ---
        if getattr(config, "TEMPORAL_MEDIAN", True):
            self._median_buffer.append(frame)
            median_window = getattr(config, "MEDIAN_WINDOW", 5)
            if len(self._median_buffer) > median_window:
                self._median_buffer.pop(0)
            frame = np.median(self._median_buffer, axis=0).astype(np.uint16)

        return frame
    '''
    # -------------------------- MAIN STREAMING FRAME PROCESSING --------------------------
    def process_frame(self, file_path, frame_time=None):
        """Process a single 16-bit frame with preprocessing and burn analysis."""

        raw_data, frame = utils.read_gray_file(file_path)
        if raw_data is None:
            return None

        # --- Preprocess (rotation, crop, thresholds, blur, median) ---
        frame_processed = self._preprocess_frame(frame)

        # --- Convert to Celsius ---
        celsius_data = utils.raw_to_celsius(frame_processed)

        # --- Time handling ---
        if frame_time is None:
            elapsed_time = self.frame_count / config.DEFAULT_CAPTURE_FPS
        else:
            if self.first_frame_time is None:
                self.first_frame_time = frame_time
            elapsed_time = frame_time - self.first_frame_time

        # --- Baseline ---
        if self.baseline_temp is None:
            self._establish_baseline(celsius_data)

        # --- Burn detection ---
        if config.EDGE_DETECTION_METHOD == "temperature":
            current_burn_mask = self._detect_burn_temperature_based(celsius_data)
        else:
            current_burn_mask = self._detect_burn_otsu(celsius_data)

        current_burn_mask = self._filter_small_regions(current_burn_mask)
        self.cumulative_burn_mask[current_burn_mask > 0] = 255

        # --- Measurements ---
        current_burn_pixels = np.sum(current_burn_mask > 0)
        cumulative_burn_pixels = np.sum(self.cumulative_burn_mask > 0)

        current_burn_area_cm2 = utils.pixels_to_cm2(current_burn_pixels)
        cumulative_burn_area_cm2 = utils.pixels_to_cm2(cumulative_burn_pixels)

        total_pixels = frame_processed.size
        burn_percentage = (cumulative_burn_pixels / total_pixels) * 100

        max_temp = np.max(celsius_data)
        mean_temp = np.mean(celsius_data)

        # --- Ignition ---
        if self.ignition_frame is None and cumulative_burn_pixels > 50:
            self.ignition_frame = self.frame_count
            self.ignition_time = elapsed_time

        # --- Rate of Spread ---
        ros_cm2_per_sec = 0
        if self.frame_data:
            prev = self.frame_data[-1]
            dt = elapsed_time - prev['elapsed_sec']
            da = cumulative_burn_area_cm2 - prev['cumulative_burn_area_cm2']
            if dt > 0:
                ros_cm2_per_sec = da / dt

        # --- Store frame results ---
        frame_result = {
            'frame_number': self.frame_count,
            'timestamp': frame_time,
            'elapsed_sec': elapsed_time,
            'current_burn_area_cm2': current_burn_area_cm2,
            'cumulative_burn_area_cm2': cumulative_burn_area_cm2,
            'burn_percentage': burn_percentage,
            'max_temp_celsius': max_temp,
            'mean_temp_celsius': mean_temp,
            'ros_instantaneous_cm2_per_sec': ros_cm2_per_sec,
        }

        self.frame_data.append(frame_result)
        self.frame_count += 1

        # --- Auto-stop logic ---
        current_ros = frame_result['ros_instantaneous_cm2_per_sec']
        if current_ros < self.ROS_STOP_THRESHOLD:
            self.ros_zero_streak += 1
        else:
            self.ros_zero_streak = 0

        if (current_ros < self.ROS_STOP_THRESHOLD and
            importlib.import_module("main").FIRE_IS_ACTIVE):
            print(f"[Analyzer] Fire stopped! ROS < {self.ROS_STOP_THRESHOLD} for {self.ros_zero_streak} frames")
            self.has_auto_stopped = True
            threading.Thread(target=self.auto_stop_callback, daemon=True).start()

        # --- FPS estimation ---
        if frame_time is not None and self.frame_count == 50:
            self.actual_fps = 50 / elapsed_time

        return frame_result

    '''
    def process_frame(self, file_path, frame_time=None):
        """Process a single 16-bit frame with preprocessing and burn analysis."""
        raw_data, raw_frame = utils.read_gray_file(file_path)
        if raw_data is None:
            return None

        # === 1. Convert to Celsius FIRST (this is the key change) ===
        celsius_frame = utils.raw_to_celsius(raw_frame)  # ← now we have real temperatures

        # === 2. Time handling ===
        if frame_time is None:
            elapsed_time = self.frame_count / config.DEFAULT_CAPTURE_FPS
        else:
            if self.first_frame_time is None:
                self.first_frame_time = frame_time
            elapsed_time = frame_time - self.first_frame_time

        # === 3. Baseline (on first frame, before any preprocessing) ===
        if self.baseline_temp is None:
            self._establish_baseline(celsius_frame)

        # === 4. Apply preprocessing IN CELSIUS SPACE ===
        celsius_processed = self._preprocess_celsius_frame(celsius_frame)

        # === 5. Burn detection on the clean, processed Celsius frame ===
        if config.EDGE_DETECTION_METHOD == "temperature":
            current_burn_mask = self._detect_burn_temperature_based(celsius_processed)
        else:
            current_burn_mask = self._detect_burn_otsu(celsius_processed)

        current_burn_mask = self._filter_small_regions(current_burn_mask)

        # Update cumulative mask (create on first run with correct shape after crop/rotate!)
        if self.cumulative_burn_mask is None or self.cumulative_burn_mask.shape != current_burn_mask.shape:
            self.cumulative_burn_mask = np.zeros_like(current_burn_mask)
        self.cumulative_burn_mask[current_burn_mask > 0] = 255

        # === 6. Measurements ===
        current_burn_pixels = np.sum(current_burn_mask > 0)
        cumulative_burn_pixels = np.sum(self.cumulative_burn_mask > 0)
        current_burn_area_cm2 = utils.pixels_to_cm2(current_burn_pixels)
        cumulative_burn_area_cm2 = utils.pixels_to_cm2(cumulative_burn_pixels)

        # Use processed frame size (correct after crop!)
        total_pixels = celsius_processed.size
        burn_percentage = (cumulative_burn_pixels / total_pixels) * 100 if total_pixels > 0 else 0

        frame_processed_2 = self._preprocess_frame(raw_frame)
        celsius_data = utils.raw_to_celsius(frame_processed_2)
        max_temp = np.max(celsius_data)
        mean_temp = np.mean(celsius_processed)

        # === 7. Ignition detection ===
        if self.ignition_frame is None and cumulative_burn_pixels > 50:
            self.ignition_frame = self.frame_count
            self.ignition_time = elapsed_time

        # === 8. Rate of Spread ===
        ros_cm2_per_sec = 0
        if self.frame_data:
            prev = self.frame_data[-1]
            dt = elapsed_time - prev['elapsed_sec']
            da = cumulative_burn_area_cm2 - prev['cumulative_burn_area_cm2']
            if dt > 0:
                ros_cm2_per_sec = da / dt

        # === 9. Store result ===
        frame_result = {
            'frame_number': self.frame_count,
            'timestamp': frame_time,
            'elapsed_sec': elapsed_time,
            'current_burn_area_cm2': current_burn_area_cm2,
            'cumulative_burn_area_cm2': cumulative_burn_area_cm2,
            'burn_percentage': burn_percentage,
            'max_temp_celsius': max_temp,
            'mean_temp_celsius': mean_temp,
            'ros_instantaneous_cm2_per_sec': ros_cm2_per_sec,
        }
        self.frame_data.append(frame_result)
        self.frame_count += 1

        # === 10. Auto-stop logic (fixed streak count) ===
        if ros_cm2_per_sec < self.ROS_STOP_THRESHOLD:
            self.ros_zero_streak += 1
        else:
            self.ros_zero_streak = 0

        if (self.ros_zero_streak >= config.MIN_ZERO_FRAMES and
            not self.has_auto_stopped and
            importlib.import_module("main").FIRE_IS_ACTIVE):
            print(f"[Analyzer] Fire stopped! ROS < {self.ROS_STOP_THRESHOLD} for {self.ros_zero_streak} consecutive frames")
            self.has_auto_stopped = True
            if self.auto_stop_callback:
                threading.Thread(target=self.auto_stop_callback, daemon=True).start()

        # === 11. FPS estimation ===
        if frame_time is not None and self.frame_count == 50:
            self.actual_fps = 50 / elapsed_time

        return frame_result

    # -------------------------- SUMMARY & LIVE --------------------------
    def get_summary_statistics(self):
        if not self.frame_data:
            return {
                'duration_sec': 0,
                'final_burn_percentage': 0,
                'avg_ros_cm2_per_sec': 0,
                'max_ros_cm2_per_sec': 0,
                'max_temp_celsius': 0,
            }

        last_frame = self.frame_data[-1]
        avg_ros = last_frame['cumulative_burn_area_cm2'] / last_frame['elapsed_sec'] if last_frame['elapsed_sec'] > 0 else 0
        ros_values = [f['ros_instantaneous_cm2_per_sec'] for f in self.frame_data[1:] if f['ros_instantaneous_cm2_per_sec'] > 0]
        max_ros = max(ros_values) if ros_values else 0
        max_temp = max(f['max_temp_celsius'] for f in self.frame_data)

        return {
            'duration_sec': last_frame['elapsed_sec'],
            'final_burn_percentage': last_frame['burn_percentage'],
            'avg_ros_cm2_per_sec': avg_ros,
            'max_ros_cm2_per_sec': max_ros,
            'max_temp_celsius': max_temp,
        }

    def get_live_update(self, frame_number=None):
        if not self.frame_data:
            return {'status': 'waiting', 'frame': 0}

        if frame_number is None or frame_number >= len(self.frame_data):
            frame_number = len(self.frame_data) - 1

        frame = self.frame_data[frame_number]
        return {
            'status': 'capturing',
            'frame': frame['frame_number'],
            'elapsed_sec': frame['elapsed_sec'],
            'burn_percentage': round(frame['burn_percentage'], 2),
            'burn_area_cm2': round(frame['cumulative_burn_area_cm2'], 2),
            'max_temp_celsius': round(frame['max_temp_celsius'], 1),
            'current_ros_cm2_per_sec': round(frame['ros_instantaneous_cm2_per_sec'], 2),
        }

    def print_summary(self):
        summary = self.get_summary_statistics()
        print(f"\n{'='*60}")
        print(f"Burn Analysis Summary")
        print(f"{'='*60}")
        print(f"Duration: {utils.format_duration(summary['duration_sec'])}")
        print(f"Average ROS: {summary['avg_ros_cm2_per_sec']:.2f} cm²/sec")
        print(f"Peak ROS: {summary['max_ros_cm2_per_sec']:.2f} cm²/sec")
        print(f"Max temperature: {summary['max_temp_celsius']:.1f}°C")
        print(f"{'='*60}\n")

