"""A creature's inventory of items (loot, gear, consumables) + equipment slots."""
from db import get_connection

# Equipment slots: (key, label, capacity). Most hold one item; rings hold two.
SLOTS = [
    ("main_hand", "Main Hand", 1),
    ("off_hand", "Off Hand", 1),
    ("armor", "Armor", 1),
    ("helmet", "Helmet", 1),
    ("cloak", "Cloak", 1),
    ("gloves", "Gloves", 1),
    ("boots", "Boots", 1),
    ("amulet", "Amulet", 1),
    ("ring", "Ring", 2),
]
SLOT_LABELS = {key: label for key, label, _ in SLOTS}
SLOT_CAP = {key: cap for key, _, cap in SLOTS}
EQUIP_SLOTS = [key for key, _, _ in SLOTS]


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


def add_item(creature_id, name, quantity=1, description="", slot="", hands=1):
    name = (name or "").strip()
    if not name:
        return None
    if slot not in EQUIP_SLOTS:
        slot = ""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO creature_items (creature_id, name, quantity, description, slot, hands) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (creature_id, name, max(1, int(quantity or 1)), (description or "").strip(),
             slot, 2 if int(hands or 1) == 2 else 1),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


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
        if cap == 1:
            panel.append({
                "key": key,
                "label": label,
                "item": items[0] if items else None,
                "blocked": key == "off_hand" and not items and main_two_handed,
            })
        else:
            base = label[:-1] if label.endswith("s") else label
            for i in range(cap):
                panel.append({
                    "key": key,
                    "label": f"{base} {i + 1}",
                    "item": items[i] if i < len(items) else None,
                    "blocked": False,
                })
    return panel
