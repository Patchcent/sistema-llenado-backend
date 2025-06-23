from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from dotenv import load_dotenv


import os

app = FastAPI()
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["water_system"]
status_collection = db["status"]
alerts_collection = db["alerts"]

class Status(BaseModel):
    tinaco_level: str
    cisterna_level: str
    bomba: bool

class Alert(BaseModel):
    message: str

@app.get("/")
def root():
    return {"message": "Sistema de llenado automático activo"}

@app.get("/status")
def get_status():
    status = status_collection.find_one(sort=[("_id", -1)])
    if status:
        status["_id"] = str(status["_id"])
        return status
    raise HTTPException(status_code=404, detail="No hay estado registrado")

@app.post("/simulate")
def simulate_status(status: Status):
    result = status_collection.insert_one(status.dict())
    return {"inserted_id": str(result.inserted_id)}

@app.post("/alert")
def create_alert(alert: Alert):
    result = alerts_collection.insert_one(alert.dict())
    return {"inserted_id": str(result.inserted_id)}
