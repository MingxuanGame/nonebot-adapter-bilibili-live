from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import time
from typing import TYPE_CHECKING, Any, Union
from typing_extensions import override
import uuid

from nonebot.adapters import Bot as BaseBot
from nonebot.compat import type_validate_python
from nonebot.drivers import URL, Request, Response
from nonebot.message import handle_event

from .const import PLATFORM_URL
from .event import DanmakuEvent, Event, SuperChatEvent
from .exception import ActionFailed, ApiNotAvailable
from .log import log
from .message import AtSegment, Message, MessageSegment
from .models.open import Game
from .models.room import MasterData, Room, UserRoomStatus
from .models.user_manage import SilentUserListData
from .utils import make_header
from .wbi import wbi_encode

if TYPE_CHECKING:
    from .adapter import _OpenplatformAdapterMixin, _WebApiAdapterMixin


def _check_to_me(bot: Bot, event: Event) -> None:
    if isinstance(event, DanmakuEvent):
        if isinstance(bot, OpenBot):
            master_open_id = bot.games[event.room_id].open_id
            event.to_me = master_open_id == event.reply_open_id
        else:
            event.to_me = int(bot.self_id) == (event.reply_mid)
    elif isinstance(event, SuperChatEvent):
        if isinstance(bot, OpenBot):
            event.to_me = True
        elif isinstance(bot, WebBot):
            master_id = bot.rooms[event.room_id].uid
            event.to_me = int(bot.self_id) == master_id


class Bot(BaseBot):
    async def _handle_event(self, event: Event) -> None:
        _check_to_me(self, event)
        await handle_event(self, event)


