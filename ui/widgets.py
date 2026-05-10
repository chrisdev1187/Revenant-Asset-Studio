import tkinter as tk
from tkinter import ttk
from core.constants import *
#  REUSABLE WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

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


class StatusBar(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG_DARK, pady=2)
        self._var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self._var, bg=BG_DARK, fg=FG_DIM,
                 font=("Consolas", 9), anchor="w").pack(side="left", padx=8)

    def set(self, msg: str):
        self._var.set(msg)
        self.update_idletasks()


# ═══════════════════════════════════════════════════════════════════════════════
#  WORLD MAP TAB
# ═══════════════════════════════════════════════════════════════════════════════

# Zone → name mapping based on diagnostic scan of actual tile data.
# Zones confirmed present: 0,2-5,30-32,36-37,39,41,44-46,48-49,51-58,73,83,100-102,205
# Zones 6-29 (except present ones) and gaps are simply absent from game data.
# Town/OrcCamp interiors have NO automap tiles (too small; developers didn't generate them).
ZONE_NAMES = {
    # ── Ahkuilon outdoor world ────────────────────────────────────────────────
    0:   "Main World (Ahkuilon)",
    # ── Interior zones (confirmed tile data) ─────────────────────────────────
    2:   "Zone 2",
    3:   "Zone 3",
    4:   "Zone 4",
    5:   "Zone 5",
    # ── Dungeon / Keep zones (30-58 range) ───────────────────────────────────
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
    # ── Large zones ───────────────────────────────────────────────────────────
    73:  "Zone 73",
    83:  "Zone 83",
    100: "Zone 100",
    101: "Zone 101",
    102: "Zone 102",
    205: "Zone 205",
}




# ═══════════════════════════════════════════════════════════════════════════════
#  WORLD MAP TAB
# ═══════════════════════════════════════════════════════════════════════════════
