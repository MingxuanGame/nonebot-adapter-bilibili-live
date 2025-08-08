from __future__ import annotations

import base64
import json
from typing import Any, Callable, Literal, Optional, TypeVar, Union
from typing_extensions import override

from nonebot.adapters import Event as BaseEvent
from nonebot.compat import model_dump, model_validator, type_validate_python
from nonebot.utils import escape_tag

from .exception import InteractionEndException
from .log import log
from .message import Emoticon, Message, MessageSegment
from .models.event import (
    BatchComboSend,
    BlindGift,
    ComboInfo,
    DanmakuCombo,
    GuardLevel,
    Medal,
    Rank,
    RankChangeMsg,
    SpecialGift,
    User,
    VoteCombo,
    VoteOption,
    WebMedal,
)
from .packet import OpCode, Packet
from .pb import InteractWordV2, OnlineRankV3

from betterproto import (
    Casing,
    Message as ProtoMessage,
)

COMMAND_TO_EVENT: dict[str, type] = {}
COMMAND_TO_PB: dict[str, type[ProtoMessage]] = {}


T = TypeVar("T")


def cmd(
    cmd: str, proto: type[ProtoMessage] | None = None
) -> Callable[[type[T]], type[T]]:
    def wrapper(cls: type[T]) -> type[T]:
        origin = COMMAND_TO_EVENT.get(cmd)
        if origin is None:
            COMMAND_TO_EVENT[cmd] = cls
        else:
            COMMAND_TO_EVENT[cmd] = Union[origin, cls]
        if proto is not None:
            COMMAND_TO_PB[cmd] = proto
        return cls

    return wrapper


class Event(BaseEvent):
    room_id: int
    """房间号"""

    @override
    def get_type(self) -> str:
        raise NotImplementedError

    @override
    def get_event_name(self) -> str:
        raise NotImplementedError

    @override
    def get_event_description(self) -> str:
        return str(model_dump(self))

    @override
    def get_message(self) -> Message:
        raise ValueError("Event has no message!")

    @override
    def get_user_id(self) -> str:
        raise ValueError("Event has no context!")

    @override
    def get_session_id(self) -> str:
        raise ValueError("Event has no context!")

    @override
    def is_tome(self) -> bool:
        return False


class OpenplatformOnlyEvent(Event):
    open_id: str = ""


class WebOnlyEvent(Event): ...


# meta event


class MetaEvent(Event):
    @override
    def get_type(self) -> str:
        return "metaevent"


class HeartbeatEvent(MetaEvent):
    popularity: int
    """人气值"""

    @override
    def get_event_name(self) -> str:
        return "heartbeat"

    @override
    def get_event_description(self) -> str:
        return f"[{self.room_id}] ACK, popularity: {self.popularity}"


# message event
class MessageEvent(Event):
    message: Message
    sender: User

    @override
    def get_type(self) -> str:
        return "message"

    @override
    def get_message(self) -> Message:
        return self.message

    @override
    def get_user_id(self) -> str:
        return (
            str(self.sender.uid) if self.sender.open_id == "" else self.sender.open_id
        )


def _medal_validator(medal: dict[str, Any] | None) -> WebMedal | None:
    if not medal or not medal["medal_name"]:
        return None
    medal["name"] = medal["medal_name"]
    medal["level"] = medal["medal_level"]
    return type_validate_python(
        WebMedal,
        medal,
    )


def _open_medal_validator(medal: dict[str, Any]) -> Medal | None:
    if not medal["fans_medal_name"]:
        return None
    return Medal(
        name=medal["fans_medal_name"],
        level=medal["fans_medal_level"],
        is_lighted=medal["fans_medal_wearing_status"],
        guard_level=GuardLevel(medal["guard_level"]),
    )


