from collections import defaultdict
from http.client import HTTPException
from app.models.event_task import ParticipantStatusEnum, TaskDocument, TaskStatusEnum, TaskTypeEnum, Vote, getTask, populate_player, populate_votes
from app.models.pyObject import PyObjectId
from app.mqtt_client import MQTTClient
from fastapi import APIRouter, Depends, status as status_code, HTTPException, Request
from app.task_manager import TaskManager

from typing import List
from app.models.event_player import PlayerDocument, PlayerRoleEnum, createPlayer
from app.models.game_event import GameEventDocument, JoiningPlayer
from datetime import datetime
from asyncstdlib.builtins import map as amap, list as alist
from datetime import datetime, timedelta

import math

router = APIRouter(
    prefix="",
    tags=["Events"],
)

@router.post("/events")
async def create_event(event_document: GameEventDocument):
    response = await GameEventDocument(**event_document.dict()).save()
    return response

# Players may only join before the event
@router.post("/events/{event_code}/tasks/{task_code}/join", response_model=TaskDocument)
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
                        document = await PlayerDocument.find_one({"_id": participant.player})
                        await document.update({"$inc": {"lives_left": -1}})

                        mqtt_topic = f"/events/{task_document.event_code}/players/{participant.player}/life"
                        message = {'message': 'You failed to join the task, you lose 1 life', "player_document" : document}
                        task_creator.mqtt_client.publish(mqtt_topic, message)

                        # If not, update status to NOT_JOINED
                        return await task_creator.update_task_participants(task_document, index, participant.player, ParticipantStatusEnum.NOT_JOINED)
            else: 
                raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Task {task_code} has already finished")
            
        else:
            raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail=f"Task {task_code} does not exist")

    raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Event {event_code} may not exist or has not started yet")

# Players may only join before the event
@router.post("/events/{event_code}/tasks/{task_code}/not_join", response_model=TaskDocument)
async def not_join_task(event_code: str, task_code: str, player: PlayerDocument):

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
                    document = await PlayerDocument.find_one({"_id": participant.player})
                    await document.update({"$inc": {"lives_left": -1}})

                    mqtt_topic = f"/events/{task_document.event_code}/players/{participant.player}/life"
                    message = {'message': 'You failed to join the task, you lose 1 life', "player_document" : document}
                    task_creator.mqtt_client.publish(mqtt_topic, message)

                    return await task_creator.update_task_participants(task_document, index, participant.player, ParticipantStatusEnum.NOT_JOINED)
            else: 
                raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Task {task_code} has already finished")
            
        else:
            raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail=f"Task {task_code} does not exist")

    raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Event {event_code} may not exist or has not started yet")

@router.post("/events/{event_code}/tasks/{task_code}/no_kill", response_model=TaskDocument)
async def kill_none_in_task(event_code: str, task_code: str, player: PlayerDocument):
    task_creator = TaskManager(None)
    print("No Kill Endpoint has been called by a client")
    now = datetime.utcnow()

    event_document = await GameEventDocument.find_one({"code" : event_code, "start": {"$lt": now}})

    if event_document is not None:

        task_document = await TaskDocument.find_one({"event_code":event_code, "task_code" : task_code, "type": TaskTypeEnum.DIAMOND})

        if task_document is not None:
            if task_document.status != TaskStatusEnum.FINISHED:
                # Check if the given player is a participant for this task
                killer = None
                index = -1
                for (i, p) in enumerate(task_document.participants):
                    print("p.player vs player.id")
                    print(p.player, "vs", player.id)
                    if p.player == player.id and player.role == PlayerRoleEnum.SPY and p.status == ParticipantStatusEnum.JOINED:
                        killer = p
                        index = i
                        break

                # If caller is not part of the task
                if killer is None:
                    raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail="You are not part of this task")
                else:
                    await task_document.update({"$set": {"end_time": now + timedelta(seconds=15), "allow_action": False}})
                    task_creator.scheduler.add_job(task_creator.end_task, 'date', run_date=task_document.end_time, args=[task_document.id, True])
                    task_document = await getTask(task_document.id)

                    mqtt_topic = f"/events/{task_document.event_code}/tasks/{task_document.task_code}/state"

                    message_body = f"The killer/s are merciful this round. Everyone's safe"
                    message = {'message': message_body, "task_document" : task_document}

                    task_creator.mqtt_client.publish(mqtt_topic, message)

                    return task_document
            else: 
                raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Task {task_code} has already finished")
            
        else:
            raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail=f"Task {task_code} does not exist")

    raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Event {event_code} may not exist or has not started yet")

