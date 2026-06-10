# CLAUDE.md

Guidance for Claude Code working in this repository. This file is the **conceptual
map**: what the app is, the architecture, the recurring patterns, current status,
and conventions. For the detailed phase-by-phase build history (migrations, model
files, exactly how each feature was built), see **`docs/BUILD_LOG.md`**.

## What this is

A **D&D 5e campaign tracker** — a personal tool for the owner, who is the
**Dungeon Master (DM)**, with a **website** his players log into to track their
own characters. Built phase-by-phase as both a real tool and a tech-learning
project (the first genuinely **multi-user, authenticated, hosted web app** in
the sibling-projects workspace).

The owner and players are **new to D&D**, so the app doubles as a way to *learn
the game*: it surfaces rules text (spell/ability descriptions, dice) inline.

**Posture:** mostly **track** (record-keeping), with targeted **assist** features
(dice roller, combat math, rules lookup) where they clearly earn their place.

## Roles & audience

- **DM (owner)** = admin. Sees and edits the entire campaign world, including
  hidden/secret entities the players don't know about.
- **Players (friends)** = each logs in, sees only their own character and the
  things they've discovered or the DM has shared.

## The two architectural spines

Everything hangs off two core ideas. Get these right and features are mostly
views on top. **When adding any feature, ask: does it reuse the creature engine?
does it respect visibility? Don't fork either.**

### 1. The creature / stat-block engine

A **PC, an NPC, and a monster are the same kind of thing**: a *creature* with a
stat block (six ability scores, HP, AC, resistances/immunities, conditions,
abilities). Model this **once**. The `kind` column ('pc' | 'npc' | 'monster') is
the only thing that distinguishes them — a tavern keeper is just a low-stat NPC.

- A **character sheet** = the full, editable creature view (player-owned).
- The **monster inspector** (BG3-style "inspect") = a trimmed, read-only view.
- **Combat tracking** operates on creatures generically — PCs and monsters with
  no special-casing.
- Two world-flavor traits live on every creature: **`disposition`** (a 5-point
  hate→love spectrum: hostile|unfriendly|neutral|friendly|allied; the DM can flip
  it **live**) and **`alignment`** (LG..CE).

### 2. The public/private visibility spine ("fog of war")

Every **entity** (creature, location, faction, map marker, quest, even individual
monster stats) carries a **visibility state**:

- The **DM sees everything.**
- **Players see only what they've discovered / the DM has revealed.**

This is **not one feature** — it's a rule the character sheets, monster inspector,
map overlays, journal, quests, and entity sidebar all enforce. **Visibility is
server-side** — never ship DM-hidden data to the client and hide it with CSS/JS.

### The shared "entity" concept

The **sidebar list of known things**, the **map markers**, and the **things
mentioned in journal notes** all point at the *same underlying entities*. Entities
are **typed, not one generic table**: NPCs stay creatures; locations and factions
get their own tables; references are by **(entity_type, id)**. Don't build parallel
lists.

## Recurring implementation patterns

These show up across nearly every feature — follow them when extending:

- **Computed on read, never stored.** Derived numbers (effective AC, effective
  abilities incl. race/ASI/item bonuses, proficiency bonus, saves, skills, spell
  attack/DC, class features, resources, speed) are computed from base data at
  render time. The base sheet is **never mutated**, so bonuses revert
  automatically on unequip/level-down/etc. Mirror this for new derived stats.
- **Snapshot on add (combat).** Combatants copy their own HP/AC/speed/defenses
  when added to a fight, so multiple instances of one stat block act
  independently and combat never mutates the sheets.
- **Reconcile, don't wipe.** Auto-granted content (class actions) is reconciled
  on class/level change — keep still-wanted rows (preserving edits + `hidden`),
  drop stale, add new. Idempotent.
- **AJAX fragment re-render.** Sheet sections (`#gear`, `#spells`, `#actions`,
  `#feats`, `#resources`, `#combat`) re-render via fetch with no page reload;
  delegated handlers survive replacement; **non-JS always falls back to
  POST→redirect**. Dice rolls are app-wide AJAX with a floating roll toast.
- **Guided, not enforced.** Many 5e limits (skill counts, spells known/prepared,
  proficiency warnings, encounter difficulty, exhaustion) are *surfaced and
  flagged* but not hard-blocked — multiclass/background/feat/item sources aren't
  fully modeled, so a hard block would misfire.
- **Edit-gating.** A player edits only their own PC (and any creature they
  control); `can_view_creature` / `can_edit_creature` + a `before_request` block
  of `_DM_ONLY_ENDPOINTS` enforce it. UI controls thread a `can_edit` flag;
  routes 403 independently. Default a query to the *least* privileged view and
  widen for the DM, not the reverse.
- **Catalog → grab onto creature.** Spells, actions, feats, loot, summons follow
  one shape: a bundled `data/*.json` catalog, surfaced in a picker, **copied**
  onto the creature so it can be tweaked/removed per-creature. Custom-add covers
  anything missing.

## Tech decisions