@cmd("DANMU_MSG")
@cmd("LIVE_OPEN_PLATFORM_DM")
class DanmakuEvent(MessageEvent):
    time: float
    mode: int
    content: str
    emots: Optional[dict[str, Emoticon]] = None
    reply_uname: str

    reply_mid: int
    color: int
    font_size: int
    send_from_me: bool
    reply_uname_color: str

    reply_open_id: str

    to_me: bool = False
    msg_id: str = ""

    @override
    def get_event_name(self) -> str:
        return "danmaku"

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "data" in data:
            # Openplatform DM
            content = data["data"]["msg"]
            mode = data["data"]["dm_type"]
            emots = None
            if mode == 1:
                emots = {
                    content: Emoticon(
                        descript="",
                        emoji=content,
                        emoticon_id=-1,
                        emoticon_unique=f"upower_{content}",
                        url=data["data"]["emoji_img_url"],
                        width=0,
                        height=0,
                    )
                }
            time = data["data"]["timestamp"]
            send_from_me = False
            sender = User(
                uid=data["data"]["uid"],
                face=data["data"]["uface"],
                name=data["data"]["uname"],
                is_admin=data["data"].get("is_admin", False),
                open_id=data["data"]["open_id"],
                medal=_open_medal_validator(data["data"]),
            )
            reply_mid = 0
            reply_uname = data["data"].get("reply_uname", "")
            reply_uname_color = ""
            reply_open_id = data["data"].get("reply_open_id", "")
            msg_id = data["data"]["msg_id"]
            color = 0
            font_size = 0
        else:
            # Web DM
            extra = json.loads(data["info"][0][15]["extra"])
            emots = extra["emots"]
            content = data["info"][1]
            user = data["info"][0][15]["user"]
            if isinstance(upower_emot_raw := data["info"][0][13], dict):
                emoji = upower_emot_raw["emoticon_unique"].removeprefix("upower_")
                emots = {
                    emoji: Emoticon(
                        descript="",
                        emoji=emoji,
                        emoticon_id=-1,
                        emoticon_unique=upower_emot_raw["emoticon_unique"],
                        url=upower_emot_raw["url"],
                        width=upower_emot_raw["width"],
                        height=upower_emot_raw["height"],
                    )
                }
            reply_mid = extra.get("reply_mid", 0)
            reply_uname = extra.get("reply_uname", "")
            reply_uname_color = extra.get("reply_uname_color", "")
            reply_open_id = ""
            time = data["info"][0][4] / 1000
            mode = data["info"][0][1]
            send_from_me = extra["send_from_me"]
            medal = user["medal"]
            if medal:
                medal = WebMedal(
                    target_id=medal["ruid"],
                    medal_color=medal["color"],
                    medal_color_border=medal["color_border"],
                    medal_color_end=medal["color_end"],
                    medal_color_start=medal["color_start"],
                    is_lighted=medal["is_light"],
                    **medal,
                )
            sender = User(
                uid=user["uid"],
                face=user["base"]["face"],
                name=user["base"]["name"],
                name_color=user["base"]["name_color"],
                medal=medal,
            )
            msg_id = ""
            color = data["info"][0][3]
            font_size = data["info"][0][2]
        message = Message.construct(content, emots)
        if reply_mid or reply_open_id:
            message.insert(
                0, MessageSegment.at(reply_mid or reply_open_id, reply_uname)
            )
        return {
            "time": time,
            "mode": mode,
            "color": color,
            "font_size": font_size,
            "content": content,
            "emots": emots or {},
            "send_from_me": send_from_me,
            "message": message,
            "sender": sender,
            "room_id": data["room_id"],
            "reply_mid": reply_mid,
            "reply_open_id": reply_open_id,
            "reply_uname": reply_uname,
            "reply_uname_color": reply_uname_color,
            "msg_id": msg_id,
        }

    @override
    def get_event_description(self) -> str:
        return (
            f"[Room@{self.room_id}] {self.sender.name}: "
            f"{f'@{self.reply_uname} ' if self.reply_uname else ''}{self.content}"
        )

    @override
    def get_session_id(self) -> str:
        return f"{self.room_id}_{self.sender.uid}"

    @override
    def is_tome(self) -> bool:
        return self.to_me


@cmd("SUPER_CHAT_MESSAGE")
@cmd("SUPER_CHAT_MESSAGE_JPN")
@cmd("LIVE_OPEN_PLATFORM_SUPER_CHAT")
class SuperChatEvent(MessageEvent):
    id: int
    price: float
    start_time: float
    end_time: float

    message_font_color: str
    message_trans: Optional[str] = None
    message_jpn: Optional[str] = None

    msg_id: str = ""

    to_me: bool = False

    @override
    def get_event_name(self) -> str:
        return "super_chat"

    @override
    def get_message(self) -> Message:
        return self.message

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        data_ = data["data"]
        if "open_id" in data_:
            sender = User(
                uid=data_["uid"],
                face=data_["uface"],
                name=data_["uname"],
                open_id=data_["open_id"],
                medal=_open_medal_validator(data_),
            )
            msg_id = data_.get("msg_id", "")
            message_id = data_.get("message_id", "")
            message_trans = None
            message_jpn = None
            start_time = data_["start_time"]
            end_time = data_["end_time"]
            message_font_color = ""
        else:
            user = data["data"]["user_info"]
            sender = User(
                uid=data["data"]["uid"],
                face=user["face"],
                name=user["uname"],
                name_color=user.get("name_color", 0),
                medal=_medal_validator(data["data"]["medal_info"]),
            )
            msg_id = ""
            message_id = ""
            message_trans = data_.get("message_trans", None)
            message_jpn = data_.get("message_jpn", None)
            start_time = data_["start_time"] / 1000
            end_time = data_["end_time"] / 1000
            message_font_color = data_.get("message_font_color", "")
        return {
            "id": data["data"].get("id", data["data"]["message_id"]),
            "price": data["data"].get("price", data["rmb"]),
            "sender": sender,
            "message": Message.construct(data["data"]["message"], None),
            "message_font_color": message_font_color,
            "start_time": start_time,
            "end_time": end_time,
            "message_trans": message_trans,
            "message_jpn": message_jpn,
            "room_id": data["room_id"],
            "msg_id": msg_id,
            "message_id": message_id,
        }

    @override
    def get_event_description(self) -> str:
        return (
            f"[Room@{self.room_id}] [￥{self.price}] {self.sender.name}: {self.message}"
        )

    @override
    def get_session_id(self) -> str:
        return f"{self.room_id}_{self.sender.uid}_{self.id}"

    @override
    def is_tome(self) -> bool:
        return self.to_me


