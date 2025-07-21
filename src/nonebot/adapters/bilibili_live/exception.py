from __future__ import annotations

from nonebot.exception import (
    ActionFailed as BaseActionFailed,
    AdapterException,
    ApiNotAvailable as BaseApiNotAvailable,
    NetworkError as BaseNetworkError,
)


class InteractionEndException(Exception):
    def __init__(self, game_id: str, timestamp: int) -> None:
        self.game_id = game_id
        self.timestamp = timestamp


class BilibiliLiveAdapterException(AdapterException):
    def __init__(self):
        super().__init__("bilibili Live")


class ApiNotAvailable(BaseApiNotAvailable, BilibiliLiveAdapterException): ...


class ActionFailed(BaseActionFailed, BilibiliLiveAdapterException):
    code: int
    message: str

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"ActionFailed(code={self.code!r}, message={self.message!r})"


class NetworkError(BilibiliLiveAdapterException, BaseNetworkError): ...
