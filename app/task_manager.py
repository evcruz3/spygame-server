import asyncio
import random
import string
from datetime import datetime, timedelta, timezone
import signal
import functools

from app.models.event_player import PlayerDocument
from app.models.event_task import TaskDocument, TaskTypeEnum, ParticipantStatusEnum, TaskStatusEnum
from app.models.game_event import GameEventDocument
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from beanie.operators import Set
from bson import json_util

# import pytz
from pytz import utc

CREATE_TASK_INTERVAL = 10 #default is 300 seconds / 5 minutes
JOIN_UNTIL_TIME_DELTA_IN_MINUTES = 0.5 #default is 10 minutes
END_TIME_DELTA_IN_MINUTES = 1 # default is 20 minutes

class TaskManager:
    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client
        # self.loop = asyncio.get_running_loop()
        self.scheduler = AsyncIOScheduler(event_loop=asyncio.get_running_loop(), timezone=utc)
        self.scheduler.start()
        self._stop_event = False

    async def create_task(self):
        # Get a random event that is currently ongoing
        now = datetime.utcnow()
        events = await GameEventDocument.find(
            {"start": {"$lt": now}, "end": {"$gt": now}}
        ).to_list()

        
        if len(events) == 0:
            print("No ongoing events found.")
            return

        for event in events:
            # Get all player ids that are not part of any task within the task's time range and of that event
            start_time = now
            end_time = now + timedelta(minutes=END_TIME_DELTA_IN_MINUTES)
            join_until = now + timedelta(minutes=JOIN_UNTIL_TIME_DELTA_IN_MINUTES)
            player_ids_in_tasks = set()
            currently_running_event_tasks = await TaskDocument.find(
                {"status": {"$ne": TaskStatusEnum.FINISHED}, "event_code": event.code}
            ).to_list()
            for task in currently_running_event_tasks:
                for participant in task.participants:
                    player_ids_in_tasks.add(participant.player)
            
            available_players = await PlayerDocument.find(
                    {"event_code": event.code, "_id": {"$nin": list(player_ids_in_tasks)}, 'lives_left' : {"$gt": 0}}
                ).to_list()
            
            if len(available_players) < 2:
                print(f"Not enough available players to create task for event {event.code}.")
                return

            # Choose a random task type
            task_type = random.choice(list(TaskTypeEnum))

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
                status=TaskStatusEnum.WAITING_FOR_PARTICIPANTS
            )
            await task.save()

            # Schedule task publication to the datetime specified in start_time
            # self.scheduler.add_job(self.announce_task, 'date', run_date=start_time, args=[result])
            # print(f"Task created: {task.dict()}")
            await self.announce_task(task)
            # Schedule penalty to those who wont be able to join and then start the task
            self.scheduler.add_job(self.start_task, 'date', run_date=task.join_until, args=[task.id])
            # End the task at the specified datetime
            self.scheduler.add_job(self.end_task, 'date', run_date=task.end_time, args=[task.id])

    async def announce_task(self, task: TaskDocument):
        mqtt_topic = f"/events/{task.event_code}/tasks"
        self.mqtt_client.publish(mqtt_topic, task.json())

    async def start_task(self, id: any):
        print(f"Starting task {id}...")

        # Get the updated task document
        task = await TaskDocument.get(id)

        # If task not manually started by the player
        if task.status == TaskStatusEnum.WAITING_FOR_PARTICIPANTS:

            # Set task status to ONGOING
            task.status = TaskStatusEnum.ONGOING
            await task.update(Set(task))

            message_body = ""

            if task.type == TaskTypeEnum.DIAMOND:
                message_body = "Killing spree! A killer may kill one of you by the end of round"
            elif task.type == TaskTypeEnum.HEART:
                message_body = "There is at least one killer among you... Vote one to kill by the end of round"
            elif task.type == TaskTypeEnum.SPADE:
                message_body = "Everyone's safe... for now"
                self.end_task(id)
            message = {'message': message_body, "task_document": task.dict()}

            # Penalize each participant that did not join
            for index, participant in enumerate(task.participants):
                if participant.status == ParticipantStatusEnum.WAITING:
                    mqtt_topic = f"/events/{task.event_code}/players/{participant.player}"

                    document = await PlayerDocument.find_one({"_id": participant.player})
                    await document.update({"$inc": {"lives_left": -1}})
                    await task.update({"$set": {f"participants.{index}.status" : ParticipantStatusEnum.NOT_JOINED}})
                    message = {'message': 'You failed to join the task, you lose 1 life', "player_document" : document.dict()}

                    self.mqtt_client.publish(mqtt_topic, json_util.dumps(message))
                else:
                    mqtt_topic = f"/events/{task.event_code}/players/{participant.player}"
                    
                    self.mqtt_client.publish(mqtt_topic, json_util.dumps(message))

    async def end_task(self, id: any):
         # Get the updated task document
        task = await TaskDocument.get(id)

        # If task not manually finished by the player/s
        if task.status != TaskStatusEnum.FINISHED:
            # Set task status to FINISHED
            task.status = TaskStatusEnum.FINISHED
            await task.update(Set(task))

    async def _run(self):
        await asyncio.sleep(5)

        try:
            while self._stop_event == False:
                await self.create_task()
                await asyncio.sleep(CREATE_TASK_INTERVAL) 
        except KeyboardInterrupt:
            print("Task Creator exited")
            self.stop()
        
    def run(self):
        print("Starting task creator")
        asyncio.get_running_loop().create_task(self._run())
        print("Task Creator started running")

    def stop(self):
        self._stop_event = True