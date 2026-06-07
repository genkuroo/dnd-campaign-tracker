"""A creature's free-form actions & abilities (Phase 5).

Deliberately separate from the spellbook (CLAUDE.md): spells are SRD-backed with
level/components, whereas these are hand-written entries — Multiattack, Rage,
breath weapons, legendary actions, passive traits — a name + description with an
optional dice expression. The data lives entirely in the DB (creature_actions),
so unlike spells there is no JSON reference file to resolve against.

The same creature-attached pattern as models/spellbook, so it works for PCs,
NPCs, and monsters with no special-casing.
"""
from db import get_connection

# Action categories, ordered the way a stat block reads (passive traits first,
# legendary actions last). (value, label); `value` is what's stored.
CATEGORIES = [
    ("trait", "Trait"),
    ("action", "Action"),
    ("bonus", "Bonus Action"),
    ("reaction", "Reaction"),
    ("legendary", "Legendary Action"),
]
CATEGORY_LABELS = dict(CATEGORIES)
_CATEGORY_ORDER = {value: i for i, (value, _) in enumerate(CATEGORIES)}
_VALID_CATEGORIES = set(_CATEGORY_ORDER)


def category_label(value):
    return CATEGORY_LABELS.get(value, value)


def add_action(creature_id, name, description="", dice="", category="action",
               source=""):
    """Add an action to a creature. Returns the new id, or None if unnamed.
    `source` marks provenance: '' = hand-added/grabbed, 'class' = auto-granted from
    a class feature (see grant_class_actions)."""
    name = (name or "").strip()
    if not name:
        return None
    if category not in _VALID_CATEGORIES:
        category = "action"
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO creature_actions"
            " (creature_id, name, category, dice, description, source)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (creature_id, name, category, (dice or "").strip(),
             (description or "").strip(), source),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def clear_class_actions(creature_id):
    """Remove a creature's class-granted actions (source='class'), leaving the
    hand-added ones (source='') untouched."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM creature_actions WHERE creature_id = ? AND source = 'class'",
            (creature_id,),
        )
        conn.commit()
    finally:
        conn.close()


def set_action_hidden(action_id, hidden):
    """Hide or unhide an action (a soft-delete / declutter that survives class
    re-syncs, unlike a real delete of an auto-granted action)."""
    conn = get_connection()
    try:
        conn.execute("UPDATE creature_actions SET hidden = ? WHERE id = ?",
                     (1 if hidden else 0, action_id))
        conn.commit()
    finally:
        conn.close()


def grant_class_actions(creature_id, slug, level):
    """Sync a creature's class-granted actions to its class + level by reconciling
    (not wiping): keep the class actions still desired — preserving each one's
    `hidden` flag and any per-creature edits — drop the ones no longer granted, and
    add the newly unlocked ones (Rage, Second Wind, Sneak Attack…). Idempotent and
    safe on class change / level-up; hand-added actions are never touched. A falsy
    `slug` clears all class actions (the creature is classless)."""
    from models.classes import grantable_class_features  # local: avoid import cycle
    desired = {f["name"]: f for f in (grantable_class_features(slug, level) if slug else [])}
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id, name FROM creature_actions"
            " WHERE creature_id = ? AND source = 'class'",
            (creature_id,),
        ).fetchall()
        existing_names = {r["name"] for r in existing}
        stale = [(r["id"],) for r in existing if r["name"] not in desired]
        if stale:
            conn.executemany("DELETE FROM creature_actions WHERE id = ?", stale)
        new_rows = [
            (creature_id, f["name"], f.get("category", "action") if f.get("category") in _VALID_CATEGORIES else "action",
             (f.get("dice", "") or "").strip(), (f.get("description", "") or "").strip())
            for name, f in desired.items() if name not in existing_names
        ]
        if new_rows:
            conn.executemany(
                "INSERT INTO creature_actions"
                " (creature_id, name, category, dice, description, source)"
                " VALUES (?, ?, ?, ?, ?, 'class')",
                new_rows,
            )
        conn.commit()
    finally:
        conn.close()


def get_action(action_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creature_actions WHERE id = ?", (action_id,)
        ).fetchone()
    finally:
        conn.close()


def remove_action(action_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM creature_actions WHERE id = ?", (action_id,))
        conn.commit()
    finally:
        conn.close()


def list_actions(creature_id):
    """A creature's actions, ordered by category (stat-block order) then name."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM creature_actions WHERE creature_id = ?", (creature_id,)
        ).fetchall()
    finally:
        conn.close()
    return sorted(
        rows, key=lambda r: (_CATEGORY_ORDER.get(r["category"], 99), r["name"].lower())
    )
