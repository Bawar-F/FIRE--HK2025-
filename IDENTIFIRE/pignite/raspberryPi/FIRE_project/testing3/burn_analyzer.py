import numpy as np
#import cv2
import config
import utils
import threading
import importlib

from scipy.ndimage import gaussian_filter, rotate, sobel


class BurnAnalyzer:
    """Analyzes thermal sequences to calculate burn propagation and Rate of Spread."""
    
    def __init__(self, temp_threshold_delta=None, baseline_percentile=None):
        self.temp_threshold_delta = temp_threshold_delta or config.BURN_TEMP_DELTA
        self.baseline_percentile = baseline_percentile or 50
        
        self.baseline_temp = None
        self.cumulative_burn_mask = None
        self.frame_count = 0
        self.first_frame_time = None
        self.frame_data = []
        
        self.ignition_frame = None
        self.ignition_time = None
        self.actual_fps = None

        self.ros_zero_streak = 0
        self.ROS_STOP_THRESHOLD = config.ROS_STOP_THRESHOLD
        self.MIN_ZERO_FRAMES = config.MIN_ZERO_FRAMES
        self.has_auto_stopped = False
        self.auto_stop_callback = None

        self.use_temporal_median = config.TEMPORAL_MEDIAN
        self.median_window = config.MEDIAN_WINDOW
        self.frame_buffer = [] 

        self.rotation_angle = config.ROTATION_ANGLE
        self.crop_sample = True
        self.crop_region = config.CROP_REGION

        self.height = config.IMAGE_HEIGHT
        self.width = config.IMAGE_WIDTH

        self.apply_threshold = config.APPLY_THRESHOLD
        self.threshold_value = config.THRESHOLD_VALUE
        self.upper_threshold = config.UPPER_THRESHOLD
        self.upper_threshold_value = config.UPPER_THRESHOLD_VALUE

        self.gaussian_blur = config.GAUSSIAN_BLUR
        self.gaussian_sigma = config.GAUSSIAN_SIGMA


    def reset(self):
        self.__init__(self.temp_threshold_delta, self.baseline_percentile)
    
    def _establish_baseline(self, celsius_frame):
        self.baseline_temp = np.percentile(celsius_frame, self.baseline_percentile)
        self.cumulative_burn_mask = np.zeros(celsius_frame.shape, dtype=np.uint8)
        print(f"[Analyzer] Baseline: {self.baseline_temp:.1f}°C")
    
    #def _detect_burn_temperature_based(self, celsius_frame):
    #    relative_threshold = self.baseline_temp + self.temp_threshold_delta
    #    effective_threshold = max(relative_threshold, config.MIN_BURN_TEMP_ABSOLUTE)
    #    return (celsius_frame > effective_threshold).astype(np.uint8) * 255
    
    #def _detect_burn_otsu(self, celsius_frame):
    #    frame_uint8 = utils.normalize_to_uint8(celsius_frame)
    #    _, thresh = cv2.threshold(frame_uint8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU) #FIX
    #    return thresh
    
    #def _filter_small_regions(self, burn_mask):
    #    num_labels, labels = cv2.connectedComponents(burn_mask) #FIX
    #    refined_mask = np.zeros_like(burn_mask)
    #    for label in range(1, num_labels):
    #        component_mask = (labels == label)
    #        if np.sum(component_mask) >= config.MIN_CONTOUR_AREA_PIXELS:
    #            refined_mask[component_mask] = 255
    #    return refined_mask
    

    def load_and_process_frame(self, file_path, frame_time=None):
        with open(file_path, "rb") as f:
            data = f.read()

        arr = np.frombuffer(data, dtype='>u2').reshape((self.height, self.width))

        # Rotate
        if self.rotation_angle != 0:
            arr = rotate(arr, self.rotation_angle, reshape=False, order=1, mode='nearest')
        
        # Crop to 12×12 cm sample
        if self.crop_sample:
            y_start, y_end = self.crop_region[0], self.crop_region[1]
            x_start, x_end = self.crop_region[2], self.crop_region[3]
            arr = arr[y_start:y_end, x_start:x_end]
        
        return arr.astype(np.uint16)

    
    def process_frame(self, file_path, frame_time=None):
        #raw_data, celsius_data = utils.read_gray_file(file_path) 

        raw_data = self.load_and_process_frame(file_path)
        
        if raw_data is None:
            return None
        
        celsius_data = utils.raw_to_celsius(raw_data)

        processed = raw_data.copy()

        if self.gaussian_blur:
            processed = gaussian_filter(processed, sigma=self.gaussian_sigma)

        if self.apply_threshold:
            processed = (processed > self.threshold_value).astype(np.uint16) * processed

        if self.upper_threshold:
            processed = (processed < self.upper_threshold_value).astype(np.uint16) * processed

        if self.use_temporal_median:
            self.frame_buffer.append(processed)
            if len(self.frame_buffer) > self.median_window:
                self.frame_buffer.pop(0)
            processed = np.median(self.frame_buffer, axis=0).astype(np.uint16)

        current_burn_mask = (processed > 0).astype(np.uint8) * 255
        



        if frame_time is None:
            elapsed_time = self.frame_count / config.DEFAULT_CAPTURE_FPS
        else:
            if self.first_frame_time is None:
                self.first_frame_time = frame_time
            elapsed_time = frame_time - self.first_frame_time
        
        if self.baseline_temp is None:
            self._establish_baseline(celsius_data)
        
        #if config.EDGE_DETECTION_METHOD == "temperature":
        #    current_burn_mask = self._detect_burn_temperature_based(celsius_data)
        #else:
        #    current_burn_mask = self._detect_burn_otsu(celsius_data)
        
        #_small_regions(current_burn_mask)

        self.cumulative_burn_mask[current_burn_mask > 0] = 255
        
        current_burn_pixels = np.sum(current_burn_mask > 0)
        cumulative_burn_pixels = np.sum(self.cumulative_burn_mask > 0)
        
        current_burn_area_cm2 = utils.pixels_to_cm2(current_burn_pixels)
        cumulative_burn_area_cm2 = utils.pixels_to_cm2(cumulative_burn_pixels)
        
        mask_height, mask_width = current_burn_mask.shape
        total_pixels = mask_height * mask_width
        burn_percentage = (cumulative_burn_pixels / total_pixels) * 100
        
        max_temp = np.max(celsius_data[current_burn_mask > 0])
        mean_temp = np.mean(celsius_data[current_burn_mask > 0])
        
        if self.ignition_frame is None and cumulative_burn_pixels > 50:
            self.ignition_frame = self.frame_count
            self.ignition_time = elapsed_time
        
        ros_cm2_per_sec = 0
        if len(self.frame_data) > 0:
            prev_frame = self.frame_data[-1]
            time_diff = elapsed_time - prev_frame['elapsed_sec']
            area_diff = cumulative_burn_area_cm2 - prev_frame['cumulative_burn_area_cm2']
            if time_diff > 0:
                ros_cm2_per_sec = area_diff / time_diff
        
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

        # === AUTO-STOP: Fire has stopped spreading ===
        current_ros = frame_result['ros_instantaneous_cm2_per_sec']

        if current_ros < self.ROS_STOP_THRESHOLD:
            self.ros_zero_streak += 1
        else:
            self.ros_zero_streak = 0

        if (self.ros_zero_streak >= self.MIN_ZERO_FRAMES 
            and self.ignition_frame is not None 
            and not self.has_auto_stopped
            and self.auto_stop_callback is not None):

            print(f"[Analyzer] Fire stopped! ROS < {self.ROS_STOP_THRESHOLD} for {self.ros_zero_streak} frames")
            self.has_auto_stopped = True
            threading.Thread(target=self.auto_stop_callback, daemon=True).start()


        
        if frame_time is not None and self.frame_count == 50:
            self.actual_fps = 50 / elapsed_time
            if abs(self.actual_fps - config.DEFAULT_CAPTURE_FPS) > 1:
                print(f"[Analyzer] WARNING: FPS {self.actual_fps:.1f} != {config.DEFAULT_CAPTURE_FPS}")
        
        return frame_result
    

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
        mean_instantaneous_ros = np.mean(ros_values) if ros_values else 0
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

