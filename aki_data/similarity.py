"""Ähnliche Titel: gewichteter Anteil gemeinsamer Merkmale (gewichtetes Jaccard-Mass)."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Title, feature_label

# Genres und Themen zählen am stärksten, dann der Entwickler, dann Publisher und Jahrzehnt.
FEATURE_WEIGHTS = {"genre": 3.0, "tag": 3.0, "developer": 2.0, "publisher": 1.0, "decade": 1.0,
                   "engine": 1.0, "platform": 0.25,
                   "keyword": 0.5}   # Keywords und Plattformen sind zahlreich: schwach gewichtet, sonst überdecken sie alles


def _weight(key: str) -> float:
    return FEATURE_WEIGHTS.get(key.split(":", 1)[0], 0.0)


def similarity(a: Title, b: Title) -> float:
    fa, fb = a.features(), b.features()
    union = sum(_weight(k) for k in fa | fb)
    if union == 0:
        return 0.0
    return sum(_weight(k) for k in fa & fb) / union


def shared_features(a: Title, b: Title, limit: int = 3) -> list[str]:
    """Die wichtigsten gemeinsamen Merkmale (als lesbare Texte) – dienen als Begründung."""
    shared = [k for k in a.features() & b.features() if _weight(k) > 0]
    shared.sort(key=lambda k: (-_weight(k), k))
    return [feature_label(k) for k in shared[:limit]]


@dataclass(frozen=True)
class Suggestion:
    title: Title
    score: float
    shared: tuple[str, ...]

    @property
    def reason(self) -> str:
        if not self.shared:
            return "Keine direkten gemeinsamen Merkmale"
        return "Gemeinsam: " + ", ".join(self.shared)


def suggest(target: Title, catalog: list[Title], count: int = 5) -> list[Suggestion]:
    """Die `count` ähnlichsten Titel (ohne den Titel selbst)."""
    candidates = [t for t in catalog if t.name != target.name and not (t.igdb_id and t.igdb_id == target.igdb_id)]
    chosen = sorted(candidates, key=lambda t: (-similarity(target, t), t.name))[:count]
    return [Suggestion(t, similarity(target, t), tuple(shared_features(target, t))) for t in chosen]
