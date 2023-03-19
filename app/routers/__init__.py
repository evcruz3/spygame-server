from pydantic import BaseModel

class PVDResponseMessage(BaseModel):
    message: str