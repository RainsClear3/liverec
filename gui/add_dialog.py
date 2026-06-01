"""Add streamer dialog — modern dark theme version."""

import asyncio
import logging
import re
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from gui.theme import setup_theme, COLORS, HAS_BOOTSTRAP
from core.models import Streamer
from platforms.factory import PlatformFactory

logger = logging.getLogger("live_recorder")


class AddStreamerDialog:
    """Dialog for adding a new streamer."""

    def __init__(self, parent, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.result: Optional[Streamer] = None

        self.top = tk.Toplevel(parent)
        self.top.title("添加主播")
        self.top.geometry("520x500")
        self.top.resizable(False, False)
        self.top.configure(bg=COLORS["bg_dark"])
        self.top.transient(parent)
        self.top.grab_set()

        setup_theme(self.top)
        self._setup_ui()

    def _setup_ui(self):
        bg = COLORS["bg_dark"]

        # Title
        title_label = tk.Label(self.top, text="添加主播", bg=bg,
                              fg=COLORS["text_primary"], font=("Segoe UI", 14, "bold"))
        title_label.pack(padx=15, pady=(15, 5), anchor=tk.W)

        # Platform selection
        plat_frame = tk.LabelFrame(self.top, text="选择平台", bg=bg,
                                  fg=COLORS["text_secondary"],
                                  font=("Segoe UI", 10), bd=1, relief="solid",
                                  highlightbackground=COLORS["border"])
        plat_frame.pack(fill=tk.X, padx=15, pady=(8, 4))

        self.platform_var = tk.StringVar(value="bilibili")
        platforms = PlatformFactory.list_platforms()
        for ptype, display in platforms:
            rb = ttk.Radiobutton(
                plat_frame, text=display, variable=self.platform_var, value=ptype,
                command=self._on_platform_change,
            )
            rb.pack(side=tk.LEFT, padx=15, pady=10)

        # --- URL input frame (for Douyin / Bilibili) ---
        self.url_frame = tk.LabelFrame(self.top, text="直播间 URL（粘贴链接自动识别）",
                                      bg=bg, fg=COLORS["text_secondary"],
                                      font=("Segoe UI", 10), bd=1, relief="solid",
                                      highlightbackground=COLORS["border"])

        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(self.url_frame, textvariable=self.url_var, width=50)
        url_entry.pack(fill=tk.X, padx=8, pady=8)

        btn_frame_url = tk.Frame(self.url_frame, bg=bg)
        btn_frame_url.pack(fill=tk.X, padx=8, pady=(0, 8))

        btn_style = {
            "bg": COLORS["primary"],
            "fg": "#ffffff",
            "font": ("Segoe UI", 10),
            "relief": "flat",
            "bd": 0,
            "cursor": "hand2",
            "padx": 12,
            "pady": 4,
        }

        tk.Button(btn_frame_url, text="粘贴", command=self._paste_url, **btn_style
                 ).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame_url, text="自动识别", command=self._auto_detect, **btn_style
                 ).pack(side=tk.LEFT, padx=4)

        # --- WeChat frame (for video号) ---
        self.wechat_frame = tk.LabelFrame(self.top, text="视频号 — 手动捕获流地址",
                                         bg=bg, fg=COLORS["text_secondary"],
                                         font=("Segoe UI", 10), bd=1, relief="solid",
                                         highlightbackground=COLORS["border"])

        tk.Label(
            self.wechat_frame,
            text="步骤：\n"
                 "1. 打开微信 → 视频号 → 直播，进入直播间\n"
                 "2. 用 Fiddler / Charles / 浏览器 F12 抓包\n"
                 "3. 找到 .m3u8 或 .flv 开头的流地址\n"
                 "4. 复制该地址，粘贴到下方输入框\n"
                 "5. 点击「添加流地址」",
            justify=tk.LEFT, bg=bg, fg=COLORS["text_primary"],
            font=("Segoe UI", 10), anchor=tk.W,
        ).pack(padx=12, pady=8, anchor=tk.W)

        url_row = tk.Frame(self.wechat_frame, bg=bg)
        url_row.pack(fill=tk.X, padx=12, pady=(0, 10))
        self._wechat_url_var = tk.StringVar()
        ttk.Entry(url_row, textvariable=self._wechat_url_var, width=40).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8)
        )
        tk.Button(url_row, text="添加流地址", command=self._add_wechat_url, **btn_style
                 ).pack(side=tk.LEFT)

        # --- Manual input fields ---
        manual_frame = tk.LabelFrame(self.top, text="主播信息", bg=bg,
                                    fg=COLORS["text_secondary"],
                                    font=("Segoe UI", 10), bd=1, relief="solid",
                                    highlightbackground=COLORS["border"])
        # Initialize platform-specific frame visibility FIRST
        self._on_platform_change()

        manual_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=4)

        fields = [
            ("昵称:", "nickname"),
            ("用户ID:", "userid"),
            ("房间号:", "web_rid"),
            ("Sec UID:", "sec_uid"),
        ]
        self.entries = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(manual_frame, text=label, bg=bg, fg=COLORS["text_primary"],
                    font=("Segoe UI", 10), anchor=tk.W).grid(
                row=i, column=0, sticky=tk.W, padx=10, pady=5
            )
            var = tk.StringVar()
            entry = ttk.Entry(manual_frame, textvariable=var, width=35)
            entry.grid(row=i, column=1, sticky=tk.EW, padx=10, pady=5)
            self.entries[key] = var
        manual_frame.columnconfigure(1, weight=1)

        # --- Bottom buttons ---
        btn_bottom = tk.Frame(self.top, bg=bg)
        btn_bottom.pack(fill=tk.X, padx=15, pady=(8, 15))

        cancel_btn = tk.Button(
            btn_bottom, text="取消", command=self._on_cancel,
            bg=COLORS["bg_surface"], fg=COLORS["text_primary"],
            font=("Segoe UI", 10), relief="flat", bd=0, cursor="hand2",
            padx=16, pady=6,
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(6, 0))

        ok_btn = tk.Button(
            btn_bottom, text="确定", command=self._on_ok,
            bg=COLORS["primary"], fg="#ffffff",
            font=("Segoe UI", 10, "bold"), relief="flat", bd=0, cursor="hand2",
            padx=16, pady=6,
        )
        ok_btn.pack(side=tk.RIGHT, padx=(6, 0))

    def _on_platform_change(self):
        """Show/hide frames based on selected platform."""
        platform = self.platform_var.get()
        if platform == "wechat":
            self.url_frame.pack_forget()
            self.wechat_frame.pack(fill=tk.X, padx=15, pady=4)
        else:
            self.wechat_frame.pack_forget()
            self.url_frame.pack(fill=tk.X, padx=15, pady=4)

    def _paste_url(self):
        try:
            text = self.top.clipboard_get()
            self.url_var.set(text)
        except tk.TclError:
            pass

    def _auto_detect(self):
        """Auto-detect platform from URL and fetch streamer info."""
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo("提示", "请先输入直播间 URL")
            return

        platform_type = PlatformFactory.detect_platform(url)
        if not platform_type:
            messagebox.showwarning("识别失败", "无法识别该链接的平台")
            return

        self.platform_var.set(platform_type)
        self._on_platform_change()

        try:
            self.top.config(cursor="wait")
            self.top.update()

            async def fetch_info():
                from utils.http_client import create_http_client
                client = await create_http_client()
                try:
                    adapter = PlatformFactory.create(platform_type, client)
                    return await adapter.parse_room_url(url)
                finally:
                    await client.close()

            future = asyncio.run_coroutine_threadsafe(fetch_info(), self.loop)
            info = future.result(timeout=30)

            if info:
                for key in ("nickname", "userid", "web_rid", "sec_uid"):
                    if info.get(key):
                        self.entries[key].set(info[key])
                messagebox.showinfo(
                    "识别成功",
                    f"平台: {PlatformFactory.get_platform_display(platform_type)}\n"
                    f"昵称: {info.get('nickname', '')}"
                )
            else:
                messagebox.showwarning("识别失败", "无法获取主播信息，请手动填写")
        except Exception as e:
            logger.error(f"Auto-detect error: {e}")
            messagebox.showerror("错误", f"识别出错: {e}")
        finally:
            self.top.config(cursor="")

    def _add_wechat_url(self):
        """Add a manually captured stream URL for WeChat recording."""
        url = self._wechat_url_var.get().strip()
        if not url:
            messagebox.showinfo("提示", "请先粘贴流地址 (.m3u8 或 .flv)")
            return
        if ".m3u8" not in url and ".flv" not in url:
            messagebox.showwarning("提示", "流地址格式不对，请粘贴 .m3u8 或 .flv 链接")
            return

        from platforms.wechat import WechatPlatform
        nickname = self.entries["nickname"].get().strip() or "视频号主播"
        WechatPlatform.add_stream_url(url, nickname)
        self._wechat_url_var.set("")
        messagebox.showinfo("成功", f"流地址已添加：\n{url[:60]}...")

    def _on_ok(self):
        nickname = self.entries["nickname"].get().strip()
        userid = self.entries["userid"].get().strip()
        web_rid = self.entries["web_rid"].get().strip()

        if not nickname:
            url = self.url_var.get().strip()
            match = re.search(r"(?:douyin|bilibili)\.com/(\d+)", url)
            if match:
                web_rid = web_rid or match.group(1)
            nickname = f"主播{web_rid}" if web_rid else ""
            if not nickname:
                messagebox.showwarning("提示", "请输入昵称或提供直播间URL")
                return

        self.result = Streamer(
            platform=self.platform_var.get(),
            nickname=nickname,
            userid=userid or "",
            sec_uid=self.entries["sec_uid"].get().strip(),
            web_rid=web_rid or "",
        )
        self.top.destroy()

    def _on_cancel(self):
        self.result = None
        self.top.destroy()
