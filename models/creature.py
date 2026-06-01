"""The creature engine — data access + stat-block math.

A creature is the shared model behind both player characters and (from Phase 5)
monsters. This module owns the ability-modifier rule and the CRUD used by the
Character Sheet tab.
"""
from db import get_connection

# (column, short label) in canonical D&D order.
ABILITIES = [
    ("strength", "STR"),
    ("dexterity", "DEX"),
    ("constitution", "CON"),
    ("intelligence", "INT"),
    ("wisdom", "WIS"),
    ("charisma", "CHA"),
]

# Fields a creature form may set, with the type to coerce each to.
_INT_FIELDS = [
    "level", "max_hp", "current_hp", "armor_class",
    *[col for col, _ in ABILITIES],
]
_TEXT_FIELDS = [
    "name", "kind", "player_name",
    "resistances", "immunities", "vulnerabilities", "notes", "visibility",
]


def ability_modifier(score):
    """D&D 5e rule: modifier = floor((score - 10) / 2)."""
    return (int(score) - 10) // 2


def format_modifier(mod):
    """Render a modifier the way sheets do: +3, -1, +0."""
    return f"+{mod}" if mod >= 0 else str(mod)


def list_characters():
    """All player characters (kind='pc'), newest first."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creatures WHERE kind = 'pc' ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()


def get_creature(creature_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creatures WHERE id = ?", (creature_id,)
        ).fetchone()
    finally:
        conn.close()


def _clean(data):
    """Coerce a form dict into safe column values."""
    fields = {}
    for col in _TEXT_FIELDS:
        if col in data:
            fields[col] = (data.get(col) or "").strip()
    for col in _INT_FIELDS:
        if col in data and str(data.get(col)).strip() != "":
            fields[col] = int(data[col])
    return fields


def create_creature(data):
    fields = _clean(data)
    fields.setdefault("kind", "pc")
    # Default current HP to full when not given.
    if "current_hp" not in fields and "max_hp" in fields:
        fields["current_hp"] = fields["max_hp"]
    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    conn = get_connection()
    try:
        cur = conn.execute(
            f"INSERT INTO creatures ({', '.join(cols)}) VALUES ({placeholders})",
            [fields[c] for c in cols],
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_creature(creature_id, data):
    fields = _clean(data)
    if not fields:
        return
    assignments = ", ".join(f"{col} = ?" for col in fields)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE creatures SET {assignments} WHERE id = ?",
            [*fields.values(), creature_id],
        )
        conn.commit()
    finally:
        conn.close()


def delete_creature(creature_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM creatures WHERE id = ?", (creature_id,))
        conn.commit()
    finally:
        conn.close()
