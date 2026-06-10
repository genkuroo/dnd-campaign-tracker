"""SQLite bootstrap + migrations for the campaign tracker.

Schema changes are applied as ordered migrations. `init_db()` reads the current
version from the `meta` table and applies any pending migrations up to
`SCHEMA_VERSION`, so a fresh clone and an existing DB both converge to the same
schema. See CLAUDE.md for the architecture (the creature engine + the
visibility-aware model).
"""
import os
import sqlite3

import shutil

# --- Storage layout --------------------------------------------------------
#
# The app supports MULTIPLE campaigns, each its own SQLite file. They live in
# `campaigns/` under the data dir; a small `registry.db` tracks the list and an
# `active_campaign` pointer file names the one currently in play. `get_connection`
# resolves the *active* campaign per call, so the DM can toggle between campaigns
# (one table at a time — see CLAUDE.md). `DND_DATA_DIR` relocates all of this onto
# the Fly persistent volume in production (default '.' for local dev).
DATA_DIR = os.environ.get("DND_DATA_DIR", ".")
CAMPAIGNS_DIR = os.path.join(DATA_DIR, "campaigns")
REGISTRY_PATH = os.path.join(DATA_DIR, "registry.db")
ACTIVE_POINTER = os.path.join(DATA_DIR, "active_campaign")  # text file: active filename

# An EXISTING single-file DB (pre-multi-campaign) to adopt as the first campaign
# on first run, so nobody loses their data on upgrade.
LEGACY_DB_PATH = os.path.join(DATA_DIR, "campaign.db")

# Single-DB / test escape hatch. When DND_DB_PATH is set (the seed + test scripts
# do this), the whole multi-campaign layer is bypassed and every connection goes
# straight to this one file — preserving the old behaviour for throwaway DBs.
# Unset in normal app runs, which then use the multi-campaign layout above.
DB_PATH = os.environ.get("DND_DB_PATH")

