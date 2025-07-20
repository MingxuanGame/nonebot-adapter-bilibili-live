from __future__ import annotations

from http.cookies import SimpleCookie
from typing import TypeVar

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


T = TypeVar("T")


def split_list(list_: list[T], n: int) -> list[list[T]]:
    return [list_[i : i + n] for i in range(0, len(list_), n)]
