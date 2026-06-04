"""Plain-English definitions for D&D jargon, surfaced as ⓘ hover tooltips.

`define(key)` returns a definition or None. Used by the `info` template macro
(templates/macros.html) so any term on any page can carry a tooltip — the app
teaches its own vocabulary to players new to D&D.
"""

_ABILITIES = {
    "strength": "Strength — physical power: melee attacks, lifting, and Athletics.",
    "dexterity": "Dexterity — agility and reflexes: AC, Stealth, ranged attacks, initiative.",
    "constitution": "Constitution — stamina and health: hit points and concentration.",
    "intelligence": "Intelligence — reasoning and memory: Arcana, Investigation.",
    "wisdom": "Wisdom — awareness and insight: Perception and many saving throws.",
    "charisma": "Charisma — force of personality: Persuasion, Deception, and many spellcasters.",
}

_ABBREVIATIONS = {
    "str": "strength", "dex": "dexterity", "con": "constitution",
    "int": "intelligence", "wis": "wisdom", "cha": "charisma",
}

GLOSSARY = {
    # Spell components
    "v": "Verbal — you must speak the spell's incantation aloud. Being gagged or silenced stops it.",
    "s": "Somatic — you must make gestures, so you need at least one free hand.",
    "m": "Material — you need specific physical items, usually covered by a component pouch or focus.",
    # Core mechanics
    "saving-throw": "Saving throw — a d20 roll a target makes to resist or reduce an effect (e.g. dodging a fireball).",
    "spell-attack": "Spell attack — roll d20 + your spell attack bonus against the target's AC to see if it hits.",
    "armor-class": "Armor Class (AC) — how hard a creature is to hit. An attack must roll this number or higher.",
    "hit-points": "Hit Points (HP) — a creature's health. At 0 HP it falls unconscious or dies.",
    "temp-hp": "Temporary HP — a buffer on top of your hit points (from some spells/abilities). Damage comes off temp HP first; they don't stack (keep the higher value) and aren't restored by healing.",
    "modifier": "Modifier — the +/- number derived from an ability score, added to related d20 rolls.",
    "hit-die": "Hit die — the die you roll for hit points each level (e.g. d8 for many classes). Level-up HP = that roll (or its average) + your Constitution modifier.",
    # Spell vocabulary
    "cantrip": "Cantrip — a level-0 spell you can cast at will, without spending a spell slot.",
    "spell-level": "Spell level (1–9) — a spell's power tier; casting it spends a spell slot of that level or higher.",
    "known": "Known — a spell in your repertoire. For prepare-casting classes you must still prepare it before you can cast it.",
    "prepared": "Prepared — a known spell you've readied (usually after a long rest) and can cast right now. Many classes can only cast prepared spells.",
    "casting-time": "Casting time — how long a spell takes: an action, bonus action, reaction, or longer.",
    "concentration": "Concentration — some spells last only while you focus; taking damage can break it.",
    "short-rest": "Short rest — a ~1 hour breather. In 5e you spend hit dice to heal; here it recovers about half of each character's missing HP.",
    "long-rest": "Long rest — ~8 hours of rest. Restores all hit points (and, in full 5e, spell slots and abilities).",
    "action": "Action — the main thing you do on your turn.",
    "bonus-action": "Bonus action — a quick extra action some abilities grant on your turn.",
    "reaction": "Reaction — an instant response triggered by an event, even on another creature's turn.",
    # Schools of magic
    "abjuration": "Abjuration — protective magic: shields, wards, and banishment.",
    "conjuration": "Conjuration — summoning creatures and objects, or teleporting.",
    "divination": "Divination — revealing information: secrets, the future, hidden things.",
    "enchantment": "Enchantment — influencing minds: charming or compelling creatures.",
    "evocation": "Evocation — channeling energy to deal damage (fire, lightning) or create effects like light.",
    "illusion": "Illusion — deceiving the senses with images, sounds, and false appearances.",
    "necromancy": "Necromancy — manipulating life force, death, and the undead.",
    "transmutation": "Transmutation — changing the properties of creatures, objects, or the environment.",
}

GLOSSARY.update(_ABILITIES)
for _abbr, _full in _ABBREVIATIONS.items():
    GLOSSARY[_abbr] = _ABILITIES[_full]


def define(key):
    """Return the definition for a term key, or None if we don't have one."""
    return GLOSSARY.get((key or "").strip().lower())
