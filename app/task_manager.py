import asyncio
import random
import string
from app.models.pyObject import PyObjectId

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from beanie.operators import Set
# from bson import json_util
import json
from asyncstdlib.builtins import map as amap, list as alist


from datetime import datetime, timedelta
from app.models.event_player import PlayerDocument
from app.models.event_task import TaskDocument, TaskTypeEnum, ParticipantStatusEnum, TaskStatusEnum, getTask, populate_player
from app.models.game_event import GameEventDocument

# import pytz
from pytz import utc

CREATE_TASK_INTERVAL = 300 #default is 300 seconds / 5 minutes
JOIN_UNTIL_TIME_DELTA_IN_MINUTES = 5 #default is 10 minutes
END_TIME_DELTA_IN_MINUTES = 10 # default is 20 minutes

class TaskManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            return cls._instance
        else:
            return cls._instance

    def __init__(self, mqtt_client):
        if getattr(self, 'mqtt_client', None) is None:
            print("TaskManager initialized")
            self.mqtt_client = mqtt_client
            # self.loop = asyncio.get_running_loop()
            # self.scheduler = AsyncIOScheduler(event_loop=asyncio.get_running_loop(), timezone=utc)
            # self.scheduler.start()
            self._stop_event = False

    async def create_task(self):
        # Get a random event that is currently ongoing
        if hasattr(self, 'scheduler') == False:
            self.scheduler = AsyncIOScheduler(event_loop=asyncio.get_running_loop(), timezone=utc)
            self.scheduler.start()
        now = datetime.utcnow()
        events = await GameEventDocument.find(
            {"start": {"$lt": now}, "end": {"$gt": now}}
        ).to_list()

        
        if len(events) == 0:
            print("No ongoing events found.")
            return "No ongoing events found"

        for event in events:
            # Get all player ids that are not part of any task within the task's time range and of that event
            start_time = now
            join_until = now + timedelta(minutes=JOIN_UNTIL_TIME_DELTA_IN_MINUTES)
            player_ids_in_tasks = set()
            currently_running_event_tasks = await TaskDocument.find(
                {"$and": [{"status": {"$ne": TaskStatusEnum.FINISHED}}, {"start_time": {"$lt": now}, "end_time": {"$gt": now}}], "event_code": event.code}
            ).to_list()

            if(len(currently_running_event_tasks) > 0):
                print("For now, only allow one task at a time")
                return "For now, only allow one task at a time"

            for task in currently_running_event_tasks:
                for participant in task.participants:
                    player_ids_in_tasks.add(participant.player.id)
                    
            
            available_players = await PlayerDocument.find(
                    {"event_code": event.code, "_id": {"$nin": list(player_ids_in_tasks)}, 'lives_left' : {"$gt": 0}}
                ).to_list()
            
            if len(available_players) < 2:
                print(f"Not enough available players to create task for event {event.code}.")
                return f"Not enough available players to create task for event {event.code}."

            # Choose a random task type
            # task_type = random.choice(list(TaskTypeEnum))
            task_type = random.choice([TaskTypeEnum.DIAMOND, TaskTypeEnum.SPADE])

            # Set end time depending on the task type chosen
            end_time = join_until + timedelta(seconds=30) if task_type == TaskTypeEnum.SPADE else now + timedelta(minutes=END_TIME_DELTA_IN_MINUTES)

            # Choose 2-6 random players to join the task
            num_players = random.randint(2, min(6, len(available_players)))
            random.shuffle(available_players)
            participant_ids = [
                {"player": available_players[i].id, "status": ParticipantStatusEnum.WAITING}
                for i in range(num_players)
            ]

            # Generate random task code
            letters = string.ascii_uppercase
            task_code = ''.join(random.choice(letters) for _ in range(4))

            # Create the task document
            task = TaskDocument(
                event_code=event.code,
                name=f"{task_type.value} task",
                type=task_type,
                participants=participant_ids,
                start_time=start_time,
                end_time=end_time,
                task_code=task_code,
                join_until=join_until,
                status=TaskStatusEnum.WAITING_FOR_PARTICIPANTS,
                allow_kill=True if task_type == TaskTypeEnum.DIAMOND else False
            )
            await task.save()
            task = await getTask(task.id)

            # Schedule task publication to the datetime specified in start_time
            # self.scheduler.add_job(self.announce_task, 'date', run_date=start_time, args=[result])
            # print(f"Task created: {task.dict()}")
            await self.announce_task(task)
            # Schedule penalty to those who wont be able to join and then start the task
            self.scheduler.add_job(self.start_task, 'date', run_date=task.join_until, args=[task.id])
            # End the task at the specified datetime
            self.scheduler.add_job(self.end_task, 'date', run_date=task.end_time, args=[task.id])

            return task

    async def announce_task(self, task: TaskDocument):
        mqtt_topic = f"/events/{task.event_code}/tasks"
        message = {"message" : "A new task is about to start", "task_document" : task}
        self.mqtt_client.publish(mqtt_topic, message)

    async def start_task(self, id: any):
        print(f"Starting task {id}...")

        # Get the updated task document
        task = await getTask(id)

        # If task not manually started by the player
        if task.status == TaskStatusEnum.WAITING_FOR_PARTICIPANTS:

            # Set task status to ONGOING
            await self.update_task_state(task, TaskStatusEnum.ONGOING)

            # Penalize each participant that did not join
            for index, participant in enumerate(task.participants):
                if participant.status == ParticipantStatusEnum.WAITING:
                    document = await PlayerDocument.find_one({"_id": participant.player.id})
                    await document.update({"$inc": {"lives_left": -1}})

                    mqtt_topic = f"/events/{task.event_code}/players/{participant.player.id}/life"
                    message = {'message': 'You failed to join the task, you lose 1 life', "player_document" : document}
                    self.mqtt_client.publish(mqtt_topic, message)

                    await self.update_task_participants(task, index, participant.player.id, ParticipantStatusEnum.NOT_JOINED)

            message_body = ""

            if task.type == TaskTypeEnum.DIAMOND:
                message_body = "Killing spree! A killer may kill one of you by the end of round"
            elif task.type == TaskTypeEnum.HEART:
                message_body = "There is at least one killer among you... Vote one to kill by the end of round"
            elif task.type == TaskTypeEnum.SPADE:
                message_body = "Everyone's safe... for now"
                await task.update({"$set": {f"end_time" : datetime.utcnow() + timedelta(seconds=30)}})
                self.scheduler.add_job(self.end_task, 'date', run_date=task.end_time, args=[task.id])
                task = await getTask(task.id)

            for index, participant in enumerate(task.participants):
                if participant.status == ParticipantStatusEnum.JOINED:
                    message = {'message': message_body, "task_document": task}
                    
                    mqtt_topic = f"/events/{task.event_code}/players/{participant.player.id}/task"
                    
                    self.mqtt_client.publish(mqtt_topic, message)
                    
    async def end_task(self, id: any):
         # Get the updated task document
        task = await getTask(id)

        # If task not manually finished by the player/s
        if task.status != TaskStatusEnum.FINISHED:
            await self.update_task_state(task, TaskStatusEnum.FINISHED)
            # Set task status to FINISHED

    async def update_task_participants(self, task: TaskDocument, participant_index: int, player_id: PyObjectId, status: ParticipantStatusEnum):
        player_document = await PlayerDocument.get(player_id)

        await task.update({"$set": {f"participants.{participant_index}.status" : status}})
        task.participants = await alist(amap(populate_player, task.participants))

        mqtt_topic = f"/events/{task.event_code}/tasks/{task.task_code}/participants"

        message_body = f"{player_document.name} joined the task" if status == ParticipantStatusEnum.JOINED else f"{player_document.name} did not join the task"
        message = {'message': message_body, "task_document" : task}

        self.mqtt_client.publish(mqtt_topic, message)

        start_task = True
        for participant in task.participants:
            if participant.status == ParticipantStatusEnum.WAITING:
                start_task = False 
                break

        if start_task == True:
            await self.start_task(task.id)
            
            
    async def update_task_state(self, task: TaskDocument, status: TaskStatusEnum):
        # task.status = status
        await task.update({"$set": {"status" : status}})
        task.participants = await alist(amap(populate_player, task.participants))


        mqtt_topic = f"/events/{task.event_code}/tasks/{task.task_code}/state"
        message_body = ""
        if status == TaskStatusEnum.WAITING_FOR_PARTICIPANTS:
            message_body = f"Task {task.name} is waiting for participants to join"
        elif status == TaskStatusEnum.ONGOING:
            message_body = f"Task {task.name} has started"
        elif status == TaskStatusEnum.FINISHED:
            message_body = f"Task {task.name} has finished"
        message = {'message': message_body, "task_document": task}
        self.mqtt_client.publish(mqtt_topic, message)

    async def _run(self):
        await asyncio.sleep(5)
        while self._stop_event == False:
            await self.create_task()
            await asyncio.sleep(CREATE_TASK_INTERVAL) 
        
    def run(self):
        print("Starting task creator")
        self.scheduler = AsyncIOScheduler(event_loop=asyncio.get_running_loop(), timezone=utc)
        self.scheduler.start()
        asyncio.get_event_loop().create_task(self._run())
        print("Task Creator started running")

    def stop(self):
        self._stop_event = True

    def __call__(self, mqtt_client):
        print("IDK WHATS HAPPENING")
        return self