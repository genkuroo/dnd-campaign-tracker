"""The combat tracker (Phase 6).

A `combat` is a live fight; `combatants` are the creatures in it. Combatants
snapshot their own HP/AC when added, so multiple instances of one stat block
(Goblin 1..4) take damage independently and the fight never mutates the
underlying character sheets — the tracker is a scratch space. Operates on
creatures generically, so PCs and monsters share one tracker (CLAUDE.md).
"""
import random

from db import get_connection
from models.creature import ability_modifier
from models.inventory import effective_ac, equipped_stat_bonuses

# The 5e conditions, in alphabetical order (exhaustion's levels are out of scope).
CONDITIONS = [
    "blinded", "charmed", "deafened", "frightened", "grappled", "incapacitated",
    "invisible", "paralyzed", "petrified", "poisoned", "prone", "restrained",
    "stunned", "unconscious",
]


# --- combats ---------------------------------------------------------------

def create_combat(name=""):
    name = (name or "").strip() or "Combat"
    conn = get_connection()
    try:
        cur = conn.execute("INSERT INTO combats (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_combats(status=None):
    """Combats (newest first) with a combatant count; optionally filter by
    status ('active' | 'ended')."""
    conn = get_connection()
    try:
        sql = (
            "SELECT c.*, COUNT(m.id) AS combatant_count "
            "FROM combats c LEFT JOIN combatants m ON m.combat_id = c.id "
        )
        params = ()
        if status:
            sql += "WHERE c.status = ? "
            params = (status,)
        sql += "GROUP BY c.id ORDER BY c.created_at DESC"
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def set_status(combat_id, status):
    """Archive ('ended') or reopen ('active') a combat — history, not deletion."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE combats SET status = ? WHERE id = ?", (status, combat_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_combat(combat_id):
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM combats WHERE id = ?", (combat_id,)).fetchone()
    finally:
        conn.close()


def delete_combat(combat_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM combats WHERE id = ?", (combat_id,))
        conn.commit()
    finally:
        conn.close()


# --- combatants ------------------------------------------------------------

def list_combatants(combat_id):
    """Combatants in initiative order: highest initiative first, DEX as the
    tiebreak, then insertion order."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT m.*, c.avatar AS avatar, c.kind AS kind, "
            "c.concentration AS concentration "
            "FROM combatants m LEFT JOIN creatures c ON c.id = m.creature_id "
            "WHERE m.combat_id = ?",
            (combat_id,),
        ).fetchall()
    finally:
        conn.close()
    return sorted(rows, key=lambda r: (-r["initiative"], -r["dex_mod"], r["id"]))


def get_combatant(combatant_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM combatants WHERE id = ?", (combatant_id,)
        ).fetchone()
    finally:
        conn.close()


def add_combatant(combat_id, creature, name=None):
    """Add one combatant from a creature row, snapshotting its current stats —
    including AC, DEX, and walking speed (with race + class/feat modifiers)."""
    from models.movement import effective_speed  # local: avoid import cycle
    dex = creature["dexterity"] + equipped_stat_bonuses(creature["id"]).get("dexterity", 0)
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO combatants "
            "(combat_id, creature_id, name, max_hp, current_hp, armor_class, dex_mod, speed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (combat_id, creature["id"], name or creature["name"],
             creature["max_hp"], creature["current_hp"], effective_ac(creature),
             ability_modifier(dex), effective_speed(creature)),
        )
        conn.commit()
    finally:
        conn.close()


def add_creature(combat_id, creature, quantity=1):
    """Add `quantity` combatants from one creature; multiples are numbered
    (Goblin 1, Goblin 2, …) so they're distinguishable in the tracker."""
    quantity = max(1, int(quantity or 1))
    for i in range(quantity):
        name = creature["name"] if quantity == 1 else f"{creature['name']} {i + 1}"
        add_combatant(combat_id, creature, name)


def remove_combatant(combatant_id):
    conn = get_connection()
    try:
        # If it was the active turn, clear the pointer so the tracker recovers.
        conn.execute(
            "UPDATE combats SET turn_combatant_id = NULL "
            "WHERE turn_combatant_id = ?",
            (combatant_id,),
        )
        conn.execute("DELETE FROM combatants WHERE id = ?", (combatant_id,))
        conn.commit()
    finally:
        conn.close()


def set_initiative(combatant_id, value):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE combatants SET initiative = ? WHERE id = ?",
            (int(value), combatant_id),
        )
        conn.commit()
    finally:
        conn.close()


