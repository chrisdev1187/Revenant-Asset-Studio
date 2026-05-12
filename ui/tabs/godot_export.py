import tkinter as tk
import re
from tkinter import ttk, filedialog
import threading
from pathlib import Path
from ui.theme import THEME, FONTS
from core.constants import *
from ui.widgets import StatusBar
from core.godot_exporter import GodotExporter

class GodotExportTab(tk.Frame):
    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=THEME["bg_mid"])
        self._status = status
        self._build_ui()

    def _build_ui(self):
        bar = tk.Frame(self, bg=THEME["bg_dark"], pady=5); bar.pack(fill='x')
        tk.Label(bar, text='Godot Engine systematic Port', bg=THEME["bg_dark"], fg=THEME["accent"], font=('Segoe UI', 11, 'bold')).pack(side='left', padx=10)

        pane = tk.PanedWindow(self, orient='horizontal', bg=THEME["bg_dark"], sashwidth=4); pane.pack(fill='both', expand=True)
        left = tk.Frame(pane, bg=THEME["bg_panel"], width=300); pane.add(left, minsize=250)
        tk.Label(left, text='Project Root:', bg=THEME["bg_panel"], fg=THEME["fg_dim"], font=('Segoe UI', 8)).pack(anchor='w', padx=10, pady=(10,0))
        self._proj_var = tk.StringVar()
        row = tk.Frame(left, bg=THEME["bg_panel"]); row.pack(fill='x', padx=10, pady=2)
        tk.Entry(row, textvariable=self._proj_var, bg=BG_CARD, fg=THEME["fg_text"], relief='flat').pack(side='left', fill='x', expand=True)
        tk.Button(row, text='...', command=self._browse).pack(side='right')

        tk.Button(left, text='FULL REBUILD', bg=ACCENT, command=self._run_full, pady=10).pack(fill='x', padx=10, pady=20)

        right = tk.Frame(pane, bg=THEME["bg_dark"]); pane.add(right, minsize=400)
        self._log = tk.Text(right, bg=THEME["bg_dark"], fg=THEME["fg_text"], font=('Consolas', 8), state='disabled'); self._log.pack(fill='both', expand=True, padx=10, pady=10)

    def _browse(self):
        d = filedialog.askdirectory();
        if d: self._proj_var.set(d)

    def _log_line(self, text):
        self._log.config(state='normal'); self._log.insert('end', f'{text}\n'); self._log.see('end'); self._log.config(state='disabled')

    def _run_full(self):
        proj = self._proj_var.get()
        if not proj: return
        exporter = GodotExporter(self.cfg, Path(proj))
        threading.Thread(target=lambda: exporter.systematic_rebuild(self._log_line), daemon=True).start()
