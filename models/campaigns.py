"""Multiple campaigns ("saves"), one table at a time.

Each campaign is its own SQLite file under `campaigns/`; a registry DB tracks the
list and which one is active (see db.py). The DM toggles the active campaign from
the Campaigns page — switching is **global** (the whole table moves to it), which
matches one group playing one campaign at a time.

Accounts live inside each campaign DB, so creating a new campaign **seeds the
DM's account** into it (same username + password hash) — that, plus keying the
session on username (see app.py), keeps the DM logged in across switches. Players
only exist in the campaigns they were registered in.

Duplicating a campaign copies its file, which doubles as a point-in-time snapshot.
"""
import os
import re
import shutil

from werkzeug.security import generate_password_hash

import db


def _slugify(name):
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return base or "campaign"


def _unique_filename(name):
    """A `<slug>.db` filename not already used by a campaign file or registry row."""
    slug = _slugify(name)
    existing = {c["filename"] for c in list_campaigns()}
    candidate = f"{slug}.db"
    n = 2
    while candidate in existing or os.path.exists(os.path.join(db.CAMPAIGNS_DIR, candidate)):
        candidate = f"{slug}-{n}.db"
        n += 1
    return candidate


def list_campaigns():
    """All campaigns, newest activity first, each with an `is_active` flag."""
    active = db.active_campaign_filename()
    conn = db.get_registry_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM campaigns "
            "ORDER BY (last_played_at IS NULL), last_played_at DESC, id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r, is_active=(r["filename"] == active)) for r in rows]


def get_campaign(campaign_id):
    conn = db.get_registry_connection()
    try:
        row = conn.execute(
            "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def active_campaign():
    """The active campaign's registry row (or None)."""
    active = db.active_campaign_filename()
    conn = db.get_registry_connection()
    try:
        row = conn.execute(
            "SELECT * FROM campaigns WHERE filename = ?", (active,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def _seed_dm(path, dm):
    """Insert the DM's account into a freshly created campaign DB at `path`, so the
    DM can use it immediately (and stays logged in across a switch). `dm` is a user
    row from another campaign — we reuse its password hash verbatim."""
    if not dm:
        return
    conn = db._connect(path)
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, color) "
            "VALUES (?, ?, 'dm', ?)",
            (dm["username"], dm["password_hash"], dm["color"] or ""),
        )
        conn.commit()
    finally:
        conn.close()


def create_campaign(name, dm=None):
    """Create a new, empty campaign and register it. Seeds the DM account (if given)
    so it's immediately playable. Does NOT switch to it. Returns the new id."""
    name = (name or "").strip() or "New Campaign"
    filename = _unique_filename(name)
    path = os.path.join(db.CAMPAIGNS_DIR, filename)
    db.migrate_path(path)        # create the schema in the fresh file
    _seed_dm(path, dm)
    return db.register_campaign(name, filename)


def duplicate_campaign(campaign_id, name=None):
    """Copy an existing campaign's file into a new campaign — a snapshot/save.
    Returns the new id, or None if the source is missing."""
    src = get_campaign(campaign_id)
    if not src:
        return None
    name = (name or "").strip() or f"{src['name']} (copy)"
    filename = _unique_filename(name)
    src_path = os.path.join(db.CAMPAIGNS_DIR, src["filename"])
    if not os.path.exists(src_path):
        return None
    shutil.copy2(src_path, os.path.join(db.CAMPAIGNS_DIR, filename))
    return db.register_campaign(name, filename)


def rename_campaign(campaign_id, name):
    name = (name or "").strip()
    if not name:
        return
    conn = db.get_registry_connection()
    try:
        conn.execute(
            "UPDATE campaigns SET name = ? WHERE id = ?", (name, campaign_id)
        )
        conn.commit()
    finally:
        conn.close()


def switch_campaign(campaign_id):
    """Make `campaign_id` the active campaign. Returns True on success."""
    camp = get_campaign(campaign_id)
    if not camp:
        return False
    db.set_active_filename(camp["filename"])
    conn = db.get_registry_connection()
    try:
        conn.execute(
            "UPDATE campaigns SET last_played_at = datetime('now') WHERE id = ?",
            (campaign_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return True


def delete_campaign(campaign_id):
    """Delete a campaign and its file. Refuses to delete the active campaign or the
    last remaining one. Returns (ok, message)."""
    camp = get_campaign(campaign_id)
    if not camp:
        return False, "Campaign not found."
    if camp["filename"] == db.active_campaign_filename():
        return False, "Switch to another campaign before deleting this one."
    if len(list_campaigns()) <= 1:
        return False, "Can't delete the only campaign."
    conn = db.get_registry_connection()
    try:
        conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
        conn.commit()
    finally:
        conn.close()
    try:
        os.remove(os.path.join(db.CAMPAIGNS_DIR, camp["filename"]))
    except OSError:
        pass
    return True, f"Deleted “{camp['name']}.”"
