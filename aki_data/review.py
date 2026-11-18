"""Rückblick nach einem falschen Tipp: Wo lag der Fehler – beim Spieler, in den IGDB-Daten oder in der Engine?"""
from __future__ import annotations

from dataclasses import dataclass, field

from .engine import STRENGTH, Game
from .models import Title, feature_label
from .similarity import FEATURE_WEIGHTS

PLAYER, IGDB_DATA, ENGINE = "Spieler", "IGDB-Daten", "Engine"

# Merkmale, die in IGDB oft fehlen (von Nutzern gepflegt): ein «Ja» ohne Eintrag ist meist eine Datenlücke
SPARSE = {"keyword", "engine", "platform", "developer", "publisher"}


def _weight(key: str) -> float:
    return FEATURE_WEIGHTS.get(key.split(":", 1)[0], 0.0)


@dataclass(frozen=True)
class Finding:
    who: str            # Spieler, IGDB-Daten oder Engine
    text: str


@dataclass
class Review:
    actual: Title
    guess: Title
    checked: int = 0                     # Antworten mit Aussage (ohne «Weiss nicht»)
    findings: list[Finding] = field(default_factory=list)

    @property
    def mismatches(self) -> int:
        return sum(1 for f in self.findings if f.who != ENGINE and f.text.startswith("Frage "))

    @property
    def summary(self) -> str:
        if (self.actual.igdb_id and self.actual.igdb_id == self.guess.igdb_id) or self.actual.key == self.guess.key:
            return "Moment – das war doch mein Tipp!"
        if not self.mismatches:
            return f"Alle {self.checked} Antworten passen zu «{self.actual.name}». Der Fehler lag bei mir."
        return (f"{self.checked - self.mismatches} von {self.checked} Antworten passen zu «{self.actual.name}», "
                f"{self.mismatches} nicht.")


def _cause(category: str, said_yes: bool, actual: Title) -> tuple[str, str]:
    """Wer hat sich wahrscheinlich geirrt, und warum (für eine Antwort, die nicht zum Spiel passt)."""
    if category == "year":
        return PLAYER, f"Laut IGDB erschien das Spiel {actual.year}."
    if said_yes and category in SPARSE:
        return IGDB_DATA, "In IGDB fehlt dieser Eintrag beim Spiel vermutlich (die Daten sind dort lückenhaft)."
    if said_yes:
        return IGDB_DATA, "IGDB ordnet das Spiel anders ein (das Merkmal ist teils Ansichtssache)."
    return PLAYER, "IGDB führt dieses Merkmal beim Spiel. Vermutlich ein Irrtum, sonst ist es Ansichtssache."


def _differences(guess: Title, actual: Title, per_title: int = 3) -> list[str]:
    """Die wichtigsten Merkmale, in denen sich Tipp und gesuchtes Spiel unterscheiden (je Spiel eine Zeile)."""
    out = []
    for title, other in ((actual, guess), (guess, actual)):
        only = sorted(title.features() - other.features(), key=lambda k: (-_weight(k), k))[:per_title]
        if only:
            out.append(f"«{title.name}»: " + ", ".join(feature_label(k) for k in only))
    return out


def review(game: Game, actual: Title) -> Review:
    guess = game.best_guess()[0]
    result = Review(actual, guess)
    if (actual.igdb_id and actual.igdb_id == guess.igdb_id) or actual.key == guess.key:
        result.findings.append(Finding(PLAYER, f"«{actual.name}» war genau mein Tipp. Vielleicht verklickt?"))
        return result
    for n, (question, answer) in enumerate(game.history, 1):
        strength = STRENGTH[answer]
        if strength == 0:
            continue
        result.checked += 1
        said_yes = strength > 0
        if question.matches(actual) == said_yes:
            continue
        who, why = _cause(question.category, said_yes, actual)
        note = ""
        if abs(strength) < 1:
            note = " Nur «Eher», darum zählte es bloss im Gewicht."
        elif question.tolerant:
            note = " Stichwort: das Spiel verlor nur Gewicht, schied aber nicht aus."
        else:
            note = " Dadurch schied das Spiel aus."
        result.findings.append(Finding(who, f"Frage {n}: «{question.text}» – du: {answer}, "
                                            f"laut IGDB: {'Ja' if question.matches(actual) else 'Nein'}. {why}{note}"))
    if result.mismatches:
        return result

    # Alle Antworten passen: der Fehler lag bei der Engine
    index = next((i for i, t in enumerate(game.titles)
                  if (actual.igdb_id and t.igdb_id == actual.igdb_id) or t.key == actual.key), None)
    if index is None:
        result.findings.append(Finding(ENGINE, "Das Spiel war nie unter meinen Kandidaten. IGDB liefert pro Anfrage "
                                               "nur die bekanntesten Treffer, weniger bekannte Spiele fehlen darum oft."))
    else:
        rank = sorted(range(len(game.weights)), key=lambda k: -game.weights[k]).index(index) + 1
        when = (f"Die {game.max_questions} Fragen haben nicht gereicht"
                if len(game.history) >= game.max_questions else "Ich habe zu früh getippt")
        result.findings.append(Finding(ENGINE, f"{when}: «{actual.name}» lag auf Platz {rank} "
                                               f"({game.weights[index]:.0%}), «{guess.name}» auf Platz 1."))
    diffs = _differences(guess, actual)
    if diffs:
        result.findings.append(Finding(ENGINE, "Danach hätte ich noch fragen können: " + "; ".join(diffs) + "."))
    return result
