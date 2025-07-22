from __future__ import annotations

from enum import IntEnum
from typing import Any, Optional, Union

from nonebot.compat import field_validator

from pydantic import BaseModel, Field


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
    is_light: bool = Field(..., alias="is_lighted")
    guard_level: GuardLevel = GuardLevel.No


class WebMedal(Medal):
    anchor_uid: int = Field(..., alias="target_id")
    anchor_room_id: Optional[int] = Field(None, alias="anchor_roomid")
    anchor_name: Optional[str] = Field(None, alias="anchor_uname")
    score: Optional[int] = None
    color_start: int = Field(..., alias="medal_color_border")
    color_end: int = Field(..., alias="medal_color_end")
    color_border: int = Field(..., alias="medal_color_start")
    color: int = Field(..., alias="medal_color")
    guard_icon: Optional[str] = None
    honor_icon: Optional[str] = None


class User(BaseModel):
    uid: int
    name: str
    face: str = ""
    open_id: str = ""
    name_color: Optional[int] = None
    is_admin: Optional[bool] = None
    special: Optional[str] = None
    medal: Optional[Union[WebMedal, Medal]] = None


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


class ComboInfo(BaseModel):
    combo_base_num: int
    combo_count: int
    combo_id: str
    combo_timeout: int


class BlindGift(BaseModel):
    blind_gift_id: int
    status: bool


class VoteOption(BaseModel):
    """投票选项"""

    idx: int
    """选项索引"""
    desc: str
    """选项内容"""
    cnt: int
    """票数"""
    percent: int
    """显示占比"""


class VoteCombo(BaseModel):
    """投票状态展示"""

    id: int
    """标识id，同VoteOption.idx"""
    status: int
    """状态，同InteractionVote.status"""
    content: str
    """投票选项内容"""
    cnt: str
    """弹幕计数"""
    guide: str
    """引导文本，通常为空字符串"""
    left_duration: int
    """剩余时间"""
    fade_duration: int
    """渐变持续时间"""
    prefix_icon: str
    """投票选项图标"""


class DanmakuCombo(BaseModel):
    """连续发送弹幕事件信息"""

    id: int
    """标识 ID"""
    status: int
    """状态"""
    content: str
    """重复的弹幕内容"""
    cnt: int
    """重复数量"""
    guide: str
    """标题词"""
    left_duration: int
    """左移时长"""
    fade_duration: int
    """淡化时长"""


# class SkinConfig(BaseModel):
#     """直播间皮肤配置"""
#     pass  # 待调查具体字段


# class RoomBlockUser(BaseModel):
#     """被禁言的用户信息"""
#     uid: int
#     """禁言用户 mid"""
#     uname: str
#     """禁言用户名"""
#     # dmscore: int  # 弹幕分数 - 待调查
#     # operator: int  # 操作者 - 待调查
