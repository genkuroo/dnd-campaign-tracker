"""The 5e race/species list (read-only reference), bundled in data/races.json.

The other half of character building beside class. A race grants **ability score
increases**, a **base speed**, a **size**, and a set of **traits** (Darkvision,
Fey Ancestry, …); many have **subraces** that add their own bonuses + traits.

Sourced from the 5e SRD 5.1 (CC-BY-4.0) — the core PHB races — with paraphrased
trait summaries. Mirrors models/classes: the data is reference, the *ability
bonuses* fold into `effective_abilities` on read (like ASI / item bonuses, so the
base sheet is never mutated), and the traits are a display layer (mechanics not
auto-applied, like feats).
"""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "races.json")
_cache = None
_DEFAULT_SPEED = 30


def _load():
    global _cache
    if _cache is None:
        with open(os.path.normpath(_PATH), encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def all_races():
    return sorted(_load(), key=lambda r: r["name"])


def get_race(slug):
    return next((r for r in _load() if r["slug"] == slug), None) if slug else None


def subraces_for(slug):
    race = get_race(slug)
    return race.get("subraces", []) if race else []


def get_subrace(slug, sub_slug):
    if not sub_slug:
        return None
    return next((s for s in subraces_for(slug) if s["slug"] == sub_slug), None)


def valid_subrace(slug, sub_slug):
    """True when `sub_slug` belongs to race `slug` — used to drop a leftover pick
    after a race change."""
    return get_subrace(slug, sub_slug) is not None


def _race_and_sub(creature):
    race = get_race(creature["race"])
    sub = get_subrace(creature["race"], creature["subrace"]) if race else None
    return race, sub


def race_ability_bonuses(creature):
    """{ability_col: amount} from the creature's race + subrace, combined. Empty for
    a creature with no race. Folded into effective_abilities on read."""
    race, sub = _race_and_sub(creature)
    if not race:
        return {}
    totals = dict(race.get("ability_bonuses", {}))
    if sub:
        for col, amt in sub.get("ability_bonuses", {}).items():
            totals[col] = totals.get(col, 0) + amt
    return totals


def race_speed(creature):
    """The creature's base walking speed in feet (subrace overrides race, e.g. Wood
    Elf 35), or None if it has no race."""
    race, sub = _race_and_sub(creature)
    if not race:
        return None
    if sub and sub.get("speed"):
        return sub["speed"]
    return race.get("speed", _DEFAULT_SPEED)


def race_size(creature):
    race, _ = _race_and_sub(creature)
    return race.get("size", "") if race else ""


def race_label(creature):
    """The display name for the sheet header: the subrace name when chosen (it
    already includes the race, e.g. 'High Elf'), else the race name, else ''."""
    race, sub = _race_and_sub(creature)
    if not race:
        return ""
    return sub["name"] if sub else race["name"]


def race_traits(creature):
    """[{name, description, source}] — race traits then the chosen subrace's, for the
    sheet's Racial Traits section. Empty for a creature with no race."""
    race, sub = _race_and_sub(creature)
    if not race:
        return []
    out = [{**t, "source": "race"} for t in race.get("traits", [])]
    if sub:
        out += [{**t, "source": "subrace"} for t in sub.get("traits", [])]
    return out
