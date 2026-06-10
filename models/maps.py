"""Maps — uploaded background images with overlay markers (Phase 10).

A map is a named image the DM places interactable markers on (markers land in
10b). Like locations/factions it carries the `visibility` fog-of-war spine and
defaults to 'hidden' (a map is revealed once the party has explored it). A map
may optionally link to a location (`location_id`, 0 = none) so a place and its
map cross-reference each other.

A map may also carry a persisted **grid overlay** (10d): `grid_enabled` plus a
cell `grid_size`, `grid_color`/`grid_opacity`, and `grid_offset_x`/`_y` — all
measured in SOURCE-IMAGE pixels so the grid stays aligned to the map content at
any display size or zoom. (Zoom/pan are per-view-session and never stored.)

Mirrors the locations/factions CRUD + `_clean` pattern.
"""
import re

from db import get_connection

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def list_maps():
    """Every map, name-ordered (DM view)."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM maps ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def visible_maps():
    """Only the maps players have discovered (visibility='visible')."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM maps WHERE visibility = 'visible' "
            "ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def get_map(map_id):
    if not map_id:
        return None
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM maps WHERE id = ?", (map_id,)
        ).fetchone()
    finally:
        conn.close()


def maps_for_location(location_id):
    """Maps linked to a given location (for the location-detail cross-link)."""
    if not location_id:
        return []
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM maps WHERE location_id = ? ORDER BY name COLLATE NOCASE",
            (location_id,),
        ).fetchall()
    finally:
        conn.close()


def create_map(data):
    """Insert a map from a cleaned data dict. Returns the new id (or None if no
    name was given). The background image is uploaded separately (needs the id)."""
    fields = _clean(data)
    if not fields.get("name"):
        return None
    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    conn = get_connection()
    try:
        cur = conn.execute(
            f"INSERT INTO maps ({', '.join(cols)}) VALUES ({placeholders})",
            [fields[c] for c in cols],
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_map(map_id, data):
    fields = _clean(data)
    if not fields:
        return
    assignments = ", ".join(f"{col} = ?" for col in fields)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE maps SET {assignments} WHERE id = ?",
            [*fields.values(), map_id],
        )
        conn.commit()
    finally:
        conn.close()


def set_map_image(map_id, image):
    """Record the uploaded background URL (or '' to clear)."""
    conn = get_connection()
    try:
        conn.execute("UPDATE maps SET image = ? WHERE id = ?", (image, map_id))
        conn.commit()
    finally:
        conn.close()


def set_map_visibility(map_id, visibility):
    """Reveal/hide a map to players (the live discovery toggle)."""
    visibility = "visible" if visibility == "visible" else "hidden"
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE maps SET visibility = ? WHERE id = ?", (visibility, map_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_map(map_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM maps WHERE id = ?", (map_id,))
        conn.commit()
    finally:
        conn.close()


# `image` is written only via set_map_image (mirrors how `avatar` stays out of
# the generic create/update path), so it's not in the cleanable field set.
_TEXT_FIELDS = ["name", "description", "visibility"]
_INT_FIELDS = ["location_id", "grid_size", "grid_opacity",
               "grid_offset_x", "grid_offset_y"]


def _clean(data):
    """Coerce a form dict into safe map column values."""
    fields = {}
    for col in _TEXT_FIELDS:
        if col in data:
            fields[col] = (data.get(col) or "").strip()
    if "visibility" in fields and fields["visibility"] != "visible":
        fields["visibility"] = "hidden"
    for col in _INT_FIELDS:
        if col in data and str(data.get(col)).strip() != "":
            try:
                fields[col] = int(float(data[col]))
            except (TypeError, ValueError):
                pass
    if "location_id" in fields and fields["location_id"] < 0:
        fields["location_id"] = 0
    # Grid cell size must stay positive; opacity is a 0..100 percentage.
    if "grid_size" in fields:
        fields["grid_size"] = max(2, fields["grid_size"])
    if "grid_opacity" in fields:
        fields["grid_opacity"] = max(0, min(100, fields["grid_opacity"]))
    # Grid colour renders into a canvas fillStyle / a style attr — validate hex.
    if "grid_color" in data:
        color = (data.get("grid_color") or "").strip()
        fields["grid_color"] = color if _HEX_COLOR.match(color) else "#000000"
    # `grid_enabled` is a checkbox: only coerce it on a real map-form submit
    # (flagged by the hidden `grid_present` field) so partial updates that don't
    # carry the grid controls leave the stored value untouched.
    if data.get("grid_present"):
        fields["grid_enabled"] = 1 if data.get("grid_enabled") else 0
    return fields
