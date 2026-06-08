"""SQLite bootstrap + migrations for the campaign tracker.

Schema changes are applied as ordered migrations. `init_db()` reads the current
version from the `meta` table and applies any pending migrations up to
`SCHEMA_VERSION`, so a fresh clone and an existing DB both converge to the same
schema. See CLAUDE.md for the architecture (the creature engine + the
visibility-aware model).
"""
import os
import sqlite3

# The campaign database. Defaults to the real local DB, but can be pointed
# elsewhere via DND_DB_PATH so a throwaway/test DB can be run without touching
# real campaign data (e.g. `DND_DB_PATH=test_campaign.db python app.py`).
DB_PATH = os.environ.get("DND_DB_PATH", "campaign.db")

SCHEMA_VERSION = 30

# Each migration brings the schema from version N-1 to N. Keep them append-only:
# never edit a shipped migration, add a new one.
MIGRATIONS = {
    1: """
    -- The creature engine. A player character and a monster are the same kind
    -- of thing under the hood (CLAUDE.md "creature/stat-block engine"); `kind`
    -- distinguishes them. `visibility` is the Phase-1 anticipation of the
    -- public/private spine: 'visible' = players may see it, 'hidden' = DM-only.
    CREATE TABLE creatures (
        id              INTEGER PRIMARY KEY,
        name            TEXT    NOT NULL,
        kind            TEXT    NOT NULL DEFAULT 'pc',   -- 'pc' | 'monster'
        player_name     TEXT    NOT NULL DEFAULT '',     -- who plays this PC (becomes a user FK in Phase 7)
        level           INTEGER NOT NULL DEFAULT 1,

        strength        INTEGER NOT NULL DEFAULT 10,
        dexterity       INTEGER NOT NULL DEFAULT 10,
        constitution    INTEGER NOT NULL DEFAULT 10,
        intelligence    INTEGER NOT NULL DEFAULT 10,
        wisdom          INTEGER NOT NULL DEFAULT 10,
        charisma        INTEGER NOT NULL DEFAULT 10,

        max_hp          INTEGER NOT NULL DEFAULT 1,
        current_hp      INTEGER NOT NULL DEFAULT 1,
        armor_class     INTEGER NOT NULL DEFAULT 10,

        resistances     TEXT    NOT NULL DEFAULT '',     -- comma-separated damage types (normalize later if needed)
        immunities      TEXT    NOT NULL DEFAULT '',
        vulnerabilities TEXT    NOT NULL DEFAULT '',

        notes           TEXT    NOT NULL DEFAULT '',
        visibility      TEXT    NOT NULL DEFAULT 'visible',  -- 'visible' | 'hidden'
        created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    2: """
    -- Two distinct D&D concepts (CLAUDE.md "creature engine"):
    --   disposition = how the creature treats the party (friendly/neutral/hostile)
    --   alignment   = the creature's moral compass (LG..CE, '' = unaligned)
    -- Both live on every creature; most useful for NPCs/monsters.
    ALTER TABLE creatures ADD COLUMN disposition TEXT NOT NULL DEFAULT 'neutral';
    ALTER TABLE creatures ADD COLUMN alignment   TEXT NOT NULL DEFAULT '';
    """,
    3: """
    -- The roll log: a persisted history for the dice roller. `label` records the
    -- context of a roll (e.g. 'Thoradin · STR check'); detail is the breakdown.
    CREATE TABLE rolls (
        id          INTEGER PRIMARY KEY,
        expression  TEXT    NOT NULL,
        total       INTEGER NOT NULL,
        detail      TEXT    NOT NULL DEFAULT '',
        label       TEXT    NOT NULL DEFAULT '',
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    4: """
    -- A creature's spellbook: which SRD spells it knows, and whether each is
    -- currently prepared. Spells themselves live in data/spells.json (referenced
    -- by slug), so this table only stores the link. ON DELETE CASCADE clears a
    -- creature's spells when it's deleted (foreign_keys pragma is ON).
    CREATE TABLE creature_spells (
        creature_id INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        spell_slug  TEXT    NOT NULL,
        prepared    INTEGER NOT NULL DEFAULT 1,
        added_at    TEXT    NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (creature_id, spell_slug)
    );
    """,
    5: """
    -- Progression + coin purse on every creature. Level already exists; XP is
    -- tracked alongside it (level stays manual to support milestone play, with
    -- XP-based level-up hints layered on in the app, not the schema).
    ALTER TABLE creatures ADD COLUMN xp     INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creatures ADD COLUMN gold   INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creatures ADD COLUMN silver INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creatures ADD COLUMN copper INTEGER NOT NULL DEFAULT 0;
    """,
    6: """
    -- A creature's inventory. Free-form items (loot lands here); ON DELETE
    -- CASCADE clears them with the creature.
    CREATE TABLE creature_items (
        id          INTEGER PRIMARY KEY,
        creature_id INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        name        TEXT    NOT NULL,
        quantity    INTEGER NOT NULL DEFAULT 1,
        description TEXT    NOT NULL DEFAULT '',
        equipped    INTEGER NOT NULL DEFAULT 0,
        added_at    TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    7: """
    -- Equipment slots. `slot` is which body slot an item occupies ('' = not
    -- equippable, e.g. potions). `hands` (1 or 2) matters for main-hand weapons:
    -- a two-handed weapon also blocks the off hand. Enforcement lives in
    -- models/inventory.equip_item (one item per slot, swap to make room).
    ALTER TABLE creature_items ADD COLUMN slot  TEXT    NOT NULL DEFAULT '';
    ALTER TABLE creature_items ADD COLUMN hands INTEGER NOT NULL DEFAULT 1;
    """,
    8: """
    -- DM-driven loot. Areas are named locations (a lightweight precursor to the
    -- fuller location system in later phases); each holds its own loot pool.
    -- Items mirror creature_items' shape so giving loot to a creature is a
    -- straight copy. ON DELETE CASCADE clears a deleted area's loot.
    CREATE TABLE areas (
        id         INTEGER PRIMARY KEY,
        name       TEXT    NOT NULL,
        created_at TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE loot_items (
        id          INTEGER PRIMARY KEY,
        area_id     INTEGER NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
        name        TEXT    NOT NULL,
        quantity    INTEGER NOT NULL DEFAULT 1,
        description TEXT    NOT NULL DEFAULT '',
        slot        TEXT    NOT NULL DEFAULT '',
        hands       INTEGER NOT NULL DEFAULT 1,
        added_at    TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    9: """
    -- A creature's free-form actions/abilities (Phase 5). Deliberately *distinct*
    -- from spells (CLAUDE.md): spells are SRD-backed with level/components, while
    -- actions (Multiattack, Rage, breath weapons, legendary actions, traits) are
    -- hand-written name + description + an optional dice expression. Rides the
    -- same creature-attached pattern as the spellbook; ON DELETE CASCADE clears a
    -- deleted creature's actions. Works for PCs, NPCs, and monsters alike.
    CREATE TABLE creature_actions (
        id          INTEGER PRIMARY KEY,
        creature_id INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        name        TEXT    NOT NULL,
        category    TEXT    NOT NULL DEFAULT 'action',  -- trait|action|bonus|reaction|legendary
        dice        TEXT    NOT NULL DEFAULT '',         -- optional roll expr, e.g. '2d6+3'
        description TEXT    NOT NULL DEFAULT '',
        added_at    TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    10: """
    -- The BG3-style monster inspector's DM-gated stat reveal (Phase 5). Distinct
    -- from `visibility` (whether the creature exists for players at all): this is
    -- whether the *stat block numbers* (AC/HP/abilities/defenses) are shown when a
    -- player inspects a known monster, vs. left as '?'. The DM flips it live from
    -- the inspector. Real enforcement against player logins lands in Phase 7; for
    -- now the inspector renders the player's-eye view as a preview.
    ALTER TABLE creatures ADD COLUMN stats_revealed INTEGER NOT NULL DEFAULT 0;
    """,
    11: """
    -- Saved encounters (Phase 5): a named group of monsters the DM can later
    -- load into the combat tracker (Phase 6). A member points at a creature
    -- (typically a monster from the bestiary) with a quantity, so 'Goblin x4' is
    -- one row. ON DELETE CASCADE both ways: deleting an encounter drops its
    -- members; deleting a creature drops it from every encounter.
    CREATE TABLE encounters (
        id         INTEGER PRIMARY KEY,
        name       TEXT    NOT NULL,
        created_at TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE encounter_members (
        id           INTEGER PRIMARY KEY,
        encounter_id INTEGER NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
        creature_id  INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        quantity     INTEGER NOT NULL DEFAULT 1,
        added_at     TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    12: """
    -- A creature's portrait. Stores either an emoji (e.g. '🧝') or the URL path
    -- to an uploaded image under static/avatars (e.g. '/static/avatars/3.png');
    -- '' falls back to a kind-based default. Reused for the character sheet figure
    -- now and the map overlay markers later (Phase 10).
    ALTER TABLE creatures ADD COLUMN avatar TEXT NOT NULL DEFAULT '';
    """,
    13: """
    -- Combat tracker (Phase 6). A `combat` is a live fight; `combatants` are the
    -- creatures in it. Combatants snapshot their own HP/AC at add time rather than
    -- editing the creature, so multiple instances of one stat block (Goblin 1..4)
    -- track damage independently and the fight is a scratch space that never
    -- mutates the underlying sheets. `creature_id` keeps the link (avatar/abilities)
    -- but ON DELETE SET NULL so deleting a creature leaves the combatant intact.
    -- `turn_combatant_id` points at whose turn it is (robust to add/remove, unlike
    -- an index); display order is by initiative.
    CREATE TABLE combats (
        id                INTEGER PRIMARY KEY,
        name              TEXT    NOT NULL DEFAULT 'Combat',
        round             INTEGER NOT NULL DEFAULT 1,
        turn_combatant_id INTEGER,
        created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE combatants (
        id          INTEGER PRIMARY KEY,
        combat_id   INTEGER NOT NULL REFERENCES combats(id) ON DELETE CASCADE,
        creature_id INTEGER REFERENCES creatures(id) ON DELETE SET NULL,
        name        TEXT    NOT NULL,
        initiative  INTEGER NOT NULL DEFAULT 0,
        max_hp      INTEGER NOT NULL DEFAULT 1,
        current_hp  INTEGER NOT NULL DEFAULT 1,
        temp_hp     INTEGER NOT NULL DEFAULT 0,
        armor_class INTEGER NOT NULL DEFAULT 10,
        dex_mod     INTEGER NOT NULL DEFAULT 0,
        conditions  TEXT    NOT NULL DEFAULT '',
        added_at    TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    14: """
    -- Combat history + one-time initiative. `status` keeps an ended fight around
    -- ('ended') instead of deleting it, so the Combat tab can show a history and
    -- reopen past fights. `initiative_rolled` lets the UI collapse the prominent
    -- "Roll initiative" button into a de-emphasized re-roll once it's been used.
    ALTER TABLE combats ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
    ALTER TABLE combats ADD COLUMN initiative_rolled INTEGER NOT NULL DEFAULT 0;
    """,
    15: """
    -- Accounts (Phase 7). The DM is the admin (role 'dm'); each player ('player')
    -- is tied to the PC they control via creature_id. `color` is the per-player
    -- roll colour (Phase 7d). Passwords are stored hashed (werkzeug), never plain.
    -- The shared signup code players register with lives in `meta` (key
    -- 'signup_code'), not here.
    CREATE TABLE users (
        id            INTEGER PRIMARY KEY,
        username      TEXT    NOT NULL UNIQUE,
        password_hash TEXT    NOT NULL,
        role          TEXT    NOT NULL DEFAULT 'player',  -- 'dm' | 'player'
        creature_id   INTEGER REFERENCES creatures(id) ON DELETE SET NULL,
        color         TEXT    NOT NULL DEFAULT '',
        created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    16: """
    -- Per-player roll colours (Phase 7d). Record who made each roll so the shared
    -- dice log can tint entries by roller. ON DELETE SET NULL keeps old rolls when
    -- a user is removed; the roll itself stays server-authoritative (anti-cheat).
    ALTER TABLE rolls ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
    """,
    17: """
    -- Where a creature is / was last seen (most useful for NPCs — 'the Prancing
    -- Pony', 'last seen fleeing north'). Free text; applies to any creature.
    ALTER TABLE creatures ADD COLUMN location TEXT NOT NULL DEFAULT '';
    """,
    18: """
    -- A loot item can be **currency**: coins that go straight into a character's
    -- purse when picked up (a 'Bag of Gold'), rather than an inventory item. Any
    -- non-zero coin amount marks the loot as money.
    ALTER TABLE loot_items ADD COLUMN gold   INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE loot_items ADD COLUMN silver INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE loot_items ADD COLUMN copper INTEGER NOT NULL DEFAULT 0;
    """,
    19: """
    -- Magic items. An item can grant an **AC bonus** and/or **spells** while it's
    -- equipped. These are applied by *computing* the creature's effective AC /
    -- spell list from its equipped items (not by mutating the sheet), so they
    -- revert automatically when the item is unequipped or removed. `grants_spells`
    -- is a comma-separated list of SRD spell slugs.
    ALTER TABLE creature_items ADD COLUMN ac_bonus      INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creature_items ADD COLUMN grants_spells TEXT    NOT NULL DEFAULT '';
    ALTER TABLE loot_items     ADD COLUMN ac_bonus      INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE loot_items     ADD COLUMN grants_spells TEXT    NOT NULL DEFAULT '';
    """,
    20: """
    -- Magic items, continued: an equipped item can also grant **ability-score
    -- bonuses** (Belt of Giant Strength, Amulet of Health, …). Stored compactly as
    -- 'ability:amount' pairs (e.g. 'strength:2, constitution:1'); the creature's
    -- *effective* scores are computed from equipped items, never mutating the base.
    ALTER TABLE creature_items ADD COLUMN stat_bonuses TEXT NOT NULL DEFAULT '';
    ALTER TABLE loot_items     ADD COLUMN stat_bonuses TEXT NOT NULL DEFAULT '';
    """,
    21: """
    -- Body armor that **sets** AC (5e rules), distinct from the additive `ac_bonus`
    -- (shields/rings). `armor_base` is the armor's listed AC and `armor_type`
    -- ('light'|'medium'|'heavy') sets the Dexterity cap when worn: light = full
    -- DEX, medium = +2 max, heavy = none. Effective AC is still computed from
    -- equipped items, so it reverts when removed.
    ALTER TABLE creature_items ADD COLUMN armor_base INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creature_items ADD COLUMN armor_type TEXT    NOT NULL DEFAULT '';
    ALTER TABLE loot_items     ADD COLUMN armor_base INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE loot_items     ADD COLUMN armor_type TEXT    NOT NULL DEFAULT '';
    """,
    22: """
    -- 5e unarmored AC for PCs. With no armor equipped a player character's AC is
    -- computed as 10 + DEX, optionally with Unarmored Defense ('barbarian' adds
    -- CON, 'monk' adds WIS). '' = standard. NPCs/monsters keep their manual
    -- (natural) AC. Computed in effective_ac, so it tracks DEX/items live.
    ALTER TABLE creatures ADD COLUMN unarmored_defense TEXT NOT NULL DEFAULT '';
    """,
    23: """
    -- The bones of the class system (data lives in data/classes.json). A creature
    -- records its class by slug; picking one applies a starting package (stats,
    -- HP from the hit die, gear, Unarmored Defense) and the hit die drives level-up.
    ALTER TABLE creatures ADD COLUMN class_name TEXT NOT NULL DEFAULT '';
    """,
    24: """
    -- Skill proficiencies (the proficiency layer). Saving-throw proficiency is
    -- derived from the creature's class (data/classes.json) and needs no storage;
    -- skill proficiency is chosen per creature, recorded here by SRD skill slug.
    -- The proficiency *bonus* is computed from level, never baked into the sheet
    -- (mirrors effective AC/abilities). ON DELETE CASCADE clears with the creature.
    CREATE TABLE creature_skills (
        creature_id INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        skill_slug  TEXT    NOT NULL,
        added_at    TEXT    NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (creature_id, skill_slug)
    );
    """,
    25: """
    -- Spell slots (the spellcasting resource). A creature's *maximum* slots are
    -- computed from its class + level (caster tables in models/spellcasting.py),
    -- so only *expended* slots are stored here, per spell level (1–9). Casting a
    -- leveled spell spends one; a long rest (or, for Warlocks, a short rest) clears
    -- them. Cantrips (level 0) cost no slot. ON DELETE CASCADE clears with the
    -- creature. Spellcasting *stats* (attack bonus, save DC) need no storage —
    -- they're computed from proficiency bonus + the class's spellcasting ability.
    CREATE TABLE creature_spell_slots (
        creature_id INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        slot_level  INTEGER NOT NULL,                 -- 1..9
        used        INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (creature_id, slot_level)
    );
    """,
    26: """
    -- Where an action came from, so class-granted ones can be re-synced without
    -- touching hand-added ones. '' = manual (the existing default: custom entries
    -- and action-book grabs); 'class' = auto-granted from the creature's class
    -- features (models/actions.grant_class_actions wipes + re-adds these on class
    -- change / level-up). Computed from data/classes.json, never authored here.
    ALTER TABLE creature_actions ADD COLUMN source TEXT NOT NULL DEFAULT '';
    """,
    27: """
    -- "Hide" (soft-delete / declutter) for the per-creature sheet lists. Hidden
    -- entries are filtered out of their list by default and only shown when the
    -- viewer toggles "Show hidden" — the persistent answer to dismissing things
    -- you never use (and to permanently removing an auto-granted class action: the
    -- class re-sync preserves a hidden flag, so a hidden Rage stays hidden).
    ALTER TABLE creature_actions ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creature_spells  ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creature_items   ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;
    """,
    28: """
    -- The creature's chosen subclass (archetype) slug, scoped to its class_name —
    -- '' = none yet. Validated against data/classes.json's per-class `subclasses`
    -- in the app (a pick that doesn't belong to the class is cleared). Subclass
    -- features merge into class_features() and auto-grant like base class actions.
    ALTER TABLE creatures ADD COLUMN subclass TEXT NOT NULL DEFAULT '';
    """,
    29: """
    -- Class resources: limited-use, rest-recharged pools (Rage, Ki, Channel
    -- Divinity, Lay on Hands, …). Mirrors creature_spell_slots — only the *expended*
    -- amount is stored; the *max* is computed on read from the class + level
    -- (data/classes.json `resources`). A short/long rest clears the matching keys.
    CREATE TABLE creature_resources (
        creature_id  INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        resource_key TEXT    NOT NULL,
        expended     INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (creature_id, resource_key)
    );
    """,
    30: """
    -- Ability Score Improvements: the permanent +1/+2 ability bumps a class grants
    -- at its ASI levels (4/8/12/16/19, plus Fighter 6/14, Rogue 10). The *number*
    -- of points available is computed on read from the class features list; only the
    -- *allocation* (which abilities got bumped) is stored. Effective ability scores
    -- fold it in on read (models/inventory.effective_abilities), so the base sheet is
    -- never mutated and a respec is just a row edit.
    CREATE TABLE creature_asi (
        creature_id INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        ability     TEXT    NOT NULL,
        bonus       INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (creature_id, ability)
    );
    """,
}


def get_connection():
    """Return a SQLite connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _current_version(conn):
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    return int(row["value"]) if row else 0


def init_db():
    """Create the DB if needed and apply pending migrations up to SCHEMA_VERSION."""
    conn = get_connection()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT NOT NULL"
            ")"
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', '0')"
            "  ON CONFLICT(key) DO NOTHING"
        )
        conn.commit()

        current = _current_version(conn)
        for version in range(current + 1, SCHEMA_VERSION + 1):
            conn.executescript(MIGRATIONS[version])
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                (str(version),),
            )
            conn.commit()
    finally:
        conn.close()
