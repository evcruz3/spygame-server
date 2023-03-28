from http.client import HTTPException
from app.models.event_task import ParticipantStatusEnum, TaskDocument, TaskStatusEnum
from app.models.pyObject import PyObjectId
from app.mqtt_client import MQTTClient
from fastapi import APIRouter, Depends, status as status_code, HTTPException, Request
from app.task_manager import TaskManager

from typing import List
from app.models.event_player import PlayerDocument, createPlayer
from app.models.game_event import GameEventDocument, JoiningPlayer
from datetime import datetime

router = APIRouter(
    prefix="",
    tags=["Events"],
)

@router.post("/events")
async def create_event(event_document: GameEventDocument):
    response = await GameEventDocument(**event_document.dict()).save()
    return response

# Players may only join before the event
@router.post("/events/{event_code}/tasks/{task_code}", response_model=TaskDocument)
async def join_task(event_code: str, task_code: str, player: PlayerDocument):

    task_creator = TaskManager(None)
    print("Endpoint has been called by a client")
    now = datetime.utcnow()

    event_document = await GameEventDocument.find_one({"code" : event_code, "start": {"$lt": now}})

    if event_document is not None:

        task_document = await TaskDocument.find_one({"event_code":event_code, "task_code" : task_code})

        if task_document is not None:
            if task_document.status != TaskStatusEnum.FINISHED:
                # Check if the given player is a participant for this task
                participant = None
                index = -1
                for (i, p) in enumerate(task_document.participants):
                    print("p.player vs player.id")
                    print(p.player, "vs", player.id)
                    if p.player == player.id:
                        participant = p
                        index = i
                        break

                if participant is None:
                    raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail="Player is not a participant for this task")
                else:
                    if task_document and now >= task_document.start_time and now <= task_document.join_until:
                        # If still within the window time, update status to JOINED
                        # participant.status = ParticipantStatusEnum.JOINED
                        # await task_document.update({ "$push": { "participants": { "player": participant.dict() } } })
                        # await task_document.update({"$set": {f"participants.{index}.status" : ParticipantStatusEnum.JOINED}})
                        return await task_creator.update_task_participants(task_document, index, participant.player, ParticipantStatusEnum.JOINED)
                    else:
                        # If not, update status to NOT_JOINED
                        return await task_creator.update_task_participants(task_document, index, participant.player, ParticipantStatusEnum.NOT_JOINED)
            else: 
                raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Task {task_code} has already finished")
            
        else:
            raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail=f"Task {task_code} does not exist")

    raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Event {event_code} may not exist or has not started yet")

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

@router.get("/events/{event_code}/players/{player_id}/current_task", response_model=TaskDocument)
async def get_current_task_of_player(event_code: str, player_id: str):
    now = datetime.now()
    task_document = await TaskDocument.find_one({"event_code": event_code, 
                                                 "status" : {"$ne": TaskStatusEnum.FINISHED}, 
                                                 "participants": {"$elemMatch": {"player": PyObjectId(player_id)}}, 
                                                 "start_time": {"$lt": now}, 
                                                 "end_time": {"$gt": now}
                                                 })
    return task_document

