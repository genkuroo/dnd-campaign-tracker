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
    "spell-attack": "Spell attack — roll d20 + your spell attack bonus (proficiency bonus + spellcasting ability) against the target's AC to see if it hits.",
    "spell-save-dc": "Spell save DC — the number a target must beat on its saving throw to resist your spell. = 8 + proficiency bonus + your spellcasting ability modifier.",
    "spell-slot": "Spell slot — a charge you spend to cast a leveled spell; you have a limited number per spell level. Cantrips are free. A long rest restores them.",
    "armor-class": "Armor Class (AC) — how hard a creature is to hit. An attack must roll this number or higher.",
    "hit-points": "Hit Points (HP) — a creature's health. At 0 HP it falls unconscious or dies.",
    "temp-hp": "Temporary HP — a buffer on top of your hit points (from some spells/abilities). Damage comes off temp HP first; they don't stack (keep the higher value) and aren't restored by healing.",
    "modifier": "Modifier — the +/- number derived from an ability score, added to related d20 rolls.",
    "proficiency": "Proficiency — training in a particular save or skill. When you're proficient, you add your proficiency bonus to that roll.",
    "proficiency-bonus": "Proficiency bonus — one number that grows with level (+2 at levels 1–4, up to +6 at 17–20), added to every save, skill, and attack you're proficient in.",
    "skill": "Skill — a specific kind of ability check (Stealth, Perception, Persuasion…), each tied to one ability. If you're proficient in it, add your proficiency bonus.",
    "expertise": "Expertise — for a chosen skill you're proficient in, add **double** your proficiency bonus (a Rogue/Bard specialty).",
    "half-proficiency": "Half proficiency — add half your proficiency bonus (rounded down) to checks you're not proficient in. Bards get this on every check (Jack of All Trades); Champion fighters on STR/DEX/CON checks (Remarkable Athlete, rounded up).",
    "saving-throw-prof": "Saving throw proficiency — your class makes you reliably good at resisting two kinds of effect (e.g. a Barbarian's STR & CON saves), adding your proficiency bonus.",
    "hit-die": "Hit die — the die you roll for hit points each level (e.g. d8 for many classes). Level-up HP = that roll (or its average) + your Constitution modifier.",
    "race": "Race / species — what kind of being your character is (Elf, Dwarf, Human…). It grants ability-score increases, a base speed, a size, and special traits; many have subraces.",
    "ability-score-improvement": "Ability Score Improvement (ASI) — at certain levels (4, 8, 12, 16, 19; a few classes get extra) you gain 2 points to raise your ability scores, as +2 to one or +1 to two, capped at 20.",
    "feat": "Feat — a special talent you can take instead of an Ability Score Improvement, granting a distinctive ability (extra reactions, combat tricks, skill boosts…).",
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
