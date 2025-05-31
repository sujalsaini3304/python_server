from fastapi import FastAPI , File , UploadFile , Form , BackgroundTasks , HTTPException , Query
from dotenv import load_dotenv
import os
from pydantic import BaseModel ,  EmailStr , Field
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
import yt_dlp
import subprocess
import io
import pytz
import bcrypt

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

class TrackResponse(BaseModel):
    id: str = Field(..., alias="_id")
    duration: int
    title: str
    artist: str
    genre: str
    album: str
    year: int | None = None
    fileSize: int | None = None
    format: str
    bitRate: int | None = None
    sampleRate: int | None = None
    originalFilename: str
    cloudinary_url: str
    cloudinary_id: str
    created_at: datetime
    like_count: int
    thumbnail: str | None

class YouTubeURL(BaseModel):
    url: str

#upload from youtube link
@app.post("/api/upload/youtube/url")
async def upload_from_youtube_link(data : YouTubeURL):
     client = None
     try:
        with yt_dlp.YoutubeDL({'format': 'bestaudio'}) as ydl:
            info = ydl.extract_info(data.url, download=False)
            audio_url = info['url']
            title = info.get('title', 'Unknown Title')
            artist = info.get('uploader', 'Unknown Artist')
            duration = int(info.get('duration', 0))
            thumbnail = info.get('thumbnail', None)
        
        # Convert audio to MP3 in memory
        ffmpeg_cmd = [
            'ffmpeg', '-i', audio_url,
            '-f', 'mp3', '-vn', '-acodec', 'libmp3lame', '-ab', '192k',
            '-hide_banner', '-loglevel', 'error', 'pipe:1'
        ]
        result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail="FFmpeg failed: " + result.stderr.decode())
        
        mp3_data = io.BytesIO(result.stdout)
        original_filename = f"{title}.mp3"
        mp3_data.name = original_filename

        # Upload to Cloudinary (as video resource for audio)
        upload_result = cloudinary.uploader.upload(
            mp3_data, resource_type="video", folder = "my-music-web-app/data/test/"
        )

        created_at = datetime.now(timezone.utc)

        # File size from upload result or mp3_data size
        file_size = upload_result.get("bytes", len(mp3_data.getbuffer()))
        year = info.get("year") 
        track_doc = {
            "duration": duration,
            "title": title,
            "artist": artist,
            "genre": "Unknown Genre",
            "album": "Unknown Album",
            "year": None,
            "fileSize": file_size,
            "format": "mp3",
            "bitRate": None,
            "sampleRate": None,
            "originalFilename": original_filename,
            "cloudinary_url": upload_result.get("secure_url"),
            "cloudinary_id": upload_result.get("public_id"),
            "created_at": created_at,
            "like_count": 0,
            "thumbnail": thumbnail,
        }
        
        if year is not None:
           track_doc["year"] = year

        client = MongoClient(os.getenv("MONGODB_URL"))
        client.admin.command('ping')
        print("Connection established with database successfully.")
        db = client["myMusicDatabase"]
        collection = db["test"]

        doc = collection.insert_one(track_doc)
        saved_track = collection.find_one({"_id":doc.inserted_id})
        created_at_ist = saved_track["created_at"].astimezone(ZoneInfo("Asia/Kolkata"))

        # Return MongoDB document with _id as string alias
        track_doc["_id"] = str(doc.inserted_id)
        track_doc["created_at"] = created_at_ist

        return track_doc

     except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
     finally:
        if client :
           client.close()
           print("Connection closed with database.")   



class User(BaseModel):
    username : str
    email: str
    password : str

