"""Feats: a per-creature tracked list of feats (skeleton — no mechanics yet).

A character may take a feat *instead* of an Ability Score Improvement (see
models/asi); for now the two aren't budget-linked — this just records which feats a
creature has so they show on the sheet.

Mirrors the action book (models/action_catalog + models/actions): a premade catalog
bundled as JSON (data/feats.json) the player grabs from — copied into
`creature_feats` (migration 31) so each pick can be edited/removed per-creature —
plus a hand-added custom feat. Display only; feats don't apply effects.

Only **Grappler** is from the 5e SRD (CC-BY-4.0); the other catalog entries carry
original, paraphrased one-line summaries and are freely editable.
"""
import json
import os

from db import get_connection

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "feats.json")
_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(os.path.normpath(_PATH), encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def all_catalog_feats():
    """Catalog entries, alphabetical by name."""
    return sorted(_load(), key=lambda f: f["name"])


def get_catalog_feat(slug):
    return next((f for f in _load() if f["slug"] == slug), None)


# --- Per-creature feats ---------------------------------------------------

def list_feats(creature_id):
    """A creature's taken feats, alphabetical by name."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creature_feats WHERE creature_id = ? ORDER BY name COLLATE NOCASE",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()


def add_feat(creature_id, name, description="", prerequisite=""):
    """Record a feat on a creature. Returns the new id, or None if unnamed."""
    name = (name or "").strip()
    if not name:
        return None
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO creature_feats (creature_id, name, description, prerequisite) "
            "VALUES (?, ?, ?, ?)",
            (creature_id, name, (description or "").strip(), (prerequisite or "").strip()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_feat(feat_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creature_feats WHERE id = ?", (feat_id,)
        ).fetchone()
    finally:
        conn.close()


def remove_feat(feat_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM creature_feats WHERE id = ?", (feat_id,))
        conn.commit()
    finally:
        conn.close()
