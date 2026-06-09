"""Factions — a typed world entity for organizations/groups (Phase 9a).

A faction is a named group (a guild, cult, noble house, kingdom). It carries the
same `visibility` fog-of-war spine as a creature/location and reuses the creature
`disposition` spectrum (how the group regards the party). Creatures point at a
faction via `creatures.faction_id`, so a faction's "members" are just the
creatures that name it.
"""
from db import get_connection
from models.creature import DISPOSITIONS  # reuse the hostile..allied spectrum


def list_factions():
    """Every faction, name-ordered (DM view)."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM factions ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def visible_factions():
    """Only the factions players have discovered (visibility='visible')."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM factions WHERE visibility = 'visible' "
            "ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def get_faction(faction_id):
    if not faction_id:
        return None
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM factions WHERE id = ?", (faction_id,)
        ).fetchone()
    finally:
        conn.close()


def create_faction(data):
    fields = _clean(data)
    if not fields.get("name"):
        return None
    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    conn = get_connection()
    try:
        cur = conn.execute(
            f"INSERT INTO factions ({', '.join(cols)}) VALUES ({placeholders})",
            [fields[c] for c in cols],
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_faction(faction_id, data):
    fields = _clean(data)
    if not fields:
        return
    assignments = ", ".join(f"{col} = ?" for col in fields)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE factions SET {assignments} WHERE id = ?",
            [*fields.values(), faction_id],
        )
        conn.commit()
    finally:
        conn.close()


def set_faction_visibility(faction_id, visibility):
    """Reveal/hide a faction to players (the live discovery toggle)."""
    visibility = "visible" if visibility == "visible" else "hidden"
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE factions SET visibility = ? WHERE id = ?",
            (visibility, faction_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_faction(faction_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM factions WHERE id = ?", (faction_id,))
        conn.commit()
    finally:
        conn.close()


def members_of(faction_id):
    """Creatures belonging to this faction. Unfiltered — the caller applies the
    per-viewer visibility filter."""
    if not faction_id:
        return []
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creatures WHERE faction_id = ? "
            "ORDER BY kind, name COLLATE NOCASE",
            (faction_id,),
        ).fetchall()
    finally:
        conn.close()


_TEXT_FIELDS = ["name", "description", "disposition", "visibility"]


def _clean(data):
    """Coerce a form dict into safe faction column values."""
    fields = {}
    for col in _TEXT_FIELDS:
        if col in data:
            fields[col] = (data.get(col) or "").strip()
    if "visibility" in fields and fields["visibility"] != "visible":
        fields["visibility"] = "hidden"
    if "disposition" in fields and fields["disposition"] not in DISPOSITIONS:
        fields["disposition"] = "neutral"
    return fields
