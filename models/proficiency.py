"""The proficiency layer — the trained bonus on saving throws and skill checks.

A creature's **proficiency bonus** scales with level (`creature.proficiency_bonus`)
and is added to any d20 roll it's *proficient* in. Two surfaces use it:

  - **Saving throws** — proficiency comes from the creature's class (each 5e class
    grants two), read straight from data/classes.json; no per-creature storage.
  - **Skill checks** — proficiency is chosen per creature and stored in the
    `creature_skills` table (migration 24).

Like effective AC/abilities, the bonus is *computed* on read, never baked into the
sheet, so it tracks the creature's level and ability scores live.
"""
from db import get_connection
from models.creature import ABILITIES, ability_modifier, proficiency_bonus
from models.classes import get_class, class_features

# The 18 SRD skills: (slug, display name, governing ability column). Fixed list.
SKILLS = [
    ("acrobatics", "Acrobatics", "dexterity"),
    ("animal-handling", "Animal Handling", "wisdom"),
    ("arcana", "Arcana", "intelligence"),
    ("athletics", "Athletics", "strength"),
    ("deception", "Deception", "charisma"),
    ("history", "History", "intelligence"),
    ("insight", "Insight", "wisdom"),
    ("intimidation", "Intimidation", "charisma"),
    ("investigation", "Investigation", "intelligence"),
    ("medicine", "Medicine", "wisdom"),
    ("nature", "Nature", "intelligence"),
    ("perception", "Perception", "wisdom"),
    ("performance", "Performance", "charisma"),
    ("persuasion", "Persuasion", "charisma"),
    ("religion", "Religion", "intelligence"),
    ("sleight-of-hand", "Sleight of Hand", "dexterity"),
    ("stealth", "Stealth", "dexterity"),
    ("survival", "Survival", "wisdom"),
]
_SKILL_SLUGS = {slug for slug, _, _ in SKILLS}
_SHORT_BY_COL = {col: short for col, short in ABILITIES}
_COL_BY_SHORT = {short: col for col, short in ABILITIES}

# (slug, name, ability_col, ability_short) — for the edit form's proficiency picker.
SKILL_OPTIONS = [(slug, name, col, _SHORT_BY_COL[col]) for slug, name, col in SKILLS]


def proficient_save_cols(creature):
    """The ability columns a creature is proficient in saving throws for, taken
    from its class (5e grants two). Classless creatures (most NPCs/monsters) → none."""
    klass = get_class(creature["class_name"]) if creature["class_name"] else None
    if not klass:
        return set()
    return {_COL_BY_SHORT[s] for s in klass.get("saves", []) if s in _COL_BY_SHORT}


def save_table(creature, eff_abilities):
    """{ability_col: {'proficient': bool, 'modifier': int}} saving-throw info,
    keyed so the ability grid can look up `saves[col]` as it loops."""
    prof = proficient_save_cols(creature)
    pb = proficiency_bonus(creature["level"])
    out = {}
    for col, _ in ABILITIES:
        mod = ability_modifier(eff_abilities[col]["score"])
        is_prof = col in prof
        out[col] = {"proficient": is_prof, "modifier": mod + (pb if is_prof else 0)}
    return out


# --- Weapon & armor proficiency (derived from the class) ------------------
# Armor categories a class can be proficient with. Equipped body armor carries an
# `armor_type` (light/medium/heavy) we check against these; 'shields' is separate
# (and not auto-checked yet — items have no reliable shield flag).
ARMOR_CATEGORIES = [("light", "Light"), ("medium", "Medium"),
                    ("heavy", "Heavy"), ("shields", "Shields")]
_ARMOR_LABELS = dict(ARMOR_CATEGORIES)


def armor_proficiencies(creature):
    """The armor categories the creature's class is proficient with (a set of
    'light'/'medium'/'heavy'/'shields'). Empty for the classless and for armorless
    casters (Wizard/Sorcerer/Monk)."""
    klass = get_class(creature["class_name"]) if creature["class_name"] else None
    return set(klass.get("armor_prof", [])) if klass else set()


def weapon_proficiencies(creature):
    """The class's weapon proficiencies as stored tokens ('simple'/'martial' or
    named weapons). Empty for the classless."""
    klass = get_class(creature["class_name"]) if creature["class_name"] else None
    return list(klass.get("weapon_prof", [])) if klass else []


def proficiency_summary(creature):
    """A compact {'armor': [labels], 'weapons': [labels]} for the sheet's
    Proficiencies line, or None for a classless creature (most NPCs/monsters)."""
    klass = get_class(creature["class_name"]) if creature["class_name"] else None
    if not klass:
        return None
    prof = armor_proficiencies(creature)
    armor = [label for key, label in ARMOR_CATEGORIES if key in prof]
    weapons = [w.capitalize() if w in ("simple", "martial") else w
               for w in weapon_proficiencies(creature)]
    return {"armor": armor, "weapons": weapons}


