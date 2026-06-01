"""Theme configuration for the live recorder GUI."""

import tkinter as tk
from tkinter import ttk

try:
    import ttkbootstrap as ttkb
    from ttkbootstrap.constants import *
    HAS_BOOTSTRAP = True
except ImportError:
    HAS_BOOTSTRAP = False

# Modern color palette
COLORS = {
    "primary": "#3b82f6",      # Blue
    "primary_hover": "#2563eb",
    "success": "#22c55e",      # Green
    "warning": "#f59e0b",      # Amber
    "danger": "#ef4444",       # Red
    "bg_dark": "#1e1e2e",      # Dark background
    "bg_card": "#2a2a3e",      # Card background
    "bg_surface": "#313145",   # Surface
    "text_primary": "#e2e8f0",
    "text_secondary": "#94a3b8",
    "border": "#3d3d5c",
    "accent": "#8b5cf6",       # Purple accent
}

# Default ttkbootstrap theme name
DEFAULT_THEME = "darkly"


def setup_theme(root):
    """Apply custom styles to the application."""
    if not HAS_BOOTSTRAP:
        return

    style = ttkb.Style()
    style.theme_use(DEFAULT_THEME)

    # Configure Treeview
    style.configure(
        "Treeview",
        background=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        fieldbackground=COLORS["bg_card"],
        borderwidth=0,
        rowheight=36,
        font=("Segoe UI", 10),
    )
    style.configure(
        "Treeview.Heading",
        background=COLORS["bg_surface"],
        foreground=COLORS["text_primary"],
        borderwidth=0,
        font=("Segoe UI", 10, "bold"),
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", COLORS["primary"])],
        foreground=[("selected", "#ffffff")],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", COLORS["bg_dark"])],
    )

    # Configure Notebook (tabs)
    style.configure(
        "TNotebook",
        background=COLORS["bg_dark"],
        borderwidth=0,
    )
    style.configure(
        "TNotebook.Tab",
        background=COLORS["bg_surface"],
        foreground=COLORS["text_secondary"],
        padding=[16, 8],
        font=("Segoe UI", 10),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLORS["primary"])],
        foreground=[("selected", "#ffffff")],
    )

    # Configure Buttons
    style.configure(
        "TButton",
        padding=[12, 6],
        font=("Segoe UI", 10),
        borderwidth=0,
        relief="flat",
    )
    style.configure(
        "Accent.TButton",
        background=COLORS["primary"],
        foreground="#ffffff",
    )
    style.map(
        "Accent.TButton",
        background=[("active", COLORS["primary_hover"])],
    )
    style.configure(
        "Success.TButton",
        background=COLORS["success"],
        foreground="#ffffff",
    )
    style.configure(
        "Danger.TButton",
        background=COLORS["danger"],
        foreground="#ffffff",
    )

    # Configure Labels
    style.configure(
        "TLabel",
        background=COLORS["bg_dark"],
        foreground=COLORS["text_primary"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "Card.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
    )
    style.configure(
        "CardTitle.TLabel",
        background=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        font=("Segoe UI", 11, "bold"),
    )
    style.configure(
        "Status.TLabel",
        background=COLORS["bg_dark"],
        foreground=COLORS["text_secondary"],
        font=("Segoe UI", 9),
    )

    # Configure Frames
    style.configure(
        "TFrame",
        background=COLORS["bg_dark"],
    )
    style.configure(
        "Card.TFrame",
        background=COLORS["bg_card"],
    )

    # Configure Scrollbar
    style.configure(
        "Vertical.TScrollbar",
        background=COLORS["bg_surface"],
        troughcolor=COLORS["bg_dark"],
        borderwidth=0,
        arrowcolor=COLORS["text_secondary"],
    )

    # Configure LabelFrame
    style.configure(
        "TLabelframe",
        background=COLORS["bg_dark"],
        foreground=COLORS["text_primary"],
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "TLabelframe.Label",
        background=COLORS["bg_dark"],
        foreground=COLORS["text_secondary"],
        font=("Segoe UI", 10),
    )

    # Configure Radiobutton
    style.configure(
        "TRadiobutton",
        background=COLORS["bg_dark"],
        foreground=COLORS["text_primary"],
        font=("Segoe UI", 10),
    )

    # Configure Checkbutton
    style.configure(
        "TCheckbutton",
        background=COLORS["bg_dark"],
        foreground=COLORS["text_primary"],
        font=("Segoe UI", 10),
    )

    # Configure Combobox
    style.configure(
        "TCombobox",
        fieldbackground=COLORS["bg_card"],
        background=COLORS["bg_surface"],
        foreground=COLORS["text_primary"],
        borderwidth=0,
        padding=6,
    )

    # Configure Spinbox
    style.configure(
        "TSpinbox",
        fieldbackground=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        borderwidth=0,
        padding=4,
    )

    # Configure Entry
    style.configure(
        "TEntry",
        fieldbackground=COLORS["bg_card"],
        foreground=COLORS["text_primary"],
        borderwidth=0,
        padding=6,
    )
