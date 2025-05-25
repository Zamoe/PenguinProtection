#machinelearning algorthms
#reads both models and runs them one after the other as well as handles capturing of images

import site
site.addsitedir('/usr/lib/python3/dist-packages')

import numpy as np
import cv2
from PIL import Image
import tflite_runtime.interpreter as tflite
from picamera2 import Picamera2
import time
import threading
from camera_manager import get_camera
from datetime import datetime, timezone

CONF_THRESHOLD = 0.2
IOU_THRESHOLD = 0.5
det_img_size = 640

det_model_path = "yolodetect_int8.tflite"
cls_model_path = "ani-int8.tflite"
det_class_names_path = "detector_class_names.txt"
cls_class_names_path = "classifier_class_names.txt"

# Globals for camera and threading lock
picam2 = None
camera_lock = threading.Lock()


with open(det_class_names_path, 'r') as f:
    det_class_names = [line.strip() for line in f.readlines()]
with open(cls_class_names_path, 'r') as f:
    cls_class_names = [line.strip() for line in f.readlines()]

#TFLite models ,allocate tensors
det_interpreter = tflite.Interpreter(model_path=det_model_path)
det_interpreter.allocate_tensors()
det_input_details = det_interpreter.get_input_details()
det_output_details = det_interpreter.get_output_details()

cls_interpreter = tflite.Interpreter(model_path=cls_model_path)
cls_interpreter.allocate_tensors()
cls_input_details = cls_interpreter.get_input_details()
cls_output_details = cls_interpreter.get_output_details()
cls_input_shape = cls_input_details[0]['shape']
cls_input_height, cls_input_width = cls_input_shape[1], cls_input_shape[2]

def init_camera():
    global picam2
    with camera_lock:
        if picam2 is None:
            picam2 = get_camera()
            if picam2:
                print("✅ Camera initialized.")
            else:
                print("⚠️ Failed to initialize camera.")

