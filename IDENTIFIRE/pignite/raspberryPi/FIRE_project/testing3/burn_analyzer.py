import numpy as np
import cv2
import config
import utils
import threading
import importlib

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


        
    def reset(self):
        self.__init__(self.temp_threshold_delta, self.baseline_percentile)
    
    def _establish_baseline(self, celsius_frame):
        self.baseline_temp = np.percentile(celsius_frame, self.baseline_percentile)
        self.cumulative_burn_mask = np.zeros(celsius_frame.shape, dtype=np.uint8)
        print(f"[Analyzer] Baseline: {self.baseline_temp:.1f}°C")
    
    def _detect_burn_temperature_based(self, celsius_frame):
        relative_threshold = self.baseline_temp + self.temp_threshold_delta
        effective_threshold = max(relative_threshold, config.MIN_BURN_TEMP_ABSOLUTE)
        return (celsius_frame > effective_threshold).astype(np.uint8) * 255
    
    def _detect_burn_otsu(self, celsius_frame):
        frame_uint8 = utils.normalize_to_uint8(celsius_frame)
        _, thresh = cv2.threshold(frame_uint8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh
    
    def _filter_small_regions(self, burn_mask):
        num_labels, labels = cv2.connectedComponents(burn_mask)
        refined_mask = np.zeros_like(burn_mask)
        for label in range(1, num_labels):
            component_mask = (labels == label)
            if np.sum(component_mask) >= config.MIN_CONTOUR_AREA_PIXELS:
                refined_mask[component_mask] = 255
        return refined_mask
    
    def process_frame(self, file_path, frame_time=None):
        raw_data, celsius_data = utils.read_gray_file(file_path)
        
        if frame_time is None:
            elapsed_time = self.frame_count / config.DEFAULT_CAPTURE_FPS
        else:
            if self.first_frame_time is None:
                self.first_frame_time = frame_time
            elapsed_time = frame_time - self.first_frame_time
        
        if self.baseline_temp is None:
            self._establish_baseline(celsius_data)
        
        if config.EDGE_DETECTION_METHOD == "temperature":
            current_burn_mask = self._detect_burn_temperature_based(celsius_data)
        else:
            current_burn_mask = self._detect_burn_otsu(celsius_data)
        
        current_burn_mask = self._filter_small_regions(current_burn_mask)
        self.cumulative_burn_mask[current_burn_mask > 0] = 255
        
        current_burn_pixels = np.sum(current_burn_mask > 0)
        cumulative_burn_pixels = np.sum(self.cumulative_burn_mask > 0)
        
        current_burn_area_cm2 = utils.pixels_to_cm2(current_burn_pixels)
        cumulative_burn_area_cm2 = utils.pixels_to_cm2(cumulative_burn_pixels)
        
        total_pixels = config.IMAGE_WIDTH * config.IMAGE_HEIGHT
        burn_percentage = (cumulative_burn_pixels / total_pixels) * 100
        
        max_temp = np.max(celsius_data)
        mean_temp = np.mean(celsius_data)
        
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
            self.ros_zero_streak = 0  # reset if any activity

        # Fire has been dead for 50+ frames AND ignition actually happened
        if (current_ros < self.ROS_STOP_THRESHOLD and importlib.import_module("main").FIRE_IS_ACTIVE):

            print(f"[Analyzer] Fire stopped! ROS < {self.ROS_STOP_THRESHOLD} for {self.ros_zero_streak} frames")
            self.has_auto_stopped = True

            # Trigger auto-stop (this runs in worker thread → use thread-safe call)
            threading.Thread(target=self.auto_stop_callback, daemon=True).start()


        
        if frame_time is not None and self.frame_count == 50:
            self.actual_fps = 50 / elapsed_time
            if abs(self.actual_fps - config.DEFAULT_CAPTURE_FPS) > 1:
                print(f"[Analyzer] WARNING: FPS {self.actual_fps:.1f} != {config.DEFAULT_CAPTURE_FPS}")
        
        return frame_result
    
    def get_summary_statistics(self):
        if not self.frame_data:
            return {
                'total_frames': 0,
                'duration_sec': 0,
                'final_burn_area_cm2': 0,
                'final_burn_percentage': 0,
                'avg_ros_cm2_per_sec': 0,
                'max_ros_cm2_per_sec': 0,
                'mean_instantaneous_ros_cm2_per_sec': 0,
                'max_temp_celsius': 0,
                'ignition_frame': None,
                'ignition_time_sec': None,
                'baseline_temp_celsius': None,
                'burn_threshold_celsius': 0,
                'actual_fps': None,
            }
        
        last_frame = self.frame_data[-1]
        avg_ros = last_frame['cumulative_burn_area_cm2'] / last_frame['elapsed_sec'] if last_frame['elapsed_sec'] > 0 else 0
        
        ros_values = [f['ros_instantaneous_cm2_per_sec'] for f in self.frame_data[1:] if f['ros_instantaneous_cm2_per_sec'] > 0]
        max_ros = max(ros_values) if ros_values else 0
        mean_instantaneous_ros = np.mean(ros_values) if ros_values else 0
        max_temp = max(f['max_temp_celsius'] for f in self.frame_data)
        
        return {
            'total_frames': self.frame_count,
            'duration_sec': last_frame['elapsed_sec'],
            'final_burn_area_cm2': last_frame['cumulative_burn_area_cm2'],
            'final_burn_percentage': last_frame['burn_percentage'],
            'avg_ros_cm2_per_sec': avg_ros,
            'max_ros_cm2_per_sec': max_ros,
            'mean_instantaneous_ros_cm2_per_sec': mean_instantaneous_ros,
            'max_temp_celsius': max_temp,
            'ignition_frame': self.ignition_frame,
            'ignition_time_sec': self.ignition_time,
            'baseline_temp_celsius': self.baseline_temp,
            'burn_threshold_celsius': max(self.baseline_temp + self.temp_threshold_delta, config.MIN_BURN_TEMP_ABSOLUTE) if self.baseline_temp else 0,
            'actual_fps': self.actual_fps,
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
        
        if summary['total_frames'] == 0:
            print("No frames processed")
            print(f"{'='*60}\n")
            return
        
        print(f"Duration: {utils.format_duration(summary['duration_sec'])}")
        print(f"Total frames: {summary['total_frames']}")
        print(f"Final burn area: {summary['final_burn_area_cm2']:.2f} cm² ({summary['final_burn_percentage']:.1f}%)")
        print(f"Average ROS: {summary['avg_ros_cm2_per_sec']:.2f} cm²/sec")
        print(f"Peak ROS: {summary['max_ros_cm2_per_sec']:.2f} cm²/sec")
        print(f"Max temperature: {summary['max_temp_celsius']:.1f}°C")
        if summary['ignition_frame'] is not None:
            print(f"Ignition: frame {summary['ignition_frame']} ({summary['ignition_time_sec']:.1f}s)")
        print(f"{'='*60}\n")

