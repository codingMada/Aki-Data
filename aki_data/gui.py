"""Grafische Oberfläche mit Tkinter"""
from __future__ import annotations

import base64
import threading
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

from . import ai_client, igdb, turns
from .catalog import search
from .engine import ANSWERS, Game
from .review import ENGINE, IGDB_DATA, PLAYER, review
from .models import Title
from .online import OnlineSearch
from .similarity import suggest
from .stats import Stats

RULES = ("Denke an ein Videospiel – ich errate es!\n"
         "Ich stelle dir bis zu 20 Fragen. Ab Frage 2 durchsuche ich die ganze IGDB.")

BG = "#0e0e10"         
SURFACE = "#18181b"     
SURFACE_2 = "#26262c"  
BORDER = "#2f2f35"
ACCENT = "#9147ff"      
ACCENT_HOVER = "#a970ff"
TEXT = "#efeff1"
MUTED = "#adadb8"
DANGER = "#ff4f4d"
WHO_COLORS = {PLAYER: "#ffb31a", IGDB_DATA: ACCENT, ENGINE: DANGER}  

GENIE_PATH = Path(__file__).resolve().parent / "assets" / "genie.gif"
GENIE_GREY = (88, 86, 86)      
GENIE_CROP = (95, 0, 305, 300) 
WRAP = 520


