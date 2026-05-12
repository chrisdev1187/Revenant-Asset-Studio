from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from ui.theme import THEME, FONTS
from core.config import Config
import os

class WelcomeWizard(tk.Toplevel):
    def __init__(self, parent, config: Config, on_complete):
        super().__init__(parent)
        self.config = config
        self.on_complete = on_complete

        self.title("RevEngine — Setup Wizard")
        self.geometry("600x500")
        self.configure(bg=THEME["bg_dark"])
        self.resizable(False, False)
        self.grab_set()

        self._step = 1
        self._build_ui()

    def _build_ui(self):
        self._main = tk.Frame(self, bg=THEME["bg_dark"], padx=40, pady=40)
        self._main.pack(fill="both", expand=True)

        self._content = tk.Frame(self._main, bg=THEME["bg_dark"])
        self._content.pack(fill="both", expand=True)

        self._nav = tk.Frame(self._main, bg=THEME["bg_dark"])
        self._nav.pack(fill="x", side="bottom")

        self._btn_next = tk.Button(self._nav, text="Next", bg=THEME["accent"],
                                   fg="white", relief="flat", font=FONTS["body_bold"],
                                   padx=20, command=self._next_step)
        self._btn_next.pack(side="right")

        self._show_step_1()

    def _next_step(self):
        self._step += 1
        for widget in self._content.winfo_children():
            widget.destroy()

        if self._step == 2:
            self._show_step_2()
        elif self._step == 3:
            self.config.save()
            self.destroy()
            self.on_complete()

    def _show_step_1(self):
        tk.Label(self._content, text="Welcome to RevEngine", bg=THEME["bg_dark"],
                 fg=THEME["accent_light"], font=FONTS["title"]).pack(anchor="w")

        tk.Label(self._content, text="Modern Asset Explorer for Revenant (1999)",
                 bg=THEME["bg_dark"], fg=THEME["fg_dim"], font=FONTS["header"]).pack(anchor="w", pady=(0, 20))

        msg = ("This tool allows you to explore, export, and modernize assets from "
               "Cinematix Studios' Revenant. Before we begin, we need to locate "
               "your game installation.")
        tk.Label(self._content, text=msg, bg=THEME["bg_dark"], fg=THEME["fg_text"],
                 font=FONTS["body"], wraplength=500, justify="left").pack(anchor="w", pady=10)

        tk.Label(self._content, text="Select Revenant Install Directory:",
                 bg=THEME["bg_dark"], fg=THEME["fg_dim"], font=FONTS["small_bold"]).pack(anchor="w", pady=(20, 5))

        self._game_dir_var = tk.StringVar(value=str(self.config.game_dir))
        entry_f = tk.Frame(self._content, bg=THEME["bg_dark"])
        entry_f.pack(fill="x")

        tk.Entry(entry_f, textvariable=self._game_dir_var, bg=THEME["bg_panel"],
                 fg=THEME["fg_text"], font=FONTS["small"], relief="flat").pack(side="left", fill="x", expand=True, padx=(0, 10), ipady=4)

        tk.Button(entry_f, text="Browse...", bg=THEME["bg_mid"], fg=THEME["fg_text"],
                  relief="flat", font=FONTS["small"], command=self._browse_game).pack(side="right")

    def _browse_game(self):
        d = filedialog.askdirectory(initialdir=self._game_dir_var.get())
        if d:
            self._game_dir_var.set(d)
            self.config.game_dir = Path(d)

    def _show_step_2(self):
        tk.Label(self._content, text="Data Extraction", bg=THEME["bg_dark"],
                 fg=THEME["accent_light"], font=FONTS["title"]).pack(anchor="w")

        msg = ("RevEngine needs to extract the game's .RVR and .RVI archives to "
               "access models, textures, and scripts. This will take about 1-2 minutes.")
        tk.Label(self._content, text=msg, bg=THEME["bg_dark"], fg=THEME["fg_text"],
                 font=FONTS["body"], wraplength=500, justify="left").pack(anchor="w", pady=10)

        self._extract_status = tk.Label(self._content, text="Ready to extract.",
                                        bg=THEME["bg_dark"], fg=THEME["success"], font=FONTS["small_bold"])
        self._extract_status.pack(anchor="w", pady=20)

        self._prog = ttk.Progressbar(self._content, maximum=100, length=500, mode='determinate')
        self._prog.pack(pady=10)

        self._btn_next.config(text="Extract & Finish", command=self._start_extraction)

    def _start_extraction(self):
        self._btn_next.config(state="disabled")
        import threading
        threading.Thread(target=self._extraction_worker, daemon=True).start()

    def _extraction_worker(self):
        from archive_extractor import extract_archive, REVENANT_ARCHIVES

        archives = []
        for ext in REVENANT_ARCHIVES:
            for f in self.config.game_dir.glob(f"*{ext}"):
                archives.append(f)

        if not archives:
            self._extract_status.config(text="No archives found! Please check path.", fg=THEME["danger"])
            self.after(0, lambda: self._btn_next.config(state="normal", text="Retry"))
            return

        total = len(archives)
        for i, arc in enumerate(archives):
            self._extract_status.config(text=f"Extracting {arc.name}...")
            self._prog["value"] = (i / total) * 100
            self.update_idletasks()

            out_dir = self.config.extract_dir / arc.stem
            extract_archive(arc, out_dir)

        self._prog["value"] = 100
        self._extract_status.config(text="Extraction Complete!")
        self.after(500, self._next_step)
