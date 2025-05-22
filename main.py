from fastapi import FastAPI , File , UploadFile , Form
from dotenv import load_dotenv
import os
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import cloudinary
import cloudinary.uploader
import uvicorn

load_dotenv()
app = FastAPI()
#Cloudinary config
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET_KEY")
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


#For complaint registering
@app.post("/api/register/complaint/student")
async def complainRegister(
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
        folder = f"python_fastapi_server/data/assets/{email}"
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
            "description":description,
            "image_url":response.get("secure_url"),
            "public_id":response.get("public_id")
       })
       return{
        "Message": "Student complain register successfully.",
        "_id": str(doc.inserted_id),
        "fullname": fullname ,
        "email":email,
        "title":title,
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

#if __name__ == "__main__":
#    uvicorn.run("main:app", port=5000, log_level="info")





