from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message as ProtobufMessage

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/102.0.0.0 Safari/537.36"
)


def make_header() -> dict[str, str]:
    return {
        "User-Agent": UA,
        "Referer": "https://live.bilibili.com/",
        "Origin": "https://live.bilibili.com",
    }


def cookie_str_to_dict(cookie_str: str) -> dict[str, str]:
    cookie = SimpleCookie()
    cookie.load(cookie_str)
    return {key: morsel.value for key, morsel in cookie.items()}


def pb_to_dict(message: ProtobufMessage) -> dict[str, Any]:
    return MessageToDict(
        message,
        preserving_proto_field_name=True,
    )