# notice event


class NoticeEvent(Event):
    @override
    def get_type(self) -> str:
        return "notice"

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {
            "room_id": data["room_id"],
            **data["data"],
        }


# INTERACT_WORD


def _interact_word_validator(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "msg_type": data["data"]["msg_type"],
        "timestamp": data["data"]["timestamp"],
        "trigger_time": data["data"]["trigger_time"],
        "uid": data["data"]["uid"],
        "uname": data["data"]["uname"],
        "uname_color": data["data"]["uname_color"],
        "room_id": data["room_id"],
        "fans_medal": _medal_validator(data["data"].get("fans_medal", None)),
    }


class _InteractWordEvent(NoticeEvent):
    msg_type: int
    timestamp: int
    trigger_time: int
    uid: int
    uname: str
    uname_color: str
    fans_medal: Optional[WebMedal] = None

    @override
    def get_user_id(self) -> str:
        return str(self.uid)

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        return _interact_word_validator(data)


@cmd("INTERACT_WORD")
@cmd("INTERACT_WORD_V2", InteractWordV2)
@cmd("LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER")
class UserEnterEvent(_InteractWordEvent):
    open_id: str = ""

    msg_type: Literal[1, "1"] = 1

    @override
    def get_event_name(self) -> str:
        return "user_enter"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} Entered the room"

    @model_validator(mode="before")
    @classmethod
    @override
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        if isinstance(data["data"], InteractWordV2) or "open_id" not in data["data"]:
            return _interact_word_validator(data)
        return {
            "room_id": data["room_id"],
            "uid": data["data"]["uid"],
            "uname": data["data"]["uname"],
            "uname_color": "",
            "timestamp": data["data"]["timestamp"],
            "trigger_time": data["data"]["timestamp"],
            "open_id": data["data"]["open_id"],
        }

    @override
    def get_user_id(self) -> str:
        return str(self.uid) if self.open_id == "" else self.open_id


@cmd("INTERACT_WORD")
@cmd("INTERACT_WORD_V2", InteractWordV2)
class UserFollowEvent(_InteractWordEvent, WebOnlyEvent):
    msg_type: Literal[2, "2"] = 2

    @override
    def get_event_name(self) -> str:
        return "user_follow"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} Followed the room"


@cmd("INTERACT_WORD")
@cmd("INTERACT_WORD_V2", InteractWordV2)
class UserShareEvent(_InteractWordEvent, WebOnlyEvent):
    msg_type: Literal[3, "3"] = 3

    @override
    def get_event_name(self) -> str:
        return "user_share"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} Shared the room"


@cmd("GUARD_BUY")
@cmd("LIVE_OPEN_PLATFORM_GUARD")
class GuardBuyEvent(NoticeEvent):
    face: str = ""
    username: str
    guard_level: GuardLevel
    num: int = 1
    price: float
    gift_id: int
    gift_name: str
    time: int

    uid: int

    open_id: str = ""
    guard_unit: str = ""
    msg_id: str = ""
    medal: Optional[Medal] = None

    @override
    def get_event_name(self) -> str:
        return "guard_buy"

    @override
    def get_event_description(self) -> str:
        return (
            f"[Room@{self.room_id}] [￥{self.price}] {self.username} bought {self.num} "
            f"{self.guard_level.name} guard(s)"
        )

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "user_info" in data["data"]:
            data["data"]["uid"] = data["data"]["user_info"]["uid"]
            data["data"]["face"] = data["data"]["user_info"]["uface"]
            data["data"]["username"] = data["data"]["user_info"]["uname"]
            data["data"]["open_id"] = data["data"]["user_info"]["open_id"]
            data["num"] = data["data"]["guard_num"]
            data["medal"] = _open_medal_validator(data["data"])
        return {
            "time": data["data"].get("start_time", data["data"]["timestamp"]),
            "room_id": data["room_id"],
            **data["data"],
        }

    @override
    def get_user_id(self) -> str:
        return str(self.uid) if self.open_id == "" else self.open_id


