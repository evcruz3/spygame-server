from enum import Enum
from typing import Optional

from beanie import Document
from beanie.operators import Set

from pydantic import BaseModel, Field, EmailStr
from typing import List
from app.models.date_deleted import DateDeleted
from datetime import datetime
from ..models.pyObject import PyObjectId
from ..models.event_player import PlayerDocument
from typing import List, Optional, Set, Union


class TaskTypeEnum(Enum):
    # CLUBS = "clubs" # Team Task
    SPADE = "spade" # Everyone's safe
    HEART = "heart" # Reveal if there's at least one killer
    DIAMOND = "diamond" # Anonymous killer kills

class ParticipantStatus(Enum):
    WAITING = "waiting" # waiting for the player to join the task
    JOINED = "joined" # the player has joined the task
    NOT_JOINED = "not joined" # the player was not able to joined

class Participant(BaseModel):
    player: Union[PlayerDocument, PyObjectId] = Field(..., description="The player's id/profile")
    status: ParticipantStatus = Field(..., description="the state of the player with respect to the task")

class TaskBase(BaseModel):
    event_code: str = Field(..., description="The event code the user is part of")
    name: str = Field(..., description="The name of the the task")
    type: TaskTypeEnum = Field(..., description="The type of the task")
    players: List[Participant] = Field(..., descrption="The joined players")
    start_time: datetime = Field(..., description="The datetime the task shall commence")
    end_time: datetime = Field(..., description="The datetime the task shall end")
    task_code: str = Field(..., description="The task code")

class TaskDocument(Document, TaskBase):
    pass

    class Settings:
        name = "tasks"

# Create a new game event
async def createTask(task_document: TaskDocument) -> TaskDocument:
    institution_profile = await TaskDocument(**task_document.dict()).save()
    return institution_profile

# Get an existing event document
async def getTask(id: str) -> TaskDocument:
    return await TaskDocument.get(id)

