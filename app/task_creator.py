import random
import string
import threading
import time
from datetime import datetime, timedelta
from typing import List

from models.event_player import PlayerDocument
from models.event_task import TaskDocument, TaskTypeEnum, ParticipantStatusEnum, TaskStatusEnum
from models.game_event import GameEventDocument
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from beanie import UpdateOne

class TaskCreator:
    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client

    async def create_task(self):
        # Get a random event that is currently ongoing
        now = datetime.utcnow()
        events = GameEventDocument.find(
            {"start": {"$lt": now}, "end": {"$gt": now}}
        ).toList()
        # if not event:
        #     print("No ongoing events found.")
        #     return
        
        for event in events:
            # Get all player ids that are not part of any task within the task's time range and of that event
            start_time = now
            end_time = now + timedelta(minutes=20)
            join_until = now + timedelta(minutes=10)
            player_ids_in_tasks = set()
            currently_running_event_tasks = TaskDocument.find(
                {"start_time": {"$lt": end_time}, "end_time": {"$gt": start_time}, "event_code": event["code"]}
            )
            for task in currently_running_event_tasks:
                for participant in task["participants"]:
                    player_ids_in_tasks.add(participant["player"])

            available_players = list(
                PlayerDocument.find(
                    {"event_code": event["code"], "_id": {"$nin": list(player_ids_in_tasks)}, 'lives_left' : {"$gt": 0}},
                    {"_id": 1},
                )
            )
            if len(available_players) < 2:
                print(f"Not enough available players to create task for event {event.code}.")
                return

            # Choose a random task type
            task_type = random.choice(list(TaskTypeEnum))

            # Choose 2-6 random players to join the task
            num_players = random.randint(2, min(6, len(available_players)))
            random.shuffle(available_players)
            participant_ids = [
                {"player": available_players[i]["_id"], "status": ParticipantStatusEnum.WAITING}
                for i in range(num_players)
            ]

            # Generate random task code
            letters = string.ascii_uppercase
            task_code = ''.join(random.choice(letters) for _ in range(4))

            # Create the task document
            task = TaskDocument(
                event_code=event["code"],
                name=f"{task_type.value} task",
                type=task_type,
                participants=participant_ids,
                start_time=start_time,
                end_time=end_time,
                task_code=task_code,
                join_until=join_until,
                status=TaskStatusEnum.WAITING_FOR_PLAYERS
            )
            result = await task.save()

            # Schedule task publication to the datetime specified in start_time
            self.scheduler.add_job(self.announce_task, 'date', run_date=start_time, args=[result])
            # Schedule penalty to those who wont be able to join and then start the task
            self.scheduler.add_job(self.start_task, 'date', run_date=task.join_until, args=[task._id])
            # End the task at the specified datetime
            self.scheduler.add_job(self.end_task, 'date', run_date=task.end_time, args=[task._id])

            print(f"Task created: {task.dict()}")
            mqtt_topic = f"/events/{event.code}/tasks"
            self.mqtt_client.publish(mqtt_topic, task.json())

    async def announce_task(self, task: TaskDocument):
        mqtt_topic = f"/events/{task.event_code}/tasks"
        self.mqtt_client.publish(mqtt_topic, task.json())

    async def start_task(self, id: any):
        # Get the updated task document
        task = await TaskDocument.get(task._id)

        # If task not manually started by the player
        if task.status == TaskStatusEnum.WAITING_FOR_PARTICIPANTS:

            # Set task status to ONGOING
            task.status = TaskStatusEnum.ONGOING
            task = await task.update(**task.dict())

            message_body = ""

            if task.type == TaskTypeEnum.DIAMOND:
                message_body = "Killing spree! A killer may kill one of you by the end of round"
            elif task.type == TaskTypeEnum.HEART:
                message_body = "There is at least one killer among you... Vote one to kill by the end of round"
            elif task.type == TaskTypeEnum.SPADE:
                message_body = "Everyone's safe... for now"
                self.end_task(id)
            message = {'message': message_body, "task_document": task.json()}

            # Penalize each participant that did not join
            for participant in task.participants:
                if participant.status == ParticipantStatusEnum.WAITING:
                    mqtt_topic = f"/events/{task.event_code}/players/{participant.player}"
                    update_operation = UpdateOne(
                        {"_id": participant.player},
                        {"$inc": {"lives_left": -1}, "status" : ParticipantStatusEnum.NOT_JOINED}
                    )

                    document = await PlayerDocument.update_one(update_operation)
                    message = {'message': 'You failed to join the task, you lose 1 life', "player_document" : document.json()}

                    self.mqtt_client.publish(mqtt_topic, message)
                else:
                    mqtt_topic = f"/events/{task.event_code}/players/{participant.player}"
                    
                    self.mqtt_client.publish(mqtt_topic, message)

    async def end_task(self, id: any):
         # Get the updated task document
        task = await TaskDocument.get(task._id)

        # If task not manually finished by the player/s
        if task.status == TaskStatusEnum.ONGOING:

            # Set task status to FINISHED
            task.status = TaskStatusEnum.FINISHED
            await task.update(**task.dict())

    def _run(self):
        while True:
            self.create_task()
            time.sleep(300)  # Wait 5 minutes

    def run(self):
        creator_thread = threading.Thread(target=self._run)
        creator_thread.start()