@cmd("USER_TOAST_MSG")
class GuardBuyToastEvent(NoticeEvent, WebOnlyEvent):
    color: str
    guard_level: GuardLevel
    num: int
    price: float
    role_name: str
    uid: int
    username: str
    toast_msg: str
    gift_id: int
    time: int

    @override
    def get_event_name(self) -> str:
        return "guard_buy_toast"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] [￥{self.price}] {escape_tag(self.toast_msg)}"

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {
            "time": data["data"]["start_time"],
            "room_id": data["room_id"],
            "toast_msg": data["data"]["toast_msg"],
            **data["data"],
        }

    @override
    def get_user_id(self) -> str:
        return str(self.uid)


@cmd("SEND_GIFT")
@cmd("LIVE_OPEN_PLATFORM_SEND_GIFT")
class SendGiftEvent(NoticeEvent, WebOnlyEvent):
    gift_name: str
    num: int
    price: float
    timestamp: int
    uid: int
    uname: str
    face: str
    medal: Optional[Medal] = None
    guard_level: Optional[int] = None
    receive_user_info: Optional[User] = None
    blind_gift: Optional[BlindGift] = None

    action: Optional[str] = None
    batch_combo_id: Optional[str] = None
    batch_combo_send: Optional[BatchComboSend] = None
    coin_type: Optional[str] = None
    original_gift_name: Optional[str] = None
    rnd: Optional[str] = None
    tid: Optional[str] = None
    total_coin: Optional[int] = None

    open_id: str = ""
    r_price: Optional[int] = None
    paid: Optional[bool] = None
    msg_id: str = ""
    gift_icon: str = ""
    combo_gift: Optional[bool] = None
    combo_info: Optional[ComboInfo] = None

    @override
    def get_event_name(self) -> str:
        return "send_gift"

    @override
    def get_event_description(self) -> str:
        display_price = self.price
        gift_count = self.num
        return (
            f"[Room@{self.room_id}] [￥{display_price}] {self.uname} sent {gift_count} "
            f"{self.gift_name}(s)"
        )

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        data_obj = data["data"]
        if "open_id" in data_obj:
            # OpenBot
            return {
                "room_id": data["room_id"],
                "uid": data_obj["uid"],
                "open_id": data_obj["open_id"],
                "uname": data_obj["uname"],
                "face": data_obj["uface"],
                "gift_id": data_obj["gift_id"],
                "gift_name": data_obj["gift_name"],
                "num": data_obj["gift_num"],
                "price": data_obj["price"] / 1000,
                "r_price": data_obj["r_price"],
                "paid": data_obj["paid"],
                "guard_level": data_obj["guard_level"],
                "timestamp": data_obj["timestamp"],
                "msg_id": data_obj["msg_id"],
                "receive_user_info": User(
                    uid=data_obj["anchor_info"]["uid"],
                    name=data_obj["anchor_info"]["uname"],
                    face=data_obj["anchor_info"]["uface"],
                    open_id=data_obj["anchor_info"]["open_id"],
                ),
                "gift_icon": data_obj.get("gift_icon", ""),
                "combo_gift": data_obj.get("combo_gift"),
                "combo_info": data_obj.get("combo_info"),
                "blind_gift": data_obj.get("blind_gift"),
                "medal": _open_medal_validator(data_obj),
            }
        else:
            # WebBot
            blind_gift = data_obj.get("blind_gift", None)
            if blind_gift:
                blind_gift = BlindGift(
                    blind_gift_id=blind_gift["blind_gift_config_id"],
                    status=True,
                )
            result = {
                "room_id": data["room_id"],
                **data_obj,
                "receive_user_info": User(
                    uid=data_obj["receive_user_info"]["uid"],
                    name=data_obj["receive_user_info"]["uname"],
                ),
                "blind_gift": blind_gift,
                "medal": _medal_validator(data_obj.get("medal_info", None)),
            }
            if "giftName" in data_obj:
                result["gift_name"] = data_obj["giftName"]
            return result

    @override
    def get_user_id(self) -> str:
        return str(self.uid) if self.open_id == "" else self.open_id


