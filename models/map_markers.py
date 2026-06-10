"""Map markers — interactable overlay pins on a map (Phase 10b).

A marker lives at fractional coords (`x`/`y` in 0..1, resolution-independent) on
a map. It optionally points at a world entity via the same polymorphic (type, id)
pattern as note_mentions — a creature (NPC/PC), location, faction, or another map
(a 'map' marker drills global→local) — or carries a free-text `label` + emoji
`icon`. Like every entity it has the `visibility` fog-of-war spine (10c). The
entity_id has no FK; a dangling reference is skipped when resolved for display.
"""
from db import get_connection

ENTITY_TYPES = {"creature", "location", "faction", "map"}


def list_markers(map_id):
    """Every marker on a map (DM view). The caller resolves + visibility-filters."""
    if not map_id:
        return []
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM map_markers WHERE map_id = ? ORDER BY id", (map_id,)
        ).fetchall()
    finally:
        conn.close()


def get_marker(marker_id):
    if not marker_id:
        return None
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM map_markers WHERE id = ?", (marker_id,)
        ).fetchone()
    finally:
        conn.close()


def create_marker(map_id, data):
    """Insert a marker on a map from a cleaned data dict. Returns the new id."""
    fields = _clean(data)
    fields["map_id"] = map_id
    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    conn = get_connection()
    try:
        cur = conn.execute(
            f"INSERT INTO map_markers ({', '.join(cols)}) VALUES ({placeholders})",
            [fields[c] for c in cols],
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_marker(marker_id, data):
    fields = _clean(data)
    if not fields:
        return
    assignments = ", ".join(f"{col} = ?" for col in fields)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE map_markers SET {assignments} WHERE id = ?",
            [*fields.values(), marker_id],
        )
        conn.commit()
    finally:
        conn.close()


def move_marker(marker_id, x, y):
    """Reposition a marker (drag-and-drop). Coords clamped to [0, 1]."""
    x = _clamp01(x)
    y = _clamp01(y)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE map_markers SET x = ?, y = ? WHERE id = ?", (x, y, marker_id)
        )
        conn.commit()
    finally:
        conn.close()


def set_marker_visibility(marker_id, visibility):
    """Reveal/hide a single marker to players (10c fog of war)."""
    visibility = "visible" if visibility == "visible" else "hidden"
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE map_markers SET visibility = ? WHERE id = ?",
            (visibility, marker_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_marker(marker_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM map_markers WHERE id = ?", (marker_id,))
        conn.commit()
    finally:
        conn.close()


def _clamp01(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))


_TEXT_FIELDS = ["entity_type", "label", "icon", "visibility"]


def _clean(data):
    """Coerce a form dict into safe marker column values."""
    fields = {}
    for col in _TEXT_FIELDS:
        if col in data:
            fields[col] = (data.get(col) or "").strip()
    # entity_type must be one of the known kinds, else a free label pin.
    if "entity_type" in fields and fields["entity_type"] not in ENTITY_TYPES:
        fields["entity_type"] = ""
    if "visibility" in fields and fields["visibility"] != "visible":
        fields["visibility"] = "hidden"
    if "entity_id" in data and str(data.get("entity_id")).strip() != "":
        try:
            fields["entity_id"] = int(data["entity_id"])
        except (TypeError, ValueError):
            fields["entity_id"] = 0
    # A free label pin (no entity) shouldn't carry a stray entity_id.
    if fields.get("entity_type", "") == "":
        if "entity_type" in fields:
            fields["entity_id"] = 0
    for col in ("x", "y"):
        if col in data and str(data.get(col)).strip() != "":
            fields[col] = _clamp01(data[col])
    return fields
