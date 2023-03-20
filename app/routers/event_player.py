from fastapi import APIRouter
from typing import List
from app.models.event_player import PlayerDocument

router = APIRouter()

@router.get("/events/{event_code}/players", response_model=List[PlayerDocument])
async def get_event_players(event_code: str):
    event_players = await PlayerDocument.find({"event_code": event_code})
    return event_players

@router.get("/events/{event_code}/players/{player_name}", response_model=PlayerDocument)
async def get_player(event_code: str, player_name: str):
    player = await PlayerDocument.find_one({"event_code": event_code, "name": player_name})
    return player