@cmd("GIFT_STAR_PROCESS")
class GiftStarProcessEvent(NoticeEvent, WebOnlyEvent):
    status: int
    tip: str

    @override
    def get_event_name(self) -> str:
        return "gift_star_process"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.tip}"


@cmd("SPECIAL_GIFT")
class SpecialGiftEvent(NoticeEvent, WebOnlyEvent):
    gifts: dict[str, SpecialGift]

    @override
    def get_event_name(self) -> str:
        return "special_gift"

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {
            "gifts": data["data"],
            "room_id": data["room_id"],
        }


@cmd("LIKE_INFO_V3_CLICK")
@cmd("LIVE_OPEN_PLATFORM_LIKE")
class LikeEvent(NoticeEvent):
    uname: str
    uid: int
    like_text: str
    fans_medal: Optional[Medal] = None

    uname_color: Optional[str] = None
    like_icon: Optional[str] = None

    open_id: str = ""
    uface: str = ""
    timestamp: Optional[int] = None
    like_count: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "open_id" in data["data"]:
            return {
                "uname": data["data"]["uname"],
                "uid": data["data"]["uid"],
                "like_text": data["data"]["like_text"],
                "open_id": data["data"]["open_id"],
                "uface": data["data"]["uface"],
                "timestamp": data["data"]["timestamp"],
                "like_count": data["data"]["like_count"],
                "room_id": data["room_id"],
                "fans_medal": _open_medal_validator(data["data"]),
            }
        return {
            "uname": data["data"]["uname"],
            "uid": data["data"]["uid"],
            "like_text": data["data"]["like_text"],
            "uname_color": data["data"]["uname_color"],
            "like_icon": data["data"]["like_icon"],
            "room_id": data["room_id"],
            "fans_medal": _medal_validator(data["data"].get("fans_medal", None)),
        }

    @override
    def get_event_name(self) -> str:
        return "like"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} {self.like_text}"

    @override
    def get_user_id(self) -> str:
        return str(self.uid) if self.open_id == "" else self.open_id


class _DMInteraction(NoticeEvent, WebOnlyEvent):
    id: int
    status: int
    type: Literal[101, 102, 103, 104, 105, 106]

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        data_ = json.loads(data["data"]["data"])
        return {
            "room_id": data["room_id"],
            **data["data"],
            **data_,
        }


@cmd("DM_INTERACTION")
class InteractionVote(_DMInteraction):
    """投票互动事件"""

    type: Literal[101]
    question: str
    """投票问题"""
    options: list[VoteOption]
    """投票详细选项"""
    vote_id: int
    """投票id"""
    cnt: int
    """弹幕计数"""
    duration: int
    """持续时间，单位毫秒"""
    left_duration: int
    """剩余时间，单位毫秒"""
    fade_duration: int
    waiting_duration: int
    result: int
    """投票倾向状态"""
    result_text: str
    """投票倾向提示"""
    component: str
    """投票链接"""
    natural_die_duration: int
    my_vote: int
    component_anchor: str
    """投票控制链接"""
    audit_reason: str
    """审核结果"""
    combo: list[VoteCombo]
    """投票状态展示"""

    @override
    def get_event_name(self) -> str:
        return "interaction_vote"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Vote: {self.question} -> {self.result_text}"


@cmd("DM_INTERACTION")
class InteractionDanmaku(_DMInteraction):
    """弹幕互动事件"""

    type: Literal[102]
    combo: list[DanmakuCombo]
    """连续发送弹幕事件信息"""
    merge_interval: int
    """合并弹幕时间间隔"""
    card_appear_interval: int
    """弹窗出现时间间隔"""
    send_interval: int
    """发送时间间隔"""

    @override
    def get_event_name(self) -> str:
        return "interaction_danmaku"


@cmd("DM_INTERACTION")
class InteractionFollow(_DMInteraction):
    """关注互动事件"""

    type: Literal[103]
    fade_duration: int
    """"""
    cnt: int
    """关注计数"""
    card_appear_interval: int
    """"""
    suffix_text: str
    """提示文本"""
    reset_cnt: int
    """"""
    display_flag: int
    """"""

    @override
    def get_event_name(self) -> str:
        return "interaction_follow"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.cnt}{self.suffix_text}"


