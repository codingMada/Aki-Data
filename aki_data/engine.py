"""Spielkern: Frage wählen (Informationsgewinn), Wahrscheinlichkeiten aktualisieren, raten."""
from __future__ import annotations

import math

from .models import Title
from .questions import Question, build_questions

ANSWERS = ("Ja", "Eher ja", "Weiss nicht", "Eher nein", "Nein")

# Stärke der Antwort
STRENGTH = {"Ja": 1.0, "Eher ja": 0.5, "Weiss nicht": 0.0, "Eher nein": -0.5, "Nein": -1.0}

UNSURE_FACTOR = 0.55
TOLERANT_FACTOR = 0.1 
MAX_QUESTIONS = 20
CONFIDENCE = 0.8
POOL_SIZE = 10
START_CATEGORIES = ("genre", "theme", "mode", "perspective", "year")


def answer_factor(matches: bool, strength: float, tolerant: bool = False) -> float:
    """Faktor, mit dem das Gewicht eines Titels nach einer Antwort multipliziert wird."""
    if strength == 0:
        return 1.0
    agrees = matches if strength > 0 else not matches
    if agrees:
        return 1.0
    if abs(strength) < 1.0:
        return UNSURE_FACTOR                                # Eher: 0,55
    return TOLERANT_FACTOR if tolerant else 0.0             # Ja/Nein: Stichwort 0,1, sonst scheidet aus


def prior(title: Title) -> float:
    """Startgewicht: bekannte Spiele sind wahrscheinlicher"""
    return 1.0 + math.log1p(title.popularity)


def normalize(weights: list[float]) -> list[float]:
    total = sum(weights)
    return [w / total for w in weights]


def entropy(probs: list[float]) -> float:
    """H = -Summe p_i * log2(p_i): Unsicherheit über den gesuchten Titel."""
    return -sum(p * math.log2(p) for p in probs if p > 0)


