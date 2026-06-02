"""SRD spell reference data (read-only).

Spells are bundled locally as JSON (data/spells.json) rather than fetched from an
external API: it works offline, has no rate limits, and survives hosting. The
content is from the D&D 5e SRD under CC-BY-4.0 (see README attribution). The set
is intentionally small to start; the full SRD list can drop into the same shape.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "spells.json")
_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(os.path.normpath(_PATH), encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def all_spells():
    """Every spell, ordered by level then name."""
    return sorted(_load(), key=lambda s: (s["level"], s["name"]))


def get_spell(slug):
    return next((s for s in _load() if s["slug"] == slug), None)


def search_spells(query):
    """Filter by name or school (case-insensitive); empty query returns all."""
    q = (query or "").strip().lower()
    spells = all_spells()
    if not q:
        return spells
    return [s for s in spells if q in s["name"].lower() or q in s["school"].lower()]


def level_label(level):
    """'Cantrip' or '1st-level', '2nd-level', ... for display."""
    if level == 0:
        return "Cantrip"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(level if level < 20 else 0, "th")
    if 11 <= (level % 100) <= 13:
        suffix = "th"
    return f"{level}{suffix}-level"
