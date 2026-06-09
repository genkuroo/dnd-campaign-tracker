"""Character backgrounds (read-only reference), bundled in data/backgrounds.json.

A background is the third pillar of a character beside race and class — who they were
*before* adventuring. It grants two skill proficiencies, some tool proficiencies
and/or languages, and a roleplay **feature**. Only **Acolyte** is in the SRD 5.1
(CC-BY-4.0); the rest carry original, paraphrased feature summaries.

Like races/feats, this is a display + tracking layer: the creature records a
`background` slug and the sheet shows what it grants. Skills stay DM-assigned via the
existing picker (the background's skills are surfaced as guidance, not auto-applied).
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "backgrounds.json")
_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(os.path.normpath(_PATH), encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def all_backgrounds():
    return sorted(_load(), key=lambda b: b["name"])


def get_background(slug):
    return next((b for b in _load() if b["slug"] == slug), None) if slug else None


def valid_background(slug):
    """True when `slug` is a known background (used to clear an unknown pick)."""
    return get_background(slug) is not None


def background_skills(creature):
    """The skill slugs a creature's background grants (for the picker's guidance), or
    an empty list."""
    bg = get_background(creature["background"])
    return list(bg.get("skills", [])) if bg else []