def letterbox_image(image, target_size):
    ih, iw = image.shape[:2]
    h, w = target_size
    scale = min(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    image_resized = cv2.resize(image, (nw, nh))
    new_image = np.full((h, w, 3), 128, dtype=np.uint8)
    top = (h - nh) // 2
    left = (w - nw) // 2
    new_image[top:top+nh, left:left+nw] = image_resized
    return new_image, scale, left, top, (iw, ih)

def preprocess_det_image(image):
    input_data = np.array(image, dtype=np.uint8)
    if det_input_details[0]['dtype'] == np.int8:
        input_scale, input_zero_point = det_input_details[0]['quantization']
        input_data = (input_data / 255.0 / input_scale + input_zero_point).astype(np.int8)
    return np.expand_dims(input_data, axis=0)

def run_det_inference(input_data):
    det_interpreter.set_tensor(det_input_details[0]['index'], input_data)
    det_interpreter.invoke()
    output_index = det_output_details[0]['index']
    output_data = det_interpreter.get_tensor(output_index)[0]
    if det_output_details[0]['dtype'] == np.int8:
        output_scale, output_zero_point = det_output_details[0]['quantization']
        output_data = (output_data.astype(np.float32) - output_zero_point) * output_scale
    return output_data

#make detections into readable format
def parse_detections(output_data, scale, pad_left, pad_top, original_size):
    ow, oh = original_size
    boxes, confidences, class_ids = [], [], []
    for det in output_data:
        conf = det[4]
        class_probs = det[5:]
        class_id = np.argmax(class_probs)
        class_score = class_probs[class_id]
        total_conf = conf * class_score
        if total_conf > CONF_THRESHOLD:
            x_center, y_center, w, h = det[0:4]
            x1 = int((x_center - w / 2) * det_img_size)
            y1 = int((y_center - h / 2) * det_img_size)
            x2 = int((x_center + w / 2) * det_img_size)
            y2 = int((y_center + h / 2) * det_img_size)
            x1 = int((x1 - pad_left) / scale)
            y1 = int((y1 - pad_top) / scale)
            x2 = int((x2 - pad_left) / scale)
            y2 = int((y2 - pad_top) / scale)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(ow - 1, x2), min(oh - 1, y2)
            boxes.append([x1, y1, x2 - x1, y2 - y1])
            confidences.append(float(total_conf))
            class_ids.append(class_id)
    indices = cv2.dnn.NMSBoxes(boxes, confidences, CONF_THRESHOLD, IOU_THRESHOLD)
    return boxes, confidences, class_ids, indices
#inoput image to correct format
def preprocess_cls_image(cropped_img):
    img_rgb = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(img_rgb, (cls_input_width, cls_input_height))
    input_tensor = np.expand_dims(resized, axis=0)
    if cls_input_details[0]['dtype'] == np.uint8:
        return input_tensor.astype(np.uint8)
    else:
        return input_tensor.astype(np.float32) / 255.0
#account for quantisation of model
def run_cls_inference(input_tensor):
    cls_interpreter.set_tensor(cls_input_details[0]['index'], input_tensor)
    cls_interpreter.invoke()
    output_index = cls_output_details[0]['index']
    output_data = cls_interpreter.get_tensor(output_index)
    output_dtype = cls_output_details[0]['dtype']
    if np.issubdtype(output_dtype, np.integer):
        scale, zero_point = cls_output_details[0]['quantization']
        output_data = scale * (output_data.astype(np.float32) - zero_point)
    output_data = output_data.flatten()
    exp_outputs = np.exp(output_data - np.max(output_data))
    probabilities = exp_outputs / exp_outputs.sum()
    pred_class = int(np.argmax(probabilities))
    confidence = float(probabilities[pred_class])
    pred_label = cls_class_names[pred_class] if pred_class < len(cls_class_names) else "Unknown"
    return pred_label, confidence

#render the boxes around object to use for cropping
def draw_detections_with_cls(image_cv, boxes, confidences, class_ids, indices):
    detection_results = []
    if indices is not None and len(indices) > 0:
        for i in indices.flatten():
            x, y, w, h = boxes[i]
            det_class_id = class_ids[i]
            det_score = confidences[i]
            det_label = det_class_names[det_class_id] if det_class_id < len(det_class_names) else f"Class {det_class_id}"

            cropped = image_cv[y:y+h, x:x+w]
            cls_label, cls_conf = "N/A", 0.0
            if cropped.size > 0 and w > 0 and h > 0:
                input_tensor = preprocess_cls_image(cropped)
                cls_label, cls_conf = run_cls_inference(input_tensor)

            detection_results.append({
                "det_label": det_label,
                "det_confidence": det_score,
                "cls_label": cls_label,
                "cls_confidence": cls_conf,
                "box": (x, y, w, h)
            })

            cv2.rectangle(image_cv, (x, y), (x + w, y + h), (255, 0, 0), 2)
            cv2.putText(image_cv, f"{det_label}: {det_score:.2f}", (x, y - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            cv2.putText(image_cv, f"{cls_label}: {cls_conf:.2f}", (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    return image_cv, detection_results
#manage camera to capture one frame
def capture_frame():
    global picam2

    with camera_lock:
        if picam2 is None:
            print("⚠️ Camera is unavailable.")
            return None, None  # Return None for both frame and timestamp

        try:
            start_time = time.time()
            frame = picam2.capture_array()
            t1 = time.time()
            print(f"📸 Frame captured in {t1 - start_time:.3f} seconds.")

            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                t2 = time.time()
                print(f"🎨 Converted BGRA to BGR in {t2 - t1:.3f} seconds.")
            else:
                t2 = t1

            # Get the current UTC time formatted for Firebase
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"🕒 Capture timestamp (UTC): {timestamp}")

            return frame, timestamp

        except Exception as e:
            print(f"❌ Capture error: {e}")
            return None, None

#main func to run fram detection.
def detect_frame(frame):
    try:
        start_time = time.time()

        frame_resized, scale, pad_left, pad_top, original_size = letterbox_image(frame, (det_img_size, det_img_size))
        t1 = time.time()
        print(f"🔄 Letterbox image in {t1 - start_time:.3f} seconds.")

        input_data = preprocess_det_image(frame_resized)
        t2 = time.time()
        print(f"🧼 Preprocessed image in {t2 - t1:.3f} seconds.")

        output_data = run_det_inference(input_data)
        t3 = time.time()
        print(f"🤖 Inference run in {t3 - t2:.3f} seconds.")

        boxes, confidences, class_ids, indices = parse_detections(output_data, scale, pad_left, pad_top, original_size)
        t4 = time.time()
        print(f"📦 Parsed detections in {t4 - t3:.3f} seconds.")

        output_frame, detection_results = draw_detections_with_cls(frame.copy(), boxes, confidences, class_ids, indices)
        t5 = time.time()
        print(f"🎯 Drew detections and classification in {t5 - t4:.3f} seconds.")

        total_elapsed = t5 - start_time
        print(f"🕒 Total detection and classification took {total_elapsed:.3f} seconds.")

        # Return total_elapsed as a third return value
        return output_frame, detection_results, total_elapsed

    except Exception as e:
        print(f"❌ Detection error: {e}")
        return None, [], 0.0



