from __future__ import annotations

import asyncio
import json
from typing import Any, NoReturn
from typing_extensions import override

from nonebot import get_plugin_config
from nonebot.adapters import Adapter as BaseAdapter
from nonebot.drivers import (
    URL,
    Driver,
    Request,
    WebSocket,
)
from nonebot.exception import WebSocketClosed
from nonebot.message import handle_event

from .bot import Bot
from .config import BLiveBot, Config
from .event import packet_to_event
from .exception import ApiNotAvailable
from .log import log
from .packet import OpCode, Packet, new_auth_packet
from .utils import UA, cookie_str_to_dict, make_header
from .wbi import get_key

# https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/login/login_info.md#%E5%AF%BC%E8%88%AA%E6%A0%8F%E7%94%A8%E6%88%B7%E4%BF%A1%E6%81%AF
NAV_API = "https://api.bilibili.com/x/web-interface/nav"
# https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/live/message_stream.md#%E8%8E%B7%E5%8F%96%E4%BF%A1%E6%81%AF%E6%B5%81%E8%AE%A4%E8%AF%81%E7%A7%98%E9%92%A5
AUTH_URL = "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo"
# https://github.com/SocialSisterYi/bilibili-API-collect/blob/c923eab77c3d64ad4acf8c2b919c970db7244a47/docs/misc/buvid3_4.md#%E4%BB%85%E8%8E%B7%E5%8F%96-buvid3
BUVID3_URL = "https://www.bilibili.com"

HEARTBEAT_INTERVAL = 30
RECONNECT_INTERVAL = 5


