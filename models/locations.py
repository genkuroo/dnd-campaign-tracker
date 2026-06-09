"""Locations — the first typed world entity beyond NPCs (Phase 9a).

A location is a named place in the world (a region, settlement, dungeon…). It
carries the same `visibility` fog-of-war spine as a creature: 'hidden' until the
party discovers it, then the DM reveals it ('visible'). Locations can nest via
`parent_id` (a region containing a city containing an inn). The sidebar, blog
mentions, and future map markers all point back at these rows.
"""
from db import get_connection

# Loose set of place kinds (label only — not enforced). First is the default.
LOCATION_KINDS = [
    ("place", "Place"),
    ("region", "Region"),
    ("settlement", "Settlement"),
    ("dungeon", "Dungeon"),
    ("landmark", "Landmark"),
]
_KIND_LABELS = dict(LOCATION_KINDS)


def kind_label(kind):
    """Human label for a location kind ('settlement' → 'Settlement')."""
    return _KIND_LABELS.get(kind or "place", "Place")


def list_locations():
    """Every location, name-ordered (DM view)."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM locations ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def visible_locations():
    """Only the locations players have discovered (visibility='visible')."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM locations WHERE visibility = 'visible' "
            "ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def get_location(location_id):
    if not location_id:
        return None
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
    finally:
        conn.close()


def create_location(data):
    """Insert a location from a cleaned data dict. Returns the new id (or None if
    no name was given)."""
    fields = _clean(data)
    if not fields.get("name"):
        return None
    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    conn = get_connection()
    try:
        cur = conn.execute(
            f"INSERT INTO locations ({', '.join(cols)}) VALUES ({placeholders})",
            [fields[c] for c in cols],
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_location(location_id, data):
    fields = _clean(data)
    if not fields:
        return
    assignments = ", ".join(f"{col} = ?" for col in fields)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE locations SET {assignments} WHERE id = ?",
            [*fields.values(), location_id],
        )
        conn.commit()
    finally:
        conn.close()


def set_location_visibility(location_id, visibility):
    """Reveal/hide a location to players (the live discovery toggle)."""
    visibility = "visible" if visibility == "visible" else "hidden"
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE locations SET visibility = ? WHERE id = ?",
            (visibility, location_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_location(location_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
        conn.commit()
    finally:
        conn.close()


def creatures_at(location_id):
    """Creatures (NPCs/PCs) whose home is this location. Unfiltered — the caller
    applies the per-viewer visibility filter."""
    if not location_id:
        return []
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creatures WHERE location_id = ? "
            "ORDER BY kind, name COLLATE NOCASE",
            (location_id,),
        ).fetchall()
    finally:
        conn.close()


def children_of(location_id):
    """Sub-locations nested under this one."""
    if not location_id:
        return []
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM locations WHERE parent_id = ? ORDER BY name COLLATE NOCASE",
            (location_id,),
        ).fetchall()
    finally:
        conn.close()


_TEXT_FIELDS = ["name", "kind", "description", "visibility"]
_INT_FIELDS = ["parent_id"]


def _clean(data):
    """Coerce a form dict into safe location column values."""
    fields = {}
    for col in _TEXT_FIELDS:
        if col in data:
            fields[col] = (data.get(col) or "").strip()
    if "visibility" in fields and fields["visibility"] != "visible":
        fields["visibility"] = "hidden"
    for col in _INT_FIELDS:
        if col in data and str(data.get(col)).strip() != "":
            fields[col] = int(data[col])
    # parent_id 0/empty means "no parent" → NULL (a 0 would violate the self-FK).
    if "parent_id" in fields and fields["parent_id"] <= 0:
        fields["parent_id"] = None
    return fields
