from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel


class AdminLevel(IntEnum):
    """管理员等级枚举"""

    ANCHOR = 0
    """主播"""
    MODERATOR = 1
    """房管"""


class SilentUser(BaseModel):
    """禁言用户信息"""

    tuid: int
    """禁言者uid"""
    tname: str
    """禁言者昵称"""
    uid: int
    """发起者uid"""
    name: str
    """发起者昵称"""
    ctime: str
    """禁言时间"""
    id: int
    """禁言记录Id，解除禁言时用到"""
    is_anchor: int
    """不明"""
    face: str
    """禁言者头像"""
    admin_level: AdminLevel
    """发起者权限"""


class SilentUserListData(BaseModel):
    """禁言用户列表数据"""

    data: list[SilentUser]
    """禁言列表"""
    total: int
    """禁言观众数量"""
    total_page: int
    """页码总数量"""
