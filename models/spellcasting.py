"""Spellcasting: the casting *stats* and the spell-slot *resource* (5e).

Two computed layers on top of the spellbook (models/spellbook.py):

  - **Stats** — a caster's **spell attack bonus** (`proficiency bonus + ability
    modifier`) and **save DC** (`8 + proficiency bonus + ability modifier`), where
    the ability comes from the class (`spell_ability` in data/classes.json). No
    storage; computed on read like effective AC.
  - **Slots** — leveled spells spend a slot of their level; cantrips are free.
    A creature's *maximum* slots come from its class's caster type + level (the
    tables below); only *expended* slots are stored (`creature_spell_slots`,
    migration 25). A long rest clears all; a Warlock's pact slots also clear on a
    short rest.

Caster types (data/classes.json `caster_type`): 'full' (Bard/Cleric/Druid/
Sorcerer/Wizard), 'half' (Paladin/Ranger), 'pact' (Warlock), 'none'.
"""
from db import get_connection
from models.creature import ability_modifier, proficiency_bonus
from models.classes import get_class

# Full-caster slots by class level (rows 1..20), columns = spell levels 1..9.
_FULL = [
    [2, 0, 0, 0, 0, 0, 0, 0, 0],
    [3, 0, 0, 0, 0, 0, 0, 0, 0],
    [4, 2, 0, 0, 0, 0, 0, 0, 0],
    [4, 3, 0, 0, 0, 0, 0, 0, 0],
    [4, 3, 2, 0, 0, 0, 0, 0, 0],
    [4, 3, 3, 0, 0, 0, 0, 0, 0],
    [4, 3, 3, 1, 0, 0, 0, 0, 0],
    [4, 3, 3, 2, 0, 0, 0, 0, 0],
    [4, 3, 3, 3, 1, 0, 0, 0, 0],
    [4, 3, 3, 3, 2, 0, 0, 0, 0],
    [4, 3, 3, 3, 2, 1, 0, 0, 0],
    [4, 3, 3, 3, 2, 1, 0, 0, 0],
    [4, 3, 3, 3, 2, 1, 1, 0, 0],
    [4, 3, 3, 3, 2, 1, 1, 0, 0],
    [4, 3, 3, 3, 2, 1, 1, 1, 0],
    [4, 3, 3, 3, 2, 1, 1, 1, 0],
    [4, 3, 3, 3, 2, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 2, 1, 1],
]
# Half-caster slots (Paladin/Ranger), columns = spell levels 1..5 (no slots at L1).
_HALF = [
    [0, 0, 0, 0, 0],
    [2, 0, 0, 0, 0],
    [3, 0, 0, 0, 0],
    [3, 0, 0, 0, 0],
    [4, 2, 0, 0, 0],
    [4, 2, 0, 0, 0],
    [4, 3, 0, 0, 0],
    [4, 3, 0, 0, 0],
    [4, 3, 2, 0, 0],
    [4, 3, 2, 0, 0],
    [4, 3, 3, 0, 0],
    [4, 3, 3, 0, 0],
    [4, 3, 3, 1, 0],
    [4, 3, 3, 1, 0],
    [4, 3, 3, 2, 0],
    [4, 3, 3, 2, 0],
    [4, 3, 3, 3, 1],
    [4, 3, 3, 3, 1],
    [4, 3, 3, 3, 2],
    [4, 3, 3, 3, 2],
]
# Warlock pact magic by class level: (number of slots, slot level). All slots are
# the same level and recharge on a short rest.
_PACT = [
    (1, 1), (2, 1), (2, 2), (2, 2), (2, 3), (2, 3), (2, 4), (2, 4), (2, 5), (2, 5),
    (3, 5), (3, 5), (3, 5), (3, 5), (3, 5), (3, 5), (4, 5), (4, 5), (4, 5), (4, 5),
]


def _klass(creature):
    return get_class(creature["class_name"]) if creature["class_name"] else None


def caster_type(creature):
    """'full' | 'half' | 'pact' | 'none' (or '' for a classless creature)."""
    klass = _klass(creature)
    return klass.get("caster_type", "none") if klass else ""


def spellcasting_ability(creature):
    """The ability column a creature casts with ('' = non-caster), from its class."""
    klass = _klass(creature)
    return klass.get("spell_ability", "") if klass else ""


def spell_stats(creature, eff_abilities):
    """{'ability', 'mod', 'attack', 'dc'} for a caster, or None for a non-caster.
    `eff_abilities` is the effective-ability map (so item bonuses count)."""
    col = spellcasting_ability(creature)
    if not col:
        return None
    pb = proficiency_bonus(creature["level"])
    mod = ability_modifier(eff_abilities[col]["score"])
    return {"ability": col, "mod": mod, "attack": pb + mod, "dc": 8 + pb + mod}


def set_concentration(creature_id, label):
    """Set (or replace) the concentration spell a creature is maintaining. 5e allows
    only one at a time, so this overwrites; '' drops it."""
    conn = get_connection()
    try:
        conn.execute("UPDATE creatures SET concentration = ? WHERE id = ?",
                     ((label or "").strip(), creature_id))
        conn.commit()
    finally:
        conn.close()


def drop_concentration(creature_id):
    set_concentration(creature_id, "")


