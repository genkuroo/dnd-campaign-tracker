"""Weapon attacks — turn an equipped weapon item into an attack + damage roll.

A weapon's stats are packed into the item's `weapon` text column (migration 34) as
**"damage|type|ability|category"** — e.g. `"1d8|slashing|str|martial"` — mirroring
how `stat_bonuses` packs its data. An empty column means the item isn't a weapon.

Computed on read (nothing stored beyond the weapon stats themselves):
  - **To-hit** = d20 + ability mod + **proficiency bonus when proficient** (finally
    consuming the weapon-proficiency layer in models/proficiency).
  - **Damage** = the weapon's dice + the same ability mod.
  - **ability** is `str` (melee), `dex` (ranged), or `finesse` (best of STR/DEX).
"""
from models.creature import ability_modifier, proficiency_bonus

_VALID_ABILITY = ("str", "dex", "finesse")
_ABILITY_COL = {"str": "strength", "dex": "dexterity"}
_ABILITY_LABEL = {"str": "STR", "dex": "DEX", "finesse": "finesse"}


def pack_weapon(damage, dtype="", ability="str", category=""):
    """Build the packed `weapon` string; '' when there's no damage (not a weapon)."""
    damage = (damage or "").strip()
    if not damage:
        return ""
    ability = ability if ability in _VALID_ABILITY else "str"
    category = category if category in ("simple", "martial") else ""
    return "|".join([damage, (dtype or "").strip(), ability, category])


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
    parts = (raw.split("|") + ["", "str", ""])[:4]
    damage, dtype, ability, category = parts
    if not damage:
        return None
    return {"damage": damage, "type": dtype,
            "ability": ability if ability in _VALID_ABILITY else "str",
            "category": category}


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
    `to_hit` is a 'd20+N' expression and `damage` a 'NdM+mod' expression."""
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
        atk = mod + (pb if prof else 0)
        out.append({
            "name": item["name"], "type": weapon["type"],
            "ability": _ABILITY_LABEL.get(weapon["ability"], "STR"),
            "proficient": prof, "mod": mod, "attack": atk,
            "to_hit": f"1d20{atk:+d}",
            "damage": weapon["damage"] + (f"{mod:+d}" if mod else ""),
        })
    return out