SCHEMA_VERSION = 55

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
    31: """
    -- Feats a creature has taken (skeleton: tracked, no mechanics yet). A character
    -- may take a feat *instead* of an Ability Score Improvement; for now the two
    -- aren't budget-linked. Mirrors the action book — entries are grabbed from a
    -- premade catalog (data/feats.json) or hand-added, then copied here so they can
    -- be edited/removed per-creature.
    CREATE TABLE creature_feats (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        creature_id  INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        name         TEXT    NOT NULL,
        description  TEXT    NOT NULL DEFAULT '',
        prerequisite TEXT    NOT NULL DEFAULT ''
    );
    """,
    32: """
    -- Expertise: a proficient skill marked for *double* proficiency bonus
    -- (Rogue/Bard picks). A flag on the existing per-creature skill row, so
    -- expertise always implies proficiency. Half-proficiency (Jack of All Trades /
    -- Remarkable Athlete) is computed from class/subclass features, not stored.
    ALTER TABLE creature_skills ADD COLUMN expertise INTEGER NOT NULL DEFAULT 0;
    """,
    33: """
    -- Race / species (the other half of character building). Scoped like
    -- class_name/subclass: a `race` slug + an optional `subrace` slug validated
    -- against data/races.json. Racial ability-score increases fold into
    -- effective_abilities on read (like ASI); traits are a display layer.
    ALTER TABLE creatures ADD COLUMN race    TEXT NOT NULL DEFAULT '';
    ALTER TABLE creatures ADD COLUMN subrace TEXT NOT NULL DEFAULT '';
    """,
    34: """
    -- Weapon stats for an item, so an equipped weapon yields an attack + damage
    -- roll. Packed (like stat_bonuses) into one column: "damage|type|ability|
    -- category", e.g. "1d8|slashing|str|martial" ('' = not a weapon). `ability` is
    -- str/dex/finesse; `category` simple/martial drives the proficiency check.
    -- On both tables so weapons keep their stats through loot give/take/drop.
    ALTER TABLE creature_items ADD COLUMN weapon TEXT NOT NULL DEFAULT '';
    ALTER TABLE loot_items     ADD COLUMN weapon TEXT NOT NULL DEFAULT '';
    """,
    35: """
    -- Death saving throws for a combatant at 0 HP (5e): 3 successes = stable,
    -- 3 failures = dead. Only the counts are stored; the dying/stable/dead state is
    -- derived from current_hp + these. Reset when healed above 0.
    ALTER TABLE combatants ADD COLUMN death_successes INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE combatants ADD COLUMN death_failures  INTEGER NOT NULL DEFAULT 0;
    """,
    36: """
    -- Walking speed (feet). On creatures it's the manual *base* (used for NPCs/
    -- monsters, and as the fallback when no race sets it); a PC's base comes from
    -- its race. effective_speed adds class/feat modifiers (Fast Movement, Unarmored
    -- Movement, Mobile) on read. Combatants snapshot the effective speed like AC/DEX.
    ALTER TABLE creatures  ADD COLUMN speed INTEGER NOT NULL DEFAULT 30;
    ALTER TABLE combatants ADD COLUMN speed INTEGER NOT NULL DEFAULT 30;
    """,
    37: """
    -- Concentration: the one concentration spell a caster is currently maintaining
    -- (stored as its display name; '' = none). 5e allows only one at a time; casting
    -- another replaces it, and damage prompts a CON save to keep it.
    ALTER TABLE creatures ADD COLUMN concentration TEXT NOT NULL DEFAULT '';
    """,
    38: """
    -- Exhaustion level (0..6, 5e's six-step track). Tracked as a *loose display*
    -- only — the sheet shows the level and what each step would mean, but the app
    -- never auto-applies the penalties or kills a character at level 6.
    ALTER TABLE creatures ADD COLUMN exhaustion INTEGER NOT NULL DEFAULT 0;
    """,
    39: """
    -- Background slug (Acolyte, Criminal, Sage…), validated against
    -- data/backgrounds.json. The third character pillar beside race + class; grants
    -- skills/tools/languages + a roleplay feature (display + guidance, not enforced).
    ALTER TABLE creatures ADD COLUMN background TEXT NOT NULL DEFAULT '';
    """,
    40: """
    -- Tool proficiencies and known languages — comma-separated free-form lists
    -- (e.g. "Thieves' tools, Lute" / "Common, Elvish"). They come from race / class
    -- / background, but are tracked as plain text the DM/player edits; shown as chips
    -- in the sheet's Proficiencies section.
    ALTER TABLE creatures ADD COLUMN tools     TEXT NOT NULL DEFAULT '';
    ALTER TABLE creatures ADD COLUMN languages TEXT NOT NULL DEFAULT '';
    """,
    41: """
    -- Attunement: 5e's soft cap on powerful magic items. `attunement_required`
    -- flags an item that needs attunement (mirrors loot_items so it survives
    -- give/take/drop); `attuned` (creature_items only) is the per-item toggle. A
    -- creature attunes to at most 3 items — guided, not enforced. STRICT mode: an
    -- attunement-required item's bonuses (ac_bonus/stat_bonuses/grants_spells) only
    -- apply while attuned, so a worn-but-unattuned magic item lies dormant.
    ALTER TABLE creature_items ADD COLUMN attunement_required INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creature_items ADD COLUMN attuned             INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE loot_items     ADD COLUMN attunement_required INTEGER NOT NULL DEFAULT 0;
    """,
    42: """
    -- Combat damage typing: a combatant snapshots its creature's defenses on add
    -- (like AC/HP/speed), so the tracker can scale typed damage — immune → 0,
    -- resisted → half (round down), vulnerable → double — without mutating the
    -- sheet. Free-form comma text, matched word-wise against the chosen type.
    ALTER TABLE combatants ADD COLUMN resistances     TEXT NOT NULL DEFAULT '';
    ALTER TABLE combatants ADD COLUMN immunities      TEXT NOT NULL DEFAULT '';
    ALTER TABLE combatants ADD COLUMN vulnerabilities TEXT NOT NULL DEFAULT '';
    """,
    43: """
    -- Heroic Inspiration: the universal advantage token a DM grants for good play
    -- (distinct from Bardic Inspiration, a class resource). A simple have/spend
    -- boolean; the DM grants it, the owner spends it for advantage on a roll.
    ALTER TABLE creatures ADD COLUMN inspiration INTEGER NOT NULL DEFAULT 0;
    """,
    44: """
    -- Challenge Rating: a monster's difficulty (0, 1/8 … 30), stored as a float so
    -- the fractional CRs work. Drives the XP value (CR_XP table) that the encounter
    -- difficulty calculator sums. 0 for PCs/NPCs (only monsters use it).
    ALTER TABLE creatures ADD COLUMN cr REAL NOT NULL DEFAULT 0;
    """,
    45: """
    -- Phase 9a — the world narrative layer's shared entities (CLAUDE.md "model
    -- entities once, surface in many views"). NPCs are already creatures; this adds
    -- the other two typed entities — locations and factions — both carrying the
    -- same `visibility` fog-of-war spine as creatures ('hidden' until the party
    -- discovers them, then the DM reveals = 'visible'). They default to **hidden**
    -- (unlike NPCs, which default visible) since narrative places/groups are meant
    -- to be uncovered. The sidebar, blog mentions, and (later) map markers all
    -- point back at these rows rather than building parallel lists.
    CREATE TABLE locations (
        id          INTEGER PRIMARY KEY,
        name        TEXT    NOT NULL,
        kind        TEXT    NOT NULL DEFAULT 'place',    -- region|settlement|place|dungeon|landmark
        parent_id   INTEGER REFERENCES locations(id) ON DELETE SET NULL,  -- nested (region > city > inn)
        description TEXT    NOT NULL DEFAULT '',
        visibility  TEXT    NOT NULL DEFAULT 'hidden',   -- 'visible' | 'hidden'
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE factions (
        id          INTEGER PRIMARY KEY,
        name        TEXT    NOT NULL,
        description TEXT    NOT NULL DEFAULT '',
        disposition TEXT    NOT NULL DEFAULT 'neutral',  -- reuses the creature disposition spectrum
        visibility  TEXT    NOT NULL DEFAULT 'hidden',
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    -- A creature (NPC or PC) can belong to one location + one faction. 0 = unset
    -- (kept as a plain int rather than a FK so a deleted location/faction just
    -- orphans the pointer, resolved as "none" on read — mirrors meta.current_area_id).
    ALTER TABLE creatures ADD COLUMN location_id INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creatures ADD COLUMN faction_id  INTEGER NOT NULL DEFAULT 0;
    """,
    46: """
    -- Phase 9b — the campaign journal: a two-level notes system (folders → notes)
    -- with both a DM side and a player side. Every folder/note has an `owner_id`
    -- (the user who wrote it); a note carries a private|shared visibility. A note
    -- is visible to its owner, the DM (omniscient), and — when 'shared' — the whole
    -- party. A folder surfaces to a viewer when they own it or it holds a note they
    -- can see. ON DELETE CASCADE: deleting a user drops their journal; deleting a
    -- folder drops its notes.
    CREATE TABLE journal_folders (
        id          INTEGER PRIMARY KEY,
        owner_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title       TEXT    NOT NULL,
        description TEXT    NOT NULL DEFAULT '',
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE journal_notes (
        id          INTEGER PRIMARY KEY,
        folder_id   INTEGER NOT NULL REFERENCES journal_folders(id) ON DELETE CASCADE,
        owner_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title       TEXT    NOT NULL,
        body        TEXT    NOT NULL DEFAULT '',
        visibility  TEXT    NOT NULL DEFAULT 'private',  -- 'private' | 'shared'
        created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    47: """
    -- Phase 9b mentions: a journal note can tag the world entities it features
    -- (NPCs/PCs = creatures, locations, factions). Polymorphic by (entity_type,
    -- entity_id) — no FK on entity_id since it spans three tables; a deleted
    -- entity just orphans the row, skipped on read. ON DELETE CASCADE drops a
    -- note's mentions with the note. The index serves the "Mentioned in" back-
    -- reference query on an entity's page.
    CREATE TABLE note_mentions (
        note_id     INTEGER NOT NULL REFERENCES journal_notes(id) ON DELETE CASCADE,
        entity_type TEXT    NOT NULL,   -- 'creature' | 'location' | 'faction'
        entity_id   INTEGER NOT NULL,
        PRIMARY KEY (note_id, entity_type, entity_id)
    );
    CREATE INDEX idx_note_mentions_entity ON note_mentions(entity_type, entity_id);
    """,
    48: """
    -- Phase 9c — the quest / objective log. A quest is a DM-authored goal with a
    -- `status` (active|completed|failed) and the same `visibility` fog-of-war
    -- spine as locations/factions (default hidden — revealed when the party picks
    -- it up). Each quest has ordered sub-objectives, themselves status-tracked and
    -- individually hide-able (a secret objective inside a known quest). ON DELETE
    -- CASCADE drops a quest's objectives with it.
    CREATE TABLE quests (
        id          INTEGER PRIMARY KEY,
        title       TEXT    NOT NULL,
        description TEXT    NOT NULL DEFAULT '',
        status      TEXT    NOT NULL DEFAULT 'active',   -- 'active' | 'completed' | 'failed'
        visibility  TEXT    NOT NULL DEFAULT 'hidden',   -- 'visible' | 'hidden'
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE quest_objectives (
        id          INTEGER PRIMARY KEY,
        quest_id    INTEGER NOT NULL REFERENCES quests(id) ON DELETE CASCADE,
        description TEXT    NOT NULL,
        status      TEXT    NOT NULL DEFAULT 'open',      -- 'open' | 'done' | 'failed'
        visibility  TEXT    NOT NULL DEFAULT 'visible',   -- 'visible' | 'hidden'
        position    INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    49: """
    -- Phase 10a — maps. A map is an uploaded background image the DM can place
    -- overlay markers on (markers arrive in 10b). It carries the same `visibility`
    -- fog-of-war spine as locations/factions (default hidden — revealed once the
    -- party has explored it). `location_id` optionally ties a map to a place
    -- (0 = none, orphan-on-delete, resolved as "none" on read — like the existing
    -- creature.location_id pattern), so a Location detail can link to its map.
    CREATE TABLE maps (
        id          INTEGER PRIMARY KEY,
        name        TEXT    NOT NULL,
        image       TEXT    NOT NULL DEFAULT '',     -- uploaded background URL ('' = none yet)
        description TEXT    NOT NULL DEFAULT '',
        location_id INTEGER NOT NULL DEFAULT 0,       -- linked place (0 = none)
        visibility  TEXT    NOT NULL DEFAULT 'hidden',-- 'visible' | 'hidden'
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    """,
    50: """
    -- Phase 10b — map markers. An interactable overlay pin on a map, positioned by
    -- FRACTIONAL coords (`x`/`y` in 0..1) so it stays put at any zoom/resolution.
    -- A marker optionally points at an entity via the same polymorphic (type, id)
    -- pattern as note_mentions — `entity_type` 'creature'|'location'|'faction'|'map'
    -- (or '' for a free-text label pin), `entity_id` (no FK; orphan-skipped on
    -- read). A 'map'-type marker drills down to a sub-map (global→local). Carries
    -- the `visibility` fog-of-war spine (10c reveals/hides per marker). ON DELETE
    -- CASCADE drops a map's markers with it.
    CREATE TABLE map_markers (
        id          INTEGER PRIMARY KEY,
        map_id      INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
        x           REAL    NOT NULL DEFAULT 0.5,     -- fractional 0..1
        y           REAL    NOT NULL DEFAULT 0.5,
        entity_type TEXT    NOT NULL DEFAULT '',       -- '' | 'creature' | 'location' | 'faction' | 'map'
        entity_id   INTEGER NOT NULL DEFAULT 0,
        label       TEXT    NOT NULL DEFAULT '',
        icon        TEXT    NOT NULL DEFAULT '',        -- emoji for free-label pins
        visibility  TEXT    NOT NULL DEFAULT 'visible', -- 'visible' | 'hidden'
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_map_markers_map ON map_markers(map_id);
    """,
    51: """
    -- Phase 12a — player-controlled companions. A creature can be put under a
    -- player's *control* (a DM-granted NPC ally, or a 12b summon) — distinct from
    -- the strict one-PC ownership link (`users.creature_id`), which stays
    -- untouched. `controlled_by` holds the controlling user's id (0 = none); a
    -- player controls many creatures, each creature has at most one controller.
    -- can_view/can_edit_creature extend to "…or the player controls it", so
    -- control rides the existing visibility spine. No FK (orphan-on-user-delete
    -- resolves as "none" on read, like creature.location_id).
    ALTER TABLE creatures ADD COLUMN controlled_by INTEGER NOT NULL DEFAULT 0;
    """,
    52: """
    -- Phase 12b — summons. A summoned creature (familiar, conjured beast) is just
    -- a creature (`kind='monster'`) the summoner `controls` (12a), flagged
    -- `is_summon=1` so it's (a) excluded from the DM's Bestiary clutter and (b)
    -- player-dismissable (a regular DM-granted companion is not). Spawned from the
    -- bundled data/summons.json catalog; Dismiss = delete.
    ALTER TABLE creatures ADD COLUMN is_summon INTEGER NOT NULL DEFAULT 0;
    """,
    53: """
    -- Combat log. A running record of what happened in a fight: who attacked
    -- whom with what spell/action, the roll, and the damage/healing. Names are
    -- snapshotted as text (like the dice roll log) so an entry survives a
    -- combatant being removed. `kind` distinguishes a full 'attack' record from
    -- a quick 'damage'/'heal' HP adjustment (auto-logged from the tracker) or a
    -- freeform 'note'. `amount` is the damage applied (or healing for 'heal').
    CREATE TABLE combat_log (
        id          INTEGER PRIMARY KEY,
        combat_id   INTEGER NOT NULL REFERENCES combats(id) ON DELETE CASCADE,
        round       INTEGER NOT NULL DEFAULT 1,
        kind        TEXT    NOT NULL DEFAULT 'attack',  -- 'attack'|'damage'|'heal'|'note'
        actor       TEXT    NOT NULL DEFAULT '',        -- attacker name (snapshot)
        target      TEXT    NOT NULL DEFAULT '',        -- target name (snapshot)
        action      TEXT    NOT NULL DEFAULT '',        -- spell / action / attack name
        attack_roll INTEGER,                            -- to-hit / save roll (nullable)
        amount      INTEGER,                            -- damage dealt / HP healed (nullable)
        damage_type TEXT    NOT NULL DEFAULT '',
        detail      TEXT    NOT NULL DEFAULT '',        -- extra note / resisted label
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_combat_log_combat ON combat_log(combat_id);
    """,
    54: """
    -- Graveyard. A fallen PC, a slain unique boss, or a notable NPC who has died
    -- is still a *creature* (the engine is reused wholesale — the sheet stays as a
    -- memorial) but is retired from active play: `deceased=1` drops it from the
    -- roster/party/bestiary/sidebar lists and surfaces it on the Graveyard tab.
    -- `epitaph` is an optional cause-of-death / memorial note; `deceased_at`
    -- timestamps the death (set when laid to rest, cleared on restore).
    ALTER TABLE creatures ADD COLUMN deceased    INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE creatures ADD COLUMN epitaph     TEXT    NOT NULL DEFAULT '';
    ALTER TABLE creatures ADD COLUMN deceased_at TEXT;
    """,
    55: """
    -- PC-to-PC trading. A directed offer one PC sends another: an inventory item
    -- OR a sum of coins. Nothing moves until the recipient accepts (status flips
    -- pending → accepted/declined; the giver may cancel). Item/gold are validated
    -- and transferred at accept time (not escrowed), so an offer that the giver can
    -- no longer honour just fails. Both creature FKs cascade-delete the offer with
    -- the creature; `item_id` cascades too, so disposing of an item drops its
    -- pending offer (no dangling rows).
    CREATE TABLE trade_offers (
        id               INTEGER PRIMARY KEY,
        from_creature_id INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        to_creature_id   INTEGER NOT NULL REFERENCES creatures(id) ON DELETE CASCADE,
        kind             TEXT    NOT NULL DEFAULT 'item',  -- 'item' | 'gold'
        item_id          INTEGER REFERENCES creature_items(id) ON DELETE CASCADE,
        gold             INTEGER NOT NULL DEFAULT 0,
        silver           INTEGER NOT NULL DEFAULT 0,
        copper           INTEGER NOT NULL DEFAULT 0,
        status           TEXT    NOT NULL DEFAULT 'pending',  -- pending|accepted|declined|cancelled
        created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_trade_to   ON trade_offers(to_creature_id, status);
    CREATE INDEX idx_trade_from ON trade_offers(from_creature_id, status);
    """,
}


def _connect(path):
    """Open a SQLite connection to `path` with our standard settings."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Wait briefly instead of erroring if another process holds a write lock.
    # Matters once multiple gunicorn workers share one SQLite file in prod.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def current_db_path():
    """The campaign-DB file this request should use. In single-DB/test mode
    (DND_DB_PATH set) it's that fixed file; otherwise it's the active campaign."""
    if DB_PATH:
        return DB_PATH
    return os.path.join(CAMPAIGNS_DIR, active_campaign_filename())


def get_connection():
    """Return a connection to the active campaign DB (rows keyed by column name)."""
    return _connect(current_db_path())


# --- Campaign registry + active-campaign pointer ---------------------------

def get_registry_connection():
    """Connection to the small registry DB (the campaign list + active marker)."""
    return _connect(REGISTRY_PATH)


def active_campaign_filename():
    """The filename of the active campaign. Read from the pointer file (cheap,
    shared across gunicorn workers); falls back to the registry, then the first
    campaign, so a missing/stale pointer self-heals."""
    try:
        with open(ACTIVE_POINTER) as fh:
            name = fh.read().strip()
        if name and os.path.exists(os.path.join(CAMPAIGNS_DIR, name)):
            return name
    except OSError:
        pass
    # Fall back to the registry's record, then the first campaign on file.
    conn = get_registry_connection()
    try:
        row = conn.execute(
            "SELECT value FROM reg_meta WHERE key = 'active_filename'"
        ).fetchone()
        name = row["value"] if row else ""
        if not name:
            first = conn.execute(
                "SELECT filename FROM campaigns ORDER BY id LIMIT 1"
            ).fetchone()
            name = first["filename"] if first else ""
    finally:
        conn.close()
    if name:
        set_active_filename(name)  # repair the pointer
    return name


def set_active_filename(filename):
    """Mark `filename` as the active campaign in both the pointer file (the hot
    path) and the registry (the source of truth)."""
    tmp = ACTIVE_POINTER + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(filename)
    os.replace(tmp, ACTIVE_POINTER)  # atomic
    conn = get_registry_connection()
    try:
        conn.execute(
            "INSERT INTO reg_meta (key, value) VALUES ('active_filename', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (filename,),
        )
        conn.commit()
    finally:
        conn.close()


def _init_registry():
    """Create the registry schema if absent."""
    conn = get_registry_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                id            INTEGER PRIMARY KEY,
                name          TEXT NOT NULL,
                filename      TEXT NOT NULL UNIQUE,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                last_played_at TEXT
            );
            CREATE TABLE IF NOT EXISTS reg_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def register_campaign(name, filename):
    """Insert a campaign into the registry. Returns the new id."""
    conn = get_registry_connection()
    try:
        cur = conn.execute(
            "INSERT INTO campaigns (name, filename) VALUES (?, ?)",
            (name, filename),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# --- Schema migrations -----------------------------------------------------

def _current_version(conn):
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    return int(row["value"]) if row else 0


def _apply_migrations(conn):
    """Bring one campaign DB up to SCHEMA_VERSION (idempotent)."""
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


def migrate_path(path):
    """Apply pending migrations to the campaign DB at `path`."""
    conn = _connect(path)
    try:
        _apply_migrations(conn)
    finally:
        conn.close()


def init_db():
    """Bootstrap storage and apply pending migrations.

    Single-DB/test mode (DND_DB_PATH set): just migrate that one file, as before.
    Multi-campaign mode: ensure the registry + at least one campaign exist (adopting
    a legacy single-file DB on first run), then migrate every campaign to the
    current schema so older saves upgrade cleanly too.
    """
    if DB_PATH:
        migrate_path(DB_PATH)
        return

    os.makedirs(CAMPAIGNS_DIR, exist_ok=True)
    _init_registry()
    _bootstrap_campaigns()
    # Migrate every registered campaign (covers older saves switched to later).
    conn = get_registry_connection()
    try:
        files = [r["filename"] for r in
                 conn.execute("SELECT filename FROM campaigns").fetchall()]
    finally:
        conn.close()
    for filename in files:
        migrate_path(os.path.join(CAMPAIGNS_DIR, filename))


def _bootstrap_campaigns():
    """Ensure at least one campaign is registered + active. On first run, adopt an
    existing legacy `campaign.db` (so no data is lost on upgrade); otherwise create
    a fresh, empty 'My Campaign'."""
    conn = get_registry_connection()
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM campaigns").fetchone()["n"]
    finally:
        conn.close()

    if count == 0:
        dest = os.path.join(CAMPAIGNS_DIR, "campaign.db")
        if os.path.exists(LEGACY_DB_PATH) and not os.path.exists(dest):
            # Adopt the pre-multi-campaign DB as the first campaign (copy, leaving
            # the original in place as an untouched backup).
            shutil.copy2(LEGACY_DB_PATH, dest)
        register_campaign("My Campaign", "campaign.db")
        # `migrate_path` in init_db() will create the schema for a fresh file.
        set_active_filename("campaign.db")
    else:
        # Make sure the active pointer resolves to a real campaign.
        active_campaign_filename()