@cmd("DM_INTERACTION")
class InteractionGift(_DMInteraction):
    """送礼互动事件"""

    type: Literal[104]
    fade_duration: int
    """"""
    cnt: int
    """投喂计数"""
    card_appear_interval: int
    """"""
    suffix_text: str
    """提示文本"""
    reset_cnt: int
    """"""
    display_flag: int
    """"""
    gift_id: int
    """礼物 ID"""
    gift_alert_message: str
    """"""

    @override
    def get_event_name(self) -> str:
        return "interaction_gift"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.cnt}{self.suffix_text}"


@cmd("DM_INTERACTION")
class InteractionShare(_DMInteraction):
    """分享互动事件"""

    type: Literal[105]
    fade_duration: int
    """"""
    cnt: int
    """分享计数"""
    card_appear_interval: int
    """"""
    suffix_text: str
    """提示文本"""
    reset_cnt: int
    """"""
    display_flag: int
    """"""

    @override
    def get_event_name(self) -> str:
        return "interaction_share"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.cnt}{self.suffix_text}"


@cmd("DM_INTERACTION")
class InteractionLike(_DMInteraction):
    """点赞互动事件"""

    type: Literal[106]
    fade_duration: int
    """"""
    cnt: int
    """点赞计数"""
    card_appear_interval: int
    """"""
    suffix_text: str
    """提示文本"""
    reset_cnt: int
    """"""
    display_flag: int
    """"""

    @override
    def get_event_name(self) -> str:
        return "interaction_like"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.cnt}{self.suffix_text}"


@cmd("LIVE")
class WebLiveStartEvent(NoticeEvent, WebOnlyEvent):
    live_time: int
    live_platform: str

    @override
    def get_event_name(self) -> str:
        return "live_start"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Live started"


class _OpenLiveEvent(NoticeEvent, OpenplatformOnlyEvent):
    area_name: str
    title: str
    timestamp: int

    @override
    def get_event_name(self) -> str:
        return "open_live_event"


@cmd("LIVE_OPEN_PLATFORM_LIVE_START")
class OpenLiveStartEvent(_OpenLiveEvent):
    @override
    def get_event_name(self) -> str:
        return "open_live_start"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Live started in {self.area_name}: {self.title}"


@cmd("LIVE_OPEN_PLATFORM_LIVE_END")
class OpenLiveEndEvent(_OpenLiveEvent):
    @override
    def get_event_name(self) -> str:
        return "open_live_end"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Live ended in {self.area_name}: {self.title}"


@cmd("ONLINE_RANK_V2")
@cmd("ONLINE_RANK_V3", OnlineRankV3)
class OnlineRankEvent(NoticeEvent, WebOnlyEvent):
    online_list: list[Rank]
    rank_type: str

    @override
    def get_event_name(self) -> str:
        return "online_rank"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Rank updated"

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any] | Any) -> Any:
        if not isinstance(data, dict):
            return data
        return {
            "online_list": data["data"]["list"],
            "rank_type": data["data"]["rank_type"],
            "room_id": data["room_id"],
        }


@cmd("ONLINE_RANK_COUNT")
class OnlineRankCountEvent(NoticeEvent, WebOnlyEvent):
    count: int

    @override
    def get_event_name(self) -> str:
        return "online_rank_count"


@cmd("ONLINE_RANK_TOP3")
class OnlineRankTopEvent(NoticeEvent, WebOnlyEvent):
    top: list[RankChangeMsg]

    @override
    def get_event_name(self) -> str:
        return "online_rank_top"

    @override
    def get_event_description(self) -> str:
        msgs = [f"{d.msg} #{d.rank}" for d in self.top]
        return f"[Room@{self.room_id}] {' + '.join(msgs)}"


@cmd("LIKE_INFO_V3_UPDATE")
class LikeInfoUpdateEvent(NoticeEvent, WebOnlyEvent):
    click_count: int
    """点赞数"""

    @override
    def get_event_name(self) -> str:
        return "like_info_update"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Click count updated: {self.click_count}"


@cmd("WATCHED_CHANGE")
class WatchedChangeEvent(NoticeEvent, WebOnlyEvent):
    num: int
    text_small: str
    text_large: str
    """观看人数变化"""

    @override
    def get_event_name(self) -> str:
        return "watched_change"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Watched people count change: {self.num}"


@cmd("STOP_LIVE_ROOM_LIST")
class StopLiveRoomListEvent(NoticeEvent, WebOnlyEvent):
    room_id_list: list[int]

    @override
    def get_event_name(self) -> str:
        return "stop_room_list"


@cmd("ROOM_REAL_TIME_MESSAGE_UPDATE")
class RoomRealTimeMessageUpdateEvent(NoticeEvent, WebOnlyEvent):
    """主播信息更新"""

    roomid: int
    """直播间ID"""
    fans: int
    """主播当前粉丝数"""
    fans_club: int
    """主播粉丝团人数"""
    # red_notice: int  # 待调查

    @override
    def get_event_name(self) -> str:
        return "room_real_time_message_update"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Fans: {self.fans}, Fan club: {self.fans_club}"