# --- Flaschengeist ---------------------------------------------------------------------------
def _hex_rgb(color: str) -> bytes:
    return bytes(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _recolor_gif(data: bytes, old: tuple[int, int, int], new: str) -> tuple[bytes, list[int]]:
    out = bytearray(data)
    target, rgb = bytes(old), _hex_rgb(new)

    def patch(start: int, count: int) -> None:
        for k in range(start, start + 3 * count, 3):
            if out[k:k + 3] == target:
                out[k:k + 3] = rgb

    delays: list[int] = []
    packed = data[10]
    i = 13
    if packed & 0x80:
        size = 2 << (packed & 7)
        patch(i, size)
        i += 3 * size
    delay = 100
    while i < len(data):
        block = data[i]
        if block == 0x21:                         # Erweiterung
            if data[i + 1] == 0xF9:               # Grafiksteuerung: Dauer des nächsten Frames
                delay = (data[i + 4] | data[i + 5] << 8) * 10 or 100
            i += 2
            while data[i]:
                i += data[i] + 1
            i += 1
        elif block == 0x2C:                       # Bild
            local = data[i + 9]
            i += 10
            if local & 0x80:
                size = 2 << (local & 7)
                patch(i, size)
                i += 3 * size
            i += 1
            while data[i]:
                i += data[i] + 1
            i += 1
            delays.append(delay)
        else:
            break
    return bytes(out), delays


def load_genie(bg: str) -> list[tuple[tk.PhotoImage, int]]:
    try:
        data, delays = _recolor_gif(GENIE_PATH.read_bytes(), GENIE_GREY, bg)
    except (OSError, IndexError):
        return []
    encoded = base64.b64encode(data)
    x1, y1, x2, y2 = GENIE_CROP
    frames = []
    for n, delay in enumerate(delays):
        try:
            full = tk.PhotoImage(data=encoded, format=f"gif -index {n}")
        except tk.TclError:
            break
        crop = tk.PhotoImage(width=x2 - x1, height=y2 - y1)
        crop.tk.call(crop, "copy", full, "-from", x1, y1, x2, y2)
        frames.append((crop, delay))
    return frames


class App:
    def __init__(self, root: tk.Tk, ai=ai_client, igdb_client=igdb):
        self.root = root
        self.ai = ai
        self.igdb = igdb_client
        self.titles: list[Title] = []      # Startpool aus IGDB (wird beim ersten Spiel geholt)
        self.stats = Stats()
        self.game: Game | None = None
        self.online: OnlineSearch | None = None
        self.igdb_error = ""
        self.guess: Title | None = None
        self._token = 0
        root.title("Aki – ich kenne jedes deiner Spiele!")
        root.geometry("920x660")
        root.minsize(860, 620)
        root.configure(bg=BG)
        families = set(tkfont.families(root))
        self.family = next((f for f in ("Segoe UI", "Helvetica Neue", "Helvetica") if f in families), "TkDefaultFont")
        self._style()
        self._layout()
        self.show_start()

    # --- Aufbau ---------------------------------------------------------------
    def _style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("IGDB.Horizontal.TProgressbar", troughcolor=SURFACE_2, background=ACCENT,
                        bordercolor=SURFACE_2, lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
        style.configure("IGDB.Vertical.TScrollbar", troughcolor=BG, background=SURFACE_2, bordercolor=BG,
                        lightcolor=SURFACE_2, darkcolor=SURFACE_2, arrowcolor=MUTED, gripcount=0, arrowsize=12)
        style.map("IGDB.Vertical.TScrollbar", background=[("active", ACCENT), ("pressed", ACCENT)])

    def _layout(self) -> None:
        header = tk.Frame(self.root, bg=BG, padx=24, pady=14)
        header.pack(fill="x")
        tk.Label(header, text=" AKI ", bg=ACCENT, fg="white", font=(self.family, 13, "bold")).pack(side="left")
        tk.Label(header, text=" Data", bg=BG, fg=TEXT, font=(self.family, 16, "bold")).pack(side="left")
        tk.Label(header, text="   der spielerische Empfehler", bg=BG, fg=MUTED,
                 font=(self.family, 10)).pack(side="left", pady=(4, 0))
        self.status = tk.Label(header, text="", bg=BG, fg=MUTED, font=(self.family, 9))
        self.status.pack(side="right")
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(self.root, bg=BG, padx=24, pady=20)
        body.pack(fill="both", expand=True)
        side = tk.Frame(body, bg=SURFACE, padx=10, pady=10, highlightthickness=1, highlightbackground=BORDER)
        side.pack(side="left", fill="y", padx=(0, 24))
        self.genie_frames = load_genie(SURFACE)
        self.genie = tk.Label(side, bg=SURFACE)
        self.genie.pack(expand=True)
        tk.Label(side, text="Der Spiele-Geist", bg=SURFACE, fg=MUTED, font=(self.family, 9, "italic")).pack()
        if self.genie_frames:
            self._animate(0)
        else:
            self.genie.configure(text="🧞", fg=TEXT, font=(self.family, 72))
        self.container = tk.Frame(body, bg=BG)
        self.container.pack(side="left", fill="both", expand=True)

    def _animate(self, n: int) -> None:
        image, delay = self.genie_frames[n]
        try:
            self.genie.configure(image=image)
            self.root.after(delay, self._animate, (n + 1) % len(self.genie_frames))
        except tk.TclError:
            pass  # Fenster wurde geschlossen

    # --- Hilfen ---------------------------------------------------------------
    def clear(self) -> tk.Frame:
        self._token += 1  # verwirft noch laufende AI-Antworten des vorherigen Bildschirms
        for key in "12345":
            self.root.unbind(key)
        for child in self.container.winfo_children():
            child.destroy()
        return self.container

    def label(self, parent, text, size=11, bold=False, color=TEXT, bg=None, wrap=WRAP, pady=(0, 8)) -> tk.Label:
        bg = bg or parent.cget("bg")
        lbl = tk.Label(parent, text=text, bg=bg, fg=color, font=(self.family, size, "bold" if bold else "normal"),
                       wraplength=wrap, justify="left", anchor="w")
        lbl.pack(anchor="w", pady=pady)
        return lbl

    def button(self, parent, text, command, kind="secondary", **pack) -> tk.Button:
        """Flacher Button: primary (lila), secondary (grau), ghost (nur Text)."""
        colors = {"primary": (ACCENT, "white", ACCENT_HOVER),
                  "secondary": (SURFACE_2, TEXT, BORDER),
                  "ghost": (parent.cget("bg"), MUTED, parent.cget("bg"))}[kind]
        bg, fg, hover = colors
        btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                        activeforeground=fg, relief="flat", bd=0, cursor="hand2", anchor="w",
                        font=(self.family, 11, "bold" if kind == "primary" else "normal"), padx=16, pady=8)
        btn.bind("<Enter>", lambda _e: btn.configure(bg=hover, fg=TEXT if kind == "ghost" else fg))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=bg, fg=fg))
        btn.pack(**({"anchor": "w", "pady": 3} | pack))
        return btn

    def disable(self, btn: tk.Button) -> None:
        btn.configure(state="disabled", bg=SURFACE_2, disabledforeground=MUTED, cursor="arrow")
        btn.unbind("<Enter>")
        btn.unbind("<Leave>")

    def bubble(self, parent, text: str, size=15, bold=True) -> tk.Frame:
        """Sprechblase des Flaschengeists (mit Spitze nach links). Gibt das Innere zurück."""
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=(0, 16))
        tail = tk.Canvas(row, width=14, height=40, bg=parent.cget("bg"), highlightthickness=0)
        tail.create_polygon(14, 12, 0, 22, 14, 32, fill=SURFACE_2, outline=SURFACE_2)
        tail.pack(side="left", anchor="n", pady=8)
        inner = tk.Frame(row, bg=SURFACE_2, padx=20, pady=16)
        inner.pack(side="left", fill="x", expand=True)
        text_label = self.label(inner, text, size, bold, wrap=WRAP - 40, pady=0)
        inner.bind("<Configure>", lambda e: text_label.configure(wraplength=max(200, e.width - 40)))
        return inner

    def scroll_area(self, parent) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview, style="IGDB.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG)
        window = canvas.create_window(0, 0, window=inner, anchor="nw")

        def update(_e=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            if inner.winfo_reqheight() > canvas.winfo_height():
                if not bar.winfo_ismapped():
                    bar.pack(side="right", fill="y", padx=(8, 0))
            elif bar.winfo_ismapped():
                bar.pack_forget()
                canvas.yview_moveto(0)

        def wheel(event) -> None:
            if inner.winfo_reqheight() > canvas.winfo_height():
                canvas.yview_scroll(-1 if event.delta > 0 or event.num == 4 else 1, "units")

        inner.bind("<Configure>", update)
        canvas.bind("<Configure>", lambda e: (canvas.itemconfigure(window, width=e.width), update()))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind(seq, wheel)
        canvas.bind("<Enter>", lambda _e: [self.root.bind_all(q, wheel) for q in ("<MouseWheel>", "<Button-4>", "<Button-5>")])
        canvas.bind("<Leave>", lambda _e: [self.root.unbind_all(q) for q in ("<MouseWheel>", "<Button-4>", "<Button-5>")])
        return inner

    def card(self, parent) -> tk.Frame:
        frame = tk.Frame(parent, bg=SURFACE, padx=14, pady=8, highlightthickness=1, highlightbackground=BORDER)
        frame.pack(fill="x", pady=3)
        return frame

    def progress(self, parent, **kw) -> ttk.Progressbar:
        bar = ttk.Progressbar(parent, style="IGDB.Horizontal.TProgressbar", **kw)
        bar.pack(fill="x", pady=(0, 16))
        return bar

    def run_async(self, fn, callback) -> None:
        """fn im Hintergrund ausführen, danach callback(result, error) im Fenster-Thread aufrufen."""
        token = self._token
        box: dict = {}

        def work() -> None:
            try:
                box["result"] = fn()
            except Exception as exc:
                box["error"] = exc

        thread = threading.Thread(target=work, daemon=True)
        thread.start()

        def poll() -> None:
            if token != self._token:
                return 
            if thread.is_alive():
                self.root.after(100, poll)
                return
            try:
                callback(box.get("result"), box.get("error"))
            except tk.TclError:
                pass 

        poll()

    # --- Bildschirme ----------------------------------------------------------------
    def problem(self) -> str | None:
        return self.igdb.availability_problem() or self.ai.availability_problem()

    def show_start(self) -> None:
        c = self.clear()
        problem = self.problem()
        self.status.configure(text=f"{self.ai.describe()}  ·  {self.igdb.describe()}" if problem is None else "")
        self.label(c, "Willkommen, Reisender!", 22, True)
        self.bubble(c, RULES, 13, False)
        if problem is not None:
            self.label(c, problem, 10, color=DANGER)
        start = self.button(c, "Spiel starten", self.start_game, "primary")
        if problem is not None:
            self.disable(start)
            self.button(c, "Erneut prüfen", self.show_start)
        self.button(c, "Beenden", self.root.destroy, "ghost")
        self.label(c, self.stats.summary(), 9, color=MUTED, pady=(16, 0))

    def show_wait(self, text: str) -> None:
        c = self.clear()
        self.bubble(c, text, 14, True)
        bar = self.progress(c, mode="indeterminate")
        bar.start(12)
        self.button(c, "Abbrechen", self.show_start, "ghost")

    def show_error(self, message: str, retry, fallback=None) -> None:
        c = self.clear()
        self.label(c, "Das hat nicht geklappt", 18, True, color=DANGER)
        self.bubble(c, message, 11, False)
        self.button(c, "Nochmals versuchen", retry, "primary")
        if fallback is not None:
            self.button(c, "Standardfrage verwenden", fallback)
        self.button(c, "Abbrechen", self.show_start, "ghost")

    # --- Spielablauf ----------------------------------------------------------------
    def start_game(self) -> None:
        """Ohne funktionierende AI und ohne IGDB beginnt keine Runde."""
        problem = self.problem()
        if problem is not None:
            self.show_error(problem, retry=self.show_start)
            return
        if not self.titles:
            self.show_wait("Ich rufe die bekanntesten Spiele aus IGDB herbei …")
            self.run_async(self.igdb.start_pool, self.on_start_pool)
            return
        self.game = Game(self.titles)
        self.online = OnlineSearch(self.igdb)
        self.igdb_error = ""
        self.step()

    def on_start_pool(self, titles, error) -> None:
        if error is not None:
            message = str(error) if isinstance(error, self.igdb.IGDBError) else f"Unerwarteter Fehler: {error}"
            self.show_error(message, retry=self.start_game)
            return
        self.titles = titles
        self.start_game()

    def step(self) -> None:
        game = self.game
        if game.is_finished():
            self.show_guess(*game.best_guess())
            return
        number = len(game.history) + 1
        searching = number >= self.online.from_question
        self.show_wait(("Ich durchsuche IGDB und überlege" if searching else "Ich überlege")
                       + f" mir Frage {number} …")
        self.run_async(lambda: turns.next_question(game, self.ai, self.online), self.on_planned)

    def on_planned(self, result, error) -> None:
        if error is not None:
            message = str(error) if isinstance(error, ai_client.AIError) else f"Unerwarteter Fehler: {error}"
            self.show_error(message, retry=self.step, fallback=self.use_default_question)
            return
        self.igdb_error = result.igdb_error
        if result.question is None:
            self.show_guess(*self.game.best_guess())
        else:
            self.show_question(result.question)

    def use_default_question(self) -> None:
        question = self.game.next_question()
        if question is None:
            self.show_guess(*self.game.best_guess())
        else:
            self.show_question(question)

    def show_question(self, question) -> None:
        c = self.clear()
        n = len(self.game.history)
        top = tk.Frame(c, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text=f"FRAGE {n + 1}", bg=BG, fg=ACCENT, font=(self.family, 10, "bold")).pack(side="left")
        tk.Label(top, text=f"von {self.game.max_questions}", bg=BG, fg=MUTED,
                 font=(self.family, 10)).pack(side="left", padx=(6, 0))
        tk.Label(top, text=f"{self.game.pool_size()} von {len(self.game.titles)} Spielen im Rennen", bg=BG,
                 fg=MUTED, font=(self.family, 9)).pack(side="right")
        self.progress(c, maximum=self.game.max_questions, value=n).pack_configure(pady=(6, 16))
        self.bubble(c, question.display, 16, True)
        answers = tk.Frame(c, bg=BG)
        answers.pack(fill="x")
        for i, answer in enumerate(ANSWERS, 1):
            kind = "primary" if answer in ("Ja", "Nein") else "secondary"
            self.button(answers, f"{i}   {answer}", lambda a=answer: self.on_answer(a), kind, fill="x", pady=2)
            self.root.bind(str(i), lambda _e, a=answer: self.on_answer(a))
        if self.game.history:
            self.label(c, f"Bisher bekannt: {self.game.known_facts()}", 9, color=MUTED, pady=(14, 0))
        if self.igdb_error:
            self.label(c, f"Hinweis: {self.igdb_error}", 9, color=DANGER, pady=(6, 0))
        self.button(c, "Abbrechen", self.show_start, "ghost", pady=(8, 0))

    def on_answer(self, answer: str) -> None:
        if self.game.current is None:
            return
        self.game.answer(answer)
        self.step()

    def show_guess(self, guess: Title, prob: float) -> None:
        self.guess = guess
        c = self.clear()
        inner = self.bubble(c, "Ich hab's! Du denkst an …", 13, False)
        self.label(inner, guess.name, 24, True, color=ACCENT, wrap=WRAP - 40, pady=(8, 0))
        self.label(inner, f"{guess.year}  ·  ich bin zu {prob:.0%} sicher", 10, color=MUTED, wrap=WRAP - 40,
                   pady=(2, 0))
        self.label(c, "Habe ich richtig geraten?", 14, True)
        row = tk.Frame(c, bg=BG)
        row.pack(anchor="w")
        self.button(row, "Ja, genau!", lambda: self.on_result(True), "primary", side="left", padx=(0, 8))
        self.button(row, "Nein", lambda: self.on_result(False), "secondary", side="left")

    def on_result(self, correct: bool) -> None:
        self.stats.record(correct, len(self.game.history))
        if correct:
            self.show_suggestions(self.guess)
        else:
            self.show_wrong()

    def show_wrong(self, message: str = "") -> None:
        c = self.clear()
        self.bubble(c, "Schade! An welches Spiel hast du gedacht?", 15, True)
        self.label(c, "Tippe den Namen ein, ich suche ihn in IGDB.", 10, color=MUTED)
        entry = tk.Entry(c, bg=SURFACE_2, fg=TEXT, insertbackground=TEXT, relief="flat", font=(self.family, 12),
                         highlightthickness=2, highlightbackground=SURFACE_2, highlightcolor=ACCENT)
        entry.pack(fill="x", ipady=8, pady=(0, 8))
        entry.focus_set()
        entry.bind("<Return>", lambda _e: self.lookup(entry.get()))
        if message:
            self.label(c, message, 10, color=DANGER)
        row = tk.Frame(c, bg=BG)
        row.pack(anchor="w")
        self.button(row, "Suchen", lambda: self.lookup(entry.get()), "primary", side="left", padx=(0, 8))
        self.button(row, "Neue Runde", self.start_game, "secondary", side="left")

    def known_titles(self) -> list[Title]:
        """Startpool plus alle Spiele, die in dieser Runde aus IGDB dazugekommen sind."""
        pool = self.game.titles if self.game else []
        seen = {t.key for t in self.titles}
        return self.titles + [t for t in pool if t.key not in seen]

    def lookup(self, text: str) -> None:
        found = search(self.known_titles(), text)
        if text.strip() and not found:
            try:
                found = self.igdb.search(text)
            except self.igdb.IGDBError as exc:
                self.show_wrong(str(exc))
                return
        if not text.strip():
            self.show_wrong("Bitte einen Titel eingeben.")
        elif not found:
            self.show_wrong(f"«{text.strip()}» habe ich nicht gefunden. Versuche einen anderen Namen.")
        elif len(found) == 1 or found[0].key == " ".join(text.casefold().split()):
            self.show_review(found[0])
        else:
            c = self.clear()
            self.bubble(c, "Meinst du eines dieser Spiele?", 15, True)
            for t in found:
                self.button(c, f"{t.name}  ({t.year})", lambda t=t: self.show_review(t), fill="x", pady=2)
            self.button(c, "Keines davon", self.show_wrong, "ghost", pady=(10, 0))

    def show_review(self, actual: Title) -> None:
        """Rückblick nach einem falschen Tipp: welche Antworten nicht zum gesuchten Spiel passen und warum."""
        if self.game is None:
            self.show_suggestions(actual)
            return
        result = review(self.game, actual)
        c = self.clear()
        self.bubble(c, f"Ah, «{actual.name}»! Schauen wir, wo es schiefging …", 14, True)
        self.label(c, result.summary, 11, True)
        row = tk.Frame(c, bg=BG)              
        row.pack(side="bottom", anchor="w", pady=(12, 0))
        self.button(row, "Ähnliche Spiele zeigen", lambda: self.show_suggestions(actual), "primary",
                    side="left", padx=(0, 8))
        self.button(row, "Neue Runde", self.start_game, "secondary", side="left")
        area = self.scroll_area(c)
        for finding in result.findings:
            card = self.card(area)
            tk.Label(card, text=finding.who.upper(), bg=SURFACE, fg=WHO_COLORS[finding.who],
                     font=(self.family, 8, "bold")).pack(anchor="w")
            text = self.label(card, finding.text, 10, wrap=WRAP - 30, pady=(2, 0))
            card.bind("<Configure>", lambda e, t=text: t.configure(wraplength=max(200, e.width - 34)))

    def show_suggestions(self, target: Title) -> None:
        c = self.clear()
        self.bubble(c, f"Wenn dir «{target.name}» gefällt, probier doch mal:", 14, True)
        for s in suggest(target, self.known_titles()):
            card = tk.Frame(c, bg=SURFACE, padx=14, pady=8, highlightthickness=1, highlightbackground=BORDER)
            card.pack(fill="x", pady=3)
            head = tk.Frame(card, bg=SURFACE)
            head.pack(fill="x")
            tk.Label(head, text=s.title.name, bg=SURFACE, fg=TEXT, font=(self.family, 11, "bold")).pack(side="left")
            tk.Label(head, text=str(s.title.year), bg=SURFACE, fg=MUTED,
                     font=(self.family, 10)).pack(side="left", padx=(8, 0))
            tk.Label(head, text=f"{s.score:.0%} ähnlich", bg=SURFACE, fg=ACCENT,
                     font=(self.family, 9, "bold")).pack(side="right")
            self.label(card, s.reason, 9, color=MUTED, wrap=WRAP - 30, pady=(2, 0))
        row = tk.Frame(c, bg=BG)
        row.pack(anchor="w", pady=(12, 0))
        self.button(row, "Neue Runde", self.start_game, "primary", side="left", padx=(0, 8))
        self.button(row, "Beenden", self.root.destroy, "ghost", side="left")
        self.label(c, self.stats.summary(), 9, color=MUTED, pady=(10, 0))


def run() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
