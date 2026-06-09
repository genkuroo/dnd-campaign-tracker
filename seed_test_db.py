"""Build a throwaway demo database that exercises every feature, for clicking
through the app by hand.

Run it, then launch the app pointed at the same file:

    python seed_test_db.py
    DND_DB_PATH=test_campaign.db python app.py     # http://127.0.0.1:5002

It writes to **test_campaign.db** (never the real campaign.db) and recreates it
from scratch each run. Logins printed at the end.
"""
import os

# Point the whole stack at the throwaway DB *before* importing anything that
# touches the database. Never the real campaign.db.
TEST_DB = os.environ.get("DND_DB_PATH", "test_campaign.db")
os.environ["DND_DB_PATH"] = TEST_DB

import db
db.DB_PATH = TEST_DB
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
db.init_db()

# Import after the DB path is set; app gives us _apply_class (the full BG3 kit).
import app  # noqa: E402
from models.creature import create_creature, update_creature, get_creature  # noqa: E402
from models.user import create_user, set_user_character, set_signup_code  # noqa: E402
from models.proficiency import set_skill_proficiencies  # noqa: E402
from models.spellbook import add_spell  # noqa: E402
from models.spellcasting import spend_slot  # noqa: E402
from models.inventory import add_item, equip_item  # noqa: E402
from models.actions import add_action  # noqa: E402
from models.loot import create_area, add_loot, set_current_area  # noqa: E402
from models.encounters import create_encounter, add_member  # noqa: E402

PASSWORD = "test1234"


def make_pc(name, klass, *, player=None, xp=0, avatar=""):
    """Create a PC, apply the class starting kit (stats/HP/gear), assign a player."""
    cid = create_creature({"name": name, "kind": "pc", "player_name": player or "",
                           "xp": xp, "avatar": avatar})
    app._apply_class(cid, klass, starting_kit=True)
    return cid


# --- Accounts -------------------------------------------------------------
dm = create_user("dm", PASSWORD, "dm")
set_signup_code("DRAGON")  # players could self-register at /register with this

# --- The party (one PC per player, varied classes) ------------------------
# Wizard — full caster: spells, slots, casting stats.
gandalf = make_pc("Gandalf", "wizard", player="alice", xp=6500, avatar="🧙")
update_creature(gandalf, {"intelligence": 16, "dexterity": 14, "level": 5,
                          "alignment": "NG", "subclass": "evocation",
                          "race": "elf", "subrace": "high-elf", "background": "sage"})
set_skill_proficiencies(gandalf, ["arcana", "history", "investigation", "insight"])
for slug in ("fire-bolt", "magic-missile", "shield", "burning-hands", "fireball"):
    add_spell(gandalf, slug)
spend_slot(gandalf, 1)  # show a partly-used slot tracker
spend_slot(gandalf, 3)

# Barbarian — martial, Unarmored Defense, a Rage ability.
grog = make_pc("Grog", "barbarian", player="bob", xp=6500, avatar="🪓")
update_creature(grog, {"strength": 17, "constitution": 16, "level": 5,
                       "alignment": "CN", "subclass": "berserker",
                       "race": "dwarf", "subrace": "mountain-dwarf",
                       "exhaustion": 1, "background": "soldier"})  # a Berserker's Frenzy leaves him exhausted
set_skill_proficiencies(grog, ["athletics", "intimidation", "survival"])
# Rage now comes from the class auto-grant; this is a hand-added extra to show
# class-granted and manual actions side by side.
add_action(grog, "Reckless Attack", "Advantage on melee attacks this turn; attacks "
           "against you have advantage until your next turn.", category="action")

# Cleric — full caster with healing + a save-DC spell.
pike = make_pc("Pike", "cleric", player="carol", xp=2700, avatar="🛡️")
update_creature(pike, {"wisdom": 16, "level": 4, "alignment": "LG", "subclass": "life", "race": "human", "background": "acolyte"})
set_skill_proficiencies(pike, ["medicine", "religion", "persuasion"])
for slug in ("cure-wounds", "healing-word", "thunderwave", "bless", "hold-person"):
    add_spell(pike, slug)
from models.spellcasting import set_concentration  # noqa: E402
set_concentration(pike, "Bless")  # show the concentration banner on load

