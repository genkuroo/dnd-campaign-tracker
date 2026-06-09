"""The creature engine — data access + stat-block math.

A creature is the shared model behind both player characters and (from Phase 5)
monsters. This module owns the ability-modifier rule and the CRUD used by the
Character Sheet tab.
"""
from db import get_connection

# (column, short label) in canonical D&D order.
ABILITIES = [
    ("strength", "STR"),
    ("dexterity", "DEX"),
    ("constitution", "CON"),
    ("intelligence", "INT"),
    ("wisdom", "WIS"),
    ("charisma", "CHA"),
]

# What a creature *is*. The Characters tab offers pc/npc; the Bestiary creates
# monsters. All three share this one engine — `kind` is the only thing that
# differs (CLAUDE.md "creature/stat-block engine").
KINDS = [("pc", "Player Character"), ("npc", "NPC")]
MONSTER_KINDS = [("monster", "Monster")]

# How a creature treats the party — a 5-point spectrum, ordered hate -> love.
DISPOSITIONS = ["hostile", "unfriendly", "neutral", "friendly", "allied"]

# A creature's moral compass. '' = unaligned (many beasts/constructs).
ALIGNMENTS = [
    ("", "Unaligned / —"),
    ("LG", "Lawful Good"), ("NG", "Neutral Good"), ("CG", "Chaotic Good"),
    ("LN", "Lawful Neutral"), ("TN", "True Neutral"), ("CN", "Chaotic Neutral"),
    ("LE", "Lawful Evil"), ("NE", "Neutral Evil"), ("CE", "Chaotic Evil"),
]
ALIGNMENT_LABELS = dict(ALIGNMENTS)

# 5e Unarmored Defense (PCs): how a player's AC is figured with no armor on.
# '' = standard (10 + DEX); class features add a second ability.
UNARMORED_DEFENSE = [
    ("", "Standard (10 + DEX)"),
    ("barbarian", "Barbarian (10 + DEX + CON)"),
    ("monk", "Monk (10 + DEX + WIS)"),
]


def alignment_label(code):
    return ALIGNMENT_LABELS.get(code or "", code or "")

# Fields a creature form may set, with the type to coerce each to.
_INT_FIELDS = [
    "level", "max_hp", "current_hp", "armor_class", "speed", "exhaustion",
    "xp", "gold", "silver", "copper", "stats_revealed",
    *[col for col, _ in ABILITIES],
]

# D&D 5e: total XP required to reach each level (index = level).
XP_THRESHOLDS = [
    0, 0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000,
    85000, 100000, 120000, 140000, 165000, 195000, 225000, 265000, 305000, 355000,
]
MAX_LEVEL = 20


def level_from_xp(xp):
    """Highest level whose XP threshold the creature has reached (1–20)."""
    xp = int(xp)
    level = 1
    for lvl in range(2, MAX_LEVEL + 1):
        if xp >= XP_THRESHOLDS[lvl]:
            level = lvl
    return level


def xp_to_next(xp):
    """(next_level, xp_remaining) toward the next level, or None at the cap."""
    xp = int(xp)
    current = level_from_xp(xp)
    if current >= MAX_LEVEL:
        return None
    return current + 1, XP_THRESHOLDS[current + 1] - xp


def proficiency_bonus(level):
    """5e proficiency bonus by character level: +2 at 1–4, +3 at 5–8, +4 at 9–12,
    +5 at 13–16, +6 at 17–20. Added to any roll a creature is proficient in."""
    return 2 + (max(1, int(level)) - 1) // 4
_TEXT_FIELDS = [
    "name", "kind", "player_name", "disposition", "alignment",
    "resistances", "immunities", "vulnerabilities", "notes", "visibility",
    "avatar", "location", "unarmored_defense", "class_name", "subclass",
    "race", "subrace",
]


def ability_modifier(score):
    """D&D 5e rule: modifier = floor((score - 10) / 2)."""
    return (int(score) - 10) // 2


def format_modifier(mod):
    """Render a modifier the way sheets do: +3, -1, +0."""
    return f"+{mod}" if mod >= 0 else str(mod)


