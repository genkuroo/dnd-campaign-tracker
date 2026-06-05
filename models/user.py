"""Accounts & authentication (Phase 7).

The DM is the admin (role 'dm'); players (role 'player') each control one PC via
`creature_id`. Passwords are stored **hashed** (werkzeug), never in plaintext.
The shared registration code players sign up with lives in the `meta` table.
"""
import re
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from db import get_connection

ROLES = ("dm", "player")

# A roll colour is a CSS hex (it's rendered into a style attribute), so only
# accept #rgb / #rrggbb; anything else is stored as '' (no tint).
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def user_count():
    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    finally:
        conn.close()


def get_user(user_id):
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            ((username or "").strip(),),
        ).fetchone()
    finally:
        conn.close()


def list_users():
    """All users, DM(s) first then by username; each joined to its PC's name."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT u.*, c.name AS creature_name FROM users u "
            "LEFT JOIN creatures c ON c.id = u.creature_id "
            "ORDER BY CASE u.role WHEN 'dm' THEN 0 ELSE 1 END, u.username COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def create_user(username, password, role="player", creature_id=None):
    """Create a user with a hashed password. Returns the new id, or None if the
    username is blank/taken or the password is empty."""
    username = (username or "").strip()
    if not username or not password:
        return None
    if role not in ROLES:
        role = "player"
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, creature_id) "
            "VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), role, creature_id),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:  # username already taken
        return None
    finally:
        conn.close()


def verify_login(username, password):
    """Return the user row if the username/password match, else None."""
    user = get_user_by_username(username)
    if user and check_password_hash(user["password_hash"], password or ""):
        return user
    return None


def set_password(user_id, password):
    if not password:
        return
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_user_character(user_id, creature_id):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET creature_id = ? WHERE id = ?",
            (creature_id or None, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_user_color(user_id, color):
    color = (color or "").strip()
    # '' clears the tint; a valid hex sets it; anything else is ignored (kept).
    if color and not _HEX_COLOR.match(color):
        return
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET color = ? WHERE id = ?", (color, user_id))
        conn.commit()
    finally:
        conn.close()


def delete_user(user_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


# --- shared signup code (stored in meta) ----------------------------------

def get_signup_code():
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'signup_code'"
        ).fetchone()
        return row["value"] if row else ""
    finally:
        conn.close()


def set_signup_code(code):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('signup_code', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ((code or "").strip(),),
        )
        conn.commit()
    finally:
        conn.close()
