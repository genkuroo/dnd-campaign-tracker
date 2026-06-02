"""Premade item catalog (read-only), bundled in data/items.json.

The DM spawns these into an area's loot pool. Same local-bundle approach as the
spell list, for the same reasons (offline, no rate limits).
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "items.json")
_cache = None

# Order categories sensibly rather than alphabetically.
_CATEGORY_ORDER = ["Weapon", "Armor", "Accessory", "Consumable", "Gear"]


def _load():
    global _cache
    if _cache is None:
        with open(os.path.normpath(_PATH), encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def all_item_defs():
    """Catalog entries, grouped sensibly by category then name."""
    def key(i):
        cat = i.get("category", "")
        rank = _CATEGORY_ORDER.index(cat) if cat in _CATEGORY_ORDER else len(_CATEGORY_ORDER)
        return (rank, i["name"])
    return sorted(_load(), key=key)


def get_item_def(slug):
    return next((i for i in _load() if i["slug"] == slug), None)