@app.post("/api/music-web-app/create/user")
async def createUser(data:User):
    client = None
    try:
       client =  MongoClient(os.getenv("MONGODB_URL"))
       client.admin.command('ping')
       print("Connection established with database successfully.")
       db = client["myMusicDatabase"]
       collection = db["user"]
       doc = collection.find_one({"email":data.email})
       if  doc :
           return {
                 "ConnectionToDatabase":"Okay",   
                 "Status" : False ,
                 "Message":"User already exists in database.",
           }
       collection_ = db["userData"]
       obj_ = {
           "email":data.email,
           "favourite_songs":[],
           "favourite_videos":[],
           "subscription":"free",
           "created_at":datetime.now()
       }
       collection_.insert_one(obj_)
       hashed_password = bcrypt.hashpw(data.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
       obj = {
           "username":data.username,
           "email":data.email,
           "password":hashed_password,
           "created_at":datetime.now(),
           "is_verified":False,
           "role":"user"
       }
       collection.insert_one(obj)
       return{
        "ConnectionToDatabase":"Okay",  
        "Status" : True ,
        "Message":"User created in database successfully."
       }
    except ConnectionFailure as e:
        return {
        "Message":"Error in connecting to database."
        }
    except Exception as e :
        return {    
        "ConnectionToDatabase":"Okay",   
        "Message":"User is not created in database.",
        "Error" : str(e)
        }
    finally:
       if client :
            client.close()
            print("Connection closed with database.")   


class UserCredential(BaseModel):
    email: str
    password : str

#login
@app.post("/api/music-web-app/login/user")
async def userLogin(data:UserCredential):
    client = None
    try:
       client =  MongoClient(os.getenv("MONGODB_URL"))
       client.admin.command('ping')
       print("Connection established with database successfully.")
       db = client["myMusicDatabase"]
       collection = db["user"]
       fetchedData = collection.find_one({"email" : data.email})
       if not fetchedData:
            return {
                "ConnectionToDatabase": "Okay",
                "Status": False,
                "Error": "User not found",
                "Message": "Login failed."
            }
       stored_hash = fetchedData.get("password", "")
       input_password = data.password
       if bcrypt.checkpw(input_password.encode('utf-8'), stored_hash.encode('utf-8')):
          return{
          "ConnectionToDatabase":"Okay",  
          "Status" : True ,
          "Message":"Login successfully."
           }
       else:
          return{
          "ConnectionToDatabase":"Okay",  
          "Status" : False ,
          "Error":"Password incorrect",
          "Message":"Login failed."
           }
       
    except ConnectionFailure as e:
        return {
        "Message":"Error in connecting to database."
        }
    except Exception as e :
        return {    
        "ConnectionToDatabase":"Okay",   
        "Message":"Something went wrong.",
        "Error" : str(e)
        }
    finally:
       if client :
            client.close()
            print("Connection closed with database.")   


@app.get("/api/music-web-app/fetch/favourite/user/song/")
async def fetchFavouriteSong(email: str = Query(...)):
    client = None
    try:
       client =  MongoClient(os.getenv("MONGODB_URL"))
       client.admin.command('ping')
       print("Connection established with database successfully.")
       db = client["myMusicDatabase"]
       collection = db["userData"]
       fetchedData = collection.find_one({"email" : email})
       if not fetchedData:
            return {
                "ConnectionToDatabase": "Okay",
                "Status": False,
                "Error": "User not found",
                "Message": "Fetch failed."
            }
       arr = fetchedData.get("favourite_songs", [])
       return{
          "ConnectionToDatabase":"Okay",  
          "Status" : True ,
          "Data" : arr,
          "Message":"Song fetched successfully."
           }
    except ConnectionFailure as e:
        return {
        "Message":"Error in connecting to database.",
        "Status":False
        }
    except Exception as e :
        return {    
        "ConnectionToDatabase":"Okay",   
        "Message":"Something went wrong.",
        "Error" : str(e),
        "Status":False
        }
    finally:
       if client :
            client.close()
            print("Connection closed with database.")   



class UserId(BaseModel):
    email: str
    song_id: str

#update favourite song
@app.post("/api/music-web-app/update/favourite/user/song/")
async def updateFavouriteSong(data:UserId):
    client = None
    try:
       client =  MongoClient(os.getenv("MONGODB_URL"))
       client.admin.command('ping')
       print("Connection established with database successfully.")
       db = client["myMusicDatabase"]
       collection = db["userData"]
       fetchedData = collection.find_one({"email" : data.email})
       if not fetchedData:
            return {
                "ConnectionToDatabase": "Okay",
                "Status": False,
                "Error": "User not found",
                "Message": "Update failed."
            }
       arr = fetchedData.get("favourite_songs", [])
       if data.song_id not in arr: 
          arr.append(data.song_id)
          collection.update_one({"email":data.email} , {"$set":{"favourite_songs" : arr}})
          return{
          "ConnectionToDatabase":"Okay",  
          "Inserted":True,
          "Deleted":False,
          "Status" : True ,
          "Message":"Song added successfully."
           }
       else :
          arr.remove(data.song_id)
          collection.update_one({"email":data.email} , {"$set":{"favourite_songs" : arr}})
          return{
          "ConnectionToDatabase":"Okay",  
          "Inserted":False,
          "Deleted":True,
          "Status" : True ,
          "Message":"Song removed successfully."
           }
    except ConnectionFailure as e:
        return {
        "Message":"Error in connecting to database.",
        "Status":False
        }
    except Exception as e :
        return {    
        "ConnectionToDatabase":"Okay",   
        "Message":"Something went wrong.",
        "Error" : str(e),
        "Status":False
        }
    finally:
       if client :
            client.close()
            print("Connection closed with database.")   


         

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
            "thumbnail":"null",
            "like_count":0,
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
            "thumbnail":"null",
            "like_count":0,
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





