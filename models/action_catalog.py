"""Premade action/ability catalog (read-only) — the "action book".

Like the spell list and item catalog, these are bundled locally as JSON
(data/actions.json) for offline use with no rate limits. The DM grabs an entry
from this book onto a creature (it's copied into creature_actions, the way loot
copies into a creature's inventory), so picked actions can then be tweaked or
removed per-creature. Custom one-off actions are still hand-addable on the sheet.
"""
import json
import os

from models.actions import _CATEGORY_ORDER

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "actions.json")
_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(os.path.normpath(_PATH), encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def all_catalog_actions():
    """Catalog entries, ordered by category (stat-block order) then name."""
    return sorted(
        _load(),
        key=lambda a: (_CATEGORY_ORDER.get(a.get("category", ""), 99), a["name"]),
    )


def get_catalog_action(slug):
    return next((a for a in _load() if a["slug"] == slug), None)
