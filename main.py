from datetime import datetime 
from app.models.event_task import TaskDocument, TaskStatusEnum
from app.task_manager import TaskManager
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from app.mqtt_client import MQTTClient
import uvicorn
from app.database import init_db
from fastapi import FastAPI, Depends
from app.routers import (
    event_player,
    debug,
)


client = MQTTClient()
task_creator = TaskManager(mqtt_client=client)

def get_mqtt_client() -> MQTTClient:
    return client

def get_task_creator() -> TaskManager:
    print("CALLING THE TASK CREATOR PAKSHET")
    return task_creator


app = FastAPI(
    title="Spy Game",
    description="Data Server of the Spy Game Project. Implemented using FastAPI and MongoDB.",
    on_startup=[init_db],
    swagger_ui_init_oauth={
        "clientId": "pvd-server",
        "realm": "philippine-virome-database",
        "appName": "Philippine Virome Database",
        "scopes": "openid email profile phone address",
        "usePkceWithAuthorizationCodeGrant": True
    }, 
)

async def start_mqtt_client():
    await asyncio.to_thread(client.start)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_mqtt_client())
    task_creator.run()

@app.on_event("shutdown")
async def shutdown_event():
    print("Shutting down")
    client.stop()
    task_creator.stop()

origins = [
    "https://localhost:3000",
    "https://localhost:3000/*",
    "http://localhost:3000",
    "http://localhost:3000/*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

    
app.include_router(event_player.router, prefix="")
app.include_router(debug.router, prefix="")

# Root
@app.get("/")
def root():
    return { "message": "Welcome to the Spy Game!" }


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)