def roll_initiative_all(combat_id):
    """Roll d20 + DEX modifier initiative for every combatant in the fight."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, dex_mod FROM combatants WHERE combat_id = ?", (combat_id,)
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE combatants SET initiative = ? WHERE id = ?",
                (random.randint(1, 20) + r["dex_mod"], r["id"]),
            )
        # Mark it rolled so the UI can collapse the prominent button into a re-roll.
        conn.execute(
            "UPDATE combats SET initiative_rolled = 1 WHERE id = ?", (combat_id,)
        )
        conn.commit()
    finally:
        conn.close()


def apply_hp(combatant_id, delta):
    """Apply damage (delta < 0) or healing (delta > 0). Damage is absorbed by
    temp HP first; healing is capped at max HP and never touches temp HP.

    Death saves (5e): taking damage *while already at 0 HP* adds a death-save
    failure; healing back above 0 clears the death-save counters (you're conscious
    again)."""
    c = get_combatant(combatant_id)
    if c is None:
        return
    temp, cur = c["temp_hp"], c["current_hp"]
    succ, fail = c["death_successes"], c["death_failures"]
    was_down = cur == 0
    if delta < 0:
        dmg = -delta
        absorbed = min(temp, dmg)
        temp -= absorbed
        dmg -= absorbed
        if was_down and dmg > 0:        # a hit while dying = one failed death save
            fail = min(3, fail + 1)
        cur = max(0, cur - dmg)
    else:
        cur = min(c["max_hp"], cur + delta)
        if was_down and cur > 0:        # healed back up — no longer dying
            succ, fail = 0, 0
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE combatants SET current_hp = ?, temp_hp = ?, "
            "death_successes = ?, death_failures = ? WHERE id = ?",
            (cur, temp, succ, fail, combatant_id),
        )
        conn.commit()
    finally:
        conn.close()


def death_state(combatant):
    """Derived life state of a combatant: 'alive' (HP > 0), else 'dead' (3 failed
    saves), 'stable' (3 successes), or 'dying'. Computed, never stored."""
    if combatant["current_hp"] > 0:
        return "alive"
    if combatant["death_failures"] >= 3:
        return "dead"
    if combatant["death_successes"] >= 3:
        return "stable"
    return "dying"


def set_death_save(combatant_id, kind, delta):
    """Manually nudge a death-save counter (`kind` 'success'|'failure', `delta` ±1),
    clamped to 0..3."""
    col = "death_successes" if kind == "success" else "death_failures"
    c = get_combatant(combatant_id)
    if c is None:
        return
    new = max(0, min(3, c[col] + int(delta)))
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE combatants SET {col} = ? WHERE id = ?", (new, combatant_id))
        conn.commit()
    finally:
        conn.close()


def clear_death_saves(combatant_id):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE combatants SET death_successes = 0, death_failures = 0 WHERE id = ?",
            (combatant_id,))
        conn.commit()
    finally:
        conn.close()


def roll_death_save(combatant_id):
    """Roll a death saving throw (d20, no modifier). 10+ = a success; under 10 = a
    failure; a nat 20 revives the creature at 1 HP (and clears saves); a nat 1 counts
    as two failures. Returns {roll, outcome, successes, failures, current_hp} or None."""
    c = get_combatant(combatant_id)
    if c is None or c["current_hp"] > 0:
        return None
    roll = random.randint(1, 20)
    succ, fail, cur = c["death_successes"], c["death_failures"], c["current_hp"]
    if roll == 20:
        cur, succ, fail, outcome = 1, 0, 0, "revive"     # back up at 1 HP
    elif roll == 1:
        fail, outcome = min(3, fail + 2), "crit-fail"     # two failures
    elif roll >= 10:
        succ, outcome = min(3, succ + 1), "success"
    else:
        fail, outcome = min(3, fail + 1), "failure"
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE combatants SET current_hp = ?, death_successes = ?, "
            "death_failures = ? WHERE id = ?", (cur, succ, fail, combatant_id))
        conn.commit()
    finally:
        conn.close()
    return {"roll": roll, "outcome": outcome, "successes": succ,
            "failures": fail, "current_hp": cur}


def set_temp_hp(combatant_id, value):
    """Set temp HP. 5e: temp HP doesn't stack — you take the higher value, so
    this is a set, not an add."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE combatants SET temp_hp = ? WHERE id = ?",
            (max(0, int(value or 0)), combatant_id),
        )
        conn.commit()
    finally:
        conn.close()


def _conditions_set(value):
    return {c.strip() for c in (value or "").split(",") if c.strip()}


def toggle_condition(combatant_id, condition):
    if condition not in CONDITIONS:
        return
    c = get_combatant(combatant_id)
    if c is None:
        return
    current = _conditions_set(c["conditions"])
    current.symmetric_difference_update({condition})
    ordered = [x for x in CONDITIONS if x in current]
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE combatants SET conditions = ? WHERE id = ?",
            (", ".join(ordered), combatant_id),
        )
        conn.commit()
    finally:
        conn.close()


# --- turn order + rests ----------------------------------------------------

def next_turn(combat_id):
    """Advance to the next combatant in initiative order, bumping the round when
    the order wraps around. Starting from no active turn begins at the top."""
    combat = get_combat(combat_id)
    order = list_combatants(combat_id)
    if combat is None or not order:
        return
    ids = [c["id"] for c in order]
    current = combat["turn_combatant_id"]
    new_round = combat["round"]
    if current not in ids:
        new_id = ids[0]
    else:
        i = ids.index(current)
        if i + 1 < len(ids):
            new_id = ids[i + 1]
        else:
            new_id = ids[0]
            new_round += 1
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE combats SET turn_combatant_id = ?, round = ? WHERE id = ?",
            (new_id, new_round, combat_id),
        )
        conn.commit()
    finally:
        conn.close()


def rest(combat_id, kind):
    """A short or long rest. Long rest = full HP, drop temp HP, clear conditions
    (a fresh start). Short rest = clear temp HP only (we don't track hit dice)."""
    conn = get_connection()
    try:
        if kind == "long":
            conn.execute(
                "UPDATE combatants SET current_hp = max_hp, temp_hp = 0, conditions = '' "
                "WHERE combat_id = ?",
                (combat_id,),
            )
        else:
            conn.execute(
                "UPDATE combatants SET temp_hp = 0 WHERE combat_id = ?", (combat_id,)
            )
        conn.commit()
    finally:
        conn.close()
