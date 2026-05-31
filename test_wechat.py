"""Automated test for WeChat live stream detection and recording.

Run: python test_wechat.py
"""
import asyncio
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))


def ask(msg, title="Test"):
    """Show a dialog asking the user to perform an action."""
    root = tk.Tk()
    root.withdraw()
    result = messagebox.askokcancel(title, msg)
    root.destroy()
    return result


def info(msg, title="Test Result"):
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(title, msg)
    root.destroy()


def run_test():
    # Step 0: Initialize
    from core.app import App
    from platforms.wechat import WechatPlatform

    app = App()
    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()

    future = asyncio.run_coroutine_threadsafe(app.initialize(), loop)
    future.result(timeout=30)
    print("[TEST] App initialized")

    # Step 1: Start sniffer
    if not ask(
        "Step 1: Start sniffer\n\n"
        "Click OK to start the sniffer.\n"
        "WeChat will be killed and restarted with proxy.\n\n"
        "After clicking OK, wait for WeChat to restart,\n"
        "then click OK again on the next prompt."
    ):
        return

    ok = app.start_sniffer()
    if not ok:
        info("FAIL: Sniffer failed to start")
        return
    print("[TEST] Sniffer started")
    time.sleep(3)

    # Step 2: Open live room 1
    if not ask(
        "Step 2: Open live room 1\n\n"
        "In WeChat, navigate to a video channel LIVE page.\n"
        "Wait for the stream to load (you should see video).\n\n"
        "Click OK when the live stream is playing."
    ):
        return

    # Wait for detection
    print("[TEST] Waiting for room 1 detection...")
    detected_room1 = None
    for i in range(30):
        time.sleep(1)
        streamers = app.config_manager.streamers
        wechat_rooms = [s for s in streamers if s.platform == "wechat" and s.is_live]
        if wechat_rooms:
            detected_room1 = wechat_rooms[0]
            break

    if not detected_room1:
        info("FAIL: Room 1 not detected after 30 seconds.\n\n"
             "Check logs for errors.")
        return

    print(f"[TEST] Room 1 detected: {detected_room1.nickname} (id={detected_room1.userid})")

    # Step 3: Open live room 2
    if not ask(
        f"Step 3: Room 1 detected!\n\n"
        f"  Name: {detected_room1.nickname}\n"
        f"  ID: {detected_room1.userid}\n\n"
        "Now open a SECOND live room in WeChat.\n"
        "Navigate to a different live stream.\n\n"
        "Click OK when the second stream is playing."
    ):
        return

    # Wait for second room
    print("[TEST] Waiting for room 2 detection...")
    detected_room2 = None
    for i in range(30):
        time.sleep(1)
        streamers = app.config_manager.streamers
        wechat_rooms = [s for s in streamers if s.platform == "wechat" and s.is_live]
        if len(wechat_rooms) >= 2:
            detected_room2 = [r for r in wechat_rooms if r.userid != detected_room1.userid]
            if detected_room2:
                detected_room2 = detected_room2[0]
                break

    rooms_info = f"Room 1: {detected_room1.nickname} ({detected_room1.userid})\n"
    if detected_room2:
        rooms_info += f"Room 2: {detected_room2.nickname} ({detected_room2.userid})\n"
    else:
        rooms_info += "Room 2: NOT DETECTED\n"

    print(f"[TEST] Rooms: {rooms_info}")

    # Step 4: Record
    if not ask(
        f"Step 4: Recording test\n\n"
        f"Detected rooms:\n{rooms_info}\n"
        "Click OK to start recording all live rooms.\n"
        "Recording will run for 15 seconds, then stop."
    ):
        return

    # Record all live
    async def record_all():
        from platforms.factory import PlatformFactory
        recorded = []
        for s in app.config_manager.streamers:
            if s.platform == "wechat" and s.is_live and not app.engine.is_recording(s):
                adapter = PlatformFactory.create(s.platform, app._http_client)
                url = await adapter.get_stream_url(s, app.config.definition)
                if url:
                    await app.engine.start_recording(s, url, adapter.get_headers())
                    recorded.append(f"{s.nickname}: {url[:60]}...")
                else:
                    recorded.append(f"{s.nickname}: NO URL (probe failed)")
        return recorded

    future = asyncio.run_coroutine_threadsafe(record_all(), loop)
    try:
        results = future.result(timeout=60)
    except Exception as e:
        results = [f"ERROR: {e}"]

    result_text = "\n".join(results) if results else "No rooms recorded"
    print(f"[TEST] Recording results: {result_text}")

    # Wait 15 seconds
    time.sleep(15)

    # Stop recording
    async def stop_all():
        await app.engine.stop_all()

    asyncio.run_coroutine_threadsafe(stop_all(), loop).result(timeout=10)

    # Report
    info(
        f"Test Complete!\n\n"
        f"Detected rooms:\n{rooms_info}\n"
        f"Recording results:\n{result_text}\n\n"
        f"Check {app.config.save_path} for recorded files."
    )

    # Cleanup
    asyncio.run_coroutine_threadsafe(app.shutdown(), loop).result(timeout=10)
    loop.call_soon_threadsafe(loop.stop)


if __name__ == "__main__":
    run_test()
