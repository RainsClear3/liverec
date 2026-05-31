"""Platform adapter factory with URL auto-detection."""

from __future__ import annotations

import re
from typing import Optional, Type

import aiohttp

from platforms.base import AbstractPlatform


class PlatformFactory:
    """Creates platform adapter instances and detects platform from URLs."""

    _registry: dict[str, Type[AbstractPlatform]] = {}

    @classmethod
    def register(cls, platform_type: str, adapter_cls: Type[AbstractPlatform]):
        cls._registry[platform_type] = adapter_cls

    @classmethod
    def create(
        cls, platform_type: str, http_client: aiohttp.ClientSession
    ) -> AbstractPlatform:
        adapter_cls = cls._registry.get(platform_type)
        if not adapter_cls:
            raise ValueError(f"Unknown platform: {platform_type}")
        return adapter_cls(http_client)

    @classmethod
    def detect_platform(cls, url: str) -> Optional[str]:
        """Auto-detect platform from a URL."""
        url_lower = url.lower()
        if "douyin.com" in url_lower:
            return "douyin"
        if "bilibili.com" in url_lower or "b23.tv" in url_lower:
            return "bilibili"
        if "channels.weixin.qq.com" in url_lower or "weixin" in url_lower:
            return "wechat"
        return None

    @classmethod
    def get_platform_display(cls, platform_type: str) -> str:
        """Get display name for a platform."""
        adapter_cls = cls._registry.get(platform_type)
        if adapter_cls:
            return adapter_cls.PLATFORM_DISPLAY
        return platform_type

    @classmethod
    def list_platforms(cls) -> list[tuple[str, str]]:
        """Return list of (type, display_name) tuples."""
        return [
            (key, cls.get_platform_display(key))
            for key in cls._registry
        ]
