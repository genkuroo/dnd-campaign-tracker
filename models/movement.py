"""Walking speed — base + class/feat modifiers, computed on read.

Base speed is the creature's **race** speed when it has one (Wood Elf 35, Dwarf 25…),
else its stored `speed` column (NPCs/monsters, or a raceless PC — default 30). On top:
  - **Fast Movement** (Barbarian 5+): +10 ft, unless wearing heavy armor.
  - **Unarmored Movement** (Monk): +10→+30 by level, unless wearing body armor.
  - **Mobile** feat: +10 ft.
Mirrors effective_ac / effective_abilities — nothing is stored beyond the base.
"""
from models.races import race_speed
from models.classes import class_features

# Monk Unarmored Movement bonus by monk level (the 5e table).
_UNARMORED_MOVEMENT = [(2, 10), (6, 15), (10, 20), (14, 25), (18, 30)]


def base_speed(creature):
    """Race speed if the creature has a race, else its stored `speed` column."""
    return race_speed(creature) or creature["speed"]


def _has_feature(creature, name):
    slug = creature["class_name"]
    if not slug:
        return False
    return any(f["name"] == name
               for f in class_features(slug, creature["level"], creature["subclass"]))


def _has_feat(creature, name):
    from models.feats import list_feats  # local: avoid import cycle
    return any((f["name"] or "").strip().lower() == name.lower()
               for f in list_feats(creature["id"]))


def _wears_body_armor(creature, heavy_only=False):
    from models.inventory import equipped_set_armor  # local: avoid import cycle
    a = equipped_set_armor(creature["id"])
    if not a:
        return False
    return a["armor_type"] == "heavy" if heavy_only else True


def speed_modifiers(creature):
    """[(label, feet)] speed bonuses the creature currently gets, for the breakdown."""
    mods = []
    if _has_feature(creature, "Fast Movement") and not _wears_body_armor(creature, heavy_only=True):
        mods.append(("Fast Movement", 10))
    if _has_feature(creature, "Unarmored Movement") and not _wears_body_armor(creature):
        lvl = int(creature["level"])
        bonus = 0
        for min_lvl, amt in _UNARMORED_MOVEMENT:
            if lvl >= min_lvl:
                bonus = amt
        if bonus:
            mods.append(("Unarmored Movement", bonus))
    if _has_feat(creature, "Mobile"):
        mods.append(("Mobile", 10))
    return mods


def effective_speed(creature):
    """Walking speed in feet: base + class/feat modifiers."""
    return base_speed(creature) + sum(amt for _, amt in speed_modifiers(creature))


def speed_breakdown(creature):
    """A short 'how the speed is figured' string for a tooltip."""
    parts = [f"{base_speed(creature)} base"]
    parts += [f"+{amt} {label}" for label, amt in speed_modifiers(creature)]
    return " · ".join(parts)
