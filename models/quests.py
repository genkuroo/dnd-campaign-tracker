"""Quests + their objectives (Phase 9c).

A quest is a DM-authored goal with a status (active/completed/failed) and the
visibility fog-of-war spine (hidden until the party picks it up). Each quest has
ordered sub-objectives, themselves status-tracked and individually hide-able.
Permission/visibility filtering for players lives in the app layer; this module
is plain CRUD.
"""
from db import get_connection

QUEST_STATUSES = ("active", "completed", "failed")
OBJECTIVE_STATUSES = ("open", "done", "failed")


# --- Quests ----------------------------------------------------------------

def _quest_rows(where=""):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM quests " + where + " ORDER BY "
            # active first, then completed, then failed; newest within each.
            "CASE status WHEN 'active' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END, "
            "created_at DESC, id DESC"
        ).fetchall()
    finally:
        conn.close()


def list_quests():
    """Every quest (DM view)."""
    return _quest_rows()


def visible_quests():
    """Only quests revealed to players."""
    return _quest_rows("WHERE visibility = 'visible'")


def get_quest(quest_id):
    if not quest_id:
        return None
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM quests WHERE id = ?", (quest_id,)
        ).fetchone()
    finally:
        conn.close()


def create_quest(data):
    fields = _clean_quest(data)
    if not fields.get("title"):
        return None
    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    conn = get_connection()
    try:
        cur = conn.execute(
            f"INSERT INTO quests ({', '.join(cols)}) VALUES ({placeholders})",
            [fields[c] for c in cols],
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_quest(quest_id, data):
    fields = _clean_quest(data)
    if not fields:
        return
    assignments = ", ".join(f"{col} = ?" for col in fields)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE quests SET {assignments} WHERE id = ?",
            [*fields.values(), quest_id],
        )
        conn.commit()
    finally:
        conn.close()


def set_quest_status(quest_id, status):
    status = status if status in QUEST_STATUSES else "active"
    conn = get_connection()
    try:
        conn.execute("UPDATE quests SET status = ? WHERE id = ?", (status, quest_id))
        conn.commit()
    finally:
        conn.close()


def set_quest_visibility(quest_id, visibility):
    visibility = "visible" if visibility == "visible" else "hidden"
    conn = get_connection()
    try:
        conn.execute("UPDATE quests SET visibility = ? WHERE id = ?",
                     (visibility, quest_id))
        conn.commit()
    finally:
        conn.close()


def delete_quest(quest_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM quests WHERE id = ?", (quest_id,))
        conn.commit()
    finally:
        conn.close()


# --- Objectives ------------------------------------------------------------

def objectives_for(quest_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM quest_objectives WHERE quest_id = ? "
            "ORDER BY position, id",
            (quest_id,),
        ).fetchall()
    finally:
        conn.close()


def get_objective(objective_id):
    if not objective_id:
        return None
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM quest_objectives WHERE id = ?", (objective_id,)
        ).fetchone()
    finally:
        conn.close()


def add_objective(quest_id, description, visibility="visible"):
    description = (description or "").strip()
    if not description:
        return None
    visibility = "visible" if visibility == "visible" else "hidden"
    conn = get_connection()
    try:
        # Append after the current last objective.
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 AS pos FROM quest_objectives "
            "WHERE quest_id = ?",
            (quest_id,),
        ).fetchone()
        cur = conn.execute(
            "INSERT INTO quest_objectives (quest_id, description, visibility, position) "
            "VALUES (?, ?, ?, ?)",
            (quest_id, description, visibility, row["pos"]),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_objective(objective_id, description):
    description = (description or "").strip()
    if not description:
        return
    conn = get_connection()
    try:
        conn.execute("UPDATE quest_objectives SET description = ? WHERE id = ?",
                     (description, objective_id))
        conn.commit()
    finally:
        conn.close()


def set_objective_status(objective_id, status):
    status = status if status in OBJECTIVE_STATUSES else "open"
    conn = get_connection()
    try:
        conn.execute("UPDATE quest_objectives SET status = ? WHERE id = ?",
                     (status, objective_id))
        conn.commit()
    finally:
        conn.close()


def set_objective_visibility(objective_id, visibility):
    visibility = "visible" if visibility == "visible" else "hidden"
    conn = get_connection()
    try:
        conn.execute("UPDATE quest_objectives SET visibility = ? WHERE id = ?",
                     (visibility, objective_id))
        conn.commit()
    finally:
        conn.close()


def delete_objective(objective_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM quest_objectives WHERE id = ?", (objective_id,))
        conn.commit()
    finally:
        conn.close()


def objective_progress(objectives):
    """(#done, #total) over a list of objective rows — for a quest's progress tag."""
    total = len(objectives)
    done = sum(1 for o in objectives if o["status"] == "done")
    return done, total


# --- Cleaning --------------------------------------------------------------

_QUEST_TEXT = ("title", "description", "status", "visibility")


def _clean_quest(data):
    fields = {}
    for col in _QUEST_TEXT:
        if col in data:
            fields[col] = (data.get(col) or "").strip()
    if "status" in fields and fields["status"] not in QUEST_STATUSES:
        fields["status"] = "active"
    if "visibility" in fields and fields["visibility"] != "visible":
        fields["visibility"] = "hidden"
    return fields
