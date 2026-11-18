"""IGDB-Anbindung"""

from __future__ import annotations

import calendar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .igdb_vocab import EROTIC_THEME, FEATURES, GENRE_FEATURES, TAG_FEATURES, labels_for
from .models import Title, title_from_dict

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "igdb.json"  # Zugangsdaten

API = "https://api.igdb.com/v4"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TIMEOUT = 20.0
MAX_LIMIT = 500
START_POOL_SIZE = 500  # so viele bekannte Spiele sind von Anfang an Kandidaten

# Hauptspiele, Remakes, Remaster, erweiterte Spiele (keine DLCs, Bundles, Mods …)
GAME_TYPES = (0, 8, 9, 10)
BASE_FILTER = (
    f"game_type = ({','.join(map(str, GAME_TYPES))}) & version_parent = null"
    f" & first_release_date != null & themes != ({EROTIC_THEME})"
)
FIELDS = (
    "name,first_release_date,genres,themes,game_modes,player_perspectives,total_rating_count,keywords.name,"
    "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
    "platforms.name,game_engines.name"
)

"""Filter nutzlose Einträge aus der Datenbank mit diesem Muster bevor daraus Fragen werden"""
META_KEYWORD = re.compile(
    r"\bios\b|android|\bpax\b|gamescom|\be3\b|award|nominee|winner|achievement|trophies|trophy|\bdlc\b|"
    r"downloadable|digital distribution|bink|dolby|\bfps\b|\b[48]k\b|\bhd\b|high definition|controller|"
    r"support|backwards? compat|games on demand|games with gold|greatest hits|platinum hits|player's choice|"
    r"ea app|origin|\bgog\b|humble|onlive|gamersgate|pre-?order|pre-release|retail|\bport\b|fan translation|"
    r"cloud|leaderboard|save point|auto-?sav|checkpoint|motion blur|ragdoll|particle|voice acting|soundtrack|"
    r"\bwasd\b|polygonal|\b[23]d\b|engine|mod support|language|censor|retroachievements|crossplay|cross-play|"
    r"exclusive|\bonline\b|in-game|\bui\b|\bhud\b|menu|loading|patch|early access|kickstarter|"
    r"demo|benchmark|cutscene|scripted|context sensitive|white noise|\bbots\b|stat tracking|unlockable|"
    r"game reference|pop culture|easter egg|meme|speedrun|developer|publisher|available on|crowd ?fund|"
    r"homebrew|unofficial|previously on",
    re.IGNORECASE,
)

META_ENGINE = re.compile(
    r"in-?house|proprietary|custom|unknown|physics|havok|bink|fmod|wwise|speedtree|scaleform|"
    r"aseprite|photoshop|blender|\bmaya\b|3ds max|zbrush|substance",
    re.IGNORECASE,
)


def is_meta_keyword(name: str) -> bool:
    return bool(META_KEYWORD.search(name or ""))


def platform_name(name: str) -> str:
    """Kurzer Plattformname: «PC (Microsoft Windows)» -> «PC»."""
    short = re.sub(r"\s*\(.*\)\s*$", "", name or "").strip()
    return short or (name or "").strip()


class IGDBError(Exception):
    """Problem mit IGDB (Text ist für den Nutzer gedacht)."""


# --- Zugangsdaten und Token -------------------------------------------------------------------
def _read_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def credentials() -> tuple[str, str] | None:
    cid = os.environ.get("IGDB_CLIENT_ID", "").strip()
    secret = os.environ.get("IGDB_CLIENT_SECRET", "").strip()
    if not (cid and secret):
        data = _read_config()
        cid, secret = (
            str(data.get("client_id", "")).strip(),
            str(data.get("client_secret", "")).strip(),
        )
    return (cid, secret) if cid and secret else None


def is_configured() -> bool:
    return credentials() is not None


SETUP_HINT = (
    "IGDB ist nicht eingerichtet. Lege im Projektordner die Datei igdb.json an: "
    '{"client_id": "...", "client_secret": "..."} (gratis unter https://dev.twitch.tv/console).'
)

_token: dict = {}


