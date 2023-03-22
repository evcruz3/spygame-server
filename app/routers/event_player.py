from http.client import HTTPException
from app.models.event_task import ParticipantStatusEnum, TaskDocument, TaskStatusEnum
from app.models.pyObject import PyObjectId
from fastapi import APIRouter
from typing import List
from app.models.event_player import PlayerDocument, createPlayer
from app.models.game_event import GameEventDocument, JoiningPlayer
from datetime import datetime
from beanie.odm.operators.update.array import AddToSet, Pull


router = APIRouter()

@router.post("/events")
async def create_event(event_document: GameEventDocument):
    response = await GameEventDocument(**event_document.dict()).save()
    return response

@router.post("/events/{event_code}/tasks/{task_code}")
async def join_task(event_code: str, task_code: str, player: PlayerDocument):
    now = datetime.utcnow()

    event_document = await GameEventDocument.find_one({"event_code" : event_code, "start": {"$lt": now}})

    if event_document is not None:

        task_document = await TaskDocument.find_one({"event_code":event_code, "task_code" : task_code})

        # Check if the given player is a participant for this task
        participant = None
        for p in task_document.participants:
            if p.player == player.id:
                participant = p
                break

        if participant is None:
            raise HTTPException(status_code=404, detail="Player is not a participant for this task")
        else:
            await task_document.update(operators=[Pull(TaskDocument.participants, {"player": participant.player})])

        if task_document and now >= task_document.start_time and now <= task_document.join_until:
            # If still within the window time, update status to JOINED
            participant.status = ParticipantStatusEnum.JOINED
            await task_document.update(operators=[AddToSet(TaskDocument.participants, participant.dict())])
            
            return {"message": "Player joined task successfully"}
        else:
            # If not, update status to NOT_JOINED
            participant.status = ParticipantStatusEnum.NOT_JOINED
            await task_document.update(operators=[AddToSet(TaskDocument.participants, participant.dict())])
            
            return {"message": "Player failed to join because the task is elready finished"}
    raise HTTPException(status_code=403, detail="Event may be gone or already ongoing")

@router.get("/events/{event_code}/players", response_model=List[PlayerDocument])
async def get_event_players(event_code: str):
    event_players = await PlayerDocument.find({"event_code": event_code})
    return event_players

@router.get("/events/{event_code}/players/{player_id}", response_model=PlayerDocument)
async def get_event_player_info(event_code: str, player_id: str):
    player = await PlayerDocument.find_one({"event_code": event_code, "_id": PyObjectId(player_id)})
    return player

@router.post("/events/{event_code}/players")
async def join_event(event_code: str, player_document: JoiningPlayer):
    event_document = await GameEventDocument.find_one({"code": event_code})
    player = PlayerDocument(event_code=event_code, name=player_document.name, lives_left=event_document.lives, state="")
    response = await createPlayer(player)
    return response

@router.get("/events/{event_code}/players/{player_id}/current_task")
async def get_current_task_of_player(event_code: str, player_id: str):
    now = datetime.now()
    task_document = await TaskDocument.find_one({"event_code": event_code, 
                                                 "status" : {"$ne": TaskStatusEnum.FINISHED}, 
                                                 "participants": {"$elemMatch": {"player": PyObjectId(player_id)}}, 
                                                 "start_time": {"$lt": now}, 
                                                 "end_time": {"$gt": now}
                                                 })
    return task_document

