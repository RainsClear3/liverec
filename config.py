"""Shared configuration for WeChat stream interception and recording.

This module provides the Config class used by the mitmproxy addon
and other components that need stream detection and FFmpeg settings.
"""

import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class Config:
    """Global configuration constants."""

    # ==================== WeChat domain configuration ====================

    WECHAT_DOMAINS = [
        "finder.video.qq.com",
        "channels.weixin.qq.com",
        "findermp.video.qq.com",
        "wxsnsdythumb.video.qq.com",
        "finder.qq.com",
        "wxvideodownload.video.qq.com",
        "live.video.qq.com",
    ]

    # Stream URL matching patterns
    STREAM_PATTERNS = [
        r"\.m3u8",       # HLS streams
        r"\.flv",        # FLV streams
        r"/live/",       # Live path
        r"stream",       # Stream keyword
        r"pull-flv",     # FLV pull
        r"pull-hls",     # HLS pull
        r"wxstream",     # WeChat stream
        r"wxvideostream", # WeChat video stream
        r"finderlive",   # Finder live
        r"wxlivecdn",    # WeChat live CDN
    ]

    # ==================== FFmpeg configuration ====================

    FFMPEG_PATH = "ffmpeg"

    # Headers to pass to FFmpeg (whitelist)
    FFMPEG_HEADER_KEYS = [
        "User-Agent",
        "Referer",
        "Cookie",
        "Origin",
        "Authorization",
    ]

    # ==================== Advanced configuration ====================

    # URL deduplication cache TTL (seconds)
    STREAM_CACHE_TTL = 1800  # 30 minutes

    # Sensitive query parameter keys (redacted in logs)
    SENSITIVE_QUERY_KEYS = {
        "sig", "sign", "signature", "token", "auth", "authorization",
        "access_token", "expires", "expire", "exp", "wssecret",
        "wstoken", "key", "hdnts", "jwt",
    }

    @classmethod
    def redact_url(cls, url):
        """Redact sensitive query parameters from URL for logging."""
        if not url:
            return url

        parsed = urlsplit(str(url))
        if not parsed.query:
            return str(url)

        sanitized_query = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key.lower() in cls.SENSITIVE_QUERY_KEYS:
                sanitized_query.append((key, "***"))
            else:
                sanitized_query.append((key, value))

        return urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(sanitized_query, doseq=True),
            parsed.fragment,
        ))

    @classmethod
    def sanitize_log_message(cls, message):
        """Sanitize all URLs in a log message."""
        if message is None:
            return message
        text = str(message)
        return re.sub(
            r"https?://[^\s\"'<>]+",
            lambda match: cls.redact_url(match.group(0)),
            text,
        )

    @classmethod
    def build_ffmpeg_headers(cls, headers):
        """Build FFmpeg -headers argument from a header dict (whitelist only)."""
        normalized = {
            str(k).lower(): str(v).replace("\r", " ").replace("\n", " ")
            for k, v in headers.items()
        }
        lines = []
        for key in cls.FFMPEG_HEADER_KEYS:
            value = normalized.get(key.lower())
            if value:
                lines.append(f"{key}: {value}")
        if not lines:
            return None
        return "\r\n".join(lines) + "\r\n"