# Rogue — no spells; skill-monkey; equips a dagger.
vex = make_pc("Vex", "rogue", player=None, xp=900, avatar="🗡️")
update_creature(vex, {"dexterity": 16, "level": 3, "alignment": "CG", "subclass": "thief",
                      "race": "halfling", "subrace": "lightfoot", "background": "criminal"})
set_skill_proficiencies(vex, ["stealth", "acrobatics", "sleight-of-hand",
                              "perception", "deception"],
                        expertise_slugs=["stealth", "sleight-of-hand"])  # Rogue expertise

# The starting kit auto-granted class actions at level 1; we bumped levels above
# with update_creature (which doesn't resync). Re-sync so each PC's class actions
# match their final level — the app does this via the level-up / edit routes.
for _pc in (gandalf, grog, pike, vex):
    app._sync_class_actions(_pc)

# Spend a couple of class resources so the tracker shows partial use on load.
from models.resources import spend_resource  # noqa: E402
spend_resource(get_creature(grog), "rage")          # Grog: 1 Rage used
spend_resource(get_creature(pike), "channel-divinity")  # Pike: Channel Divinity used

# Allocate Ability Score Improvements (each of these PCs has hit level 4+, so the
# class granted 2 points to spend; the sheet shows the allocator + folds it into
# the effective scores). Gandalf/Grog spend their full +2; Pike splits +1/+1.
from models.asi import adjust_asi  # noqa: E402
for _ in range(2): adjust_asi(get_creature(gandalf), "intelligence", 1)  # 16 → 18 INT
for _ in range(2): adjust_asi(get_creature(grog), "strength", 1)          # 17 → 19 STR
adjust_asi(get_creature(pike), "wisdom", 1)
adjust_asi(get_creature(pike), "constitution", 1)

# Feats are tracked separately (skeleton) — grab one from the catalog onto Vex and
# a custom one onto Gandalf, to show both add paths on the sheet.
from models.feats import add_feat, get_catalog_feat  # noqa: E402
_alert = get_catalog_feat("alert")
add_feat(vex, _alert["name"], _alert["description"], _alert["prerequisite"])
add_feat(gandalf, "Arcane Savant", "Custom: advantage on checks to identify magic items.",
         "Spellcaster")

# Players linked to their PCs (Vex is left unassigned to demo "Create my character").
alice = create_user("alice", PASSWORD, "player", creature_id=gandalf)
bob = create_user("bob", PASSWORD, "player", creature_id=grog)
carol = create_user("carol", PASSWORD, "player", creature_id=pike)
dave = create_user("dave", PASSWORD, "player")  # no character yet
set_user_character(alice, gandalf)
set_user_character(bob, grog)
set_user_character(carol, pike)

# Give a couple of players colours so the dice log tints rolls.
from models.user import set_user_color  # noqa: E402
set_user_color(alice, "#4ea1ff")
set_user_color(bob, "#e0533d")
set_user_color(carol, "#7bd66b")

# --- NPCs (cast the DM runs; varied dispositions/locations) ---------------
def make_npc(name, *, disp="neutral", align="", loc="", hidden=False, avatar="",
             hp=9, ac=12):
    cid = create_creature({"name": name, "kind": "npc", "disposition": disp,
                           "alignment": align, "location": loc, "avatar": avatar,
                           "max_hp": hp, "armor_class": ac,
                           "visibility": "hidden" if hidden else "visible"})
    return cid

make_npc("Barliman the Barkeep", disp="friendly", align="NG",
         loc="The Prancing Pony, Bree", avatar="🍺")
make_npc("Captain Hale", disp="neutral", align="LN", loc="Bree West Gate", avatar="💂",
         hp=22, ac=16)
make_npc("The Hooded Stranger", disp="unfriendly", align="CN",
         loc="back corner booth", avatar="🧥")
make_npc("Mordecai the Betrayer", disp="hostile", align="CE",
         loc="(unknown)", hidden=True, avatar="🩸", hp=40, ac=15)

