from __future__ import annotations

from nonebot.exception import (
    ActionFailed as BaseActionFailed,
    AdapterException,
    ApiNotAvailable as BaseApiNotAvailable,
)


class BilibiliLiveAdapterException(AdapterException):
    def __init__(self):
        super().__init__("Bilibili Live")


class ApiNotAvailable(BaseApiNotAvailable, BilibiliLiveAdapterException): ...


class ActionFailed(BaseActionFailed, BilibiliLiveAdapterException):
    code: int
    message: str

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"ActionFailed(code={self.code!r}, message={self.message!r})"
