from fastapi import FastAPI , File , UploadFile , Form , BackgroundTasks , HTTPException
from dotenv import load_dotenv
import os
from pydantic import BaseModel ,  EmailStr
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure 
import cloudinary
import cloudinary.uploader
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mail import ConnectionConfig
from fastapi_mail import FastMail, MessageSchema, MessageType
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json

origins = ["*"]

load_dotenv()
app = FastAPI()

#Email config
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=os.getenv("MAIL_PORT"),
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
)

class EmailSchema(BaseModel):
    email: EmailStr
    subject: str
    body: str

#Cloudinary config
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET_KEY")
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#Independent code to upload file
@app.post("/api/upload")
async def upload(file:UploadFile = File(...)):
    contents = await file.read()
    response = cloudinary.uploader.upload(
        contents , 
        filename = file.filename ,
        resource_type = "auto",
        folder = "python_fastapi_server/data/assets/"
    )
    return{
        "url":response.get("secure_url"),
        "public_id":response.get("public_id")
    }



#music-app
@app.post("/api/upload/music")
async def upload_music(
    audio_file: UploadFile = File(...),
    metadata: str = Form(...)
):
    try:
        client = None
        # Parse metadata
        track_metadata = json.loads(metadata)
        
        # Upload to Cloudinary
        audio_contents = await audio_file.read()
        cloudinary_result = cloudinary.uploader.upload(
           audio_contents , 
           resource_type = "auto",
           folder = "my-music-web-app/data/assets/"
           )
        
        # Save to database
        client = MongoClient(os.getenv("MONGODB_URL"))
        client.admin.command('ping')
        print("Connection established with database successfully.")
        db = client["myMusicDatabase"]
        collection = db["song"]
        doc = collection.insert_one({
            **track_metadata,
            "cloudinary_url": cloudinary_result["secure_url"],
            "cloudinary_id": cloudinary_result["public_id"],
            "created_at":datetime.now(timezone.utc)
        })
        
        saved_track = collection.find_one({"_id":doc.inserted_id})
        created_at_ist = saved_track["created_at"].astimezone(ZoneInfo("Asia/Kolkata"))

        return {
            "id": str(doc.inserted_id),
            "title": saved_track["title"],
            "artist": saved_track["artist"],
            "genre": saved_track["genre"],
            "album": saved_track["album"],
            "duration": saved_track["duration"],
            "cloudinary_url": saved_track["cloudinary_url"],
            "created_at": created_at_ist.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if client :
           client.close()
           print("Connection closed with database.")   

#fetching the song
@app.get("/api/get/music_data")
async def fetchMusic():
    arr=[]
    try:
        client = None
        client = MongoClient(os.getenv("MONGODB_URL"))
        client.admin.command('ping')
        print("Connection established with database successfully.")
        db = client["myMusicDatabase"]
        collection = db["song"]
        for doc in collection.find():
           doc["_id"]= str(doc["_id"])
           arr.append(doc)
        return arr   

    except Exception as e:
       return {
           "Error": e
       }
    finally:
        if client :
           client.close()
           print("Connection closed with database.")          

#student-complaint-management-system
#For complaint registering
@app.post("/api/register/complaint/student")
async def complainRegister(
    background_tasks: BackgroundTasks ,
    file:UploadFile = File(...) , # for image upload
    fullname:str = Form(...),
    email:str = Form(...),
    title:str = Form(...),
    description:str = Form(...)
):
    client = None
    contents = await file.read()
    response = cloudinary.uploader.upload(
        contents , 
        filename = file.filename ,
        resource_type = "auto",
        folder = f"student-complaint-management-system/data/assets/{email}"
    )

    try:
       client = MongoClient(os.getenv("MONGODB_URL"))
       client.admin.command('ping')
       print("Connection established with database successfully.")
       db = client["mydb"]
       collection = db["complaint"]
       doc = collection.insert_one({
            "fullname": fullname ,
            "email":email,
            "title":title,
            "status":"pending",
            "description":description,
            "image_url":response.get("secure_url"),
            "public_id":response.get("public_id"),
            "created_at":datetime.now()
       })
       #Email sending for registered complaint 
       async def sendConfirmationThroughemail(email_data:EmailSchema, background_tasks: BackgroundTasks):
        message = MessageSchema(
        subject=email_data.subject,
        recipients=[email_data.email],
        body=email_data.body,
        subtype=MessageType.html
        )
        fm = FastMail(conf)
        background_tasks.add_task(fm.send_message, message)


       await sendConfirmationThroughemail(
            EmailSchema(
            email = f"{email}",
            subject = f"{title[0].upper()}{title[1:]} Complaint",
            body = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f6f8; color: #333;">
            <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 25px; border-radius: 10px; box-shadow: 0 0 8px rgba(0,0,0,0.1);">
            <h1 style="color: #2e86de; border-bottom: 2px solid #3498db; padding-bottom: 10px;">
            ✅ Complaint Registered Successfully
            </h1>

            <p style="font-size: 16px; line-height: 1.6;">
            Thank you for submitting your complaint. Below are the details:
            </p>

            <ul style="list-style: none; padding: 0; font-size: 16px; line-height: 1.6;">
            <li style="margin-bottom: 8px;"><strong>🆔 Complaint ID:</strong> {str(doc.inserted_id)}</li>
            <li style="margin-bottom: 8px;"><strong>📝 Description:</strong> {description}</li>
            <li style="margin-bottom: 8px;"><strong>📎 File/Image:</strong> <a href="{response.get("secure_url")}" style="color: #2980b9;">Click to View</a></li>
            </ul>

            <p style="margin-top: 30px; font-size: 14px; color: #666;">
            If you did not submit this complaint, please contact support immediately.
            </p>

            <p style="font-size: 14px; color: #999; margin-top: 10px;">
            — Student Complaint Portal
            </p>
            </div>
            </div>
            """
            ),
             background_tasks
            )
       
       created_at = collection.find_one({"_id": doc.inserted_id})["created_at"].astimezone(ZoneInfo("Asia/Kolkata"))
       await sendConfirmationThroughemail(
            EmailSchema(
            email = os.getenv("MY_EMAIL_ID"),
            subject = f"{title[0].upper()}{title[1:]} Complaint Received",
            body = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f6f8; color: #333; max-width: 600px; margin: auto;">
            <div style="background-color: #ffffff; padding: 25px; border-radius: 10px; box-shadow: 0 0 8px rgba(0,0,0,0.1); overflow-wrap: break-word; word-break: break-word;">
    
            <h1 style="color: #c0392b; border-bottom: 2px solid #e74c3c; padding-bottom: 10px; margin-top: 0;">
            🚨 New Complaint Received
            </h1>

            <p style="font-size: 16px; line-height: 1.6; margin-top: 0;">
            A new complaint has been submitted. Details are below:
            </p>

            <ul style="list-style: none; padding: 0; font-size: 16px; line-height: 1.6; margin: 0;">
            <li style="margin-bottom: 8px;"><strong>🆔 Complaint ID:</strong> {str(doc.inserted_id)}</li>
            <li style="margin-bottom: 8px; word-wrap: break-word; white-space: normal;"><strong>👤 Username:</strong> {fullname}</li>
            <li style="margin-bottom: 8px;"><strong>📧 User Email:</strong> {email}</li>
            <li style="margin-bottom: 8px;"><strong>🕒 Created At:</strong> {created_at}</li>
            <li style="margin-bottom: 8px; word-wrap: break-word; white-space: normal;"><strong>📝 Description:</strong> {description}</li>
            <li style="margin-bottom: 8px;"><strong>📎 File/Image Link:</strong> <a href="{response.get("secure_url")}" style="color: #2980b9; word-break: break-word;">Click to View</a></li>
            </ul>

            <p style="margin-top: 30px; font-size: 14px; color: #666;">
            Please review this complaint and take appropriate action in the admin dashboard.
            </p>

            <p style="font-size: 14px; color: #999; margin-top: 10px;">
            — Student Complaint Portal
            </p>
            </div>
            </div>
            """
            ) ,
             background_tasks
            )

       return{
        "Message": "Student complain register successfully.",
        "_id": str(doc.inserted_id),
        "fullname": fullname ,
        "email":email,
        "title":title,
        "status":"pending",
        "description":description,
        "url":response.get("secure_url"),
        "public_id":response.get("public_id")
    }
    except ConnectionFailure as e:
        return {
        "Message":"Error in connecting to database."
        }
    except Exception as e :
        return {
        "ConnectionToDatabase":"Okay",   
        "Message":"Complaint not registered in database.",
        "Error":str(e)
        }
    finally:
        if client :
            client.close()
            print("Connection closed with database.")   

@app.get("/")
def root():
    return {
        "Message": "Server is active"
    }

class User(BaseModel):
    username : str
    email: str
    password : str

@app.post("/api/create/user")
async def createUser(data:User):
    client = None
    try:
       client =  MongoClient(os.getenv("MONGODB_URL"))
       client.admin.command('ping')
       print("Connection established with database successfully.")
       db = client["mydb"]
       collection = db["user"]
       collection.insert_one(data.dict())
       return{
        "ConnectionToDatabase":"Okay",  
        "Message":"User created in database successfully."
       }
    except ConnectionFailure as e:
        return {
        "Message":"Error in connecting to database."
        }
    except:
        return {
        "ConnectionToDatabase":"Okay",   
        "Message":"User is not created in database."
        }
    finally:
       if client :
            client.close()
            print("Connection closed with database.")   



@app.get("/api/show/user")
async def showUser():
    client = None
    arr = []
    try:
       client =  MongoClient(os.getenv("MONGODB_URL"))
       client.admin.command('ping')
       print("Connection established with database successfully.")
       db = client["mydb"]
       collection = db["user"]
       for doc in collection.find():
           doc["_id"]= str(doc["_id"])
           arr.append(doc)
       return{
        "ConnectionToDatabase":"Okay",  
        "Message":"User fetched from database successfully.",
        "Data":arr
       }
    except ConnectionFailure as e:
        return {
        "Message":"Error in connecting to database."
        }
    except Exception as e :
        return {
        "ConnectionToDatabase":"Okay",   
        "Message":"Unable to fetch the data.",
        "Error":e
        }
    finally:
       if client :
            client.close()
            print("Connection closed with database.")  


#Independent email sending code
@app.post("/api/send/email")
async def send_email(email_data: EmailSchema, background_tasks: BackgroundTasks):
    message = MessageSchema(
        subject=email_data.subject,
        recipients=[email_data.email],
        body=email_data.body,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    background_tasks.add_task(fm.send_message, message)
    return {"message": "Email has been sent"}

# if __name__ == "__main__":
#    uvicorn.run("main:app", port=5000, log_level="info")





