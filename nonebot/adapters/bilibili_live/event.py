from __future__ import annotations

import base64
import json
from typing import Any, Callable, Literal, Optional, TypeVar, Union
from typing_extensions import override

from nonebot.adapters import Event as BaseEvent
from nonebot.compat import model_dump, model_validator, type_validate_python
from nonebot.utils import escape_tag

from .log import log
from .message import Emoticon, Message
from .models.event import GuardLevel, Rank, RankChangeMsg, Sender, SpecialGift
from .packet import OpCode, Packet
from .pb import interact_word_v2_pb2, online_rank_v3_pb2

from google.protobuf.message import Message as ProtoMessage

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
    sender: Sender

    @override
    def get_type(self) -> str:
        return "message"

    @override
    def get_message(self) -> Message:
        return self.message

    @override
    def get_user_id(self) -> str:
        return str(self.sender.uid)


@cmd("DANMU_MSG")
class DanmakuEvent(MessageEvent):
    time: float
    mode: int
    color: int
    font_size: int
    content: str
    emots: Optional[dict[str, Emoticon]] = None
    send_from_me: bool
    reply_mid: int
    reply_uname: str
    reply_uname_color: str
    to_me: bool = False

    """弹幕消息"""

    @override
    def get_event_name(self) -> str:
        return "danmaku"

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any]) -> Any:
        extra = json.loads(data["info"][0][15]["extra"])
        emots = extra["emots"]
        content = data["info"][1]
        user = data["info"][0][15]["user"]
        return {
            "time": data["info"][0][4] / 1000,
            "mode": data["info"][0][1],
            "color": data["info"][0][3],
            "font_size": data["info"][0][2],
            "content": content,
            "emots": emots or {},
            "send_from_me": extra["send_from_me"],
            "message": Message.construct(content, emots),
            "sender": {
                "uid": user["uid"],
                "face": user["base"]["face"],
                "name": user["base"]["name"],
                "name_color": user["base"]["name_color"],
                "medal": user["medal"],
            },
            "room_id": data["room_id"],
            "reply_mid": extra.get("reply_mid", 0),
            "reply_uname": extra.get("reply_uname", ""),
            "reply_uname_color": extra.get("reply_uname_color", ""),
        }

    @override
    def get_event_description(self) -> str:
        return (
            f"[Room@{self.room_id}] {self.sender.name}: "
            f"{f'@{self.reply_uname}' if self.reply_uname else ''} {self.content}"
        )

    @override
    def get_session_id(self) -> str:
        return f"{self.room_id}_{self.sender.uid}"

    @override
    def is_tome(self) -> bool:
        return self.to_me


@cmd("SUPER_CHAT_MSG")
class SuperChatEvent(MessageEvent):
    id: int
    price: float
    message_font_color: str
    start_time: float
    end_time: float
    message_trans: Optional[str] = None
    message_jpn: Optional[str] = None

    @override
    def get_event_name(self) -> str:
        return "super_chat"

    @override
    def get_message(self) -> Message:
        return self.message

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any]) -> Any:
        user = data["data"]["user_info"]
        return {
            "id": data["data"]["id"],
            "price": data["data"]["price"],
            "sender": {
                "uid": data["data"]["uid"],
                "face": user["face"],
                "name": user["uname"],
                "name_color": data["data"]["uinfo"].get("name_color", 0),
                "medal": data["data"]["uinfo"].get("medal", None),
            },
            "message": Message.construct(data["data"]["message"], None),
            "message_font_color": data["data"].get("message_font_color", ""),
            "start_time": data["data"]["start_time"] / 1000,
            "end_time": data["data"]["end_time"] / 1000,
            "message_trans": data["data"]["message_trans"],
            "message_jpn": data["data"].get("message_jpn", None),
            "room_id": data["room_id"],
        }

    @override
    def get_event_description(self) -> str:
        return (
            f"[Room@{self.room_id}] [￥{self.price}] {self.sender.name}: {self.message}"
        )

    @override
    def get_session_id(self) -> str:
        return f"{self.room_id}_{self.sender.uid}_{self.id}"


# notice event


class NoticeEvent(Event):
    @override
    def get_type(self) -> str:
        return "notice"

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any]) -> Any:
        return {
            "room_id": data["room_id"],
            **data["data"],
        }


# INTERACT_WORD


class _InteractWordEvent(NoticeEvent):
    msg_type: int
    timestamp: int
    trigger_time: int
    uid: int
    uname: str
    uname_color: str
    # fans_medal: Medal

    @override
    def get_user_id(self) -> str:
        return str(self.uid)

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any]) -> Any:
        if isinstance(data["data"], interact_word_v2_pb2.InteractWord):
            p = data["data"]
            return {
                "msg_type": p.msg_type,
                "timestamp": p.timestamp,
                "trigger_time": p.trigger_time,
                "uid": p.uid,
                "uname": p.uname,
                "uname_color": p.uname_color,
                "room_id": data["room_id"],
            }
        return {
            "msg_type": data["data"]["msg_type"],
            "timestamp": data["data"]["timestamp"],
            "trigger_time": data["data"]["trigger_time"],
            "uid": data["data"]["uid"],
            "uname": data["data"]["uname"],
            "uname_color": data["data"]["uname_color"],
            "room_id": data["room_id"],
        }


@cmd("INTERACT_WORD")
@cmd("INTERACT_WORD_V2", interact_word_v2_pb2.InteractWord)
class UserEnterEvent(_InteractWordEvent):
    msg_type: Literal[1]

    @override
    def get_event_name(self) -> str:
        return "user_enter"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} Entered the room"