class Adapter(BaseAdapter):
    @override
    def __init__(self, driver: Driver, **kwargs: Any):
        super().__init__(driver, **kwargs)
        self.adapter_config = get_plugin_config(Config)
        self.bots: dict[str, Bot] = {}
        self.tasks = set()
        self.ws = set()
        self.setup()

    def setup(
        self,
    ):
        self.driver.on_startup(self.startup)
        self.driver.on_shutdown(self.shutdown)

    async def _get_wbi_keys(self, cookie: dict[str, str]) -> tuple[str, str, int]:
        req = Request(
            "GET",
            URL(NAV_API),
            headers=make_header(),
            cookies=cookie,
        )
        resp = await self.request(req)
        if not resp.content:
            raise RuntimeError(f"Failed to login: {resp.status_code}")
        data = json.loads(resp.content)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to login: {resp.status_code}, "
                f"{data.get('message', 'Unknown error')}"
            )
        img_key = data["data"]["wbi_img"]["img_url"]
        sub_key = data["data"]["wbi_img"]["sub_url"]
        return get_key(img_key), get_key(sub_key), data["data"]["mid"]

    async def startup(self):
        for botconf in self.adapter_config.bilibili_live_bots:
            await self._login(botconf)

    async def shutdown(self):
        self.ws.clear()
        for task in self.tasks:
            task.cancel()
        self.tasks.clear()
        for bot in self.bots.copy().values():
            self.bot_disconnect(bot)
        self.bots.clear()

    async def _login(self, botconf: BLiveBot):
        img_key, sub_key, mid = await self._get_wbi_keys(
            cookie_str_to_dict(botconf.cookie)
        )
        bot = Bot(
            self,
            self_id=str(mid),
            img_key=img_key,
            sub_key=sub_key,
            rooms=botconf.room_ids,
            cookie=cookie_str_to_dict(botconf.cookie),
        )
        self.bot_connect(bot)
        for room_id in botconf.room_ids:
            task = asyncio.create_task(self._listen_room(bot, room_id))
            task.add_done_callback(self.tasks.discard)

    async def _request_buvid3(self, bot: Bot) -> str:
        request = Request("GET", URL(BUVID3_URL), headers=make_header())
        resp = await self.request(request)
        return resp.headers["set-cookie"].split(";")[0].split("=")[1]

    async def _auth(self, bot: Bot, room_id: int) -> dict[str, Any]:
        request = Request(
            "GET",
            URL(AUTH_URL),
            params=await bot._wbi_encode({"id": room_id, "type": 0}),
        )
        resp = await bot._request(request)
        if resp.status_code != 200 or not resp.content:
            raise RuntimeError(
                f"Failed to get auth info: {resp.status_code}, {resp.content}"
            )
        data = json.loads(resp.content)
        if data.get("code") != 0:
            raise RuntimeError(
                f"Failed to get auth info: {data.get('code')}, {data.get('message')}"
            )
        return data["data"]

    async def _listen_room(self, bot: Bot, room_id: int):
        buvid3 = await self._request_buvid3(bot)
        bot.cookie["buvid3"] = buvid3
        room_id = (await bot.get_room_info(room_id)).room_id
        heartbeat_task: asyncio.Task[NoReturn] | None = None
        while True:
            auth_info = await self._auth(bot, room_id)
            token = auth_info["token"]
            host = auth_info["host_list"][0]["host"]
            port = auth_info["host_list"][0]["wss_port"]

            ws = Request(
                "GET",
                URL(f"wss://{host}:{port}/sub"),
                headers={
                    "User-Agent": UA,
                },
                timeout=30,
                cookies=bot.cookie,
            )
            async with self.websocket(ws) as ws_conn:
                try:
                    await ws_conn.send_bytes(
                        new_auth_packet(
                            room_id, int(bot.self_id), token, bot.cookie["buvid3"]
                        ).to_bytes()
                    )
                    packet = Packet.from_bytes(await ws_conn.receive_bytes())
                    bot.seq = packet.seq
                    self.ws.add(ws_conn)
                    log(
                        "SUCCESS",
                        f"[{bot.self_id}] Connected to room {room_id} successfully.",
                    )
                    heartbeat_task = asyncio.create_task(self._heartbeat(bot, ws_conn))
                    await self._ws_loop(bot, ws_conn, room_id)
                except WebSocketClosed as e:
                    log(
                        "ERROR",
                        "<r><bg #f8bbd0>WebSocket Closed</bg #f8bbd0></r>",
                        e,
                    )
                except Exception as e:
                    log(
                        "ERROR",
                        (
                            "<r><bg #f8bbd0>Error while process data from"
                            f" room {room_id}. "
                            "Trying to reconnect...</bg #f8bbd0></r>"
                        ),
                        e,
                    )
                finally:
                    if ws_conn in self.ws:
                        self.ws.remove(ws_conn)
                    if heartbeat_task:
                        heartbeat_task.cancel()
                        heartbeat_task = None
                await asyncio.sleep(RECONNECT_INTERVAL)

    async def _ws_loop(self, bot: Bot, ws: WebSocket, room_id: int):
        while True:
            data = await ws.receive_bytes()
            await self._handle_ws_message(bot, data, room_id)

    async def _handle_ws_message(self, bot: Bot, data: bytes, room_id: int):
        offset = 0
        try:
            packet = Packet.from_bytes(data[offset:])
        except Exception:
            log(
                "ERROR",
                f"room={room_id} parsing header failed, "
                f"offset={offset}, data length={len(data)}",
            )
            return

        if packet.opcode in (OpCode.Command, OpCode.AuthReply):
            while True:
                try:
                    current_packet = Packet.from_bytes(
                        data[offset : offset + packet.length]
                    )
                    await self._handle_business_message(bot, current_packet, room_id)

                    offset += packet.length
                    if offset >= len(data):
                        break

                    packet = Packet.from_bytes(data[offset:])
                except Exception:
                    log(
                        "ERROR",
                        f"room={room_id} parsing packet failed, "
                        f"offset={offset}, data length={len(data)}",
                    )
                    break
        else:
            # 单个包，直接处理
            await self._handle_business_message(bot, packet, room_id)

    async def _handle_business_message(self, bot: Bot, packet: Packet, room_id: int):
        try:
            decoded_data = packet.decode_data()
            if isinstance(decoded_data, list):
                for sub_packet in decoded_data:
                    event = packet_to_event(sub_packet, room_id)
                    task = asyncio.create_task(handle_event(bot, event))
                    self.tasks.add(task)
                    task.add_done_callback(self.tasks.discard)
            else:
                event = packet_to_event(packet, room_id)
                task = asyncio.create_task(handle_event(bot, event))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
        except RuntimeError as e:
            log("DEBUG", f"{e}")
        except Exception as e:
            log("ERROR", f"Error processing business message for room {room_id}", e)

    async def _heartbeat(self, bot: Bot, ws: WebSocket):
        while True:
            try:
                await ws.send_bytes(
                    Packet.new_binary(OpCode.Heartbeat, bot.seq, b"").to_bytes()
                )
                bot.seq += 1
            except Exception as e:
                log("WARNING", "Error while sending heartbeat, Ignored!", e)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    @classmethod
    @override
    def get_name(cls) -> str:
        return "Bilibili Live"

    @override
    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:
        log("DEBUG", f"Bot {bot.self_id} calling API <y>{api}</y>")
        api_handler = getattr(bot.__class__, api, None)
        if api.startswith("_") or api_handler is None:
            raise ApiNotAvailable
        return await api_handler(bot, **data)
