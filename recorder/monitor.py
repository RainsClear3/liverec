"""Async monitoring scheduler — periodically checks live status for all streamers."""

import asyncio
import logging
from typing import Optional

import aiohttp

from core.events import EventBus, EventType
from core.models import AppConfig, Streamer
from platforms.factory import PlatformFactory
from recorder.engine import RecordingEngine

logger = logging.getLogger("live_recorder")


class Monitor:
    """Periodically checks live status for all enabled streamers.
    Emits LIVE_START/LIVE_END events and triggers recording.
    """

    def __init__(
        self,
        config: AppConfig,
        event_bus: EventBus,
        engine: RecordingEngine,
        http_client: aiohttp.ClientSession,
    ):
        self.config = config
        self.event_bus = event_bus
        self.engine = engine
        self._http = http_client
        self._streamers: list[Streamer] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_status_change: Optional[callable] = None  # GUI callback

    def set_streamers(self, streamers: list[Streamer]):
        """Update the list of streamers to monitor."""
        self._streamers = streamers

    def set_status_callback(self, callback: callable):
        """Register a callback for status changes (for GUI updates)."""
        self._on_status_change = callback

    async def start(self):
        """Start the monitoring loop."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Monitor started (interval={self.config.interval_time}s)")

    async def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Monitor stopped")

    async def check_once(self, streamer: Streamer) -> bool:
        """Manually trigger a single status check for a streamer."""
        return await self._check_streamer(streamer)

    async def _monitor_loop(self):
        """Main monitoring loop — checks all streamers every interval."""
        while self._running:
            try:
                # Build list of checks
                checks = []
                for s in self._streamers:
                    if not s.disable:
                        checks.append(self._check_streamer(s))

                if checks:
                    await asyncio.gather(*checks, return_exceptions=True)

            except Exception as e:
                logger.error(f"Monitor loop error: {e}", exc_info=True)

            # Wait for the configured interval
            try:
                await asyncio.sleep(self.config.interval_time)
            except asyncio.CancelledError:
                break

    async def _check_streamer(self, streamer: Streamer):
        """Check live status for a single streamer and handle transitions."""
        try:
            adapter = PlatformFactory.create(streamer.platform, self._http)

            # For WeChat: browser must be open for capture to work.
            # check_live_status will open the browser if needed (first time only).
            was_live = streamer.is_live
            is_live = await adapter.check_live_status(streamer)

            # No change in status
            if is_live == was_live:
                return

            streamer.is_live = is_live

            # Notify GUI
            if self._on_status_change:
                self._on_status_change(streamer)

            if is_live and not was_live:
                # Transition: offline -> live
                logger.info(
                    f"🔴 {streamer.nickname} ({adapter.PLATFORM_DISPLAY}) "
                    f"started live: {streamer.room_title}"
                )
                await self.event_bus.emit(
                    EventType.LIVE_START,
                    streamer=streamer,
                    adapter=adapter,
                )

                # Auto-start recording for non-WeChat platforms
                # (WeChat requires manual recording — user clicks 录制)
                if streamer.platform != "wechat":
                    if not self.engine.is_recording(streamer):
                        stream_url = await adapter.get_stream_url(
                            streamer, self.config.definition
                        )
                        if stream_url:
                            await self.engine.start_recording(
                                streamer, stream_url, adapter.get_headers()
                            )
                        else:
                            logger.warning(
                                f"Failed to get stream URL for {streamer.nickname}"
                            )

            elif not is_live and was_live:
                # Transition: live -> offline
                logger.info(
                    f"⚫ {streamer.nickname} ({adapter.PLATFORM_DISPLAY}) "
                    f"ended live"
                )
                await self.event_bus.emit(
                    EventType.LIVE_END,
                    streamer=streamer,
                )

                # Auto-stop recording
                if self.engine.is_recording(streamer):
                    await self.engine.stop_recording(streamer)

        except Exception as e:
            logger.error(
                f"Error checking {streamer.nickname}: {e}", exc_info=True
            )
