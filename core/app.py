"""Application orchestrator — bridges GUI thread with async event loop."""

import asyncio
import logging
import threading

from core.config import ConfigManager
from core.events import EventBus, EventType
from core.models import AppConfig
from notify.webhook import WebhookNotifier
from recorder.engine import RecordingEngine
from recorder.monitor import Monitor
from utils.http_client import create_http_client

logger = logging.getLogger("live_recorder")


class App:
    """Central application orchestrator.

    Owns all subsystems and bridges the GUI (main thread) with
    the async event loop (background thread).
    """

    def __init__(self):
        self.config_manager = ConfigManager()
        self.event_bus = EventBus()
        self.engine: RecordingEngine = None
        self.monitor: Monitor = None
        self.notifier: WebhookNotifier = None
        self._http_client = None
        self._loop = None
        self.sniffer = None
        self._thumbnail_callback = None  # called with (room_id, image_path)

    async def initialize(self):
        """Initialize all async subsystems. Must be called on the async event loop."""
        self._loop = asyncio.get_running_loop()
        # Load configuration
        self.config_manager.load()

        # Clean up stale WeChat entries from previous session
        self.config_manager.streamers = [
            s for s in self.config_manager.streamers if s.platform != "wechat"
        ]
        # Persist the cleaned config so old WeChat entries are removed from file
        self.config_manager.save()
        from platforms.wechat import WechatPlatform
        with WechatPlatform._lock:
            WechatPlatform._room_streams.clear()

        config = self.config_manager.app_config

        # Create HTTP client
        self._http_client = await create_http_client()

        # Create recording engine
        self.engine = RecordingEngine(config, self.event_bus)
        self.engine._http_client = self._http_client

        # Create monitor
        self.monitor = Monitor(
            config=config,
            event_bus=self.event_bus,
            engine=self.engine,
            http_client=self._http_client,
        )
        self.monitor.set_streamers(self.config_manager.streamers)

        # Create webhook notifier
        self.notifier = WebhookNotifier(config.push_config, self._http_client)
        if config.push_msg:
            self.event_bus.on(EventType.LIVE_START, self.notifier.on_event)
            self.event_bus.on(EventType.REC_START, self.notifier.on_event)
            self.event_bus.on(EventType.REC_END, self.notifier.on_event)

        # Start monitoring
        await self.monitor.start()
        logger.info("Application initialized successfully")

    def start_sniffer(self):
        """Start the WeChat stream sniffer."""
        if self.sniffer and self.sniffer.is_running:
            return True
        try:
            from wechat.sniffer import StreamSniffer
            from platforms.wechat import WechatPlatform
            from core.models import Streamer as StreamerModel
            self.sniffer = StreamSniffer()
            self._thumb_captured = set()  # rooms already thumbnailed

            def on_stream_captured(url: str, headers: dict, info: dict):
                room_id = info.get("room_id", "")
                if not room_id or not url:
                    return

                # Store URL (thread-safe, has lock)
                WechatPlatform.add_stream_url(url, room_id=room_id, headers=headers)

                # Schedule streamer list mutation on the event loop (thread-safe)
                def _update():
                    streamers = self.config_manager.streamers
                    existing = next(
                        (s for s in streamers
                         if s.platform == "wechat" and s.userid == room_id),
                        None,
                    )
                    if existing:
                        existing.is_live = True
                    else:
                        name = info.get("name", f"视频号_{room_id[:8]}")
                        s = StreamerModel(
                            platform="wechat", nickname=name,
                            userid=room_id, web_rid=room_id,
                        )
                        s.is_live = True
                        streamers.append(s)
                        logger.info(f"New live room: {name} (room={room_id})")
                    if self.monitor and self.monitor._on_status_change:
                        self.monitor._on_status_change(existing or s)

                if self._loop:
                    self._loop.call_soon_threadsafe(_update)
                else:
                    _update()

                # Capture thumbnail (once per room, in background)
                if room_id not in self._thumb_captured:
                    self._thumb_captured.add(room_id)
                    threading.Thread(
                        target=self._capture_thumb,
                        args=(room_id, url, headers),
                        daemon=True,
                    ).start()

            return self.sniffer.start(callback=on_stream_captured)
        except Exception as e:
            logger.error(f"Sniffer start failed: {e}", exc_info=True)
            return False

    def _capture_thumb(self, room_id: str, url: str, headers: dict):
        """Background: capture a frame and notify GUI."""
        try:
            from platforms.wechat import WechatPlatform
            logger.info(f"Capturing thumbnail for room {room_id}...")
            img = WechatPlatform.capture_frame(url, headers)
            if img:
                logger.info(f"Thumbnail captured: {img}")
                if self._thumbnail_callback:
                    self._thumbnail_callback(room_id, img)
            else:
                logger.warning(f"Thumbnail capture failed for room {room_id}")
        except Exception as e:
            logger.error(f"Thumbnail error: {e}", exc_info=True)

    def stop_sniffer(self):
        """Stop the WeChat stream sniffer and restore proxy."""
        if self.sniffer:
            self.sniffer.stop()
            self.sniffer = None

    async def shutdown(self):
        """Gracefully shut down all subsystems."""
        logger.info("Shutting down...")

        # Stop sniffer first (restores system proxy)
        self.stop_sniffer()

        if self.monitor:
            await self.monitor.stop()
        if self.engine:
            await self.engine.stop_all()
        if self._http_client:
            await self._http_client.close()

        # Remove ALL WeChat streamers and URL buffers
        from platforms.wechat import WechatPlatform
        with WechatPlatform._lock:
            WechatPlatform._room_streams.clear()
        self.config_manager.streamers = [
            s for s in self.config_manager.streamers if s.platform != "wechat"
        ]
        logger.info(f"Cleaned up WeChat entries, {len(self.config_manager.streamers)} streamers remaining")

        self.config_manager.save()
        logger.info("Shutdown complete")

        self.config_manager.save()
        logger.info("Shutdown complete")
