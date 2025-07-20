from __future__ import annotations

from enum import IntEnum
from typing import Optional

from pydantic import BaseModel, Field


class LiveStatus(IntEnum):
    """直播状态枚举"""

    NOT_LIVE = 0
    """未开播"""
    LIVE = 1
    """直播中"""
    ROUND = 2
    """轮播中"""


class Gender(IntEnum):
    """性别枚举"""

    SECRET = -1
    """保密"""
    FEMALE = 0
    """女"""
    MALE = 1
    """男"""


class OfficialVerifyType(IntEnum):
    """认证类型枚举"""

    NONE = -1
    """无"""
    PERSONAL = 0
    """个人认证"""
    ORGANIZATION = 1
    """机构认证"""


class Frame(BaseModel):
    """直播间边框信息"""

    name: str
    """名称"""
    value: str
    """值"""
    position: int
    """位置"""
    desc: str
    """描述"""
    area: int
    """分区"""
    area_old: int
    """旧分区"""
    bg_color: str
    """背景色"""
    bg_pic: str
    """背景图"""
    use_old_area: bool
    """是否旧分区号"""


class Badge(BaseModel):
    """直播间徽章信息"""

    name: str
    """类型 v_person: 个人认证(黄) v_company: 企业认证(蓝)"""
    position: int
    """位置"""
    value: str
    """值"""
    desc: str
    """描述"""


class NewPendants(BaseModel):
    """新版挂件信息"""

    frame: Frame
    """头像框"""
    badge: Optional[Badge] = None
    """大v认证信息"""
    mobile_frame: Frame
    """手机版头像框，结构一致"""
    mobile_badge: Optional[Badge] = None
    """手机版大v认证信息，结构一致，可能为null"""


class StudioInfo(BaseModel):
    """工作室信息"""

    status: int
    """工作室状态"""
    master_list: list = Field(default_factory=list)
    """主播列表"""


class Room(BaseModel):
    """直播间数据"""

    uid: int
    """主播mid"""
    room_id: int
    """直播间长号"""
    short_id: int
    """直播间短号，为0时无短号"""
    attention: int
    """关注数量"""
    online: int
    """观看人数"""
    is_portrait: bool
    """是否竖屏"""
    description: str
    """房间描述"""
    live_status: LiveStatus
    """直播状态"""
    area_id: int
    """分区id"""
    parent_area_id: int
    """父分区id"""
    parent_area_name: str
    """父分区名称"""
    old_area_id: int
    """旧版分区id"""
    background: str
    """背景图片链接"""
    title: str
    """直播间标题"""
    user_cover: str
    """封面"""
    keyframe: str
    """关键帧，用于网页端悬浮展示"""
    is_strict_room: bool
    """是否严格房间（未知）"""
    live_time: str
    """直播开始时间 YYYY-MM-DD HH:mm:ss"""
    tags: str
    """标签，','分隔"""
    is_anchor: int
    """是否主播（未知）"""
    room_silent_type: str
    """禁言状态"""
    room_silent_level: int
    """禁言等级"""
    room_silent_second: int
    """禁言时间，单位是秒"""
    area_name: str
    """分区名称"""
    pendants: str
    """挂件（未知）"""
    area_pendants: str
    """分区挂件（未知）"""
    hot_words: list[str] = Field(default_factory=list)
    """热词"""
    hot_words_status: int
    """热词状态"""
    verify: str
    """认证信息（未知）"""
    new_pendants: NewPendants
    """新版挂件：头像框和大v认证"""
    up_session: str
    """UP主会话（未知）"""
    pk_status: int
    """pk状态"""
    pk_id: int
    """pk id"""
    battle_id: int
    """战斗id（未知）"""
    allow_change_area_time: int
    """允许改变分区时间"""
    allow_upload_cover_time: int
    """允许上传封面时间"""
    studio_info: StudioInfo
    """工作室信息"""


class UserRoomStatus(BaseModel):
    """用户直播间状态数据"""

    has_room: bool = Field(alias="roomStatus")
    """是否有房间 对应原字段 room_status 0：无房间 1：有房间"""
    is_round: bool = Field(alias="roundStatus")
    """是否轮播 对应原字段 round_status 0：未轮播 1：轮播"""
    is_live: bool = Field(alias="live_status")
    """直播状态 对应原字段 live_status 0：未开播 1：直播中"""
    url: str
    """直播间网页url"""
    title: str
    """直播间标题"""
    cover: str
    """直播间封面url"""
    online: int
    """直播间人气，值为上次直播时刷新"""
    room_id: int = Field(alias="roomid")
    """直播间id（短号） 对应原字段 roomid"""
    broadcast_type: int
    """广播类型，通常为0"""
    online_hidden: int
    """在线隐藏状态，通常为0"""


class OfficialVerify(BaseModel):
    """认证信息"""

    type: OfficialVerifyType
    """主播认证类型"""
    desc: str
    """主播认证信息"""


class MasterInfo(BaseModel):
    """主播基本信息"""

    uid: int
    """主播mid"""
    uname: str
    """主播用户名"""
    face: str
    """主播头像url"""
    official_verify: OfficialVerify
    """认证信息"""
    gender: Gender
    """主播性别"""


class MasterLevel(BaseModel):
    """主播等级信息"""

    level: int
    """当前等级"""
    color: int
    """等级框颜色"""
    current: list[int]
    """当前等级信息 [升级积分, 总积分]"""
    next: list[int]
    """下一等级信息 [升级积分, 总积分]"""


class MasterExp(BaseModel):
    """主播经验等级"""

    master_level: MasterLevel
    """主播等级"""


class RoomNews(BaseModel):
    """主播公告"""

    content: str
    """公告内容"""
    ctime: str
    """公告时间"""
    ctime_text: str
    """公告日期"""


class MasterData(BaseModel):
    """主播信息数据"""

    info: MasterInfo
    """主播信息"""
    exp: MasterExp
    """经验等级"""
    follower_num: int
    """主播粉丝数"""
    room_id: int
    """直播间id（短号）"""
    medal_name: str
    """粉丝勋章名"""
    glory_count: int
    """主播荣誉数"""
    pendant: str
    """直播间头像框url"""
    link_group_num: int
    """0 作用尚不明确"""
    room_news: RoomNews
    """主播公告"""
