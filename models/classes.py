"""The 5e class list (read-only reference), bundled in data/classes.json.

The bones of a class system: each class carries its hit die, primary/save
abilities, Unarmored Defense, spellcasting ability, a recommended stat array, and
a starting-equipment kit. Picking a class on character creation applies that
package (stats, HP from the hit die, starting gear, unarmored defense), and the
hit die drives level-up HP. Features/subclasses can layer on later.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "classes.json")
_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(os.path.normpath(_PATH), encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def all_classes():
    return sorted(_load(), key=lambda c: c["name"])


def get_class(slug):
    return next((c for c in _load() if c["slug"] == slug), None)


def hit_die_average(hit_die):
    """The fixed (taken-not-rolled) HP per level for a hit die: d6→4, d8→5,
    d10→6, d12→7 (i.e. die/2 + 1) — the BG3/'average' rule."""
    return hit_die // 2 + 1
