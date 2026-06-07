"""The 5e class list (read-only reference), bundled in data/classes.json.

The bones of a class system: each class carries its hit die, primary/save
abilities, Unarmored Defense, spellcasting ability, a recommended stat array, and
a starting-equipment kit. Picking a class on character creation applies that
package (stats, HP from the hit die, starting gear, unarmored defense), and the
hit die drives level-up HP. Features/subclasses can layer on later.
"""
import json
import math
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


# --- Subclasses -----------------------------------------------------------

def subclasses_for(slug):
    """The subclass options for a class (e.g. Barbarian → [Path of the Berserker]).
    Empty for the classless or an unknown class. SRD ships one archetype per class,
    but the list is open for hand-added ones."""
    klass = get_class(slug) if slug else None
    return klass.get("subclasses", []) if klass else []


def get_subclass(slug, sub_slug):
    """The subclass dict for a class, or None."""
    if not sub_slug:
        return None
    return next((s for s in subclasses_for(slug) if s["slug"] == sub_slug), None)


def valid_subclass(slug, sub_slug):
    """True when `sub_slug` is one of `slug`'s subclasses — used to reject a
    subclass that doesn't belong to the chosen class (e.g. after a class change)."""
    return get_subclass(slug, sub_slug) is not None


def subclass_label(slug):
    """The class's in-world name for its subclass choice (Primal Path, Divine
    Domain, …), or 'Subclass' as a fallback."""
    klass = get_class(slug) if slug else None
    return (klass.get("subclass_label") if klass else None) or "Subclass"


def subclass_level(slug):
    """The level at which this class chooses its subclass (1, 2, or 3), or 0."""
    klass = get_class(slug) if slug else None
    return int(klass.get("subclass_level", 0)) if klass else 0


def _subclass_features(slug, sub_slug):
    """The chosen subclass's features, each shallow-copied with a `subclass` marker
    (and the subclass name) so callers can merge + tag without mutating the cache."""
    sub = get_subclass(slug, sub_slug)
    if not sub:
        return []
    return [{**f, "subclass": True, "subclass_name": sub["name"]}
            for f in sub.get("features", [])]


def _all_features(slug, sub_slug):
    """Base class features + the chosen subclass's features, in level order. Class
    features carry `subclass: False`; subclass ones carry `subclass: True`."""
    klass = get_class(slug) if slug else None
    if not klass:
        return []
    base = [{**f, "subclass": False} for f in klass.get("features", [])]
    merged = base + _subclass_features(slug, sub_slug)
    return sorted(merged, key=lambda f: f["level"])


def _scaled_dice(scale, level):
    """Resolve a feature's `scale` spec to a dice expression at `level`:
      - dice_count: N d<die>, N from a `steps` table or ceil/floor(level/per_levels)
      - die_steps : the die expr for the highest level threshold reached
      - dice_plus_level: "<base>+<level>" (e.g. Second Wind 1d10 + fighter level)
    Returns '' if nothing applies yet."""
    kind = scale.get("type")
    if kind == "dice_count":
        die = scale["die"]
        if "steps" in scale:
            n = 0
            for lv, count in scale["steps"]:
                if level >= lv:
                    n = count
        else:
            per = scale.get("per_levels", 1)
            n = math.ceil(level / per) if scale.get("round") == "up" else max(1, level // per)
        return f"{n}{die}" if n else ""
    if kind == "die_steps":
        expr = ""
        for lv, value in scale["steps"]:
            if level >= lv:
                expr = value
        return expr
    if kind == "dice_plus_level":
        return f"{scale['base']}+{level}"
    return ""


def _apply_scaling(feature, level):
    """If a feature scales with level, return a copy with its `dice` recomputed for
    `level` (Sneak Attack 1d6→Nd6, Martial Arts die, Second Wind 1d10+level…).
    Untouched otherwise."""
    scale = feature.get("scale")
    if not scale:
        return feature
    expr = _scaled_dice(scale, int(level or 1))
    return {**feature, "dice": expr} if expr else feature


def class_features(slug, level, subclass=None):
    """The class's features a creature has unlocked at `level` (everything with
    level ≤ the creature's), in level order — base class plus the chosen `subclass`.
    Level-scaling features get their `dice` recomputed for `level`. Computed on read
    — reference only, never stored. Empty for the classless."""
    lvl = int(level or 1)
    return [_apply_scaling(f, lvl)
            for f in _all_features(slug, subclass) if f["level"] <= lvl]


def class_features_remaining(slug, level, subclass=None):
    """Not-yet-unlocked features (level > the creature's), in level order — for a
    'what's next' preview, including the chosen subclass's upcoming features. A
    scaling feature previews at its own unlock level."""
    lvl = int(level or 1)
    return [_apply_scaling(f, f["level"])
            for f in _all_features(slug, subclass) if f["level"] > lvl]


def grantable_class_features(slug, level, subclass=None):
    """The action-type features unlocked through `level` — the subset tagged with a
    `category` in classes.json (Rage, Second Wind, Sneak Attack, plus subclass ones
    like Cutting Words / Preserve Life / Fast Hands). These are auto-granted into the
    creature's actions list; passives without a category stay display-only."""
    return [f for f in class_features(slug, level, subclass) if f.get("category")]
