"""FFmpeg recording engine — manages subprocess lifecycle, auto-split, reconnect."""

import asyncio
import logging
import os
import platform as plat
import re
import shutil
import signal
import time
from datetime import datetime
from typing import Optional

from core.models import AppConfig, RecordingSession, Streamer
from core.events import EventBus, EventType

logger = logging.getLogger("live_recorder")


def find_ffmpeg() -> str:
    """Find ffmpeg executable path."""
    # Check project ffmpeg/ directory first
    project_ffmpeg = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "ffmpeg", "ffmpeg.exe"
    )
    if os.path.isfile(project_ffmpeg):
        return project_ffmpeg

    # Check system PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    return "ffmpeg"  # Hope it's in PATH


class RecordingEngine:
    """Manages FFmpeg recording sessions for multiple streamers."""

    def __init__(self, config: AppConfig, event_bus: EventBus):
        self.config = config
        self.event_bus = event_bus
        self.ffmpeg_path = find_ffmpeg()
        self._http_client = None
        self._sessions: dict[str, RecordingSession] = {}  # keyed by streamer.userid
        self._tasks: dict[str, asyncio.Task] = {}

    @property
    def active_sessions(self) -> dict[str, RecordingSession]:
        return {k: v for k, v in self._sessions.items() if v.is_active}

    def is_recording(self, streamer: Streamer) -> bool:
        session = self._sessions.get(streamer.userid)
        return session is not None and session.is_active

    def get_session(self, streamer: Streamer) -> Optional[RecordingSession]:
        return self._sessions.get(streamer.userid)

    async def start_recording(
        self,
        streamer: Streamer,
        stream_url: str,
        headers: Optional[dict] = None,
    ) -> Optional[RecordingSession]:
        """Start recording a stream for the given streamer."""
        if self.is_recording(streamer):
            logger.warning(f"Already recording {streamer.nickname}")
            return None

        # Create output directory
        output_dir = os.path.join(self.config.save_path, streamer.nickname)
        os.makedirs(output_dir, exist_ok=True)

        # Create recording session
        session = RecordingSession(
            streamer=streamer,
            start_time=datetime.now(),
            output_dir=output_dir,
            is_active=True,
        )
        self._sessions[streamer.userid] = session
        streamer.is_recording = True

        # Start the recording task
        task = asyncio.create_task(
            self._recording_loop(session, stream_url, headers or {})
        )
        self._tasks[streamer.userid] = task

        logger.info(f"Started recording: {streamer.nickname}")
        await self.event_bus.emit(
            EventType.REC_START,
            streamer=streamer,
            session=session,
        )
        return session

    async def stop_recording(self, streamer: Streamer):
        """Stop recording for the given streamer."""
        session = self._sessions.get(streamer.userid)
        if not session or not session.is_active:
            return

        session.is_active = False
        streamer.is_recording = False

        # Cancel the recording task
        task = self._tasks.get(streamer.userid)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Calculate duration
        duration = time.time() - session.start_time.timestamp()
        session.duration_seconds = duration

        # Calculate total file size
        total_size = self._get_session_size(session)

        logger.info(
            f"Stopped recording: {streamer.nickname}, "
            f"duration={self._format_duration(duration)}, "
            f"size={self._format_size(total_size)}"
        )
        await self.event_bus.emit(
            EventType.REC_END,
            streamer=streamer,
            session=session,
            duration=self._format_duration(duration),
            size=self._format_size(total_size),
        )

    async def stop_all(self):
        """Stop all active recordings."""
        streamers = [s.streamer for s in self.active_sessions.values()]
        for streamer in streamers:
            await self.stop_recording(streamer)

    async def _recording_loop(
        self,
        session: RecordingSession,
        stream_url: str,
        headers: dict,
    ):
        """Main recording loop with auto-split and reconnect."""
        reconnect_delay = 5
        max_reconnect_delay = 60

        while session.is_active:
            # Build output path
            output_path = session.build_output_filename(self.config)
            session.current_file = output_path

            # Build and launch FFmpeg
            cmd = self._build_ffmpeg_cmd(stream_url, output_path, headers)
            logger.debug(f"FFmpeg cmd: {' '.join(cmd)}")

            process = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                session.ffmpeg_pid = process.pid
                logger.info(
                    f"FFmpeg started for {session.streamer.nickname} "
                    f"(PID={process.pid}, output={os.path.basename(output_path)})"
                )

                # Monitor the process
                split_reason = await self._monitor_process(session, process)

                # Wait for process to exit
                await process.wait()

                if not session.is_active:
                    break  # User stopped recording

                if split_reason:
                    # Auto-split: increment index and continue
                    logger.info(
                        f"Auto-split ({split_reason}) for {session.streamer.nickname}, "
                        f"file_index={session.file_index}"
                    )
                    session.file_index += 1
                    reconnect_delay = 5  # Reset reconnect delay
                    continue
                else:
                    # Unexpected exit — try to reconnect
                    logger.warning(
                        f"FFmpeg exited unexpectedly for {session.streamer.nickname} "
                        f"(code={process.returncode})"
                    )

            except asyncio.CancelledError:
                if process and process.returncode is None:
                    await self._kill_process(process)
                raise
            except Exception as e:
                logger.error(f"Recording error for {session.streamer.nickname}: {e}")

            if not session.is_active:
                break

            # Reconnect with backoff
            logger.info(
                f"Reconnecting {session.streamer.nickname} in {reconnect_delay}s..."
            )
            await asyncio.sleep(reconnect_delay)

            # Re-fetch stream URL
            from platforms.factory import PlatformFactory
            try:
                adapter = PlatformFactory.create(
                    session.streamer.platform,
                    self._http_client,
                )
                new_url = await adapter.get_stream_url(
                    session.streamer, self.config.definition
                )
                if new_url:
                    stream_url = new_url
                    reconnect_delay = 5
                else:
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
            except Exception as e:
                logger.error(f"Reconnect URL fetch error: {e}")
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

    async def _monitor_process(
        self, session: RecordingSession, process: asyncio.subprocess.Process
    ) -> Optional[str]:
        """Monitor FFmpeg process for errors and auto-split conditions.
        Returns split reason ("size" or "time") if auto-split needed, None otherwise.
        """
        segment_start = time.time()

        async def read_stderr():
            """Read and log FFmpeg stderr."""
            try:
                while process.returncode is None:
                    line = await asyncio.wait_for(
                        process.stderr.readline(), timeout=5.0
                    )
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").strip()
                    if text and "size=" in text:
                        # Parse progress line for size info
                        size_match = re.search(r"size=\s*(\d+)(\w+)", text)
                        if size_match:
                            val = int(size_match.group(1))
                            unit = size_match.group(2).upper()
                            if unit == "KB":
                                session.bytes_written = val * 1024
                            elif unit == "MB":
                                session.bytes_written = val * 1024 * 1024
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception:
                pass

        stderr_task = asyncio.create_task(read_stderr())

        try:
            while process.returncode is None:
                await asyncio.sleep(2)

                # Check file size limit
                if self.config.file_size > 0:
                    current_size = os.path.getsize(session.current_file) if os.path.exists(session.current_file) else 0
                    size_mb = current_size / (1024 * 1024)
                    if size_mb >= self.config.file_size:
                        await self._kill_process(process)
                        stderr_task.cancel()
                        return "size"

                # Check time limit
                if self.config.file_time > 0:
                    elapsed = time.time() - segment_start
                    if elapsed >= self.config.file_time:
                        await self._kill_process(process)
                        stderr_task.cancel()
                        return "time"

        except asyncio.CancelledError:
            stderr_task.cancel()
            raise
        finally:
            if not stderr_task.done():
                stderr_task.cancel()

        return None

    def _build_ffmpeg_cmd(
        self, stream_url: str, output_path: str, headers: dict
    ) -> list[str]:
        """Build the FFmpeg command line."""
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-loglevel", "warning",
            "-hide_banner",
            "-rw_timeout", "10000000",  # 10s read/write timeout (microseconds)
        ]

        # User-Agent via dedicated flag
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")
        cmd.extend(["-user_agent", ua])

        # Referer via dedicated flag
        referer = headers.get("Referer", headers.get("referer", ""))
        if referer:
            cmd.extend(["-referer", referer])

        # Additional headers via -headers
        extra = []
        for key, value in headers.items():
            if key.lower() not in ("user-agent", "referer"):
                extra.append(f"{key}: {value}")
        if extra:
            cmd.extend(["-headers", "\r\n".join(extra) + "\r\n"])

        # Map format names to FFmpeg format identifiers
        fmt_map = {
            "ts": "mpegts",
            "mp4": "mp4",
            "flv": "flv",
            "mkv": "matroska",
        }
        ffmpeg_fmt = fmt_map.get(self.config.out_format, self.config.out_format)

        # Input
        cmd.extend([
            "-i", stream_url,
            "-c", "copy",          # No re-encoding
            "-f", ffmpeg_fmt,
        ])

        # Output
        cmd.append(output_path)
        return cmd

    async def _kill_process(self, process: asyncio.subprocess.Process):
        """Kill FFmpeg process (platform-aware)."""
        try:
            if process.returncode is not None:
                return
            if plat.system() == "Windows":
                process.terminate()
            else:
                process.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        except ProcessLookupError:
            pass

    @staticmethod
    def _format_duration(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h}h{m:02d}m{s:02d}s"
        return f"{m}m{s:02d}s"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes >= 1024 * 1024 * 1024:
            return f"{size_bytes / (1024**3):.1f}GB"
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024**2):.0f}MB"
        if size_bytes >= 1024:
            return f"{size_bytes / 1024:.0f}KB"
        return f"{size_bytes}B"

    @staticmethod
    def _get_session_size(session: RecordingSession) -> int:
        """Get total size of all files in the session's output directory."""
        total = 0
        if os.path.isdir(session.output_dir):
            for fname in os.listdir(session.output_dir):
                fpath = os.path.join(session.output_dir, fname)
                if os.path.isfile(fpath):
                    total += os.path.getsize(fpath)
        return total
