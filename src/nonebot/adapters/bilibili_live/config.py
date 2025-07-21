from __future__ import annotations

from typing import Union

from pydantic import BaseModel, Field


class WebBotConf(BaseModel):
    cookie: str
    room_ids: list[int] = Field(default_factory=list)


class OpenBotConf(BaseModel):
    access_key: str
    access_secret: str
    app_id: int
    identify_codes: list[str] = Field(default_factory=list)


class Config(BaseModel):
    bilibili_live_bots: list[Union[WebBotConf, OpenBotConf]] = Field(
        default_factory=list
    )
