"""A creature's inventory of items (loot, gear, consumables) + equipment slots."""
from db import get_connection
from models.spells import get_spell

# Equipment slots: (key, label, capacity). Most hold one item; rings hold two.
SLOTS = [
    ("main_hand", "Main Hand", 1),
    ("off_hand", "Off Hand", 1),
    # Left column renders head-to-toe: helmet, cloak, armor, gloves, boots.
    ("helmet", "Helmet", 1),
    ("cloak", "Cloak", 1),
    ("armor", "Armor", 1),
    ("gloves", "Gloves", 1),
    ("boots", "Boots", 1),
    ("amulet", "Amulet", 1),
    ("ring", "Ring", 2),
]
SLOT_LABELS = {key: label for key, label, _ in SLOTS}
SLOT_CAP = {key: cap for key, _, cap in SLOTS}
EQUIP_SLOTS = [key for key, _, _ in SLOTS]

# Paper-doll layout: armor on the left, a character frame in the middle, and
# weapons + jewelry on the right (Baldur's Gate-style).
SLOT_COLUMN = {
    "armor": "left", "helmet": "left", "cloak": "left", "gloves": "left", "boots": "left",
    "main_hand": "right", "off_hand": "right", "amulet": "right", "ring": "right",
}


def list_items(creature_id):
    """A creature's items: equipped first, then by name."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creature_items WHERE creature_id = ? "
            "ORDER BY equipped DESC, name COLLATE NOCASE",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()


def get_item(item_id):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM creature_items WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        conn.close()


def add_item(creature_id, name, quantity=1, description="", slot="", hands=1,
             ac_bonus=0, grants_spells="", stat_bonuses=""):
    name = (name or "").strip()
    if not name:
        return None
    if slot not in EQUIP_SLOTS:
        slot = ""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO creature_items "
            "(creature_id, name, quantity, description, slot, hands, ac_bonus, "
            " grants_spells, stat_bonuses) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (creature_id, name, max(1, int(quantity or 1)), (description or "").strip(),
             slot, 2 if int(hands or 1) == 2 else 1,
             int(ac_bonus or 0), _clean_slugs(grants_spells), _clean_stat_bonuses(stat_bonuses)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# Ability score columns, for parsing item stat bonuses.
_ABILITY_COLS = ("strength", "dexterity", "constitution",
                 "intelligence", "wisdom", "charisma")
_ABILITY_SHORT = {"strength": "STR", "dexterity": "DEX", "constitution": "CON",
                  "intelligence": "INT", "wisdom": "WIS", "charisma": "CHA"}


def item_effects(item):
    """Human-readable list of an item's magic effects, e.g. ['+2 AC', 'STR +2',
    'grants Fire Bolt']. Empty for a mundane item."""
    out = []
    if item["ac_bonus"]:
        out.append(f"{item['ac_bonus']:+d} AC")
    for col, amt in _parse_stat_bonuses(item["stat_bonuses"]).items():
        out.append(f"{_ABILITY_SHORT[col]} {amt:+d}")
    names = [(get_spell(s.strip()) or {}).get("name", s.strip())
             for s in (item["grants_spells"] or "").split(",") if s.strip()]
    if names:
        out.append("grants " + ", ".join(names))
    return out


def _clean_slugs(value):
    """Normalize a spell-slug list (list or comma string) to a comma string."""
    if isinstance(value, (list, tuple)):
        parts = value
    else:
        parts = (value or "").split(",")
    return ", ".join(s.strip() for s in parts if s and s.strip())


def _parse_stat_bonuses(text):
    """'strength:2, dexterity:1' -> {'strength': 2, 'dexterity': 1} (valid only)."""
    out = {}
    for pair in (text or "").split(","):
        key, sep, val = pair.partition(":")
        key = key.strip().lower()
        if sep and key in _ABILITY_COLS:
            try:
                out[key] = out.get(key, 0) + int(val)
            except ValueError:
                pass
    return out


def _clean_stat_bonuses(value):
    """Normalize stat bonuses (dict or 'ability:amount' string) to a stored string,
    dropping zero/invalid entries."""
    data = value if isinstance(value, dict) else _parse_stat_bonuses(value)
    return ", ".join(f"{k}:{v}" for k, v in data.items() if v)


def equipped_ac_bonus(creature_id):
    """Total AC bonus from the creature's currently-equipped items."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(ac_bonus), 0) AS total FROM creature_items "
            "WHERE creature_id = ? AND equipped = 1",
            (creature_id,),
        ).fetchone()
        return row["total"]
    finally:
        conn.close()


def effective_ac(creature):
    """A creature's AC including bonuses from equipped items (base AC is never
    mutated — this is computed, so it reverts when items come off)."""
    return creature["armor_class"] + equipped_ac_bonus(creature["id"])