class Game:
    def __init__(self, titles: list[Title], questions: list[Question] | None = None,
                 max_questions: int = MAX_QUESTIONS, confidence: float = CONFIDENCE):
        self._fixed_questions = questions
        self.max_questions = max_questions
        self.confidence = confidence
        self.history: list[tuple[Question, str]] = []
        self._current: Question | None = None
        self._set_titles(titles)

    def _set_titles(self, titles: list[Title]) -> None:
        unique: dict[str, Title] = {}
        for t in titles:
            unique.setdefault(t.key, t)
        if len(unique) < 2:
            raise ValueError("Das Spiel braucht mindestens 2 Titel")
        self.titles = list(unique.values())
        self.questions = self._fixed_questions if self._fixed_questions is not None else build_questions(self.titles)
        self._matches: dict[str, list[bool]] = {q.id: [q.matches(t) for t in self.titles] for q in self.questions}
        weights = [prior(t) for t in self.titles]
        self.mismatches = [0] * len(self.titles)  # klare Widersprüche zu toleranten Fragen (Stichwörtern)
        for question, answer in self.history:     # bisherige Antworten auf die (neuen) Titel anwenden
            strength = STRENGTH[answer]
            for i, t in enumerate(self.titles):
                m = question.matches(t)
                weights[i] *= answer_factor(m, strength, question.tolerant)
                if question.tolerant and abs(strength) == 1.0 and (strength > 0) != m:
                    self.mismatches[i] += 1
        if not any(weights):
            raise ValueError("Kein Titel passt zu den klaren Antworten")
        self.weights = normalize(weights)

    def replace_titles(self, titles: list[Title]) -> None:
        """Neuer Kandidaten-Pool. Alle bisherigen Antworten werden neu angewendet.
        """
        self._set_titles(titles)
        self._current = None

    # --- Wahrscheinlichkeiten -------------------------------------------------
    @property
    def probabilities(self) -> list[float]:
        return list(self.weights)

    def transcript(self) -> list[tuple[str, str]]:
        """Bisherige Fragen (so wie gestellt) und Antworten."""
        return [(q.text, a) for q, a in self.history]

    def best_guess(self) -> tuple[Title, float]:
        i = max(range(len(self.weights)), key=lambda k: self.weights[k])
        return self.titles[i], self.weights[i]

    def top(self, n: int = 3) -> list[tuple[Title, float]]:
        order = sorted(range(len(self.weights)), key=lambda k: -self.weights[k])[:n]
        return [(self.titles[i], self.weights[i]) for i in order]

    # --- Pool der AI -------------------------------------------------------------
    def candidates(self, n: int = POOL_SIZE) -> list[int]:
        """Indizes der n wahrscheinlichsten Titel"""
        alive = [i for i, w in enumerate(self.weights) if w > 0]
        return sorted(alive, key=lambda k: -self.weights[k])[:n]

    def pool_size(self) -> int:
        """Wie viele Titel noch im Rennen sind (Gewicht mindestens 1 % vom besten)."""
        top = max(self.weights)
        return sum(1 for w in self.weights if w >= top / 100)

    def known_facts(self) -> str:
        """Was die bisherigen Antworten sagen, als kurzer Text."""
        prefix = {"Ja": "", "Eher ja": "wahrscheinlich ", "Eher nein": "wahrscheinlich nicht ", "Nein": "nicht "}
        parts = [prefix[a] + q.fact for q, a in self.history if q.fact and a in prefix]
        return "; ".join(parts) if parts else "noch nichts"

    def options(self, n: int = 5, diverse: bool = False) -> list[Question]:
        """Die n besten Merkmalsfragen der aktuellen Phase"""
        ranked = [q for _, q in sorted(self._usable(), key=lambda pair: pair[0], reverse=True)]
        if not diverse:
            return ranked[:n]
        best: dict[str, Question] = {}
        for q in ranked:
            best.setdefault(q.category, q)
        first = list(best.values())
        chosen = (first + [q for q in ranked if q not in first])[:n]
        return [q for q in ranked if q in chosen]   # Reihenfolge nach Wertung

    def result_hits(self, question: Question) -> int:
        """Auf wie viele Resultate trifft die Frage zu?"""
        matches = self._matches[question.id]
        return sum(1 for i in self.results() if matches[i])

    def select(self, question: Question, text: str | None = None) -> Question:
        """Stellt eine der Fragen."""
        self._current = question.with_text(text) if text else question
        return self._current

    # --- Fragen wählen --------------------------------------------------------
    def information_gain(self, question: Question) -> float:
        """IG(q) = H(vorher) - erwartetes H(nachher). Hoch, wenn Ja/Nein gleichmässig aufteilen."""
        probs = self.weights
        matches = self._matches[question.id]
        p_yes = sum(p for p, m in zip(probs, matches) if m)
        if p_yes <= 1e-12 or p_yes >= 1 - 1e-12:
            return 0.0

        def posterior_entropy(answer_is_yes: bool) -> float:
            ws = [p * answer_factor(m, 1.0 if answer_is_yes else -1.0, question.tolerant)
                  for p, m in zip(probs, matches)]
            return entropy(normalize(ws))

        expected = p_yes * posterior_entropy(True) + (1 - p_yes) * posterior_entropy(False)
        return entropy(probs) - expected

    def results(self) -> list[int]:
        """Indizes der Titel, die am besten zu den klaren Antworten passen (die «Resultate»)."""
        alive = [i for i, w in enumerate(self.weights) if w > 0]
        fewest = min(self.mismatches[i] for i in alive)
        return [i for i in alive if self.mismatches[i] == fewest]

    def expected_exclusion(self, question: Question, results: list[int] | None = None) -> float:
        """Erwarteter Anteil der Resultate (0 bis 1), den die Antwort ausschliesst."""
        results = self.results() if results is None else results
        total = sum(self.weights[i] for i in results)
        if len(results) < 2 or total <= 0:
            return 0.0
        matches = self._matches[question.id]
        n_yes = sum(1 for i in results if matches[i])
        p_yes = sum(self.weights[i] for i in results if matches[i]) / total
        excluded = p_yes * (len(results) - n_yes) + (1 - p_yes) * n_yes
        return excluded / len(results)

    def asked_categories(self) -> set[str]:
        return {q.category for q, _ in self.history}

    def collecting(self, question: Question) -> bool:
        """Gehört die Frage zur ersten Phase (Kriterien sammeln)?"""
        return question.category in START_CATEGORIES and question.category not in self.asked_categories()

    def _remaining(self) -> list[Question]:
        asked = {q.id for q, _ in self.history}
        return [q for q in self.questions if q.id not in asked]

    def _usable(self) -> list[tuple[tuple[float, float], Question]]:
        """Fragen der aktuellen Phase mit Wertung (erwarteter Ausschluss, Informationsgewinn)."""
        gains = {q.id: self.information_gain(q) for q in self._remaining()}
        usable = [q for q in self._remaining() if gains[q.id] > 1e-9]
        results = self.results()
        if len(results) >= 2:
            open_ = [q for q in usable if not self._answer_follows(q, results)]
            usable = open_ or usable   # passt nichts mehr eindeutig, lieber eine «überflüssige» Frage als keine
        # Phase 1: solange eine Startkategorie noch offen ist, nur aus diesen fragen
        start = [q for q in usable if self.collecting(q)]
        usable = start or usable
        return [((self.expected_exclusion(q, results), gains[q.id]), q) for q in usable]

    def _answer_follows(self, question: Question, consistent: list[int]) -> bool:
        """Folgt die Antwort schon aus dem Bekannten? (z. B. «vor 2000?» nach «2010er: Ja»)."""
        matches = self._matches[question.id]
        hits = sum(1 for i in consistent if matches[i])
        return hits == 0 or hits == len(consistent)

    def is_finished(self) -> bool:
        if len(self.history) >= self.max_questions or self.best_guess()[1] >= self.confidence:
            return True
        return not self._usable()   # keine Frage teilt die Kandidaten noch auf

    def next_question(self) -> Question | None:
        """Die beste Frage der aktuellen Phase (None, wenn das Spiel zu Ende ist)."""
        if self.is_finished():
            self._current = None
            return None
        self._current = max(self._usable(), key=lambda pair: pair[0])[1]
        return self._current

    @property
    def current(self) -> Question | None:
        return self._current

    def set_text(self, text: str) -> None:
        """Die aktuelle Frage mit dem von der AI formulierten Text stellen."""
        if self._current is None:
            raise RuntimeError("Es wurde noch keine Frage gewählt (next_question aufrufen)")
        self._current = self._current.with_text(text)

    # --- Antworten verarbeiten ---------------------------------------------------
    def answer(self, answer: str) -> None:
        if answer not in STRENGTH:
            raise ValueError(f"Unbekannte Antwort: {answer!r}")
        if self._current is None:
            raise RuntimeError("Es wurde noch keine Frage gestellt (next_question aufrufen)")
        question, strength = self._current, STRENGTH[answer]
        matches = self._matches[question.id]
        weights = [w * answer_factor(m, strength, question.tolerant) for w, m in zip(self.weights, matches)]
        if not any(weights):
            # kann nur bei einer Frage vorkommen, die die verbleibenden Titel nicht aufteilt
            raise ValueError("Kein Titel passt mehr zu den klaren Antworten")
        self.weights = normalize(weights)
        if question.tolerant and abs(strength) == 1.0:
            for i, m in enumerate(matches):
                if (strength > 0) != m:
                    self.mismatches[i] += 1
        self.history.append((question, answer))
        self._current = None
