from __future__ import annotations

from enum import IntEnum
from typing import Any, Optional

from nonebot.compat import field_validator

from pydantic import BaseModel


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
    uid: int
    face: str
    name: str
    name_color: int
    medal: Optional[Medal]


class SpecialGift(BaseModel):
    action: str
    content: str
    has_join: bool
    id: str
    num: int
    storm_gif: str
    time: int

    @field_validator("has_join", mode="before")
    @classmethod
    def validate(cls, value: Any) -> Any:
        return bool(value)


class Rank(BaseModel):
    uid: int
    face: str
    score: int
    uname: str
    rank: int
    guard_level: GuardLevel


class RankChangeMsg(BaseModel):
    msg: str
    rank: int
