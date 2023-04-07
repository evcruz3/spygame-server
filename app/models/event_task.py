from enum import Enum
from typing import Optional

from beanie import Document
from beanie.operators import Set

from pydantic import BaseModel, Field, EmailStr
from typing import List
from datetime import datetime
from app.models.pyObject import PyObjectId
from app.models.event_player import PlayerDocument
from typing import List, Optional, Set, Union
from asyncstdlib.builtins import map as amap, list as alist



class TaskTypeEnum(str, Enum):
    # CLUBS = "clubs" # Team Task
    SPADE = "spade" # Everyone's safe... for now
    HEART = "heart" # There is a killer among you... Discuss and vote one to kill by the end of round
    DIAMOND = "diamond" # Watch out! A killer may kill one of you by the end of round

class ParticipantStatusEnum(str, Enum):
    WAITING = "waiting" # waiting for the player to join the task
    JOINED = "joined" # the player has joined the task
    NOT_JOINED = "not joined" # the player was not able to join the task

class TaskStatusEnum(str, Enum):
    WAITING_FOR_PARTICIPANTS = "waiting for participants"
    ONGOING = "ongoing"
    FINISHED = "finished"

class Participant(BaseModel):
    player: Union[PlayerDocument, PyObjectId] = Field(..., description="The player's id/profile")
    status: ParticipantStatusEnum = Field(..., description="the state of the player with respect to the task")

class TaskBase(BaseModel):
    event_code: str = Field(..., description="The event code the user is part of")
    name: str = Field(..., description="The name of the the task")
    type: TaskTypeEnum = Field(..., description="The type of the task")
    participants: List[Participant] = Field(..., descrption="The joined players")
    start_time: datetime = Field(..., description="The datetime the task shall commence")
    end_time: datetime = Field(..., description="The datetime the task shall end")
    task_code: str = Field(..., description="The task code")
    join_until: datetime = Field(..., description="The datetime the participants must join the task")
    status: TaskStatusEnum = Field(..., description="The current state of the task")
    allow_kill: bool = Field(..., description="Allow kill, field used by diamond task, default to True")

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
    task_document = await TaskDocument.get(id)
    task_document.participants = await alist(amap(populate_player, task_document.participants))

    return task_document
    

async def populate_player(participant: Participant):
    participant.player = await PlayerDocument.get(PyObjectId(participant.player))
    return participant
