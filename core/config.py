"""Configuration loading, validation, and persistence."""

import json
import logging
import os
from typing import Optional

from core.models import AppConfig, PushConfig, Streamer

logger = logging.getLogger("live_recorder")

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")


class ConfigManager:
    """Manages application configuration with JSON persistence."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.app_config = AppConfig()
        self.streamers: list[Streamer] = []

    def load(self):
        """Load configuration from JSON file."""
        if not os.path.exists(self.config_path):
            logger.info(f"Config file not found at {self.config_path}, using defaults")
            self._ensure_save_path()
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load config: {e}")
            return

        # Parse config section
        cfg = data.get("config", {})
        push = cfg.get("pushConfig", {})
        self.app_config = AppConfig(
            interval_time=cfg.get("intervalTime", 15),
            definition=cfg.get("definition", "标清"),
            stream_type=cfg.get("streamType", "flv"),
            out_format=cfg.get("outFormat", "ts"),
            check_pk=cfg.get("checkPK", False),
            file_size=cfg.get("fileSize", 0),
            file_time=cfg.get("fileTime", 0),
            rec_time=cfg.get("recTime", 0),
            rec_file_size=cfg.get("recFileSize", 0),
            save_path=cfg.get("save", "D:\\录播"),
            mp3_play=cfg.get("mp3play", False),
            hide_time=cfg.get("hideTime", False),
            hide_file_size=cfg.get("hideFileSize", False),
            show_user_count=cfg.get("showUserCount", False),
            run_server=cfg.get("runServer", False),
            server_port=cfg.get("serverPort", 8088),
            push_msg=cfg.get("pushMsg", True),
            push_config=PushConfig(
                live_status=push.get("liveStatus", True),
                rec_start=push.get("recStart", True),
                rec_end=push.get("recEnd", True),
                web_hook_url=push.get("webHookUrl", ""),
                userid=push.get("userid", "@all"),
            ),
        )

        # Parse user section
        self.streamers = []
        for user_data in data.get("user", []):
            try:
                streamer = Streamer.from_dict(user_data)
                self.streamers.append(streamer)
            except Exception as e:
                logger.warning(f"Failed to parse streamer: {e}")

        self._ensure_save_path()
        logger.info(
            f"Loaded config: {len(self.streamers)} streamers, "
            f"interval={self.app_config.interval_time}s, "
            f"quality={self.app_config.definition}"
        )

    def save(self):
        """Save current configuration to JSON file."""
        data = {
            "config": self.app_config.to_dict(),
            "user": [s.to_dict() for s in self.streamers if s.platform != "wechat"],
        }
        try:
            os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.debug("Config saved successfully")
        except IOError as e:
            logger.error(f"Failed to save config: {e}")

    def add_streamer(self, streamer: Streamer):
        """Add a streamer and save config."""
        self.streamers.append(streamer)
        self.save()

    def remove_streamer(self, index: int):
        """Remove a streamer by index and save config."""
        if 0 <= index < len(self.streamers):
            self.streamers.pop(index)
            self.save()

    def _ensure_save_path(self):
        """Ensure the recording save directory exists."""
        save_path = self.app_config.save_path
        if save_path:
            os.makedirs(save_path, exist_ok=True)
