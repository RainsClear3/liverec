"""Main application window with streamer list, log output, and status bar."""

import asyncio
import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

try:
    import ttkbootstrap as ttkb
    from ttkbootstrap.constants import *
    HAS_BOOTSTRAP = True
except ImportError:
    HAS_BOOTSTRAP = False

from core.events import EventBus, EventType
from core.models import AppConfig, Streamer
from platforms.factory import PlatformFactory
from recorder.engine import RecordingEngine
from recorder.monitor import Monitor

logger = logging.getLogger("live_recorder")


class MainWindow:
    """Main application window."""

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
                themename="cosmo",
                size=(900, 600),
                minsize=(700, 400),
            )
        else:
            self.root = tk.Tk()
            self.root.title("直播录屏 v2.0")
            self.root.geometry("900x600")
            self.root.minsize(700, 400)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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

    def _setup_ui(self):
        """Build the main UI layout."""
        # Menu bar
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="添加主播", command=self._show_add_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="设置", command=self._show_settings)
        menubar.add_cascade(label="设置", menu=settings_menu)

        self.root.config(menu=menubar)

        # Toolbar frame
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=(5, 0))

        ttk.Button(toolbar, text="➕ 添加", command=self._show_add_dialog).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="🗑 删除", command=self._remove_streamer).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=2
        )
        ttk.Button(toolbar, text="▶ 全部开始", command=self._start_all).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="⏹ 全部停止", command=self._stop_all).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(toolbar, text="⏺ 录制选中", command=self._record_selected).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=2
        )
        ttk.Button(toolbar, text="⚙ 设置", command=self._show_settings).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=2
        )
        self._sniffer_btn = ttk.Button(
            toolbar, text="🔍 启动视频号嗅探", command=self._toggle_sniffer
        )
        self._sniffer_btn.pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=2
        )
        ttk.Button(toolbar, text="❌ 退出", command=self._on_close).pack(
            side=tk.LEFT, padx=2
        )

        # Main content: Notebook (tabs) + Log
        main_pane = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Notebook with tabs
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
        list_frame = ttk.Frame(tab_main)
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("nickname", "platform", "status", "recording", "size", "title")
        self.tree = ttk.Treeview(
            list_frame, columns=columns, show="headings", height=10
        )
        self.tree.heading("nickname", text="昵称")
        self.tree.heading("platform", text="平台")
        self.tree.heading("status", text="状态")
        self.tree.heading("recording", text="录制")
        self.tree.heading("size", text="文件大小")
        self.tree.heading("title", text="直播标题")

        self.tree.column("nickname", width=150)
        self.tree.column("platform", width=60, anchor=tk.CENTER)
        self.tree.column("status", width=80, anchor=tk.CENTER)
        self.tree.column("recording", width=80, anchor=tk.CENTER)
        self.tree.column("size", width=100, anchor=tk.CENTER)
        self.tree.column("title", width=300)

        # Style for separator rows
        self.tree.tag_configure("separator", background="#ddd", foreground="#666")
        self.tree.tag_configure("wechat", foreground="#0066cc")
        self.tree.tag_configure("wechat_live", foreground="#009900")

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Double-click to toggle enable/disable
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # --- Tab 2: WeChat thumbnail grid ---
        self._wc_canvas = tk.Canvas(tab_wechat, highlightthickness=0)
        wc_scrollbar = ttk.Scrollbar(tab_wechat, orient=tk.VERTICAL, command=self._wc_canvas.yview)
        self._wc_grid = ttk.Frame(self._wc_canvas)
        self._wc_grid.bind("<Configure>",
                           lambda e: self._wc_canvas.configure(scrollregion=self._wc_canvas.bbox("all")))
        self._wc_canvas_window = self._wc_canvas.create_window(
            (0, 0), window=self._wc_grid, anchor="nw")
        self._wc_canvas.configure(yscrollcommand=wc_scrollbar.set)
        self._wc_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        wc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # Resize inner frame to fill canvas width
        self._wc_canvas.bind("<Configure>", self._on_wc_canvas_resize)
        # Mouse wheel scroll
        self._wc_canvas.bind("<MouseWheel>",
                             lambda e: self._wc_canvas.yview_scroll(-e.delta // 120, "units"))

        self._thumb_images = {}  # room_id -> PhotoImage (prevent GC)
        self._wc_cards = {}      # room_id -> Frame widget

        # Log output (bottom)
        log_frame = ttk.LabelFrame(main_pane, text="日志")
        main_pane.add(log_frame, weight=1)

        self.log_text = tk.Text(
            log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9)
        )
        log_scrollbar = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Status bar
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(
            self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=(0, 5))

    def _setup_tray(self):
        """Setup system tray icon."""
        try:
            import pystray
            from PIL import Image

            # Create a simple green dot icon
            img = Image.new("RGB", (64, 64), (0, 128, 0))

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
            status = "🔴 直播中" if s.is_live else ("⚫ 禁用" if s.disable else "⚫ 离线")
            rec = "● 录制中" if s.is_recording else ""
            size = ""
            if s.is_recording:
                session = self.engine.get_session(s)
                if session and session.current_file and os.path.exists(session.current_file):
                    size = self._format_size(os.path.getsize(session.current_file))
            title = s.room_title if s.is_live else ""
            tags = ("disabled",) if s.disable else (("live",) if s.is_live else ())
            self.tree.insert(
                "", tk.END, iid=f"m_{i}",
                values=(s.nickname, platform_display, status, rec, size, title),
                tags=tags,
            )

        self.tree.tag_configure("disabled", foreground="gray")
        self.tree.tag_configure("live", foreground="green")
        self._update_status_bar()
        self._refresh_wechat_grid()

    def _update_status_bar(self):
        """Update the bottom status bar."""
        total = len(self.streamers)
        enabled = sum(1 for s in self.streamers if not s.disable)
        live = sum(1 for s in self.streamers if s.is_live)
        recording = sum(1 for s in self.streamers if s.is_recording)
        self.status_var.set(
            f"监控 {enabled}/{total} | "
            f"直播 {live} | "
            f"录制 {recording} | "
            f"间隔 {self.config.interval_time}s"
        )

    def _refresh_ui_periodic(self):
        """Periodically refresh UI data from async state."""
        self._refresh_streamer_list()
        self.root.after(5000, self._refresh_ui_periodic)

    def _show_add_dialog(self):
        """Show the add streamer dialog."""
        from gui.add_dialog import AddStreamerDialog
        dialog = AddStreamerDialog(self.root, self.loop)
        self.root.wait_window(dialog.top)
        if dialog.result:
            streamer = dialog.result
            # Check for duplicates (same platform + web_rid or userid)
            for existing in self.streamers:
                if existing.platform == streamer.platform and (
                    (existing.web_rid == streamer.web_rid and streamer.web_rid)
                    or (existing.userid == streamer.userid and streamer.userid)
                ):
                    messagebox.showinfo("提示", f"该主播已存在: {existing.nickname}")
                    return
            # Only call add_streamer (it appends to self.streamers internally)
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
            # Stop recording if active
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
            self._sniffer_btn.configure(text="🔍 启动视频号嗅探")
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
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="操作步骤：", font=("", 10, "bold")).pack(
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

            # Add to WeChat platform captured streams
            from platforms.wechat import WechatPlatform
            room_id = "manual_paste"
            WechatPlatform.add_stream_url(url, room_id=room_id)

            # Ensure there's a WeChat streamer to record
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
                # Update card if it exists
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
        """Rebuild the WeChat thumbnail grid."""
        wechat_rooms = [s for s in self.streamers if s.platform == "wechat"]

        # Destroy old cards
        for widget in self._wc_grid.winfo_children():
            widget.destroy()
        self._wc_cards.clear()

        if not wechat_rooms:
            ttk.Label(self._wc_grid, text="暂无视频号直播\n启动嗅探后，进入直播间将自动检测",
                      font=("", 12), foreground="gray").pack(pady=50)
            return

        cols = max(1, self.root.winfo_width() // 260)
        for idx, s in enumerate(wechat_rooms):
            row, col = divmod(idx, cols)
            card = ttk.Frame(self._wc_grid, relief="groove", borderwidth=2)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

            # Thumbnail placeholder
            img_label = ttk.Label(card)
            img_label.pack(padx=5, pady=(5, 0))
            card._img_label = img_label

            # Show cached thumbnail if available
            photo = self._thumb_images.get(s.userid)
            if photo:
                img_label.configure(image=photo)
                img_label.image = photo
            else:
                img_label.configure(text="加载中...", width=20, anchor="center")

            # Name + status
            name_lbl = ttk.Label(card, text=s.nickname, font=("", 10, "bold"))
            name_lbl.pack(padx=5, pady=(2, 0))

            status_text = "🔴 直播中" if s.is_live else "⚫ 离线"
            if s.is_recording:
                status_text = "● 录制中"
            status_lbl = ttk.Label(card, text=status_text,
                                   foreground="green" if s.is_live else "gray")
            status_lbl.pack(padx=5)

            # Buttons
            btn_frame = ttk.Frame(card)
            btn_frame.pack(padx=5, pady=(2, 8))

            if s.is_live and not s.is_recording:
                ttk.Button(btn_frame, text="录制",
                           command=lambda sid=s.userid: self._wc_record(sid)).pack(side=tk.LEFT, padx=2)
            if s.is_recording:
                ttk.Button(btn_frame, text="停止",
                           command=lambda sid=s.userid: self._wc_stop(sid)).pack(side=tk.LEFT, padx=2)

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
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
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
