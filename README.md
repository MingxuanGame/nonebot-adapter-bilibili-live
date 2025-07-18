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

- `cookie` 机器人账号的 Cookies，需要存在 `SESSDATA`（必须） 和 `bili_jct`（用于一些 API 调用）。
- `room_ids` 监听的直播间房间号列表，长短号均可。

#### 示例

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

## 实现

<details>
<summary>消息类事件</summary>

- `DanmakuEvent` 弹幕消息
- `SuperChatEvent` 醒目留言

</details>

<details>
<summary>通知类事件</summary>

### 用户互动

- `UserEnterEvent` 用户进入直播间
- `UserFollowEvent` 用户关注主播
- `UserShareEvent` 用户分享直播间

### 礼物相关

- `SendGiftEvent` 送礼
- `GuardBuyEvent` 上舰通知
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

- `HeartbeatEvent` 心跳包，包含人气值

</details>

<details>
<summary>API 实现</summary>

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
- [ ] 使用开平接口 + 主播身份码

## 代码实现参考

- [BAC](https://github.com/SocialSisterYi/bilibili-API-collect)
- [blivedm](https://github.com/xfgryujk/blivedm)
- [adapter-bilibili](https://github.com/wwweww/adapter-bilibili)
