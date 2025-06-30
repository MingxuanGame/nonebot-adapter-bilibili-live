from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Union
from typing_extensions import override

from nonebot.adapters import Bot as BaseBot
from nonebot.drivers import Request, Response

from .event import Event
from .message import Message, MessageSegment
from .utils import make_header
from .wbi import wbi_encode

if TYPE_CHECKING:
    from .adapter import Adapter


class Bot(BaseBot):
    adapter: "Adapter"

    def __init__(
        self,
        adapter: "Adapter",
        self_id: str,
        img_key: str,
        sub_key: str,
        rooms: list[int],
        cookie: dict[str, str],
    ):
        super().__init__(adapter, self_id)
        self.img_key = img_key
        self.sub_key = sub_key
        self.rooms = rooms
        self.cookie = cookie
        self.seq = 0
        self._today = datetime.datetime.now().day

    async def wbi_encode(self, data: dict[str, Any]) -> dict[str, Any]:
        """Encode data with WBI keys."""
        if datetime.datetime.now().day != self._today:
            # Update wbi key
            self.img_key, self.sub_key, _ = await self.adapter._get_wbi_keys(
                self.cookie
            )
            self._today = datetime.datetime.now().day
        return wbi_encode(data, self.img_key, self.sub_key)

    async def _request(self, req: Request) -> Response:
        req.headers.update(make_header())
        req.cookies.update(self.cookie)
        return await self.adapter.request(req)

    @override
    async def send(
        self,
        event: Event,
        message: Union[str, Message, MessageSegment],
        **kwargs,
    ) -> Any: ...
