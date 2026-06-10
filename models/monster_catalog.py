"""SRD monster catalog — a bundled set of standard 5e monsters the DM can import
into the Bestiary in one click.

A monster is just a creature (`kind='monster'`), so importing copies a catalog
stat block into a new creature (the same "catalog → grab" pattern as loot items,
the action book, and summons) and attaches its actions. Import is **idempotent**:
a monster whose name already exists in the Bestiary is skipped, so the DM can
re-run it after updates without creating duplicates.

Imported monsters default to **visibility='hidden'** — they live in the DM's
library until the DM reveals each one to players (the level-1 monster fog of war).

Stat blocks are from the SRD 5.1 (CC-BY-4.0); see data/monsters.json `_attribution`.
"""
import json
import os

from db import get_connection
from models.actions import add_action
from models.creature import create_creature

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "monsters.json")
_cache = None

# Creature columns a catalog entry may carry into the new creature (the rest —
# slug / actions — is handled separately). Mirrors summons._STAT_FIELDS, widened
# with the world-flavor + reference fields a monster wants.
_STAT_FIELDS = [
    "name", "kind", "avatar", "notes", "armor_class", "max_hp", "speed", "cr",
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
    "resistances", "immunities", "vulnerabilities",
    "alignment", "disposition", "languages",
]


def _load():
    global _cache
    if _cache is None:
        with open(os.path.normpath(_PATH), encoding="utf-8") as f:
            _cache = json.load(f)["monsters"]
    return _cache


def all_monsters():
    """Catalog entries, by challenge rating then name."""
    return sorted(_load(), key=lambda m: (m.get("cr", 0), m["name"]))


def catalog_size():
    return len(_load())


def _existing_monster_names():
    """Lowercased names of monsters already in the Bestiary, to skip duplicates."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM creatures WHERE kind = 'monster'"
        ).fetchall()
    finally:
        conn.close()
    return {(r["name"] or "").strip().lower() for r in rows}


def import_missing():
    """Insert every catalog monster not already present (by name). Idempotent.

    Returns {'added': int, 'skipped': int} so the route can report what happened.
    """
    existing = _existing_monster_names()
    added = skipped = 0
    for entry in _load():
        if entry["name"].strip().lower() in existing:
            skipped += 1
            continue
        data = {k: entry[k] for k in _STAT_FIELDS if k in entry}
        data.setdefault("kind", "monster")
        data["visibility"] = "hidden"   # DM's library; reveal per the fog of war
        new_id = create_creature(data)
        for a in entry.get("actions", []):
            add_action(new_id, a.get("name", ""), a.get("description", ""),
                       a.get("dice", ""), a.get("category", "action"))
        existing.add(entry["name"].strip().lower())
        added += 1
    return {"added": added, "skipped": skipped}
