from __future__ import annotations

import json
from typing import Any
from typing_extensions import override

from nonebot.adapters import Event as BaseEvent
from nonebot.compat import model_dump, model_validator, type_validate_python

from .message import Emoticon, Message
from .models.danmaku import Sender
from .packet import OpCode, Packet


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
    @override
    def get_type(self) -> str:
        return "message"


class DanmakuEvent(MessageEvent):
    message: Message
    time: float
    mode: int
    color: int
    font_size: int
    content: str
    emots: dict[str, Emoticon]
    send_from_me: bool
    sender: Sender

    """弹幕消息"""

    @override
    def get_event_name(self) -> str:
        return "danmaku"

    @override
    def get_message(self) -> Message:
        return self.message

    @model_validator(mode="before")
    @classmethod
    def validate(cls, data: dict[str, Any]) -> Any:
        extra = json.loads(data["info"][0][15]["extra"])
        emots = extra["emots"]
        content = data["info"][1]
        return {
            "time": data["info"][0][4] / 1000,
            "mode": data["info"][0][1],
            "color": data["info"][0][3],
            "font_size": data["info"][0][2],
            "content": content,
            "emots": emots or {},
            "send_from_me": extra["send_from_me"],
            "message": Message.construct(content, emots),
            "sender": data["info"][0][15]["user"],
            **data,
        }

    @override
    def get_event_description(self) -> str:
        return f"[Room@{self.room_id}] {self.sender.base.name}: {self.content}"


class NoticeEvent(Event):
    @override
    def get_type(self) -> str:
        return "notice"


COMMAND_TO_EVENT = {"DANMU_MSG": DanmakuEvent}


def packet_to_event(packet: Packet, room_id: int) -> Event:
    data = packet.decode_dict()
    if packet.opcode == OpCode.HeartbeatReply.value:
        return HeartbeatEvent(popularity=data["popularity"], room_id=room_id)
    elif packet.opcode == OpCode.Command.value:
        data["room_id"] = room_id
        event_model = COMMAND_TO_EVENT.get(data["cmd"])
        if event_model:
            return type_validate_python(event_model, data)
    raise ValueError(
        f"Unknown packet opcode: {packet.opcode} or command: {data.get('cmd')}"
    )