def _http(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def _load_token(cid: str) -> str | None:
    tok = _token or {}
    if not tok:
        tok = _read_config().get("token")
        if not isinstance(tok, dict):
            return None
    if tok.get("client_id") == cid and tok.get("expires_at", 0) > time.time() + 60:
        _token.update(tok)
        return tok.get("access_token")
    return None


def _new_token(cid: str, secret: str) -> str:
    query = urllib.parse.urlencode(
        {"client_id": cid, "client_secret": secret, "grant_type": "client_credentials"}
    )
    try:
        data = json.loads(
            _http(
                urllib.request.Request(f"{TOKEN_URL}?{query}", data=b"", method="POST")
            )
        )
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            raise IGDBError(
                "Twitch lehnt Client-ID oder Client-Secret ab. Bitte igdb.json prüfen."
            ) from exc
        raise IGDBError(f"Twitch meldet einen Fehler (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise IGDBError(
            "Twitch ist nicht erreichbar. Besteht eine Internetverbindung?"
        ) from exc
    token = data.get("access_token")
    if not token:
        raise IGDBError("Twitch hat kein Token geliefert.")
    tok = {
        "client_id": cid,
        "access_token": token,
        "expires_at": time.time() + int(data.get("expires_in", 0)),
    }
    _token.clear()
    _token.update(tok)
    try:
        CONFIG_PATH.write_text(
            json.dumps({**_read_config(), "token": tok}, indent=2), encoding="utf-8"
        )
    except OSError:
        pass  # dann wird das Token beim nächsten Start neu geholt
    return token


def query(endpoint: str, body: str) -> list[dict]:
    cred = credentials()
    if cred is None:
        raise IGDBError(SETUP_HINT)
    cid, secret = cred
    token = _load_token(cid) or _new_token(cid, secret)
    for attempt in range(4):
        request = urllib.request.Request(
            f"{API}/{endpoint}",
            data=body.encode("utf-8"),
            method="POST",
            headers={
                "Client-ID": cid,
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
        try:
            data = json.loads(_http(request))
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt == 0:
                token = _new_token(cid, secret)  # Token abgelaufen oder widerrufen
                continue
            if exc.code == 429 and attempt < 3:
                time.sleep(0.5 * (attempt + 1))
                continue
            detail = _error_detail(exc)
            raise IGDBError(
                f"IGDB meldet einen Fehler (HTTP {exc.code}){detail}."
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise IGDBError(
                "IGDB ist nicht erreichbar. Besteht eine Internetverbindung?"
            ) from exc
        except ValueError as exc:
            raise IGDBError("IGDB hat eine unlesbare Antwort geliefert.") from exc
        if not isinstance(data, list):
            raise IGDBError("IGDB hat eine unerwartete Antwort geliefert.")
        return data
    raise IGDBError(
        "IGDB ist überlastet (zu viele Anfragen). Bitte gleich nochmals versuchen."
    )


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8"))
        first = body[0] if isinstance(body, list) and body else body
        text = first.get("cause") or first.get("title") or ""
        return f": {text}" if text else ""
    except Exception:  # noqa: BLE001
        return ""


# --- Antworten -> Anfrage -------------------------------------------------------------------------
def _year_ts(year: int) -> int:
    return calendar.timegm((year, 1, 1, 0, 0, 0))


def clause_for(question_id: str, yes: bool) -> str | None:
    """IGDB-Filter für eine klare Antwort (Ja/Nein) auf eine Merkmalsfrage. None: nicht als Filter senden."""
    kind, _, value = question_id.partition(":")
    if kind in ("platform", "engine") and value.isdigit():
        field = "platforms" if kind == "platform" else "game_engines"
        return f"{field} = ({int(value)})" if yes else f"{field} != ({int(value)})"
    if kind in ("developer", "publisher"):
        return (
            f"involved_companies.company = ({int(value)})"
            if yes and value.isdigit()
            else None
        )
    if kind in ("genre", "tag"):
        feature = FEATURES.get(value)
        if feature is None:
            return None
        ids = ",".join(map(str, feature.ids))
        return f"{feature.field} = ({ids})" if yes else f"{feature.field} != ({ids})"
    if kind == "decade" and value[:4].isdigit():
        start = int(value[:4])
        a, b = _year_ts(start), _year_ts(start + 10)
        return (
            f"first_release_date >= {a} & first_release_date < {b}"
            if yes
            else f"(first_release_date < {a} | first_release_date >= {b})"
        )
    if kind == "before" and value.isdigit():
        ts = _year_ts(int(value))
        return f"first_release_date < {ts}" if yes else f"first_release_date >= {ts}"
    return None


def constraints(history) -> list[str]:
    """Filter aus allen klaren Antworten (Ja/Nein) der bisherigen Fragen; «Eher …» und «Weiss nicht» zählen nicht."""
    out: list[str] = []
    for question, answer in history:
        if answer in ("Ja", "Nein"):
            clause = clause_for(question.id, answer == "Ja")
            if clause and clause not in out:
                out.append(clause)
    return out


def build_query(clauses: list[str], limit: int = MAX_LIMIT, offset: int = 0) -> str:
    """Apicalypse-Anfrage: passende Hauptspiele, die bekanntesten zuerst."""
    where = " & ".join([BASE_FILTER, *clauses])
    return (
        f"fields {FIELDS}; where {where}; sort total_rating_count desc; "
        f"limit {min(limit, MAX_LIMIT)}; offset {offset};"
    )


# --- IGDB-Spiel -> Titel ------------------------------------------------------------------------------
def release_year(ts) -> int | None:
    if not isinstance(ts, (int, float)):
        return None
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=ts)).year


def _companies(involved, role: str) -> list[dict]:
    """Firmen mit der Rolle `role` ("developer" oder "publisher") aus involved_companies."""
    out = []
    for ic in involved or ():
        company = ic.get("company") if isinstance(ic, dict) else None
        if ic.get(
            "developer" if role == "developer" else "publisher"
        ) is True and isinstance(company, dict):
            out.append({"id": company.get("id"), "name": company.get("name", "")})
    return out


def _keywords(values) -> list[dict]:
    return [
        {"id": k.get("id"), "name": k.get("name", "")}
        for k in values or ()
        if isinstance(k, dict) and not is_meta_keyword(k.get("name", ""))
    ]


def _platforms(values) -> list[dict]:
    return [
        {"id": p.get("id"), "name": platform_name(p.get("name", ""))}
        for p in values or ()
        if isinstance(p, dict)
    ]


def _engines(values) -> list[dict]:
    return [
        {"id": e.get("id"), "name": e.get("name", "")}
        for e in values or ()
        if isinstance(e, dict) and not META_ENGINE.search(e.get("name", ""))
    ]


def game_to_title(game: dict) -> Title | None:
    """Ein IGDB-Spiel als Titel mit deutschen Merkmalen. None, wenn Name, Jahr oder Genre fehlen."""
    if not isinstance(game, dict):
        return None
    year = release_year(game.get("first_release_date"))
    if year is None:
        return None
    tags = (
        labels_for("themes", game.get("themes"))
        + labels_for("game_modes", game.get("game_modes"))
        + labels_for("player_perspectives", game.get("player_perspectives"))
    )
    involved = game.get("involved_companies")
    return title_from_dict(
        {
            "name": game.get("name", ""),
            "year": year,
            "genres": labels_for("genres", game.get("genres")),
            "tags": tags,
            "developers": _companies(involved, "developer"),
            "publishers": _companies(involved, "publisher"),
            "keywords": _keywords(game.get("keywords")),
            "platforms": _platforms(game.get("platforms")),
            "engines": _engines(game.get("game_engines")),
            "igdb_id": game.get("id", 0),
            "popularity": game.get("total_rating_count") or 0,
        }
    )


def unique_names(
    titles: list[Title], taken: dict[str, int] | None = None
) -> list[Title]:
    """Gleich heissende Spiele (z. B. «Doom» 1993 und 2016) bekommen das Jahr im Namen; Doppelte fallen weg."""
    from dataclasses import replace

    seen = dict(taken or {})  # Schlüssel -> IGDB-ID
    seen_ids = set(seen.values())
    out: list[Title] = []
    for t in titles:
        if t.igdb_id and t.igdb_id in seen_ids:
            continue
        if t.key in seen:
            t = replace(t, name=f"{t.name} ({t.year})")
            if t.key in seen:
                continue
        seen[t.key] = t.igdb_id
        seen_ids.add(t.igdb_id)
        out.append(t)
    return out


def to_titles(games: list[dict]) -> list[Title]:
    return [t for t in map(game_to_title, games) if t is not None]


# --- Abfragen ----------------------------------------------------------------------------------------
def fetch(clauses: list[str], limit: int = MAX_LIMIT) -> tuple[list[Title], str, bool]:
    """Passende Spiele zu den Filtern. Gibt (Titel, Anfrage, abgeschnitten) zurück."""
    body = build_query(clauses, limit)
    games = query("games", body)
    return to_titles(games), body, len(games) >= min(limit, MAX_LIMIT)


def search(name: str, limit: int = 5) -> list[Title]:
    """Spiele nach Namen suchen (für «An welchen Titel hast du gedacht?»)."""
    text = " ".join(name.replace('"', " ").split())
    if not text:
        return []
    return to_titles(
        query(
            "games",
            f'search "{text}"; fields {FIELDS}; where {BASE_FILTER}; limit {limit};',
        )
    )


def fetch_popular(count: int = START_POOL_SIZE) -> list[Title]:
    """Die `count` bekanntesten Spiele (nach Anzahl Bewertungen)."""
    titles: list[Title] = []
    for offset in range(0, count, MAX_LIMIT):
        games = query(
            "games",
            build_query(
                ["total_rating_count != null"], min(MAX_LIMIT, count - offset), offset
            ),
        )
        titles += to_titles(games)
        if len(games) < MAX_LIMIT:
            break
        time.sleep(0.3)  # höchstens 4 Anfragen pro Sekunde
    return unique_names(titles)


_start_pool: list[Title] = []


def start_pool() -> list[Title]:
    """Die Kandidaten zu Spielbeginn: die bekanntesten Spiele, einmal pro Programmstart aus IGDB geholt."""
    if not _start_pool:
        titles = fetch_popular()
        if len(titles) < 2:
            raise IGDBError("IGDB hat zu wenige Spiele geliefert.")
        _start_pool.extend(titles)
    return list(_start_pool)


def describe() -> str:
    return "IGDB: eingerichtet" if is_configured() else "IGDB: nicht eingerichtet"


def availability_problem() -> str | None:
    """None, wenn Zugangsdaten vorhanden sind, sonst ein Text für den Nutzer (ohne Netzwerkzugriff)."""
    return None if is_configured() else SETUP_HINT


# --- Prüfung der Merkmals-IDs ---------------------------------------------------------------------------
def check_vocab() -> list[str]:
    """Vergleicht die fest eingetragenen IDs mit den Namen in IGDB. Gibt Abweichungen zurück."""
    problems: list[str] = []
    endpoints = {
        "genres": "genres",
        "themes": "themes",
        "game_modes": "game_modes",
        "player_perspectives": "player_perspectives",
    }
    for field, endpoint in endpoints.items():
        feats = [f for f in (*GENRE_FEATURES, *TAG_FEATURES) if f.field == field]
        ids = [i for f in feats for i in f.ids]
        names = {
            row["id"]: row.get("name", "")
            for row in query(
                endpoint,
                f"fields name; where id = ({','.join(map(str, ids))}); limit 500;",
            )
        }
        for f in feats:
            got = names.get(f.ids[0])
            if got is None:
                problems.append(
                    f"{f.label}: ID {f.ids[0]} gibt es in IGDB/{endpoint} nicht."
                )
            elif got.casefold() != f.igdb_name.casefold():
                problems.append(
                    f"{f.label}: ID {f.ids[0]} heisst in IGDB «{got}» (erwartet «{f.igdb_name}»)."
                )
        time.sleep(0.3)
    types = {
        row["id"]: row.get("type", "")
        for row in query("game_types", "fields type; limit 50;")
    }
    print(
        "  Spieltypen in der Anfrage: "
        + ", ".join(f"{i}={types.get(i, '?')}" for i in GAME_TYPES)
    )
    return problems


def main(argv: list[str]) -> int:
    if not is_configured():
        print(SETUP_HINT)
        return 1
    try:
        if "--check" in argv:
            print("Prüfe Zugang und Merkmals-IDs …")
            problems = check_vocab()
            for p in problems:
                print("  PROBLEM:", p)
            print(
                "Alles stimmt."
                if not problems
                else f"{len(problems)} Abweichung(en), bitte igdb_vocab.py anpassen."
            )
            return 1 if problems else 0
        if "--search" in argv:
            name = " ".join(argv[argv.index("--search") + 1 :])
            for t in search(name):
                dev = ", ".join(c.name for c in t.developers) or "?"
                pub = ", ".join(c.name for c in t.publishers) or "?"
                print(
                    f"  {t.name} ({t.year}): {', '.join(t.genres)} | {', '.join(t.tags)} | "
                    f"Entwickler: {dev} | Publisher: {pub}"
                )
                print(
                    f"    Plattformen: {', '.join(p.name for p in t.platforms) or '-'} | "
                    f"Engine: {', '.join(e.name for e in t.engines) or '-'}"
                )
                print(f"    Keywords: {', '.join(k.name for k in t.keywords) or '-'}")
            return 0
    except IGDBError as exc:
        print("FEHLER –", exc)
        return 1
    print("Aufruf: python -m aki_data.igdb --check | --search NAME")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