@router.post("/events/{event_code}/tasks/{task_code}/vote_out/{player_id}", response_model=TaskDocument)
async def vote_out(event_code: str, task_code: str, player: PlayerDocument, player_id: str):
    task_creator = TaskManager(None)
    now = datetime.utcnow()

    event_document = await GameEventDocument.find_one({"code" : event_code, "start": {"$lt": now}})

    if event_document is not None:

        task_document = await TaskDocument.find_one({"event_code":event_code, "task_code" : task_code, "type": TaskTypeEnum.HEART})

        if task_document is not None:
            if task_document.status != TaskStatusEnum.FINISHED:
                # Check if the given player is a participant for this task
                isJoined = False
                for (i, p) in enumerate(task_document.participants):
                    print("p.player vs player.id")
                    print(p.player, "vs", player.id)
                    if p.player == player.id:
                        isJoined = True
                        break

                if isJoined == False:
                    raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"You are not currently joined in this task")

                voter = None
                index = -1
                for (i, p) in enumerate(task_document.votes):
                    print("p.player vs player.id")
                    print(p.player, "vs", player.id)
                    if p.player == player.id:
                        voter = p
                        index = i
                        break

                # If player has not voted yet
                if voter is None:
                    player_voted_out = await PlayerDocument.get(PyObjectId(player_id))
                    if player_voted_out is None:
                        raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail=f"Player does not exist")
                    
                    # vote = Vote(player=player.id, vote=player_id)

                    # await task_document.update({"$set": {"end_time": now + timedelta(seconds=15), "allow_action": False}})
                    # task_creator.scheduler.add_job(task_creator.end_task, 'date', run_date=task_document.end_time, args=[task_document.id])
                    # task_document = await getTask(task_document.id)
                    await task_document.update({"$push": {"votes": {"player": player.id, "vote": player_id}}})

                    mqtt_topic = f"/events/{task_document.event_code}/tasks/{task_document.task_code}/state"
                    task_document = await getTask(task_document.id)

                    message_body = f"{player.name} voted for {player_voted_out.name}"
                    message = {'message': message_body, "task_document" : task_document}

                    task_creator.mqtt_client.publish(mqtt_topic, message)

                    # check if everyone who has joined has already voted
                    joined_participants = list(filter(lambda x: x.status == ParticipantStatusEnum.JOINED, task_document.participants))
                    # print("joined players: ")
                    # print(joined_participants)
                    all_has_voted = all(any(vote.player.id == participant.player.id for vote in task_document.votes) for participant in joined_participants)
                    # print("all has voted: ")
                    # print(all_has_voted)

                    if all_has_voted == True:
                        vote_counts = defaultdict(int)
                        for vote in task_document.votes:
                            vote_counts[(vote.vote.id, vote.vote.name)] += 1

                        # Find the players with the highest count
                        max_count = max(vote_counts.values())
                        most_voted_players = [player for player, count in vote_counts.items() if count == max_count]

                        for (player_id, player_name) in most_voted_players:
                            # document = await PlayerDocument.find_one({"_id": participant.player})
                            player = await PlayerDocument.get(player_id)
                            await player.update({"$inc": {"lives_left": -2}})

                            mqtt_topic = f"/events/{task_document.event_code}/players/{player.id}/life"
                            message = {'message': 'You have been voted out, you lose 2 lives', "player_document" : player}
                            task_creator.mqtt_client.publish(mqtt_topic, message)

                        await task_document.update({"$set": {"end_time": now + timedelta(seconds=15), "allow_action": False}})
                        task_creator.scheduler.add_job(task_creator.end_task, 'date', run_date=task_document.end_time, args=[task_document.id, True])
                        task_document = await getTask(task_document.id)

                        mqtt_topic = f"/events/{task_document.event_code}/tasks/{task_document.task_code}/state"

                        message_body = f"{', '.join([player_name for (player_id, player_name) in most_voted_players])} gained the most number of votes. They lose 2 lives"
                        message = {'message': message_body, "task_document" : task_document}

                        task_creator.mqtt_client.publish(mqtt_topic, message)

                        # return task_document
                        # # Print the result
                        # if len(most_voted_players) == 1:
                        #     print(f"{most_voted_players[0]} is the most voted player")
                        # else:
                        #     print(f"There is a tie for the most voted player between {', '.join(most_voted_players)}")

                    return task_document
                else:
                    raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"You've already voted")
            else: 
                raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Task {task_code} has already finished")
            
        else:
            raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail=f"Task {task_code} does not exist")

    raise HTTPException(status_code=status_code.HTTP_403_FORBIDDEN, detail=f"Event {event_code} may not exist or has not started yet")


