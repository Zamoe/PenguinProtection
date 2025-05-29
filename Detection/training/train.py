# train.py

import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
import os

# size parmeters
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS = 10

# manipulate the imeagas
datagen = ImageDataGenerator(
    rescale=1./255,
    rotation_range=20,
    zoom_range=0.2,
    horizontal_flip=True,
    brightness_range=(0.7, 1.3)
)

#Load images 
train_ds = datagen.flow_from_directory(
    'images/',
    target_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    class_mode='categorical',
    shuffle=True
)

# automiatic class naming file as a txt 
class_names = list(train_ds.class_indices.keys())
with open('class_names.txt', 'w') as f:
    for name in class_names:
        f.write(name + '\n')

print(f"📂 Classes found: {class_names}")
print(f"🖼️ Number of training images: {train_ds.samples}")

# From tf docs
base_model = tf.keras.applications.MobileNetV2(
    input_shape=IMG_SIZE + (3,),
    include_top=False,
    weights='imagenet'
)


base_model.trainable = True
for layer in base_model.layers[:-30]:
    layer.trainable = False


model = tf.keras.Sequential([
    base_model,
    tf.keras.layers.GlobalAveragePooling2D(),
    tf.keras.layers.Dense(train_ds.num_classes, activation='softmax')
])

# compile model
model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
              loss='categorical_crossentropy',
              metrics=['accuracy'])

# Train the model
model.fit(train_ds, epochs=EPOCHS)

# output keras
model.save('honeybadger_model.keras')
print("Model saved as 'honeybadger_model.keras'")
