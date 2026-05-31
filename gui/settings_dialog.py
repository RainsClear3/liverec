"""Settings dialog — recording, notifications, save path."""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from core.models import AppConfig


class SettingsDialog:
    """Application settings dialog."""

    def __init__(self, parent, config: AppConfig):
        self.config = config
        self.result: Optional[AppConfig] = None

        self.top = tk.Toplevel(parent)
        self.top.title("设置")
        self.top.geometry("500x480")
        self.top.resizable(False, False)
        self.top.transient(parent)
        self.top.grab_set()

        self._setup_ui()

    def _setup_ui(self):
        notebook = ttk.Notebook(self.top)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tab 1: Recording
        rec_frame = ttk.Frame(notebook)
        notebook.add(rec_frame, text="录制")
        self._build_recording_tab(rec_frame)

        # Tab 2: Notifications
        notify_frame = ttk.Frame(notebook)
        notebook.add(notify_frame, text="通知")
        self._build_notify_tab(notify_frame)

        # Buttons
        btn_frame = ttk.Frame(self.top)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="确定", command=self._on_ok).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(btn_frame, text="取消", command=self._on_cancel).pack(
            side=tk.RIGHT, padx=5
        )

    def _build_recording_tab(self, parent):
        # Quality
        row = 0
        ttk.Label(parent, text="清晰度:").grid(
            row=row, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.quality_var = tk.StringVar(value=self.config.definition)
        ttk.Combobox(
            parent,
            textvariable=self.quality_var,
            values=["流畅", "标清", "高清", "超清"],
            state="readonly",
            width=15,
        ).grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)

        # Output format
        row += 1
        ttk.Label(parent, text="输出格式:").grid(
            row=row, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.format_var = tk.StringVar(value=self.config.out_format)
        ttk.Combobox(
            parent,
            textvariable=self.format_var,
            values=["ts", "mp4", "flv"],
            state="readonly",
            width=15,
        ).grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)

        # Check interval
        row += 1
        ttk.Label(parent, text="检查间隔(秒):").grid(
            row=row, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.interval_var = tk.IntVar(value=self.config.interval_time)
        ttk.Spinbox(
            parent, from_=5, to=300, textvariable=self.interval_var, width=10
        ).grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)

        # Max file size
        row += 1
        ttk.Label(parent, text="最大文件大小(MB):").grid(
            row=row, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.filesize_var = tk.IntVar(value=self.config.file_size)
        ttk.Spinbox(
            parent, from_=0, to=100000, textvariable=self.filesize_var, width=10
        ).grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(parent, text="(0=不限制)").grid(
            row=row, column=2, sticky=tk.W, padx=5, pady=5
        )

        # Max file time
        row += 1
        ttk.Label(parent, text="最大时长(秒):").grid(
            row=row, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.filetime_var = tk.IntVar(value=self.config.file_time)
        ttk.Spinbox(
            parent, from_=0, to=86400, textvariable=self.filetime_var, width=10
        ).grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(parent, text="(0=不限制)").grid(
            row=row, column=2, sticky=tk.W, padx=5, pady=5
        )

        # Save path
        row += 1
        ttk.Label(parent, text="保存路径:").grid(
            row=row, column=0, sticky=tk.W, padx=5, pady=5
        )
        path_frame = ttk.Frame(parent)
        path_frame.grid(row=row, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.path_var = tk.StringVar(value=self.config.save_path)
        ttk.Entry(path_frame, textvariable=self.path_var, width=30).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(path_frame, text="浏览", command=self._browse_path).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        parent.columnconfigure(1, weight=1)

    def _build_notify_tab(self, parent):
        # Enable push
        self.push_var = tk.BooleanVar(value=self.config.push_msg)
        ttk.Checkbutton(parent, text="启用 Webhook 推送", variable=self.push_var).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5
        )

        # Event checkboxes
        push = self.config.push_config
        self.live_var = tk.BooleanVar(value=push.live_status)
        self.rec_start_var = tk.BooleanVar(value=push.rec_start)
        self.rec_end_var = tk.BooleanVar(value=push.rec_end)

        ttk.Checkbutton(parent, text="开播通知", variable=self.live_var).grid(
            row=1, column=0, sticky=tk.W, padx=20, pady=3
        )
        ttk.Checkbutton(parent, text="开始录制通知", variable=self.rec_start_var).grid(
            row=1, column=1, sticky=tk.W, padx=20, pady=3
        )
        ttk.Checkbutton(parent, text="录制结束通知", variable=self.rec_end_var).grid(
            row=2, column=0, sticky=tk.W, padx=20, pady=3
        )

        # Webhook URL
        ttk.Label(parent, text="Webhook URL:").grid(
            row=3, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.webhook_var = tk.StringVar(value=push.web_hook_url)
        ttk.Entry(parent, textvariable=self.webhook_var, width=40).grid(
            row=3, column=1, sticky=tk.EW, padx=5, pady=5
        )

        # Target user
        ttk.Label(parent, text="通知目标:").grid(
            row=4, column=0, sticky=tk.W, padx=5, pady=5
        )
        self.userid_var = tk.StringVar(value=push.userid)
        ttk.Entry(parent, textvariable=self.userid_var, width=20).grid(
            row=4, column=1, sticky=tk.W, padx=5, pady=5
        )
        ttk.Label(parent, text="(@all=所有人)").grid(
            row=4, column=2, sticky=tk.W, padx=5, pady=5
        )

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
