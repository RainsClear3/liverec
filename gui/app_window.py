"""Main application window — modern UI redesign."""

import asyncio
import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from gui.theme import setup_theme, COLORS, HAS_BOOTSTRAP

if HAS_BOOTSTRAP:
    import ttkbootstrap as ttkb
    from ttkbootstrap.constants import *

from core.events import EventBus, EventType
from core.models import AppConfig, Streamer
from platforms.factory import PlatformFactory
from recorder.engine import RecordingEngine
from recorder.monitor import Monitor

logger = logging.getLogger("live_recorder")


class MainWindow:
    """Main application window with modern dark theme."""

    def __init__(self, app, loop: asyncio.AbstractEventLoop):
        self.app = app
        self.loop = loop
        self.config: AppConfig = app.config_manager.app_config
        self.streamers: list[Streamer] = app.config_manager.streamers
        self.monitor: Monitor = app.monitor
        self.engine: RecordingEngine = app.engine
        self.event_bus: EventBus = app.event_bus

        # Create main window
        if HAS_BOOTSTRAP:
            self.root = ttkb.Window(
                title="直播录屏 v2.0",
                themename="darkly",
                size=(1000, 650),
                minsize=(750, 450),
            )
        else:
            self.root = tk.Tk()
            self.root.title("直播录屏 v2.0")
            self.root.geometry("1000x650")
            self.root.minsize(750, 450)
            self.root.configure(bg="#1e1e2e")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Apply theme
        setup_theme(self.root)

        # Try to set icon
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
        if os.path.isfile(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        self._setup_ui()
        self._setup_tray()
        self._refresh_streamer_list()

        # Register thumbnail callback on app
        self.app._thumbnail_callback = self._on_thumbnail_ready

        # Register event callbacks
        self.event_bus.on(EventType.REC_START, self._on_rec_start)
        self.event_bus.on(EventType.REC_END, self._on_rec_end)
        self.event_bus.on(EventType.REC_ERROR, self._on_rec_error)

        # Register monitor status callback
        self.monitor.set_status_callback(self._on_status_change)

        # Periodic UI refresh
        self._refresh_ui_periodic()
        self._refresh_wc_duration()

    def _setup_ui(self):
        """Build the main UI layout with modern design."""
        bg = COLORS["bg_dark"]

        # ─── Toolbar ───
        toolbar = tk.Frame(self.root, bg=COLORS["bg_surface"], height=52)
        toolbar.pack(fill=tk.X, padx=0, pady=0)
        toolbar.pack_propagate(False)

        btn_style = {
            "bg": COLORS["primary"],
            "fg": "#ffffff",
            "activebackground": COLORS["primary_hover"],
            "activeforeground": "#ffffff",
            "font": ("Segoe UI", 10),
            "relief": "flat",
            "bd": 0,
            "cursor": "hand2",
            "padx": 14,
            "pady": 6,
        }

        def _create_btn(parent, text, command, bg=None):
            style = btn_style.copy()
            if bg:
                style["bg"] = bg
            btn = tk.Button(parent, text=text, command=command, **style)
            btn.pack(side=tk.LEFT, padx=(4, 4), pady=8)
            return btn

        _create_btn(toolbar, "+ 添加", self._show_add_dialog, COLORS["primary"])
        _create_btn(toolbar, "🗑 删除", self._remove_streamer, COLORS["danger"])
        _create_btn(toolbar, "▶ 全部开始", self._start_all, COLORS["success"])
        _create_btn(toolbar, "⏹ 全部停止", self._stop_all, COLORS["warning"])
        _create_btn(toolbar, "⏺ 录制选中", self._record_selected, COLORS["accent"])

        # Separator
        sep = tk.Frame(toolbar, bg=COLORS["border"], width=1)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=12)

        _create_btn(toolbar, "⚙ 设置", self._show_settings, COLORS["bg_card"])

        self._sniffer_btn = _create_btn(
            toolbar, "🔍 启动嗅探", self._toggle_sniffer, COLORS["accent"]
        )

        # Right side: status + exit
        right_frame = tk.Frame(toolbar, bg=COLORS["bg_surface"])
        right_frame.pack(side=tk.RIGHT, padx=8)

        self._status_label = tk.Label(
            right_frame, text="就绪", bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"], font=("Segoe UI", 9)
        )
        self._status_label.pack(side=tk.RIGHT, padx=4)

        _create_btn(toolbar, "✕", self._on_close, COLORS["danger"])

        # ─── Main content area ───
        main_pane = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))

        # ─── Notebook (tabs) ───
        notebook_frame = ttk.Frame(main_pane)
        main_pane.add(notebook_frame, weight=3)

        self.notebook = ttk.Notebook(notebook_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Main (other platforms)
        tab_main = ttk.Frame(self.notebook)
        self.notebook.add(tab_main, text="  主页  ")

        # Tab 2: WeChat live streams
        tab_wechat = ttk.Frame(self.notebook)
        self.notebook.add(tab_wechat, text="  视频号直播  ")

        # --- Tab 1: Treeview ---
        list_frame = tk.Frame(tab_main, bg=bg)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        columns = ("nickname", "platform", "status", "recording", "size", "title")
        self.tree = ttk.Treeview(
            list_frame, columns=columns, show="headings", height=10
        )

        self.tree.heading("nickname", text="  昵称", anchor=tk.W)
        self.tree.heading("platform", text="  平台", anchor=tk.W)
        self.tree.heading("status", text="  状态", anchor=tk.W)
        self.tree.heading("recording", text="  录制", anchor=tk.W)
        self.tree.heading("size", text="  文件大小", anchor=tk.W)
        self.tree.heading("title", text="  直播标题", anchor=tk.W)

        self.tree.column("nickname", width=160, minwidth=120)
        self.tree.column("platform", width=80, minwidth=60, anchor=tk.CENTER)
        self.tree.column("status", width=100, minwidth=80, anchor=tk.CENTER)
        self.tree.column("recording", width=90, minwidth=70, anchor=tk.CENTER)
        self.tree.column("size", width=100, minwidth=80, anchor=tk.CENTER)
        self.tree.column("title", width=320, minwidth=200)

        # Tag colors for treeview rows
        self.tree.tag_configure("odd", background=COLORS["bg_card"])
        self.tree.tag_configure("even", background=COLORS["bg_surface"])
        self.tree.tag_configure("live", foreground=COLORS["success"])
        self.tree.tag_configure("recording", foreground=COLORS["warning"])
        self.tree.tag_configure("disabled", foreground=COLORS["text_secondary"])

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # --- Tab 2: WeChat thumbnail grid ---
        wc_outer = tk.Frame(tab_wechat, bg=bg)
        wc_outer.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self._wc_canvas = tk.Canvas(wc_outer, highlightthickness=0, bg=bg)
        wc_scrollbar = ttk.Scrollbar(wc_outer, orient=tk.VERTICAL, command=self._wc_canvas.yview)
        self._wc_grid = tk.Frame(self._wc_canvas, bg=bg)
        self._wc_grid.bind("<Configure>",
                           lambda e: self._wc_canvas.configure(scrollregion=self._wc_canvas.bbox("all")))
        self._wc_canvas_window = self._wc_canvas.create_window(
            (0, 0), window=self._wc_grid, anchor="nw")
        self._wc_canvas.configure(yscrollcommand=wc_scrollbar.set)
        self._wc_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        wc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._wc_canvas.bind("<Configure>", self._on_wc_canvas_resize)
        self._wc_canvas.bind("<MouseWheel>",
                             lambda e: self._wc_canvas.yview_scroll(-e.delta // 120, "units"))

        self._thumb_images = {}
        self._wc_cards = {}
        self._wc_prev_state = None  # snapshot to avoid unnecessary rebuilds

        # ─── Log output ───
        log_frame = tk.Frame(main_pane, bg=bg)
        main_pane.add(log_frame, weight=1)

        log_label = tk.Label(log_frame, text="  运行日志", bg=bg,
                            fg=COLORS["text_secondary"], font=("Segoe UI", 9, "bold"),
                            anchor=tk.W)
        log_label.pack(fill=tk.X, padx=4, pady=(4, 0))

        log_container = tk.Frame(log_frame, bg=COLORS["bg_card"], bd=1, relief="solid")
        log_container.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 4))

        self.log_text = tk.Text(
            log_container, height=6, wrap=tk.WORD, state=tk.DISABLED,
            font=("Consolas", 9), bg=COLORS["bg_card"], fg=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"], relief="flat", bd=0,
            padx=8, pady=4, selectbackground=COLORS["primary"],
        )
        log_scrollbar = tk.Scrollbar(
            log_container, orient=tk.VERTICAL, command=self.log_text.yview,
            bg=COLORS["bg_surface"], troughcolor=COLORS["bg_card"],
        )
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure log text tag colors
        self.log_text.tag_configure("timestamp", foreground=COLORS["text_secondary"])
        self.log_text.tag_configure("info", foreground=COLORS["text_primary"])
        self.log_text.tag_configure("success", foreground=COLORS["success"])
        self.log_text.tag_configure("warning", foreground=COLORS["warning"])
        self.log_text.tag_configure("error", foreground=COLORS["danger"])

    def _setup_tray(self):
        """Setup system tray icon."""
        try:
            import pystray
            from PIL import Image, ImageDraw

            # Create a nicer tray icon (play button shape)
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(59, 130, 246, 255))
            draw.polygon([(24, 18), (24, 46), (48, 32)], fill=(255, 255, 255, 255))

            def on_show(icon=None, item=None):
                self.root.after(0, self._restore_from_tray)

            def on_exit(icon=None, item=None):
                if icon:
                    icon.stop()
                self.root.after(0, self._on_close)

            menu = pystray.Menu(
                pystray.MenuItem("显示窗口", on_show, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", on_exit),
            )
            self._tray_icon = pystray.Icon("live_recorder", img, "直播录屏", menu)
        except ImportError:
            self._tray_icon = None

    def _restore_from_tray(self):
        """Restore window from system tray."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _minimize_to_tray(self):
        """Minimize window to system tray."""
        if self._tray_icon:
            self.root.withdraw()
            threading.Thread(
                target=self._tray_icon.run, daemon=True
            ).start()

    def _on_close(self):
        """Handle window close — ask quit or minimize."""
        if self._tray_icon:
            if messagebox.askyesno("退出", "确定退出程序吗？\n（点否将最小化到托盘）"):
                if self._tray_icon:
                    self._tray_icon.stop()
                self._quit()
            else:
                self._minimize_to_tray()
        else:
            self._quit()

    def _quit(self):
        """Actually quit the application."""
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.app.shutdown(), self.loop
            )
            future.result(timeout=10)
        except Exception as e:
            logger.error(f"Shutdown error: {e}")
        self.root.destroy()

    def _refresh_streamer_list(self):
        """Refresh the treeview (main tab — non-WeChat only)."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, s in enumerate(self.streamers):
            if s.platform == "wechat":
                continue
            platform_display = PlatformFactory.get_platform_display(s.platform)

            if s.is_live:
                status = "🟢 直播中"
            elif s.disable:
                status = "⚫ 已禁用"
            else:
                status = "⚪ 离线"

            rec = "⏺ 录制中" if s.is_recording else ""
            size = ""
            if s.is_recording:
                session = self.engine.get_session(s)
                if session and session.current_file and os.path.exists(session.current_file):
                    size = self._format_size(os.path.getsize(session.current_file))
            title = s.room_title if s.is_live else ""

            # Row styling
            row_bg = "even" if i % 2 == 0 else "odd"
            if s.is_recording:
                tag = "recording"
            elif s.is_live:
                tag = "live"
            elif s.disable:
                tag = "disabled"
            else:
                tag = row_bg

            self.tree.insert(
                "", tk.END, iid=f"m_{i}",
                values=(s.nickname, platform_display, status, rec, size, title),
                tags=(tag, row_bg),
            )

        self._update_status_bar()
        self._refresh_wechat_grid()

    def _update_status_bar(self):
        """Update the status bar label."""
        total = len(self.streamers)
        enabled = sum(1 for s in self.streamers if not s.disable)
        live = sum(1 for s in self.streamers if s.is_live)
        recording = sum(1 for s in self.streamers if s.is_recording)
        status_text = f"监控 {enabled}/{total}  |  直播 {live}  |  录制 {recording}  |  间隔 {self.config.interval_time}s"
        self._status_label.config(text=status_text)

    def _refresh_ui_periodic(self):
        """Periodically refresh UI data from async state."""
        self._refresh_streamer_list()
        self.root.after(5000, self._refresh_ui_periodic)

    def _refresh_wc_duration(self):
        """Update recording duration labels on WeChat cards every second."""
        import time
        for room_id, card in self._wc_cards.items():
            dur_label = getattr(card, "_dur_label", None)
            if dur_label is None:
                continue
            s = next((s for s in self.streamers
                      if s.platform == "wechat" and s.userid == room_id), None)
            if not s or not s.is_recording:
                continue
            session = self.engine.get_session(s)
            if session and session.start_time:
                elapsed = int(time.time() - session.start_time.timestamp())
                h, rem = divmod(elapsed, 3600)
                m, sec = divmod(rem, 60)
                dur_label.config(text=f" {h:02d}:{m:02d}:{sec:02d} " if h else f" {m:02d}:{sec:02d} ")
        self.root.after(1000, self._refresh_wc_duration)

    def _show_add_dialog(self):
        """Show the add streamer dialog."""
        from gui.add_dialog import AddStreamerDialog
        dialog = AddStreamerDialog(self.root, self.loop)
        self.root.wait_window(dialog.top)
        if dialog.result:
            streamer = dialog.result
            for existing in self.streamers:
                if existing.platform == streamer.platform and (
                    (existing.web_rid == streamer.web_rid and streamer.web_rid)
                    or (existing.userid == streamer.userid and streamer.userid)
                ):
                    messagebox.showinfo("提示", f"该主播已存在: {existing.nickname}")
                    return
            self.app.config_manager.add_streamer(streamer)
            self.monitor.set_streamers(self.streamers)
            self._refresh_streamer_list()
            self._log(f"已添加: {streamer.nickname} ({streamer.platform})")

    def _remove_streamer(self):
        """Remove selected streamer."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要删除的主播")
            return

        idx = int(selected[0].replace("m_", ""))
        streamer = self.streamers[idx]

        if messagebox.askyesno("确认删除", f"确定要删除 {streamer.nickname} 吗？"):
            if self.engine.is_recording(streamer):
                asyncio.run_coroutine_threadsafe(
                    self.engine.stop_recording(streamer), self.loop
                )
            self.streamers.pop(idx)
            self.app.config_manager.remove_streamer(idx)
            self.monitor.set_streamers(self.streamers)
            self._refresh_streamer_list()
            self._log(f"已删除: {streamer.nickname}")

    def _start_all(self):
        """Start recording all live streamers."""
        for s in self.streamers:
            s.disable = False
        self.app.config_manager.save()
        self._refresh_streamer_list()

        async def _record_all():
            recorded = []
            for s in self.streamers:
                if s.is_live and not self.engine.is_recording(s):
                    adapter = PlatformFactory.create(s.platform, self.app._http_client)
                    url = await adapter.get_stream_url(s, self.config.definition)
                    if url:
                        await self.engine.start_recording(s, url, adapter.get_headers())
                        recorded.append(s.nickname)
            return recorded

        future = asyncio.run_coroutine_threadsafe(_record_all(), self.loop)
        self._log("正在批量录制...")

        def _poll():
            try:
                if not future.done():
                    self.root.after(500, _poll)
                    return
                names = future.result()
                if names:
                    self._log(f"已开始录制: {', '.join(names)}")
                else:
                    self._log("没有可录制的直播")
            except Exception as e:
                self._log(f"录制失败: {e}")

        self.root.after(500, _poll)

    def _stop_all(self):
        """Stop all recordings."""
        asyncio.run_coroutine_threadsafe(
            self.engine.stop_all(), self.loop
        )
        self._log("已停止全部录制")

    def _record_selected(self):
        """Start recording the selected streamer (manual trigger)."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要录制的主播")
            return
        idx = int(selected[0].replace("m_", ""))
        if idx >= len(self.streamers):
            return
        streamer = self.streamers[idx]

        if self.engine.is_recording(streamer):
            messagebox.showinfo("提示", f"{streamer.nickname} 已在录制中")
            return

        if not streamer.is_live:
            messagebox.showinfo("提示", f"{streamer.nickname} 未在直播中")
            return

        async def _start():
            adapter = PlatformFactory.create(streamer.platform, self.app._http_client)
            stream_url = await adapter.get_stream_url(streamer, self.config.definition)
            if stream_url:
                await self.engine.start_recording(
                    streamer, stream_url, adapter.get_headers()
                )
                return True
            return False

        future = asyncio.run_coroutine_threadsafe(_start(), self.loop)
        self._log(f"正在获取 {streamer.nickname} 的直播流...")

        def _poll():
            try:
                if not future.done():
                    self.root.after(300, _poll)
                    return
                ok = future.result()
                if ok:
                    self._log(f"⏺ 开始录制: {streamer.nickname}")
                else:
                    messagebox.showerror("错误", f"获取 {streamer.nickname} 的直播流失败")
            except Exception as e:
                messagebox.showerror("错误", f"录制失败: {e}")

        self.root.after(300, _poll)

    def _on_tree_double_click(self, event):
        """Toggle streamer enable/disable on double-click."""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        idx = int(item.replace("m_", ""))
        if 0 <= idx < len(self.streamers):
            self.streamers[idx].disable = not self.streamers[idx].disable
            self.app.config_manager.save()
            self.monitor.set_streamers(self.streamers)
            self._refresh_streamer_list()

    def _toggle_sniffer(self):
        if self.app.sniffer and self.app.sniffer.is_running:
            self.app.stop_sniffer()
            self._sniffer_btn.configure(text="🔍 启动嗅探")
            self._log("嗅探已停止")
        else:
            self._log("正在启动嗅探...将关闭并重启微信")
            ok = self.app.start_sniffer()
            if ok and self.app.sniffer and self.app.sniffer.is_running:
                self._sniffer_btn.configure(text="⏹ 停止嗅探")
                self._log("嗅探已启动，微信已重启，请进入视频号直播页面")
            else:
                messagebox.showerror("错误", "嗅探启动失败")

    def _paste_stream_url(self):
        """Paste a m3u8/flv stream URL to start recording."""
        dialog = tk.Toplevel(self.root)
        dialog.title("粘贴视频号直播流地址")
        dialog.geometry("550x220")
        dialog.configure(bg=COLORS["bg_dark"])
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="操作步骤：", font=("Segoe UI", 10, "bold")).pack(
            padx=10, pady=(10, 2), anchor=tk.W
        )
        ttk.Label(dialog, text=(
            "1. 在微信视频号直播间页面，按 F12 打开开发者工具\n"
            "2. 切到 Network 标签，筛选 m3u8 或 flv\n"
            "3. 找到直播流地址，右键 Copy URL\n"
            "4. 粘贴到下方输入框，点击确定开始录制"
        ), justify=tk.LEFT).pack(padx=10, pady=2, anchor=tk.W)

        ttk.Label(dialog, text="直播流地址 (m3u8 / flv)：").pack(
            padx=10, pady=(10, 2), anchor=tk.W
        )

        url_var = tk.StringVar()
        url_entry = ttk.Entry(dialog, textvariable=url_var, width=65)
        url_entry.pack(padx=10, pady=2, fill=tk.X)

        def on_paste():
            try:
                text = dialog.clipboard_get()
                url_var.set(text)
            except tk.TclError:
                pass

        def on_ok():
            url = url_var.get().strip()
            if not url:
                messagebox.showwarning("提示", "请输入流地址", parent=dialog)
                return
            if ".m3u8" not in url and ".flv" not in url:
                messagebox.showwarning("提示", "请输入 m3u8 或 flv 格式的地址", parent=dialog)
                return

            from platforms.wechat import WechatPlatform
            room_id = "manual_paste"
            WechatPlatform.add_stream_url(url, room_id=room_id)

            existing = next(
                (s for s in self.streamers
                 if s.platform == "wechat" and s.userid == room_id),
                None,
            )
            if not existing:
                from core.models import Streamer
                ws = Streamer(platform="wechat", nickname="粘贴的直播流", userid=room_id)
                ws.is_live = True
                self.streamers.append(ws)
                self.monitor.set_streamers(self.streamers)

            self._refresh_streamer_list()
            self._log(f"视频号直播流已添加: {url[:80]}...")
            dialog.destroy()
            messagebox.showinfo("成功", "直播流已添加，程序将自动开始录制")

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(padx=10, pady=10)
        ttk.Button(btn_frame, text="从剪贴板粘贴", command=on_paste).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="确定录制", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _show_settings(self):
        """Show the settings dialog."""
        from gui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.root, self.config)
        self.root.wait_window(dialog.top)
        if dialog.result:
            self.config = dialog.result
            self.app.config_manager.app_config = self.config
            self.app.config_manager.save()
            self._refresh_streamer_list()
            self._log("设置已保存")

    def _on_rec_start(self, event_type, **kwargs):
        """Handle REC_START event (called from async thread)."""
        streamer = kwargs.get("streamer")
        if streamer:
            self.root.after(0, lambda: self._log(f"⏺ 开始录制: {streamer.nickname}"))

    def _on_rec_end(self, event_type, **kwargs):
        """Handle REC_END event (called from async thread)."""
        streamer = kwargs.get("streamer")
        duration = kwargs.get("duration", "")
        size = kwargs.get("size", "")
        if streamer:
            self.root.after(
                0,
                lambda: self._log(
                    f"⏹ 录制结束: {streamer.nickname} (时长: {duration}, 大小: {size})"
                ),
            )

    def _on_rec_error(self, event_type, **kwargs):
        """Handle REC_ERROR event."""
        streamer = kwargs.get("streamer")
        error = kwargs.get("error", "")
        if streamer:
            self.root.after(
                0, lambda: self._log(f"❌ 录制错误: {streamer.nickname}: {error}")
            )

    def _on_status_change(self, streamer: Streamer):
        """Callback from monitor when streamer status changes."""
        self.root.after(0, self._refresh_streamer_list)

    def _on_thumbnail_ready(self, room_id: str, image_path: str):
        """Called from background thread when a thumbnail is captured."""
        logger.info(f"Thumbnail ready: room={room_id} path={image_path}")
        def _update():
            try:
                from PIL import Image, ImageTk
                if not os.path.isfile(image_path):
                    logger.warning(f"Thumbnail file missing: {image_path}")
                    return
                img = Image.open(image_path)
                img.thumbnail((240, 180), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._thumb_images[room_id] = photo
                logger.info(f"Thumbnail loaded: {room_id} ({img.size})")
                card = self._wc_cards.get(room_id)
                if card:
                    lbl = card._img_label
                    lbl.configure(image=photo)
                    lbl.image = photo
                    logger.info(f"Thumbnail applied to card: {room_id}")
                else:
                    logger.info(f"Card not found for {room_id}, cached for next refresh")
            except Exception as e:
                logger.error(f"Thumbnail display error: {e}", exc_info=True)
        self.root.after(0, _update)

    def _on_wc_canvas_resize(self, event):
        """Resize inner grid frame to fill canvas width."""
        self._wc_canvas.itemconfig(self._wc_canvas_window, width=event.width)

    def _refresh_wechat_grid(self):
        """Rebuild the WeChat thumbnail grid only if state changed."""
        wechat_rooms = [s for s in self.streamers if s.platform == "wechat"]

        # Build current state snapshot
        state = tuple(
            (s.userid, s.is_live, s.is_recording, s.nickname)
            for s in wechat_rooms
        )
        if state == self._wc_prev_state:
            return  # no change — skip rebuild to avoid flicker
        self._wc_prev_state = state

        for widget in self._wc_grid.winfo_children():
            widget.destroy()
        self._wc_cards.clear()

        if not wechat_rooms:
            empty_frame = tk.Frame(self._wc_grid, bg=COLORS["bg_dark"])
            empty_frame.pack(fill=tk.BOTH, expand=True)
            tk.Label(
                empty_frame, text="暂无视频号直播",
                bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                font=("Segoe UI", 14, "bold"),
            ).pack(pady=(120, 8))
            tk.Label(
                empty_frame, text="启动嗅探后，进入直播间将自动检测",
                bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
                font=("Segoe UI", 10),
            ).pack()
            return

        cols = max(1, self.root.winfo_width() // 280)
        for idx, s in enumerate(wechat_rooms):
            row, col = divmod(idx, cols)

            # Card container with rounded look
            card = tk.Frame(self._wc_grid, bg=COLORS["bg_card"],
                           highlightbackground=COLORS["border"],
                           highlightthickness=1, bd=0)
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            self._wc_grid.columnconfigure(col, weight=1)

            # Thumbnail
            img_container = tk.Frame(card, bg=COLORS["bg_surface"], height=180)
            img_container.pack(fill=tk.X, padx=6, pady=(6, 0))
            img_container.pack_propagate(False)

            img_label = tk.Label(img_container, bg=COLORS["bg_surface"],
                                anchor="center", fg=COLORS["text_secondary"],
                                font=("Segoe UI", 9))
            img_label.pack(fill=tk.BOTH, expand=True)
            card._img_label = img_label

            photo = self._thumb_images.get(s.userid)
            if photo:
                img_label.configure(image=photo, text="")
                img_label.image = photo
            else:
                img_label.configure(text="加载中...")

            # Info section
            info_frame = tk.Frame(card, bg=COLORS["bg_card"])
            info_frame.pack(fill=tk.X, padx=10, pady=(8, 4))

            name_lbl = tk.Label(info_frame, text=s.nickname, bg=COLORS["bg_card"],
                               fg=COLORS["text_primary"], font=("Segoe UI", 11, "bold"),
                               anchor=tk.W)
            name_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Status badge + duration
            if s.is_live:
                status_text = "直播中"
                status_bg = COLORS["success"]
            elif s.is_recording:
                status_text = "录制中"
                status_bg = COLORS["warning"]
            else:
                status_text = "离线"
                status_bg = COLORS["text_secondary"]

            badge_row = tk.Frame(info_frame, bg=COLORS["bg_card"])
            badge_row.pack(side=tk.RIGHT)

            # Duration label (only when recording)
            card._dur_label = None
            if s.is_recording:
                session = self.engine.get_session(s)
                if session and session.start_time:
                    import time
                    elapsed = int(time.time() - session.start_time.timestamp())
                    h, rem = divmod(elapsed, 3600)
                    m, sec = divmod(rem, 60)
                    dur_text = f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"
                else:
                    dur_text = "00:00"
                dur_lbl = tk.Label(badge_row, text=f" {dur_text} ", bg=COLORS["bg_surface"],
                                  fg=COLORS["warning"], font=("Consolas", 9, "bold"),
                                  padx=4, pady=2)
                dur_lbl.pack(side=tk.LEFT, padx=(0, 4))
                card._dur_label = dur_lbl

            status_badge = tk.Label(badge_row, text=f" {status_text} ",
                                   bg=status_bg, fg="#ffffff",
                                   font=("Segoe UI", 9, "bold"), padx=6, pady=2)
            status_badge.pack(side=tk.LEFT)

            # Action buttons
            btn_frame = tk.Frame(card, bg=COLORS["bg_card"])
            btn_frame.pack(fill=tk.X, padx=6, pady=(4, 8))

            if s.is_live and not s.is_recording:
                record_btn = tk.Button(
                    btn_frame, text="⏺ 开始录制",
                    command=lambda sid=s.userid: self._wc_record(sid),
                    bg=COLORS["success"], fg="#ffffff", font=("Segoe UI", 10),
                    activebackground=COLORS["success"], activeforeground="#ffffff",
                    relief="flat", bd=0, cursor="hand2", padx=12, pady=4,
                )
                record_btn.pack(side=tk.LEFT, padx=4)

            if s.is_recording:
                stop_btn = tk.Button(
                    btn_frame, text="⏹ 停止录制",
                    command=lambda sid=s.userid: self._wc_stop(sid),
                    bg=COLORS["danger"], fg="#ffffff", font=("Segoe UI", 10),
                    activebackground="#dc2626", activeforeground="#ffffff",
                    relief="flat", bd=0, cursor="hand2", padx=12, pady=4,
                )
                stop_btn.pack(side=tk.LEFT, padx=4)

            self._wc_cards[s.userid] = card

    def _wc_record(self, room_id: str):
        """Start recording a WeChat room from the grid."""
        s = next((s for s in self.streamers
                  if s.platform == "wechat" and s.userid == room_id), None)
        if not s:
            return

        async def _start():
            adapter = PlatformFactory.create(s.platform, self.app._http_client)
            url = await adapter.get_stream_url(s, self.config.definition)
            if url:
                await self.engine.start_recording(s, url, adapter.get_headers())
                return True
            return False

        future = asyncio.run_coroutine_threadsafe(_start(), self.loop)
        try:
            ok = future.result(timeout=10)
            if ok:
                self._log(f"⏺ 开始录制: {s.nickname}")
                self._refresh_wechat_grid()
            else:
                messagebox.showerror("错误", "获取直播流失败")
        except Exception as e:
            messagebox.showerror("错误", f"录制失败: {e}")

    def _wc_stop(self, room_id: str):
        """Stop recording a WeChat room from the grid."""
        s = next((s for s in self.streamers
                  if s.platform == "wechat" and s.userid == room_id), None)
        if s:
            asyncio.run_coroutine_threadsafe(
                self.engine.stop_recording(s), self.loop
            )
            self._log(f"⏹ 停止录制: {s.nickname}")
            self.root.after(500, self._refresh_wechat_grid)

    def _log(self, message: str):
        """Append a message to the log text widget."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)

        # Color code log messages
        if "❌" in message or "错误" in message:
            tag = "error"
        elif "⏺" in message or "开始录制" in message:
            tag = "success"
        elif "⏹" in message or "停止" in message:
            tag = "warning"
        else:
            tag = "info"

        self.log_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.log_text.insert(tk.END, f"{message}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes >= 1024 * 1024 * 1024:
            return f"{size_bytes / (1024**3):.1f}GB"
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024**2):.0f}MB"
        if size_bytes >= 1024:
            return f"{size_bytes / 1024:.0f}KB"
        return f"{size_bytes}B"

    def run(self):
        """Start the GUI event loop (blocks until window closes)."""
        self.root.mainloop()