def concentration_dc(damage):
    """The CON-save DC to keep concentration after taking `damage`: 10, or half the
    damage taken (rounded down), whichever is higher."""
    return max(10, int(damage) // 2)


def is_prepared_caster(creature):
    """True for a prepared caster (Cleric/Druid/Wizard/Paladin — prepare a subset of
    a large list each day) vs a known caster (Bard/Sorcerer/Ranger/Warlock — learn a
    fixed set). From `prepared_caster` in data/classes.json; False for non-casters."""
    klass = _klass(creature)
    return bool(klass.get("prepared_caster")) if klass else False


def _table_at(arr, level):
    """The level-indexed value from a 20-long class table (cantrips_known /
    spells_known), or None if the class has no such table."""
    if not arr:
        return None
    return arr[max(1, min(20, int(level))) - 1]


def spell_limits(creature, eff_abilities):
    """Spell-count limits for a caster, or None for a non-caster. Shape:
      {'mode': 'prepared'|'known',
       'cantrips': {'count','max'} | None,     # None if the class has no cantrips
       'leveled':  {'count','max','label'}}    # label = 'prepared' | 'known'
    Counts come from the creature's *own spellbook* (item-granted spells don't count
    toward a limit). A `max` of None means the class publishes no cap (we don't
    invent one). Guided, not enforced — the UI flags going over, adding still works."""
    klass = _klass(creature)
    if not klass or caster_type(creature) in ("", "none"):
        return None
    from models.spellbook import creature_spells  # local: avoid import cycle
    known = creature_spells(creature["id"])
    cantrip_count = sum(1 for s in known if s["level"] == 0)
    leveled = [s for s in known if s["level"] >= 1]
    lvl = creature["level"]

    cmax = _table_at(klass.get("cantrips_known"), lvl)
    cantrips = ({"count": cantrip_count, "max": cmax}
                if klass.get("cantrips_known") else None)

    if is_prepared_caster(creature):
        col = spellcasting_ability(creature)
        mod = ability_modifier(eff_abilities[col]["score"]) if col else 0
        # prepared = ability mod + caster level (full) or half level rounded down
        # (Paladin); minimum 1.
        base = lvl if caster_type(creature) == "full" else lvl // 2
        leveled_block = {"count": sum(1 for s in leveled if s["prepared"]),
                         "max": max(1, mod + base), "label": "prepared"}
    else:
        leveled_block = {"count": len(leveled),
                         "max": _table_at(klass.get("spells_known"), lvl),
                         "label": "known"}
    return {"mode": "prepared" if is_prepared_caster(creature) else "known",
            "cantrips": cantrips, "leveled": leveled_block}


def max_slots(creature):
    """{slot_level: count} of a creature's maximum spell slots (only non-zero
    levels), from its caster type + level. Empty for non-casters."""
    ct = caster_type(creature)
    lvl = max(1, min(20, int(creature["level"])))
    if ct == "full":
        row = _FULL[lvl - 1]
        return {i + 1: n for i, n in enumerate(row) if n}
    if ct == "half":
        row = _HALF[lvl - 1]
        return {i + 1: n for i, n in enumerate(row) if n}
    if ct == "pact":
        count, slot_level = _PACT[lvl - 1]
        return {slot_level: count} if count else {}
    return {}


def used_slots(creature_id):
    """{slot_level: used} expended-slot counts for a creature."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT slot_level, used FROM creature_spell_slots WHERE creature_id = ?",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()
    return {r["slot_level"]: r["used"] for r in rows}


def slot_rows(creature):
    """Per-slot-level display rows: [{level, total, used, available}], only for
    levels the creature actually has. `pact` is flagged separately by caster_type."""
    totals = max_slots(creature)
    used = used_slots(creature["id"])
    out = []
    for level in sorted(totals):
        total = totals[level]
        u = min(used.get(level, 0), total)  # clamp in case the table shrank (level loss)
        out.append({"level": level, "total": total, "used": u, "available": total - u})
    return out


def spend_slot(creature_id, slot_level):
    """Expend one slot of `slot_level` (cast a leveled spell). Returns True if a
    slot was available, False if none left. Capped at the creature's maximum."""
    creature = _slot_owner(creature_id)
    if creature is None:
        return False
    total = max_slots(creature).get(int(slot_level), 0)
    cur = used_slots(creature_id).get(int(slot_level), 0)
    if cur >= total:
        return False
    _set_used(creature_id, slot_level, cur + 1)
    return True


def restore_slot(creature_id, slot_level):
    """Recover one expended slot of `slot_level` (clamped at 0)."""
    cur = used_slots(creature_id).get(int(slot_level), 0)
    if cur <= 0:
        return
    _set_used(creature_id, slot_level, cur - 1)


def restore_all_slots(creature_id):
    """A long rest: clear every expended slot for the creature."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM creature_spell_slots WHERE creature_id = ?", (creature_id,)
        )
        conn.commit()
    finally:
        conn.close()


def restore_pact_slots(creature_id):
    """A short rest only recharges Warlock pact slots; everyone else keeps theirs."""
    creature = _slot_owner(creature_id)
    if creature is not None and caster_type(creature) == "pact":
        restore_all_slots(creature_id)


def _slot_owner(creature_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT id, level, class_name FROM creatures WHERE id = ?", (creature_id,)
        ).fetchone()
    finally:
        conn.close()


def _set_used(creature_id, slot_level, used):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO creature_spell_slots (creature_id, slot_level, used) "
            "VALUES (?, ?, ?) ON CONFLICT(creature_id, slot_level) "
            "DO UPDATE SET used = excluded.used",
            (creature_id, int(slot_level), int(used)),
        )
        conn.commit()
    finally:
        conn.close()
