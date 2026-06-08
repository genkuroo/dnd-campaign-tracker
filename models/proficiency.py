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
from models.classes import get_class

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


def set_skill_proficiencies(creature_id, slugs):
    """Replace a creature's proficient skills with `slugs` (ignoring unknown ones)."""
    chosen = [s for s in dict.fromkeys(slugs) if s in _SKILL_SLUGS]
    conn = get_connection()
    try:
        conn.execute("DELETE FROM creature_skills WHERE creature_id = ?", (creature_id,))
        conn.executemany(
            "INSERT INTO creature_skills (creature_id, skill_slug) VALUES (?, ?)",
            [(creature_id, s) for s in chosen],
        )
        conn.commit()
    finally:
        conn.close()


def skill_table(creature, eff_abilities):
    """Per-skill display rows: {slug, name, ability (short), proficient, modifier}.
    The modifier already folds in the proficiency bonus when proficient."""
    prof = proficient_skills(creature["id"])
    pb = proficiency_bonus(creature["level"])
    out = []
    for slug, name, col in SKILLS:
        mod = ability_modifier(eff_abilities[col]["score"])
        is_prof = slug in prof
        out.append({
            "slug": slug, "name": name, "ability": _SHORT_BY_COL[col],
            "proficient": is_prof, "modifier": mod + (pb if is_prof else 0),
        })
    return out
