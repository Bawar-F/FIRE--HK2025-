import numpy as np
import os
import cv2

width, height = 160, 120
passed_area = np.zeros((height, width), dtype=np.uint8)
prev_burn = 0
rates = []

def read_data(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    data_frame = np.frombuffer(data, dtype=">u2").copy()
    assert width * height == data_frame.size
    return data_frame.reshape((height, width))

def find_outer_edge(image, min_area=20):
    img_uint8 = ((image - image.min()) / (image.max() - image.min()) * 255).astype(np.uint8)
    _, thresh = cv2.threshold(img_uint8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours_info = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]
    result = np.zeros_like(img_uint8)
    for cntr in contours:
        if cv2.contourArea(cntr) > min_area:
            cv2.drawContours(result, [cntr], 0, 255, 1)
    return result

def update(file_path):
    global passed_area, prev_burn, rates
    image = read_data(file_path)  # <-- read image here
    outer_edges = find_outer_edge(image, min_area=20)
    passed_area[passed_area == 0] = outer_edges[passed_area == 0]
    curr_burn = len(passed_area[passed_area != 0]) / (width*height)*1000
    try:
        ros = round(prev_burn/curr_burn, 2) if round(prev_burn,2) != round(curr_burn,2) else 0
        if ros != 0:
            rates.append(ros)
        print(round(curr_burn,2), "ros:", np.mean(rates) if rates else 0)
    except ZeroDivisionError:
        print(curr_burn, "ros: NAN")
    prev_burn = curr_burn



