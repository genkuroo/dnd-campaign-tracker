"""Persistence for the dice roller's roll history."""
from db import get_connection


def add_roll(result, label="", user_id=None):
    """Record a roll. `result` is the dict returned by the dice engine; `user_id`
    is the roller (so the shared log can tint by player)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO rolls (expression, total, detail, label, user_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (result["expression"], result["total"], result["detail"], label, user_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def recent_rolls(limit=20):
    """Recent rolls, newest first, joined to the roller's name + colour."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT r.*, u.username AS roller, u.color AS roller_color "
            "FROM rolls r LEFT JOIN users u ON u.id = r.user_id "
            "ORDER BY r.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def delete_roll(roll_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM rolls WHERE id = ?", (roll_id,))
        conn.commit()
    finally:
        conn.close()


def clear_rolls():
    conn = get_connection()
    try:
        conn.execute("DELETE FROM rolls")
        conn.commit()
    finally:
        conn.close()
