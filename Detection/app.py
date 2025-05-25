#app.py to run detection and inference
#--------notes-------
#flask only used for easy debugging and viewing without ssh
#*comments for debugging added with AI*

# === Configurable Detection Settings ===
TARGET_ANIMALS = ['honey-badger', 'leopard'] 
DEFAULT_CAPTURE_COUNT = 5   # Multiple images
DEFAULT_CAPTURE_INTERVAL = 2  # time between capture

#import my custom files
from flask import Flask, render_template, send_from_directory, request, jsonify
import detection
import cv2
import os
import time
import threading
from threading import Event, Thread, Lock
from datetime import datetime
from uart import UART
import firebase
from firebase import upload_image_and_post_metadata
import sensors
import atexit

#flask only used for easy debugging and viewing without ssh
app = Flask(__name__)

# --- Globals ---
processing_lock = threading.Lock()
stop_event = Event()
inference_lock = Lock()  # serialize TFLite calls
results = {
    'originals': [],
    'processed': [],
    'detections': [],
    'times': [],
    'status': 'idle'
}
# PIR trigger flag
pir_enabled = True
pir_lock = threading.Lock()

# Initialise hardware

detection.init_camera()
uart = UART(port="/dev/serial0", baudrate=115200, timeout=1)

@atexit.register
def cleanup():
    try:
        uart.close()
    except:
        pass


def local_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#help mangae threading
def inference_worker(idx, orig_path, timestamp):
    if stop_event.is_set():
        return
    try:
        img = cv2.imread(orig_path)
        if img is None:
            raise ValueError(f"Image load failed: {orig_path}")
        with inference_lock:
            output_img, dets, elapsed = detection.detect_frame(img)
    except Exception as e:
        print(f"❌ Worker {idx} detection error: {e}")
        dets, elapsed, output_img = [], 0, None
    # check target match
    if output_img is not None:
        for det in dets:
            label = det.get('cls_label') or det.get('class') or det.get('label')
            if not label:
                continue
            clean = label.split(' (')[0].lower().replace('-', ' ').strip()
            if clean in [a.lower().replace('-', ' ').strip() for a in TARGET_ANIMALS]:
                stop_event.set()
                try: upload_image_and_post_metadata(orig_path, animal_name=clean, timestamp=timestamp)
                except Exception as e: print(f"❌ Firebase upload failed: {e}")
                try:
                    if not uart.send_and_wait_ack("TRIGGER", ack="ACK", timeout=2, retries=3):
                        print("❌ No UART ACK")
                except Exception as e:
                    print(f"❌ UART error: {e}")
                break
    proc_fname = f"processed_{idx+1}_{int(time.time())}.jpg"
    proc_path = os.path.join('static', proc_fname)
    if output_img is not None:
        cv2.imwrite(proc_path, output_img)
        results['processed'].append(proc_fname)
    else:
        results['processed'].append(None)
    results['detections'].append(dets)
    results['times'].append(round(elapsed, 3))
    print(f"✅ Worker {idx} done: {len(dets)} dets in {elapsed:.3f}s")

#btaching logic
def run_batch(count, interval):
    stop_event.clear()
    results.update({'originals':[], 'processed':[], 'detections':[], 'times':[], 'status':'processing'})
    threads = []
    os.makedirs('static', exist_ok=True)
    for i in range(count):
        frame, _ = detection.capture_frame()
        ts = local_timestamp()
        fname = f"orig_{i+1}_{int(time.time())}.jpg"
        path = os.path.join('static', fname)
        if frame is not None:
            cv2.imwrite(path, frame)
            results['originals'].append((fname, ts))
            t=Thread(target=inference_worker,args=(i,path,ts),daemon=True)
            t.start(); threads.append(t)
            print(f"📸 Frame {i+1} captured at {ts}")
        else:
            results['originals'].append((None, ts)); results['processed'].append(None)
            results['detections'].append([]); results['times'].append(0)
            print(f"⚠️ Frame {i+1} failed capture")
        time.sleep(interval)
    def finalize():
        for t in threads: t.join()
        results['status']='done'
    Thread(target=finalize,daemon=True).start()


@app.route('/')
def index():
    disp=[]
    for idx,(fn,ts) in enumerate(results['originals']):
        proc = results['processed'][idx] if idx<len(results['processed']) else None
        dets=results['detections'][idx] if idx<len(results['detections']) else []
        tme=results['times'][idx] if idx<len(results['times']) else 0
        disp.append({'original_filename':fn,'processed_filename':proc,'timestamp':ts,'detections':dets,'processing_time':tme})
    r,l=sensors.get_pir_status()
    with pir_lock: pe=pir_enabled
    return render_template('index.html',results=disp,status=results['status'],pir_enabled=pe,pir1=r,pir2=l)


@app.route('/detect')
def detect():
    if not processing_lock.acquire(blocking=False): return jsonify({'error':'Busy'}),429
    try: Thread(target=run_batch,args=(DEFAULT_CAPTURE_COUNT,DEFAULT_CAPTURE_INTERVAL),daemon=True).start(); return jsonify({'status':'processing','count':DEFAULT_CAPTURE_COUNT})
    finally: processing_lock.release()

@app.route('/status')
def status():
    data={'status':results['status'],'results':[]}
    for idx,(fn,ts) in enumerate(results['originals']):
        proc=results['processed'][idx] if idx<len(results['processed']) else None
        dets=results['detections'][idx] if idx<len(results['detections']) else []
        tme=results['times'][idx] if idx<len(results['times']) else 0
        data['results'].append({'original_filename':fn,'processed_filename':proc,'timestamp':ts,'detections':dets,'processing_time':tme})
    r,l=sensors.get_pir_status()
    with pir_lock: pe=pir_enabled
    data.update({'pir_enabled':pe,'pir_status':[r,l]})
    return jsonify(data)

@app.route('/pir_toggle',methods=['POST'])
def pir_toggle():
    global pir_enabled
    with pir_lock: pir_enabled=not pir_enabled
    return jsonify({'pir_enabled':pir_enabled})

@app.route('/static/<path:f>')
def serve_image(f): return send_from_directory('static',f)

def firebase_status_updater():
    while True:
        try: firebase.update_raspberry_pi_status()
        except: pass
        time.sleep(60)


def pir_monitor_thread():
    while True:
        with pir_lock: en=pir_enabled
        if en:
            r,l=sensors.get_pir_status()
            if r or l:
                if processing_lock.acquire(blocking=False):
                    try: run_batch(DEFAULT_CAPTURE_COUNT,DEFAULT_CAPTURE_INTERVAL)
                    finally: processing_lock.release()
                time.sleep(DEFAULT_CAPTURE_COUNT*DEFAULT_CAPTURE_INTERVAL+0.1)
        time.sleep(1)


if __name__=='__main__':
    threading.Thread(target=firebase_status_updater,daemon=True).start()
    threading.Thread(target=pir_monitor_thread,daemon=True).start()
    app.run(host='0.0.0.0',port=8080,debug=False)
