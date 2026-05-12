import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.constants import *
from ui.widgets import *
from core.parsers import *

# ---------------------------------------------------------------------------
# Sound-file prefix → category mapping (longest-match wins)
# Derived from Revenant (1999) sound naming conventions.
# ---------------------------------------------------------------------------
_SFX_PREFIXES: List[Tuple[str, str]] = sorted([
    # ── Player ──────────────────────────────────────────────────────────────
    ("loc",    "Player — Locke"),
    # ── Named story NPCs ────────────────────────────────────────────────────
    ("bae",    "NPC — Bayne"),
    ("mor",    "NPC — Morganna"),
    ("nav",    "NPC — Navarro"),
    ("jon",    "NPC — Jong"),
    ("gina",   "NPC — Gina"),
    ("gin",    "NPC — Gina"),
    ("and",    "NPC — Andria"),
    ("dal",    "NPC — Dalindra"),
    ("ger",    "NPC — Geralt"),
    ("gow",    "NPC — Gowin"),
    ("hru",    "NPC — Hruthford"),
    ("jas",    "NPC — Jastree"),
    ("miy",    "NPC — Miyamoto"),
    ("mau",    "NPC — Maureen"),
    ("oli",    "NPC — Oli"),
    ("pau",    "NPC — Pauline"),
    ("ran",    "NPC — Randolph"),
    ("sab",    "NPC — Sab"),
    ("she",    "NPC — Shekiss"),
    ("tm",     "NPC — Town Male"),
    ("tw",     "NPC — Town Woman"),
    ("gir",    "NPC — Townfolk"),
    ("loo",    "NPC — Townfolk"),
    # ── Human enemies ───────────────────────────────────────────────────────
    ("war",    "Enemy — Warrior"),
    ("kni",    "Enemy — Knight"),
    ("nin",    "Enemy — Ninja"),
    ("dru",    "Enemy — Druid"),
    ("mon",    "Enemy — Monk"),
    ("dor",    "Enemy — Dorgon"),
    ("jha",    "Enemy — Jhang"),
    ("yha",    "Enemy — Yhang"),
    ("pri",    "Enemy — Priest"),
    ("lur",    "Enemy — Lurker"),
    ("mos",    "Enemy — Mossback"),
    ("oc",     "Enemy — Orc"),
    ("og",     "Enemy — Ogre"),
    # ── Undead ──────────────────────────────────────────────────────────────
    ("ske",    "Undead — Skeleton"),
    ("sk",     "Undead — Skeleton"),
    ("zom",    "Undead — Zombie"),
    ("und",    "Undead"),
    ("wra",    "Undead — Wraith"),
    ("app",    "Undead — Apparition"),
    # ── Beasts ──────────────────────────────────────────────────────────────
    ("ara",    "Beast — Arakna"),
    ("spi",    "Beast — Spider"),
    ("wol",    "Beast — Wolf"),
    ("bat",    "Beast — Bat"),
    ("kan",    "Beast — Kanaric"),
    ("hop",    "Beast — Hopper"),
    ("iss",    "Beast — Isstass"),
    ("sol",    "Beast — Solja"),
    # ── Bosses / large creatures ────────────────────────────────────────────
    ("dem",    "Boss — Demon"),
    ("dra",    "Boss — Dragon"),
    ("gol",    "Boss — Golem"),
    ("gar",    "Boss — Gargoyle"),
    ("sto",    "Boss — Stone Golem"),
    # ── Combat SFX ──────────────────────────────────────────────────────────
    ("swo",    "Combat — Sword Swing"),
    ("kic",    "Combat — Kick"),
    ("blo",    "Combat — Block"),
    ("hit",    "Combat — Hit"),
    ("imp",    "Combat — Impact"),
    ("arm",    "Combat — Armor"),
    ("step",   "Combat — Footsteps"),
    ("bow",    "Combat — Bow"),
    ("arr",    "Combat — Arrow"),
    ("rol",    "Combat — Roll"),
    ("str",    "Combat — Struggle"),
    ("nec",    "Combat — Neck Break"),
    ("fis",    "Combat — Fist"),
    ("pul",    "Combat — Pull Out"),
    ("hip",    "Combat — Hip"),
    ("fal",    "Environment — Fall"),
    # ── Magic & Spells ──────────────────────────────────────────────────────
    ("fir",    "Magic — Fire"),
    ("ice",    "Magic — Ice"),
    ("fre",    "Magic — Freeze"),
    ("lig",    "Magic — Lightning"),
    ("mag",    "Magic"),
    ("spl",    "Magic — Spell"),
    ("hea",    "Magic — Heal"),
    ("ant",    "Magic — Antimagic"),
    ("cha",    "Magic — Charm"),
    ("aur",    "Magic — Aura"),
    ("tel",    "Magic — Teleport"),
    ("jte",    "Magic — Teleport"),
    ("cur",    "Magic — Cure"),
    ("dex",    "Magic — Dexterity"),
    ("nou",    "Magic — Nourish"),
    ("res",    "Magic — Restore"),
    ("inv",    "Magic — Invisibility"),
    ("par",    "Magic — Paralyze"),
    ("cat",    "Magic — Cataclysm"),
    ("cry",    "Magic — Crystalism"),
    ("mae",    "Magic — Maelstrom"),
    ("man",    "Magic — Mana Drain"),
    ("met",    "Magic — Meteor Storm"),
    ("nap",    "Magic — Napalm"),
    ("poi",    "Magic — Poison"),
    ("sym",    "Magic — Symbol"),
    ("ten",    "Magic — Tensizzle"),
    ("vil",    "Magic — Viles"),
    ("gvo",    "Magic — Vortex"),
    ("iri",    "Magic — Iris Pulse"),
    ("fge",    "Magic — Geyser"),
    ("sge",    "Magic — Geyser"),
    ("tal",    "Magic — Talisman"),
    ("lif",    "Magic — Life Drain"),
    ("nak",    "Magic — Nakmemite"),
    ("oce",    "Magic — Ocean"),
    ("aci",    "Magic — Acid Pool"),
    ("esp",    "Magic — Spray"),
    ("qui",    "Magic — Quicksand"),
    ("fon",    "Magic — Font"),
    ("cata",   "Magic — Cataclysm"),
    ("onf",    "Magic — On Fire"),
    ("san",    "Magic — Sand?"),
    # ── Environment / ambient ────────────────────────────────────────────────
    ("amb",    "Environment — Ambient"),
    ("cav",    "Environment — Cave"),
    ("wat",    "Environment — Water"),
    ("tor",    "Environment — Torch/Tornado"),
    ("win",    "Environment — Wind"),
    ("swa",    "Environment — Swamp"),
    ("roc",    "Environment — Rock"),
    ("mud",    "Environment — Mud"),
    ("wor",    "Environment — Worm"),
    ("fee",    "Environment — Feet"),
    ("sna",    "Environment — Snake"),
    ("sco",    "Environment — Scorpion"),
    # ── Doors / containers / traps ──────────────────────────────────────────
    ("keepd",  "Doors — Keep Door"),
    ("kee",    "Doors — Keep"),
    ("lab",    "Doors — Lab Chest"),
    ("por",    "Doors — Portcullis"),
    ("woo",    "Doors — Wood Door"),
    ("cla",    "Doors — Clay"),
    ("tre",    "Doors — Treasure"),
    ("lev",    "Doors — Lever"),
    ("sty",    "Area — Stygeon"),
    ("che",    "Doors — Chest"),
    ("cra",    "Doors — Crack"),
    # ── Items ───────────────────────────────────────────────────────────────
    ("pot",    "Items — Potion"),
    ("scr",    "Items — Scroll"),
    ("key",    "Items — Key"),
    ("gold",   "Items — Gold"),
    ("gol",    "Items — Gold"),
    ("jew",    "Items — Jewel"),
    ("wea",    "Items — Weapon"),
    ("rep",    "Items — Weapon Replace"),
    ("pou",    "Items — Pouch"),
    ("foo",    "Items — Food"),
    ("coi",    "Items — Coins"),
    # ── UI ──────────────────────────────────────────────────────────────────
    ("cli",    "UI — Click"),
    ("fai",    "UI — Fail"),
    ("sel",    "UI — Select"),
    ("bla",    "UI — Blank"),
    ("ins",    "UI — Install"),
    ("pow",    "UI — Power Up"),
], key=lambda t: -len(t[0]))   # longest prefix first → most specific wins


