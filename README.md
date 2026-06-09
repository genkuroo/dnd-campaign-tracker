# D&D Campaign Tracker

A web app for running a Dungeons & Dragons 5e campaign. The **Dungeon Master** manages
the whole world; **players** log in to track their own characters and look up how their
spells and abilities work — handy for a table that's new to D&D.

> Status: **Phases 0–8 complete** — live on Fly.io with multiple campaigns ("saves"). Creature engine + character sheets (PCs/NPCs/monsters, classes/subclasses/races/backgrounds, leveling, ASI/feats, inventory + magic items, weapon attacks), a dice roller, SRD spells + spellcasting, a combat tracker, accounts with DM/player roles and server-side fog-of-war, and now a Fly.io deploy setup (see below). See [CLAUDE.md](./CLAUDE.md) for the full architecture and phased plan.

## Running

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py    # http://127.0.0.1:5002
```

## Deploying (Fly.io)

The app is a stateful Flask + SQLite app with local file uploads, so it runs as
**one machine with one persistent volume** (`/data` holds `campaign.db` and the
uploaded avatars). Production is served by **gunicorn** (see `Dockerfile`);
`fly.toml` declares the machine + volume.

First-time setup (requires the [`flyctl`](https://fly.io/docs/flyctl/install/) CLI):

```bash
fly auth login                         # opens a browser
fly launch --no-deploy                 # reuses fly.toml; pick a unique app name + region
fly volumes create dnd_data --size 1   # 1 GB persistent volume, in the app's region
fly secrets set SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
fly deploy
```

`fly deploy` builds the image, ships it, and gunicorn's `--preload` runs the DB
migrations once before serving. The first visit lands on `/setup` to create the
DM account. Subsequent updates are just `fly deploy`.

**Bringing existing local data up** (optional — to keep the campaign you've been
running locally instead of starting fresh):

```bash
# Copy the local DB + avatar files onto the volume (machine must be running):
fly ssh console -C "mkdir -p /data/avatars"
fly ssh sftp shell                     # then: put campaign.db /data/campaign.db
                                       #       (and put each static/avatars/* into /data/avatars/)
fly apps restart                       # pick up the uploaded DB
```

**Backups:** the DB is a single file — `fly ssh console -C "cat /data/campaign.db" > backup.db`
(or use `fly ssh sftp get`). Worth doing before big changes.

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
