from PIL import Image, ImageTk
import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ui.theme import THEME, FONTS
from core.constants import *
from ui.widgets import *
from core.parsers import *
class CharCard(tk.Frame):
    """A single character card widget."""
    def __init__(self, parent, config, char: Dict, photo=None, on_click=None, **kwargs):
        self.cfg = config
        super().__init__(parent, bg=BG_CARD, bd=0, highlightthickness=1,
                         highlightbackground=BORDER, **kwargs)
        self._on_click = on_click
        self._char     = char

        # Portrait
        img_frame = tk.Frame(self, bg=BG_CARD, padx=4, pady=4)
        img_frame.pack(fill="x")
        if photo:
            lbl = tk.Label(img_frame, image=photo, bg=BG_CARD)
            lbl.pack()
        else:
            tk.Label(img_frame, text="?", bg=THEME["bg_mid"], fg=THEME["fg_dim"],
                     width=8, height=4, font=("Segoe UI", 18)).pack()

        # Name
        tk.Label(self, text=char["name"], bg=BG_CARD, fg=THEME["fg_text"],
                 font=("Segoe UI", 9, "bold"), wraplength=110,
                 justify="center").pack(pady=(0, 2))

        # Quick stats
        cls  = char.get("class", "") or "—"
        atks = char.get("attack_count", 0)
        grp  = (char.get("groups", "") or "—").split(",")[0]
        tk.Label(self, text=f"Class: {cls}", bg=BG_CARD, fg=THEME["accent_light"],
                 font=("Segoe UI", 8)).pack()
        tk.Label(self, text=f"Group: {grp}", bg=BG_CARD, fg=THEME["fg_dim"],
                 font=("Segoe UI", 8)).pack()
        tk.Label(self, text=f"Attacks: {atks}", bg=BG_CARD, fg=THEME["success"],
                 font=("Segoe UI", 8)).pack(pady=(0, 4))

        # Click binding
        for w in self.winfo_children() + [self]:
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>",    lambda e: self.configure(highlightbackground=ACCENT))
            w.bind("<Leave>",    lambda e: self.configure(highlightbackground=BORDER))

    def _click(self, _=None):
        if self._on_click:
            self._on_click(self._char)


