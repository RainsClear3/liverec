"""Event bus for decoupled communication between components."""

import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger("live_recorder")


class EventType(Enum):
    LIVE_START = "live_start"
    LIVE_END = "live_end"
    REC_START = "rec_start"
    REC_END = "rec_end"
    REC_ERROR = "rec_error"
    STREAM_DISCONNECT = "stream_disconnect"


class EventBus:
    """Simple async publish/subscribe event bus."""

    def __init__(self):
        self._listeners: dict[EventType, list[Callable]] = {}

    def on(self, event_type: EventType, callback: Callable):
        """Register a callback (sync or async) for an event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def off(self, event_type: EventType, callback: Callable):
        """Unregister a callback."""
        if event_type in self._listeners:
            self._listeners[event_type] = [
                cb for cb in self._listeners[event_type] if cb != callback
            ]

    async def emit(self, event_type: EventType, **kwargs):
        """Emit an event, calling all registered callbacks."""
        listeners = self._listeners.get(event_type, [])
        for callback in listeners:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_type=event_type, **kwargs)
                else:
                    callback(event_type=event_type, **kwargs)
            except Exception as e:
                logger.error(f"Event callback error for {event_type}: {e}", exc_info=True)
