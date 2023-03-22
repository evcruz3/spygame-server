import asyncio
from app.mqtt_client import MQTTClient
from app.task_creator import TaskManager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .auth import idp

from .routers import (
    event_player,
    event_task
)

import logging

logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

origins = [
    "https://localhost:3000",
    "https://localhost:3000/*",
    "http://localhost:3000",
    "http://localhost:3000/*"
]

app = FastAPI(
    title="Spy Game",
    description="Data Server of the Spy Game Project. Implemented using FastAPI and MongoDB.",
    on_startup=[init_db],
    swagger_ui_init_oauth={
        "clientId": "pvd-server",
        "realm": "philippine-virome-database",
        "appName": "Spy Game",
        "scopes": "openid email profile phone address",
        "usePkceWithAuthorizationCodeGrant": True
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

idp.add_swagger_config(app)

# Root
@app.get("/")
def root():
    return { "message": "Welcome to the Spy Game!" }

app.include_router(event_task.router)
app.include_router(event_player.router)

client = MQTTClient()
task_creator = TaskManager(client)

client.start()
task_creator.run()