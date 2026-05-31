# D&D Campaign Tracker

A web app for running a Dungeons & Dragons 5e campaign. The **Dungeon Master** manages
the whole world; **players** log in to track their own characters and look up how their
spells and abilities work — handy for a table that's new to D&D.

> Status: **Phase 0 complete** — Flask shell with tab navigation, entity-sidebar placeholder, and SQLite bootstrap. See [CLAUDE.md](./CLAUDE.md) for the full architecture and phased plan.

## Running

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py    # http://127.0.0.1:5002
```

## What it does (planned)

- **Character sheets** — ability scores, HP, AC, resistances, inventory.
- **Spells & actions** with inline **5e SRD rules text**, so new players can read what a spell does — including clickable dice (`1d8` → roll it).
- **Dice roller** — full polyhedral set plus expressions like `2d6+3`, for anyone without physical dice.
- **Monster inspector** — Baldur's Gate 3-style read-only stat view (HP, AC, resistances).
- **Combat tracker** — initiative, conditions, damage/healing, rests.
- **Maps** — global + local, with overlay markers for position and interactables.
- **Campaign blog + quest log + known-entity sidebar.**
- **Public/private knowledge** — the DM sees everything; players see only what they've discovered.

## Tech

Python + Flask + SQLite. Rules reference data comes from the D&D 5e **SRD**
(System Reference Document), used under **CC-BY-4.0**.

## Attribution

Rules reference content is derived from the **System Reference Document 5.1** by Wizards
of the Coast LLC, available under the
[Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/legalcode).
