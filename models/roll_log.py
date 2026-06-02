"""Persistence for the dice roller's roll history."""
from db import get_connection


def add_roll(result, label=""):
    """Record a roll. `result` is the dict returned by the dice engine."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO rolls (expression, total, detail, label) VALUES (?, ?, ?, ?)",
            (result["expression"], result["total"], result["detail"], label),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def recent_rolls(limit=20):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM rolls ORDER BY id DESC LIMIT ?", (limit,)
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
