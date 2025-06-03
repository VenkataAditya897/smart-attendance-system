import qrcode
import os
import cv2
from config import Config
from twilio.rest import Client

# def generate_qr(student_id, email,roll_number,student_name,phone):
#     qr_data = f"{student_id},{email}"
#     qr = qrcode.make(qr_data)
#     filename = f"{student_id}.png"
#     path = os.path.join(Config.UPLOAD_FOLDER, filename)
#     qr.save(path)
#     return filename

def generate_qr(student_id, email, roll_number, student_name, phone):
    qr_data = f"{student_id} ,{email} ,{roll_number} ,{student_name} ,{phone}"
    qr = qrcode.make(qr_data)
    filename = f"{student_id}.png"
    path = os.path.join(Config.UPLOAD_FOLDER, filename)
    qr.save(path)
    return filename


# def capture_image(student_id):
#     cap = cv2.VideoCapture(0)
#     ret, frame = cap.read()
#     if ret:
#         filepath = os.path.join(Config.IMAGE_FOLDER, f"{student_id}.jpg")
#         cv2.imwrite(filepath, frame)
#     cap.release()


def capture_image(student_id):
    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Show live camera feed
        cv2.imshow("Capture Image (Press 'c' to Capture, 'q' to Quit)", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('c'):  # Press 'c' to capture
            filepath = os.path.join(Config.IMAGE_FOLDER, f"{student_id}.jpg")
            cv2.imwrite(filepath, frame)
            print(f"Image saved at: {filepath}")
            break
        elif key == ord('q'):  # Press 'q' to quit without capturing
            break

    cap.release()
    cv2.destroyAllWindows()
    
def send_absent_sms(parent_number, student_name):
    client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
    message = f"Dear Parent, your child {student_name} was absent today."
    client.messages.create(to=parent_number, from_=Config.TWILIO_PHONE_NUMBER, body=message)