def armor_proficiency_issue(creature):
    """If the creature wears body armor its class isn't proficient with, return
    {'name', 'armor_type'} (the 5e penalty: disadvantage on STR/DEX d20 rolls, and a
    caster can't cast in it). Else None. Only **classed** creatures are checked — an
    NPC/monster has no class proficiencies to violate. Shields aren't checked yet."""
    if not creature["class_name"]:
        return None
    from models.inventory import equipped_set_armor  # local: avoid import cycle
    armor = equipped_set_armor(creature["id"])
    if not armor or not armor["armor_type"]:
        return None
    if armor["armor_type"] in armor_proficiencies(creature):
        return None
    return {"name": armor["name"], "armor_type": armor["armor_type"]}


def proficient_skills(creature_id):
    """The set of skill slugs a creature is proficient in."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT skill_slug FROM creature_skills WHERE creature_id = ?",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()
    return {r["skill_slug"] for r in rows}


def expertise_skills(creature_id):
    """The set of skill slugs a creature has **expertise** in (double proficiency).
    A subset of the proficient skills (expertise is a flag on the same row)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT skill_slug FROM creature_skills "
            "WHERE creature_id = ? AND expertise = 1",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()
    return {r["skill_slug"] for r in rows}


def set_skill_proficiencies(creature_id, slugs, expertise_slugs=()):
    """Replace a creature's proficient skills with `slugs` (ignoring unknown ones);
    mark expertise for any of `expertise_slugs` that are also proficient (expertise
    always implies proficiency)."""
    chosen = [s for s in dict.fromkeys(slugs) if s in _SKILL_SLUGS]
    exp = {s for s in expertise_slugs if s in chosen}
    conn = get_connection()
    try:
        conn.execute("DELETE FROM creature_skills WHERE creature_id = ?", (creature_id,))
        conn.executemany(
            "INSERT INTO creature_skills (creature_id, skill_slug, expertise) "
            "VALUES (?, ?, ?)",
            [(creature_id, s, 1 if s in exp else 0) for s in chosen],
        )
        conn.commit()
    finally:
        conn.close()


def passive_perception(creature, eff_abilities):
    """A creature's **passive Perception** = 10 + its Perception check modifier
    (proficiency / expertise / half-proficiency already folded in). The DM compares
    this 'always-on' awareness score against how well something is hidden, without
    asking for a roll."""
    for row in skill_table(creature, eff_abilities):
        if row["slug"] == "perception":
            return 10 + row["modifier"]
    return 10


def _has_feature(creature, name):
    """True if the creature's class/subclass has unlocked a named feature at its
    level (used to detect Jack of All Trades / Remarkable Athlete)."""
    slug = creature["class_name"]
    if not slug:
        return False
    return any(f["name"] == name
               for f in class_features(slug, creature["level"], creature["subclass"]))


def has_jack_of_all_trades(creature):
    """Bard (level 2+): add half proficiency (rounded down) to any ability/skill
    check not already proficient."""
    return _has_feature(creature, "Jack of All Trades")


def has_remarkable_athlete(creature):
    """Champion fighter (level 7+): add half proficiency (rounded up) to STR/DEX/CON
    checks not already proficient."""
    return _has_feature(creature, "Remarkable Athlete")


_PHYSICAL = {"strength", "dexterity", "constitution"}


def skill_table(creature, eff_abilities):
    """Per-skill display rows: {slug, name, ability (short), proficient, expertise,
    tier, modifier}. `tier` is 'expertise' | 'proficient' | 'half' | None; the
    modifier folds in the right bonus: 2×PB (expertise), PB (proficient), or half PB
    from Jack of All Trades (any skill, rounded down) / Remarkable Athlete (STR/DEX/
    CON, rounded up) when not proficient."""
    prof = proficient_skills(creature["id"])
    exp = expertise_skills(creature["id"])
    pb = proficiency_bonus(creature["level"])
    joat = has_jack_of_all_trades(creature)
    ra = has_remarkable_athlete(creature)
    half_floor, half_ceil = pb // 2, (pb + 1) // 2
    out = []
    for slug, name, col in SKILLS:
        mod = ability_modifier(eff_abilities[col]["score"])
        if slug in exp:
            bonus, tier = 2 * pb, "expertise"
        elif slug in prof:
            bonus, tier = pb, "proficient"
        else:
            half = 0
            if ra and col in _PHYSICAL:
                half = max(half, half_ceil)
            if joat:
                half = max(half, half_floor)
            bonus, tier = half, ("half" if half else None)
        out.append({
            "slug": slug, "name": name, "ability": _SHORT_BY_COL[col],
            "proficient": slug in prof, "expertise": slug in exp,
            "tier": tier, "modifier": mod + bonus,
        })
    return out
