from typing import List
from pydantic import validator

class UniqueList(List):
    @validator('', pre=True)
    def _validate_unique(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('List elements must be unique')
        return value