@cmd("POPULAR_RANK_CHANGED")
class PopularRankChangedEvent(NoticeEvent, WebOnlyEvent):
    """直播间在人气榜的排名改变"""

    uid: int
    """主播 mid"""
    rank: int
    """人气榜排名"""
    countdown: int
    """人气榜下轮结算剩余时长"""
    timestamp: int
    """触发时的Unix时间戳"""
    # cache_key: str  # 待调查

    @override
    def get_event_name(self) -> str:
        return "popular_rank_changed"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Popular rank changed to #{self.rank}"

    @override
    def get_user_id(self) -> str:
        return str(self.uid)


@cmd("HOT_RANK_CHANGED")
@cmd("HOT_RANK_CHANGED_V2")
class HotRankChangedEvent(NoticeEvent, WebOnlyEvent):
    """直播间限时热门榜排名改变"""

    rank: int
    """排名"""
    # trend: int  # 趋势 - 待调查
    countdown: int
    """剩余时间"""
    timestamp: int
    """当前时间"""
    web_url: str
    """排行榜 URL"""
    live_url: str
    """排行榜 URL"""
    blink_url: str
    """排行榜 URL"""
    live_link_url: str
    """排行榜 URL"""
    pc_link_url: str
    """排行榜 URL"""
    icon: str
    """图标 URL"""
    area_name: str
    """分区名称"""
    rank_desc: Optional[str] = None
    """排行榜说明"""

    @override
    def get_event_name(self) -> str:
        return "hot_rank_changed"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Hot rank changed to #{self.rank}"


@cmd("HOT_RANK_SETTLEMENT")
@cmd("HOT_RANK_SETTLEMENT_V2")
class HotRankSettlementEvent(NoticeEvent, WebOnlyEvent):
    """限时热门榜上榜信息"""

    area_name: str
    """分区名称"""
    # cache_key: str  # 待调查
    dm_msg: str
    """弹幕提示信息"""
    # dmscore: int  # 待调查
    face: str
    """主播头像 URL"""
    icon: str
    """图标 URL"""
    rank: int
    """排名"""
    timestamp: int
    """时间"""
    uname: str
    """主播用户名"""
    url: str
    """排行榜 URL"""

    @override
    def get_event_name(self) -> str:
        return "hot_rank_settlement"

    @override
    def get_event_description(self) -> str:
        return (
            f"[Room@{self.room_id}] {self.uname} ranked "
            f"#{self.rank} in {self.area_name}"
        )


@cmd("AREA_RANK_CHANGED")
class AreaRankChangedEvent(NoticeEvent, WebOnlyEvent):
    """直播间在所属分区的排名改变"""

    # conf_id: int  # 配置 ID - 待调查
    rank_name: str
    """排行榜名称"""
    uid: int
    """主播 mid"""
    rank: int
    """直播间在分区的排名"""
    icon_url_blue: str
    """蓝色排名图标 URL"""
    icon_url_pink: str
    """粉色排名图标 URL"""
    icon_url_grey: str
    """灰色排名图标 URL"""
    # action_type: int  # 待调查
    timestamp: int
    """当前时间"""
    # msg_id: str  # 待调查
    jump_url_link: str
    """排行榜跳转链接"""
    jump_url_pc: str
    """排行榜跳转链接"""
    jump_url_pink: str
    """排行榜跳转链接"""
    jump_url_web: str
    """排行榜跳转链接"""

    @override
    def get_event_name(self) -> str:
        return "area_rank_changed"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.rank_name} rank changed to #{self.rank}"

    @override
    def get_user_id(self) -> str:
        return str(self.uid)


@cmd("ROOM_CHANGE")
class RoomChangeEvent(NoticeEvent, WebOnlyEvent):
    """直播间信息更改"""

    title: str
    """直播间标题"""
    area_id: int
    """当前直播间所属二级分区的ID"""
    parent_area_id: int
    """当前直播间所属一级分区的ID"""
    area_name: str
    """当前直播间所属二级分区的名称"""
    parent_area_name: str
    """当前直播间所属一级分区名称"""
    live_key: str
    """标记直播场次的key"""
    sub_session_key: str
    """待调查"""

    @override
    def get_event_name(self) -> str:
        return "room_change"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Room info changed: {self.title}"