class CharacterGalleryTab(tk.Frame):
    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=THEME["bg_mid"])
        self._status  = status
        self._photos  = {}
        self._chars   = []
        self._filter  = tk.StringVar()
        self._filter.trace_add("write", self._apply_filter)
        self._build_ui()
        self.after(200, self._load_all)

    def _build_ui(self):
        # ── Toolbar ──────────────────────────────────────────────────────────
        bar = tk.Frame(self, bg=THEME["bg_dark"], pady=6)
        bar.pack(fill="x")

        tk.Label(bar, text="Filter:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["body"]).pack(side="left", padx=(10, 4))
        self._search = tk.Entry(bar, textvariable=self._filter,
                                 bg=THEME["bg_panel"], fg=THEME["fg_text"],
                                 insertbackground=FG_TEXT,
                                 font=FONTS["body"], relief="flat",
                                 width=24)
        self._search.pack(side="left", padx=4)

        tk.Button(bar, text="Export All Portraits", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all).pack(side="right", padx=4)
        self._count_lbl = tk.Label(bar, text="", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                                    font=FONTS["small"])
        self._count_lbl.pack(side="right", padx=12)

        # ── Panes ─────────────────────────────────────────────────────────────
        pane = tk.PanedWindow(self, orient="horizontal", bg=THEME["bg_dark"],
                               sashrelief="flat", sashwidth=6)
        pane.pack(fill="both", expand=True)

        # Left: gallery grid
        left = tk.Frame(pane, bg=THEME["bg_mid"])
        pane.add(left, minsize=400)
        self._scroll = ScrollFrame(left, bg=THEME["bg_mid"])
        self._scroll.pack(fill="both", expand=True)
        self._grid = self._scroll.inner

        # Right: detail panel
        right = tk.Frame(pane, bg=THEME["bg_panel"], padx=12, pady=12)
        pane.add(right, minsize=260)
        tk.Label(right, text="CHARACTER DETAILS", bg=THEME["bg_panel"], fg=THEME["accent"],
                 font=FONTS["header"]).pack(anchor="w")
        ttk.Separator(right).pack(fill="x", pady=6)

        self._detail_name = tk.Label(right, text="Select a character",
                                      bg=THEME["bg_panel"], fg=THEME["fg_text"],
                                      font=("Segoe UI", 14, "bold"),
                                      wraplength=240, justify="left")
        self._detail_name.pack(anchor="w", pady=(0, 4))

        self._detail_portrait = tk.Label(right, bg=THEME["bg_panel"])
        self._detail_portrait.pack(anchor="w", pady=4)

        self._detail_text = tk.Text(right, bg=THEME["bg_panel"], fg=THEME["fg_text"],
                                     font=("Consolas", 9),
                                     relief="flat", wrap="word",
                                     state="disabled", height=32,
                                     cursor="arrow")
        sb = ttk.Scrollbar(right, orient="vertical",
                            command=self._detail_text.yview)
        self._detail_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=(8, 0))
        self._detail_text.pack(fill="both", expand=True, pady=(8, 0))

        # Text tags
        self._detail_text.tag_configure("h",    foreground=ACCENT,
                                                 font=("Segoe UI", 9, "bold"))
        self._detail_text.tag_configure("v",    foreground=FG_TEXT,
                                                 font=("Consolas", 9))
        self._detail_text.tag_configure("kv",   foreground=ACCENT2,
                                                 font=FONTS["small"])
        self._detail_text.tag_configure("dim",  foreground=FG_DIM,
                                                 font=("Segoe UI", 8))
        self._detail_text.tag_configure("link", foreground="#6ab0f5",
                                                 font=("Segoe UI", 8),
                                                 underline=True)
        self._detail_text.tag_configure("good", foreground="#80e080",
                                                 font=("Consolas", 9))
        self._detail_text.tag_configure("warn", foreground="#e0c060",
                                                 font=("Consolas", 9))
        self._detail_text.tag_configure("anim", foreground="#c080ff",
                                                 font=("Consolas", 9))
        self._detail_text.tag_configure("raw",  foreground="#607060",
                                                 font=("Consolas", 8))

    def _load_all(self):
        self._status.set("Parsing char.def...")
        if not HAS_PIL:
            self._status.set("PIL/Pillow not found — character gallery disabled")
            return
        self._chars = parse_char_def(self.cfg)
        self._status.set(f"Loading portraits for {len(self._chars)} characters...")
        self._load_portraits()
        self._render_gallery(self._chars)
        self._count_lbl.config(text=f"{len(self._chars)} characters")
        self._status.set(f"Character gallery: {len(self._chars)} characters loaded")

    def _load_portraits(self):
        """Load portrait images (PIL) for all characters."""
        if not HAS_PIL:
            return
        for ch in self._chars:
            name = ch["name"]
            portrait_path = find_portrait(self.cfg, name)
            if portrait_path:
                try:
                    img = Image.open(portrait_path).convert("RGB")
                    img = img.resize((96, 96), Image.LANCZOS)
                    self._photos[name] = ImageTk.PhotoImage(img)
                    continue
                except Exception:
                    pass
            # Placeholder
            img = make_placeholder_portrait(name, 96)
            if img:
                self._photos[name] = ImageTk.PhotoImage(img)

    def _render_gallery(self, chars: List[Dict]):
        for w in self._grid.winfo_children():
            w.destroy()

        cols = 5
        for i, ch in enumerate(chars):
            photo = self._photos.get(ch["name"])
            card  = CharCard(self._grid, self.cfg, ch, photo=photo,
                              on_click=self._show_detail)
            card.grid(row=i // cols, column=i % cols,
                      padx=6, pady=6, sticky="nw")

    def _apply_filter(self, *_):
        flt = self._filter.get().strip().lower()
        if not flt:
            filtered = self._chars
        else:
            filtered = [c for c in self._chars
                        if flt in c["name"].lower()
                        or flt in c.get("class", "").lower()
                        or flt in c.get("groups", "").lower()
                        or flt in c.get("script", "").lower()]
        self._render_gallery(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._chars)}")

    def _show_detail(self, char: Dict):
        name = char["name"]
        self._detail_name.config(text=name)

        # Portrait (larger in detail pane)
        portrait_path = find_portrait(self.cfg, name)
        if portrait_path and HAS_PIL:
            try:
                img = Image.open(portrait_path).convert("RGB").resize(
                    (128, 128), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._detail_portrait.config(image=photo, text="")
                self._detail_portrait._photo = photo
            except Exception:
                self._detail_portrait.config(image="", text="")
        else:
            photo = self._photos.get(name)
            if photo:
                self._detail_portrait.config(image=photo, text="")
                self._detail_portrait._photo = photo
            else:
                self._detail_portrait.config(image="", text="")

        # i3d / animation info
        i3d_path    = find_char_i3d(self.cfg, name)
        anim_states = parse_i3d_anim_states(i3d_path) if i3d_path else []

        txt = self._detail_text
        txt.configure(state="normal")
        txt.delete("1.0", "end")

        # Bind tag so clicking a "link" opens Explorer/Finder
        txt.tag_unbind("link", "<Button-1>")

        def row(label, value, vtag="v", txt=txt):
            txt.insert("end", f"  {label:<16}", "kv")
            txt.insert("end", f"{value or '—'}\n", vtag)

        def file_row(label, path: Optional[Path], txt=txt):
            txt.insert("end", f"  {label:<16}", "kv")
            if path and path.exists():
                display = path.name
                start   = txt.index("end-1c")
                txt.insert("end", display, "link")
                end = txt.index("end-1c")
                tag = f"link_{path}"
                txt.tag_add(tag, start, end)
                txt.tag_configure(tag, foreground="#6ab0f5", underline=True)
                txt.tag_bind(tag, "<Button-1>",
                             lambda e, p=path: self._open_path(p))
                txt.tag_bind(tag, "<Enter>",
                             lambda e: txt.config(cursor="hand2"))
                txt.tag_bind(tag, "<Leave>",
                             lambda e: txt.config(cursor="arrow"))
                txt.insert("end", "\n")
            else:
                txt.insert("end", "not found\n", "dim")

        # ── IDENTITY ─────────────────────────────────────────────────────────
        txt.insert("end", "IDENTITY\n", "h")
        row("Name",    name)
        row("Class",   char.get("class"))
        row("Groups",  char.get("groups"))
        row("Enemies", char.get("enemies"))
        if char.get("script"):
            row("Script",  char.get("script"))

        # ── FILES ────────────────────────────────────────────────────────────
        txt.insert("end", "\nFILES\n", "h")
        file_row("Portrait",   portrait_path)
        file_row("3D Model",   i3d_path)
        if self.cfg.char_def.exists():
            file_row("char.def",   self.cfg.char_def)

        # ── COMBAT ───────────────────────────────────────────────────────────
        txt.insert("end", "\nCOMBAT\n", "h")
        row("Health",     str(char.get("health", 0)) if char.get("health") else "—")
        row("Speed",      str(char.get("speed",  0)) if char.get("speed")  else "—")
        row("Block %",    f"{char.get('block_pct', 0)}%")
        row("Weapon DMG", str(char.get("weapon_dmg", 0)))
        row("Sight",      str(char.get("sight", 0)))

        # Attacks
        attacks = char.get("attacks", [])
        if attacks:
            txt.insert("end", f"\nATTACKS  ({len(attacks)})\n", "h")
            for atk in attacks:
                aname = atk.get("name", "?")
                dmg   = atk.get("damage", "")
                anim  = atk.get("anim", "")
                txt.insert("end", f"  • {aname}", "v")
                if dmg:
                    txt.insert("end", f"  dmg:{dmg}", "warn")
                if anim:
                    txt.insert("end", f"  [{anim}]", "anim")
                txt.insert("end", "\n")
        elif char.get("attack_count", 0):
            row("Attacks", str(char["attack_count"]))

        # Impacts
        impacts = char.get("impacts", [])
        if impacts:
            txt.insert("end", f"\nIMPACTS  ({len(impacts)})\n", "h")
            for imp in impacts:
                txt.insert("end", f"  • {imp.get('name','?')}\n", "v")
        elif char.get("impact_count", 0):
            row("Impacts", str(char["impact_count"]))

        # Spells
        spells = char.get("spells", [])
        if spells:
            txt.insert("end", f"\nSPELLS  ({len(spells)})\n", "h")
            for sp in spells:
                txt.insert("end", f"  • {sp}\n", "good")

        # ── 3D MODEL / ANIMATIONS ────────────────────────────────────────────
        txt.insert("end", "\n3D MODEL\n", "h")
        if i3d_path:
            row("File",   i3d_path.name)
            row("Size",   f"{i3d_path.stat().st_size // 1024} KB")
            if anim_states:
                txt.insert("end", f"\nANIMATION STATES  ({len(anim_states)})\n", "h")
                for st in anim_states:
                    sname  = st["name"]
                    frames = st["frames"]
                    w, h   = st.get("width", 0), st.get("height", 0)
                    txt.insert("end", f"  {sname:<14}", "anim")
                    txt.insert("end", f"  {frames} frame{'s' if frames!=1 else ''}", "v")
                    if w and h:
                        txt.insert("end", f"  ({w}×{h})", "dim")
                    txt.insert("end", "\n")

                # Show which states char.def references
                anim_refs = char.get("anim_refs", [])
                if anim_refs:
                    known   = {st["name"] for st in anim_states}
                    txt.insert("end", f"\nANIM REFS IN char.def\n", "h")
                    for ref in anim_refs:
                        found = ref in known
                        txt.insert("end", f"  {'✓' if found else '?'} {ref}\n",
                                   "good" if found else "warn")
            else:
                row("Anim states", "0 (header unreadable)")
        else:
            txt.insert("end", "  No .i3d file found for this character.\n", "dim")
            txt.insert("end", "  Expected in:\n", "dim")
            txt.insert("end", f"  {self.cfg.imagery_assets / 'Chars'}\n", "dim")

        # ── RAW char.def BLOCK ───────────────────────────────────────────────
        raw_body = char.get("_raw", "")
        if raw_body:
            txt.insert("end", "\n▼ RAW char.def  (click to expand)\n", "h")
            # Collapsed by default — show first 3 lines
            lines = raw_body.splitlines()
            preview = "\n".join(f"  {l}" for l in lines[:3])
            if len(lines) > 3:
                preview += f"\n  … ({len(lines)-3} more lines)"
            txt.insert("end", preview + "\n", "raw")

            # Tag to expand/collapse
            raw_start = txt.index("end-1c linestart")
            full_raw  = "\n".join(f"  {l}" for l in lines) + "\n"
            self._raw_expanded = getattr(self, "_raw_expanded", {})
            self._raw_expanded[name] = False

            def _toggle_raw(e, n=name, full=full_raw, preview_text=preview+"\n", self=self, txt=txt):
                expanded = self._raw_expanded.get(n, False)
                txt.configure(state="normal")
                # Find the raw block
                idx = txt.search("▼ RAW char.def", "1.0")
                if not idx:
                    txt.configure(state="disabled")
                    return
                block_start = txt.index(f"{idx} +1 line")
                block_end   = txt.index(f"{block_start} lineend +1c")
                # Count lines in current raw section
                cur = txt.get(block_start, "end")
                if not expanded:
                    # Expand: replace preview with full
                    txt.delete(block_start, "end")
                    txt.insert(block_start, full, "raw")
                    self._raw_expanded[n] = True
                else:
                    txt.delete(block_start, "end")
                    txt.insert(block_start, preview_text, "raw")
                    self._raw_expanded[n] = False
                txt.configure(state="disabled")

            # Bind the header line
            h_start = txt.search("▼ RAW char.def", "1.0")
            if h_start:
                h_end = f"{h_start} lineend"
                txt.tag_add("raw_toggle", h_start, h_end)
                txt.tag_configure("raw_toggle", foreground=ACCENT,
                                   font=("Segoe UI", 9, "bold"), underline=True)
                txt.tag_bind("raw_toggle", "<Button-1>", _toggle_raw)
                txt.tag_bind("raw_toggle", "<Enter>",
                             lambda e: txt.config(cursor="hand2"))
                txt.tag_bind("raw_toggle", "<Leave>",
                             lambda e: txt.config(cursor="arrow"))

        txt.configure(state="disabled")

    def _open_path(self, path: Path):
        """Open a file or its parent folder in the OS file manager."""
        import subprocess, sys
        try:
            target = path if path.is_dir() else path.parent
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(target)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception:
            pass

    def _export_all(self):
        if not HAS_PIL:
            self._status.set("PIL not available")
            return
        if not self._chars:
            self._status.set("No characters loaded")
            return
        dest = self.cfg.renders_dir / "Characters"
        dest.mkdir(parents=True, exist_ok=True)
        ok = skip = 0
        for ch in self._chars:
            name = ch["name"]
            portrait_path = find_portrait(self.cfg, name)
            try:
                if portrait_path:
                    img = Image.open(portrait_path).convert("RGB")
                else:
                    img = make_placeholder_portrait(name, 128)
                if img:
                    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
                    img.save(str(dest / f"{safe}.png"))
                    ok += 1
                else:
                    skip += 1
            except Exception:
                skip += 1
        self._status.set(f"Characters exported: {ok} portraits → {dest}")
