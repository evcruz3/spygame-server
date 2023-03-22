from typing import Optional

from beanie import Document
from beanie.operators import Set

from pydantic import BaseModel, Field, EmailStr
from typing import List
from datetime import datetime


# Institution Profile Model Class
class GameEventBase(BaseModel):
    code: str = Field(..., description="The code of the current event")
    start: datetime = Field(..., description="The start datetime of the event")
    end: datetime = Field(..., description="The end datetime of the event")
    lives: int = Field(..., desctipion="The configured initial number of lives of the players in this event")


class GameEventDocument(Document, GameEventBase):
    pass

    class Settings:
        name = "game_events"


class JoiningPlayer(BaseModel):
    name: str = Field(..., description="The name of the player who will join the event")

# Create a new game event
async def createEvent(event_document: GameEventDocument) -> GameEventDocument:
    institution_profile = await GameEventDocument(**event_document.dict()).save()
    return institution_profile

# Get an existing event document
async def getEvent(id: str) -> GameEventDocument:
    return await GameEventDocument.get(id)

# /events/{event_code}/
# possible event notifications
# 1. New task is about to begin (details include the players chosen for the task, and the player who knows the code)
# 2. A player has just been killed (details include the player killed and its remaining lives)

# /events/{event_code}/task/{task_code}
# possible task notifications
# 1. Player has just joined the task