@router.post("/events/{event_code}/tasks/{task_code}/kill/{player_id}", response_model=TaskDocument)
async def kill_in_task(event_code: str, task_code: str, player: PlayerDocument, player_id: str):
    task_creator = TaskManager(None)
    print("Kill Endpoint has been called by a client")
    now = datetime.utcnow()

    event_document = await GameEventDocument.find_one({"code" : event_code, "start": {"$lt": now}})

    if event_document is not None:

        task_document = await TaskDocument.find_one({"event_code":event_code, "task_code" : task_code, "type": TaskTypeEnum.DIAMOND})

        if task_document is not None:
            if task_document.status != TaskStatusEnum.FINISHED:
                # Check if the given player is a participant for this task
                killer = None
                index = -1
                for (i, p) in enumerate(task_document.participants):
                    print("p.player vs player.id")
                    print(p.player, "vs", player.id)
                    if p.player == player.id and player.role == PlayerRoleEnum.SPY and p.status == ParticipantStatusEnum.JOINED:
                        killer = p
                        index = i
                        break

                # If caller is not part of the task
                if killer is None:
                    raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail="You are not part of this task")
                else:
                    # document = await PlayerDocument.find_one({"_id": participant.player})
                    # await document.update({"$inc": {"lives_left": -1}})

                    # mqtt_topic = f"/events/{task_document.event_code}/players/{participant.player}/life"
                    # message = {'message': 'You failed to join the task, you lose 1 life', "player_document" : document}
                    # task_creator.mqtt_client.publish(mqtt_topic, message)

                    # return await task_creator.update_task_participants(task_document, index, participant.player, ParticipantStatusEnum.NOT_JOINED)
                    to_be_killed = None
                    for (i, p) in enumerate(task_document.participants):
                        print("p.player vs player.id")
                        print(p.player, p.status, "vs", player_id)
                        print("p.player == player_id: ", p.player == player_id)
                        print("p.status == ParticipantStatusEnum.JOINED: ", p.status == ParticipantStatusEnum.JOINED)
                        if str(p.player) == str(player_id) and p.status == ParticipantStatusEnum.JOINED:
                            to_be_killed = p
                            index = i
                            break

                    print("to be killed: ", to_be_killed)
                    if to_be_killed is None:
                        raise HTTPException(status_code=status_code.HTTP_404_NOT_FOUND, detail="Player you want to kill is not part of the ongoing task")
                    else:
                        document = await PlayerDocument.find_one({"_id": PyObjectId(player_id)})
                        await document.update({"$inc": {"lives_left": -2}})

                        mqtt_topic = f"/events/{task_document.event_code}/players/{player_id}/life"
                        message = {'message': 'You have just been killed by one of the people in the task, you lose 2 lives', "player_document" : document}
                        task_creator.mqtt_client.publish(mqtt_topic, message)
                        
                        await task_document.update({"$set": {"end_time": now + timedelta(seconds=15), "allow_action": False}})
                        task_creator.scheduler.add_job(task_creator.end_task, 'date', run_date=task_document.end_time, args=[task_document.id, True])
                        task_document = await getTask(task_document.id)

                        mqtt_topic = f"/events/{task_document.event_code}/tasks/{task_document.task_code}/state"

                        message_body = f"{document.name} has just been killed. {document.name} lost 2 lives"
                        message = {'message': message_body, "task_document" : task_document}

                        task_creator.mqtt_client.publish(mqtt_topic, message)

                        return task_document
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
    players = await PlayerDocument.find({'event_code': event_code, 'lives_left': {'$gt': 0}, "name" : {"$ne": "VIEWER"}}).to_list()
    active_players_size = len(players)
    expected_num_of_spies = math.ceil(0.3*active_players_size)
    current_num_of_spies = len([p for p in players if p.role == PlayerRoleEnum.SPY])
    player = None
    if player_document.name == "VIEWER":
        player = PlayerDocument(event_code=event_code, name=player_document.name, lives_left=event_document.lives, state="", role=PlayerRoleEnum.NOT_SET)
    elif current_num_of_spies != expected_num_of_spies:
        player = PlayerDocument(event_code=event_code, name=player_document.name, lives_left=event_document.lives, state="", role=PlayerRoleEnum.SPY)
    else:
        player = PlayerDocument(event_code=event_code, name=player_document.name, lives_left=event_document.lives, state="", role=PlayerRoleEnum.ORDINARY)
    response = await createPlayer(player)
    return response

@router.get("/events/{event_code}/players/{player_id}/current_task", response_model=TaskDocument)
async def get_current_task_of_player(event_code: str, player_id: str):
    now = datetime.utcnow()
    task_document = await TaskDocument.find_one({"event_code": event_code, 
                                                 "status" : {"$ne": TaskStatusEnum.FINISHED}, 
                                                 "participants": {"$elemMatch": {"player": PyObjectId(player_id)}}, 
                                                 "start_time": {"$lt": now}, 
                                                 "end_time": {"$gt": now}
                                                 })
    if task_document is not None:
        task_document.participants = await alist(amap(populate_player, task_document.participants))
        task_document.votes = await alist(amap(populate_votes, task_document.votes))
    return task_document

