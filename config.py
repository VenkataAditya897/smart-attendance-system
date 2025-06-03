import os

class Config:
    SECRET_KEY = 'your_secret_key'  # Change this
    MONGO_URI = 'mongodb://localhost:27017/Attendance'
    UPLOAD_FOLDER = os.path.join('static', 'qr_codes')
    IMAGE_FOLDER = os.path.join('static', 'captured_images')

