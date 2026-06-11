"""Weapon attacks — turn an equipped weapon item into an attack + damage roll.

A weapon's stats are packed into the item's `weapon` text column (migration 34) as
**"damage|type|ability|category[|bonus]"** — e.g. `"1d8|slashing|str|martial"` or
`"1d8|slashing|str|martial|1"` for a +1 magic weapon — mirroring how `stat_bonuses`
packs its data. The 5th `bonus` field is optional (absent = +0), so older 4-field
strings keep parsing. An empty column means the item isn't a weapon.

Computed on read (nothing stored beyond the weapon stats themselves):
  - **To-hit** = d20 + ability mod + **proficiency bonus when proficient** (finally
    consuming the weapon-proficiency layer in models/proficiency) + the magic bonus.
  - **Damage** = the weapon's dice + the same ability mod + the magic bonus (a flat
    add, applied once — it is NOT doubled on a critical hit).
  - **ability** is `str` (melee), `dex` (ranged), or `finesse` (best of STR/DEX).
"""
import re

from models.creature import ability_modifier, proficiency_bonus

_VALID_ABILITY = ("str", "dex", "finesse")
_DICE_TERM = re.compile(r"(\d*)d(\d+)")
_ABILITY_COL = {"str": "strength", "dex": "dexterity"}
_ABILITY_LABEL = {"str": "STR", "dex": "DEX", "finesse": "finesse"}


def pack_weapon(damage, dtype="", ability="str", category="", bonus=0):
    """Build the packed `weapon` string; '' when there's no damage (not a weapon).
    The magic `bonus` (5th field) is appended only when nonzero, so mundane weapons
    stay 4-field strings."""
    damage = (damage or "").strip()
    if not damage:
        return ""
    ability = ability if ability in _VALID_ABILITY else "str"
    category = category if category in ("simple", "martial") else ""
    try:
        bonus = int(bonus or 0)
    except (TypeError, ValueError):
        bonus = 0
    fields = [damage, (dtype or "").strip(), ability, category]
    if bonus:
        fields.append(str(bonus))
    return "|".join(fields)


def _raw_weapon(item):
    try:
        return (item["weapon"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return ""


def parse_weapon(item):
    """{damage, type, ability, category} from an item's packed `weapon` column, or
    None if the item isn't a weapon."""
    raw = _raw_weapon(item)
    if not raw:
        return None
    parts = (raw.split("|") + ["", "str", "", "0"])[:5]
    damage, dtype, ability, category, bonus = parts
    if not damage:
        return None
    try:
        bonus = int(bonus or 0)
    except (TypeError, ValueError):
        bonus = 0
    return {"damage": damage, "type": dtype,
            "ability": ability if ability in _VALID_ABILITY else "str",
            "category": category, "bonus": bonus}


def _double_dice(damage):
    """Double each dice term's count for a critical hit (5e: roll the damage dice
    twice; the flat modifier is *not* doubled). '1d8' -> '2d8', '2d6' -> '4d6'."""
    def repl(m):
        count = int(m.group(1)) if m.group(1) else 1
        return f"{count * 2}d{m.group(2)}"
    return _DICE_TERM.sub(repl, damage)


def _ability_mod(weapon, eff_abilities):
    """The ability modifier a weapon uses (finesse = the better of STR/DEX)."""
    a = weapon["ability"]
    if a == "finesse":
        return max(ability_modifier(eff_abilities["strength"]["score"]),
                   ability_modifier(eff_abilities["dexterity"]["score"]))
    return ability_modifier(eff_abilities[_ABILITY_COL.get(a, "strength")]["score"])


def weapon_is_proficient(creature, item, weapon):
    """Whether the creature's class is proficient with this weapon — its category in
    the class's simple/martial proficiencies, or a named-weapon match (e.g. a Rogue's
    'Longswords'). A creature with no class (NPC/monster) is assumed proficient."""
    if not creature["class_name"]:
        return True
    from models.proficiency import weapon_proficiencies  # local: avoid import cycle
    profs = [p.lower() for p in weapon_proficiencies(creature)]
    if weapon["category"] and weapon["category"] in profs:
        return True
    iname = (item["name"] or "").strip().lower().rstrip("s")
    for p in profs:
        if p in ("simple", "martial"):
            continue
        if p.rstrip("s") == iname:  # "Longswords" vs item "Longsword"
            return True
    return False


def weapon_attacks(creature, eff_abilities):
    """Attack rows for the creature's *equipped* weapons:
    [{name, type, ability, proficient, mod, attack, to_hit, damage}], where
    `to_hit` is a 'd20+N' expression, `damage` a 'NdM+mod' expression, and `crit`
    the same with the dice doubled (for a natural-20 hit)."""
    from models.inventory import list_items  # local: avoid import cycle
    pb = proficiency_bonus(creature["level"])
    out = []
    for item in list_items(creature["id"]):
        if not item["equipped"]:
            continue
        weapon = parse_weapon(item)
        if not weapon:
            continue
        mod = _ability_mod(weapon, eff_abilities)
        prof = weapon_is_proficient(creature, item, weapon)
        bonus = weapon["bonus"]
        atk = mod + (pb if prof else 0) + bonus
        flat = mod + bonus   # the magic bonus adds to damage too, but isn't doubled on a crit
        out.append({
            "name": item["name"], "type": weapon["type"],
            "ability": _ABILITY_LABEL.get(weapon["ability"], "STR"),
            "proficient": prof, "mod": mod, "attack": atk, "bonus": bonus,
            "to_hit": f"1d20{atk:+d}",
            "damage": weapon["damage"] + (f"{flat:+d}" if flat else ""),
            "crit": _double_dice(weapon["damage"]) + (f"{flat:+d}" if flat else ""),
        })
    return out
