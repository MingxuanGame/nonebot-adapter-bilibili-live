from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Literal, TypedDict
from typing_extensions import override

from nonebot.adapters import (
    Message as BaseMessage,
    MessageSegment as BaseMessageSegment,
)


class MessageSegment(BaseMessageSegment["Message"]):
    @classmethod
    @override
    def get_message_class(cls) -> type["Message"]:
        return Message

    @override
    def __repr__(self) -> str:
        return self.__str__()

    @override
    def __str__(self) -> str:
        return f"[{self.type}]{self.data.get('text', '')}[/{self.type}]"

    @override
    def is_text(self) -> bool:
        return self.type == "text"

    @staticmethod
    def text(text: str) -> "TextSegment":
        return TextSegment(type="text", data={"text": text})

    @staticmethod
    def at(user_id: int | str, name: str | None = None) -> "AtSegment":
        is_uid = isinstance(user_id, int) or (
            isinstance(user_id, str) and user_id.isdigit()
        )
        return AtSegment(
            type="at",
            data={
                "uid": int(user_id) if is_uid else 0,
                "open_id": str(user_id) if not is_uid else "",
                "name": name,
            },
        )

    @staticmethod
    def emoticon(emoji: str) -> "EmoticonSegment":
        return EmoticonSegment(
            type="emoticon",
            data={
                "descript": emoji,
                "emoji": emoji,
                "emoticon_id": 0,
                "emoticon_unique": "",
                "height": 0,
                "width": 0,
                "url": "",
            },
        )


class Text(TypedDict):
    text: str


@dataclass
class TextSegment(MessageSegment):
    if TYPE_CHECKING:
        type: Literal["text"]
        data: Text  # type: ignore

    @override
    def __str__(self) -> str:
        return self.data["text"]


class Emoticon(TypedDict):
    descript: str
    emoji: str
    emoticon_id: int
    emoticon_unique: str
    height: int
    width: int
    url: str


@dataclass
class EmoticonSegment(MessageSegment):
    if TYPE_CHECKING:
        type: Literal["emoticon"]
        data: Emoticon  # type: ignore

    @override
    def __str__(self) -> str:
        return f"<emoticon:{self.data['emoji']}>"


class At(TypedDict):
    uid: int
    open_id: str
    name: str | None


@dataclass
class AtSegment(MessageSegment):
    if TYPE_CHECKING:
        type: Literal["at"]
        data: At  # type: ignore

    @property
    def user_id(self) -> int | str:
        return self.data["uid"] or self.data["open_id"]

    @property
    def name(self) -> str | None:
        return self.data["name"]

    @property
    def open_id(self) -> str:
        assert self.data["open_id"]
        return self.data["open_id"]

    @property
    def uid(self) -> int:
        assert self.data["uid"]
        return self.data["uid"]

    @override
    def __str__(self) -> str:
        return f"<at:{self.user_id}>"


class Message(BaseMessage[MessageSegment]):
    @classmethod
    @override
    def get_segment_class(cls) -> type[MessageSegment]:
        return MessageSegment

    @staticmethod
    @override
    def _construct(msg: str) -> Iterable[MessageSegment]:
        text_begin = 0
        for embed in re.finditer(
            r"\<(?P<type>(?:at:|emoticon:))!?(?P<id>\w+?)\>",
            msg,
        ):
            content = msg[text_begin : embed.pos + embed.start()]
            if content:
                yield MessageSegment.text(content)
            text_begin = embed.pos + embed.end()
            if embed.group("type") == "at:":
                yield MessageSegment.at(
                    user_id=embed.group("id"),
                )
            else:
                yield MessageSegment.emoticon(
                    emoji=embed.group("id"),
                )
        content = msg[text_begin:]
        if content:
            yield MessageSegment.text(content)

    @classmethod
    def construct(cls, msg: str, emots: dict[str, Emoticon] | None) -> "Message":
        segments = []
        cached_text = []
        cached_emoticon = []
        in_emoticon = False
        if not emots:
            emots = {}
        for s in msg:
            if s == "[":
                in_emoticon = True
                if cached_text:
                    segments.append(MessageSegment.text("".join(cached_text)))
                    cached_text = []
                cached_emoticon.append(s)
            elif s == "]":
                cached_emoticon.append(s)
                in_emoticon = False
                if cached_emoticon:
                    emoticon_str = "".join(cached_emoticon)
                    if emoticon_str in emots:
                        segments.append(
                            EmoticonSegment(type="emoticon", data=emots[emoticon_str])
                        )
                    else:
                        segments.append(MessageSegment.text(emoticon_str))
                    cached_emoticon = []
            elif in_emoticon:
                cached_emoticon.append(s)
            else:
                cached_text.append(s)
        if cached_text:
            segments.append(MessageSegment.text("".join(cached_text)))
        if cached_emoticon:
            segments.append(MessageSegment.text("".join(cached_emoticon)))
        return cls(segments)
