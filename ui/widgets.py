from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from core.constants import *

#  REUSABLE WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

class LoadingOverlay(tk.Frame):
    def __init__(self, parent, text="Processing Data..."):
        from ui.theme import THEME, FONTS
        super().__init__(parent, bg=THEME["bg_deep"])
        self.place(x=0, y=0, relwidth=1, relheight=1)

        inner = tk.Frame(self, bg=THEME["bg_deep"])
        inner.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(inner, text=text, bg=THEME["bg_deep"], fg=THEME["fg_text"],
                 font=FONTS["header"]).pack(pady=10)

        self.prog = ttk.Progressbar(inner, mode='indeterminate', length=300)
        self.prog.pack(pady=10)
        self.prog.start(10)

class ScrollFrame(tk.Frame):
    """A frame with a vertical scrollbar."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=kwargs.pop('bg', BG_MID), **kwargs)
        self.canvas = tk.Canvas(self, bg=BG_MID, highlightthickness=0)
        self.vsb    = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner  = tk.Frame(self.canvas, bg=BG_MID)
        self._win   = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>",  self._on_mousewheel)
        self.inner.bind("<MouseWheel>",   self._on_mousewheel)

    def _on_inner_configure(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self.canvas.itemconfig(self._win, width=e.width)

    def _on_mousewheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        from ui.theme import THEME, FONTS
        x, y, _cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + cy + self.widget.winfo_rooty() + 25
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background=THEME["bg_card"], foreground=THEME["fg_text"],
                         relief=tk.FLAT, borderwidth=1,
                         font=FONTS["small"], padx=5, pady=2)
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

def add_tooltip(widget, text):
    ToolTip(widget, text)

class StatusBar(tk.Frame):
    def __init__(self, parent):
        from ui.theme import THEME, FONTS
        super().__init__(parent, bg=THEME["bg_dark"], pady=4,
                         highlightbackground=THEME["border"], highlightthickness=1)

        self._var = tk.StringVar(value="Ready")
        self._lbl = tk.Label(self, textvariable=self._var, bg=THEME["bg_dark"],
                             fg=THEME["fg_dim"], font=FONTS["mono"], anchor="w")
        self._lbl.pack(side="left", padx=12)

        # Progress bar (hidden by default)
        self._prog_var = tk.DoubleVar(value=0)
        self._prog = ttk.Progressbar(self, variable=self._prog_var,
                                     maximum=100, length=200, mode='determinate')

    def set(self, msg: str, type: str = "info"):
        from ui.theme import THEME
        colors = {
            "info":    THEME["fg_dim"],
            "success": THEME["success"],
            "warning": THEME["warning"],
            "error":   THEME["danger"]
        }
        self._lbl.config(fg=colors.get(type, THEME["fg_dim"]))
        self._var.set(msg)
        self.update_idletasks()

    def progress(self, value: float, visible: bool = True):
        """Update progress bar (0-100)."""
        if visible:
            if not self._prog.winfo_viewable():
                self._prog.pack(side="right", padx=12, pady=2)
            self._prog_var.set(value)
        else:
            self._prog.pack_forget()
        self.update_idletasks()


# ═══════════════════════════════════════════════════════════════════════════════
#  ZONE NAMES
# ═══════════════════════════════════════════════════════════════════════════════

ZONE_NAMES = {
    0:   "Main World (Ahkuilon)",
    2:   "Zone 2",
    3:   "Zone 3",
    4:   "Zone 4",
    5:   "Zone 5",
    30:  "Zone 30",
    31:  "Zone 31",
    32:  "Zone 32",
    36:  "Zone 36",
    37:  "Zone 37",
    39:  "Zone 39",
    41:  "Zone 41",
    44:  "Zone 44",
    45:  "Zone 45",
    46:  "Zone 46",
    48:  "Zone 48",
    49:  "Zone 49",
    51:  "Zone 51",
    52:  "Zone 52",
    53:  "Zone 53",
    54:  "Zone 54",
    55:  "Zone 55",
    56:  "Zone 56",
    57:  "Zone 57",
    58:  "Zone 58",
    73:  "Zone 73",
    83:  "Zone 83",
    100: "Zone 100",
    101: "Zone 101",
    102: "Zone 102",
    205: "Zone 205",
}
