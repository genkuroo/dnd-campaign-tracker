"""SQLite bootstrap + migrations for the campaign tracker.

Schema changes are applied as ordered migrations. `init_db()` reads the current
version from the `meta` table and applies any pending migrations up to
`SCHEMA_VERSION`, so a fresh clone and an existing DB both converge to the same
schema. See CLAUDE.md for the architecture (the creature engine + the
visibility-aware model).
"""
import sqlite3

DB_PATH = "campaign.db"

SCHEMA_VERSION = 14

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
