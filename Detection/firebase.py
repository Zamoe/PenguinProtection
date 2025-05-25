# firebase.py
#helper function to post image to firebase storage and then post firbase storage link to realtime DB

import firebase_admin
from firebase_admin import credentials, storage, db
import uuid
import os
import datetime
import firebase_config  # 🔽 Import your config

# Initialize Firebase 
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_config.FIREBASE_CREDENTIALS)
    firebase_admin.initialize_app(cred, {
        'storageBucket': firebase_config.FIREBASE_STORAGE_BUCKET,
        'databaseURL': firebase_config.FIREBASE_DATABASE_URL
    })


def upload_image_and_post_metadata(local_image_path, animal_name, timestamp=None):
    if not os.path.isfile(local_image_path):
        raise FileNotFoundError(f"Image not found: {local_image_path}")

    bucket = storage.bucket()
    image_id = str(uuid.uuid4())
    blob = bucket.blob(f'deterrent_images/{image_id}.jpg')

    blob.upload_from_filename(local_image_path)
    blob.make_public()
    image_url = blob.public_url

    if timestamp is None:
        timestamp = datetime.datetime.utcnow().isoformat() + 'Z'

    data = {
        'animal': animal_name,
        'image_url': image_url,
        'timestamp': timestamp
    }

    ref = db.reference('Deterrents')
    new_entry = ref.push(data)

    print(f"✅ Uploaded and logged: {data}")
    return {'key': new_entry.key, 'url': image_url}


def update_raspberry_pi_status():
    """Updates the Raspberry Pi's online status and last seen time in Firebase."""
    status_ref = db.reference('status/raspberry_pi')

    # Get local time without milliseconds: YYYY-MM-DDTHH:MM:SS
    local_time_str = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    data = {
        'online': True,
        'last_seen': local_time_str
    }

    status_ref.set(data)
    print(f"📡 Status updated: {data}")
    return data



# test debug
if __name__ == '__main__':
    try:
        print("🚀 Uploading test image...")
        test_path = 'static/processed_1.jpg'
        test_animal = 'Leopard'
        test_timestamp = '2025-05-17T22:10:00Z'

        upload_image_and_post_metadata(test_path, test_animal, test_timestamp)

        print("🔁 Updating Raspberry Pi status...")
        update_raspberry_pi_status()

    except Exception as e:
        print(f"❌ Error: {e}")
