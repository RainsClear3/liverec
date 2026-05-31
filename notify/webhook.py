"""Webhook notification system — compatible with WeChat Work (企业微信) robot webhooks."""

import logging
from typing import Optional

import aiohttp

from core.events import EventType
from core.models import PushConfig, Streamer

logger = logging.getLogger("live_recorder")

PLATFORM_NAMES = {
    "douyin": "抖音",
    "bilibili": "B站",
    "wechat": "视频号",
}


class WebhookNotifier:
    """Sends push notifications via webhook (企业微信/钉钉/自定义)."""

    def __init__(self, push_config: PushConfig, http_client: aiohttp.ClientSession):
        self.config = push_config
        self._http = http_client

    async def on_event(self, event_type: EventType, **kwargs):
        """Handle an event from the event bus."""
        if not self.config.web_hook_url:
            return

        # Check if this event type should be notified
        streamer: Streamer = kwargs.get("streamer")
        if not streamer:
            return

        should_notify = False
        if event_type == EventType.LIVE_START and self.config.live_status:
            should_notify = True
        elif event_type == EventType.REC_START and self.config.rec_start:
            should_notify = True
        elif event_type == EventType.REC_END and self.config.rec_end:
            should_notify = True

        if not should_notify:
            return

        message = self._format_message(event_type, **kwargs)
        await self._send(message)

    async def _send(self, content: str):
        """Send a markdown message to the webhook URL."""
        try:
            # Try WeChat Work format first
            payload = {
                "msgtype": "markdown",
                "markdown": {"content": content},
            }
            async with self._http.post(
                self.config.web_hook_url, json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("errcode", 0) == 0:
                        logger.debug(f"Webhook notification sent successfully")
                        return

            # Fallback: try DingTalk format
            payload = {
                "msgtype": "markdown",
                "markdown": {"title": "直播录屏通知", "text": content},
            }
            async with self._http.post(
                self.config.web_hook_url, json=payload
            ) as resp:
                if resp.status == 200:
                    logger.debug("Webhook notification sent (DingTalk format)")

        except Exception as e:
            logger.error(f"Webhook send error: {e}")

    def _format_message(self, event_type: EventType, **kwargs) -> str:
        """Format event data into a markdown message."""
        streamer: Streamer = kwargs.get("streamer")
        plat = PLATFORM_NAMES.get(streamer.platform, streamer.platform)

        if event_type == EventType.LIVE_START:
            title = kwargs.get("title") or streamer.room_title
            return (
                f"🔴 **{streamer.nickname}** ({plat}) 开始直播\n"
                f"> {title}"
            )
        elif event_type == EventType.REC_START:
            return f"⏺ **{streamer.nickname}** ({plat}) 开始录制"
        elif event_type == EventType.REC_END:
            duration = kwargs.get("duration", "未知")
            size = kwargs.get("size", "未知")
            return (
                f"⏹ **{streamer.nickname}** ({plat}) 录制结束\n"
                f"> 时长: {duration}, 大小: {size}"
            )
        return ""
