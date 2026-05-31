"""Data models for the live recorder application."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PushConfig:
    live_status: bool = True
    rec_start: bool = True
    rec_end: bool = True
    web_hook_url: str = ""
    userid: str = "@all"


@dataclass
class AppConfig:
    interval_time: int = 15
    definition: str = "标清"
    stream_type: str = "flv"
    out_format: str = "ts"
    check_pk: bool = False
    file_size: int = 0          # max MB per file (0=unlimited)
    file_time: int = 0          # max seconds per file (0=unlimited)
    rec_time: int = 0           # total max recording time
    rec_file_size: int = 0      # total max recording size
    save_path: str = "D:\\录播"
    mp3_play: bool = False
    hide_time: bool = False
    hide_file_size: bool = False
    show_user_count: bool = False
    run_server: bool = False
    server_port: int = 8088
    push_msg: bool = True
    push_config: PushConfig = field(default_factory=PushConfig)

    def to_dict(self) -> dict:
        return {
            "intervalTime": self.interval_time,
            "definition": self.definition,
            "streamType": self.stream_type,
            "outFormat": self.out_format,
            "checkPK": self.check_pk,
            "fileSize": self.file_size,
            "fileTime": self.file_time,
            "recTime": self.rec_time,
            "recFileSize": self.rec_file_size,
            "save": self.save_path,
            "mp3play": self.mp3_play,
            "hideTime": self.hide_time,
            "hideFileSize": self.hide_file_size,
            "showUserCount": self.show_user_count,
            "runServer": self.run_server,
            "serverPort": self.server_port,
            "pushMsg": self.push_msg,
            "pushConfig": {
                "liveStatus": self.push_config.live_status,
                "recStart": self.push_config.rec_start,
                "recEnd": self.push_config.rec_end,
                "webHookUrl": self.push_config.web_hook_url,
                "userid": self.push_config.userid,
            },
        }


@dataclass
class Streamer:
    platform: str = ""      # "douyin", "bilibili", "wechat"
    nickname: str = ""
    userid: str = ""        # platform-specific user ID
    sec_uid: str = ""       # douyin-specific
    web_rid: str = ""       # room ID from URL
    unique_id: str = ""     # platform handle
    avatar: str = ""        # avatar URL
    disable: bool = False

    # Runtime state (not persisted)
    is_live: bool = False
    is_recording: bool = False
    room_title: str = ""
    viewer_count: int = 0

    def to_dict(self) -> dict:
        return {
            "type": self.platform,
            "nickname": self.nickname,
            "userid": self.userid,
            "sec_uid": self.sec_uid,
            "web_rid": self.web_rid,
            "unique_id": self.unique_id,
            "avatar": self.avatar,
            "disable": self.disable,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Streamer:
        return cls(
            platform=data.get("type", "douyin"),
            nickname=data.get("nickname", ""),
            userid=data.get("userid", ""),
            sec_uid=data.get("sec_uid", ""),
            web_rid=data.get("web_rid", ""),
            unique_id=data.get("unique_id", ""),
            avatar=data.get("avatar", ""),
            disable=data.get("disable", False),
        )


@dataclass
class RecordingSession:
    streamer: Streamer
    start_time: datetime = field(default_factory=datetime.now)
    output_dir: str = ""
    file_index: int = 0
    ffmpeg_pid: Optional[int] = None
    bytes_written: int = 0
    duration_seconds: float = 0.0
    current_file: str = ""
    is_active: bool = False

    def build_output_filename(self, config: AppConfig) -> str:
        """Build output file path with index for auto-split."""
        safe_name = "".join(
            c for c in self.streamer.nickname if c.isalnum() or c in " _-"
        ).strip()
        ts = self.start_time.strftime("%Y%m%d_%H%M%S")
        ext = f".{config.out_format}"
        index_suffix = f"_{self.file_index:03d}" if self.file_index > 0 else ""
        filename = f"{safe_name}_{ts}{index_suffix}{ext}"
        return os.path.join(self.output_dir, filename)
