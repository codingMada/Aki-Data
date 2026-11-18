"""Fragen zu den Merkmalen, nach denen IGDB suchen kann."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable

from .igdb_vocab import FEATURES, fact_text, question_text, topic_text
from .models import Company, Engine, Keyword, Platform, Title

YEAR_STEPS = (1990, 2000, 2010, 2020)
MIN_COMPANY_TITLES = 3     # Firmen mit weniger Spielen im Pool teilen kaum auf und machen die Wahl nur langsam
MIN_KEYWORD_TITLES = 3
MAX_KEYWORD_QUESTIONS = 60  # nur die häufigsten Keywords im Pool (sonst wird die Fragewahl langsam)
MIN_PLATFORM_TITLES = 3
MAX_PLATFORM_QUESTIONS = 25  # Plattformen gibt es viele (jede Konsolengeneration): nur die, die am besten aufteilen
MIN_ENGINE_TITLES = 3

# Kategorie in Worten, steht bei der Anzeige in Klammern hinter der Frage
CATEGORY_LABELS = {"genre": "Genre", "theme": "Thema", "mode": "Spielmodus", "perspective": "Perspektive",
                   "year": "Erscheinungsjahr", "developer": "Entwickler", "publisher": "Publisher",
                   "keyword": "Stichwort", "platform": "Plattform", "engine": "Game Engine"}


@dataclass(frozen=True)
class Question:
    id: str
    text: str                              # Standardtext, bzw. der von der AI formulierte Text
    predicate: Callable[[Title], bool]
    topic: str = ""                        # sachliche Beschreibung des Merkmals (für die AI)
    must: tuple[str, ...] = ()             # eines davon muss in der AI-Formulierung vorkommen
    variants: tuple[str, ...] = ()         # feste Formulierungen: dann braucht es keine AI (z. B. bei Jahreszahlen)
    fact: str = ""                         # Merkmal als kurzer Satzteil, z. B. «Genre Horror» (für den AI-Kontext)
    term: str = ""                         # englischer IGDB-Begriff (Keywords): die AI darf ihn übersetzen
    tolerant: bool = False                 # True: auch ein klares Ja/Nein schliesst nicht aus (IGDB-Daten lückenhaft)
    category: str = ""                     # Kategorie des Merkmals: genre, theme, mode, perspective, year,
                                           # developer, publisher, keyword, platform, engine
    patterns: tuple[str, ...] = ()         # korrekte Mustersätze für die AI (Satzbau, an den sie sich hält)

    def matches(self, title: Title) -> bool:
        """Trifft die Frage (mit «Ja») auf diesen Titel zu?"""
        return bool(self.predicate(title))

    @property
    def display(self) -> str:
        """Fragetext mit der Kategorie in Klammern, z. B. «Ist das Spiel für PC erschienen? (Plattform)»."""
        label = CATEGORY_LABELS.get(self.category)
        if not label or self.text.endswith(")") and f"({label}" in self.text:
            return self.text
        return f"{self.text} ({label})"

    def with_text(self, text: str) -> "Question":
        return replace(self, text=text)


def question_key(text: str) -> str:
    """Vergleichsform einer Frage (Gross-/Kleinschreibung und Satzzeichen egal)."""
    return re.sub(r"[\W_]+", " ", text.casefold()).strip()


def genre_question(genre: str) -> Question:
    return Question(f"genre:{genre}", f"Gehört das Spiel zum Genre «{genre}»?",
                    lambda t: genre in t.genres, topic=f"Das Genre «{genre}»", must=(genre.casefold(),),
                    fact=f"Genre {genre}", category="genre")


def tag_question(tag: str) -> Question:
    """Theme, Game Mode oder Perspektive (Text je nach Art, siehe igdb_vocab.py)."""
    return Question(f"tag:{tag}", question_text(tag), lambda t: tag in t.tags, topic=topic_text(tag),
                    must=(tag.casefold(),), fact=fact_text(tag), category=FEATURES[tag].kind)


def developer_question(company: Company) -> Question:
    return Question(f"developer:{company.id}", f"Wurde das Spiel von {company.name} entwickelt?",
                    lambda t: any(c.id == company.id for c in t.developers),
                    topic=f"Entwickelt vom Studio «{company.name}»", must=(company.name.casefold(),),
                    fact=f"entwickelt von {company.name}", category="developer",
                    patterns=(f"Wurde das Spiel von {company.name} entwickelt?",
                              f"Hat {company.name} das Spiel entwickelt?",
                              f"Stammt das Spiel vom Studio {company.name}?"))


def publisher_question(company: Company) -> Question:
    return Question(f"publisher:{company.id}", f"Wurde das Spiel von {company.name} veröffentlicht?",
                    lambda t: any(c.id == company.id for c in t.publishers),
                    topic=f"Veröffentlicht vom Publisher «{company.name}»", must=(company.name.casefold(),),
                    fact=f"veröffentlicht von {company.name}", category="publisher",
                    patterns=(f"Wurde das Spiel von {company.name} veröffentlicht?",
                              f"Hat {company.name} das Spiel herausgebracht?",
                              f"Ist {company.name} der Publisher des Spiels?"))


def keyword_question(keyword: Keyword) -> Question:
    """Ein Keyword aus IGDB (englisch, so wie IGDB es führt, z. B. «zombies»)."""
    return Question(f"keyword:{keyword.id}", f"Passt das Stichwort «{keyword.name}» zum Spiel?",
                    lambda t: any(k.id == keyword.id for k in t.keywords),
                    topic=f"Das Stichwort «{keyword.name}» passt zum Spiel", must=(keyword.name.casefold(),),
                    fact=f"Stichwort {keyword.name}", term=keyword.name, tolerant=True,
                    category="keyword",
                    patterns=("Spielt <deutscher Begriff> im Spiel eine Rolle?",
                              "Kommt <deutscher Begriff> im Spiel vor?",
                              "Passt <deutscher Begriff> zum Spiel?"))


def platform_question(platform: Platform) -> Question:
    return Question(f"platform:{platform.id}", f"Ist das Spiel für {platform.name} erschienen?",
                    lambda t: any(p.id == platform.id for p in t.platforms),
                    topic=f"Erschienen für die Plattform «{platform.name}»", must=(platform.name.casefold(),),
                    fact=f"erschienen für {platform.name}", category="platform",
                    patterns=(f"Ist das Spiel für {platform.name} erschienen?",
                              f"Gibt es das Spiel für {platform.name}?",
                              f"Kann man das Spiel auf {platform.name} spielen?"))


def engine_question(engine: Engine) -> Question:
    return Question(f"engine:{engine.id}", f"Läuft das Spiel auf der Engine «{engine.name}»?",
                    lambda t: any(e.id == engine.id for e in t.engines),
                    topic=f"Entwickelt mit der Game Engine «{engine.name}»", must=(engine.name.casefold(),),
                    fact=f"Engine {engine.name}", category="engine",
                    patterns=(f"Läuft das Spiel auf der Engine «{engine.name}»?",
                              f"Wurde das Spiel mit der Engine «{engine.name}» entwickelt?",
                              f"Nutzt das Spiel die Engine «{engine.name}»?"))


def decade_question(decade: str) -> Question:
    start = int(decade[:4])
    return Question(f"decade:{decade}", f"Erschien das Spiel in den {decade}-Jahren?",
                    lambda t: t.decade == decade,
                    variants=(f"Erschien das Spiel in den {decade}-Jahren?",
                              f"Stammt das Spiel aus den {decade}-Jahren?",
                              f"Kam das Spiel in den {decade}-Jahren heraus?"),
                    topic=f"Erscheinungsjahr zwischen {start} und {start + 9}",
                    must=(str(start), f"{start % 100:02d}er"), fact=f"erschienen in den {decade}-Jahren", category="year")


def before_question(year: int) -> Question:
    return Question(f"before:{year}", f"Erschien das Spiel vor dem Jahr {year}?",
                    lambda t: t.year < year,
                    variants=(f"Erschien das Spiel vor dem Jahr {year}?",
                              f"Kam das Spiel vor {year} heraus?",
                              f"Wurde das Spiel vor {year} veröffentlicht?"),
                    topic=f"Erscheinungsjahr vor {year}", must=(str(year),),
                    fact=f"vor {year} erschienen", category="year")


def _frequent(items: list, minimum: int, limit: int | None = None, pool: int = 0) -> list:
    """Firmen, Keywords, Plattformen bzw. Engines, die mindestens `minimum`-mal vorkommen."""
    counts = Counter(x.id for x in items)
    by_id = {x.id: x for x in items}
    chosen = [i for i, n in counts.items() if n >= minimum]
    if limit is not None:
        chosen = sorted(chosen, key=lambda i: abs(counts[i] - pool / 2))[:limit]
    return sorted((by_id[i] for i in chosen), key=lambda x: x.name)


def build_questions(titles: list[Title]) -> list[Question]:
    """Alle Fragen, die den Pool aufteilen (auf alle oder auf keinen Titel passende entfallen)."""
    candidates: list[Question] = [genre_question(g) for g in sorted({g for t in titles for g in t.genres})]
    candidates += [tag_question(x) for x in sorted({x for t in titles for x in t.tags})]
    candidates += [developer_question(c) for c in _frequent([c for t in titles for c in t.developers],
                                                            MIN_COMPANY_TITLES)]
    candidates += [publisher_question(c) for c in _frequent([c for t in titles for c in t.publishers],
                                                            MIN_COMPANY_TITLES)]
    candidates += [keyword_question(k) for k in _frequent([k for t in titles for k in t.keywords],
                                                          MIN_KEYWORD_TITLES, MAX_KEYWORD_QUESTIONS, len(titles))]
    candidates += [platform_question(p) for p in _frequent([p for t in titles for p in t.platforms],
                                                           MIN_PLATFORM_TITLES, MAX_PLATFORM_QUESTIONS, len(titles))]
    candidates += [engine_question(e) for e in _frequent([e for t in titles for e in t.engines], MIN_ENGINE_TITLES)]
    candidates += [decade_question(d) for d in sorted({t.decade for t in titles})]
    candidates += [before_question(y) for y in YEAR_STEPS]
    n = len(titles)
    return [q for q in candidates if 0 < sum(1 for t in titles if q.matches(t)) < n]
