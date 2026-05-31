"""Douyin (抖音) live stream platform adapter.

Uses the webcast API (/webcast/room/web/enter/) instead of page scraping
to avoid captcha/verification challenges.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import urlencode

import aiohttp

from core.models import Streamer
from platforms.base import AbstractPlatform
from platforms.factory import PlatformFactory

logger = logging.getLogger("live_recorder")

WEBCAST_API = "https://live.douyin.com/webcast/room/web/enter/"
COOKIE_URL = "https://live.douyin.com/"

# Browser-like defaults
DEFAULT_PARAMS = {
    "aid": "6383",
    "app_name": "douyin_web",
    "live_id": "1",
    "device_platform": "web",
    "language": "zh-CN",
    "enter_from": "web_live",
    "cookie_enabled": "true",
    "screen_width": "1920",
    "screen_height": "1080",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Chrome",
    "browser_version": "120",
}


class DouyinPlatform(AbstractPlatform):
    PLATFORM_NAME = "douyin"
    PLATFORM_DISPLAY = "抖音"

    QUALITY_MAP = {
        "流畅": "SD2",
        "标清": "SD1",
        "高清": "HD1",
        "超清": "FULL_HD1",
    }

    _initialized: bool = False

    async def _ensure_cookies(self):
        """Visit douyin.com to get ttwid cookie if not already done."""
        if self._initialized:
            return
        try:
            async with self._http.get(COOKIE_URL, allow_redirects=True) as resp:
                logger.debug(f"Douyin cookie init: status={resp.status}")
            self._initialized = True
        except Exception as e:
            logger.warning(f"Douyin cookie init failed: {e}")

    async def _call_webcast_api(self, web_rid: str) -> Optional[dict]:
        """Call the webcast room enter API. Returns the room data dict or None."""
        await self._ensure_cookies()
        try:
            params = {**DEFAULT_PARAMS, "web_rid": web_rid}
            headers = {
                "Referer": f"https://live.douyin.com/{web_rid}",
            }
            async with self._http.get(
                WEBCAST_API, params=params, headers=headers
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Douyin API HTTP {resp.status} for web_rid={web_rid}")
                    return None
                data = await resp.json()

            status_code = data.get("status_code", -1)
            if status_code != 0:
                logger.warning(
                    f"Douyin API error: status_code={status_code}, "
                    f"msg={data.get('status_msg', '')}"
                )
                return None

            # The API returns data.data as a list of rooms (usually just one)
            rooms = data.get("data", {}).get("data", [])
            if not rooms:
                logger.info(f"Douyin API: no room data for web_rid={web_rid}")
                return None

            return rooms[0]  # First room

        except Exception as e:
            logger.error(f"Douyin webcast API error: {e}", exc_info=True)
            return None

    async def check_live_status(self, streamer: Streamer) -> bool:
        """Check if streamer is currently live via webcast API."""
        room = await self._call_webcast_api(streamer.web_rid)
        if not room:
            return False

        status = room.get("status", 0)
        # status: 2 = live, 4 = offline/ended
        streamer.room_title = room.get("title", "")
        streamer.viewer_count = room.get("user_count", 0)
        return status == 2

    async def get_stream_url(
        self, streamer: Streamer, quality: str = "标清"
    ) -> Optional[str]:
        """Get stream URL from webcast API response."""
        room = await self._call_webcast_api(streamer.web_rid)
        if not room:
            return None

        stream_url_info = room.get("stream_url", {})
        if not stream_url_info:
            logger.warning(f"Douyin: no stream_url in API response for {streamer.nickname}")
            return None

        quality_key = self.QUALITY_MAP.get(quality, "SD1")

        # Quality fallback order: requested -> SD1 -> HD1 -> FULL_HD1 -> any
        fallback_order = [quality_key, "SD1", "HD1", "FULL_HD1", "SD2", "LD1"]

        def _pick_url(url_map: dict) -> Optional[str]:
            """Pick URL by quality with fallback to any available."""
            if not url_map:
                return None
            for qkey in fallback_order:
                if qkey in url_map:
                    return url_map[qkey]
            # Last resort: return any URL
            if url_map:
                return next(iter(url_map.values()))
            return None

        # Try flv_pull_url first
        flv_urls = stream_url_info.get("flv_pull_url", {})
        stream_url = _pick_url(flv_urls)
        if stream_url:
            logger.info(f"Douyin stream URL (FLV) for {streamer.nickname}")
            return stream_url

        # Try hls_pull_url_map
        hls_urls = stream_url_info.get("hls_pull_url_map", {})
        stream_url = _pick_url(hls_urls)
        if stream_url:
            logger.info(f"Douyin stream URL (HLS) for {streamer.nickname}")
            return stream_url

        logger.warning(f"Douyin: no stream URL found for {streamer.nickname}")
        return None

    async def get_room_info(self, streamer: Streamer) -> dict:
        """Get room metadata from webcast API."""
        room = await self._call_webcast_api(streamer.web_rid)
        return room or {}

    async def parse_room_url(self, url: str) -> Optional[dict]:
        """Parse a Douyin live room URL to extract streamer info via API."""
        # Match URLs like: https://live.douyin.com/891207851592?...
        match = re.search(r"live\.douyin\.com/(\d+)", url)
        if not match:
            return None

        web_rid = match.group(1)

        room = await self._call_webcast_api(web_rid)
        if not room:
            # Fallback: return just the web_rid
            return {
                "platform": "douyin",
                "nickname": f"抖音主播{web_rid}",
                "userid": "",
                "sec_uid": "",
                "web_rid": web_rid,
                "avatar": "",
            }

        owner = room.get("owner", {})
        nickname = owner.get("nickname", "")
        avatar = owner.get("avatar_thumb", {}).get("url_list", [""])[0] if isinstance(
            owner.get("avatar_thumb"), dict
        ) else ""
        sec_uid = owner.get("sec_uid", "")
        user_id = str(owner.get("id_str", ""))

        return {
            "platform": "douyin",
            "nickname": nickname or f"抖音主播{web_rid}",
            "userid": user_id,
            "sec_uid": sec_uid,
            "web_rid": web_rid,
            "avatar": avatar,
        }

    def get_headers(self) -> dict:
        return {"Referer": "https://live.douyin.com/"}


# Register the platform
PlatformFactory.register("douyin", DouyinPlatform)
