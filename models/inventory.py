"""A creature's inventory of items (loot, gear, consumables)."""
from db import get_connection


def list_items(creature_id):
    """A creature's items: equipped first, then by name."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creature_items WHERE creature_id = ? "
            "ORDER BY equipped DESC, name COLLATE NOCASE",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()


def get_item(item_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creature_items WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        conn.close()


def add_item(creature_id, name, quantity=1, description=""):
    name = (name or "").strip()
    if not name:
        return None
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO creature_items (creature_id, name, quantity, description) "
            "VALUES (?, ?, ?, ?)",
            (creature_id, name, max(1, int(quantity or 1)), (description or "").strip()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def remove_item(item_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM creature_items WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()


def adjust_quantity(item_id, delta):
    """Nudge quantity by delta, clamped to a minimum of 1."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE creature_items SET quantity = MAX(1, quantity + ?) WHERE id = ?",
            (int(delta), item_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_equipped(item_id, equipped):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE creature_items SET equipped = ? WHERE id = ?",
            (1 if equipped else 0, item_id),
        )
        conn.commit()
    finally:
        conn.close()
