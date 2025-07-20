from __future__ import annotations

from pydantic import BaseModel


class Game(BaseModel):
    seq: int = 0
    code: str
    game_id: str
    room_id: int
    uname: str
    uface: str
    open_id: str
    union_id: str