def equipped_stat_bonuses(creature_id):
    """{ability_col: total_bonus} from the creature's equipped items."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT stat_bonuses FROM creature_items "
            "WHERE creature_id = ? AND equipped = 1 AND stat_bonuses != ''",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()
    totals = {}
    for r in rows:
        for k, v in _parse_stat_bonuses(r["stat_bonuses"]).items():
            totals[k] = totals.get(k, 0) + v
    return totals


def effective_abilities(creature):
    """{ability_col: {'score': effective, 'bonus': from_items}} for the six scores,
    base never mutated."""
    bonuses = equipped_stat_bonuses(creature["id"])
    return {col: {"score": creature[col] + bonuses.get(col, 0),
                  "bonus": bonuses.get(col, 0)}
            for col in _ABILITY_COLS}


def equipped_granted_spells(creature_id):
    """[(spell_slug, item_name)] for each spell granted by an equipped item."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name, grants_spells FROM creature_items "
            "WHERE creature_id = ? AND equipped = 1 AND grants_spells != ''",
            (creature_id,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        for slug in (s.strip() for s in r["grants_spells"].split(",")):
            if slug:
                out.append((slug, r["name"]))
    return out


def remove_item(item_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM creature_items WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()


def adjust_quantity(item_id, delta):
    """Nudge quantity by delta, clamped to a minimum of 1."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE creature_items SET quantity = MAX(1, quantity + ?) WHERE id = ?",
            (int(delta), item_id),
        )
        conn.commit()
    finally:
        conn.close()


def unequip_item(item_id):
    conn = get_connection()
    try:
        conn.execute("UPDATE creature_items SET equipped = 0 WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()


def equip_item(item_id):
    """Equip an item into its slot, swapping out whatever conflicts.

    Enforces one item per slot (two for rings) and the two-handed rule: a
    two-handed main-hand weapon clears the off hand, and equipping anything in
    the off hand frees a two-handed weapon. No-op for non-equippable items.
    """
    item = get_item(item_id)
    if item is None or not item["slot"]:
        return
    cid, slot, hands = item["creature_id"], item["slot"], item["hands"]
    conn = get_connection()
    try:
        equipped = conn.execute(
            "SELECT id, slot, hands FROM creature_items WHERE creature_id = ? AND equipped = 1",
            (cid,),
        ).fetchall()

        free = set()
        if slot == "main_hand":
            free |= {e["id"] for e in equipped if e["slot"] == "main_hand"}
            if hands == 2:  # a two-handed weapon also occupies the off hand
                free |= {e["id"] for e in equipped if e["slot"] == "off_hand"}
        elif slot == "off_hand":
            free |= {e["id"] for e in equipped if e["slot"] == "off_hand"}
            # can't hold a shield/off-hand and a two-handed weapon at once
            free |= {e["id"] for e in equipped if e["slot"] == "main_hand" and e["hands"] == 2}
        elif SLOT_CAP.get(slot, 1) == 1:
            free |= {e["id"] for e in equipped if e["slot"] == slot}
        else:  # multi-capacity (rings): if full, free the oldest
            same = [e for e in equipped if e["slot"] == slot]
            if len(same) >= SLOT_CAP[slot]:
                free.add(min(same, key=lambda e: e["id"])["id"])

        for fid in free:
            conn.execute("UPDATE creature_items SET equipped = 0 WHERE id = ?", (fid,))
        conn.execute("UPDATE creature_items SET equipped = 1 WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()


def equipped_by_slot(creature_id):
    """{slot_key: [equipped items]} keyed by canonical slot."""
    by_slot = {key: [] for key in EQUIP_SLOTS}
    for it in list_items(creature_id):
        if it["equipped"] and it["slot"] in by_slot:
            by_slot[it["slot"]].append(it)
    return by_slot


def equipment_panel(creature_id):
    """Flat list of display boxes for the equipment panel.

    Multi-capacity slots (rings) expand into one numbered box each (Ring 1,
    Ring 2), filled positionally — so the model keeps a single 'ring' slot while
    the UI shows two. Each box: {key (canonical slot for drops), label, item, blocked}.
    """
    by_slot = equipped_by_slot(creature_id)
    main_two_handed = any(i["hands"] == 2 for i in by_slot["main_hand"])
    panel = []
    for key, label, cap in SLOTS:
        items = by_slot[key]
        column = SLOT_COLUMN.get(key, "left")
        if cap == 1:
            panel.append({
                "key": key,
                "label": label,
                "item": items[0] if items else None,
                "blocked": key == "off_hand" and not items and main_two_handed,
                "column": column,
            })
        else:
            base = label[:-1] if label.endswith("s") else label
            for i in range(cap):
                panel.append({
                    "key": key,
                    "label": f"{base} {i + 1}",
                    "item": items[i] if i < len(items) else None,
                    "blocked": False,
                    "column": column,
                })
    return panel
