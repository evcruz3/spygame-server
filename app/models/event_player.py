from typing import Optional

from beanie import Document
from beanie.operators import Set

from pydantic import BaseModel, Field, EmailStr
from typing import List
from app.models.date_deleted import DateDeleted
from datetime import datetime


# Institution Profile Model Class
class PlayerBase(BaseModel):
    event_code: str = Field(..., description="The event code the user is part of")
    name: str = Field(..., description="The name of the the player")
    lives_left: int = Field(..., description="Remaining number of lives left")
    state: str = Field(..., description="State of the player")

class PlayerDocument(Document, PlayerBase):
    pass

    class Settings:
        name = "players"

# Create a new game event
async def createPlayer(player_document: PlayerDocument) -> PlayerDocument:
    player_documente = await PlayerDocument(**player_document.dict()).save()
    return player_documente

# Get an existing event document
async def getPlayer(id: str) -> PlayerDocument:
    return await PlayerDocument.get(id)
