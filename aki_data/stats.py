"""Einfache Statistik: Trefferquote und durchschnittliche Fragenzahl (optionale Anforderung)."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "stats.json"


class Stats:
    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)
        self.games: list[dict] = []
        try:
            self.games = json.loads(self.path.read_text(encoding="utf-8"))["games"]
        except (OSError, ValueError, KeyError):
            self.games = []

    def record(self, correct: bool, questions: int) -> None:
        self.games.append({"correct": bool(correct), "questions": int(questions)})
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"games": self.games}), encoding="utf-8")
        except OSError:
            pass  # Statistik ist optional, ein Schreibfehler darf das Spiel nicht stoppen

    @property
    def hit_rate(self) -> float:
        return sum(g["correct"] for g in self.games) / len(self.games) if self.games else 0.0

    @property
    def avg_questions(self) -> float:
        return sum(g["questions"] for g in self.games) / len(self.games) if self.games else 0.0

    def summary(self) -> str:
        if not self.games:
            return "Noch keine Spiele gespielt."
        return (f"Spiele: {len(self.games)} · Trefferquote: {self.hit_rate:.0%} · "
                f"Ø Fragen: {self.avg_questions:.1f}")
