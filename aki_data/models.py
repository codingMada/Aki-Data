"""Datenmodell: ein Titel (Videospiel) mit den Merkmalen, nach denen IGDB suchen kann."""
from __future__ import annotations

from dataclasses import dataclass

from .igdb_vocab import FEATURES, GENRES, TAGS

MAX_GENRES = 4
MAX_TAGS = 12
MAX_COMPANIES = 4
MAX_KEYWORDS = 40
MAX_PLATFORMS = 20
MAX_ENGINES = 4

_GENRE_MAP = {g.casefold(): g for g in GENRES}
_TAG_MAP = {t.casefold(): t for t in TAGS}


@dataclass(frozen=True)
class Company:
    id: int          # IGDB-ID der Firma (für die Suche)
    name: str


@dataclass(frozen=True)
class Keyword:
    id: int          # IGDB-ID des Keywords (für die Suche)
    name: str        # wie in IGDB, englisch, z. B. "zombies"


@dataclass(frozen=True)
class Platform:
    id: int          # IGDB-ID der Plattform (für die Suche)
    name: str        # z. B. "PlayStation 4", "PC"


@dataclass(frozen=True)
class Engine:
    id: int          # IGDB-ID der Game Engine (für die Suche)
    name: str        # z. B. "Unreal Engine 4"


@dataclass(frozen=True)
class Title:
    name: str
    year: int
    genres: tuple[str, ...]
    tags: tuple[str, ...] = ()               # Themes, Game Modes und Perspektiven
    developers: tuple[Company, ...] = ()
    publishers: tuple[Company, ...] = ()
    keywords: tuple[Keyword, ...] = ()
    platforms: tuple[Platform, ...] = ()
    engines: tuple[Engine, ...] = ()
    igdb_id: int = 0                         # 0 = nicht aus IGDB (z. B. in Tests)
    popularity: int = 0                      # Anzahl Bewertungen in IGDB (für die Startwahrscheinlichkeit)

    @property
    def key(self) -> str:
        return self.name.casefold()

    @property
    def decade(self) -> str:
        return f"{self.year // 10 * 10}er"

    def features(self) -> set[str]:
        """Alle Merkmale als Schlüssel der Form 'art:wert', z. B. 'genre:Sci-Fi'."""
        feats = {f"decade:{self.decade}"}
        feats |= {f"genre:{g}" for g in self.genres}
        feats |= {f"tag:{t}" for t in self.tags}
        feats |= {f"developer:{c.name}" for c in self.developers}
        feats |= {f"publisher:{c.name}" for c in self.publishers}
        feats |= {f"keyword:{k.name}" for k in self.keywords}
        feats |= {f"platform:{p.name}" for p in self.platforms}
        feats |= {f"engine:{e.name}" for e in self.engines}
        return feats


_TAG_KIND_NAME = {"theme": "Thema", "mode": "Modus", "perspective": "Perspektive"}


def feature_label(key: str) -> str:
    """Merkmal in lesbarer Form, z. B. 'genre:Sci-Fi' -> 'Genre Sci-Fi'."""
    kind, value = key.split(":", 1)
    if kind == "tag" and value in FEATURES:
        return f"{_TAG_KIND_NAME[FEATURES[value].kind]} {value}"
    return {
        "genre": f"Genre {value}",
        "tag": f"Thema {value}",
        "decade": f"Jahrzehnt {value}",
        "developer": f"Entwickler {value}",
        "publisher": f"Publisher {value}",
        "keyword": f"Stichwort {value}",
        "platform": f"Plattform {value}",
        "engine": f"Engine {value}",
    }.get(kind, key)


def _pick(values, mapping: dict[str, str], limit: int) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    result: list[str] = []
    for v in values:
        mapped = mapping.get(str(v).strip().casefold())
        if mapped and mapped not in result:
            result.append(mapped)
    return tuple(result[:limit])


def _named(values, kind, limit: int) -> tuple:
    """Firmen, Keywords, Plattformen oder Engines als [{"id": .., "name": ..}, ...] (ungültige fallen weg, ohne Doppelte)."""
    out: list = []
    for v in values if isinstance(values, (list, tuple)) else ():
        if not isinstance(v, dict):
            continue
        vid, name = v.get("id"), " ".join(str(v.get("name", "")).split())
        if isinstance(vid, int) and not isinstance(vid, bool) and vid > 0 and name and len(name) <= 80:
            if all(x.id != vid for x in out):
                out.append(kind(vid, name))
    return tuple(out[:limit])


def title_from_dict(d) -> Title | None:
    """Prüft einen Titel streng. Gibt None zurück, wenn etwas nicht passt."""
    if not isinstance(d, dict):
        return None
    try:
        name = " ".join(str(d.get("name", "")).split())
        if not name or len(name) > 120:
            return None
        year = int(d.get("year"))
        if not 1950 <= year <= 2100:
            return None
    except (TypeError, ValueError):
        return None
    genres = _pick(d.get("genres"), _GENRE_MAP, MAX_GENRES)
    if not genres:
        return None
    tags = _pick(d.get("tags"), _TAG_MAP, MAX_TAGS)
    try:
        igdb_id = max(0, int(d.get("igdb_id") or 0))
        popularity = max(0, int(d.get("popularity") or 0))
    except (TypeError, ValueError):
        igdb_id = popularity = 0
    return Title(name, year, genres, tags, _named(d.get("developers"), Company, MAX_COMPANIES),
                 _named(d.get("publishers"), Company, MAX_COMPANIES), _named(d.get("keywords"), Keyword, MAX_KEYWORDS),
                 _named(d.get("platforms"), Platform, MAX_PLATFORMS), _named(d.get("engines"), Engine, MAX_ENGINES),
                 igdb_id, popularity)
