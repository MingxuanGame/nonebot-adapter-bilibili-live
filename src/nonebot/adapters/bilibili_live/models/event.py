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
    id: int
    typ: int
    is_light: int
    ruid: int
    guard_level: GuardLevel
    score: int
    guard_icon: str
    honor_icon: str
    user_receive_count: int
    color_start: int
    color_end: int
    color_border: int
    color: int


class User(BaseModel):
    uid: int
    name: str
    face: str = ""
    open_id: str = ""
    name_color: Optional[int] = None
    is_admin: Optional[bool] = None
    special: Optional[str] = None
    medal: Optional[Medal] = None


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
    score: str
    uname: str
    rank: int
    guard_level: GuardLevel = GuardLevel.No


class RankChangeMsg(BaseModel):
    msg: str
    rank: int


class BatchComboSend(BaseModel):
    action: str
    batch_combo_id: str
    batch_combo_num: int
    gift_id: int
    gift_name: str
    gift_num: int
    uid: int
    uname: str


# class ReceiveUserInfo(BaseModel):
#     uid: int
#     uname: str


# class AnchorInfo(BaseModel):
#     uid: int
#     open_id: str = ""
#     union_id: str = ""
#     uname: str
#     uface: str


class ComboInfo(BaseModel):
    combo_base_num: int
    combo_count: int
    combo_id: str
    combo_timeout: int


class BlindGift(BaseModel):
    blind_gift_id: int
    status: bool
