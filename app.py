from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import mongo
from utils import generate_qr, capture_image, send_absent_sms
from flask_session import Session
import datetime
from bson import ObjectId
import os
import base64
from config import Config
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import time
import shutil
import json
import face_recognition


app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config["SESSION_TYPE"] = "filesystem"
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024
Session(app)

@app.route('/')
def home():
    return render_template('index1.html')

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = mongo.db.users.find_one({'email': email})
        
        if user and check_password_hash(user['password'], password):
            if user['role'] == 'student' and not user['approved']:
                error = "Your registration is pending approval."
            else:
                session['user_id'] = str(user['_id'])
                session['role'] = user['role']
                session['student_name'] = user.get('student_name', '')
                session['roll_number'] = user.get('roll_number', '')
                session['phone'] = user.get('phone', '')
                return redirect(url_for('dashboard'))
        else:
            error = "Invalid credentials, try again."
    
    return render_template('signin.html', error=error)

@app.route('/signin/student', methods=['GET', 'POST'])
def student_signin():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = mongo.db.users.find_one({'email': email, 'role': 'student'})

        if user and check_password_hash(user['password'], password):
            if not user['approved']:
                error = "Your registration is pending approval."
            else:
                session['user_id'] = str(user['_id'])
                session['role'] = 'student'
                session['student_name'] = user.get('student_name', '')
                session['roll_number'] = user.get('roll_number', '')
                session['phone'] = user.get('phone', '')
                return redirect(url_for('dashboard'))
        else:
            error = "Invalid credentials, try again."

    return render_template('student_signin.html', error=error, role="student")


@app.route('/signin/staff', methods=['GET', 'POST'])
def staff_signin():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = mongo.db.users.find_one({'email': email, 'role': 'staff'})

        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['role'] = 'staff'
            session['student_name'] = user.get('student_name', '')
            session['roll_number'] = user.get('roll_number', '')
            session['phone'] = user.get('phone', '')
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid credentials, try again."

    return render_template('staff_signin.html', error=error, role="staff")



def sanitize_email_for_path(email):
    return email.replace('@', '_at_').replace('.', '_dot_').strip()

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        roll_number = request.form.get('roll_number')
        student_name = request.form.get('student_name')
        phone = request.form.get('phone')
        face_images = request.form.get('face_images')

        hashed_password = generate_password_hash(password)
        
        existing_user = mongo.db.users.find_one({'email': email})
        if existing_user:
            error = "Email already exists! Please use a different one."
        else:
            student_id = str(mongo.db.users.count_documents({}) + 1)
            qr_code = generate_qr(student_id, email,roll_number,student_name,phone)

            mongo.db.users.insert_one({
                'email': email,
                'password': hashed_password,
                'role': 'student',
                'roll_number': roll_number,
                'student_name': student_name,
                'phone': phone,
                'approved': False,
                'qr_code': qr_code
            })
            saniemail = sanitize_email_for_path(email)
            # Save face images
            if face_images:
                img_dir = f"static/face_dataset/{saniemail}"
                os.makedirs(img_dir, exist_ok=True)

                images = json.loads(face_images)
                for idx, img_data in enumerate(images):
                    img_bytes = base64.b64decode(img_data.split(',')[1])
                    with open(os.path.join(img_dir, f"img_{idx+1}.jpg"), 'wb') as f:
                        f.write(img_bytes)

            flash("Signup successful! Staff approval required for students.", "success")
            return redirect(url_for('signin'))

    return render_template('signup.html', error=error)


