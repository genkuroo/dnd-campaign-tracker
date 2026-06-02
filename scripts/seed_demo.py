"""Seed the local campaign.db with demo characters to exercise Phase 1-4.

Run from the project root:
    python scripts/seed_demo.py          # resets: wipes existing creatures first
    python scripts/seed_demo.py --keep   # appends: leaves your data intact

By default this resets the demo data (deletes all creatures, cascading to their
spells/items, plus the roll log) before inserting the samples below. Pass
--keep once you've started entering real characters so it only appends.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_connection, init_db
from models.creature import create_creature
from models.inventory import add_item, equip_item
from models.items import get_item_def
from models.loot import add_loot, create_area, set_current_area
from models.spellbook import add_spell


def reset():
    conn = get_connection()
    try:
        conn.execute("DELETE FROM creatures")   # cascades to spells + items
        conn.execute("DELETE FROM areas")       # cascades to loot
        conn.execute("DELETE FROM rolls")
        conn.commit()
    finally:
        conn.close()


def spawn(area_id, slug, qty=1):
    """Drop a premade catalog item into an area's loot pool."""
    d = get_item_def(slug)
    add_loot(area_id, d["name"], qty, d["description"], slot=d["slot"], hands=d["hands"])


def seed_loot():
    pony = create_area("The Prancing Pony (Tavern)")
    spawn(pony, "potion-of-healing", 2)
    spawn(pony, "rations", 10)
    add_loot(pony, "Mysterious sealed letter", 1, "Addressed to no one. Wax seal shows a black raven.")

    warren = create_area("Goblin Warren")
    spawn(warren, "shortbow")
    spawn(warren, "shield")
    spawn(warren, "longsword")
    spawn(warren, "ring-of-protection")
    add_loot(warren, "Pouch of gold", 1, "37 gp pried from a goblin chieftain.")
    set_current_area(warren)
    return [pony, warren]


def item(cid, name, qty=1, desc="", slot="", hands=1, equipped=False):
    iid = add_item(cid, name, qty, desc, slot=slot, hands=hands)
    if equipped:
        equip_item(iid)


def seed():
    # --- Thoradin: a level-3 cleric sitting on enough XP to level up ---
    thoradin = create_creature({
        "name": "Thoradin Stoneheart", "kind": "pc", "player_name": "Sam",
        "level": 3, "xp": 2700, "alignment": "LG",
        "strength": 14, "dexterity": 10, "constitution": 16,
        "intelligence": 11, "wisdom": 16, "charisma": 12,
        "max_hp": 27, "current_hp": 27, "armor_class": 18,
        "gold": 45, "silver": 12, "copper": 8,
        "notes": "Dwarf cleric of the forge. Gruff but loyal.",
    })
    item(thoradin, "Mace", 1, "1d6 bludgeoning", slot="main_hand", equipped=True)
    item(thoradin, "Shield", 1, "+2 AC", slot="off_hand", equipped=True)
    item(thoradin, "Chain mail", 1, "AC 16", slot="armor", equipped=True)
    item(thoradin, "Amulet of health", 1, "CON 19", slot="amulet", equipped=True)
    item(thoradin, "Potion of healing", 3, "Regain 2d4+2 HP")
    item(thoradin, "Torch", 5)
    item(thoradin, "Rations", 10, "1 day each")
    item(thoradin, "Holy symbol", 1, "Spellcasting focus")
    add_spell(thoradin, "cure-wounds")
    add_spell(thoradin, "healing-word")

    # --- Aria: a level-5 wizard, mid-progression toward level 6 ---
    aria = create_creature({
        "name": "Aria Moonwhisper", "kind": "pc", "player_name": "Jess",
        "level": 5, "xp": 6500, "alignment": "CG",
        "strength": 8, "dexterity": 16, "constitution": 13,
        "intelligence": 17, "wisdom": 12, "charisma": 11,
        "max_hp": 27, "current_hp": 22, "armor_class": 12,
        "gold": 120, "silver": 0, "copper": 0,
        "notes": "High-elf evoker. Loves fire.",
    })
    item(aria, "Quarterstaff", 1, "1d6 bludgeoning", slot="main_hand", equipped=True)
    item(aria, "Robe of the archmagi", 1, "AC 15 + bonuses", slot="armor", equipped=True)
    item(aria, "Cloak of protection", 1, "+1 AC and saves", slot="cloak", equipped=True)
    item(aria, "Ring of evasion", 1, slot="ring", equipped=True)
    item(aria, "Ring of spell storing", 1, slot="ring", equipped=True)
    item(aria, "Component pouch", 1, "Spellcasting focus")
    item(aria, "Dagger", 2, "1d4 piercing")
    item(aria, "Potion of healing", 2, "Regain 2d4+2 HP")
    for slug in ("fire-bolt", "magic-missile", "shield", "fireball", "lightning-bolt"):
        add_spell(aria, slug)

    # --- Grok: a level-2 barbarian also ready to level up, no spells ---
    grok = create_creature({
        "name": "Grok", "kind": "pc", "player_name": "Alex",
        "level": 2, "xp": 900, "alignment": "CN",
        "strength": 17, "dexterity": 14, "constitution": 16,
        "intelligence": 8, "wisdom": 10, "charisma": 9,
        "max_hp": 26, "current_hp": 19, "armor_class": 14,
        "gold": 8, "silver": 50, "copper": 0,
        "resistances": "bludgeoning, piercing, slashing",
        "notes": "Half-orc barbarian. Smashes first.",
    })
    # Greataxe is two-handed -> blocks the off hand. The unequipped shield lets
    # you test the swap (equipping it frees the greataxe).
    item(grok, "Greataxe", 1, "1d12 slashing", slot="main_hand", hands=2, equipped=True)
    item(grok, "Shield", 1, "+2 AC (try equipping it!)", slot="off_hand")
    item(grok, "Javelin", 4, "1d6 piercing")
    item(grok, "Bedroll", 1)
    item(grok, "Rations", 5)

    # --- Greta: an NPC, to show inventory works for them too ---
    greta = create_creature({
        "name": "Greta the Tavernkeep", "kind": "npc",
        "level": 1, "xp": 0, "alignment": "NG", "disposition": "friendly",
        "strength": 10, "dexterity": 11, "constitution": 12,
        "intelligence": 10, "wisdom": 13, "charisma": 14,
        "max_hp": 9, "current_hp": 9, "armor_class": 11,
        "gold": 30, "silver": 5, "copper": 0,
        "notes": "Runs the Prancing Pony. Knows all the local gossip.",
    })
    item(greta, "Frying pan", 1, "Improvised weapon", slot="main_hand", equipped=True)
    item(greta, "Ring of keys", 1)
    item(greta, "Mug of ale", 12)

    return [thoradin, aria, grok, greta]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data into campaign.db.")
    parser.add_argument("--keep", action="store_true",
                        help="append the samples instead of wiping existing creatures first")
    args = parser.parse_args()

    init_db()
    if not args.keep:
        reset()
    ids = seed()
    areas = seed_loot()
    mode = "Appended" if args.keep else "Seeded"
    print(f"{mode} {len(ids)} creatures (3 PCs + 1 NPC) and {len(areas)} loot areas into campaign.db.")
    print("Run:  python app.py   then open http://127.0.0.1:5002/character")
