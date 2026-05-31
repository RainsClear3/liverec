"""直播录屏 v2.0 — 入口文件

Multi-platform live stream recorder supporting Douyin, Bilibili, and WeChat Channels.
No concurrent recording limit. FFmpeg-based with zero-encoding (-c copy).
"""

import asyncio
import os
import sys
import threading

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from utils.logger import setup_logger
from core.app import App


def main():
    # 1. Setup logging
    logger = setup_logger()
    logger.info("=" * 60)
    logger.info("直播录屏 v2.0 starting...")
    logger.info(f"Python {sys.version}")
    logger.info(f"Project root: {PROJECT_ROOT}")
    logger.info("=" * 60)

    # 2. Create application
    app = App()

    # 3. Start async event loop in background thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    thread = threading.Thread(target=loop.run_forever, daemon=True, name="AsyncLoop")
    thread.start()

    # 4. Initialize async subsystems on that loop
    try:
        future = asyncio.run_coroutine_threadsafe(app.initialize(), loop)
        future.result(timeout=30)
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}", exc_info=True)
        print(f"启动失败: {e}")
        sys.exit(1)

    # 5. Start GUI on main thread (tkinter requires main thread)
    try:
        from gui.app_window import MainWindow
        gui = MainWindow(app, loop)
        gui.run()
    except ImportError as e:
        logger.error(f"GUI import error: {e}")
        print(f"GUI 加载失败，请安装依赖: pip install ttkbootstrap pystray Pillow")
        print(f"错误详情: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"GUI error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # 6. Cleanup
        try:
            future = asyncio.run_coroutine_threadsafe(app.shutdown(), loop)
            future.result(timeout=10)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        logger.info("Application exited")


if __name__ == "__main__":
    main()