@app.route('/staff_attendance')
def staff_attendance():
    if 'user_id' not in session or session.get('role') != 'staff':
        return redirect(url_for('signin'))

    selected_date = request.args.get('date', None)
    
    students = {s["roll_number"]: s for s in mongo.db.users.find({"role": "student", "approved": True})}

    attendance_records = []
    if selected_date:
        try:
            date_obj = datetime.datetime.strptime(selected_date, "%Y-%m-%d")
            query = {
                "date": {
                    "$gte": datetime.datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0),
                    "$lt": datetime.datetime(date_obj.year, date_obj.month, date_obj.day, 23, 59, 59)
                }
            }
            attendance_records = list(mongo.db.attendance.find(query))
        except ValueError:
            return "Invalid date format", 400

    attendance_summary = {}
    
    for record in attendance_records:
        roll_number = record["roll_number"]
        status = record["approval_request"]

        if roll_number in students:
            attendance_summary[roll_number] = {
                "name": students[roll_number]["student_name"],
                "email": students[roll_number]["email"],
                "present": status == "approved",
                "absent": status == "rejected"
            }

    for roll_number, student in students.items():
        if roll_number not in attendance_summary:
            attendance_summary[roll_number] = {
                "name": student["student_name"],
                "email": student["email"],
                "present": False,
                "absent": True
            }

    total_present = sum(1 for s in attendance_summary.values() if s["present"])
    total_absent = sum(1 for s in attendance_summary.values() if s["absent"])

    return render_template(
        "staff_attendance.html",
        attendance_summary=attendance_summary,
        total_present=total_present,
        total_absent=total_absent,
        selected_date=selected_date
    )

import smtplib
from email.mime.text import MIMEText

@app.route('/notify_absent', methods=['POST'])
def notify_absent():
    if 'user_id' not in session or session.get('role') != 'staff':
        return jsonify({"error": "Unauthorized"}), 403

    roll_number = request.json.get("roll_number")
    student = mongo.db.users.find_one({"roll_number": roll_number, "approved": True})

    if not student:
        return jsonify({"error": "Student not found"}), 404

    student_email = student["email"]
    message_body = f"Dear {student['student_name']},\n\nYou were marked absent today. Please contact your instructor if this is an error.\n\nBest,\nYour School"

    try:
        sender_email = "REPLACE_WITH_YOUR_EMAIL"  # put your email address from where you want to send the email message from
        sender_password = "REPLACE_WITH_PASSWORD" #this is not your gmail password check documentation for steps
        smtp_server = "smtp.gmail.com"
        smtp_port = 587

        msg = MIMEText(message_body)
        msg["Subject"] = "Attendance Notification"
        msg["From"] = sender_email
        msg["To"] = student_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, student_email, msg.as_string())
        print("msg sent")
        return jsonify({"success": f"Notification sent to {student_email}"}), 200
    except Exception as e:
        print("msg error")
        return jsonify({"error": str(e)}), 500
    

@app.route('/notify_absentees', methods=['POST'])
def notify_absentees():
    if 'user_id' not in session or session.get('role') != 'staff':
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    absentees = data.get("absentees", [])

    if not absentees:
        return jsonify({"message": "No absentees to notify"}), 400

    sender_email = "REPLACE_WITH_YOUR_EMAIL"
    sender_password = "REPLACE_WITH_PASSWORD"
    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    notified_students = []
    errors = []

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)

            for roll_number in absentees:
                student = mongo.db.users.find_one({"roll_number": roll_number, "approved": True})
                if student:
                    student_email = student["email"]
                    message_body = f"Dear {student['student_name']},\n\nYou were marked absent today. Please contact your instructor if this is an error.\n\nBest,\nYour School"
                    
                    msg = MIMEText(message_body)
                    msg["Subject"] = "Attendance NotificationALLABSNTIES"
                    msg["From"] = sender_email
                    msg["To"] = student_email
                    
                    server.sendmail(sender_email, student_email, msg.as_string())
                    notified_students.append(student_email)
                else:
                    errors.append(f"Student {roll_number} not found or not approved")

        return jsonify({"success": f"Notifications sent to {notified_students}", "errors": errors}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('signin'))
    
    if session['role'] == 'staff':

        students = list(mongo.db.users.find({'role': 'student', 'approved': False}))

        return render_template('staff_dashboard.html', students=students)
    
 
    student_id = session['user_id']
    student = mongo.db.users.find_one({'_id': ObjectId(student_id)})

    if not student:
        return redirect(url_for('student_signin'))
    qr_code_url = student.get('qr_code', None) 
    student_email = student.get('email', 'Unknown')
    student_name = student.get('student_name', '')
    student_roll_number = student.get('roll_number', '')
    student_phone = student.get('phone', '')

    attendance_records = list(mongo.db.attendance.find({'email': student_email}))
    saniemail = sanitize_email_for_path(student_email)

    image_dir = os.path.join('static', 'face_dataset', saniemail)  
    profile_img_path = None
    if os.path.exists(image_dir) and os.path.isdir(image_dir):
        print("exists")
        images = sorted([img for img in os.listdir(image_dir) if img.endswith('.jpg')])
        if images:
            profile_img_path = f"face_dataset/{saniemail}/{images[0]}"  # This should be the relative path from the 'static' folder


    return render_template('dashboard.html', qr_code_url=qr_code_url, student_email=student_email, student_id=str(student_id),student_name=student_name,student_roll_number=student_roll_number,student_phone=student_phone, attendance_records=attendance_records, profile_img_path=profile_img_path)



