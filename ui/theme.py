from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from core.constants import *

#  PROFESSIONAL THEME CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Refined Professional Palette
THEME = {
    "bg_deep":      "#0a0a12",
    "bg_dark":      "#12121f",
    "bg_mid":       "#1a1a2e",
    "bg_panel":     "#1e1e35",
    "bg_card":      "#252545",
    "fg_text":      "#f0f2fc",
    "fg_dim":       "#a0a8c8",
    "fg_muted":     "#686d85",
    "accent":       "#8b5cf6", # Indigo/Violet
    "accent_light": "#a78bfa",
    "success":      "#10b981",
    "warning":      "#f59e0b",
    "danger":       "#ef4444",
    "info":         "#3b82f6",
    "border":       "#2d2d4a",
    "gold":         "#fbbf24",
}

FONTS = {
    "title":        ("Segoe UI", 18, "bold"),
    "header":       ("Segoe UI", 12, "bold"),
    "body":         ("Segoe UI", 10),
    "body_bold":    ("Segoe UI", 10, "bold"),
    "small":        ("Segoe UI", 9),
    "small_bold":   ("Segoe UI", 9, "bold"),
    "mono":         ("Consolas", 9),
    "mono_bold":    ("Consolas", 9, "bold"),
}

def apply_global_styles(root: tk.Tk):
    """Configure ttk.Style with the centralized theme."""
    style = ttk.Style(root)
    style.theme_use("clam")

    # Notebook
    style.configure("TNotebook",
                    background=THEME["bg_dark"],
                    borderwidth=0)
    style.configure("TNotebook.Tab",
                    background=THEME["bg_mid"],
                    foreground=THEME["fg_dim"],
                    padding=[16, 8],
                    font=FONTS["body_bold"])
    style.map("TNotebook.Tab",
              background=[("selected", THEME["bg_panel"])],
              foreground=[("selected", THEME["fg_text"])])

    # Treeview
    style.configure("Treeview",
                    background=THEME["bg_panel"],
                    foreground=THEME["fg_text"],
                    fieldbackground=THEME["bg_panel"],
                    rowheight=28,
                    font=FONTS["small"],
                    borderwidth=0)
    style.configure("Treeview.Heading",
                    background=THEME["bg_mid"],
                    foreground=THEME["accent_light"],
                    font=FONTS["small_bold"],
                    relief="flat",
                    padding=5)
    style.map("Treeview",
              background=[("selected", THEME["bg_card"])],
              foreground=[("selected", THEME["fg_text"])])

    # Scrollbar
    style.configure("TScrollbar",
                    background=THEME["bg_mid"],
                    troughcolor=THEME["bg_deep"],
                    arrowcolor=THEME["fg_dim"],
                    borderwidth=0,
                    relief="flat")

    # Combobox
    style.configure("TCombobox",
                    background=THEME["bg_panel"],
                    foreground=THEME["fg_text"],
                    fieldbackground=THEME["bg_panel"],
                    arrowcolor=THEME["accent"])

    # Buttons (Custom variant can be added if needed, though we often use tk.Button for more control)
    style.configure("TButton",
                    font=FONTS["small_bold"],
                    padding=6)

    # Frame
    style.configure("TFrame", background=THEME["bg_mid"])

    # Separator
    style.configure("TSeparator", background=THEME["border"])

def enable_high_dpi(root: tk.Tk):
    """Enable High DPI scaling for Windows/macOS."""
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass # Non-Windows or older Windows

    # Base scaling adjustment if needed
    root.tk.call('tk', 'scaling', 1.5)
