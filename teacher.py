from pymongo import MongoClient
from bson import ObjectId  # Import ObjectId to handle MongoDB _id

# Connect to MongoDB (Replace with your MongoDB URI)
client = MongoClient("mongodb://localhost:27017/")  # Change if using a remote DB

# Select database and collection
db = client["Attendance"]  # Your database name
collection = db["users"]  # Your collection name

# Document to upload
document = {
    "_id": ObjectId("67ba95c2d0a50a336c3a3333"),
    "email": "staff1@gmail.com",
    "password": "scrypt:32768:8:1$VMDP4DqdJupLHHzy$efaaa6aeb49eab8fe4e464330bf76fd20082116afcfa921f3c4c364e0fb8e4c45dcddcfdb2e8c1d548ca8004c86686b23b6f8e853ef559ccaa9729c89ab3959e",
    "role": "staff",
    "roll_number": "101",
    "student_name": "Staff",
    "phone": "123456789",
    "approved": True,
    "qr_code": "f4.png"
}

# Insert into MongoDB
result = collection.insert_one(document)

# Print confirmation
print(f"Teacher Created")
