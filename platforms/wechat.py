"""WeChat Channels platform adapter — simplified.

Each room identified by trtc_ number. No FFmpeg probe — latest URL used.
Thumbnail captured via FFmpeg frame extraction.
"""

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Optional

from core.models import Streamer
from platforms.base import AbstractPlatform
from platforms.factory import PlatformFactory

logger = logging.getLogger("live_recorder")


def _find_ffmpeg():
    p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ffmpeg", "ffmpeg.exe")
    if os.path.isfile(p):
        return p
    return shutil.which("ffmpeg") or "ffmpeg"


class WechatPlatform(AbstractPlatform):
    PLATFORM_NAME = "wechat"
    PLATFORM_DISPLAY = "视频号"

    # {room_id: [(url, headers, ts), ...]}
    _room_streams: dict[str, list[tuple[str, dict, float]]] = {}
    _lock = threading.Lock()

    @classmethod
    def add_stream_url(cls, url: str, room_id: str, headers: dict = None):
        with cls._lock:
            if room_id not in cls._room_streams:
                cls._room_streams[room_id] = []
            cls._room_streams[room_id].append((url, headers or {}, time.time()))
            # Prune entries older than 1 hour
            cutoff = time.time() - 3600
            for rid in list(cls._room_streams):
                cls._room_streams[rid] = [
                    (u, h, t) for u, h, t in cls._room_streams[rid] if t > cutoff
                ]
                if not cls._room_streams[rid]:
                    del cls._room_streams[rid]

    @classmethod
    def get_urls_for_room(cls, room_id: str) -> list[tuple[str, dict]]:
        """Return all stored URLs for a room (for thumbnail capture)."""
        with cls._lock:
            return [(u, h) for u, h, _ in cls._room_streams.get(room_id, [])]

    async def check_live_status(self, streamer: Streamer) -> bool:
        with self._lock:
            return len(self._room_streams.get(streamer.userid, [])) > 0

    async def get_stream_url(self, streamer: Streamer, quality: str = "标清") -> Optional[str]:
        """Return the latest URL. No probe — just use the newest."""
        with self._lock:
            streams = self._room_streams.get(streamer.userid, [])
            if not streams:
                return None
            url, headers, ts = streams[-1]
            self._current_headers = headers
        return url

    async def get_room_info(self, streamer: Streamer) -> dict:
        return {}

    async def parse_room_url(self, url: str) -> Optional[dict]:
        if any(ext in url.lower() for ext in [".m3u8", ".flv"]):
            return {"platform": "wechat", "nickname": "", "userid": "",
                    "web_rid": "", "stream_url": url}
        return None

    def get_headers(self) -> dict:
        return getattr(self, "_current_headers", {})

    @staticmethod
    def capture_frame(url: str, headers: dict = None, timeout: int = 15) -> Optional[str]:
        """Capture a single frame from stream URL, return path to JPEG."""
        ffmpeg = _find_ffmpeg()
        out = os.path.join(tempfile.gettempdir(), f"wc_thumb_{int(time.time()*1000)}.jpg")
        cmd = [
            ffmpeg, "-y", "-loglevel", "warning",
            "-analyzeduration", "3000000",
            "-probesize", "1000000",
        ]
        if headers:
            hdr = "\r\n".join(f"{k}: {v}" for k, v in headers.items()) + "\r\n"
            cmd += ["-headers", hdr]
        cmd += ["-i", url, "-frames:v", "1", "-q:v", "5", out]
        logger.debug(f"Capturing thumbnail: {url[:60]}...")
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout)
            if r.returncode == 0 and os.path.isfile(out) and os.path.getsize(out) > 0:
                logger.info(f"Thumbnail captured: {out}")
                return out
            else:
                err = r.stderr.decode("utf-8", errors="replace")[:200]
                logger.warning(f"Thumbnail FFmpeg failed (rc={r.returncode}): {err}")
        except subprocess.TimeoutExpired:
            logger.warning(f"Thumbnail capture timed out ({timeout}s)")
        except Exception as e:
            logger.warning(f"Thumbnail capture error: {e}")
        return None


PlatformFactory.register("wechat", WechatPlatform)
