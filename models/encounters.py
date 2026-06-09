"""Saved encounters — named groups of monsters (Phase 5).

An encounter is a reusable roster of monsters ('Goblin x4, Hobgoblin x1') the DM
assembles ahead of time and later loads into the combat tracker (Phase 6). Each
member is a creature_id + quantity, so the same bestiary stat block backs every
copy of a monster in the fight (the creature engine, reused — CLAUDE.md).
"""
from db import get_connection


def create_encounter(name):
    """Create a named encounter; returns its id, or None if the name is blank."""
    name = (name or "").strip()
    if not name:
        return None
    conn = get_connection()
    try:
        cur = conn.execute("INSERT INTO encounters (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_encounters():
    """All encounters (newest first) with a member count + total creature tally."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT e.*, "
            "  COUNT(m.id) AS member_count, "
            "  COALESCE(SUM(m.quantity), 0) AS total_creatures "
            "FROM encounters e "
            "LEFT JOIN encounter_members m ON m.encounter_id = e.id "
            "GROUP BY e.id ORDER BY e.created_at DESC"
        ).fetchall()
    finally:
        conn.close()


def get_encounter(encounter_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM encounters WHERE id = ?", (encounter_id,)
        ).fetchone()
    finally:
        conn.close()


def rename_encounter(encounter_id, name):
    name = (name or "").strip()
    if not name:
        return
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE encounters SET name = ? WHERE id = ?", (name, encounter_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_encounter(encounter_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM encounters WHERE id = ?", (encounter_id,))
        conn.commit()
    finally:
        conn.close()


def encounter_members(encounter_id):
    """Members resolved against their creature, with the stats the combat tracker
    will want (HP/AC). Ordered by creature name."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT m.id, m.creature_id, m.quantity, "
            "  c.name, c.max_hp, c.armor_class, c.kind, c.cr "
            "FROM encounter_members m "
            "JOIN creatures c ON c.id = m.creature_id "
            "WHERE m.encounter_id = ? "
            "ORDER BY c.name COLLATE NOCASE",
            (encounter_id,),
        ).fetchall()
    finally:
        conn.close()


def add_member(encounter_id, creature_id, quantity=1):
    """Add a monster to an encounter. If it's already a member, bump the quantity
    instead of adding a duplicate row."""
    quantity = max(1, int(quantity or 1))
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id, quantity FROM encounter_members "
            "WHERE encounter_id = ? AND creature_id = ?",
            (encounter_id, creature_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE encounter_members SET quantity = ? WHERE id = ?",
                (existing["quantity"] + quantity, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO encounter_members (encounter_id, creature_id, quantity) "
                "VALUES (?, ?, ?)",
                (encounter_id, creature_id, quantity),
            )
        conn.commit()
    finally:
        conn.close()


def set_member_quantity(member_id, quantity):
    """Set a member's quantity; drop the member entirely if it falls below 1."""
    quantity = int(quantity or 0)
    conn = get_connection()
    try:
        if quantity < 1:
            conn.execute("DELETE FROM encounter_members WHERE id = ?", (member_id,))
        else:
            conn.execute(
                "UPDATE encounter_members SET quantity = ? WHERE id = ?",
                (quantity, member_id),
            )
        conn.commit()
    finally:
        conn.close()


def remove_member(member_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM encounter_members WHERE id = ?", (member_id,))
        conn.commit()
    finally:
        conn.close()


# --- encounter difficulty (the DMG XP-budget calculator) -------------------

# DMG XP thresholds *per character*, by level: (easy, medium, hard, deadly).
_THRESHOLDS = {
    1: (25, 50, 75, 100),      2: (50, 100, 150, 200),    3: (75, 150, 225, 400),
    4: (125, 250, 375, 500),   5: (250, 500, 750, 1100),  6: (300, 600, 900, 1400),
    7: (350, 750, 1100, 1700), 8: (450, 900, 1400, 2100), 9: (550, 1100, 1600, 2400),
    10: (600, 1200, 1900, 2800),  11: (800, 1600, 2400, 3600),
    12: (1000, 2000, 3000, 4500), 13: (1100, 2200, 3400, 5100),
    14: (1250, 2500, 3800, 5700), 15: (1400, 2800, 4300, 6400),
    16: (1600, 3200, 4800, 7200), 17: (2000, 3900, 5900, 8800),
    18: (2100, 4200, 6300, 9500), 19: (2400, 4900, 7300, 10900),
    20: (2800, 5700, 8500, 12700),
}


def encounter_multiplier(count):
    """The DMG 'number of monsters' multiplier on total XP — more monsters hit
    harder than their raw XP suggests (action economy)."""
    if count <= 1:
        return 1.0
    if count == 2:
        return 1.5
    if count <= 6:
        return 2.0
    if count <= 10:
        return 2.5
    if count <= 14:
        return 3.0
    return 4.0


def party_thresholds(party):
    """Sum each PC's easy/medium/hard/deadly XP thresholds into a party budget."""
    keys = ("easy", "medium", "hard", "deadly")
    totals = dict.fromkeys(keys, 0)
    for pc in party:
        row = _THRESHOLDS.get(max(1, min(20, pc["level"])), _THRESHOLDS[20])
        for k, v in zip(keys, row):
            totals[k] += v
    return totals


def encounter_difficulty(members, party):
    """Rate an encounter against the party (the DMG XP-budget method).

    `members` are rows with `cr`/`quantity`; `party` are the PC rows. Returns
    {raw_xp, adjusted_xp, count, multiplier, thresholds, party_size, rating},
    where `rating` is Trivial/Easy/Medium/Hard/Deadly — or None when there's no
    party to compare against (so the caller can show XP without a verdict)."""
    from models.creature import cr_xp  # local: avoid import cycle
    count = sum(m["quantity"] for m in members)
    raw = sum(cr_xp(m["cr"]) * m["quantity"] for m in members)
    mult = encounter_multiplier(count)
    adjusted = int(raw * mult)
    th = party_thresholds(party)
    rating = None
    if party:
        if adjusted >= th["deadly"]:
            rating = "Deadly"
        elif adjusted >= th["hard"]:
            rating = "Hard"
        elif adjusted >= th["medium"]:
            rating = "Medium"
        elif adjusted >= th["easy"]:
            rating = "Easy"
        else:
            rating = "Trivial"
    return {"raw_xp": raw, "adjusted_xp": adjusted, "count": count,
            "multiplier": mult, "thresholds": th, "party_size": len(party),
            "rating": rating}
