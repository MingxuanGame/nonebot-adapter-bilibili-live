# NoneBot-Adapter-Bilibili-Live

B 站直播间协议支持

## 配置

修改 NoneBot 配置文件 `.env` 或者 `.env.*`。

### Driver

请参考 [driver](https://nonebot.dev/docs/appendices/config#driver) 配置项，添加 `HTTPClient` 和 `WebSocketClient` 支持。如：

```dotenv
DRIVER=~httpx+~websockets
DRIVER=~aiohttp
```

### BILIBILI_LIVE_BOTS

#### 用户 Bot (Web API)

- `cookie` 机器人账号的 Cookies，需要存在 `SESSDATA`（必须） 和 `bili_jct`（用于一些 API 调用）。
- `room_ids` 监听的直播间房间号列表，长短号均可。

类型为 `WebBot`。

#### 开放平台 Bot

- `access_key` 开放平台提供的 `access_key`
- `access_secret` 开放平台提供的 `access_secret`
- `app_id` 项目 ID，在[此处](https://open-live.bilibili.com/open-manage)查看
- `identify_codes` 主播身份码列表，主播身份码可以在[幻星-互动玩法](https://play-live.bilibili.com)页面右下角 身份码 查看

类型为 `OpenBot`。

__开放平台 Bot 无法调用任何 API。__

#### 示例

用户 Bot 配置示例：

```dotenv
BILIBILI_LIVE_BOTS='
[
  {
    "cookie": "SESSDATA=xxxxxxxxxxxxxxxx; bili_jct=xxxxxxxxxxxxx;",
    "room_ids": [544853]
  }
]
'
```

开放平台 Bot 配置示例：

```dotenv
BILIBILI_LIVE_BOTS='
[
  {
    "access_key": "xxxxxxxxxxxxxxxxxxxx",
    "access_secret": "xxxxxxxxxxxxxxxxxxxx",
    "app_id": 100000,
    "identify_codes": ["xxxxxxxxxxxxxxxxxxxx"]
  }
]
'
```

## 实现

标斜体的为用户 Bot 和开放平台 Bot 共有实现。

来自开放平台的事件的 `uid` 均为 `0`，相应的存在 `open_id` 字段。

获取用户 ID 建议使用 `Event.get_user_id()` 方法，而不是 `event.uid` 或 `event.open_id`。

来自开放平台的 `SuperChatEvent` 事件会被认为是 `to_me`。

<details>
<summary>消息类事件</summary>

- _`DanmakuEvent` 弹幕消息_
- _`SuperChatEvent` 醒目留言_

</details>

<details>
<summary>通知类事件</summary>

### 用户互动

- _`UserEnterEvent` 用户进入直播间_
- `UserFollowEvent` 用户关注主播
- `UserShareEvent` 用户分享直播间

### 礼物相关

- _`SendGiftEvent` 送礼_
- _`GuardBuyEvent` 上舰通知_
- `GuardBuyToastEvent` 用户庆祝消息
- `SpecialGiftEvent` 特殊礼物
- `GiftStarProcessEvent` 礼物星球点亮

### 直播状态

- `LiveStartEvent` 直播开始
- `OnlineRankEvent` 高能榜更新
- `OnlineRankCountEvent` 高能用户数量
- `OnlineRankTopEvent` 到达直播间高能榜前三名
- `LikeInfoUpdateEvent` 点赞数更新
- `WatchedChangeEvent` 看过人数
- `StopLiveRoomListEvent` 下播的直播间

</details>

<details>
<summary>元事件</summary>

- _`HeartbeatEvent` 心跳包，包含人气值_
- `LIVE_OPEN_PLATFORM_INTERACTION_END` 开放平台互动结束事件。此事件不会进入 NoneBot 事件处理流程，会由适配器自行捕获。

</details>

<details>
<summary>API 实现</summary>

__API 仅限用户 Bot。__

### 弹幕发送

- `send_danmaku()` 发送弹幕消息

### 直播间信息

- `get_room_info()` 获取直播间详细信息
- `get_user_room_status()` 获取用户对应的直播间状态
- `get_master_info()` 获取主播信息

### 用户管理

- `add_silent_user()` 禁言观众
- `get_silent_user_list()` 查询直播间禁言列表
- `del_silent_user()` 解除禁言

</details>

## ToDo

- [ ] 完善事件
- [ ] 完善 API

## 代码实现参考

- [BAC](https://github.com/SocialSisterYi/bilibili-API-collect)
- [直播开放平台文档](https://open-live.bilibili.com/document)
- [blivedm](https://github.com/xfgryujk/blivedm)
- [adapter-bilibili](https://github.com/wwweww/adapter-bilibili)
