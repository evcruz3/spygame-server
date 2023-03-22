from fastapi import APIRouter
from typing import List
from app.models.event_player import PlayerDocument, createPlayer
from app.models.game_event import GameEventDocument

router = APIRouter()

@router.get("/events/{event_code}/players", response_model=List[PlayerDocument])
async def get_event_players(event_code: str):
    event_players = await PlayerDocument.find({"event_code": event_code})
    return event_players

@router.get("/events/{event_code}/players/{player_name}", response_model=PlayerDocument)
async def get_player(event_code: str, player_name: str):
    player = await PlayerDocument.find_one({"event_code": event_code, "name": player_name})
    return player

@router.post("/events/{event_code}/players")
async def join_event(event_code: str, player_document: PlayerDocument):
    event_document = await GameEventDocument.find_one({"code": event_code})
    player = PlayerDocument(event_code=event_code, name=player_document.name, lives_left=event_document.lives, state="")
    response = await createPlayer(player)
    return response