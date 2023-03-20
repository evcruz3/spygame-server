from fastapi import APIRouter, HTTPException, Depends
from beanie.odm.operators import AddToSet, Pull
from datetime import datetime

from app.models.event_player import PlayerDocument
from app.models.event_task import TaskDocument, TaskTypeEnum, Participant, ParticipantStatusEnum

router = APIRouter()

@router.post("/events/{event_code}/tasks/{task_code}")
async def join_task(
    event_code: str, task_code: str, player: PlayerDocument
):
    task_document = await TaskDocument.find_one({"event_code":event_code, "task_code" : task_code})

    # Check if the given player is a participant for this task
    participant = None
    for p in task_document.participants:
        if p.player == player.id:
            participant = p
            await task_document.update(operators=[Pull(TaskDocument.participants, {"player": p.player})])
            break

    if participant is None:
        raise HTTPException(status_code=404, detail="Player is not a participant for this task")

    now = datetime.utcnow()
    if task_document and now >= task_document.start_time and now <= task_document.join_until:
        # If still within the window time, update status to JOINED
        participant.status = ParticipantStatusEnum.JOINED
        await task_document.update(operators=[AddToSet(TaskDocument.participants, participant.dict())])
        
        return {"message": "Player joined task successfully"}
    else:
        # If not, update status to NOT_JOINED
        participant.status = ParticipantStatusEnum.JOINED
        await task_document.update(operators=[AddToSet(TaskDocument.participants, participant.dict())])
        
        return {"message": "Player failed to join because the task is elready finished"}
