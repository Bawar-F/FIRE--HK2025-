import numpy as np
import os
import cv2


width, height = 160, 120
passed_area = np.zeros((120, 160), dtype=np.uint8)

def read_data(file_path, width=160, height=120):
    """
    Read 16-bit big-endian .gray file and return a numpy array
    """
    with open(file_path, "rb") as f:
        data = f.read()
    
    data_frame = np.frombuffer(data, dtype=">u2").copy()
    
    assert width * height == data_frame.size, f"File {file_path} is not {width}x{height}"
    
    image = data_frame.reshape((height, width))
    return image

def edge_detection(image_data, thr1=100, thr2=200):
    """
    Normalize 16-bit image to 0-255 and apply Canny edge detection
    """
    image_norm = (image_data - image_data.min()) / (image_data.max() - image_data.min())
    image_uint8 = (image_norm * 255).astype(np.uint8)
    edges = Canny(image_uint8, thr1, thr2)
    return edges

def find_outer_edge(image_data, min_area=20):
    """
    Apply Otsu threshold, find contours, filter small areas,
    and return an image with only outer edges drawn
    """
    # Convert 16-bit image to 8-bit for thresholding
    img_uint8 = ((image_data - image_data.min()) / (image_data.max() - image_data.min()) * 255).astype(np.uint8)
    
    # Apply Otsu threshold
    _, thresh = cv2.threshold(img_uint8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Find contours
    contours_info = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]
    
    # Draw only contours above min_area
    result = np.zeros_like(img_uint8)
    for cntr in contours:
        area = cv2.contourArea(cntr)
        if area > min_area:
            cv2.drawContours(result, [cntr], 0, 255, 1)
    
    return result


    
# Folder containing .gray files
gray_folder = "/tmp/capture"

# List all .gray files in folder
gray_files = sorted([f for f in os.listdir(gray_folder) if f.endswith(".gray")])



prev_burn = 0
rates = []

def update(frame_idx):
    global passed_area
    global prev_burn
    global rates
    filename = gray_files[frame_idx]
    file_path = os.path.join(gray_folder, filename)
    image = read_data(file_path, width, height)
    outer_edges = find_outer_edge(image, min_area=20)
    # Update passed_area
    passed_area[passed_area == 0] = outer_edges[passed_area == 0]
    curr_burn = len(passed_area[passed_area != 0]) / (width*height)*1000
    try:
        if round(prev_burn, 2) != round(curr_burn, 2):
            ros = round(prev_burn/curr_burn,2)
            rates.append(ros)
        else:
            ros = 0
        print(round(curr_burn,2), "ros:", np.mean(rates))
    except ZeroDivisionError:
        print(curr_burn, "ros:", "NAN")
    prev_burn = curr_burn

for ind in range(len(gray_files)-1):
    update(ind)