@cmd("INTERACT_WORD")
@cmd("INTERACT_WORD_V2", interact_word_v2_pb2.InteractWord)
class UserFollowEvent(_InteractWordEvent):
    msg_type: Literal[2]

    @override
    def get_event_name(self) -> str:
        return "user_follow"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} Followed the room"


@cmd("INTERACT_WORD")
@cmd("INTERACT_WORD_V2", interact_word_v2_pb2.InteractWord)
class UserShareEvent(_InteractWordEvent):
    msg_type: Literal[3]

    @override
    def get_event_name(self) -> str:
        return "user_share"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} Shared the room"


@cmd("GUARD_BUY")
class GuardBuyEvent(NoticeEvent):
    uid: int
    username: str
    guard_level: GuardLevel
    num: int
    price: float
    gift_id: int
    gift_name: str
    time: int

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
    def validate(cls, data: dict[str, Any]) -> Any:
        return {
            "time": data["data"]["start_time"],
            "room_id": data["room_id"],
            **data["data"],
        }

    @override
    def get_user_id(self) -> str:
        return str(self.uid)


@cmd("GUARD_BUY_TOAST")
class GuardBuyToastEvent(NoticeEvent):
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
    def validate(cls, data: dict[str, Any]) -> Any:
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
class SendGiftEvent(NoticeEvent):
    gift_name: str
    num: int
    price: float
    timestamp: int
    total_coin: int
    uid: int
    uname: str
    face: str
    coin_type: Literal["gold", "silver"]
    # medal_info: Medal

    @override
    def get_event_name(self) -> str:
        return "send_gift"

    @override
    def get_event_description(self) -> str:
        return (
            f"[Room@{self.room_id}] [￥{self.price}] {self.uname} sent {self.num} "
            f"{self.gift_name}(s)"
        )

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any]) -> Any:
        return {
            "gift_name": data["data"]["giftName"],
            "room_id": data["room_id"],
            **data["data"],
        }

    @override
    def get_user_id(self) -> str:
        return str(self.uid)


@cmd("GIFT_STAR_PROCESS")
class GiftStarProcessEvent(NoticeEvent):
    status: int
    tip: str

    @override
    def get_event_name(self) -> str:
        return "gift_star_process"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.tip}"


@cmd("SPECIAL_GIFT")
class SpecialGiftEvent(NoticeEvent):
    gifts: dict[str, SpecialGift]

    @override
    def get_event_name(self) -> str:
        return "special_gift"

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any]) -> Any:
        return {
            "gifts": data["data"],
            "room_id": data["room_id"],
        }


# class NoticeMsgEvent(NoticeEvent):
@cmd("LIVE")
class LiveStartEvent(NoticeEvent):
    live_time: int
    live_platform: str

    @override
    def get_event_name(self) -> str:
        return "live_start"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Live started"


@cmd("ONLINE_RANK_V2")
@cmd("ONLINE_RANK_V3", online_rank_v3_pb2.GoldRankBroadcast)
class OnlineRankEvent(NoticeEvent):
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
    def validate(cls, data: dict[str, Any]) -> Any:
        if isinstance(data["data"], online_rank_v3_pb2.GoldRankBroadcast):
            p = data["data"]
            return {
                "online_list": [
                    type_validate_python(
                        Rank,
                        {
                            "uid": rank.uid,
                            "uname": rank.uname,
                            "face": rank.face,
                            "rank": rank.rank,
                            "score": rank.score,
                            "guard_level": rank.guard_level,
                        },
                    )
                    for rank in p.online_list
                ],
                "rank_type": p.rank_type,
                "room_id": data["room_id"],
            }
        return {
            "online_list": data["data"]["online_list"],
            "rank_type": data["data"]["rank_type"],
            "room_id": data["room_id"],
        }


@cmd("ONLINE_RANK_COUNT")
class OnlineRankCountEvent(NoticeEvent):
    count: int

    @override
    def get_event_name(self) -> str:
        return "online_rank_count"


@cmd("ONLINE_RANK_TOP3")
class OnlineRankTopEvent(NoticeEvent):
    top: list[RankChangeMsg]

    @override
    def get_event_name(self) -> str:
        return "online_rank_top"

    @override
    def get_event_description(self) -> str:
        msgs = [f"{d.msg} #{d.rank}" for d in self.top]
        return f"[Room@{self.room_id}] {' + '.join(msgs)}"


@cmd("LIKE_INFO_V3_UPDATE")
class LikeInfoUpdateEvent(NoticeEvent):
    click_count: int
    """点赞数"""

    @override
    def get_event_name(self) -> str:
        return "like_info_update"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] Click count updated: {self.click_count}"


@cmd("WATCHED_CHANGE")
class WatchedChangeEvent(NoticeEvent):
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
class StopLiveRoomListEvent(NoticeEvent):
    room_id_list: list[int]

    @override
    def get_event_name(self) -> str:
        return "stop_room_list"


def packet_to_event(packet: Packet, room_id: int) -> Event:
    data = packet.decode_dict()
    cmd = data.get("cmd", "")
    if packet.opcode == OpCode.HeartbeatReply.value:
        return HeartbeatEvent(popularity=data["popularity"], room_id=room_id)
    elif packet.opcode == OpCode.Command.value:
        if (pb := COMMAND_TO_PB.get(cmd)) is not None:
            # https://github.com/SocialSisterYi/bilibili-API-collect/issues/1332
            message = pb()
            message.ParseFromString(base64.b64decode(data["data"]["pb"]))
            data["data"] = message
        data["room_id"] = room_id
        log("TRACE", f"[{cmd}] Receive: {escape_tag(str(data))}")
        event_model = COMMAND_TO_EVENT.get(cmd)
        if event_model:
            return type_validate_python(event_model, data)
    raise RuntimeError(f"Unknown packet opcode: {packet.opcode} or command: {cmd}")
