"""Titelsuche im aktuellen Pool"""

from __future__ import annotations

import difflib

from .models import Title


# sucht im Katalog nach dem Spiel
def search(titles: list[Title], text: str, limit: int = 5) -> list[Title]:
    query = " ".join(text.casefold().split())
    if not query:
        return []
    exact = [t for t in titles if t.key == query]
    contains = [t for t in titles if query in t.key and t not in exact]
    contains.sort(key=lambda t: (len(t.key), t.key))
    found = exact + contains
    if len(found) < limit:
        names = {t.key: t for t in titles}
        for key in difflib.get_close_matches(query, list(names), n=limit, cutoff=0.6):
            if names[key] not in found:
                found.append(names[key])
    return found[:limit]
