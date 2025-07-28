from __future__ import annotations

import asyncio
import json
from typing import Any
from typing_extensions import override

from nonebot import get_plugin_config
from nonebot.adapters import Adapter as BaseAdapter
from nonebot.drivers import (
    URL,
    Driver,
    HTTPClientMixin,
    Request,
    WebSocket,
    WebSocketClientMixin,
)
from nonebot.exception import WebSocketClosed

from .bot import Bot, OpenBot, WebBot
from .config import Config, OpenBotConf, WebBotConf
from .const import (
    AUTH_URL,
    BUVID3_URL,
    GAME_HEARTBEAT_INTERVAL,
    HEARTBEAT_INTERVAL,
    NAV_API,
    RECONNECT_INTERVAL,
)
from .event import packet_to_event
from .exception import ApiNotAvailable, InteractionEndException
from .log import log
from .models.open import Game
from .packet import OpCode, Packet, ProtocolVersion, new_auth_packet
from .utils import UA, cookie_str_to_dict, make_header, split_list
from .wbi import get_key


class _Base(BaseAdapter):
    @override
    def __init__(self, driver: Driver, **kwargs: Any):
        super().__init__(driver, **kwargs)
        self.adapter_config = get_plugin_config(Config)
        self.bots: dict[str, Bot] = {}
        self.tasks = set()
        self.ws = set()

    async def _ws(
        self,
        bot: Bot,
        room_id: int,
        ws_conn: WebSocket,
        auth_packet: Packet,
    ):
        heartbeat_task: asyncio.Task[None] | None = None
        try:
            await ws_conn.send_bytes(auth_packet.to_bytes())
            _ = Packet.from_bytes(await ws_conn.receive_bytes())
            self.ws.add(ws_conn)
            log(
                "SUCCESS",
                f"[{bot.self_id}] Connected to room {room_id} successfully.",
            )
            heartbeat_task = asyncio.create_task(self._heartbeat(ws_conn))
            await self._ws_loop(bot, ws_conn, room_id)
        except InteractionEndException as e:
            log(
                "WARNING",
                (
                    f"<r><bg #f8bbd0>Openplatform stopped the game "
                    f"{e.game_id} at {e.timestamp} for {room_id}</bg #f8bbd0></r>"
                    "Trying to reconnect...</bg #f8bbd0></r>"
                ),
            )
        except WebSocketClosed as e:
            log(
                "ERROR",
                (
                    "<r><bg #f8bbd0>WebSocket Closed</bg #f8bbd0></r>"
                    "Trying to reconnect...</bg #f8bbd0></r>"
                ),
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
                    task = asyncio.create_task(bot._handle_event(event))
                    self.tasks.add(task)
                    task.add_done_callback(self.tasks.discard)
            else:
                event = packet_to_event(packet, room_id)
                task = asyncio.create_task(bot._handle_event(event))
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
        except InteractionEndException:
            raise
        except RuntimeError as e:
            log("TRACE", f"{e}")
        except Exception as e:
            log("ERROR", f"Error processing business message for room {room_id}", e)

    async def _heartbeat(
        self,
        ws: WebSocket,
    ):
        while True:
            try:
                await ws.send_bytes(
                    Packet.new_binary(OpCode.Heartbeat, 0, b"").to_bytes()
                )
            except Exception as e:
                log("WARNING", "Error while sending heartbeat, Ignored!", e)
            await asyncio.sleep(HEARTBEAT_INTERVAL)


class _WebApiAdapterMixin(_Base):
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

    async def _login_web(self, botconf: WebBotConf):
        img_key, sub_key, mid = await self._get_wbi_keys(
            cookie_str_to_dict(botconf.cookie)
        )
        bot = WebBot(
            self,
            self_id=str(mid),
            img_key=img_key,
            sub_key=sub_key,
            cookie=cookie_str_to_dict(botconf.cookie),
        )
        self.bot_connect(bot)
        for room_id in botconf.room_ids:
            task = asyncio.create_task(self._listen_room_web(bot, room_id))
            task.add_done_callback(self.tasks.discard)

    async def _request_buvid3(self, bot: WebBot) -> str:
        request = Request("GET", URL(BUVID3_URL), headers=make_header())
        resp = await self.request(request)
        return resp.headers["set-cookie"].split(";")[0].split("=")[1]

    async def _auth(self, bot: WebBot, room_id: int) -> dict[str, Any]:
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

    async def _listen_room_web(self, bot: WebBot, room_id: int):
        buvid3 = await self._request_buvid3(bot)
        bot.cookie["buvid3"] = buvid3
        room = await bot.get_room_info(room_id)
        bot.rooms[room_id] = room
        room_id = room.room_id
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
                auth_packet = new_auth_packet(
                    room_id, int(bot.self_id), token, bot.cookie["buvid3"]
                )
                await self._ws(
                    bot,
                    room_id,
                    ws_conn,
                    auth_packet,
                )


class _OpenplatformAdapterMixin(_Base):
    @override
    def __init__(self, driver: Driver, **kwargs: Any):
        super().__init__(driver, **kwargs)
        self.bots: dict[str, OpenBot] = {}

    async def _login_open(self, botconf: OpenBotConf) -> None:
        bot = self.bots.get(botconf.access_key)
        if not bot:
            bot = OpenBot(
                self,
                self_id=botconf.access_key,
                access_secret=botconf.access_secret,
                app_id=botconf.app_id,
            )
            self.bot_connect(bot)
        task = asyncio.create_task(self._game_heartbeat(bot))
        task.add_done_callback(self.tasks.discard)
        self.tasks.add(task)
        for code in botconf.identify_codes:
            task = asyncio.create_task(self._listen_room_open(bot, code))
            task.add_done_callback(self.tasks.discard)
            self.tasks.add(task)

    async def _game_heartbeat(self, bot: OpenBot):
        while True:
            game_ids = split_list([game.game_id for game in bot.games.values()], 199)
            for game_ids_chunk in game_ids:
                try:
                    request = bot.make_request(
                        "v2/app/batchHeartbeat", {"game_ids": game_ids_chunk}
                    )
                    resp = await self.request(request)
                    if resp.status_code != 200 or not resp.content:
                        log(
                            "WARNING",
                            (
                                f"Failed to send heartbeat for games {game_ids_chunk}: "
                                f"[{resp.status_code}] {resp.content}"
                            ),
                        )
                        continue
                    data = json.loads(resp.content)
                    if data["data"]["failed_game_ids"]:
                        log(
                            "WARNING",
                            (
                                "Failed to send heartbeat for games: "
                                f"{data['data']['failed_game_ids']}"
                            ),
                        )
                except Exception as e:
                    log("WARNING", "Error while sending game heartbeat.", e)
            await asyncio.sleep(GAME_HEARTBEAT_INTERVAL)

    async def _listen_room_open(self, bot: OpenBot, code: str):
        while True:
            request = bot.make_request(
                "v2/app/start", {"code": code, "app_id": bot.app_id}
            )
            resp = await self.request(request)
            if resp.status_code != 200 or not resp.content:
                log(
                    "ERROR",
                    (
                        f"Failed to start game with identify {code}: "
                        f"[{resp.status_code}] {resp.content}"
                    ),
                )
                return
            data = json.loads(resp.content)
            if data.get("code") != 0:
                log(
                    "ERROR",
                    (
                        f"Failed to start game with identify {code}"
                        f": [{data.get('code')}] {data.get('message')}"
                    ),
                )
                return
            game = Game(
                code=code,
                game_id=data["data"]["game_info"]["game_id"],
                **data["data"]["anchor_info"],
            )
            bot.games[game.room_id] = game
            url = data["data"]["websocket_info"]["wss_link"][0]
            auth_body = data["data"]["websocket_info"]["auth_body"]
            ws = Request(
                "GET",
                URL(url),
                timeout=30,
            )
            auth_packet = Packet.new_binary(
                OpCode.Auth, 0, auth_body.encode("utf-8"), ProtocolVersion.Heartbeat
            )
            async with self.websocket(ws) as ws_conn:
                await self._ws(
                    bot,
                    game.room_id,
                    ws_conn,
                    auth_packet,
                )
            bot.games.pop(game.room_id, None)


class Adapter(_WebApiAdapterMixin, _OpenplatformAdapterMixin):
    @override
    def __init__(self, driver: Driver, **kwargs: Any):
        super().__init__(driver, **kwargs)
        self.setup()

    def setup(
        self,
    ):
        if not isinstance(self.driver, HTTPClientMixin) or not isinstance(
            self.driver, WebSocketClientMixin
        ):
            raise RuntimeError(
                "bilibili Live adapter requires drivers "
                "that supports HTTP and WebSocket."
                f"Current driver {self.config.driver} does not support this."
            )
        self.on_ready(self.startup)
        self.driver.on_shutdown(self.shutdown)

    async def startup(self):
        for botconf in self.adapter_config.bilibili_live_bots:
            if isinstance(botconf, WebBotConf):
                await self._login_web(botconf)
            else:
                await self._login_open(botconf)

    async def shutdown(self):
        self.ws.clear()
        for task in self.tasks:
            task.cancel()
        self.tasks.clear()
        for bot in self.bots.copy().values():
            self.bot_disconnect(bot)
            if isinstance(bot, OpenBot):
                await bot._close()
        self.bots.clear()

    @classmethod
    @override
    def get_name(cls) -> str:
        return "bilibili Live"

    @override
    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:
        if not isinstance(bot, WebBot):
            raise RuntimeError("APIs are only available for WebBot.")
        log("DEBUG", f"WebBot {bot.self_id} calling API <y>{api}</y>")
        api_handler = getattr(bot.__class__, api, None)
        if api.startswith("_") or api_handler is None:
            raise ApiNotAvailable
        return await api_handler(bot, **data)
