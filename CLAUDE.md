# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **D&D campaign tracker** — a personal tool for the project owner, who is the **Dungeon Master (DM)**, with a **website** his players log into to track their own characters. Built phase-by-phase as both a real tool and a tech-learning project (the natural "next level up" from the sibling `stock-tracker` and `cloud-habit-tracker` projects: this one is the first genuinely **multi-user, authenticated, hosted web app** in the workspace).

The owner and his players are **new to D&D**, so the app doubles as a way to *learn the game*: it surfaces rules text (spell/ability descriptions, dice) inline so the table doesn't need to memorize the rulebook.

**Posture:** mostly **track** (record-keeping), with targeted **assist** features (dice roller, combat math, rules lookup) where they clearly earn their place.

## Roles & audience

- **DM (owner)** = admin. Sees and edits the entire campaign world, including hidden/secret entities the players don't know about.
- **Players (friends)** = each logs in, sees only their own character and the things they've discovered or the DM has shared.

## The two architectural spines

Everything in this app hangs off two core ideas. Get these right and the features are mostly views on top.

### 1. The creature / stat-block engine

A **player character, an NPC, and a monster are the same kind of thing**: a *creature* with a stat block (six ability scores, HP, AC, resistances/immunities, conditions, abilities). Model this **once**. The `kind` column ('pc' | 'npc' | 'monster') is the only thing that distinguishes them — a tavern keeper is just a low-stat NPC. Two world-flavor traits also live on every creature (migration 2):

- **`disposition`** — a 5-point spectrum, hate→love: 'hostile' | 'unfriendly' | 'neutral' | 'friendly' | 'allied'. How the creature treats the party. The DM can flip it **live** from the creature's page (a friendly merchant turning hostile mid-scene), not just via the edit form. Surfaced for NPCs/monsters.
- **`alignment`** ('' | LG..CE) — the creature's moral compass. A separate, more granular axis from disposition; applies to anyone, including PCs.