- **Python + Flask**, **SQLite** (stdlib `sqlite3`), server-rendered Jinja
  templates + light JS. No build step (the map's canvas work is plain JS).
- **Schema migrations** run in `db.py` at import (`init_db()`), so every boot /
  every campaign DB is brought to the current version. The migration index lives
  in `docs/BUILD_LOG.md`.
- **Rules data** = D&D 5e **SRD** (CC-BY-4.0), bundled locally in `data/*.json`.
  **Attribute per CC-BY.** The SRD doesn't cover everything (PHB text is *not*
  redistributable) — non-SRD catalog entries carry **original paraphrased**
  summaries (game *mechanics* aren't copyrightable, only exact wording), and
  custom-add covers gaps.
- **Hosting:** Fly.io, gunicorn in Docker, one machine + a persistent volume at
  `/data`. Multiple campaigns = separate SQLite files. See README + `BUILD_LOG`.

## Current status

The app is **built out and deployed** (live on Fly.io). All core phases are done;
what remains is post-launch ideas. See `docs/BUILD_LOG.md` for full detail.

**Done (0–10, 12):** scaffold · creature engine + sheets · dice · spells & SRD
reference · inventory/loot/equipment · monsters/inspector/encounters · combat
tracker · accounts/roles/visibility enforcement · the full class system (classes,
subclasses, features, resources, scaling, ASI/feats, proficiency, spellcasting,
expertise) · race/background/weapons/death-saves/speed/concentration/exhaustion ·
attunement + combat damage types + inspiration + adv/dis + crits + CR · hosting +
multi-campaign · world layer (locations/factions/journal/quests/known-entities
sidebar) · maps with markers + fog · companions & summons.

**Not done / deferred:**
- **Hit dice as a real short-rest resource** — skipped (owner is happy with the
  Party tab's "half missing HP" fudge).
- **Session scheduling** + optional AI assists (NPC gen, session summaries) —
  "near the end."
- **LAN / local-hosting convenience** (pinned 2026-06-10) — env-driven
  host/port/debug so `HOST=0.0.0.0 python app.py` serves an in-person game on
  the local network. Low priority (the Fly URL already works in-room).
- **Phase 11 — ambient/media embeds** — **decided against** (better solved
  outside the app; in-page player stutters on the full-page-reload nav).
- **Phase 13 — blank-slate / homebrew mode** (DM-editable, DB-backed content
  catalogs; SRD/PHB-free distributable) — idea, not committed.
- **Phase 14 — multiclassing** — deferred post-launch; the most invasive change
  to the class spine.

When something here is finished or a new direction is decided, update this status
block and add the detail to `docs/BUILD_LOG.md`.

## Project layout

```
dnd-campaign-tracker/
├── app.py              # Flask entry (port 5002); routes + permission gates
├── db.py               # SQLite bootstrap + migrations (init_db at import)
├── models/             # creature engine, entities, derived stats, visibility
├── templates/          # tab views, sidebar, sheet + AJAX fragments, macros
├── static/             # css/js; map canvas; avatars/ + maps/ (gitignored)
├── data/               # bundled SRD reference (CC-BY-4.0): spells, classes,
│                       #   races, backgrounds, feats, items, actions, summons,
│                       #   monsters (bestiary import catalog)
├── docs/BUILD_LOG.md   # detailed build history (this file's companion)
├── campaigns/          # per-campaign SQLite DBs (gitignored)
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

**Testing hygiene:** never run against the live campaign DB — use a temp DB via
`DND_DB_PATH` (forces single-DB/test mode; tests/seed unaffected).

## Conventions

- **Two spines first** (reuse the creature engine; respect visibility).
- **Visibility is server-side.** Never client-side hide DM data.
- **SRD attribution.** Anything from the 5e SRD carries CC-BY-4.0 attribution;
  non-SRD catalog text is original paraphrase.
- **DM data vs player data** stay clearly separated in queries.
- **No build step** unless a phase truly needs one.
- **Commits / PRs: no AI attribution.** No `Co-Authored-By: Claude` trailer, no
  "Generated with Claude Code" line. Plain commit messages. Solo repo — commit
  directly to `main`, no branches; push/force-push only when asked.

## D&D glossary (for the owner — and future sessions)

- **DM** — runs the game and world; the admin role. **PC** — player character.
  **NPC** — non-player character (run by the DM).
- **Ability scores** — STR, DEX, CON, INT, WIS, CHA. Most numbers derive from
  these via a **modifier** = `floor((score-10)/2)`.
- **Check / saving throw** — `d20 + modifier` vs a **DC** (Difficulty Class).
  Check = attempt something; save = resist something.
- **AC (Armor Class)** — how hard to hit. **HP** — health.
- **Initiative** — turn order in combat (`d20 + DEX modifier`).
- **Condition** — status effect (poisoned, prone, stunned, frightened, …).
- **Spell slot** — a consumable resource for casting; refreshes on a long rest.
- **Short rest / long rest** — recovery that restores HP / resources.
- **Encounter** — a prepared set of monsters. **Stat block** — a creature's
  combat-relevant numbers. **CR** — Challenge Rating (monster difficulty).
- **SRD** — System Reference Document; the CC-BY-4.0 subset of 5e we draw from.
- **dNN notation** — `d20` = roll a 20-sided die; `2d6+3` = two d6 plus 3.
```

