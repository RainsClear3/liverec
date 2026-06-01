"""Settings dialog — modern dark theme version."""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from gui.theme import setup_theme, COLORS, HAS_BOOTSTRAP
from core.models import AppConfig


class SettingsDialog:
    """Application settings dialog."""

    def __init__(self, parent, config: AppConfig):
        self.config = config
        self.result: Optional[AppConfig] = None

        self.top = tk.Toplevel(parent)
        self.top.title("设置")
        self.top.geometry("520x520")
        self.top.resizable(False, False)
        self.top.configure(bg=COLORS["bg_dark"])
        self.top.transient(parent)
        self.top.grab_set()

        setup_theme(self.top)
        self._setup_ui()

    def _setup_ui(self):
        bg = COLORS["bg_dark"]

        # Title
        title_label = tk.Label(self.top, text="应用设置", bg=bg,
                              fg=COLORS["text_primary"], font=("Segoe UI", 14, "bold"))
        title_label.pack(padx=15, pady=(15, 8), anchor=tk.W)

        notebook = ttk.Notebook(self.top)
        notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        # Tab 1: Recording
        rec_frame = tk.Frame(notebook, bg=bg)
        notebook.add(rec_frame, text="  录制  ")
        self._build_recording_tab(rec_frame)

        # Tab 2: Notifications
        notify_frame = tk.Frame(notebook, bg=bg)
        notebook.add(notify_frame, text="  通知  ")
        self._build_notify_tab(notify_frame)

        # Buttons
        btn_frame = tk.Frame(self.top, bg=bg)
        btn_frame.pack(fill=tk.X, padx=15, pady=(0, 15))

        cancel_btn = tk.Button(
            btn_frame, text="取消", command=self._on_cancel,
            bg=COLORS["bg_surface"], fg=COLORS["text_primary"],
            font=("Segoe UI", 10), relief="flat", bd=0, cursor="hand2",
            padx=16, pady=6,
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(6, 0))

        ok_btn = tk.Button(
            btn_frame, text="确定", command=self._on_ok,
            bg=COLORS["primary"], fg="#ffffff",
            font=("Segoe UI", 10, "bold"), relief="flat", bd=0, cursor="hand2",
            padx=16, pady=6,
        )
        ok_btn.pack(side=tk.RIGHT, padx=(6, 0))

    def _build_recording_tab(self, parent):
        bg = COLORS["bg_dark"]
        label_fg = COLORS["text_primary"]
        sub_fg = COLORS["text_secondary"]

        # Quality
        row = 0
        tk.Label(parent, text="清晰度:", bg=bg, fg=label_fg, font=("Segoe UI", 10),
                anchor=tk.W).grid(row=row, column=0, sticky=tk.W, padx=12, pady=7)
        self.quality_var = tk.StringVar(value=self.config.definition)
        ttk.Combobox(
            parent,
            textvariable=self.quality_var,
            values=["流畅", "标清", "高清", "超清"],
            state="readonly",
            width=15,
        ).grid(row=row, column=1, sticky=tk.W, padx=12, pady=7)

        # Output format
        row += 1
        tk.Label(parent, text="输出格式:", bg=bg, fg=label_fg, font=("Segoe UI", 10),
                anchor=tk.W).grid(row=row, column=0, sticky=tk.W, padx=12, pady=7)
        self.format_var = tk.StringVar(value=self.config.out_format)
        ttk.Combobox(
            parent,
            textvariable=self.format_var,
            values=["ts", "mp4", "flv"],
            state="readonly",
            width=15,
        ).grid(row=row, column=1, sticky=tk.W, padx=12, pady=7)

        # Check interval
        row += 1
        tk.Label(parent, text="检查间隔(秒):", bg=bg, fg=label_fg, font=("Segoe UI", 10),
                anchor=tk.W).grid(row=row, column=0, sticky=tk.W, padx=12, pady=7)
        self.interval_var = tk.IntVar(value=self.config.interval_time)
        ttk.Spinbox(
            parent, from_=5, to=300, textvariable=self.interval_var, width=10
        ).grid(row=row, column=1, sticky=tk.W, padx=12, pady=7)

        # Max file size
        row += 1
        tk.Label(parent, text="最大文件大小(MB):", bg=bg, fg=label_fg, font=("Segoe UI", 10),
                anchor=tk.W).grid(row=row, column=0, sticky=tk.W, padx=12, pady=7)
        self.filesize_var = tk.IntVar(value=self.config.file_size)
        ttk.Spinbox(
            parent, from_=0, to=100000, textvariable=self.filesize_var, width=10
        ).grid(row=row, column=1, sticky=tk.W, padx=12, pady=7)
        tk.Label(parent, text="(0=不限制)", bg=bg, fg=sub_fg, font=("Segoe UI", 9),
                anchor=tk.W).grid(row=row, column=2, sticky=tk.W, padx=4, pady=7)

        # Max file time
        row += 1
        tk.Label(parent, text="最大时长(秒):", bg=bg, fg=label_fg, font=("Segoe UI", 10),
                anchor=tk.W).grid(row=row, column=0, sticky=tk.W, padx=12, pady=7)
        self.filetime_var = tk.IntVar(value=self.config.file_time)
        ttk.Spinbox(
            parent, from_=0, to=86400, textvariable=self.filetime_var, width=10
        ).grid(row=row, column=1, sticky=tk.W, padx=12, pady=7)
        tk.Label(parent, text="(0=不限制)", bg=bg, fg=sub_fg, font=("Segoe UI", 9),
                anchor=tk.W).grid(row=row, column=2, sticky=tk.W, padx=4, pady=7)

        # Save path
        row += 1
        tk.Label(parent, text="保存路径:", bg=bg, fg=label_fg, font=("Segoe UI", 10),
                anchor=tk.W).grid(row=row, column=0, sticky=tk.W, padx=12, pady=7)
        path_frame = tk.Frame(parent, bg=bg)
        path_frame.grid(row=row, column=1, columnspan=2, sticky=tk.EW, padx=12, pady=7)
        self.path_var = tk.StringVar(value=self.config.save_path)
        ttk.Entry(path_frame, textvariable=self.path_var, width=30).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        browse_btn = tk.Button(
            path_frame, text="浏览", command=self._browse_path,
            bg=COLORS["bg_surface"], fg=COLORS["text_primary"],
            font=("Segoe UI", 9), relief="flat", bd=0, cursor="hand2",
            padx=10, pady=3,
        )
        browse_btn.pack(side=tk.LEFT, padx=(8, 0))

        parent.columnconfigure(1, weight=1)

    def _build_notify_tab(self, parent):
        bg = COLORS["bg_dark"]
        label_fg = COLORS["text_primary"]
        sub_fg = COLORS["text_secondary"]

        # Enable push
        self.push_var = tk.BooleanVar(value=self.config.push_msg)
        ttk.Checkbutton(parent, text="启用 Webhook 推送", variable=self.push_var).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, padx=12, pady=8
        )

        # Event checkboxes
        push = self.config.push_config
        self.live_var = tk.BooleanVar(value=push.live_status)
        self.rec_start_var = tk.BooleanVar(value=push.rec_start)
        self.rec_end_var = tk.BooleanVar(value=push.rec_end)

        ttk.Checkbutton(parent, text="开播通知", variable=self.live_var).grid(
            row=1, column=0, sticky=tk.W, padx=28, pady=5
        )
        ttk.Checkbutton(parent, text="开始录制通知", variable=self.rec_start_var).grid(
            row=1, column=1, sticky=tk.W, padx=12, pady=5
        )
        ttk.Checkbutton(parent, text="录制结束通知", variable=self.rec_end_var).grid(
            row=2, column=0, sticky=tk.W, padx=28, pady=5
        )

        # Webhook URL
        tk.Label(parent, text="Webhook URL:", bg=bg, fg=label_fg, font=("Segoe UI", 10),
                anchor=tk.W).grid(row=3, column=0, sticky=tk.W, padx=12, pady=8)
        self.webhook_var = tk.StringVar(value=push.web_hook_url)
        ttk.Entry(parent, textvariable=self.webhook_var, width=40).grid(
            row=3, column=1, sticky=tk.EW, padx=12, pady=8
        )

        # Target user
        tk.Label(parent, text="通知目标:", bg=bg, fg=label_fg, font=("Segoe UI", 10),
                anchor=tk.W).grid(row=4, column=0, sticky=tk.W, padx=12, pady=8)
        self.userid_var = tk.StringVar(value=push.userid)
        ttk.Entry(parent, textvariable=self.userid_var, width=20).grid(
            row=4, column=1, sticky=tk.W, padx=12, pady=8
        )
        tk.Label(parent, text="(@all=所有人)", bg=bg, fg=sub_fg, font=("Segoe UI", 9),
                anchor=tk.W).grid(row=4, column=2, sticky=tk.W, padx=4, pady=8)

        parent.columnconfigure(1, weight=1)

    def _browse_path(self):
        path = filedialog.askdirectory(title="选择保存路径")
        if path:
            self.path_var.set(path)

    def _on_ok(self):
        self.result = AppConfig(
            interval_time=self.interval_var.get(),
            definition=self.quality_var.get(),
            out_format=self.format_var.get(),
            file_size=self.filesize_var.get(),
            file_time=self.filetime_var.get(),
            save_path=self.path_var.get(),
            push_msg=self.push_var.get(),
            push_config=__import__("core.models", fromlist=["PushConfig"]).PushConfig(
                live_status=self.live_var.get(),
                rec_start=self.rec_start_var.get(),
                rec_end=self.rec_end_var.get(),
                web_hook_url=self.webhook_var.get(),
                userid=self.userid_var.get(),
            ),
        )
        self.top.destroy()

    def _on_cancel(self):
        self.result = None
        self.top.destroy()
