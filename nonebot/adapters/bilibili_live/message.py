from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
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
        return f"[{self.data['emoji']}]"


class Message(BaseMessage[MessageSegment]):
    @classmethod
    @override
    def get_segment_class(cls) -> type[MessageSegment]:
        return MessageSegment

    @staticmethod
    @override
    def _construct(msg: str) -> Iterable[MessageSegment]:
        # just implement it, use `construct` to construct the accurate message
        messages = []
        cached_text = []
        cached_emoticon = []
        in_emoticon = False
        for s in msg:
            if s == "[":
                in_emoticon = True
                if cached_text:
                    messages.append(MessageSegment.text(" ".join(cached_text)))
                    cached_text = []
            elif s == "]":
                in_emoticon = False
                if cached_emoticon:
                    messages.append(MessageSegment.emoticon("".join(cached_emoticon)))
                    cached_emoticon = []
            elif in_emoticon:
                cached_emoticon.append(s)
            else:
                cached_text.append(s)
        return messages

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
            elif s == "]":
                in_emoticon = False
                if cached_emoticon:
                    emoticon_str = "".join(cached_emoticon)
                    if emoticon_str in emots:
                        segments.append(
                            MessageSegment.emoticon(emots[emoticon_str]["emoji"])
                        )
                    else:
                        segments.append(MessageSegment.text(f"[{emoticon_str}]"))
                    cached_emoticon = []
            elif in_emoticon:
                cached_emoticon.append(s)
            else:
                cached_text.append(s)
        if cached_text:
            segments.append(MessageSegment.text("".join(cached_text)))
        return cls(segments)
