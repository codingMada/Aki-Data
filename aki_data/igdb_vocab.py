"""Feste Merkmale aus IGDB."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    label: str                  # deutsche Bezeichnung, kommt in Fragen und im Katalog vor
    kind: str                   # genre, theme, mode, perspective
    field: str                  # IGDB-Feld der Spiele, z. B. "genres"
    ids: tuple[int, ...]        # IGDB-IDs
    igdb_name: str = ""         # englischer Name in IGDB (für --check)
    question: str = ""          # eigene Standardfrage (sonst die der Art)


GENRE_FEATURES = (
    Feature("Point-and-Click", "genre", "genres", (2,), "Point-and-click"),
    Feature("Kampfspiel", "genre", "genres", (4,), "Fighting"),
    Feature("Shooter", "genre", "genres", (5,), "Shooter"),
    Feature("Musikspiel", "genre", "genres", (7,), "Music"),
    Feature("Jump-and-Run", "genre", "genres", (8,), "Platform"),
    Feature("Puzzle", "genre", "genres", (9,), "Puzzle"),
    Feature("Rennspiel", "genre", "genres", (10,), "Racing"),
    Feature("Echtzeit-Strategie", "genre", "genres", (11,), "Real Time Strategy (RTS)"),
    Feature("Rollenspiel (RPG)", "genre", "genres", (12,), "Role-playing (RPG)"),
    Feature("Simulation", "genre", "genres", (13,), "Simulator"),
    Feature("Sport", "genre", "genres", (14,), "Sport"),
    Feature("Strategie", "genre", "genres", (15,), "Strategy"),
    Feature("Rundenstrategie", "genre", "genres", (16,), "Turn-based strategy (TBS)"),
    Feature("Taktik", "genre", "genres", (24,), "Tactical"),
    Feature("Hack-and-Slash", "genre", "genres", (25,), "Hack and slash/Beat 'em up"),
    Feature("Quiz", "genre", "genres", (26,), "Quiz/Trivia"),
    Feature("Flipper", "genre", "genres", (30,), "Pinball"),
    Feature("Abenteuer", "genre", "genres", (31,), "Adventure"),
    Feature("Indie", "genre", "genres", (32,), "Indie"),
    Feature("Arcade", "genre", "genres", (33,), "Arcade"),
    Feature("Visual Novel", "genre", "genres", (34,), "Visual Novel"),
    Feature("Kartenspiel & Brettspiel", "genre", "genres", (35,), "Card & Board Game"),
    Feature("MOBA", "genre", "genres", (36,), "MOBA"),
)

TAG_FEATURES = (
    # Themen
    Feature("Action", "theme", "themes", (1,), "Action"),
    Feature("Fantasy", "theme", "themes", (17,), "Fantasy"),
    Feature("Sci-Fi", "theme", "themes", (18,), "Science fiction"),
    Feature("Horror", "theme", "themes", (19,), "Horror"),
    Feature("Thriller", "theme", "themes", (20,), "Thriller"),
    Feature("Überleben", "theme", "themes", (21,), "Survival"),
    Feature("Historisch", "theme", "themes", (22,), "Historical"),
    Feature("Schleichen", "theme", "themes", (23,), "Stealth"),
    Feature("Komödie", "theme", "themes", (27,), "Comedy"),
    Feature("Wirtschaft", "theme", "themes", (28,), "Business"),
    Feature("Drama", "theme", "themes", (31,), "Drama"),
    Feature("Sandbox", "theme", "themes", (33,), "Sandbox"),
    Feature("Lernspiel", "theme", "themes", (34,), "Educational"),
    Feature("Kinder", "theme", "themes", (35,), "Kids",
            question="Ist das Spiel speziell für Kinder gemacht?"),
    Feature("Offene Welt", "theme", "themes", (38,), "Open world",
            question="Spielt das Spiel in einer offenen Welt?"),
    Feature("Krieg", "theme", "themes", (39,), "Warfare"),
    Feature("Party", "theme", "themes", (40,), "Party"),
    Feature("4X", "theme", "themes", (41,), "4X (explore, expand, exploit, and exterminate)"),
    Feature("Mystery", "theme", "themes", (43,), "Mystery"),
    Feature("Romantik", "theme", "themes", (44,), "Romance"),
    # Spielmodi
    Feature("Einzelspieler", "mode", "game_modes", (1,), "Single player",
            question="Kann man das Spiel als Einzelspieler spielen?"),
    Feature("Mehrspieler", "mode", "game_modes", (2,), "Multiplayer",
            question="Hat das Spiel einen Mehrspieler-Modus?"),
    Feature("Koop", "mode", "game_modes", (3,), "Co-operative",
            question="Kann man das Spiel im Koop-Modus spielen?"),
    Feature("Splitscreen", "mode", "game_modes", (4,), "Split screen",
            question="Kann man das Spiel im Splitscreen spielen?"),
    Feature("MMO", "mode", "game_modes", (5,), "Massively Multiplayer Online (MMO)",
            question="Ist das Spiel ein MMO?"),
    Feature("Battle Royale", "mode", "game_modes", (6,), "Battle Royale",
            question="Hat das Spiel einen Battle-Royale-Modus?"),
    # Perspektiven
    Feature("Ich-Perspektive", "perspective", "player_perspectives", (1,), "First person",
            question="Spielt man das Spiel aus der Ich-Perspektive?"),
    Feature("Third-Person", "perspective", "player_perspectives", (2,), "Third person",
            question="Sieht man die Spielfigur von hinten (Third-Person)?"),
    Feature("Vogelperspektive", "perspective", "player_perspectives", (3,), "Bird view / Isometric",
            question="Sieht man das Spiel von oben (Vogelperspektive)?"),
    Feature("Seitenansicht", "perspective", "player_perspectives", (4,), "Side view",
            question="Sieht man das Spielgeschehen von der Seite (Seitenansicht)?"),
    Feature("Textbasiert", "perspective", "player_perspectives", (5,), "Text",
            question="Ist das Spiel textbasiert?"),
    Feature("VR", "perspective", "player_perspectives", (7,), "Virtual Reality",
            question="Spielt man das Spiel in VR?"),
)

# Fragetexte und Kurzform (für «Bisher bekannt») je Art
KIND_QUESTION = {
    "genre": "Gehört das Spiel zum Genre «{label}»?",
    "theme": "Spielt das Thema «{label}» eine Rolle?",
    "mode": "Hat das Spiel den Spielmodus «{label}»?",
    "perspective": "Spielt man das Spiel in der Perspektive «{label}»?",
}
KIND_FACT = {
    "genre": "Genre {label}",
    "theme": "Thema {label}",
    "mode": "Modus {label}",
    "perspective": "Perspektive {label}",
}
KIND_TOPIC = {
    "genre": "Das Genre «{label}»",
    "theme": "Das Thema «{label}» kommt vor",
    "mode": "Der Spielmodus «{label}» ist vorhanden",
    "perspective": "Die Spielperspektive «{label}»",
}

FEATURES: dict[str, Feature] = {f.label: f for f in (*GENRE_FEATURES, *TAG_FEATURES)}
GENRES = tuple(f.label for f in GENRE_FEATURES)
TAGS = tuple(f.label for f in TAG_FEATURES)
EROTIC_THEME = 42   # erotische Spiele werden in allen Anfragen ausgeschlossen

# IGDB-Feld -> {IGDB-ID -> Bezeichnung}
_BY_ID: dict[str, dict[int, str]] = {}
for _f in FEATURES.values():
    for _id in _f.ids:
        _BY_ID.setdefault(_f.field, {})[_id] = _f.label


def labels_for(field: str, ids) -> list[str]:
    """Deutsche Bezeichnungen zu IGDB-IDs eines Feldes (unbekannte IDs fallen weg, ohne Doppelte)."""
    table = _BY_ID.get(field, {})
    out: list[str] = []
    for i in ids or ():
        label = table.get(i) if isinstance(i, int) else None
        if label and label not in out:
            out.append(label)
    return out


def question_text(label: str) -> str:
    f = FEATURES[label]
    return f.question or KIND_QUESTION[f.kind].format(label=label)


def fact_text(label: str) -> str:
    f = FEATURES[label]
    return KIND_FACT[f.kind].format(label=label)


def topic_text(label: str) -> str:
    f = FEATURES[label]
    return KIND_TOPIC[f.kind].format(label=label)