def list_roster():
    """The DM's cast — player characters and NPCs, PCs listed first.

    Monsters are excluded; they get their own home with encounters in Phase 5.
    """
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creatures WHERE kind IN ('pc', 'npc') "
            "ORDER BY CASE kind WHEN 'pc' THEN 0 ELSE 1 END, created_at DESC"
        ).fetchall()
    finally:
        conn.close()


def list_party():
    """The player characters — the adventuring party — by name."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creatures WHERE kind = 'pc' ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def list_npcs():
    """Non-player characters (the cast the DM runs), by name."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creatures WHERE kind = 'npc' ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def party_rest(kind):
    """A party-wide rest on the actual character sheets (not a combat snapshot).
    Long rest = everyone to full HP. Short rest = each PC recovers half their
    *missing* HP — an approximation of spending hit dice, which we don't track."""
    conn = get_connection()
    try:
        if kind == "long":
            conn.execute(
                "UPDATE creatures SET current_hp = max_hp WHERE kind = 'pc'"
            )
        elif kind == "short":
            conn.execute(
                "UPDATE creatures SET current_hp = current_hp + (max_hp - current_hp) / 2 "
                "WHERE kind = 'pc'"
            )
        conn.commit()
    finally:
        conn.close()


def adjust_coins(creature_id, d_gold=0, d_silver=0, d_copper=0):
    """Add (or subtract, with negatives) coins to a creature's purse, clamped at
    0 per denomination. Denominations are kept independent (no auto-conversion)."""
    c = get_creature(creature_id)
    if c is None:
        return
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE creatures SET gold = ?, silver = ?, copper = ? WHERE id = ?",
            (max(0, c["gold"] + int(d_gold)),
             max(0, c["silver"] + int(d_silver)),
             max(0, c["copper"] + int(d_copper)),
             creature_id),
        )
        conn.commit()
    finally:
        conn.close()


def adjust_hp(creature_id, delta):
    """Apply damage (delta < 0) or healing (delta > 0) to a creature's sheet,
    clamped to 0..max_hp. (Creatures have no temp HP; that's a combat concept.)"""
    c = get_creature(creature_id)
    if c is None:
        return
    new_hp = max(0, min(c["max_hp"], c["current_hp"] + int(delta)))
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE creatures SET current_hp = ? WHERE id = ?", (new_hp, creature_id)
        )
        conn.commit()
    finally:
        conn.close()


def list_monsters():
    """The bestiary — every creature with kind 'monster', newest first.

    Kept separate from list_roster (PCs/NPCs) so the Characters tab and the
    Bestiary stay distinct views of the one creatures table.
    """
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creatures WHERE kind = 'monster' ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def get_creature(creature_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creatures WHERE id = ?", (creature_id,)
        ).fetchone()
    finally:
        conn.close()


def _clean(data):
    """Coerce a form dict into safe column values."""
    fields = {}
    for col in _TEXT_FIELDS:
        if col in data:
            fields[col] = (data.get(col) or "").strip()
    for col in _INT_FIELDS:
        if col in data and str(data.get(col)).strip() != "":
            fields[col] = int(data[col])
    return fields


def create_creature(data):
    fields = _clean(data)
    fields.setdefault("kind", "pc")
    # Default current HP to full when not given.
    if "current_hp" not in fields and "max_hp" in fields:
        fields["current_hp"] = fields["max_hp"]
    cols = list(fields.keys())
    placeholders = ", ".join("?" for _ in cols)
    conn = get_connection()
    try:
        cur = conn.execute(
            f"INSERT INTO creatures ({', '.join(cols)}) VALUES ({placeholders})",
            [fields[c] for c in cols],
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_creature(creature_id, data):
    fields = _clean(data)
    if not fields:
        return
    assignments = ", ".join(f"{col} = ?" for col in fields)
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE creatures SET {assignments} WHERE id = ?",
            [*fields.values(), creature_id],
        )
        conn.commit()
    finally:
        conn.close()


def delete_creature(creature_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM creatures WHERE id = ?", (creature_id,))
        conn.commit()
    finally:
        conn.close()
