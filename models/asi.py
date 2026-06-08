"""Ability Score Improvements (ASI): the permanent +2/+1 ability bumps a class
grants at its ASI levels (5e).

Each "Ability Score Improvement" feature a class unlocks (levels 4/8/12/16/19, plus
Fighter's extra at 6/14 and Rogue's at 10 — all already in data/classes.json's
`features`) grants **2 points** to raise ability scores, capped at 20 per ability.
A player may spend a slot as +2 to one ability or +1 to two; across multiple slots
the budget is just `2 × slots` points spent freely in +1 steps (the per-slot rule
collapses to the same thing for a tracker).

Same compute-on-read shape as the rest of the class layer: the **budget** is derived
from the class + level; only the **allocation** is stored (`creature_asi`, migration
30). Effective ability scores fold the allocation in on read
(models/inventory.effective_abilities), so the base sheet is never mutated.

(Feats — taking a feat *instead* of an ASI — aren't modelled yet; this is the stat
bump half of the roadmap item.)
"""
from db import get_connection
from models.classes import class_features

POINTS_PER_SLOT = 2
ABILITY_CAP = 20
_ABILITY_COLS = ("strength", "dexterity", "constitution",
                 "intelligence", "wisdom", "charisma")
_ASI_FEATURE = "Ability Score Improvement"


def asi_slots(slug, level, subclass=None):
    """How many ASI opportunities a class has unlocked at `level` — the count of
    'Ability Score Improvement' features at or below the creature's level. 0 for the
    classless."""
    if not slug:
        return 0
    return sum(1 for f in class_features(slug, level, subclass)
               if f["name"] == _ASI_FEATURE)


def asi_bonuses(creature_id):
    """{ability_col: bonus} of a creature's allocated ASI points (non-zero only)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT ability, bonus FROM creature_asi "
            "WHERE creature_id = ? AND bonus != 0",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()
    return {r["ability"]: r["bonus"] for r in rows}


def asi_summary(creature):
    """{slots, budget, spent, remaining} for a creature — the budget the class+level
    grants vs. how many points are allocated. `remaining` floors at 0 (a stale
    over-allocation after a level/class change just shows 0 left, never negative)."""
    slots = asi_slots(creature["class_name"], creature["level"], creature["subclass"])
    budget = POINTS_PER_SLOT * slots
    spent = sum(asi_bonuses(creature["id"]).values())
    return {"slots": slots, "budget": budget, "spent": spent,
            "remaining": max(0, budget - spent)}


def adjust_asi(creature, ability, delta):
    """Raise (+1) or lower (-1) a single ability's ASI bonus, respecting the budget
    and the 20 cap. Returns the new bonus for that ability (unchanged if the move was
    illegal)."""
    if ability not in _ABILITY_COLS:
        return None
    cur = asi_bonuses(creature["id"]).get(ability, 0)
    if delta > 0:
        if asi_summary(creature)["remaining"] <= 0:
            return cur
        if creature[ability] + cur >= ABILITY_CAP:
            return cur
        new = cur + 1
    elif delta < 0:
        if cur <= 0:
            return cur
        new = cur - 1
    else:
        return cur
    _set_bonus(creature["id"], ability, new)
    return new


def _set_bonus(creature_id, ability, bonus):
    """Upsert one ability's ASI bonus; a 0 deletes the row (keeps the table sparse)."""
    conn = get_connection()
    try:
        if bonus:
            conn.execute(
                "INSERT INTO creature_asi (creature_id, ability, bonus) "
                "VALUES (?, ?, ?) ON CONFLICT(creature_id, ability) "
                "DO UPDATE SET bonus = excluded.bonus",
                (creature_id, ability, int(bonus)),
            )
        else:
            conn.execute(
                "DELETE FROM creature_asi WHERE creature_id = ? AND ability = ?",
                (creature_id, ability),
            )
        conn.commit()
    finally:
        conn.close()
