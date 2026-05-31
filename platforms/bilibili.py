"""Bilibili (B站) live stream platform adapter."""

import logging
import re
from typing import Optional

import aiohttp

from core.models import Streamer
from platforms.base import AbstractPlatform
from platforms.factory import PlatformFactory

logger = logging.getLogger("live_recorder")


class BilibiliPlatform(AbstractPlatform):
    PLATFORM_NAME = "bilibili"
    PLATFORM_DISPLAY = "B站"

    QUALITY_MAP = {
        "流畅": 300,
        "标清": 800,
        "高清": 1500,
        "超清": 2500,
        "蓝光": 400,
    }

    # Real room_id cache (URL room_id -> real room_id)
    _room_id_cache: dict[str, int] = {}

    async def check_live_status(self, streamer: Streamer) -> bool:
        """Check if streamer is currently live via Bilibili API."""
        try:
            real_room_id = await self._get_real_room_id(streamer.web_rid)
            if not real_room_id:
                return False

            url = "https://api.live.bilibili.com/room/v1/Room/get_info"
            params = {"room_id": real_room_id}
            async with self._http.get(url, params=params) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json()
                if data.get("code") != 0:
                    return False
                room_data = data.get("data", {})
                # live_status: 0=offline, 1=live, 2=loop
                live_status = room_data.get("live_status", 0)
                streamer.room_title = room_data.get("title", "")
                streamer.viewer_count = room_data.get("online", 0)
                return live_status == 1
        except Exception as e:
            logger.warning(f"Bilibili check_live_status error for {streamer.nickname}: {e}")
            return False

    async def get_stream_url(
        self, streamer: Streamer, quality: str = "标清"
    ) -> Optional[str]:
        """Get stream URL from Bilibili getRoomPlayInfo API."""
        try:
            real_room_id = await self._get_real_room_id(streamer.web_rid)
            if not real_room_id:
                return None

            qn = self.QUALITY_MAP.get(quality, 800)
            url = "https://api.live.bilibili.com/xlive/web-room/v2/index/getRoomPlayInfo"
            params = {
                "room_id": real_room_id,
                "protocol": "0,1",      # 0=http-stream, 1=hls
                "format": "0,1,2",      # 0=flv, 1=ts, 2=fmp4
                "codec": "0,1",         # 0=AVC, 1=HEVC
                "qn": qn,
                "platform": "web",
                "dolby": "5",
                "panorama": "1",
            }
            headers = {
                "Referer": "https://live.bilibili.com/",
            }
            async with self._http.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(f"Bilibili getRoomPlayInfo HTTP {resp.status}")
                    return None
                data = await resp.json()
                if data.get("code") != 0:
                    logger.warning(f"Bilibili getRoomPlayInfo error: {data.get('message')}")
                    return None

                playurl_info = data.get("data", {}).get("playurl_info", {})
                playurl = playurl_info.get("playurl", {})
                streams = playurl.get("stream", [])

                # Try to find HTTP stream (FLV) first, then HLS
                for stream in streams:
                    formats = stream.get("format", [])
                    for fmt in formats:
                        codecs = fmt.get("codec", [])
                        for codec in codecs:
                            url_info_list = codec.get("url_info", [])
                            base_url = codec.get("base_url", "")
                            if url_info_list and base_url:
                                host = url_info_list[0].get("host", "")
                                extra = url_info_list[0].get("extra", "")
                                stream_url = f"{host}{base_url}{extra}"
                                logger.info(
                                    f"Bilibili stream URL obtained for {streamer.nickname}: "
                                    f"format={fmt.get('format_name')}, codec={codec.get('codec_name')}"
                                )
                                return stream_url

                # Fallback: try durl
                durl = data.get("data", {}).get("durl", [])
                if durl:
                    return durl[0].get("url")

                logger.warning(f"Bilibili: no stream URL found for {streamer.nickname}")
                return None
        except Exception as e:
            logger.error(f"Bilibili get_stream_url error for {streamer.nickname}: {e}")
            return None

    async def get_room_info(self, streamer: Streamer) -> dict:
        """Get room metadata."""
        try:
            real_room_id = await self._get_real_room_id(streamer.web_rid)
            if not real_room_id:
                return {}

            url = "https://api.live.bilibili.com/room/v1/Room/get_info"
            params = {"room_id": real_room_id}
            async with self._http.get(url, params=params) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                if data.get("code") != 0:
                    return {}
                return data.get("data", {})
        except Exception as e:
            logger.warning(f"Bilibili get_room_info error: {e}")
            return {}

    async def parse_room_url(self, url: str) -> Optional[dict]:
        """Parse a Bilibili live room URL to extract streamer info."""
        # Match URLs like: https://live.bilibili.com/12345
        match = re.search(r"live\.bilibili\.com/(\d+)", url)
        if not match:
            return None

        room_id = match.group(1)

        try:
            # Get real room_id and UID
            real_room_id = await self._get_real_room_id(room_id)
            if not real_room_id:
                return None

            # Get room info for nickname and avatar
            info_url = "https://api.live.bilibili.com/room/v1/Room/get_info"
            async with self._http.get(info_url, params={"room_id": real_room_id}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data.get("code") != 0:
                    return None
                room = data.get("data", {})
                uid = room.get("uid", "")

            # Get user info for nickname and avatar
            nickname = ""
            avatar = ""
            if uid:
                user_url = "https://api.live.bilibili.com/live_user/v1/UserInfo/get_anchor_in_room"
                async with self._http.get(user_url, params={"roomid": real_room_id}) as resp:
                    if resp.status == 200:
                        udata = await resp.json()
                        if udata.get("code") == 0:
                            info = udata.get("data", {}).get("info", {})
                            nickname = info.get("uname", "")
                            avatar = info.get("face", "")

            return {
                "platform": "bilibili",
                "nickname": nickname or f"B站主播{room_id}",
                "userid": str(uid),
                "web_rid": room_id,
                "avatar": avatar,
            }
        except Exception as e:
            logger.error(f"Bilibili parse_room_url error: {e}")
            return None

    def get_headers(self) -> dict:
        return {"Referer": "https://live.bilibili.com/"}

    async def _get_real_room_id(self, room_id: str) -> Optional[int]:
        """Convert URL room_id to real room_id (Bilibili sometimes uses short IDs)."""
        if room_id in self._room_id_cache:
            return self._room_id_cache[room_id]

        try:
            url = "https://api.live.bilibili.com/room/v1/Room/room_init"
            async with self._http.get(url, params={"id": room_id}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data.get("code") != 0:
                    return None
                real_id = data["data"]["room_id"]
                self._room_id_cache[room_id] = real_id
                return real_id
        except Exception as e:
            logger.warning(f"Bilibili room_init error for {room_id}: {e}")
            return None


# Register the platform
PlatformFactory.register("bilibili", BilibiliPlatform)
