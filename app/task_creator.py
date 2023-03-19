import random
import string
import threading
import time
from datetime import datetime, timedelta
from typing import List

from models.event_player import PlayerDocument
from models.event_task import TaskDocument, TaskTypeEnum, ParticipantStatus
from models.game_event import GameEventDocument

class TaskCreator:
    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client

    def create_task(self):
        # Get a random event that is currently ongoing
        now = datetime.utcnow()
        event = GameEventDocument.find_one(
            {"start": {"$lt": now}, "end": {"$gt": now}}
        )
        if not event:
            print("No ongoing events found.")
            return

        # Get all player ids that are not part of any task within the task's time range and of that event
        start_time = now
        end_time = now + timedelta(minutes=20)
        player_ids_in_tasks = set()
        currently_running_event_tasks = TaskDocument.find(
            {"start_time": {"$lt": end_time}, "end_time": {"$gt": start_time}, "event_code": event["code"]}
        )
        for task in currently_running_event_tasks:
            for participant in task["players"]:
                player_ids_in_tasks.add(participant["player"])

        available_players = list(
            PlayerDocument.find(
                {"event_code": event["code"], "_id": {"$nin": list(player_ids_in_tasks)}},
                {"_id": 1},
            )
        )
        if len(available_players) < 2:
            print(f"Not enough available players to create task for event {event.code}.")
            return

        # Choose a random task type
        task_type = random.choice(list(TaskTypeEnum))

        # Choose 2-6 random players to join the task
        num_players = random.randint(2, 6)
        random.shuffle(available_players)
        participant_ids = [
            {"player": available_players[i]["_id"], "status": ParticipantStatus.WAITING}
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
            players=participant_ids,
            start_time=start_time,
            end_time=end_time,
            task_code=task_code
        )
        task.save()
        print(f"Task created: {task.dict()}")
        mqtt_topic = f"/events/{event.code}/tasks"
        self.mqtt_client.publish(mqtt_topic, task.json())

    def _run(self):
        while True:
            self.create_task()
            time.sleep(300)  # Wait 5 minutes

    def run(self):
        creator_thread = threading.Thread(target=self._run)
        creator_thread.start()

