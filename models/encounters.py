"""Saved encounters — named groups of monsters (Phase 5).

An encounter is a reusable roster of monsters ('Goblin x4, Hobgoblin x1') the DM
assembles ahead of time and later loads into the combat tracker (Phase 6). Each
member is a creature_id + quantity, so the same bestiary stat block backs every
copy of a monster in the fight (the creature engine, reused — CLAUDE.md).
"""
from db import get_connection


def create_encounter(name):
    """Create a named encounter; returns its id, or None if the name is blank."""
    name = (name or "").strip()
    if not name:
        return None
    conn = get_connection()
    try:
        cur = conn.execute("INSERT INTO encounters (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_encounters():
    """All encounters (newest first) with a member count + total creature tally."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT e.*, "
            "  COUNT(m.id) AS member_count, "
            "  COALESCE(SUM(m.quantity), 0) AS total_creatures "
            "FROM encounters e "
            "LEFT JOIN encounter_members m ON m.encounter_id = e.id "
            "GROUP BY e.id ORDER BY e.created_at DESC"
        ).fetchall()
    finally:
        conn.close()


def get_encounter(encounter_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM encounters WHERE id = ?", (encounter_id,)
        ).fetchone()
    finally:
        conn.close()


def rename_encounter(encounter_id, name):
    name = (name or "").strip()
    if not name:
        return
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE encounters SET name = ? WHERE id = ?", (name, encounter_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_encounter(encounter_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM encounters WHERE id = ?", (encounter_id,))
        conn.commit()
    finally:
        conn.close()


def encounter_members(encounter_id):
    """Members resolved against their creature, with the stats the combat tracker
    will want (HP/AC). Ordered by creature name."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT m.id, m.creature_id, m.quantity, "
            "  c.name, c.max_hp, c.armor_class, c.kind "
            "FROM encounter_members m "
            "JOIN creatures c ON c.id = m.creature_id "
            "WHERE m.encounter_id = ? "
            "ORDER BY c.name COLLATE NOCASE",
            (encounter_id,),
        ).fetchall()
    finally:
        conn.close()


def add_member(encounter_id, creature_id, quantity=1):
    """Add a monster to an encounter. If it's already a member, bump the quantity
    instead of adding a duplicate row."""
    quantity = max(1, int(quantity or 1))
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id, quantity FROM encounter_members "
            "WHERE encounter_id = ? AND creature_id = ?",
            (encounter_id, creature_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE encounter_members SET quantity = ? WHERE id = ?",
                (existing["quantity"] + quantity, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO encounter_members (encounter_id, creature_id, quantity) "
                "VALUES (?, ?, ?)",
                (encounter_id, creature_id, quantity),
            )
        conn.commit()
    finally:
        conn.close()


def set_member_quantity(member_id, quantity):
    """Set a member's quantity; drop the member entirely if it falls below 1."""
    quantity = int(quantity or 0)
    conn = get_connection()
    try:
        if quantity < 1:
            conn.execute("DELETE FROM encounter_members WHERE id = ?", (member_id,))
        else:
            conn.execute(
                "UPDATE encounter_members SET quantity = ? WHERE id = ?",
                (quantity, member_id),
            )
        conn.commit()
    finally:
        conn.close()


def remove_member(member_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM encounter_members WHERE id = ?", (member_id,))
        conn.commit()
    finally:
        conn.close()
