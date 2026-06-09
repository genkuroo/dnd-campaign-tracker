"""The campaign journal (Phase 9b): a two-level notes system.

Folders (overarching adventures / topics) contain notes (the actual writing).
Both the DM and players author them. Each folder/note has an `owner_id`; a note
carries a private|shared visibility. The *permission* logic (who may see/edit
what) lives in the app layer (it needs the current user) — this module is plain
CRUD, joining the author's name for display.
"""
from db import get_connection

VISIBILITIES = ("private", "shared")


# --- Folders ---------------------------------------------------------------

def list_folders():
    """Every folder with its author's name + note count. App layer filters by
    viewer."""
    conn = get_connection()
    try:
        return conn.execute(
            """
            SELECT f.*, u.username AS owner_name,
                   (SELECT COUNT(*) FROM journal_notes n WHERE n.folder_id = f.id) AS note_count
            FROM journal_folders f
            LEFT JOIN users u ON u.id = f.owner_id
            ORDER BY f.created_at DESC, f.id DESC
            """
        ).fetchall()
    finally:
        conn.close()


def get_folder(folder_id):
    if not folder_id:
        return None
    conn = get_connection()
    try:
        return conn.execute(
            """
            SELECT f.*, u.username AS owner_name
            FROM journal_folders f
            LEFT JOIN users u ON u.id = f.owner_id
            WHERE f.id = ?
            """,
            (folder_id,),
        ).fetchone()
    finally:
        conn.close()


def create_folder(owner_id, title, description=""):
    title = (title or "").strip()
    if not title:
        return None
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO journal_folders (owner_id, title, description) VALUES (?, ?, ?)",
            (owner_id, title, (description or "").strip()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_folder(folder_id, title, description=""):
    title = (title or "").strip()
    if not title:
        return
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE journal_folders SET title = ?, description = ? WHERE id = ?",
            (title, (description or "").strip(), folder_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_folder(folder_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM journal_folders WHERE id = ?", (folder_id,))
        conn.commit()
    finally:
        conn.close()


# --- Notes -----------------------------------------------------------------

def notes_in_folder(folder_id):
    """All notes in a folder (author name joined). App layer filters by viewer."""
    conn = get_connection()
    try:
        return conn.execute(
            """
            SELECT n.*, u.username AS owner_name
            FROM journal_notes n
            LEFT JOIN users u ON u.id = n.owner_id
            WHERE n.folder_id = ?
            ORDER BY n.created_at, n.id
            """,
            (folder_id,),
        ).fetchall()
    finally:
        conn.close()


def get_note(note_id):
    if not note_id:
        return None
    conn = get_connection()
    try:
        return conn.execute(
            """
            SELECT n.*, u.username AS owner_name, f.title AS folder_title
            FROM journal_notes n
            LEFT JOIN users u ON u.id = n.owner_id
            LEFT JOIN journal_folders f ON f.id = n.folder_id
            WHERE n.id = ?
            """,
            (note_id,),
        ).fetchone()
    finally:
        conn.close()


def create_note(folder_id, owner_id, title, body="", visibility="private"):
    title = (title or "").strip()
    if not title:
        return None
    visibility = visibility if visibility in VISIBILITIES else "private"
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO journal_notes (folder_id, owner_id, title, body, visibility) "
            "VALUES (?, ?, ?, ?, ?)",
            (folder_id, owner_id, title, body or "", visibility),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_note(note_id, title, body="", visibility=None):
    title = (title or "").strip()
    if not title:
        return
    conn = get_connection()
    try:
        if visibility in VISIBILITIES:
            conn.execute(
                "UPDATE journal_notes SET title = ?, body = ?, visibility = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (title, body or "", visibility, note_id),
            )
        else:
            conn.execute(
                "UPDATE journal_notes SET title = ?, body = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (title, body or "", note_id),
            )
        conn.commit()
    finally:
        conn.close()


def set_note_visibility(note_id, visibility):
    """Flip a note private↔shared (the DM 'reveal' / a player 'share')."""
    visibility = "shared" if visibility == "shared" else "private"
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE journal_notes SET visibility = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (visibility, note_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_note(note_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM journal_notes WHERE id = ?", (note_id,))
        conn.commit()
    finally:
        conn.close()