class WebBot(Bot):
    adapter: "_WebApiAdapterMixin"

    def __init__(
        self,
        adapter: "_WebApiAdapterMixin",
        self_id: str,
        img_key: str,
        sub_key: str,
        cookie: dict[str, str],
    ):
        super().__init__(adapter, self_id)
        self.img_key = img_key
        self.sub_key = sub_key
        self.rooms: dict[int, Room] = {}
        self.cookie = cookie
        self.seq = 0
        self._today = datetime.datetime.now().day

    async def _wbi_encode(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Encode data with WBI keys."""
        if datetime.datetime.now().day != self._today:
            # Update wbi key
            self.img_key, self.sub_key, _ = await self.adapter._get_wbi_keys(
                self.cookie
            )
            self._today = datetime.datetime.now().day
        return wbi_encode(data or {}, self.img_key, self.sub_key)

    async def _request(self, req: Request) -> Response:
        req.headers.update(make_header())
        req.cookies.update(self.cookie)
        return await self.adapter.request(req)

    async def _request_api(self, req: Request) -> dict[str, Any]:
        resp = await self._request(req)
        if not resp.content:
            raise ApiNotAvailable()
        data = json.loads(resp.content)
        if data["code"] != 0:
            raise ActionFailed(
                code=data["code"],
                message=data.get("message", "Unknown error"),
            )
        return data["data"]

    async def send_danmaku(
        self, room_id: int, msg: str, mode: int = 1, reply_mid: int = 0
    ) -> None:
        """发送弹幕

        Args:
            room_id: 直播间Id
            msg: 弹幕内容
            mode: 弹幕发送模式
            reply_mid: 回复的用户mid，默认为0表示不回复

        Returns:
            None
        """
        csrf = self.cookie.get("bili_jct", "")
        request = Request(
            "POST",
            "https://api.live.bilibili.com/msg/send",
            params=await self._wbi_encode({}),
            data={
                "roomid": room_id,
                "msg": msg,
                "mode": mode,
                "rnd": int(datetime.datetime.now().timestamp()),
                "csrf": csrf,
                "csrf_token": csrf,
                "color": 16777215,  # Default color
                "fontsize": 25,  # Default font size
                "bubble": 0,  # Default bubble
                "reply_mid": reply_mid,
            },
        )
        await self._request_api(request)

    async def get_room_info(self, room_id: int) -> Room:
        request = Request(
            "GET",
            "https://api.live.bilibili.com/room/v1/Room/get_info",
            params=await self._wbi_encode({"room_id": room_id}),
        )
        data = await self._request_api(request)
        return type_validate_python(Room, data)

    async def get_user_room_status(self, mid: int) -> UserRoomStatus:
        """获取用户对应的直播间状态

        Args:
            mid: 目标用户mid

        Returns:
            UserRoomStatus: 用户直播间状态信息
        """
        request = Request(
            "GET",
            "https://api.live.bilibili.com/room/v1/Room/getRoomInfoOld",
            params={"mid": mid},
        )
        data = await self._request_api(request)
        return type_validate_python(UserRoomStatus, data)

    async def get_master_info(self, uid: int) -> MasterData:
        """获取主播信息

        Args:
            uid: 目标用户mid

        Returns:
            MasterData: 主播信息数据
        """
        request = Request(
            "GET",
            "https://api.live.bilibili.com/live_user/v1/Master/info",
            params={"uid": uid},
        )
        data = await self._request_api(request)
        return type_validate_python(MasterData, data)

    async def add_silent_user(
        self,
        room_id: int,
        tuid: int,
        hour: int,
        msg: str = "",
        visit_id: str = "",
    ) -> None:
        """禁言观众

        Args:
            room_id: 直播间Id
            tuid: 要禁言的uid
            hour: 禁言时长，-1为永久，0为本场直播
            msg: 要禁言的弹幕内容（可选）
            visit_id: 访问ID（可选）
        """
        csrf = self.cookie.get("bili_jct", "")
        request = Request(
            "POST",
            "https://api.live.bilibili.com/xlive/web-ucenter/v1/banned/AddSilentUser",
            data={
                "room_id": str(room_id),
                "tuid": str(tuid),
                "msg": msg,
                "mobile_app": "web",
                "hour": hour,
                "csrf_token": csrf,
                "csrf": csrf,
                "visit_id": visit_id,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        await self._request_api(request)

    async def get_silent_user_list(
        self, room_id: int, ps: int = 1, visit_id: str = ""
    ) -> SilentUserListData:
        """查询直播间禁言列表

        Args:
            room_id: 直播间Id
            ps: 列表页码
            visit_id: 访问ID（可选）

        Returns:
            SilentUserListData: 禁言用户列表数据
        """
        csrf = self.cookie.get("bili_jct", "")
        request = Request(
            "POST",
            "https://api.live.bilibili.com/xlive/web-ucenter/v1/banned/GetSilentUserList",
            data={
                "room_id": str(room_id),
                "ps": str(ps),
                "csrf_token": csrf,
                "csrf": csrf,
                "visit_id": visit_id,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = await self._request_api(request)
        return type_validate_python(SilentUserListData, data)

    async def del_silent_user(
        self, room_id: int, silent_id: int, visit_id: str = ""
    ) -> None:
        """解除禁言

        Args:
            room_id: 直播间Id
            silent_id: 禁言记录Id（从GetSilentUserList接口获取）
            visit_id: 访问ID（可选）
        """
        csrf = self.cookie.get("bili_jct", "")
        request = Request(
            "POST",
            "https://api.live.bilibili.com/banned_service/v1/Silent/del_room_block_user",
            data={
                "roomid": str(room_id),  # 注意该接口使用roomid而非room_id
                "id": str(silent_id),
                "csrf_token": csrf,
                "csrf": csrf,
                "visit_id": visit_id,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        await self._request_api(request)

    @override
    async def send(
        self,
        event: Event,
        message: Union[str, Message, MessageSegment],
        reply_message: bool = False,
        **kwargs,
    ) -> Any:
        """发送消息

        Args:
            event: 事件对象
            message: 消息内容，可以是字符串、Message对象或MessageSegment对象
            reply_message: 是否回复消息
            **kwargs: 其他参数

        Returns:
            Any: 发送结果
        """
        reply_mid = 0
        if reply_message:
            try:
                reply_mid = int(event.get_user_id())
            except ValueError:
                log("WARNING", "Event has no user_id, cannot reply")
        if isinstance(message, AtSegment):
            reply_mid = message.data.get("uid", 0)
        if isinstance(message, MessageSegment):
            message = str(message)
        elif isinstance(message, Message):
            reply_mid = message["at"][-1].data.get("uid", 0) if message["at"] else 0
            message = "".join(str(seg) for seg in message)
        return await self.send_danmaku(
            event.room_id, message, reply_mid=reply_mid, **kwargs
        )


class OpenBot(Bot):
    adapter: "_OpenplatformAdapterMixin"

    def __init__(
        self,
        adapter: "_OpenplatformAdapterMixin",
        self_id: str,
        access_secret: str,
        app_id: int,
    ):
        super().__init__(adapter, self_id)
        self.access_key = self_id
        self.access_secret = access_secret
        self.app_id = app_id

        self.games: dict[int, Game] = {}

    def make_request(self, path: str, data: dict[str, Any]) -> Request:
        content = json.dumps(data, ensure_ascii=False)
        x_bili_header = {
            "x-bili-accesskeyid": self.access_key,
            "x-bili-content-md5": hashlib.md5(content.encode("utf-8")).hexdigest(),
            "x-bili-signature-method": "HMAC-SHA256",
            "x-bili-signature-nonce": str(uuid.uuid4()),
            "x-bili-signature-version": "1.0",
            "x-bili-timestamp": str(round(time.time())),
        }
        return Request(
            method="POST",
            url=URL(PLATFORM_URL).joinpath(path),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": hmac.new(
                    self.access_secret.encode("utf-8"),
                    "\n".join((f"{k}:{v}" for k, v in x_bili_header.items())).encode(
                        "utf-8"
                    ),
                    hashlib.sha256,
                ).hexdigest(),
                **x_bili_header,
            },
            content=content,
        )

    @override
    async def send(
        self,
        event: Event,
        message: Union[str, Message, MessageSegment],
        reply_message: bool = False,
        **kwargs,
    ) -> Any:
        raise ApiNotAvailable

    async def _close(self) -> None:
        for game in self.games.values():
            request = self.make_request(
                "v2/app/end",
                {"app_id": self.app_id, "game_id": game.game_id},
            )
            _ = await self.adapter.request(request)
        self.games.clear()