@app.route('/attendance_report')
def attendance_report():
    student_id = session.get("user_id")  
    student = mongo.db.users.find_one({'_id': ObjectId(student_id)})
    if not student:
        return redirect(url_for('student_signin'))
    student_email = student.get('email', 'Unknown')
    all_attendance_records = list(mongo.db.attendance.find({}))
    student_attendance_records = list(mongo.db.attendance.find({"email": student_email}))

    unique_dates = set(record.get("date").date() for record in all_attendance_records)

    days_present = set(
        record.get("date").date() for record in student_attendance_records
        if record.get("approval_request") == "approved"
    )

    total_classes = len(unique_dates)
    days_present_count = len(days_present) 

    attendance_percentage = (days_present_count / total_classes) * 100 if total_classes > 0 else 0

    attendance_data = {
        "Student Name": student.get("student_name", "Unknown"),
        "Days Present": days_present_count,
        "Total Classes": total_classes,
        "Attendance Percentage": f"{attendance_percentage:.2f}%"
    }

    return render_template("attendance_report.html", attendance_data=attendance_data,student_attendance_records=student_attendance_records)

@app.route('/approve_student/<student_id>')
def approve_student(student_id):
    if 'user_id' in session and session.get('role') == 'staff':
        try:
            result = mongo.db.users.update_one({'_id': ObjectId(student_id)}, {'$set': {'approved': True}})
            
            if result.modified_count > 0:
                flash("Student approved successfully!", "success")
            else:
                flash("Student not found or already approved.", "warning")

        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
    
    return redirect(url_for('dashboard'))


@app.route('/attendance_validation')
def attendance_validation():
    if 'user_id' not in session or session.get('role') != 'staff':
        return redirect(url_for('signin'))
    
    filter_status = request.args.get('status', 'pending')

    if filter_status == 'all':
        query = {}
    elif filter_status == 'pending':
        query = {'approval_request': False} 
    elif filter_status == 'approved':
        query = {'approval_request': 'approved'}
    elif filter_status == 'rejected':
        query = {'approval_request': 'rejected'}
    else:
        query = {}

    attendance_records = list(mongo.db.attendance.find(query))
    
    return render_template('attendance_validation.html', attendance_records=attendance_records, filter_status=filter_status)


@app.route('/update_attendance/<record_id>', methods=['POST'])
def update_attendance(record_id):
    if 'user_id' not in session or session.get('role') != 'staff':
        return jsonify({"success": False, "message": "Unauthorized access"}), 403

    data = request.get_json()
    new_status = data.get('status') 

    if new_status not in ['approved', 'rejected', 'pending']:
        return jsonify({"success": False, "message": "Invalid status"}), 400

    try:
        mongo.db.attendance.update_one({'_id': ObjectId(record_id)}, {'$set': {'approval_request': new_status}})
        return jsonify({"success": True, "new_status": new_status})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/approve_attendance/<record_id>', methods=['POST'])