def _classify_sfx(stem: str) -> str:
    """Return a category string for a sound file stem using prefix matching."""
    s = stem.lower()
    for pfx, cat in _SFX_PREFIXES:
        if s.startswith(pfx):
            return cat
    return "Effects — Misc"


class SoundsTab(tk.Frame):
    """Browse and play all 1000+ game SFX/speech/music files, grouped by category."""

    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=BG_MID)
        self._status       = status
        self._sounds: List[Dict] = []
        self._all_cats: List[str] = []
        self._current_proc = None
        self._build_ui()
        self.after(600, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")

        tk.Label(bar, text="Category:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10, 4))
        self._cat_var = tk.StringVar(value="All")
        self._cat_cb = ttk.Combobox(bar, textvariable=self._cat_var,
                                    state="readonly", width=28,
                                    font=("Segoe UI", 9))
        self._cat_cb.pack(side="left", padx=(0, 10))
        self._cat_cb.bind("<<ComboboxSelected>>", self._filter)

        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))
        self._flt_var = tk.StringVar()
        tk.Entry(bar, textvariable=self._flt_var,
                 bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                 font=("Segoe UI", 10), relief="flat", width=20
                 ).pack(side="left", padx=4)
        self._flt_var.trace_add("write", self._filter)

        tk.Button(bar, text="▶ Play", bg=ACCENT3, fg="#000", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10,
                  command=self._play_selected).pack(side="left", padx=8)
        tk.Button(bar, text="■ Stop", bg=RED, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10,
                  command=self._stop).pack(side="left", padx=2)

        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        tv_f = tk.Frame(pane, bg=BG_MID)
        pane.add(tv_f, minsize=560)
        cols = ("name", "cat", "size")
        self._tv = ttk.Treeview(tv_f, columns=cols, show="headings",
                                selectmode="browse")
        self._tv.heading("name", text="File",     anchor="w")
        self._tv.heading("cat",  text="Category", anchor="w")
        self._tv.heading("size", text="KB",        anchor="center")
        self._tv.column("name", width=280, stretch=True)
        self._tv.column("cat",  width=220, stretch=False)
        self._tv.column("size", width=55,  stretch=False, anchor="center")
        sb = ttk.Scrollbar(tv_f, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<Double-Button-1>", lambda e: self._play_selected())

        det = tk.Frame(pane, bg=BG_PANEL, padx=12, pady=12)
        pane.add(det, minsize=200)
        tk.Label(det, text="SOUND DETAILS", bg=BG_PANEL, fg=ACCENT2,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Separator(det).pack(fill="x", pady=6)
        self._det_lbl = tk.Label(det, text="Select a file to preview",
                                 bg=BG_PANEL, fg=FG_DIM,
                                 font=("Segoe UI", 9), wraplength=180,
                                 justify="left", anchor="w")
        self._det_lbl.pack(anchor="w")

    def _load_all(self):
        self._status.set("Scanning sound files…")
        sounds = []
        seen: set = set()

        for snd_root in self.cfg.extract_dir.rglob("Sound"):
            if not snd_root.is_dir():
                continue

            # Effects WAV files (in Sound/effects/ subdirectory)
            eff_dir = snd_root / "effects"
            if eff_dir.is_dir():
                for f in sorted(eff_dir.glob("*.wav")):
                    key = f.name.upper()
                    if key in seen:
                        continue
                    seen.add(key)
                    sounds.append({
                        "name": f.name,
                        "cat":  _classify_sfx(f.stem),
                        "path": f,
                        "size_kb": f.stat().st_size // 1024,
                    })

            # WAV files directly in Sound/ (fallback for alternate layouts)
            for f in sorted(snd_root.glob("*.wav")):
                key = f.name.upper()
                if key in seen:
                    continue
                seen.add(key)
                sounds.append({
                    "name": f.name,
                    "cat":  _classify_sfx(f.stem),
                    "path": f,
                    "size_kb": f.stat().st_size // 1024,
                })

            # OGG music tracks
            for f in sorted(snd_root.rglob("*.ogg")):
                key = f.name.upper()
                if key in seen:
                    continue
                seen.add(key)
                sounds.append({
                    "name": f.name,
                    "cat":  "Music",
                    "path": f,
                    "size_kb": f.stat().st_size // 1024,
                })

            # English speech MP3s
            eng = snd_root / "english"
            if eng.is_dir():
                for f in sorted(eng.glob("*.mp3")):
                    key = f.name.upper()
                    if key in seen:
                        continue
                    seen.add(key)
                    sounds.append({
                        "name": f.name,
                        "cat":  "Speech (English)",
                        "path": f,
                        "size_kb": f.stat().st_size // 1024,
                    })

        # Sort by category then filename for a clean grouped view
        sounds.sort(key=lambda s: (s["cat"], s["name"].lower()))

        self._sounds = sounds
        cats = sorted(set(s["cat"] for s in sounds))
        self._all_cats = cats
        self._cat_cb["values"] = ["All"] + cats
        self._cat_cb.current(0)

        self._populate(sounds)
        self._count_lbl.config(text=f"{len(sounds)} sounds")
        self._status.set(f"Sounds: {len(sounds)} files  |  {len(cats)} categories")

    def _populate(self, data: List[Dict]):
        self._tv.delete(*self._tv.get_children())
        for s in data:
            self._tv.insert("", "end",
                values=(s["name"], s["cat"], s["size_kb"]),
                tags=(str(s["path"]),))

    def _filter(self, *_):
        cat = self._cat_var.get()
        flt = self._flt_var.get().strip().lower()
        filtered = self._sounds
        if cat and cat != "All":
            filtered = [s for s in filtered if s["cat"] == cat]
        if flt:
            filtered = [s for s in filtered
                        if flt in s["name"].lower() or flt in s["cat"].lower()]
        self._populate(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._sounds)}")

    def _selected_path(self) -> Optional[Path]:
        sel = self._tv.selection()
        if not sel:
            return None
        tags = self._tv.item(sel[0], "tags")
        return Path(tags[0]) if tags else None

    def _play_selected(self):
        p = self._selected_path()
        if p is None or not p.exists():
            self._status.set("Select a sound file first.")
            return
        self._stop()
        self._status.set(f"Playing: {p.name}")
        self._det_lbl.config(text=f"{p.name}\n{p.stat().st_size // 1024} KB\n{p.parent.name}/")
        import subprocess, sys, os
        try:
            if sys.platform == "win32":
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            self._status.set(f"Playback error: {e}")

    def _stop(self):
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass
        self._current_proc = None


# ═══════════════════════════════════════════════════════════════════════════════
#  CINEMATIX TAB
# ═══════════════════════════════════════════════════════════════════════════════
