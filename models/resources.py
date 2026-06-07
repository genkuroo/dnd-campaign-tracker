"""Class resources: limited-use, rest-recharged pools (5e).

The non-spell cousin of models/spellcasting's slot tracker. A class grants pools
like **Rage**, **Ki**, **Channel Divinity**, **Lay on Hands**, **Action Surge** —
each with a *maximum* (by class + level) and a *recharge* (short or long rest).

Same shape as spell slots: the **maximum is computed on read** from the class
definition (data/classes.json `resources`); only the **expended** amount is stored
(`creature_resources`, migration 29). A long rest clears every pool; a short rest
clears only the ones flagged to recharge on a short rest (recharge == 'short', or
a `short_from_level` the creature has reached — e.g. Bard Font of Inspiration).

A resource's `max` is one of:
  - fixed(value)            — a flat number (Second Wind = 1)
  - level                   — = the creature's level (Ki, Sorcery Points)
  - level_times(factor)     — level × factor (Lay on Hands = 5 × level)
  - steps([[lvl, n], ...])  — the highest n whose lvl ≤ the creature's; -1 = ∞
  - ability_mod(ability, plus, min) — ability modifier (+ plus, floored at min)

`pool: true` marks an HP/point pool (Lay on Hands) rendered as a number with an
amount control instead of pips.
"""
from db import get_connection
from models.creature import ability_modifier
from models.classes import get_class
from models.inventory import effective_abilities

UNLIMITED = -1  # a `steps` value of -1 means the pool is unlimited (e.g. L20 Rage)


def _klass(creature):
    return get_class(creature["class_name"]) if creature["class_name"] else None


def _max_for(resource, creature, eff_abilities):
    """Compute a resource's maximum for this creature (UNLIMITED for an ∞ pool)."""
    spec = resource.get("max", {})
    kind = spec.get("type")
    lvl = max(1, int(creature["level"]))
    if kind == "fixed":
        return int(spec.get("value", 0))
    if kind == "level":
        return lvl
    if kind == "level_times":
        return lvl * int(spec.get("factor", 1))
    if kind == "steps":
        value = 0
        for min_lvl, n in spec.get("steps", []):
            if lvl >= min_lvl:
                value = n
        return value
    if kind == "ability_mod":
        mod = ability_modifier(eff_abilities[spec["ability"]]["score"])
        return max(int(spec.get("min", 0)), mod + int(spec.get("plus", 0)))
    return 0


def _recharges_on_short(resource, creature):
    """True if a short rest refills this resource (its own short recharge, or a
    `short_from_level` the creature has reached)."""
    if resource.get("recharge") == "short":
        return True
    sfl = resource.get("short_from_level")
    return bool(sfl) and int(creature["level"]) >= int(sfl)


def class_resources(creature):
    """The resource specs this creature's class grants at its level (past each
    one's min_level), in declared order. Empty for the classless / resourceless."""
    klass = _klass(creature)
    if not klass:
        return []
    lvl = int(creature["level"])
    return [r for r in klass.get("resources", []) if lvl >= int(r.get("min_level", 1))]


def _expended(creature_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT resource_key, expended FROM creature_resources WHERE creature_id = ?",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()
    return {r["resource_key"]: r["expended"] for r in rows}


def resource_rows(creature, eff_abilities=None):
    """Display rows for a creature's class resources:
    [{key, name, total, available, expended, unlimited, pool, short}], skipping
    pools that compute to 0 at this level. `total` is UNLIMITED for an ∞ pool."""
    if eff_abilities is None:
        eff_abilities = effective_abilities(creature)
    used = _expended(creature["id"])
    out = []
    for r in class_resources(creature):
        total = _max_for(r, creature, eff_abilities)
        if total == 0:
            continue
        if total == UNLIMITED:
            out.append({"key": r["key"], "name": r["name"], "total": UNLIMITED,
                        "available": UNLIMITED, "expended": 0, "unlimited": True,
                        "pool": bool(r.get("pool")),
                        "short": _recharges_on_short(r, creature)})
            continue
        exp = min(max(0, used.get(r["key"], 0)), total)
        out.append({"key": r["key"], "name": r["name"], "total": total,
                    "available": total - exp, "expended": exp, "unlimited": False,
                    "pool": bool(r.get("pool")),
                    "short": _recharges_on_short(r, creature)})
    return out


def _resource(creature, key):
    """The (spec, row) for one resource key on a creature, or (None, None)."""
    eff = effective_abilities(creature)
    for r in class_resources(creature):
        if r["key"] == key:
            return r, next((row for row in resource_rows(creature, eff)
                            if row["key"] == key), None)
    return None, None


def _set_expended(creature_id, key, expended):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO creature_resources (creature_id, resource_key, expended) "
            "VALUES (?, ?, ?) ON CONFLICT(creature_id, resource_key) "
            "DO UPDATE SET expended = excluded.expended",
            (creature_id, key, int(expended)),
        )
        conn.commit()
    finally:
        conn.close()


def spend_resource(creature, key, amount=1):
    """Expend `amount` of a resource (clamped to what's available). No-op for an
    unlimited pool. Returns True if anything was spent."""
    spec, row = _resource(creature, key)
    if row is None or row["unlimited"] or amount <= 0:
        return False
    take = min(amount, row["available"])
    if take <= 0:
        return False
    _set_expended(creature["id"], key, row["expended"] + take)
    return True


def restore_resource(creature, key, amount=1):
    """Recover `amount` of a resource (clamped at 0). Returns True if anything was
    restored."""
    spec, row = _resource(creature, key)
    if row is None or row["unlimited"] or amount <= 0:
        return False
    give = min(amount, row["expended"])
    if give <= 0:
        return False
    _set_expended(creature["id"], key, row["expended"] - give)
    return True


def rest(creature, kind):
    """Recharge a creature's resources for a rest. A long rest refills every pool;
    a short rest refills only the short-recharging ones. Clears their stored
    expended rows."""
    if kind not in ("short", "long"):
        return
    keys = [row["key"] for row in resource_rows(creature)
            if kind == "long" or row["short"]]
    if not keys:
        return
    conn = get_connection()
    try:
        conn.executemany(
            "DELETE FROM creature_resources WHERE creature_id = ? AND resource_key = ?",
            [(creature["id"], k) for k in keys],
        )
        conn.commit()
    finally:
        conn.close()