def approve_attendance(record_id):
    if 'user_id' not in session or session.get('role') != 'staff':
        return redirect(url_for('signin'))
    
    try:
        mongo.db.attendance.update_one({'_id': ObjectId(record_id)}, {'$set': {'approval_request': 'approved'}})
        flash("Attendance approved successfully!", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")

    return redirect(url_for('attendance_validation'))

@app.route('/reject_attendance/<record_id>', methods=['POST'])
def reject_attendance(record_id):
    if 'user_id' not in session or session.get('role') != 'staff':
        return redirect(url_for('signin'))
    
    try:
        mongo.db.attendance.update_one({'_id': ObjectId(record_id)}, {'$set': {'approval_request': 'rejected'}})
        flash("Attendance rejected successfully!", "warning")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")

    return redirect(url_for('attendance_validation'))


face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')


def scan_qr_code(image):
    """Detects and decodes QR code from an image."""
    qr_codes = decode(image)
    if qr_codes:
        return qr_codes[0].data.decode('utf-8') 
    return None

def detect_face(image):
    """Detects a face in the image and returns True if found."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    return len(faces) > 0  


@app.route('/mark_attendance_page')
def mark_attendance_page():
    if 'user_id' not in session:
        return redirect(url_for('signin'))
    
    return render_template('mark_attendance.html') 



import face_recognition

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'user_id' not in session:
        return redirect(url_for('signin'))

    student_id = session['user_id']
    student = mongo.db.users.find_one({'_id': ObjectId(student_id)})

    if student and student.get('approved'):
        image_data = request.json.get('imageData')
        if not image_data:
            return jsonify({"status": "error", "message": "No image received"})

        image_data = image_data.replace('data:image/jpeg;base64,', '')
        image_bytes = base64.b64decode(image_data)

        filename = f"attendance_{student_id}_{int(time.time())}.jpg"
        temp_filepath = os.path.join(Config.IMAGE_FOLDER, filename)

        with open(temp_filepath, 'wb') as f:
            f.write(image_bytes)

        image = cv2.imread(temp_filepath)

        if not detect_face(image):
            os.remove(temp_filepath)
            return jsonify({"status": "error", "message": "No face detected"})

        qr_data = scan_qr_code(image)
        if not qr_data:
            os.remove(temp_filepath)
            return jsonify({"status": "error", "message": "QR code not detected"})
        
        # Extract QR data
        student_info = qr_data.split(",")
        qr_roll, qr_name, qr_email = student_info[2], student_info[3], student_info[1]
        sanitized_qr_email = sanitize_email_for_path(qr_email)

        # Load and encode uploaded face
        uploaded_image = face_recognition.load_image_file(temp_filepath)
        uploaded_encodings = face_recognition.face_encodings(uploaded_image)
        if not uploaded_encodings:
            return jsonify({"status":"error","message":"Face not clear"}), 400
        uploaded_encoding = uploaded_encodings[0]

        # 1) Check against *all* known faces to find whose face this really is
        detected_owner = None
        face_dataset_root = os.path.join(app.root_path, 'static', 'face_dataset')
        for folder in os.listdir(face_dataset_root):
            folder_path = os.path.join(face_dataset_root, folder)
            if not os.path.isdir(folder_path): continue
            for img_file in os.listdir(folder_path):
                if not img_file.lower().endswith('.jpg'): continue
                known_encodings = face_recognition.face_encodings(
                    face_recognition.load_image_file(os.path.join(folder_path, img_file))
                )
                if known_encodings and face_recognition.compare_faces([known_encodings[0]], uploaded_encoding)[0]:
                    detected_owner = folder  # this is the *sanitized* email folder
                    break
            if detected_owner: break

        if not detected_owner:
            os.remove(temp_filepath)
            return jsonify({"status":"error","message":"Face not recognized"}), 400

        # 2) Now compare detected_owner vs qr_email folder
        if detected_owner != sanitized_qr_email:
            os.remove(temp_filepath)
            return jsonify({
                "status": "error",
                "message": f"Face belongs to {detected_owner}, not the QR-code holder ({qr_email})"
            }), 403

        # 3) If both match, it’s authentic—proceed to record attendance
        session['scanned_student'] = {
            'roll_number': qr_roll,
            'name': qr_name,
            'email': qr_email,
            'image_path': filename
        }
        return jsonify({"status":"success","roll_number":qr_roll,"name":qr_name,"email":qr_email,"image_path":url_for('static',filename=f'captured_images/{filename}')})

    return jsonify({"status": "error", "message": "You are not approved yet!"})


@app.route('/confirm_attendance', methods=['POST'])
def confirm_attendance():
    """Marks attendance after student confirmation."""
    if 'scanned_student' not in session:
        return jsonify({"status": "error", "message": "No student data available!"})

    student_id = session['user_id']
    scanned_student = session['scanned_student']

    roll_number = scanned_student['roll_number'].strip()
    name = scanned_student['name'].strip()
    email = scanned_student['email'].strip()
    temp_filename = scanned_student.get('image_path')
    temp_image_path = scanned_student.get('image_path')

    today = datetime.datetime.now().date()
    existing_attendance = mongo.db.attendance.find_one({
        'roll_number': roll_number,
        'email': email,
        'date': {
            '$gte': datetime.datetime.combine(today, datetime.time.min),
            '$lt': datetime.datetime.combine(today, datetime.time.max)
        }
    })

    if existing_attendance:
        abs_image_path = os.path.join(Config.IMAGE_FOLDER, os.path.basename(temp_image_path))
        if os.path.exists(abs_image_path):
            os.remove(abs_image_path)
            print("removed")
        print("Already registered")
        return jsonify({"status": "error", "message": "Attendance already marked for today!"})


    mongo.db.attendance.insert_one({
        'student_id': ObjectId(student_id),
        'roll_number': roll_number,
        'name': name,
        'email': email,
        'date': datetime.datetime.now(),
        'image_path': temp_filename,
        'approval_request': "approved"
    })

    session.pop('scanned_student', None) 

    print("Attendance confirmed")
    return jsonify({"status": "success", "message": "Attendance confirmed!"})


@app.route('/calculate_attendance')
def calculate_attendance():
    if 'user_id' not in session:
        return redirect(url_for('signin'))


    students = list(mongo.db.users.find({"role": "student"}))
    attendance_records = list(mongo.db.attendance.find({}))

    attendance_count = {}
    unique_dates = set()

    for record in attendance_records:
        roll_number = record.get("roll_number")
        date = record.get("date").date() 
        approval_status = record.get("approval_request")

        unique_dates.add(date)

        if approval_status == "approved":
            if roll_number not in attendance_count:
                attendance_count[roll_number] = set()
            attendance_count[roll_number].add(date)

    total_classes = len(unique_dates)

    attendance_table = []
    
    for student in students:
        roll_number = student.get("roll_number")
        name = student.get("student_name")
        days_present = len(attendance_count.get(roll_number, set()))
        attendance_percentage = (days_present / total_classes) * 100 if total_classes > 0 else 0
        
        attendance_table.append({
            "Roll Number": roll_number,
            "Student Name": name,
            "Days Present": days_present,
            "Total Classes": total_classes,
            "Attendance Percentage": f"{attendance_percentage:.2f}%"
        })

    return render_template('attendance01.html', attendance_table=attendance_table)


@app.route('/logout')
def logout():
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=False)
