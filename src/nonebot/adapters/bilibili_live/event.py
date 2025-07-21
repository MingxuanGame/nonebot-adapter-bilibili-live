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
from .message import Emoticon, Message
from .models.event import (
    BatchComboSend,
    BlindGift,
    ComboInfo,
    GuardLevel,
    Rank,
    RankChangeMsg,
    SpecialGift,
    User,
)
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


@cmd("DANMU_MSG")
@cmd("LIVE_OPEN_PLATFORM_DM")
class DanmakuEvent(MessageEvent):
    time: float
    mode: int
    color: int
    font_size: int
    content: str
    emots: Optional[dict[str, Emoticon]] = None
    send_from_me: bool
    reply_mid: int
    reply_open_id: str
    reply_uname: str
    reply_uname_color: str
    to_me: bool = False
    msg_id: str = ""

    @override
    def get_event_name(self) -> str:
        return "danmaku"

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any]) -> Any:
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
                # medal
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
            sender = User(
                uid=user["uid"],
                face=user["base"]["face"],
                name=user["base"]["name"],
                name_color=user["base"]["name_color"],
                medal=user["medal"],
            )
            msg_id = ""
            color = data["info"][0][3]
            font_size = data["info"][0][2]
        return {
            "time": time,
            "mode": mode,
            "color": color,
            "font_size": font_size,
            "content": content,
            "emots": emots or {},
            "send_from_me": send_from_me,
            "message": Message.construct(content, emots),
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


@cmd("SUPER_CHAT_MSG")
@cmd("SUPER_CHAT_MESSAGE_JPN")
@cmd("LIVE_OPEN_PLATFORM_SUPER_CHAT")
class SuperChatEvent(MessageEvent):
    id: int
    price: float
    message_font_color: str
    start_time: float
    end_time: float
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
    def validate(cls, data: dict[str, Any]) -> Any:
        data_ = data["data"]
        if "open_id" in data_:
            sender = User(
                uid=data_["uid"],
                face=data_["uface"],
                name=data_["uname"],
                open_id=data_["open_id"],
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
                medal=user.get("medal", None),
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
    def validate(cls, data: dict[str, Any]) -> Any:
        return {
            "room_id": data["room_id"],
            **data["data"],
        }


# INTERACT_WORD


def _interact_word_validator(data: dict[str, Any]) -> dict[str, Any]:
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
        return _interact_word_validator(data)


@cmd("INTERACT_WORD")
@cmd("INTERACT_WORD_V2", interact_word_v2_pb2.InteractWord)
@cmd("LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER")
class UserEnterEvent(_InteractWordEvent):
    msg_type: Literal[1]
    open_id: str = ""

    @override
    def get_event_name(self) -> str:
        return "user_enter"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} Entered the room"

    @model_validator(mode="before")
    @classmethod
    @override
    def validate(cls, data: dict[str, Any]) -> Any:
        if (
            isinstance(data["data"], interact_word_v2_pb2.InteractWord)
            or "open_id" not in data["data"]
        ):
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
@cmd("INTERACT_WORD_V2", interact_word_v2_pb2.InteractWord)
class UserFollowEvent(_InteractWordEvent, WebOnlyEvent):
    msg_type: Literal[2]

    @override
    def get_event_name(self) -> str:
        return "user_follow"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} Followed the room"


@cmd("INTERACT_WORD")
@cmd("INTERACT_WORD_V2", interact_word_v2_pb2.InteractWord)
class UserShareEvent(_InteractWordEvent, WebOnlyEvent):
    msg_type: Literal[3]

    @override
    def get_event_name(self) -> str:
        return "user_share"

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.uname} Shared the room"


@cmd("GUARD_BUY")
@cmd("LIVE_OPEN_PLATFORM_GUARD")
class GuardBuyEvent(NoticeEvent):
    uid: int
    open_id: str = ""
    face: str = ""
    username: str
    guard_level: GuardLevel
    guard_unit: str = ""
    num: int = 1
    price: float
    gift_id: int
    gift_name: str
    time: int
    msg_id: str = ""

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
        if "user_info" in data["data"]:
            data["data"]["uid"] = data["data"]["user_info"]["uid"]
            data["data"]["face"] = data["data"]["user_info"]["uface"]
            data["data"]["username"] = data["data"]["user_info"]["uname"]
            data["data"]["open_id"] = data["data"]["user_info"]["open_id"]
            data["num"] = data["data"]["guard_num"]
        return {
            "time": data["data"].get("start_time", data["data"]["timestamp"]),
            "room_id": data["room_id"],
            **data["data"],
        }

    @override
    def get_user_id(self) -> str:
        return str(self.uid) if self.open_id == "" else self.open_id


@cmd("GUARD_BUY_TOAST")
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
@cmd("LIVE_OPEN_PLATFORM_SEND_GIFT")
class SendGiftEvent(NoticeEvent, WebOnlyEvent):
    gift_name: str
    num: int
    price: float
    timestamp: int
    uid: int
    uname: str
    face: str
    guard_level: Optional[int] = None
    receive_user_info: Optional[User] = None

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
    blind_gift: Optional[BlindGift] = None

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
    def validate(cls, data: dict[str, Any]) -> Any:
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
            }
        else:
            # WebBot
            result = {
                "room_id": data["room_id"],
                **data_obj,
                "receive_user_info": User(
                    uid=data_obj["receive_user_info"]["uid"],
                    name=data_obj["receive_user_info"]["uname"],
                ),
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
    def validate(cls, data: dict[str, Any]) -> Any:
        return {
            "gifts": data["data"],
            "room_id": data["room_id"],
        }


# # class NoticeMsgEvent(NoticeEvent):
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
@cmd("ONLINE_RANK_V3", online_rank_v3_pb2.GoldRankBroadcast)
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
            message.ParseFromString(base64.b64decode(data["data"]["pb"]))
            data["data"] = message
        data["room_id"] = room_id
        log("TRACE", f"[{cmd}] Receive: {escape_tag(str(data))}")
        event_model = COMMAND_TO_EVENT.get(cmd)
        if event_model:
            return type_validate_python(event_model, data)
    raise RuntimeError(f"Unknown packet opcode: {packet.opcode} or command: {cmd}")
