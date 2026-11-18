"""Ab Frage 2: aus den bisherigen Antworten eine IGDB-Anfrage bauen und den Pool mit den Treffern erweitern."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import igdb
from .engine import Game

FROM_QUESTION = 2      # ab der zweiten Frage: sobald die erste klare Antwort da ist
MAX_POOL = 1500       # mehr Kandidaten machen die Fragewahl langsam; die unwahrscheinlichsten fallen weg


@dataclass
class OnlineSearch:
    client: object = igdb                 # braucht fetch(clauses) -> (titel, anfrage, abgeschnitten)
    from_question: int = FROM_QUESTION
    queries: list[str] = field(default_factory=list)   # gesendete Anfragen (für Debug)
    last_error: str = ""
    _clauses: tuple[str, ...] | None = None
    _truncated: bool = True

    def update(self, game: Game) -> str | None:
        """Vor der nächsten Frage aufrufen. Gibt eine Notiz zurück (oder None, wenn es nichts zu tun gab)."""
        if len(game.history) + 1 < self.from_question:
            return None
        clauses = igdb.constraints(game.history)
        if not clauses:
            return "IGDB: noch keine klare Antwort, die sich abfragen lässt."
        key = tuple(clauses)
        if key == self._clauses:
            return None
        try:
            note = self._strict(game, key)
        except igdb.IGDBError as exc:
            self.last_error = str(exc)
            return f"IGDB: {exc} Das Spiel läuft mit dem bisherigen Pool weiter."
        self.last_error = ""
        return note

    def _strict(self, game: Game, key: tuple[str, ...]) -> str:
        if self._clauses is not None and not self._truncated and set(self._clauses) <= set(key):
            self._clauses = key
            return "IGDB: letzte Trefferliste war vollständig, die neue Antwort engt lokal ein."
        note, self._truncated = self._fetch(game, list(key), "Passend zu allen klaren Antworten")
        self._clauses = key
        return note

    def _fetch(self, game: Game, clauses: list[str], what: str) -> tuple[str, bool]:
        """Treffer holen und in den Pool aufnehmen. Gibt (Notiz, abgeschnitten) zurück."""
        titles, body, truncated = self.client.fetch(clauses)
        self.queries.append(body)
        if not titles:
            return f"IGDB: {what}: keine Treffer, der Pool bleibt.", truncated
        before = len(game.titles)
        merged = igdb.unique_names([*game.titles, *titles])
        game.replace_titles(merged)
        if len(game.titles) > MAX_POOL:
            keep = sorted(range(len(game.titles)), key=lambda i: -game.weights[i])[:MAX_POOL]
            game.replace_titles([game.titles[i] for i in sorted(keep)])
        more = " (abgeschnitten, die bekanntesten)" if truncated else ""
        return (f"IGDB: {what}: {len(titles)} Treffer{more}, {len(merged) - before} neu im Pool, "
                f"jetzt {len(game.titles)} Spiele."), truncated
