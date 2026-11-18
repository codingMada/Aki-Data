"""Eine Spielrunde mit der AI: IGDB abfragen (ab Frage 2), Frage wählen, Frage formulieren."""
from __future__ import annotations

from dataclasses import dataclass, field

from .engine import Game
from .questions import Question

CHOICES = 5   # so viele Merkmale bekommt die AI zur Auswahl


@dataclass
class Result:
    question: Question | None            # None: das Spiel ist zu Ende (Tipp)
    notes: list[str] = field(default_factory=list)   # was in dieser Runde passiert ist (für die Ausgabe im Terminal)
    raw: list[str] = field(default_factory=list)     # Rohantworten der AI
    choice_called: bool = False
    choice_ok: bool = False              # AI-Wahl des Merkmals war brauchbar (sonst das beste laut Programm)
    text_ok: bool = False                # AI-Frage war brauchbar (sonst Standardtext)
    igdb_error: str = ""                 # IGDB-Problem in dieser Runde (das Spiel läuft trotzdem weiter)


def next_question(game: Game, ai, online=None) -> Result:
    """Führt eine Runde aus und stellt (per game.select) die nächste Frage. Wirft ai_client.AIError."""
    res = Result(None)
    if online is not None:
        note = online.update(game)
        if note:
            res.notes.append(note)
        res.igdb_error = online.last_error
    known = game.known_facts()
    shown = game.candidates()

    if game.is_finished():
        _collect(res, ai)
        return res
    question = _choose(game, ai, res, known, shown)
    phase = "Kriterien sammeln" if game.collecting(question) else "eingrenzen"
    res.notes.append(f"Merkmal ({phase}): {question.fact or question.id}, schliesst erwartet "
                     f"{game.expected_exclusion(question):.0%} von {len(game.results())} Resultaten aus.")
    asked = [text for text, _ in game.transcript()]
    if question.variants:   # Jahreszahlen: feste, geprüfte Formulierungen, keine AI nötig
        text = question.variants[len(game.history) % len(question.variants)]
        res.notes.append("Frage: feste Formulierung (Jahr), kein AI-Aufruf.")
        res.question = game.select(question, text)
        res.text_ok = True
        _collect(res, ai)
        return res
    text = ai.phrase_question(question, asked)
    if text is None:
        res.notes.append("Frage: AI-Antwort unbrauchbar, Standardtext verwendet.")
        res.question = game.select(question)
    else:
        res.text_ok = True
        res.question = game.select(question, text)
    _collect(res, ai)
    return res


def _choose(game: Game, ai, res: Result, known: str, shown: list[int]) -> Question:
    """Die AI wählt unter den besten Merkmalen das, das am meisten ausschliesst (sonst gilt das beste)."""
    options = game.options(CHOICES, diverse=True)
    pick = getattr(ai, "pick_question", None)
    if pick is None or len(options) < 2:
        return options[0]
    res.choice_called = True
    hits = [(q, game.result_hits(q)) for q in options]
    index = pick(hits, len(game.results()), [game.titles[i] for i in shown], known)
    if index is None:
        res.notes.append("Wahl: AI-Antwort unbrauchbar, das Programm wählt das Merkmal.")
        return options[0]
    res.choice_ok = True
    res.notes.append(f"Wahl: AI wählt {options[index].fact or options[index].id} "
                     f"(Option {index + 1} von {len(options)}).")
    return options[index]


def _collect(res: Result, ai) -> None:
    take = getattr(ai, "take_log", None)
    if take:
        res.raw = take()
