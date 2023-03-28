from app.models.event_task import TaskDocument, TaskStatusEnum
from app.task_manager import TaskManager
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

task_creator = TaskManager(None)


@router.get("/trigger_create_task")
async def trigger_create_task():
    # response = await GameEventDocument(**event_document.dict()).save()
    # return response
    return await task_creator.create_task()

@router.get("/trigger_start_task")
async def trigger_start_task():
    now = datetime.utcnow()
    event_code = "KIKO"
    event_task = await TaskDocument.find_one(
                {"$and": [{"status": TaskStatusEnum.WAITING_FOR_PARTICIPANTS}, {"start_time": {"$lt": now}, "end_time": {"$gt": now}}], "event_code": event_code}
            )
    if event_task is not None:
        return await task_creator.start_task(event_task.id)
    else:
        return "No available task to start"

@router.get("/trigger_end_task")
async def trigger_end_task():
    now = datetime.utcnow()
    event_code = "KIKO"
    running_event_task = await TaskDocument.find_one(
                {"$and": [{"status": TaskStatusEnum.ONGOING}, {"start_time": {"$lt": now}, "end_time": {"$gt": now}}], "event_code": event_code}
            )
    if running_event_task is not None:
        return await task_creator.end_task(running_event_task.id)
    else:
        return "No running task to end"