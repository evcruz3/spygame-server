from app.models.game_event import GameEventDocument
from app.models.event_player import PlayerDocument
from app.models.event_task import TaskDocument
import motor.motor_asyncio
from beanie import init_beanie

from app.config import get_settings


settings = get_settings()

async def init_db():
    # Database Settings
    db_client = motor.motor_asyncio.AsyncIOMotorClient(
    host = settings.main_db_host,
    port = settings.main_db_port,
    username = settings.main_db_username,
    password = settings.main_db_password,
    connect = settings.main_db_connect
    )

    await init_beanie(database=db_client[settings.main_db_name], document_models=[
        GameEventDocument,
        PlayerDocument,
        TaskDocument
    ])
