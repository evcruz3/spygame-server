import os

from functools import lru_cache

from pydantic import BaseSettings

from .error import PVDError

class PVDServerSettings(BaseSettings):
    keycloak_server_url: str
    keycloak_client_id: str
    keycloak_client_secret: str
    keycloak_admin_client_secret: str
    keycloak_realm: str
    keycloak_callback_uri: str

    main_db_host: str
    main_db_port: int
    main_db_connect: bool
    main_db_name: str
    main_db_username: str
    main_db_password: str

    draft_db_host: str
    draft_db_port: int
    draft_db_connect: bool
    draft_db_name: str
    draft_db_username: str
    draft_db_password: str

class PVDServerDotenvSettings(PVDServerSettings):
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

@lru_cache()
def get_settings() -> PVDServerSettings:
    if 'PVD_SERVER_ENV' not in os.environ:
        raise PVDError('PVD Server Environment not configured!')
    else:
        environment = os.environ['PVD_SERVER_ENV']
        if environment == 'development':
            return PVDServerDotenvSettings()
        elif environment == 'production' or environment == 'testing':
            return PVDServerSettings()
        else:
            raise PVDError("Uknown PVD Server Environment '{}'!".format(environment))