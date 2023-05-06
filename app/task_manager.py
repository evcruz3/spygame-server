import asyncio
from collections import defaultdict
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

CREATE_TASK_INTERVAL = 15 #default is 300 seconds / 5 minutes
JOIN_UNTIL_TIME_DELTA_IN_MINUTES = 3 #default is 10 minutes
END_TIME_DELTA_IN_MINUTES = 3 # default is 20 minutes

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
                    {"event_code": event.code, "_id": {"$nin": list(player_ids_in_tasks)}, 'lives_left' : {"$gt": 0}, 'name': {"$ne": "VIEWER"}}
                ).to_list()
            viewers = await PlayerDocument.find(
                    {"event_code": event.code, "name": "VIEWER"}
                ).to_list()
            
            if len(available_players) < 2:
                print(f"Not enough available players to create task for event {event.code}.")
                return f"Not enough available players to create task for event {event.code}."

            # Choose a random task type
            task_type = random.choice(list(TaskTypeEnum))
            # task_type = random.choice([TaskTypeEnum.HEART])

            # Set end time depending on the task type chosen
            end_time = join_until + timedelta(seconds=30) if task_type == TaskTypeEnum.SPADE else (now + timedelta(minutes=END_TIME_DELTA_IN_MINUTES))

            # Choose 3-6 random players to join the task
            limit = max(3, len(available_players))
            num_players = limit if limit == 3 else random.randint(3, min(6, limit))
            random.shuffle(available_players)
            participant_ids = [
                {"player": available_players[i].id, "status": ParticipantStatusEnum.WAITING}
                for i in range(num_players)
            ]
            viewer_ids = [{"player": viewers[i].id, "status": ParticipantStatusEnum.WAITING}
                for i in range(len(viewers))]
            participant_ids.extend(viewer_ids)

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
                allow_action=True if task_type in [TaskTypeEnum.HEART, TaskTypeEnum.DIAMOND] else False,
                votes=[]
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
            # self.scheduler.add_job(self.end_task, 'date', run_date=task.end_time, args=[task.id])

            return task

    async def announce_task(self, task: TaskDocument):
        mqtt_topic = f"/events/{task.event_code}/tasks"
        leaders = task.participants[::2]
        # print(f"leaders: {leaders[0].player.name}, {leaders[1].player.name}")
        message = {"message" : f"A new task is about to begin\n{leaders[0].player.name}, {leaders[1].player.name} have the task code", "task_document" : task}
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
                message_body = "There may be a killer among you... This is your time to vote one out to kill by the end of round. The players/s with the most number of votes will lose 2 lives"
            elif task.type == TaskTypeEnum.SPADE:
                message_body = "Everyone's safe... for now"
                await task.update({"$set": {f"end_time" : datetime.utcnow() + timedelta(seconds=15)}})
                self.scheduler.add_job(self.end_task, 'date', run_date=task.end_time, args=[task.id])
                task = await getTask(task.id)

            for index, participant in enumerate(task.participants):
                if participant.status == ParticipantStatusEnum.JOINED:
                    message = {'message': message_body, "task_document": task}
                    
                    mqtt_topic = f"/events/{task.event_code}/players/{participant.player.id}/task"
                    
                    self.mqtt_client.publish(mqtt_topic, message)
                    
    async def end_task(self, id: any, handled: bool = False):

         # Get the updated task document
        task_document = await getTask(id)

        print("handled?: ", handled)
        # If task is not yet handled, perform necessary actions
        if handled == False:
            if task_document.type == TaskTypeEnum.HEART and task_document.status != TaskStatusEnum.FINISHED:
                now = datetime.utcnow()
                vote_counts = defaultdict(int)
                for vote in task_document.votes:
                    vote_counts[(vote.vote.id, vote.vote.name)] += 1

                try:
                    # Find the players with the highest count
                    max_count = max(vote_counts.values())
                    most_voted_players = [player for player, count in vote_counts.items() if count == max_count]

                    for (player_id, player_name) in most_voted_players:
                        # document = await PlayerDocument.find_one({"_id": participant.player})
                        player = await PlayerDocument.get(player_id)
                        await player.update({"$inc": {"lives_left": -2}})

                        mqtt_topic = f"/events/{task_document.event_code}/players/{player.id}/life"
                        message = {'message': 'You have been voted out, you lose 2 lives', "player_document" : player}
                        self.mqtt_client.publish(mqtt_topic, message)

                    await task_document.update({"$set": {"end_time": now + timedelta(seconds=15), "allow_action": False}})
                    self.scheduler.add_job(self.end_task, 'date', run_date=task_document.end_time, args=[task_document.id, True])
                    task_document = await getTask(task_document.id)

                    mqtt_topic = f"/events/{task_document.event_code}/tasks/{task_document.task_code}/state"

                    message_body = f"{', '.join([player_name for (player_id, player_name) in most_voted_players])} gained the most number of votes. They lose 2 lives"
                    message = {'message': message_body, "task_document" : task_document}

                    self.mqtt_client.publish(mqtt_topic, message)
                except ValueError:
                    await task_document.update({"$set": {"end_time": now + timedelta(seconds=15)}})
                    self.scheduler.add_job(self.end_task, 'date', run_date=task_document.end_time, args=[task_document.id, True])
                    task_document = await getTask(task_document.id)

                    mqtt_topic = f"/events/{task_document.event_code}/tasks/{task_document.task_code}/state"

                    message_body = f"Everybody abstained. Nobody loses life this round"
                    message = {'message': message_body, "task_document" : task_document}

                    self.mqtt_client.publish(mqtt_topic, message)
            else:
                # If task not manually finished by the player/s
                if task_document.status != TaskStatusEnum.FINISHED:
                    await self.update_task_state(task_document, TaskStatusEnum.FINISHED)
                    # Set task status to FINISHED
        else:
            # If task not manually finished by the player/s
            if task_document.status != TaskStatusEnum.FINISHED:
                await self.update_task_state(task_document, TaskStatusEnum.FINISHED)
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