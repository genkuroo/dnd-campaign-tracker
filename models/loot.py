"""Areas + their loot pools, and handing loot to characters.

An area is a named location with its own loot pool. The DM spawns premade or
custom items into the current area; loot persists per-area (switching areas
never deletes loot). Giving a loot item to a creature copies it into that
creature's inventory and removes it from the pool.
"""
from db import get_connection
from models.inventory import EQUIP_SLOTS, add_item as add_creature_item

_CURRENT_KEY = "current_area_id"


# --- Areas ----------------------------------------------------------------

def list_areas():
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM areas ORDER BY created_at, id").fetchall()
    finally:
        conn.close()


def get_area(area_id):
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM areas WHERE id = ?", (area_id,)).fetchone()
    finally:
        conn.close()


def create_area(name):
    name = (name or "").strip()
    if not name:
        return None
    conn = get_connection()
    try:
        cur = conn.execute("INSERT INTO areas (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def delete_area(area_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM areas WHERE id = ?", (area_id,))  # cascades loot
        conn.commit()
    finally:
        conn.close()


def current_area_id():
    """The selected area, falling back to the earliest one; None if no areas."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (_CURRENT_KEY,)
        ).fetchone()
        aid = int(row["value"]) if row and row["value"] else None
        if aid is not None and conn.execute(
            "SELECT 1 FROM areas WHERE id = ?", (aid,)
        ).fetchone() is None:
            aid = None
        if aid is None:
            first = conn.execute("SELECT id FROM areas ORDER BY created_at, id LIMIT 1").fetchone()
            aid = first["id"] if first else None
        return aid
    finally:
        conn.close()


def set_current_area(area_id):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_CURRENT_KEY, str(area_id)),
        )
        conn.commit()
    finally:
        conn.close()


# --- Loot pool ------------------------------------------------------------

def area_loot(area_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM loot_items WHERE area_id = ? ORDER BY added_at DESC, id DESC",
            (area_id,),
        ).fetchall()
    finally:
        conn.close()


def get_loot(loot_id):
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM loot_items WHERE id = ?", (loot_id,)).fetchone()
    finally:
        conn.close()


def add_loot(area_id, name, quantity=1, description="", slot="", hands=1):
    name = (name or "").strip()
    if not name:
        return None
    if slot not in EQUIP_SLOTS:
        slot = ""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO loot_items (area_id, name, quantity, description, slot, hands) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (area_id, name, max(1, int(quantity or 1)), (description or "").strip(),
             slot, 2 if int(hands or 1) == 2 else 1),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def remove_loot(loot_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM loot_items WHERE id = ?", (loot_id,))
        conn.commit()
    finally:
        conn.close()


def clear_area_loot(area_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM loot_items WHERE area_id = ?", (area_id,))
        conn.commit()
    finally:
        conn.close()


def give_loot(loot_id, creature_id):
    """Move a loot item into a creature's inventory (copy, then drop from pool)."""
    loot = get_loot(loot_id)
    if loot is None:
        return False
    add_creature_item(creature_id, loot["name"], loot["quantity"],
                      loot["description"], slot=loot["slot"], hands=loot["hands"])
    remove_loot(loot_id)
    return True