# --- Bestiary (monsters; some hidden / some revealed) ---------------------
def make_monster(name, *, str_=10, dex=10, con=10, int_=3, wis=10, cha=6,
                 hp=7, ac=13, visible=True, revealed=False, avatar=""):
    cid = create_creature({"name": name, "kind": "monster",
                           "strength": str_, "dexterity": dex, "constitution": con,
                           "intelligence": int_, "wisdom": wis, "charisma": cha,
                           "max_hp": hp, "armor_class": ac, "avatar": avatar,
                           "visibility": "visible" if visible else "hidden",
                           "stats_revealed": 1 if revealed else 0})
    return cid

goblin = make_monster("Goblin", str_=8, dex=14, con=10, hp=7, ac=15, avatar="👺",
                      visible=True, revealed=True)
add_action(goblin, "Scimitar", "Melee weapon attack, one target. Hit: 1d6+2 slashing.",
           dice="1d6+2", category="action")
add_action(goblin, "Nimble Escape", "Disengage or Hide as a bonus action.",
           category="bonus")

wolf = make_monster("Wolf", str_=12, dex=15, con=12, wis=12, hp=11, ac=13, avatar="🐺",
                    visible=True, revealed=False)  # visible but stats masked
add_action(wolf, "Bite", "Melee weapon attack. Hit: 2d4+2 piercing, DC 11 STR save or "
           "prone.", dice="2d4+2", category="action")

orc = make_monster("Orc", str_=16, dex=12, con=16, hp=15, ac=13, avatar="🧌",
                   visible=True, revealed=False)
add_action(orc, "Greataxe", "Melee weapon attack. Hit: 1d12+3 slashing.",
           dice="1d12+3", category="action")

dragon = make_monster("Young Red Dragon", str_=23, dex=10, con=21, int_=14, wis=11,
                      cha=19, hp=178, ac=18, visible=False, avatar="🐉")  # hidden boss
add_action(dragon, "Fire Breath (Recharge 5–6)", "30-ft cone, DC 17 DEX save, 16d6 fire "
           "(half on success).", dice="16d6", category="action")
add_action(dragon, "Multiattack", "One Bite and two Claw attacks.", category="action")

# --- An encounter to load into combat -------------------------------------
ambush = create_encounter("Goblin Ambush")
add_member(ambush, goblin, 3)
add_member(ambush, wolf, 1)

# --- A loot area with premade + custom + currency loot --------------------
from models.items import get_item_def  # noqa: E402

pony = create_area("The Prancing Pony")
set_current_area(pony)
for slug in ("potion-of-healing", "shield", "ring-of-protection"):
    it = get_item_def(slug)
    add_loot(pony, it["name"], 1, it["description"], slot=it["slot"], hands=it["hands"],
             ac_bonus=it.get("ac_bonus", 0), stat_bonuses=it.get("stat_bonuses", ""),
             grants_spells=it.get("grants_spells", ""),
             armor_base=it.get("armor_base", 0), armor_type=it.get("armor_type", ""))
add_loot(pony, "Mysterious Locked Chest", 1, "Iron-bound, needs a key.")
add_loot(pony, "Pouch of Coins", 1, "Loose change.", gold=15, silver=30, copper=50)

# --- A second area to show switching --------------------------------------
cave = create_area("Goblin Cave")
add_loot(cave, "Crude Goblin Totem", 1, "Worth a few coins to the right buyer.")

print("\n=== test_campaign.db built ===")
print(f"DB file : {os.path.abspath(TEST_DB)}")
print("Launch  : DND_DB_PATH=%s python app.py   (http://127.0.0.1:5002)" % TEST_DB)
print("\nLogins (password for all: %s):" % PASSWORD)
print("  dm     — Dungeon Master (sees & edits everything)")
print("  alice  — Gandalf (Wizard 5 / School of Evocation)")
print("  bob    — Grog (Barbarian 5 / Path of the Berserker — Frenzy)")
print("  carol  — Pike (Cleric 4 / Life Domain — Preserve Life)")
print("  dave   — no character yet (demo 'Create my character')")
print("Vex (Rogue 3 / Thief — Fast Hands) is unassigned. Signup code for /register: DRAGON")
print("Subclasses show in each sheet's <Class> Features section (SUBCLASS pill);")
print("action-type ones are auto-granted into Actions & Abilities.")