@cmd("CHANGE_ROOM_INFO")
class ChangeRoomInfoEvent(NoticeEvent, WebOnlyEvent):
    """直播间背景图片修改"""

    background: str
    """背景图 URL"""
    roomid: int
    """直播间 ID"""

    @override
    def get_event_name(self) -> str:
        return "change_room_info"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Background image changed"


@cmd("ROOM_SKIN_MSG")
class RoomSkinMsgEvent(NoticeEvent, WebOnlyEvent):
    """直播间皮肤变更"""

    skin_id: int
    """皮肤 ID"""
    # status: int  # 状态 - 待调查
    end_time: int
    """皮肤结束时间"""
    current_time: int
    """当前时间"""
    only_local: bool
    """仅在本地显示"""
    # scatter: dict  # 待调查
    # skin_config: SkinConfig  # 皮肤配置 - 待调查

    @override
    def get_event_name(self) -> str:
        return "room_skin_msg"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Skin changed: {self.skin_id}"


@cmd("ROOM_SILENT_ON")
class RoomSilentOnEvent(NoticeEvent, WebOnlyEvent):
    """开启等级禁言"""

    type: str
    """类型"""
    level: int
    """等级"""
    second: int
    """时间"""

    @override
    def get_event_name(self) -> str:
        return "room_silent_on"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Level silent on: level {self.level}"


@cmd("ROOM_SILENT_OFF")
class RoomSilentOffEvent(NoticeEvent, WebOnlyEvent):
    """关闭等级禁言"""

    type: str
    """类型"""
    level: int
    """等级"""
    second: int
    """时间"""

    @override
    def get_event_name(self) -> str:
        return "room_silent_off"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Level silent off"


@cmd("ROOM_BLOCK_MSG")
class RoomBlockMsgEvent(NoticeEvent, WebOnlyEvent):
    """指定观众禁言"""

    uid: int
    """禁言用户 mid"""
    uname: str
    """禁言用户名"""
    # data: RoomBlockUser  # 详细信息 - 含有重复字段，暂时注释

    @override
    def get_event_name(self) -> str:
        return "room_block_msg"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} blocked"

    @override
    def get_user_id(self) -> str:
        return str(self.uid)


@cmd("ROOM_ADMINS")
class RoomAdminsEvent(NoticeEvent, WebOnlyEvent):
    """房管列表"""

    uids: list[int]
    """房管 mid 列表"""

    @override
    def get_event_name(self) -> str:
        return "room_admins"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Admin list updated, {len(self.uids)} admins"


@cmd("room_admin_entrance")
class RoomAdminEntranceEvent(NoticeEvent, WebOnlyEvent):
    """设立房管"""

    # dmscore: int  # 弹幕分数 - 待调查
    # level: int  # 等级 - 待调查
    msg: str
    """提示信息"""
    uid: int
    """用户 mid"""

    @override
    def get_event_name(self) -> str:
        return "room_admin_entrance"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.msg}"

    @override
    def get_user_id(self) -> str:
        return str(self.uid)


@cmd("ROOM_ADMIN_REVOKE")
class RoomAdminRevokeEvent(NoticeEvent, WebOnlyEvent):
    """撤销房管"""

    msg: str
    """提示信息"""
    uid: int
    """用户 mid"""

    @override
    def get_event_name(self) -> str:
        return "room_admin_revoke"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.msg}"

    @override
    def get_user_id(self) -> str:
        return str(self.uid)


def packet_to_event(packet: Packet, room_id: int) -> Event:
    data = packet.decode_dict()
    cmd = data.get("cmd", "")
    if packet.opcode == OpCode.HeartbeatReply.value:
        return HeartbeatEvent(popularity=data["popularity"], room_id=room_id)
    elif cmd == "LIVE_OPEN_PLATFORM_INTERACTION_END":
        raise InteractionEndException(
            data["data"]["game_id"], data["data"]["timestamp"]
        )
    elif packet.opcode == OpCode.Command.value:
        if (pb := COMMAND_TO_PB.get(cmd)) is not None:
            # https://github.com/SocialSisterYi/bilibili-API-collect/issues/1332
            message = pb()
            message.parse(base64.b64decode(data["data"]["pb"]))
            data["data"] = message.to_dict(
                casing=Casing.SNAKE,  # pyright: ignore[reportArgumentType]
                include_default_values=True,
            )
        data["room_id"] = room_id
        log("TRACE", f"[{cmd}] Receive: {escape_tag(str(data))}")
        event_model = COMMAND_TO_EVENT.get(cmd)
        if event_model:
            return type_validate_python(event_model, data)
    raise RuntimeError(f"Unknown packet opcode: {packet.opcode} or command: {cmd}")
