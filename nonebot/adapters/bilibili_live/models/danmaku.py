from __future__ import annotations

from enum import IntEnum
from typing import Optional

from pydantic import BaseModel


class SenderBase(BaseModel):
    face: str
    is_mystery: bool
    name: str
    name_color: int


class GuardLevel(IntEnum):
    """
    1: 总督
    2: 提督
    3: 舰长
    """

    No = 0
    Guard1 = 1
    Guard2 = 2
    Guard3 = 3


class Medal(BaseModel):
    name: str
    level: int
    color_start: int
    color_end: int
    color_border: int
    color: int
    id: int
    typ: int
    is_light: int
    ruid: int
    guard_level: GuardLevel
    score: int
    guard_icon: str
    honor_icon: str
    user_receive_count: int


class Sender(BaseModel):
    base: SenderBase
    uid: int
    medal: Optional[Medal]
