from __future__ import annotations

from pydantic import BaseModel, Field


class BLiveBot(BaseModel):
    cookie: str
    room_ids: list[int] = Field(default_factory=list)


class Config(BaseModel):
    bilibili_live_bots: list[BLiveBot] = Field(default_factory=list)
