"""Summons — a bundled catalog players spawn under their control (Phase 12b).

A summon (familiar, conjured beast) is just a creature (`kind='monster'`) the
summoner controls (the 12a `controlled_by` spine), flagged `is_summon=1` so it's
kept out of the DM's Bestiary and is player-dismissable. Spawning copies a catalog
stat block into a new creature (the way loot copies an item, or the action book
copies an action); Dismiss deletes it. Stat blocks are SRD 5.1 (CC-BY-4.0).
"""
import json
import os

from db import get_connection
from models.creature import create_creature, get_creature
from models.actions import add_action

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "summons.json")
_cache = None

# Creature columns a catalog entry may carry into the new creature (the rest of
# the entry — slug/actions — is handled separately).
_STAT_FIELDS = [
    "name", "kind", "avatar", "notes", "armor_class", "max_hp", "speed", "cr",
    "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma",
    "resistances", "immunities", "vulnerabilities",
]


def _load():
    global _cache
    if _cache is None:
        with open(os.path.normpath(_PATH), encoding="utf-8") as f:
            _cache = json.load(f)["summons"]
    return _cache


def all_summons():
    """Catalog entries, by challenge rating then name."""
    return sorted(_load(), key=lambda s: (s.get("cr", 0), s["name"]))


def get_summon(slug):
    return next((s for s in _load() if s["slug"] == slug), None)


def spawn(slug, user_id):
    """Spawn a catalog summon under `user_id`'s control. Returns the new creature
    id, or None if the slug is unknown."""
    entry = get_summon(slug)
    if not entry:
        return None
    data = {k: entry[k] for k in _STAT_FIELDS if k in entry}
    data.setdefault("kind", "monster")
    new_id = create_creature(data)
    # Mark it a controlled summon (kept out of _clean / the generic form path).
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE creatures SET controlled_by = ?, is_summon = 1 WHERE id = ?",
            (int(user_id or 0), new_id),
        )
        conn.commit()
    finally:
        conn.close()
    for a in entry.get("actions", []):
        add_action(new_id, a.get("name", ""), a.get("description", ""),
                   a.get("dice", ""), a.get("category", "action"))
    return new_id


def is_summon(creature_id):
    """True if the creature is a spawned summon (player-dismissable)."""
    c = get_creature(creature_id)
    return bool(c) and bool(c["is_summon"])
