"""Abstract base class for all platform adapters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

import aiohttp

from core.models import Streamer

logger = logging.getLogger("live_recorder")


class AbstractPlatform(ABC):
    """Base class for all live streaming platform adapters."""

    PLATFORM_NAME: str = ""
    PLATFORM_DISPLAY: str = ""

    # Maps Chinese quality labels to platform-specific quality codes
    QUALITY_MAP: dict = {}

    def __init__(self, http_client: aiohttp.ClientSession):
        self._http = http_client

    @abstractmethod
    async def check_live_status(self, streamer: Streamer) -> bool:
        """Return True if the streamer is currently live."""

    @abstractmethod
    async def get_stream_url(
        self, streamer: Streamer, quality: str = "标清"
    ) -> Optional[str]:
        """Extract the actual stream URL (FLV/HLS). Returns None if unavailable."""

    @abstractmethod
    async def get_room_info(self, streamer: Streamer) -> dict:
        """Fetch room metadata: title, viewer count, cover image, etc."""

    @abstractmethod
    async def parse_room_url(self, url: str) -> Optional[dict]:
        """Given a live room URL, extract streamer fields.
        Returns dict with keys: userid, web_rid, nickname, sec_uid, avatar, etc.
        """

    async def get_avatar(self, streamer: Streamer) -> Optional[bytes]:
        """Download avatar image bytes."""
        if not streamer.avatar:
            return None
        try:
            async with self._http.get(streamer.avatar) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logger.warning(f"Failed to download avatar for {streamer.nickname}: {e}")
        return None

    def get_headers(self) -> dict:
        """Return platform-specific headers needed for stream URLs."""
        return {}