- A **character sheet** = the full, editable creature view (player-owned).
- The **monster inspector** (Baldur's Gate 3-style "inspect") = a trimmed, read-only creature view.
- **Combat tracking** operates on creatures generically, so it works for PCs and monsters with no special-casing.

### 2. The public/private visibility spine ("fog of war")

Every **entity** (NPC, location, map marker, monster, even individual monster stats and abilities) carries a **visibility state** per viewer:

- The **DM sees everything.**
- **Players see only what they've discovered** (invisible / partially-known / fully-known).

This is **not one feature** — it's a rule the character sheets, monster inspector, map overlays, campaign blog, and entity sidebar all enforce. **Bake a `visibility` concept into the data model from Phase 1**, even while the app is still single-user (DM-only). Real enforcement against player logins arrives in the auth phase, but the schema must anticipate it from the start.

## Shared "entity" concept

The **sidebar list of known things**, the **map markers**, and the **things mentioned in the campaign blog** all point at the *same underlying entities* (NPCs, locations, factions, items). Model entities **once** and surface them in multiple views — do not build three parallel lists.

## Tech decisions

- **Language / framework:** Python + **Flask** (continuity with `stock-tracker`; owner already knows the patterns).
- **Storage:** **SQLite** (stdlib `sqlite3`) to start, same as stock-tracker Phase 3+. Revisit only if hosting demands it.
- **Frontend:** server-rendered templates + light JS. Keep it simple early; the interactive map (late phase) is the one place that needs real client-side canvas work.
- **Rules data source:** D&D 5e **SRD** content, available under **CC-BY-4.0** (System Reference Document 5.1). Pull spell/ability/monster reference data from an open SRD source (e.g. Open5e / the 5e-SRD API), bundled locally where practical. **Attribute per CC-BY.** The SRD does not cover *every* official spell/monster (some are in paid books) — design so custom entries can be hand-added.
- **Privacy:** DM secrets and hidden entities must never leak to the player-facing API/templates. Treat visibility as a server-side filter, never a client-side hide.
- **AI (optional, later):** the workspace already has Claude API patterns (`stock-tracker`). Possible assist uses — generating an NPC, summarizing a session — are explicitly *late / optional*, not core.

## Phased plan

Ordering favors dependencies and the "local single-user first → auth → hosting → ambitious visuals last" arc the owner asked for. The visibility field is designed in from Phase 1; it is *enforced against players* in Phase 7.

- [x] **Phase 0 — Scaffold & shell.** Flask app (`app.py`, port 5002), SQLite bootstrap (`db.py`, `meta`/schema-version table), base layout with the tab navigation shell (Character / Spells & Actions / Map / Blog) + entity sidebar placeholder. No real data yet.
- [x] **Phase 1 — Creature engine + character sheets.** Six ability scores + modifiers (`floor((score-10)/2)`), HP, AC, resistances/immunities/vulnerabilities. Shared `creatures` table (migration 1) with `kind` ('pc'|'monster') and the `visibility` field ('visible'|'hidden'). `models/creature.py` owns the stat-block math + CRUD; Character Sheet tab does list/view/create/edit/delete. DM-only, local — player enforcement of `visibility` waits for Phase 7.
- [x] **Phase 2 — Dice roller.** `models/dice.py`: `parse_and_roll` is the single entry point — it dispatches an optional adv/dis suffix (`d20 adv`, `d20+3 dis`) to `roll_check`, else parses an expression (`2d6+3`, `1d20+1d4-1`, bounds-guarded). Dice tab uses a **confirm-before-roll** flow: quick buttons (d4–d100, adv/dis) only *populate* the expression box via JS (dice append, adv/dis replace); nothing rolls until the Roll button — keeps accidental clicks from flooding the roll log. Persisted log = migration 3 `rolls` table + `models/roll_log.py`; each entry shows a local-time stamp (relative time on hover), and a >5-min pause (`ROLL_GAP_SECONDS`) draws a divider grouping rolls into bursts (`_decorate_rolls`). Wired to the sheet: a per-ability **Check** button rolls `d20 + modifier`, logs it, flashes in place (`next` returns to the sheet; `_safe_next` blocks open redirects). Saving throws fold in once proficiency exists.
- [ ] **Phase 3 — Spells/abilities + SRD rules reference.** Spells & Actions tab. Pull SRD descriptions; "inspect" a spell/ability to read what it does. Dice in descriptions (e.g. `1d8`) are **clickable → roll**. Respects visibility/permissions.
- [ ] **Phase 4 — Inventory, loot, currency, XP/leveling.** Items on creatures; gold/silver/copper; XP + character level.
- [ ] **Phase 5 — Monsters, inspector, encounters.** Monster stat blocks (reuse the creature engine), the BG3-style read-only inspector (with optional DM-gated stat reveal), and saved **encounters** (named groups of monsters) to load into combat.
- [ ] **Phase 6 — Combat tracker.** Initiative order, conditions (poisoned/prone/stunned/…), apply damage/healing/temp HP, short rest / long rest resets. Operates on creatures, so PCs + monsters in one tracker.
- [ ] **Phase 7 — Accounts, roles & the visibility spine (enforced).** Login, DM-vs-player permissions, server-side enforcement of public/private knowledge across every view. **This is the leap to a true multi-user web app.**
- [ ] **Phase 8 — Hosting / deployment.** Put it online so friends can reach it (reuse the Cloudflare or AWS toolchains from the habit-tracker projects).
- [ ] **Phase 9 — World narrative layer.** Campaign blog + quest/objective log + the "entities you're aware of" sidebar, all wired to the shared entity model and visibility. (Track-only; could be pulled earlier if desired.)
- [ ] **Phase 10 — Maps.** Global + local maps with image backgrounds, position + interactable **overlay markers**, per-player visibility on markers. Most technically ambitious; intentionally last.
- [ ] **Later / optional — Session scheduling.** Owner explicitly wants this near the end. Optional AI assists (NPC generation, session summaries) also slot here.

## Planned project layout (grows with phases)

```
dnd-campaign-tracker/
├── app.py              # Flask entry (Phase 0)
├── models/             # creature engine, entities, visibility
├── templates/          # tab views, sidebar, sheets
├── static/             # css/js; map canvas (Phase 10)
├── data/               # bundled SRD reference data (CC-BY-4.0)
├── campaign.db         # SQLite (gitignored)
├── requirements.txt
├── README.md
└── CLAUDE.md
```

## Running

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py          # serves at http://127.0.0.1:5002 (init_db runs on startup)
```

## Conventions

- **Two spines first.** When adding any feature, ask: does it reuse the creature engine? does it respect visibility? Don't fork either.
- **Visibility is server-side.** Never ship DM-hidden data to the client and hide it with CSS/JS.
- **SRD attribution.** Anything sourced from the 5e SRD must carry CC-BY-4.0 attribution.
- **DM data vs player data** stay clearly separated in queries; default a query to the *least* privileged view and widen for the DM, not the reverse.
- **No build step** unless a phase truly needs one (likely only the map).

## D&D glossary (for the owner — and future sessions)

- **DM (Dungeon Master)** — runs the game and the world; the admin role here.
- **PC** — player character. **NPC** — non-player character (run by the DM).
- **Ability scores** — STR, DEX, CON, INT, WIS, CHA. Most numbers derive from these via a **modifier**.
- **Check / saving throw** — `d20 + modifier` vs a **DC** (Difficulty Class). Check = attempt something; save = resist something.
- **AC (Armor Class)** — how hard a creature is to hit. **HP (Hit Points)** — health.
- **Initiative** — turn order in combat (`d20 + DEX modifier`).
- **Condition** — status effect (poisoned, prone, stunned, frightened, unconscious, …).
- **Spell slot** — a consumable resource for casting; refreshes on a **long rest**.
- **Short rest / long rest** — recovery mechanics that restore HP / resources.
- **Encounter** — a prepared set of monsters for a fight.
- **Stat block** — the bundle of a creature's combat-relevant numbers.
- **SRD** — System Reference Document; the openly-licensed (CC-BY-4.0) subset of D&D 5e rules we draw reference text from.
- **dNN notation** — `d20` = roll a 20-sided die; `2d6+3` = roll two d6 and add 3.
