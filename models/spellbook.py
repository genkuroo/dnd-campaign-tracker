"""A creature's spellbook: the link between creatures and SRD spells.

The join lives in the DB (creature_spells); the spell content stays in
data/spells.json (models/spells.py). This module resolves the two together.
"""
from db import get_connection
from models.inventory import equipped_granted_spells
from models.spells import get_spell


def add_spell(creature_id, slug):
    """Add a known spell to a creature (no-op if the slug is unknown or dup)."""
    if get_spell(slug) is None:
        return
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO creature_spells (creature_id, spell_slug) VALUES (?, ?)",
            (creature_id, slug),
        )
        conn.commit()
    finally:
        conn.close()


def remove_spell(creature_id, slug):
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM creature_spells WHERE creature_id = ? AND spell_slug = ?",
            (creature_id, slug),
        )
        conn.commit()
    finally:
        conn.close()


def set_prepared(creature_id, slug, prepared):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE creature_spells SET prepared = ? WHERE creature_id = ? AND spell_slug = ?",
            (1 if prepared else 0, creature_id, slug),
        )
        conn.commit()
    finally:
        conn.close()


def set_spell_hidden(creature_id, slug, hidden):
    """Hide or unhide a known spell (declutter for the spellbook list)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE creature_spells SET hidden = ? WHERE creature_id = ? AND spell_slug = ?",
            (1 if hidden else 0, creature_id, slug),
        )
        conn.commit()
    finally:
        conn.close()


def creature_spells(creature_id):
    """Full spell dicts a creature knows (+ `prepared`/`hidden` flags), by level
    then name."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT spell_slug, prepared, hidden FROM creature_spells WHERE creature_id = ?",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        spell = get_spell(r["spell_slug"])
        if spell:  # silently skip slugs no longer in the data file
            out.append({**spell, "prepared": bool(r["prepared"]),
                        "hidden": bool(r["hidden"])})
    return sorted(out, key=lambda s: (s["level"], s["name"]))


def creature_spell_slugs(creature_id):
    return {s["slug"] for s in creature_spells(creature_id)}


def effective_spells(creature_id):
    """Known spells plus spells granted by equipped items (flagged `from_item`,
    so the UI shows them read-only and they vanish when the item comes off).
    Owned spells win over a duplicate grant."""
    spells = creature_spells(creature_id)
    have = {s["slug"] for s in spells}
    for slug, item_name in equipped_granted_spells(creature_id):
        if slug in have:
            continue
        spell = get_spell(slug)
        if spell:
            spells.append({**spell, "prepared": True, "hidden": False,
                           "from_item": item_name})
            have.add(slug)
    return sorted(spells, key=lambda s: (s["level"], s["name"]))
