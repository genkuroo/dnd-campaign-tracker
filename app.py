"""D&D Campaign Tracker — Flask entry point.

Phase 1: the creature engine + working character sheets. The Character Sheet tab
lists, views, creates, and edits player characters (ability scores + modifiers,
HP, AC, resistances). DM-only for now; player logins arrive in Phase 7.
See CLAUDE.md for the full phased plan.
"""
import os
import re
from datetime import datetime, timezone

from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template, request, session,
    url_for,
)
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

import db
from db import init_db
from models.creature import (
    ABILITIES,
    ALIGNMENTS,
    DISPOSITIONS,
    KINDS,
    MAX_LEVEL,
    MONSTER_KINDS,
    UNARMORED_DEFENSE,
    CR_CHOICES,
    ability_modifier,
    adjust_coins,
    adjust_hp,
    alignment_label,
    cr_label,
    clear_control_for_user,
    create_creature,
    delete_creature,
    format_modifier,
    get_creature,
    level_from_xp,
    list_controlled_by,
    list_deceased,
    list_monsters,
    list_npcs,
    list_party,
    list_roster,
    party_rest,
    proficiency_bonus,
    set_controlled_by,
    set_deceased,
    set_inspiration,
    update_creature,
    xp_to_next,
)
from models.proficiency import (
    SKILL_OPTIONS,
    armor_proficiency_issue,
    expertise_skills,
    passive_perception,
    proficiency_summary,
    proficient_skills,
    save_table,
    set_skill_proficiencies,
    skill_table,
)
from models.dice import DiceError, parse_and_roll
from models.glossary import define
from models.roll_log import add_roll, clear_rolls, delete_roll, recent_rolls
from models.inventory import (
    SLOT_LABELS,
    SLOTS,
    ac_breakdown,
    add_item,
    adjust_quantity,
    attunement_summary,
    effective_abilities,
    effective_ac,
    equip_item,
    equipment_panel,
    equipped_ac_bonus,
    get_item,
    item_effects,
    list_items,
    remove_item,
    set_attuned,
    set_item_hidden,
    transfer_item,
    unequip_item,
)
from models.trades import (
    create_gold_offer,
    create_item_offer,
    get_offer,
    pending_incoming,
    pending_outgoing,
    set_status as set_trade_status,
)
from models.classes import (all_classes, get_class, hit_die_average,
                            class_features, class_features_remaining,
                            get_subclass, valid_subclass, subclass_level)
from models.races import (all_races, race_label, race_traits, race_speed,
                          race_size, valid_subrace)
from models.weapons import pack_weapon, weapon_attacks
from models.movement import effective_speed, speed_breakdown
from models.exhaustion import exhaustion_effects, set_exhaustion, MAX_EXHAUSTION
from models.backgrounds import all_backgrounds, get_background, valid_background
from models.items import all_item_defs, get_item_def
from models.loot import (
    add_loot,
    area_loot,
    clear_area_loot,
    create_area,
    current_area_id,
    delete_area,
    drop_to_loot,
    get_area,
    get_loot,
    give_loot,
    list_areas,
    remove_loot,
    set_current_area,
)
from models.actions import (
    CATEGORIES as ACTION_CATEGORIES,
    add_action,
    category_label as action_category_label,
    get_action,
    grant_class_actions,
    list_actions,
    remove_action,
    set_action_hidden,
)
from models.action_catalog import all_catalog_actions, get_catalog_action
from models.combat import (
    CONDITIONS,
    DAMAGE_TYPES,
    add_creature as combat_add_creature,
    add_log_entry,
    apply_hp,
    clear_combat_log,
    create_combat,
    delete_combat,
    delete_log_entry,
    get_log_entry,
    list_combat_log,
    get_combat,
    get_combatant,
    list_combatants,
    list_combats,
    next_turn,
    remove_combatant,
    roll_initiative_all,
    set_initiative,
    set_status as set_combat_status,
    set_temp_hp,
    toggle_condition,
    clear_death_saves,
    roll_death_save,
    set_death_save,
)
from models.encounters import (
    add_member,
    create_encounter,
    delete_encounter,
    encounter_difficulty,
    encounter_members,
    get_encounter,
    list_encounters,
    remove_member,
    rename_encounter,
    set_member_quantity,
)
from models.campaigns import (
    active_campaign,
    create_campaign,
    delete_campaign,
    duplicate_campaign,
    list_campaigns,
    rename_campaign,
    switch_campaign,
)
from models.spells import all_spells, get_spell, level_label, search_spells
from models.locations import (
    LOCATION_KINDS,
    children_of,
    create_location,
    creatures_at,
    delete_location,
    get_location,
    kind_label as location_kind_label,
    list_locations,
    set_location_visibility,
    update_location,
    visible_locations,
)
from models.maps import (
    create_map,
    delete_map,
    get_map,
    list_maps,
    maps_for_location,
    set_map_image,
    set_map_visibility,
    update_map,
    visible_maps,
)
from models.summons import (
    all_summons,
    is_summon as creature_is_summon,
    spawn as spawn_summon,
)
from models.map_markers import (
    create_marker,
    delete_marker,
    get_marker,
    list_markers,
    move_marker,
    set_marker_visibility,
    update_marker,
)
from models.factions import (
    create_faction,
    delete_faction,
    get_faction,
    list_factions,
    members_of,
    set_faction_visibility,
    update_faction,
    visible_factions,
)
from models.quests import (
    QUEST_STATUSES,
    add_objective,
    create_quest,
    delete_objective,
    delete_quest,
    get_objective,
    get_quest,
    list_quests,
    objective_progress,
    objectives_for,
    set_objective_status,
    set_objective_visibility,
    set_quest_status,
    set_quest_visibility,
    update_objective,
    update_quest,
    visible_quests,
)
from models.journal import (
    create_folder,
    create_note,
    delete_folder,
    delete_note,
    get_folder,
    get_note,
    list_folders,
    mentions_for_note,
    notes_in_folder,
    notes_mentioning,
    set_mentions,
    set_note_visibility,
    update_folder,
    update_note,
)
from models.user import (
    create_user,
    delete_user,
    get_signup_code,
    get_user,
    get_user_by_username,
    list_users,
    set_password,
    set_signup_code,
    set_user_character,
    set_user_color,
    user_count,
    verify_login,
)
from models.spellbook import (
    add_spell,
    creature_spell_slugs,
    creature_spells,
    effective_spells,
    remove_spell,
    set_prepared,
    set_spell_hidden,
)
from models.spellcasting import (
    caster_type,
    concentration_dc,
    drop_concentration,
    restore_all_slots,
    restore_pact_slots,
    restore_slot,
    set_concentration,
    slot_rows,
    spell_limits,
    spell_stats,
    spend_slot,
)
from models.resources import (
    resource_rows,
    spend_resource,
    restore_resource,
)
from models.resources import rest as resource_rest
from models.asi import asi_summary, adjust_asi
from models.feats import (
    all_catalog_feats,
    get_catalog_feat,
    list_feats,
    add_feat,
    get_feat,
    remove_feat,
)

# Quick-roll die buttons on the dice page.
DICE_BUTTONS = [4, 6, 8, 10, 12, 20, 100]

# A pause longer than this between rolls starts a new visual group in the log.
ROLL_GAP_SECONDS = 5 * 60

app = Flask(__name__)
# In production the secret is supplied via the SECRET_KEY env var (e.g.
# `fly secrets set SECRET_KEY=...`); the fallback is for local dev only.
app.secret_key = os.environ.get("SECRET_KEY", "dnd-campaign-tracker-local-only")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # cap uploads at 12 MB (map backgrounds run large)

# Uploaded character portraits live under static/avatars (served by Flask's
# static route). Kept out of git; the dir is created on demand.
AVATAR_DIR = os.path.join(app.static_folder, "avatars")
ALLOWED_AVATAR_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Uploaded map backgrounds live under static/maps (same pattern as avatars:
# symlinked onto the Fly volume in the Dockerfile so they persist across deploys).
MAP_DIR = os.path.join(app.static_folder, "maps")
ALLOWED_MAP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Apply any pending schema migrations at import time. This covers BOTH ways the
# app boots: `python app.py` locally and a WSGI server (gunicorn) in production,
# where the `__main__` block never runs. init_db() is idempotent. Under gunicorn
# we use --preload so this runs once in the master before workers fork, avoiding
# a migration race between workers on first deploy.
init_db()

# Exposed as a Jinja global (not a context processor) so imported macros — which
# don't receive template context — can still look up glossary terms.
app.jinja_env.globals["define"] = define

# The top-level tabs. `endpoint` is the Flask view name; `label` is what the
# navigation renders. Single source of truth so nav and routes can't drift.
TABS = [
    {"endpoint": "character", "label": "Character Sheet"},
    {"endpoint": "party", "label": "Party"},
    {"endpoint": "bestiary", "label": "Bestiary"},
    {"endpoint": "combat", "label": "Combat"},
    {"endpoint": "graveyard", "label": "Graveyard"},
    {"endpoint": "loot", "label": "Loot"},
    {"endpoint": "spells", "label": "Spells & Actions"},
    {"endpoint": "dice", "label": "Dice"},
    {"endpoint": "map", "label": "Map"},
    {"endpoint": "journal", "label": "Journal"},
    {"endpoint": "quests", "label": "Quests"},
]
# NPCs, Locations, and Factions are the "Known Entities" — they live in the left
# sidebar (inject_sidebar) rather than the top tab row.
# DM admin lives in the top-right cluster (not the main tab row) to keep the nav
# tidy: the campaign chip is the Campaigns entry; Users sits beside it.


@app.context_processor
def inject_nav():
    """Make the tab list available to every template (the base layout uses it)."""
    return {"tabs": TABS}


@app.context_processor
def inject_sidebar():
    """The left "Known Entities" sidebar: NPCs, locations, and factions, filtered
    to what the viewer may see (DM sees all). Empty before login (auth pages use a
    different layout and have no campaign/user context yet)."""
    empty = {"sidebar_npcs": [], "sidebar_locations": [], "sidebar_factions": []}
    if current_user() is None:
        return empty
    try:
        npcs = list_npcs() if is_dm() else [c for c in list_npcs() if can_view_creature(c)]
        return {
            "sidebar_npcs": npcs,
            "sidebar_locations": list_locations() if is_dm() else visible_locations(),
            "sidebar_factions": list_factions() if is_dm() else visible_factions(),
        }
    except Exception:  # never let a sidebar query break a page render
        return empty


@app.context_processor
def inject_badges():
    """Nav badges. `trade_offer_count` = pending trade offers waiting on the
    logged-in player's PC (so the Character tab can flag "you have offers"). 0 for
    the DM (not a PC) or anyone without a character. Never let it break a render."""
    try:
        pc_id = _my_pc_id()
        return {"trade_offer_count": len(pending_incoming(pc_id)) if pc_id else 0}
    except Exception:
        return {"trade_offer_count": 0}


def current_user():
    """The logged-in user row for this request, or None. Cached on flask.g.

    Keyed on **username** (not the row id) because ids aren't stable across
    campaign DBs — resolving by username lets the DM stay logged in when the
    active campaign is switched (the DM account is seeded into every campaign)."""
    if "user" not in g:
        username = session.get("username")
        g.user = get_user_by_username(username) if username else None
    return g.user


def is_dm():
    """Whether the current viewer is the Dungeon Master (admin).

    Single server-side chokepoint for every DM-only control/route, so they all
    lock down together (CLAUDE.md: never hide privileged actions with CSS/JS
    alone — the route must enforce it too)."""
    u = current_user()
    return u is not None and u["role"] == "dm"


# Endpoints reachable without being logged in (auth pages + static assets).
_PUBLIC_ENDPOINTS = {"login", "logout", "register", "setup", "static"}

# Endpoints only the DM may reach — the whole authoring/management surface.
# Enforced server-side here, not just hidden in the nav (CLAUDE.md). Per-creature
# edits (a player editing their own PC) are guarded separately by can_edit_creature.
# NOTE: the Party + Combat *views* (party, combat, combat_detail) are deliberately
# NOT here — players get a read-only view (controls hidden in-template) while every
# mutation route below stays DM-only.
_DM_ONLY_ENDPOINTS = {
    "character_new", "character_delete",
    "character_lay_to_rest", "character_restore",
    "monster_new", "monster_reveal", "monster_visibility",
    "encounter_detail", "encounter_new", "encounter_rename", "encounter_delete",
    "encounter_add_member", "encounter_member_quantity", "encounter_member_remove",
    "encounter_start_combat",
    "combat_new", "combat_end", "combat_reopen",
    "combat_delete", "combat_add", "combat_load_encounter",
    "combat_roll_initiative", "combat_next_turn",
    "combatant_initiative", "combatant_hp", "combatant_temp",
    "combatant_condition", "combatant_remove", "combatant_death_save",
    "combat_log_add", "combat_log_clear", "combat_log_entry_delete",
    "loot_area_new", "loot_area_switch", "loot_area_delete",
    "loot_area_clear", "loot_spawn", "loot_create", "loot_give", "loot_remove",
    "party_rest_route", "party_hp",
    "users", "users_set_code", "users_set_character", "users_reset_password",
    "users_set_color", "users_delete",
    "campaigns", "campaign_switch", "campaign_new", "campaign_rename",
    "campaign_duplicate", "campaign_delete",
    # World narrative layer (Phase 9a): list/detail views are shared (visibility-
    # gated in the route); only authoring mutations are DM-only.
    "location_new", "location_edit", "location_delete", "location_visibility",
    "faction_new", "faction_edit", "faction_delete", "faction_visibility",
    # Quests are DM-authored; list/detail views are shared (visibility-gated).
    "quest_new", "quest_edit", "quest_delete", "quest_status", "quest_visibility",
    "objective_new", "objective_status", "objective_edit", "objective_visibility",
    "objective_delete",
    # Maps (Phase 10): list/detail views are shared (visibility-gated); only
    # authoring mutations are DM-only.
    "map_new", "map_edit", "map_delete", "map_visibility",
    "marker_new", "marker_move", "marker_edit", "marker_visibility",
    "marker_delete",
}


@app.before_request
def _require_login():
    """Gate the whole app behind login (with first-run setup), then block the
    DM-only authoring surface for players — both server-side."""
    endpoint = request.endpoint or ""
    if endpoint in _PUBLIC_ENDPOINTS:
        return
    if user_count() == 0:
        return redirect(url_for("setup"))
    if current_user() is None:
        return redirect(url_for("login"))
    if endpoint in _DM_ONLY_ENDPOINTS and not is_dm():
        abort(403)


# --- Per-creature visibility (the fog-of-war spine) ------------------------

def _my_pc_id():
    """The creature id of the logged-in player's own character (None for the DM
    or an unassigned player)."""
    u = current_user()
    return u["creature_id"] if (u and u["role"] == "player") else None


def _controls_creature(creature):
    """True if the logged-in player controls this creature — a DM-granted
    companion or a 12b summon (`controlled_by` = their user id). Distinct from
    owning their single PC."""
    if creature is None:
        return False
    cb = creature["controlled_by"]
    return bool(cb) and cb == _my_user_id()


def can_view_creature(creature):
    """DM sees everyone. A player sees their own PC, any creature they **control**
    (companions/summons), can **read-only inspect** fellow party members, and the
    **encountered NPCs** the DM has revealed — any PC *or* NPC the DM hasn't hidden
    (`visibility='visible'`). Monsters stay DM-only (players meet them via the
    inspector / Phase 9 entity surfacing)."""
    if is_dm():
        return True
    if creature is None:
        return False
    if creature["id"] == _my_pc_id() or _controls_creature(creature):
        return True
    return creature["kind"] in ("pc", "npc") and creature["visibility"] == "visible"


def can_edit_creature(creature):
    """DM edits anyone; a player edits their own PC and any creature they control
    (companions/summons)."""
    if is_dm():
        return True
    if creature is None:
        return False
    return creature["id"] == _my_pc_id() or _controls_creature(creature)


def can_inspect_monster(creature):
    """Two-level monster fog of war. **Level 1** (this check): can the viewer open
    the monster's inspector at all — the DM always can; a player only if the DM has
    made it `visible`. **Level 2** (the `stats_revealed` flag, enforced in the
    inspector) governs whether the *stat block* is shown or masked. The full
    monster sheet stays DM-only; players only ever get the inspector."""
    if is_dm():
        return True
    return (creature is not None and creature["kind"] == "monster"
            and creature["visibility"] == "visible")


def can_view_entity(entity):
    """Fog of war for the non-creature world entities (locations, factions): the
    DM sees all, players see only the ones revealed (`visibility='visible'`)."""
    if is_dm():
        return True
    return entity is not None and entity["visibility"] == "visible"


# --- Journal permissions (Phase 9b) ----------------------------------------

def _my_user_id():
    u = current_user()
    return u["id"] if u else None


def can_view_note(note):
    """A note is visible to its owner, the DM (omniscient), and — when 'shared' —
    the whole party."""
    if note is None:
        return False
    if is_dm() or note["owner_id"] == _my_user_id():
        return True
    return note["visibility"] == "shared"


def can_edit_note(note):
    """Only the note's author (or the DM) may edit/share/delete it."""
    return note is not None and (is_dm() or note["owner_id"] == _my_user_id())


def can_edit_folder(folder):
    """Only a folder's owner (or the DM) may rename/delete it or add notes to it."""
    return folder is not None and (is_dm() or folder["owner_id"] == _my_user_id())


def can_view_folder(folder):
    """A folder shows to its owner, the DM, or anyone who can see a note inside it."""
    if folder is None:
        return False
    if can_edit_folder(folder):
        return True
    return any(can_view_note(n) for n in notes_in_folder(folder["id"]))


def _visible_notes(folder_id):
    """Notes in a folder the current viewer may see, newest-relevant order kept."""
    return [n for n in notes_in_folder(folder_id) if can_view_note(n)]


# --- Journal ↔ entity mentions (Phase 9b) ----------------------------------

def _mention_options():
    """The entities the current viewer may tag in a note (the form picker) —
    scoped to what they can see, so a player can't mention a hidden entity."""
    return {
        "creatures": visible_roster(),  # PCs + NPCs the viewer can see (DM: all)
        "locations": list_locations() if is_dm() else visible_locations(),
        "factions": list_factions() if is_dm() else visible_factions(),
    }


def _form_mentions(form):
    """Pull (entity_type, entity_id) pairs from a submitted note form, keeping only
    entities the author may actually see (defends against a crafted POST)."""
    opts = _mention_options()
    allowed = {
        "creature": {c["id"] for c in opts["creatures"]},
        "location": {l["id"] for l in opts["locations"]},
        "faction": {f["id"] for f in opts["factions"]},
    }
    out = []
    for etype in ("creature", "location", "faction"):
        for raw in form.getlist("mention_" + etype):
            if str(raw).strip().isdigit() and int(raw) in allowed[etype]:
                out.append((etype, int(raw)))
    return out


def _note_mention_links(note_id):
    """Resolve a note's mentions to link dicts, filtered to what the *viewer* may
    see (so a DM-shared note can't leak a hidden NPC to a player)."""
    links = []
    for m in mentions_for_note(note_id):
        etype, eid = m["entity_type"], m["entity_id"]
        if etype == "creature":
            c = get_creature(eid)
            if can_view_creature(c):
                icon = "👹" if c["kind"] == "monster" else ("🧑" if c["kind"] == "npc" else "🛡")
                links.append({"icon": icon, "name": c["name"],
                              "url": url_for("character_detail", creature_id=eid)})
        elif etype == "location":
            loc = get_location(eid)
            if can_view_entity(loc):
                links.append({"icon": "📍", "name": loc["name"],
                              "url": url_for("location_detail", location_id=eid)})
        elif etype == "faction":
            fac = get_faction(eid)
            if can_view_entity(fac):
                links.append({"icon": "🏛", "name": fac["name"],
                              "url": url_for("faction_detail", faction_id=eid)})
    return links


def _mentioned_in(entity_type, entity_id):
    """The journal notes that mention an entity, filtered to what the viewer may
    read — the 'Mentioned in' back-reference for an entity's page."""
    return [n for n in notes_mentioning(entity_type, entity_id) if can_view_note(n)]


def _resolve_marker(marker):
    """Turn a raw marker row into a display dict the map overlay can render, or
    None if the viewer shouldn't see it. Enforces the marker's own visibility AND
    the target entity's visibility (so a revealed marker pointing at a hidden NPC
    still hides). A dangling entity reference (deleted target) is skipped, except
    free-label pins which have no target. Mirrors `_note_mention_links`."""
    if not is_dm() and marker["visibility"] != "visible":
        return None
    base = {
        "id": marker["id"], "x": marker["x"], "y": marker["y"],
        "visibility": marker["visibility"], "entity_type": marker["entity_type"],
        "entity_id": marker["entity_id"], "label": marker["label"],
        "icon": marker["icon"], "creature": None, "url": None,
    }
    etype, eid = marker["entity_type"], marker["entity_id"]
    if etype == "":
        base["name"] = marker["label"] or "Marker"
        base["icon"] = marker["icon"] or "📌"
        return base
    if etype == "creature":
        c = get_creature(eid)
        if not can_view_creature(c):
            return None
        base.update(name=c["name"], creature=c,
                    url=url_for("character_detail", creature_id=eid))
        return base
    if etype == "location":
        loc = get_location(eid)
        if not can_view_entity(loc):
            return None
        base.update(name=loc["name"], icon=marker["icon"] or "📍",
                    url=url_for("location_detail", location_id=eid))
        return base
    if etype == "faction":
        fac = get_faction(eid)
        if not can_view_entity(fac):
            return None
        base.update(name=fac["name"], icon=marker["icon"] or "🏛",
                    url=url_for("faction_detail", faction_id=eid))
        return base
    if etype == "map":
        m = get_map(eid)
        if not can_view_entity(m):
            return None
        base.update(name=m["name"], icon=marker["icon"] or "🗺️",
                    url=url_for("map_detail", map_id=eid))
        return base
    return None


def _resolved_markers(map_id):
    """All viewable, resolved markers for a map."""
    out = []
    for marker in list_markers(map_id):
        r = _resolve_marker(marker)
        if r is not None:
            out.append(r)
    return out


def visible_roster():
    """The roster filtered to what the viewer may see."""
    roster = list_roster()
    return roster if is_dm() else [c for c in roster if can_view_creature(c)]


def editable_roster():
    """The roster filtered to what the viewer may edit (own PC, or all for DM)."""
    roster = list_roster()
    return roster if is_dm() else [c for c in roster if can_edit_creature(c)]


def _require_edit(creature_id):
    """Fetch a creature and 404/403 if the viewer can't see/edit it. Returns it."""
    creature = get_creature(creature_id)
    if not can_view_creature(creature):
        abort(404)
    if not can_edit_creature(creature):
        abort(403)
    return creature


def _require_edit_form_creature():
    """Guard a mutation keyed by a form `creature_id` (spellbook/actions). Returns
    the creature id, or aborts 403 if the viewer can't edit that creature."""
    cid = request.form.get("creature_id", type=int)
    creature = get_creature(cid) if cid else None
    if creature is None or not can_edit_creature(creature):
        abort(403)
    return cid


@app.context_processor
def inject_auth():
    """Expose the current user + is_dm() to every template (topbar, DM-only UI)."""
    return {"is_dm": is_dm(), "current_user": current_user()}


@app.context_processor
def inject_campaign():
    """Expose the active campaign (for the topbar switcher). None in single-DB/test
    mode, where there's no campaign registry."""
    if db.DB_PATH:
        return {"active_campaign": None}
    try:
        return {"active_campaign": active_campaign()}
    except Exception:
        return {"active_campaign": None}


@app.context_processor
def inject_mode():
    """Assist vs Track is a personal UI preference, stored per-browser in a cookie.

    'track' (default) = clicking a spell just shows what it does.
    'assist'          = clicking a spell rolls it for you.
    """
    return {"mode": request.cookies.get("mode", "track")}


@app.route("/mode", methods=["POST"])
def set_mode():
    chosen = request.form.get("mode")
    resp = redirect(_safe_next(request.form.get("next"), url_for("character")))
    if chosen in ("assist", "track"):
        resp.set_cookie("mode", chosen, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return resp


@app.template_filter("mod")
def _mod_filter(score):
    """Jinja filter: an ability score -> its formatted modifier (e.g. 14 -> '+2')."""
    return format_modifier(ability_modifier(score))


@app.template_filter("signed")
def _signed_filter(value):
    """Jinja filter: an already-computed modifier int -> signed string (3 -> '+3',
    0 -> '+0'). Used for save/skill totals and the dice expressions they post."""
    return format_modifier(int(value))


@app.template_filter("commalist")
def _commalist_filter(value):
    """Split a comma-separated field into a clean list for chip rendering."""
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@app.template_filter("alignment")
def _alignment_filter(code):
    """Jinja filter: alignment code -> full label (e.g. 'LG' -> 'Lawful Good')."""
    return alignment_label(code)


@app.template_filter("ordinal_level")
def _ordinal_level_filter(level):
    return level_label(level)


@app.template_filter("cr")
def _cr_filter(cr):
    """Jinja filter: a Challenge Rating value -> display label ('0.25' -> '1/4')."""
    return cr_label(cr)


@app.template_filter("action_category")
def _action_category_filter(value):
    """Jinja filter: action category code -> label (e.g. 'bonus' -> 'Bonus Action')."""
    return action_category_label(value)


@app.template_filter("item_effects")
def _item_effects_filter(item):
    """Jinja filter: an item row -> readable magic effects (['+2 AC', 'STR +2', …])."""
    return item_effects(item)


@app.template_filter("eff_ac")
def _eff_ac_filter(creature):
    """Jinja filter: a creature row -> its effective AC (armor / 10+DEX / natural,
    plus equipped item bonuses). Used on cards so they match the sheet."""
    return effective_ac(creature)


# Dice tokens inside prose, e.g. '8d6', '1d4 + 1'.
_DICE_TOKEN = re.compile(r"\d*d\d+(?:\s*[+-]\s*\d+)?", re.IGNORECASE)


@app.template_filter("dicetext")
def _dicetext_filter(text, mode="track", label=""):
    """Highlight dice in rules text. In assist mode each die is clickable (rolls
    via the base-layout JS); in track mode it's just styled, non-interactive.

    Surrounding prose is escaped; only our generated markup is trusted.
    """
    out, last = [], 0
    for m in _DICE_TOKEN.finditer(text or ""):
        out.append(str(escape(text[last:m.start()])))
        token = escape(m.group(0))
        if mode == "assist":
            out.append(
                f'<button type="button" class="rollable" '
                f'data-expr="{token}" data-label="{escape(label)}">{token}</button>'
            )
        else:
            out.append(f'<span class="die-text">{token}</span>')
        last = m.end()
    out.append(str(escape((text or "")[last:])))
    return Markup("".join(out))


def _parse_ts(value):
    """Parse a stored 'YYYY-MM-DD HH:MM:SS' UTC timestamp; None if unparseable."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


@app.template_filter("nicedate")
def _nicedate_filter(value):
    """A friendly local date, e.g. 'Jun 10, 2026'. Empty string if unparseable."""
    ts = _parse_ts(value)
    return ts.astimezone().strftime("%b %-d, %Y") if ts else ""


@app.template_filter("nicedatetime")
def _nicedatetime_filter(value):
    """A friendly local date + time, e.g. 'Jun 10, 2026 · 3:24 PM'."""
    ts = _parse_ts(value)
    if not ts:
        return ""
    local = ts.astimezone()
    return local.strftime("%b %-d, %Y · %-I:%M %p")


@app.template_filter("timeago")
def _timeago_filter(value):
    """A short relative label for a stored timestamp, e.g. '3 days ago'."""
    ts = _parse_ts(value)
    if not ts:
        return ""
    return _relative((datetime.now(timezone.utc) - ts).total_seconds())


# Vocab the character form needs; injected so the form template stays declarative.
def _form_vocab():
    return {"abilities": ABILITIES, "kinds": KINDS,
            "dispositions": DISPOSITIONS, "alignments": ALIGNMENTS,
            "unarmored_defenses": UNARMORED_DEFENSE, "classes": all_classes(),
            "races": all_races(), "backgrounds": all_backgrounds(),
            "skill_options": SKILL_OPTIONS, "cr_choices": CR_CHOICES,
            "location_options": list_locations(), "faction_options": list_factions()}


def _apply_class(creature_id, class_slug, starting_kit=False):
    """Set a creature's class. Always records the class + its Unarmored Defense;
    with `starting_kit` it also applies the BG3-style package — the recommended
    stat array, level-1 HP from the hit die (+CON), starting gold, and starting
    equipment (auto-equipped). Stats/HP it doesn't touch unless the kit is applied."""
    klass = get_class(class_slug)
    if klass is None:
        return
    fields = {"class_name": klass["slug"]}
    if klass.get("unarmored_defense"):
        fields["unarmored_defense"] = klass["unarmored_defense"]
    if starting_kit:
        stats = klass.get("recommended_stats", {})
        fields.update(stats)
        hp = max(1, klass["hit_die"] + ability_modifier(stats.get("constitution", 10)))
        fields.update({"max_hp": hp, "current_hp": hp, "gold": klass.get("starting_gold", 0)})
    update_creature(creature_id, fields)
    _sync_class_actions(creature_id)  # auto-grant the class's usable abilities
    if starting_kit:
        for slug in klass.get("starting_equipment", []):
            item = get_item_def(slug)
            if not item:
                continue
            new_id = add_item(
                creature_id, item["name"], 1, item["description"],
                slot=item["slot"], hands=item["hands"],
                ac_bonus=item.get("ac_bonus", 0), grants_spells=item.get("grants_spells", ""),
                stat_bonuses=item.get("stat_bonuses", ""), armor_base=item.get("armor_base", 0),
                armor_type=item.get("armor_type", ""), weapon=item.get("weapon", ""))
            if item.get("slot"):
                equip_item(new_id)  # auto-equip starting gear


def _sync_class_actions(creature_id):
    """Re-sync a creature's class-granted actions to its *current* class + level
    (reads the creature fresh). Called after anything that can change either — class
    apply, edit, or level-up. Clears class actions for the classless; never touches
    hand-added ones."""
    c = get_creature(creature_id)
    if c:
        grant_class_actions(creature_id, c["class_name"], c["level"], c["subclass"])


@app.route("/")
def index():
    return redirect(url_for("character"))


# --- Campaigns ("saves") — DM only ----------------------------------------
# Multiple self-contained campaigns; the DM toggles which one is active (global
# switch — the whole table moves). See models/campaigns.py + db.py.

@app.route("/campaigns")
def campaigns():
    _require_dm()
    return render_template(
        "campaigns.html", active="campaigns", title="Campaigns",
        campaigns=list_campaigns(),
    )


@app.route("/campaigns/switch", methods=["POST"])
def campaign_switch():
    _require_dm()
    cid = request.form.get("campaign_id", type=int)
    if cid and switch_campaign(cid):
        flash("Switched campaign.")
        return redirect(url_for("character"))
    return redirect(url_for("campaigns"))


@app.route("/campaigns/new", methods=["POST"])
def campaign_new():
    _require_dm()
    # Seed the new campaign with the DM's own account so it's playable immediately.
    cid = create_campaign(request.form.get("name", ""), dm=current_user())
    if request.form.get("switch"):
        switch_campaign(cid)
        flash("Created and switched to the new campaign.")
        return redirect(url_for("character"))
    flash("Campaign created.")
    return redirect(url_for("campaigns"))


@app.route("/campaigns/<int:campaign_id>/rename", methods=["POST"])
def campaign_rename(campaign_id):
    _require_dm()
    rename_campaign(campaign_id, request.form.get("name", ""))
    flash("Campaign renamed.")
    return redirect(url_for("campaigns"))


@app.route("/campaigns/<int:campaign_id>/duplicate", methods=["POST"])
def campaign_duplicate(campaign_id):
    _require_dm()
    if duplicate_campaign(campaign_id, request.form.get("name", "")):
        flash("Snapshot saved as a new campaign.")
    else:
        flash("Couldn't duplicate that campaign.")
    return redirect(url_for("campaigns"))


@app.route("/campaigns/<int:campaign_id>/delete", methods=["POST"])
def campaign_delete(campaign_id):
    _require_dm()
    _ok, msg = delete_campaign(campaign_id)
    flash(msg)
    return redirect(url_for("campaigns"))


# --- Auth (Phase 7) -------------------------------------------------------

def _safe_next_or(default):
    return _safe_next(request.args.get("next") or request.form.get("next"), default)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """First-run bootstrap: create the DM (admin) account. Disabled once any user
    exists, so a second DM can't be minted through it."""
    if user_count() > 0:
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        new_id = create_user(username, password, role="dm")
        if new_id:
            session.clear()
            session["username"] = username.strip()
            flash("DM account created — welcome, Dungeon Master.")
            return redirect(url_for("character"))
        flash("Couldn't create the account. Pick a username and password.")
    return render_template("setup.html", title="First-time setup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if user_count() == 0:  # nothing to log into yet — go create the DM
        return redirect(url_for("setup"))
    if current_user():
        return redirect(url_for("character"))
    if request.method == "POST":
        user = verify_login(request.form.get("username", ""), request.form.get("password", ""))
        if user:
            session.clear()
            session["username"] = user["username"]
            return redirect(_safe_next_or(url_for("character")))
        flash("Wrong username or password.")
    return render_template(
        "login.html", title="Log in", signup_enabled=bool(get_signup_code()),
    )


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Code-gated player self-registration. Players join with the shared code the
    DM sets; the DM then assigns each to their character on the Users page."""
    if current_user():
        return redirect(url_for("character"))
    code = get_signup_code()
    if not code:
        flash("Registration isn't open yet — ask your DM for a signup code.")
        return redirect(url_for("login"))
    if request.method == "POST":
        if (request.form.get("code") or "").strip() != code:
            flash("That signup code isn't right.")
        else:
            uname = request.form.get("username", "")
            new_id = create_user(uname, request.form.get("password", ""), role="player")
            if new_id:
                session.clear()
                session["username"] = uname.strip()
                flash("Account created. Your DM will link you to your character.")
                return redirect(url_for("character"))
            flash("That username is taken or invalid.")
    return render_template("register.html", title="Create account")


# --- Users admin (DM only) ------------------------------------------------

def _require_dm():
    if not is_dm():
        abort(403)


@app.route("/users")
def users():
    _require_dm()
    return render_template(
        "users.html",
        active="users",
        title="Users",
        users=list_users(),
        party=list_party(),
        signup_code=get_signup_code(),
    )


@app.route("/users/code", methods=["POST"])
def users_set_code():
    _require_dm()
    set_signup_code(request.form.get("code", ""))
    flash("Signup code updated.")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/character", methods=["POST"])
def users_set_character(user_id):
    _require_dm()
    if get_user(user_id):
        cid = request.form.get("creature_id", type=int)
        set_user_character(user_id, cid)
        flash("Character assigned." if cid else "Character unassigned.")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/color", methods=["POST"])
def users_set_color(user_id):
    _require_dm()
    if get_user(user_id):
        set_user_color(user_id, request.form.get("color", ""))
        flash("Roll colour updated.")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/password", methods=["POST"])
def users_reset_password(user_id):
    _require_dm()
    if get_user(user_id):
        set_password(user_id, request.form.get("password", ""))
        flash("Password reset.")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
def users_delete(user_id):
    _require_dm()
    target = get_user(user_id)
    # Don't let the DM delete themselves out of the only admin seat.
    if target and not (target["role"] == "dm" and target["id"] == current_user()["id"]):
        clear_control_for_user(user_id)  # release any companions they controlled
        delete_user(user_id)
        flash("User removed.")
    return redirect(url_for("users"))


# --- Character Sheet tab --------------------------------------------------

@app.route("/character")
def character():
    """Character Sheet tab. A player jumps straight to their own PC (they only
    have one); the DM gets the party roster (PCs). NPCs live on their own tab."""
    if not is_dm():
        pc_id = _my_pc_id()
        if pc_id and get_creature(pc_id):
            return redirect(url_for("character_detail", creature_id=pc_id))
        # No character yet — show the create-your-character prompt.
        return render_template(
            "character.html", active="character", title="Character Sheet", roster=[],
        )
    return render_template(
        "character.html",
        active="character",
        title="Characters",
        roster=list_party(),
    )


@app.route("/npcs")
def npcs():
    """The NPC cast. The DM manages all of them; a player sees the ones they've
    encountered (NPCs the DM has revealed, i.e. not hidden)."""
    roster = list_npcs()
    if not is_dm():
        roster = [c for c in roster if can_view_creature(c)]
    return render_template(
        "npcs.html", active="npcs", title="NPCs", roster=roster,
    )


@app.route("/character/new", methods=["GET", "POST"])
def character_new():
    if request.method == "POST":
        new_id = create_creature(_form_to_data(request.form))
        _apply_avatar(new_id)
        set_skill_proficiencies(new_id, request.form.getlist("skills"),
                                request.form.getlist("skills_expertise"))
        if request.form.get("class_name"):
            _apply_class(new_id, request.form.get("class_name"),
                         starting_kit=bool(request.form.get("apply_kit")))
        flash("Character created.")
        return redirect(url_for("character_detail", creature_id=new_id))
    default_kind = request.args.get("kind") if request.args.get("kind") in {"pc", "npc"} else "pc"
    return render_template(
        "character_form.html",
        active="npcs" if default_kind == "npc" else "character",
        title="New NPC" if default_kind == "npc" else "New Character",
        creature=None,
        default_kind=default_kind,
        cancel_url=url_for("npcs") if default_kind == "npc" else url_for("character"),
        **_form_vocab(),
    )


@app.route("/character/create-mine", methods=["GET", "POST"])
def character_create_mine():
    """Self-service character creation for a player who has none yet — creates a
    PC and assigns it to them. (The DM uses the normal new-character flow.)"""
    u = current_user()
    if u is None:
        abort(403)
    if is_dm():
        return redirect(url_for("character_new"))
    if u["creature_id"] and get_creature(u["creature_id"]):
        return redirect(url_for("character_detail", creature_id=u["creature_id"]))
    if request.method == "POST":
        data = _form_to_data(request.form)
        data["kind"] = "pc"            # players make their own PC
        data["visibility"] = "visible"  # a player can't hide themselves from the DM
        if not (data.get("player_name") or "").strip():
            data["player_name"] = u["username"]
        new_id = create_creature(data)
        _apply_avatar(new_id)
        # Skills stay DM-controlled — the DM assigns proficiencies later (the picker
        # is hidden from players), so a self-created PC starts with none.
        if request.form.get("class_name"):  # players get the full starting kit
            _apply_class(new_id, request.form.get("class_name"), starting_kit=True)
        set_user_character(u["id"], new_id)  # auto-assign to the creator
        flash("Your character is ready — welcome to the party!")
        return redirect(url_for("character_detail", creature_id=new_id))
    return render_template(
        "character_form.html",
        active="character",
        title="Create your character",
        creature=None,
        cancel_url=url_for("character"),
        **{**_form_vocab(), "kinds": [("pc", "Player Character")]},
    )


@app.route("/character/<int:creature_id>")
def character_detail(creature_id):
    creature = get_creature(creature_id)
    if not can_view_creature(creature):  # hidden/forbidden creatures 404 for players
        abort(404)
    known = effective_spells(creature_id)            # known + equipped-item grants
    known_slugs = {s["slug"] for s in known}
    next_level = xp_to_next(creature["xp"])
    eff_ab = effective_abilities(creature)           # base + equipped-item bonuses
    klass = get_class(creature["class_name"]) if creature["class_name"] else None
    # BG3-style fixed level-up HP: average of the class hit die + CON modifier.
    level_hp = (max(1, hit_die_average(klass["hit_die"])
                    + ability_modifier(eff_ab["constitution"]["score"]))
                if klass else 0)
    return render_template(
        "character_detail.html",
        active={"monster": "bestiary", "npc": "npcs"}.get(creature["kind"], "character"),
        title=creature["name"],
        can_edit=can_edit_creature(creature),
        abilities=ABILITIES,
        klass=klass,
        subclass=get_subclass(creature["class_name"], creature["subclass"]),
        race_label=race_label(creature),
        race_traits=race_traits(creature),
        race_speed=race_speed(creature),
        race_size=race_size(creature),
        background=get_background(creature["background"]),
        speed=effective_speed(creature),
        speed_breakdown=speed_breakdown(creature),
        exhaustion=creature["exhaustion"],
        exhaustion_effects=exhaustion_effects(creature["exhaustion"]),
        max_exhaustion=MAX_EXHAUSTION,
        weapon_attacks=weapon_attacks(creature, eff_ab),
        class_features=class_features(creature["class_name"], creature["level"], creature["subclass"]),
        class_features_next=class_features_remaining(
            creature["class_name"], creature["level"], creature["subclass"])[:4],
        level_hp=level_hp,
        eff_abilities=eff_ab,
        saves=save_table(creature, eff_ab),
        skills=skill_table(creature, eff_ab),
        passive_perception=passive_perception(creature, eff_ab),
        proficiencies=proficiency_summary(creature),
        armor_issue=armor_proficiency_issue(creature),
        prof_bonus=proficiency_bonus(creature["level"]),
        eff_ac=effective_ac(creature),
        ac_bonus=equipped_ac_bonus(creature_id),
        ac_breakdown=ac_breakdown(creature),
        dispositions=DISPOSITIONS,
        # Fog of war: only surface the home/faction link if the viewer may see it.
        home=(lambda l: l if can_view_entity(l) else None)(get_location(creature["location_id"])),
        faction=(lambda f: f if can_view_entity(f) else None)(get_faction(creature["faction_id"])),
        mentioned_in=_mentioned_in("creature", creature_id),
        creature=creature,
        spells=known,
        addable_spells=[s for s in all_spells() if s["slug"] not in known_slugs],
        resource_rows=resource_rows(creature, eff_ab),
        asi=asi_summary(creature),
        feats=list_feats(creature_id),
        feat_book=all_catalog_feats(),
        **_spellcasting_ctx(creature),
        next_level=next_level,                         # (level, xp_to_go) or None
        xp_level=level_from_xp(creature["xp"]),         # level the XP implies
        items=list_items(creature_id),
        slot_labels=SLOT_LABELS,
        slots=SLOTS,
        spell_options=all_spells(),
        panel=equipment_panel(creature_id),
        attunement=attunement_summary(creature_id),
        actions=list_actions(creature_id),
        action_categories=ACTION_CATEGORIES,
        action_book=all_catalog_actions(),
        # Phase 12a: companions the *viewer* controls (for the panel) + who
        # controls THIS creature (a badge for the DM / the controller).
        companions=[c for c in list_controlled_by(_my_user_id())
                    if c["id"] != creature_id],
        controller=get_user(creature["controlled_by"]) if creature["controlled_by"] else None,
        # Phase 12b: the summon picker shows on the player's OWN PC sheet.
        can_summon=(creature_id == _my_pc_id()),
        summon_catalog=all_summons(),
        # PC-to-PC trading: pending offers in/out + the party members this PC can
        # trade with (other living PCs). Only meaningful on a PC's own sheet.
        trades_in=pending_incoming(creature_id) if creature["kind"] == "pc" else [],
        trades_out=pending_outgoing(creature_id) if creature["kind"] == "pc" else [],
        trade_partners=[p for p in list_party() if p["id"] != creature_id],
    )


@app.route("/character/<int:creature_id>/edit", methods=["GET", "POST"])
def character_edit(creature_id):
    creature = _require_edit(creature_id)
    if request.method == "POST":
        update_creature(creature_id, _form_to_data(request.form))
        _apply_avatar(creature_id)
        _sync_class_actions(creature_id)  # class/level may have changed → resync
        if is_dm():  # skill profs + companion control are DM-only
            set_skill_proficiencies(creature_id, request.form.getlist("skills"),
                                    request.form.getlist("skills_expertise"))
            if "controlled_by" in request.form:
                set_controlled_by(creature_id, request.form.get("controlled_by") or 0)
        flash("Character updated.")
        return redirect(url_for("character_detail", creature_id=creature_id))
    vocab = _form_vocab()
    if creature["kind"] == "monster":
        vocab["kinds"] = MONSTER_KINDS  # keep the Type field as Monster, not pc/npc
    return render_template(
        "character_form.html",
        active={"monster": "bestiary", "npc": "npcs"}.get(creature["kind"], "character"),
        title=f"Edit {creature['name']}",
        creature=creature,
        proficient_skills=proficient_skills(creature_id),
        expertise_skills=expertise_skills(creature_id),
        # Players who can be granted control of this creature (DM-only field).
        players=[u for u in list_users() if u["role"] == "player"],
        cancel_url=url_for("character_detail", creature_id=creature_id),
        **vocab,
    )


@app.route("/character/<int:creature_id>/avatar", methods=["POST"])
def character_avatar(creature_id):
    """Update just the portrait from the sheet — no full edit needed, so a PC can
    change their own picture anytime. Returns the gear fragment (the figure lives
    there) for in-place AJAX, else redirects back to the sheet."""
    _require_edit(creature_id)
    _apply_avatar(creature_id)
    return _gear_response(creature_id, url_for("character_detail", creature_id=creature_id))


# --- Summons (Phase 12b) ---------------------------------------------------

def _my_sheet_redirect():
    """Back to the viewer's own PC sheet (where summons live), else the tab."""
    pc_id = _my_pc_id()
    return redirect(url_for("character_detail", creature_id=pc_id) if pc_id
                    else url_for("character"))


@app.route("/summon", methods=["POST"])
def summon_new():
    """A player spawns a catalog summon under their own control. (DM-less action —
    summoning is a player feature; the DM grants companions via the edit form.)"""
    uid = _my_user_id()
    if not uid:
        abort(403)
    new_id = spawn_summon(request.form.get("slug"), uid)
    flash("Summoned!" if new_id else "Unknown summon.")
    return _my_sheet_redirect()


@app.route("/summon/<int:creature_id>/dismiss", methods=["POST"])
def summon_dismiss(creature_id):
    """Dismiss (delete) a summon — only its controller or the DM, and only an
    actual summon (a DM-granted companion isn't player-dismissable)."""
    creature = get_creature(creature_id)
    if creature is None or not creature["is_summon"]:
        abort(404)
    if not (is_dm() or _controls_creature(creature)):
        abort(403)
    delete_creature(creature_id)
    flash("Summon dismissed.")
    return _my_sheet_redirect()


@app.route("/character/<int:creature_id>/disposition", methods=["POST"])
def character_set_disposition(creature_id):
    """Quick live toggle of a creature's disposition (for NPCs/monsters)."""
    _require_edit(creature_id)
    value = request.form.get("disposition")
    if value in DISPOSITIONS:
        update_creature(creature_id, {"disposition": value})
        flash(f"Disposition set to {value}.")
    return redirect(url_for("character_detail", creature_id=creature_id))


@app.route("/character/<int:creature_id>/levelup", methods=["POST"])
def character_levelup(creature_id):
    """Bump a creature one level (milestone- or XP-driven, DM's call) and add the
    HP gained. Level stays manual; this just applies the step. Capped at the max.
    """
    creature = _require_edit(creature_id)
    if creature["level"] < MAX_LEVEL:
        hp_gain = max(0, request.form.get("hp_gain", 0, type=int) or 0)
        new_level = creature["level"] + 1
        update_creature(creature_id, {
            "level": new_level,
            "max_hp": creature["max_hp"] + hp_gain,
            "current_hp": creature["current_hp"] + hp_gain,
        })
        _sync_class_actions(creature_id)  # unlock any features gained at the new level
        flash(f"Leveled up to {new_level}." + (f" +{hp_gain} HP." if hp_gain else ""))
    return redirect(url_for("character_detail", creature_id=creature_id))


@app.route("/character/<int:creature_id>/coins", methods=["POST"])
def character_coins(creature_id):
    """Directly add or subtract coins from a creature's purse (owner or DM)."""
    _require_edit(creature_id)
    sign = -1 if request.form.get("mode") == "subtract" else 1
    adjust_coins(
        creature_id,
        sign * (request.form.get("gold", 0, type=int) or 0),
        sign * (request.form.get("silver", 0, type=int) or 0),
        sign * (request.form.get("copper", 0, type=int) or 0),
    )
    flash("Purse updated.")
    return redirect(url_for("character_detail", creature_id=creature_id))


# --- PC-to-PC trading -----------------------------------------------------
# A directed offer (item or gold) one PC sends another; nothing moves until the
# recipient accepts. Offering/cancelling is gated to the *giver's* owner (or DM);
# accept/decline to the *recipient's* owner (or DM). These are player actions, so
# they are NOT in _DM_ONLY_ENDPOINTS — each route enforces ownership itself.

def _valid_trade_partner(from_creature, to_id):
    """The recipient must be a different, living PC. Returns the recipient row or
    None."""
    to_creature = get_creature(to_id)
    if (to_creature is None or to_creature["id"] == from_creature["id"]
            or to_creature["kind"] != "pc" or to_creature["deceased"]):
        return None
    return to_creature


@app.route("/character/<int:creature_id>/trade/offer", methods=["POST"])
def trade_offer(creature_id):
    """Offer an item or gold from this PC to a party member (the giver's owner/DM).
    `kind` = 'item' (with `item_id`) or 'gold' (with gold/silver/copper)."""
    giver = _require_edit(creature_id)
    to_id = request.form.get("to_creature_id", type=int)
    recipient = _valid_trade_partner(giver, to_id) if to_id else None
    if recipient is None:
        flash("Pick a valid party member to trade with.")
        return _trade_response(creature_id)
    kind = request.form.get("kind")
    if kind == "item":
        item = get_item(request.form.get("item_id", type=int))
        if item is None or item["creature_id"] != creature_id:
            flash("That item isn't in your inventory.")
        else:
            create_item_offer(creature_id, recipient["id"], item["id"])
            flash(f"Offered {item['name']} to {recipient['name']}.")
    elif kind == "gold":
        g = max(0, request.form.get("gold", 0, type=int) or 0)
        s = max(0, request.form.get("silver", 0, type=int) or 0)
        c = max(0, request.form.get("copper", 0, type=int) or 0)
        if g + s + c == 0:
            flash("Enter an amount to offer.")
        elif g > giver["gold"] or s > giver["silver"] or c > giver["copper"]:
            flash("You don't have that many coins.")
        else:
            create_gold_offer(creature_id, recipient["id"], g, s, c)
            flash(f"Offered coins to {recipient['name']}.")
    return _trade_response(creature_id)


@app.route("/trade/<int:offer_id>/accept", methods=["POST"])
def trade_accept(offer_id):
    """The recipient accepts a pending offer — the item/gold moves now. Re-validates
    that the giver can still honour it (no escrow), failing cleanly otherwise."""
    offer = get_offer(offer_id)
    if offer is None or offer["status"] != "pending":
        abort(404)
    recipient = _require_edit(offer["to_creature_id"])  # only the recipient/DM
    giver = get_creature(offer["from_creature_id"])
    if giver is None:
        set_trade_status(offer_id, "declined")
        flash("The other character is no longer available.")
        return _trade_response(recipient["id"])
    if offer["kind"] == "item":
        item = get_item(offer["item_id"])
        if item is None or item["creature_id"] != giver["id"]:
            set_trade_status(offer_id, "declined")
            flash(f"{giver['name']} no longer has that item — offer voided.")
        else:
            transfer_item(item["id"], recipient["id"])
            set_trade_status(offer_id, "accepted")
            flash(f"Received {item['name']} from {giver['name']}.")
    else:  # gold
        g, s, c = offer["gold"], offer["silver"], offer["copper"]
        if g > giver["gold"] or s > giver["silver"] or c > giver["copper"]:
            set_trade_status(offer_id, "declined")
            flash(f"{giver['name']} no longer has the coins — offer voided.")
        else:
            adjust_coins(giver["id"], -g, -s, -c)
            adjust_coins(recipient["id"], g, s, c)
            set_trade_status(offer_id, "accepted")
            flash(f"Received coins from {giver['name']}.")
    return _trade_response(recipient["id"])


@app.route("/trade/<int:offer_id>/decline", methods=["POST"])
def trade_decline(offer_id):
    """The recipient declines a pending offer."""
    offer = get_offer(offer_id)
    if offer is None or offer["status"] != "pending":
        abort(404)
    recipient = _require_edit(offer["to_creature_id"])
    set_trade_status(offer_id, "declined")
    flash("Offer declined.")
    return _trade_response(recipient["id"])


@app.route("/trade/<int:offer_id>/cancel", methods=["POST"])
def trade_cancel(offer_id):
    """The giver cancels their own pending offer."""
    offer = get_offer(offer_id)
    if offer is None or offer["status"] != "pending":
        abort(404)
    giver = _require_edit(offer["from_creature_id"])
    set_trade_status(offer_id, "cancelled")
    flash("Offer cancelled.")
    return _trade_response(giver["id"])


def _trade_response(creature_id):
    """Re-render just the #trades panel for fetch requests (offer/cancel/decline
    only touch the offers list; an accept also moves an item/gold, which the client
    refreshes via #gear + the purse). Non-JS falls back to a full redirect."""
    if _is_fetch():
        return _trades_fragment(creature_id)
    return redirect(url_for("character_detail", creature_id=creature_id))


def _trades_fragment(creature_id):
    """Render the trade panel for a creature (the #trades AJAX fragment)."""
    creature = get_creature(creature_id)
    return render_template(
        "_trades.html",
        creature=creature,
        items=list_items(creature_id),
        trades_in=pending_incoming(creature_id),
        trades_out=pending_outgoing(creature_id),
        trade_partners=[p for p in list_party() if p["id"] != creature_id],
    )


@app.route("/character/<int:creature_id>/exhaustion", methods=["POST"])
def character_exhaustion(creature_id):
    """Adjust a creature's exhaustion level by ±1 (a loose tracker — no mechanics are
    auto-applied). Owner or DM. AJAX re-renders just the #exhaustion fragment (it's
    display-only, so nothing else on the sheet depends on it)."""
    creature = _require_edit(creature_id)
    delta = 1 if request.form.get("delta", type=int) and request.form.get("delta", type=int) > 0 else -1
    set_exhaustion(creature_id, creature["exhaustion"] + delta)
    if _is_fetch():
        return _exhaustion_fragment(creature_id)
    return redirect(_safe_next(request.form.get("next"),
                               url_for("character_detail", creature_id=creature_id)))


def _exhaustion_fragment(creature_id):
    """Render the exhaustion tracker for a creature (the #exhaustion AJAX fragment)."""
    creature = get_creature(creature_id)
    return render_template(
        "_exhaustion.html",
        creature=creature,
        can_edit=can_edit_creature(creature),
        exhaustion=creature["exhaustion"],
        exhaustion_effects=exhaustion_effects(creature["exhaustion"]),
        max_exhaustion=MAX_EXHAUSTION,
    )


@app.route("/character/<int:creature_id>/inspiration", methods=["POST"])
def character_inspiration(creature_id):
    """Toggle Heroic Inspiration (the DM grants it, the owner spends it). Owner or DM."""
    creature = _require_edit(creature_id)
    set_inspiration(creature_id, not creature["inspiration"])
    return redirect(_safe_next(request.form.get("next"),
                               url_for("character_detail", creature_id=creature_id)))


@app.route("/character/<int:creature_id>/delete", methods=["POST"])
def character_delete(creature_id):
    delete_creature(creature_id)
    flash("Character deleted.")
    return redirect(url_for("character"))


# --- Graveyard tab --------------------------------------------------------
# Fallen PCs, slain unique bosses, and dead notable NPCs. A deceased creature is
# still a creature (the sheet lives on as a memorial); `deceased=1` just retires
# it from every active list. The view is shared (visibility-filtered like the
# other lists); marking dead / restoring is DM-only.

@app.route("/graveyard")
def graveyard():
    dead = list_deceased()
    if not is_dm():
        dead = [c for c in dead if can_view_creature(c)]
    # Group for display: fallen heroes (PCs), then NPCs, then monsters/bosses.
    by_kind = [
        ("Fallen heroes", "pc"),
        ("Departed NPCs", "npc"),
        ("Vanquished foes", "monster"),
    ]
    groups = [
        {"label": label, "members": [c for c in dead if c["kind"] == kind]}
        for label, kind in by_kind
    ]
    return render_template(
        "graveyard.html",
        active="graveyard",
        title="Graveyard",
        grave_groups=[g for g in groups if g["members"]],
        total=len(dead),
    )


@app.route("/character/<int:creature_id>/lay-to-rest", methods=["POST"])
def character_lay_to_rest(creature_id):
    """Retire a creature to the graveyard with an optional epitaph."""
    creature = get_creature(creature_id)
    if creature is None:
        abort(404)
    set_deceased(creature_id, True, request.form.get("epitaph", ""))
    flash(f"{creature['name']} has been laid to rest.")
    return redirect(_safe_next(request.form.get("next"), url_for("graveyard")))


@app.route("/character/<int:creature_id>/restore", methods=["POST"])
def character_restore(creature_id):
    """Bring a creature back from the graveyard into active play."""
    creature = get_creature(creature_id)
    if creature is None:
        abort(404)
    set_deceased(creature_id, False)
    flash(f"{creature['name']} returns to the campaign.")
    return redirect(_safe_next(request.form.get("next"),
                               url_for("character_detail", creature_id=creature_id)))


# --- Bestiary tab (monsters) ----------------------------------------------
# Monsters reuse the creature engine wholesale — the editable sheet is the same
# character_detail view, and create/edit/delete go through the shared character
# routes. The Bestiary only adds a monster-scoped list, a create entry point, and
# the BG3-style read-only inspector with its DM-gated stat reveal.

@app.route("/bestiary")
def bestiary():
    # Level-1 fog of war: players see only monsters the DM has made visible; the
    # DM sees the whole database. Encounters are DM combat-prep (hidden from players).
    monsters = list_monsters()
    if not is_dm():
        monsters = [m for m in monsters if m["visibility"] == "visible"]
    return render_template(
        "bestiary.html",
        active="bestiary",
        title="Bestiary",
        monsters=monsters,
        encounters=list_encounters() if is_dm() else [],
    )


@app.route("/bestiary/new", methods=["GET", "POST"])
def monster_new():
    if request.method == "POST":
        data = _form_to_data(request.form)
        data["kind"] = "monster"  # the Bestiary only makes monsters
        new_id = create_creature(data)
        _apply_avatar(new_id)
        set_skill_proficiencies(new_id, request.form.getlist("skills"),
                                request.form.getlist("skills_expertise"))
        flash("Monster created.")
        return redirect(url_for("character_detail", creature_id=new_id))
    return render_template(
        "character_form.html",
        active="bestiary",
        title="New Monster",
        creature=None,
        cancel_url=url_for("bestiary"),
        **{**_form_vocab(), "kinds": MONSTER_KINDS},
    )


@app.route("/bestiary/<int:creature_id>/inspect")
def monster_inspect(creature_id):
    """The BG3-style read-only inspector — a trimmed creature view that previews
    what a player sees. Stat-block numbers are masked until the DM reveals them.
    """
    creature = get_creature(creature_id)
    if not can_inspect_monster(creature):  # hidden monsters 404 for players (level 1)
        abort(404)
    return render_template(
        "inspector.html",
        active="bestiary",
        title=f"Inspect {creature['name']}",
        creature=creature,
        abilities=ABILITIES,
        revealed=bool(creature["stats_revealed"]),  # level 2: stat-block mask
        spells=[s for s in creature_spells(creature_id) if s["prepared"]],
        actions=list_actions(creature_id),
    )


@app.route("/bestiary/<int:creature_id>/reveal", methods=["POST"])
def monster_reveal(creature_id):
    """Level 2: toggle whether the stat block is revealed to players (the inspector
    masks the numbers until then). DM-only, live from the inspector."""
    creature = get_creature(creature_id)
    if creature and creature["kind"] == "monster":
        update_creature(creature_id, {"stats_revealed": 0 if creature["stats_revealed"] else 1})
    return redirect(url_for("monster_inspect", creature_id=creature_id))


@app.route("/bestiary/<int:creature_id>/visibility", methods=["POST"])
def monster_visibility(creature_id):
    """Level 1: toggle whether players can see this monster in the Bestiary at all.
    DM-only. `next` returns to the bestiary list or the inspector."""
    creature = get_creature(creature_id)
    if creature and creature["kind"] == "monster":
        new = "hidden" if creature["visibility"] == "visible" else "visible"
        update_creature(creature_id, {"visibility": new})
        flash("Monster shown to players." if new == "visible" else "Monster hidden from players.")
    return redirect(_safe_next(request.form.get("next"),
                               url_for("monster_inspect", creature_id=creature_id)))


# --- Encounters (saved monster groups, on the Bestiary tab) ---------------

@app.route("/encounters/new", methods=["POST"])
def encounter_new():
    new_id = create_encounter(request.form.get("name", ""))
    if new_id:
        flash("Encounter created.")
        return redirect(url_for("encounter_detail", encounter_id=new_id))
    return redirect(url_for("bestiary"))


@app.route("/encounters/<int:encounter_id>")
def encounter_detail(encounter_id):
    enc = get_encounter(encounter_id)
    if enc is None:
        abort(404)
    members = encounter_members(encounter_id)
    return render_template(
        "encounter_detail.html",
        active="bestiary",
        title=enc["name"],
        encounter=enc,
        members=members,
        total_creatures=sum(m["quantity"] for m in members),
        monsters=list_monsters(),
        difficulty=encounter_difficulty(members, list_party()),
    )


@app.route("/encounters/<int:encounter_id>/rename", methods=["POST"])
def encounter_rename(encounter_id):
    if get_encounter(encounter_id):
        rename_encounter(encounter_id, request.form.get("name", ""))
        flash("Encounter renamed.")
    return redirect(url_for("encounter_detail", encounter_id=encounter_id))


@app.route("/encounters/<int:encounter_id>/delete", methods=["POST"])
def encounter_delete(encounter_id):
    delete_encounter(encounter_id)
    flash("Encounter deleted.")
    return redirect(url_for("bestiary"))


@app.route("/encounters/<int:encounter_id>/add", methods=["POST"])
def encounter_add_member(encounter_id):
    if get_encounter(encounter_id) is None:
        abort(404)
    cid = request.form.get("creature_id", type=int)
    monster = get_creature(cid) if cid else None
    # Encounters are groups of monsters; the bestiary is the only source.
    if monster and monster["kind"] == "monster":
        add_member(encounter_id, cid, request.form.get("quantity", 1, type=int) or 1)
        flash(f"Added {monster['name']}.")
    return redirect(url_for("encounter_detail", encounter_id=encounter_id))


@app.route("/encounters/member/<int:member_id>/quantity", methods=["POST"])
def encounter_member_quantity(member_id):
    enc_id = request.form.get("encounter_id", type=int)
    set_member_quantity(member_id, request.form.get("quantity", 0, type=int))
    return redirect(url_for("encounter_detail", encounter_id=enc_id) if enc_id
                    else url_for("bestiary"))


@app.route("/encounters/member/<int:member_id>/remove", methods=["POST"])
def encounter_member_remove(member_id):
    enc_id = request.form.get("encounter_id", type=int)
    remove_member(member_id)
    return redirect(url_for("encounter_detail", encounter_id=enc_id) if enc_id
                    else url_for("bestiary"))


@app.route("/encounters/<int:encounter_id>/start-combat", methods=["POST"])
def encounter_start_combat(encounter_id):
    """Spin up a live combat pre-loaded with this encounter's monsters."""
    enc = get_encounter(encounter_id)
    if enc is None:
        abort(404)
    new_id = create_combat(enc["name"])
    _load_encounter_into_combat(new_id, encounter_id)
    flash("Combat started from encounter.")
    return redirect(url_for("combat_detail", combat_id=new_id))


# --- Combat tracker tab ---------------------------------------------------
# A live fight built on the creature engine: PCs and monsters share one tracker.
# Combatants snapshot their own HP, so the fight never mutates the sheets and
# multiple instances of a stat block (Goblin 1..4) take damage independently.

def _load_encounter_into_combat(combat_id, encounter_id):
    """Add every member of an encounter (respecting quantities) as combatants."""
    for m in encounter_members(encounter_id):
        creature = get_creature(m["creature_id"])
        if creature:
            combat_add_creature(combat_id, creature, m["quantity"])


def _combat_fragment(combat_id):
    """Render the combat tracker body (the #combat AJAX fragment)."""
    return render_template(
        "_combat_body.html",
        combat=get_combat(combat_id),
        combatants=list_combatants(combat_id),
        conditions=CONDITIONS,
        damage_types=DAMAGE_TYPES,
        roster=list_roster(),
        encounters=list_encounters(),
        log=list_combat_log(combat_id),
    )


def _combat_response(combat_id):
    """Re-render the tracker fragment for fetch requests; else full redirect."""
    if _is_fetch() and get_combat(combat_id):
        return _combat_fragment(combat_id)
    return redirect(url_for("combat_detail", combat_id=combat_id))




@app.route("/combat")
def combat():
    return render_template(
        "combat.html", active="combat", title="Combat",
        combats=list_combats("active"),
        history=list_combats("ended"),
    )


@app.route("/combat/new", methods=["POST"])
def combat_new():
    new_id = create_combat(request.form.get("name", ""))
    flash("Combat started.")
    return redirect(url_for("combat_detail", combat_id=new_id))


@app.route("/combat/<int:combat_id>")
def combat_detail(combat_id):
    c = get_combat(combat_id)
    if c is None:
        abort(404)
    return render_template(
        "combat_detail.html",
        active="combat",
        title=c["name"],
        combat=c,
        combatants=list_combatants(combat_id),
        conditions=CONDITIONS,
        damage_types=DAMAGE_TYPES,
        roster=list_roster(),
        encounters=list_encounters(),
        log=list_combat_log(combat_id),
    )


@app.route("/combat/<int:combat_id>/end", methods=["POST"])
def combat_end(combat_id):
    """Archive a combat (keep it in history) rather than destroying it."""
    if get_combat(combat_id):
        set_combat_status(combat_id, "ended")
        flash("Combat ended — kept in history.")
    return redirect(url_for("combat"))


@app.route("/combat/<int:combat_id>/reopen", methods=["POST"])
def combat_reopen(combat_id):
    if get_combat(combat_id):
        set_combat_status(combat_id, "active")
        flash("Combat reopened.")
    return redirect(url_for("combat_detail", combat_id=combat_id))


@app.route("/combat/<int:combat_id>/delete", methods=["POST"])
def combat_delete(combat_id):
    """Permanently delete a combat (from history)."""
    delete_combat(combat_id)
    flash("Combat deleted.")
    return redirect(url_for("combat"))


@app.route("/combat/<int:combat_id>/add", methods=["POST"])
def combat_add(combat_id):
    if get_combat(combat_id) is None:
        abort(404)
    cid = request.form.get("creature_id", type=int)
    creature = get_creature(cid) if cid else None
    if creature:
        combat_add_creature(combat_id, creature, request.form.get("quantity", 1, type=int) or 1)
        flash(f"Added {creature['name']}.")
    return _combat_response(combat_id)


@app.route("/combat/<int:combat_id>/load-encounter", methods=["POST"])
def combat_load_encounter(combat_id):
    if get_combat(combat_id) is None:
        abort(404)
    eid = request.form.get("encounter_id", type=int)
    if eid and get_encounter(eid):
        _load_encounter_into_combat(combat_id, eid)
        flash("Encounter loaded.")
    return _combat_response(combat_id)


@app.route("/combat/<int:combat_id>/roll-initiative", methods=["POST"])
def combat_roll_initiative(combat_id):
    if get_combat(combat_id):
        roll_initiative_all(combat_id)
        flash("Initiative rolled.")
    return _combat_response(combat_id)


@app.route("/combat/<int:combat_id>/next-turn", methods=["POST"])
def combat_next_turn(combat_id):
    if get_combat(combat_id):
        next_turn(combat_id)
    return _combat_response(combat_id)


def _combatant_combat_id(combatant_id):
    c = get_combatant(combatant_id)
    return c["combat_id"] if c else None


@app.route("/combatant/<int:combatant_id>/initiative", methods=["POST"])
def combatant_initiative(combatant_id):
    cid = _combatant_combat_id(combatant_id)
    if cid:
        set_initiative(combatant_id, request.form.get("initiative", 0, type=int) or 0)
        return _combat_response(cid)
    return redirect(url_for("combat"))


@app.route("/combatant/<int:combatant_id>/hp", methods=["POST"])
def combatant_hp(combatant_id):
    """Apply damage or healing. `mode` is 'damage' or 'heal'; `amount` is positive."""
    cid = _combatant_combat_id(combatant_id)
    if cid:
        amount = request.form.get("amount", 0, type=int) or 0
        is_damage = request.form.get("mode") == "damage"
        if amount:
            delta = -amount if is_damage else amount
            damage_type = request.form.get("damage_type", "") if is_damage else ""
            if damage_type not in DAMAGE_TYPES:
                damage_type = ""
            # Concentration: damage to a concentrating caster prompts a CON save; a
            # drop to 0 HP ends it outright.
            conc_creature = None
            if delta < 0:
                m = get_combatant(combatant_id)
                cr = get_creature(m["creature_id"]) if m and m["creature_id"] else None
                if cr and cr["concentration"]:
                    conc_creature = cr
            result = apply_hp(combatant_id, delta, damage_type)
            # Surface a resisted/immune/vulnerable note when the defenses changed it.
            if result and result["label"]:
                flash(f"{result['raw']} {result['damage_type']} → {result['applied']} "
                      f"({result['label']}).")
            # Auto-log the HP adjustment so the combat log fills even from the quick
            # Dmg/Heal buttons (the manual "Log attack" form adds the richer record).
            target = get_combatant(combatant_id)
            if target:
                applied = result["applied"] if result else amount
                add_log_entry(
                    cid, kind=("damage" if is_damage else "heal"),
                    target=target["name"], amount=applied, damage_type=damage_type,
                    detail=(result["label"] if result else ""),
                )
            # The concentration save DC is half the damage *taken* (post-resistance).
            taken = result["applied"] if result else amount
            if conc_creature is not None:
                after = get_combatant(combatant_id)
                if after and after["current_hp"] == 0:
                    drop_concentration(conc_creature["id"])
                    flash(f"{conc_creature['name']} is down — concentration on "
                          f"{conc_creature['concentration']} ends.")
                else:
                    flash(f"{conc_creature['name']}: DC {concentration_dc(taken)} "
                          f"Constitution save or lose concentration on "
                          f"{conc_creature['concentration']}.")
        return _combat_response(cid)
    return redirect(url_for("combat"))


@app.route("/combatant/<int:combatant_id>/temp", methods=["POST"])
def combatant_temp(combatant_id):
    cid = _combatant_combat_id(combatant_id)
    if cid:
        set_temp_hp(combatant_id, request.form.get("temp_hp", 0, type=int) or 0)
        return _combat_response(cid)
    return redirect(url_for("combat"))


@app.route("/combatant/<int:combatant_id>/condition", methods=["POST"])
def combatant_condition(combatant_id):
    cid = _combatant_combat_id(combatant_id)
    if cid:
        toggle_condition(combatant_id, request.form.get("condition", ""))
        return _combat_response(cid)
    return redirect(url_for("combat"))


@app.route("/combatant/<int:combatant_id>/death-save", methods=["POST"])
def combatant_death_save(combatant_id):
    """Death saving throws for a combatant at 0 HP. `action`: 'roll' (d20),
    'success+'/'failure+' (mark one manually), or 'reset'."""
    cid = _combatant_combat_id(combatant_id)
    if cid:
        action = request.form.get("action", "")
        if action == "roll":
            res = roll_death_save(combatant_id)
            if res and res["outcome"] == "revive":
                flash("Nat 20 — back up at 1 HP!")
        elif action == "success+":
            set_death_save(combatant_id, "success", 1)
        elif action == "failure+":
            set_death_save(combatant_id, "failure", 1)
        elif action == "reset":
            clear_death_saves(combatant_id)
        return _combat_response(cid)
    return redirect(url_for("combat"))


@app.route("/combat/<int:combat_id>/log", methods=["POST"])
def combat_log_add(combat_id):
    """Record a manual combat-log entry: who attacked whom with what, the to-hit
    roll, and the damage. Optionally applies the damage to the target's HP so the
    DM logs and resolves a hit in one step."""
    if get_combat(combat_id) is None:
        abort(404)
    actor = request.form.get("actor", "")
    target = request.form.get("target", "")
    action = request.form.get("action", "")
    attack_roll = request.form.get("attack_roll", type=int)
    amount = request.form.get("amount", type=int)
    damage_type = request.form.get("damage_type", "")
    if damage_type not in DAMAGE_TYPES:
        damage_type = ""
    detail = ""
    # The target can be a tracked combatant (a select of ids) — snapshot its name,
    # and when "apply" is ticked, deal the damage to its HP via apply_hp so
    # resistances/temp-HP/death-saves all behave; the resulting label (resisted/
    # immune/…) and adjusted amount ride into the log entry.
    target_id = request.form.get("target_id", type=int)
    if target_id:
        tc = get_combatant(target_id)
        if tc and tc["combat_id"] == combat_id:
            target = tc["name"]   # snapshot the real combatant name
            if amount and request.form.get("apply"):
                res = apply_hp(target_id, -amount, damage_type)
                if res:
                    amount = res["applied"]
                    detail = res["label"]
    if actor or target or action or amount is not None:
        add_log_entry(
            combat_id, kind="attack", actor=actor, target=target, action=action,
            attack_roll=attack_roll, amount=amount, damage_type=damage_type,
            detail=detail,
        )
    return _combat_response(combat_id)


@app.route("/combat-log/<int:entry_id>/delete", methods=["POST"])
def combat_log_entry_delete(entry_id):
    """Delete a single log line (a mistyped entry). Doesn't reverse any HP it
    applied — just corrects the record."""
    entry = get_log_entry(entry_id)
    if entry is None:
        abort(404)
    cid = entry["combat_id"]
    delete_log_entry(entry_id)
    return _combat_response(cid)


@app.route("/combat/<int:combat_id>/log/clear", methods=["POST"])
def combat_log_clear(combat_id):
    if get_combat(combat_id):
        clear_combat_log(combat_id)
        flash("Combat log cleared.")
    return _combat_response(combat_id)


@app.route("/combatant/<int:combatant_id>/remove", methods=["POST"])
def combatant_remove(combatant_id):
    cid = _combatant_combat_id(combatant_id)
    remove_combatant(combatant_id)
    if cid:
        return _combat_response(cid)
    return redirect(url_for("combat"))


# --- Party tab ------------------------------------------------------------
# The adventuring party (the PCs). Home for between-fights actions like rests,
# which restore the actual character sheets (not a combat snapshot).

@app.route("/party")
def party():
    # Players see the party minus any DM-hidden PC; everyone's clickable to a
    # read-only inspect (edit stays own-PC-only).
    roster = list_party()
    if not is_dm():
        roster = [c for c in roster if can_view_creature(c)]
    return render_template(
        "party.html", active="party", title="Party", party=roster,
    )


@app.route("/party/rest", methods=["POST"])
def party_rest_route():
    if not is_dm():  # DM-only: a player shouldn't rest the whole party (Phase 7)
        abort(403)
    kind = request.form.get("kind")
    if kind in ("short", "long"):
        party_rest(kind)
        # Slots + class resources refresh with the rest: a long rest clears all
        # expended slots & every resource; a short rest recharges Warlock pact slots
        # and the short-recharging resources (Ki, Channel Divinity, …).
        for pc in list_party():
            restore_all_slots(pc["id"]) if kind == "long" else restore_pact_slots(pc["id"])
            resource_rest(pc, kind)
        flash("Long rest — party restored to full HP, spell slots & resources." if kind == "long"
              else "Short rest — party recovered some HP, pact slots & short-rest resources.")
    return redirect(url_for("party"))


@app.route("/party/<int:creature_id>/hp", methods=["POST"])
def party_hp(creature_id):
    """Adjust a PC's HP by an amount (damage or heal). DM-only — players can't
    freely set their own HP. The guard is server-side; the UI is hidden too."""
    if not is_dm():
        abort(403)
    cr = get_creature(creature_id)
    if cr and cr["kind"] == "pc":
        amount = request.form.get("amount", 0, type=int) or 0
        if amount:
            delta = -amount if request.form.get("mode") == "damage" else amount
            adjust_hp(creature_id, delta)
    return redirect(url_for("party"))


def _apply_avatar(creature_id):
    """Apply an avatar change from the character form, if any. A change only
    happens on an explicit action, so a plain save never wipes an existing
    portrait: an uploaded file wins; else a 'remove' clears it; else a non-empty
    emoji sets it; otherwise the avatar is left untouched.

    The emoji field is named `avatar_emoji` (not `avatar`) so it stays out of the
    generic create/update path — avatar is only ever written here.
    """
    file = request.files.get("avatar_file")
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext in ALLOWED_AVATAR_EXT:
            os.makedirs(AVATAR_DIR, exist_ok=True)
            fname = secure_filename(f"{creature_id}{ext}")
            file.save(os.path.join(AVATAR_DIR, fname))
            update_creature(creature_id, {"avatar": url_for("static", filename=f"avatars/{fname}")})
            return
    if request.form.get("remove_avatar"):
        update_creature(creature_id, {"avatar": ""})
        return
    emoji = (request.form.get("avatar_emoji") or "").strip()
    if emoji:
        update_creature(creature_id, {"avatar": emoji})


def _form_to_data(form):
    """Normalize a submitted character form into a data dict for the model.

    The `hidden` checkbox maps onto the visibility spine: checked = DM-only.
    `kind` is constrained to the values the form offers (pc | npc).
    """
    data = form.to_dict()
    data["visibility"] = "hidden" if form.get("hidden") else "visible"
    data["kind"] = form.get("kind") if form.get("kind") in {"pc", "npc", "monster"} else "pc"
    # A subclass only sticks if it belongs to the chosen class (a leftover pick from
    # a previous class is dropped) — the rest of the spine validates against the slug.
    if not valid_subclass(data.get("class_name"), data.get("subclass")):
        data["subclass"] = ""
    # Same for subrace vs the chosen race.
    if not valid_subrace(data.get("race"), data.get("subrace")):
        data["subrace"] = ""
    # Background must be a known slug, else cleared.
    if data.get("background") and not valid_background(data.get("background")):
        data["background"] = ""
    # Location/faction links must point at a real row, else reset to 0 (none).
    if data.get("location_id") and not get_location(_to_int(data.get("location_id"))):
        data["location_id"] = "0"
    if data.get("faction_id") and not get_faction(_to_int(data.get("faction_id"))):
        data["faction_id"] = "0"
    return data


def _to_int(value):
    """Best-effort int from a form value (None/'' → 0)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# --- Inventory (on the character sheet) -----------------------------------

def _item_owner_next(item_id):
    """Return (item, redirect_target) for an item, or (None, character list).
    Aborts 403 if the viewer can't edit the item's owner (visibility spine)."""
    item = get_item(item_id)
    if item is None:
        return None, url_for("character")
    if not can_edit_creature(get_creature(item["creature_id"])):
        abort(403)
    return item, url_for("character_detail", creature_id=item["creature_id"])


def _is_fetch():
    """True when the request came from the sheet's in-place AJAX (vs. a plain form
    POST), so a handler can return just a fragment instead of redirecting."""
    return request.headers.get("X-Requested-With") == "fetch"


def _gear_response(creature_id, target):
    """Re-render just the gear fragment for fetch requests; else full redirect."""
    if _is_fetch():
        creature = get_creature(creature_id)
        return render_template(
            "_gear.html",
            creature=creature,
            can_edit=can_edit_creature(creature),
            items=list_items(creature_id),
            slot_labels=SLOT_LABELS,
            slots=SLOTS,
            abilities=ABILITIES,
            spell_options=all_spells(),
            panel=equipment_panel(creature_id),
            attunement=attunement_summary(creature_id),
        )
    return redirect(target)


def _spellcasting_ctx(creature):
    """Computed spellcasting context for the spellbook fragment: casting stats
    (attack/DC), the slot pool, a level→available lookup (for per-spell Cast
    buttons), and the spells-known/prepared limits. Reused by the sheet and the
    #spells fragment."""
    eff_ab = effective_abilities(creature)
    rows = slot_rows(creature)
    return {
        "spell_stats": spell_stats(creature, eff_ab),
        "slot_rows": rows,
        "caster_type": caster_type(creature),
        "slots_available": {r["level"]: r["available"] for r in rows},
        "spell_limits": spell_limits(creature, eff_ab),
        # 5e: wearing armor you're not proficient with bars spellcasting.
        "armor_block": armor_proficiency_issue(creature),
    }


def _spells_fragment(creature_id):
    """Render the spellbook section for a creature (the #spells AJAX fragment)."""
    creature = get_creature(creature_id)
    known = effective_spells(creature_id)
    known_slugs = {s["slug"] for s in known}
    return render_template(
        "_spells.html",
        creature=creature,
        can_edit=can_edit_creature(creature),
        spells=known,
        addable_spells=[s for s in all_spells() if s["slug"] not in known_slugs],
        **_spellcasting_ctx(creature),
    )


def _resources_fragment(creature_id):
    """Render the class-resources panel for a creature (the #resources AJAX fragment)."""
    creature = get_creature(creature_id)
    return render_template(
        "_resources.html",
        creature=creature,
        can_edit=can_edit_creature(creature),
        resource_rows=resource_rows(creature),
    )


def _feats_fragment(creature_id):
    """Render the feats section for a creature (the #feats AJAX fragment)."""
    creature = get_creature(creature_id)
    return render_template(
        "_feats.html",
        creature=creature,
        can_edit=can_edit_creature(creature),
        feats=list_feats(creature_id),
        feat_book=all_catalog_feats(),
    )


def _actions_fragment(creature_id):
    """Render the actions section for a creature (the #actions AJAX fragment)."""
    creature = get_creature(creature_id)
    return render_template(
        "_actions.html",
        creature=creature,
        can_edit=can_edit_creature(creature),
        actions=list_actions(creature_id),
        action_categories=ACTION_CATEGORIES,
        action_book=all_catalog_actions(),
    )


@app.route("/inventory/add", methods=["POST"])
def inventory_add():
    """Manual item entry — used by the DM on NPC sheets (PCs get items via loot)."""
    cid = request.form.get("creature_id", type=int)
    creature = get_creature(cid) if cid else None
    if creature is None:
        return redirect(url_for("character"))
    if not can_edit_creature(creature):
        abort(403)
    add_item(cid, request.form.get("name", ""),
             request.form.get("quantity", 1, type=int) or 1,
             request.form.get("description", ""),
             slot=request.form.get("slot", ""),
             hands=2 if request.form.get("two_handed") else 1,
             **_magic_fields_from_form())
    return _gear_response(cid, url_for("character_detail", creature_id=cid))


@app.route("/inventory/<int:item_id>/quantity", methods=["POST"])
def inventory_quantity(item_id):
    item, target = _item_owner_next(item_id)
    if item is None:
        return redirect(target)
    adjust_quantity(item_id, request.form.get("delta", 0, type=int))
    return _gear_response(item["creature_id"], target)


@app.route("/inventory/<int:item_id>/equipped", methods=["POST"])
def inventory_equipped(item_id):
    """Toggle: equip an unequipped item, or unequip an equipped one."""
    item, target = _item_owner_next(item_id)
    if item is None:
        return redirect(target)
    if item["equipped"]:
        unequip_item(item_id)
    else:
        equip_item(item_id)
    return _gear_response(item["creature_id"], target)


@app.route("/inventory/<int:item_id>/equip", methods=["POST"])
def inventory_equip(item_id):
    """Always-equip (used by drag-and-drop drops); swap logic lives in equip_item."""
    item, target = _item_owner_next(item_id)
    if item is None:
        return redirect(target)
    equip_item(item_id)
    return _gear_response(item["creature_id"], _safe_next(request.form.get("next"), target))


@app.route("/inventory/<int:item_id>/remove", methods=["POST"])
def inventory_remove(item_id):
    item, target = _item_owner_next(item_id)
    if item is None:
        return redirect(target)
    cid = item["creature_id"]
    remove_item(item_id)
    return _gear_response(cid, target)


@app.route("/inventory/<int:item_id>/hidden", methods=["POST"])
def inventory_hidden(item_id):
    """Toggle an item's hidden flag (declutter the inventory list)."""
    item, target = _item_owner_next(item_id)
    if item is None:
        return redirect(target)
    set_item_hidden(item_id, not item["hidden"])
    return _gear_response(item["creature_id"], target)


@app.route("/inventory/<int:item_id>/attune", methods=["POST"])
def inventory_attune(item_id):
    """Toggle attunement on an item that requires it (a no-op otherwise). Bonuses
    on an attunement-required item only apply while attuned (strict 5e)."""
    item, target = _item_owner_next(item_id)
    if item is None:
        return redirect(target)
    if item["attunement_required"]:
        set_attuned(item_id, not item["attuned"])
    return _gear_response(item["creature_id"], target)


# --- Loot tab -------------------------------------------------------------

@app.route("/loot")
def loot():
    """The loot table at the current location. The DM stocks/manages it and hands
    out items; players can **take** items to their PC and **drop** items from
    their PC's inventory into the pool."""
    area_id = current_area_id()
    my_pc = get_creature(_my_pc_id()) if _my_pc_id() else None
    return render_template(
        "loot.html",
        active="loot",
        title="Loot",
        areas=list_areas(),
        area=get_area(area_id) if area_id else None,
        loot=area_loot(area_id) if area_id else [],
        catalog=all_item_defs(),
        pcs=[c for c in list_roster() if c["kind"] == "pc"],
        slots=SLOTS,
        slot_labels=SLOT_LABELS,
        abilities=ABILITIES,
        spell_options=all_spells(),
        my_pc=my_pc,
        my_items=list_items(my_pc["id"]) if my_pc else [],
    )


@app.route("/loot/<int:loot_id>/take", methods=["POST"])
def loot_take(loot_id):
    """A player picks up a loot item into their own PC (current location only)."""
    pc_id = _my_pc_id()
    if not pc_id:
        abort(403)  # DM hands out via 'give'; only a player with a PC can take
    loot_item = get_loot(loot_id)
    if loot_item and loot_item["area_id"] == current_area_id():
        give_loot(loot_id, pc_id)
        flash("Picked up.")
    return redirect(url_for("loot"))


@app.route("/loot/drop", methods=["POST"])
def loot_drop():
    """Drop an item from your PC's inventory into the current location's loot."""
    item = get_item(request.form.get("item_id", type=int))
    if item is None:
        return redirect(url_for("loot"))
    if not can_edit_creature(get_creature(item["creature_id"])):
        abort(403)  # only your own items
    area_id = current_area_id()
    if area_id:
        drop_to_loot(item["id"], area_id)
        flash("Dropped into the loot table.")
    else:
        flash("No location to drop into yet.")
    return redirect(url_for("loot"))


@app.route("/loot/area/new", methods=["POST"])
def loot_area_new():
    new_id = create_area(request.form.get("name", ""))
    if new_id:
        set_current_area(new_id)
        flash("Area created.")
    return redirect(url_for("loot"))


@app.route("/loot/area/switch", methods=["POST"])
def loot_area_switch():
    aid = request.form.get("area_id", type=int)
    if aid and get_area(aid):
        set_current_area(aid)
    return redirect(url_for("loot"))


@app.route("/loot/area/delete", methods=["POST"])
def loot_area_delete():
    aid = request.form.get("area_id", type=int)
    if aid:
        delete_area(aid)
        flash("Area deleted.")
    return redirect(url_for("loot"))


@app.route("/loot/area/clear", methods=["POST"])
def loot_area_clear():
    aid = request.form.get("area_id", type=int)
    if aid:
        clear_area_loot(aid)
        flash("Area loot cleared.")
    return redirect(url_for("loot"))


@app.route("/loot/spawn", methods=["POST"])
def loot_spawn():
    aid = request.form.get("area_id", type=int)
    item = get_item_def(request.form.get("slug", ""))
    if aid and get_area(aid) and item:
        add_loot(aid, item["name"], request.form.get("quantity", 1, type=int) or 1,
                 item["description"], slot=item["slot"], hands=item["hands"],
                 gold=item.get("gold", 0), silver=item.get("silver", 0),
                 copper=item.get("copper", 0), ac_bonus=item.get("ac_bonus", 0),
                 grants_spells=item.get("grants_spells", ""),
                 stat_bonuses=item.get("stat_bonuses", ""),
                 armor_base=item.get("armor_base", 0),
                 armor_type=item.get("armor_type", ""),
                 weapon=item.get("weapon", ""),
                 attunement_required=item.get("attunement_required", 0))
        flash(f"Spawned {item['name']}.")
    return redirect(url_for("loot"))


def _magic_fields_from_form():
    """Read an item's optional magic properties (AC bonus, ability-score bonuses,
    granted spells) from a submitted form into kwargs for add_item / add_loot."""
    stat = {col: request.form.get("bonus_" + col, 0, type=int) or 0
            for col, _ in ABILITIES}
    return {
        "ac_bonus": request.form.get("ac_bonus", 0, type=int) or 0,
        "grants_spells": request.form.getlist("grants_spells"),
        "stat_bonuses": ", ".join(f"{c}:{v}" for c, v in stat.items() if v),
        "armor_base": request.form.get("armor_base", 0, type=int) or 0,
        "armor_type": request.form.get("armor_type", ""),
        "weapon": pack_weapon(request.form.get("weapon_damage", ""),
                              request.form.get("weapon_type", ""),
                              request.form.get("weapon_ability", "str"),
                              request.form.get("weapon_category", "")),
        "attunement_required": 1 if request.form.get("attune_required") else 0,
    }


@app.route("/loot/create", methods=["POST"])
def loot_create():
    aid = request.form.get("area_id", type=int)
    if aid and get_area(aid):
        add_loot(aid, request.form.get("name", ""),
                 request.form.get("quantity", 1, type=int) or 1,
                 request.form.get("description", ""),
                 slot=request.form.get("slot", ""),
                 hands=2 if request.form.get("two_handed") else 1,
                 gold=request.form.get("gold", 0, type=int) or 0,
                 silver=request.form.get("silver", 0, type=int) or 0,
                 copper=request.form.get("copper", 0, type=int) or 0,
                 **_magic_fields_from_form())
        flash("Item added to loot.")
    return redirect(url_for("loot"))


@app.route("/loot/<int:loot_id>/give", methods=["POST"])
def loot_give(loot_id):
    cid = request.form.get("creature_id", type=int)
    target = get_creature(cid) if cid else None
    # Loot is distributed to player characters only; NPCs are stocked manually.
    if target and target["kind"] == "pc" and give_loot(loot_id, cid):
        flash("Item given.")
    return redirect(url_for("loot"))


@app.route("/loot/<int:loot_id>/remove", methods=["POST"])
def loot_remove(loot_id):
    remove_loot(loot_id)
    flash("Loot removed.")
    return redirect(url_for("loot"))


# --- Dice tab -------------------------------------------------------------

def _humanize_duration(seconds):
    """A coarse gap label like '12 min' / '3 hr' / '2 days'."""
    minutes = int(seconds) // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr"
    days = hours // 24
    return f"{days} day" + ("s" if days != 1 else "")


def _relative(seconds):
    """A short 'time ago' label for a single roll."""
    s = int(seconds)
    if s < 10:
        return "just now"
    if s < 60:
        return f"{s}s ago"
    return _humanize_duration(s) + " ago"


def _decorate_rolls(rows):
    """Add display times to rolls and flag where a long pause separates groups.

    Rows arrive newest-first. `break_after` marks a roll whose next (older)
    neighbour is more than ROLL_GAP_SECONDS earlier, so the template can draw a
    divider between bursts.
    """
    now = datetime.now(timezone.utc)
    parsed = []
    for r in rows:
        try:
            ts = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except (ValueError, TypeError):
            ts = now
        parsed.append((r, ts))

    items = []
    for i, (r, ts) in enumerate(parsed):
        gap_label = None
        if i + 1 < len(parsed):
            gap = (ts - parsed[i + 1][1]).total_seconds()
            if gap > ROLL_GAP_SECONDS:
                gap_label = _humanize_duration(gap)
        items.append({
            "id": r["id"],
            "total": r["total"],
            "detail": r["detail"],
            "label": r["label"],
            "roller": r["roller"],          # username, or None for legacy rolls
            "color": r["roller_color"],     # the roller's tint, or ''
            "clock": ts.astimezone().strftime("%I:%M %p").lstrip("0"),
            "relative": _relative((now - ts).total_seconds()),
            "break_after": gap_label,   # truthy gap string, or None
        })
    return items


@app.route("/dice")
def dice():
    u = current_user()
    return render_template(
        "dice.html",
        active="dice",
        title="Dice",
        die_buttons=DICE_BUTTONS,
        rolls=_decorate_rolls(recent_rolls()),
        my_color=(u["color"] if u else "") or "#c9a14a",
    )


@app.route("/me/color", methods=["POST"])
def set_my_color():
    """Let the logged-in user pick their own dice-log colour."""
    u = current_user()
    if u:
        set_user_color(u["id"], request.form.get("color", ""))
        flash("Roll colour updated.")
    return redirect(_safe_next(request.form.get("next"), url_for("dice")))


@app.route("/dice/roll", methods=["POST"])
def dice_roll():
    """Roll the submitted expression, log it, and bounce back.

    The expression may carry an adv/dis suffix ('d20 adv'); parse_and_roll
    dispatches. `next` lets a roll launched from a character sheet return to that
    sheet instead of the dice page, with the result shown as a flash.
    """
    target = _safe_next(request.form.get("next"), default=url_for("dice"))
    label = (request.form.get("label") or "").strip()
    ajax = _is_fetch()
    try:
        result = parse_and_roll(request.form.get("expression", ""))
    except DiceError as err:
        if ajax:
            return jsonify({"ok": False, "error": str(err)}), 400
        flash(str(err))
        return redirect(target)

    u = current_user()
    add_roll(result, label, user_id=u["id"] if u else None)
    if ajax:
        # Inline-roll path: the sheet's Check/Save/Skill/Cast/Attack buttons (and
        # any .rollable die) fetch this and flash a toast instead of reloading.
        return jsonify({
            "ok": True,
            "total": result["total"],
            "detail": result["detail"],
            "label": label,
            "color": (u["color"] if u and u["color"] else ""),
        })
    prefix = f"{label}: " if label else ""
    flash(f"🎲 {prefix}{result['detail']} = {result['total']}")
    return redirect(target)


@app.route("/dice/roll/<int:roll_id>/delete", methods=["POST"])
def dice_delete(roll_id):
    delete_roll(roll_id)
    flash("Roll deleted.")
    return redirect(url_for("dice"))


@app.route("/dice/clear", methods=["POST"])
def dice_clear():
    clear_rolls()
    flash("Roll history cleared.")
    return redirect(url_for("dice"))


def _safe_next(value, default):
    """Only allow same-site relative redirects (avoid open-redirect)."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return default


# --- Placeholder tabs (filled in later phases) ----------------------------

@app.route("/spells")
def spells():
    # Known/prepared is *per character*, never global (a barbarian's player must
    # not see the wizard's spells flagged). With no auth yet, a "Viewing as"
    # selector scopes the library to one character; in Phase 7 this is replaced
    # by the logged-in user's own character (the DM may still view as anyone).
    roster = editable_roster()  # add-to dropdowns: DM = all, player = own PC only
    view_id = request.args.get("as", type=int)
    if not is_dm():
        view_id = _my_pc_id()  # a player always views the library as their own PC
    view_creature = get_creature(view_id) if view_id else None
    if view_creature and not can_view_creature(view_creature):
        view_creature = None
    spell_status = {}  # slug -> 'prepared' | 'known', for the viewed character only
    if view_creature:
        for s in creature_spells(view_id):
            spell_status[s["slug"]] = "prepared" if s["prepared"] else "known"
    # Prepared float above known, known above the rest; level/name order holds
    # within each group. Search + type/casting/known filters are client-side.
    rank = {"prepared": 0, "known": 1}
    spells_sorted = sorted(
        all_spells(),
        key=lambda s: (rank.get(spell_status.get(s["slug"]), 2), s["level"], s["name"]),
    )
    return render_template(
        "spells.html",
        active="spells",
        title="Spells & Actions",
        spells=spells_sorted,
        spell_status=spell_status,
        view_creature=view_creature,
        action_book=all_catalog_actions(),
        roster=roster,
    )


@app.route("/spells/<slug>")
def spell_detail(slug):
    spell = get_spell(slug)
    if spell is None:
        abort(404)
    # Characters this spell could be added to (DM: all; player: their own PC),
    # flagged with whether they already have it.
    roster = [
        {"id": c["id"], "name": c["name"],
         "has": spell["slug"] in creature_spell_slugs(c["id"])}
        for c in editable_roster()
    ]
    return render_template(
        "spell_detail.html",
        active="spells",
        title=spell["name"],
        spell=spell,
        roster=roster,
    )


# Spellbook mutations work from both the character sheet and the spell page, so
# creature + slug come from the form and `next` decides where to return.

@app.route("/spellbook/add", methods=["POST"])
def spellbook_add():
    cid = _require_edit_form_creature()
    slug = request.form.get("slug", "")
    if get_spell(slug):
        add_spell(cid, slug)
        flash("Spell added.")
    if _is_fetch():
        return _spells_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/spellbook/remove", methods=["POST"])
def spellbook_remove():
    cid = _require_edit_form_creature()
    remove_spell(cid, request.form.get("slug", ""))
    flash("Spell removed.")
    if _is_fetch():
        return _spells_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/spellbook/hidden", methods=["POST"])
def spellbook_hidden():
    """Toggle a known spell's hidden flag (declutter the spellbook list)."""
    cid = _require_edit_form_creature()
    set_spell_hidden(cid, request.form.get("slug", ""),
                     request.form.get("hidden") == "1")
    if _is_fetch():
        return _spells_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/spellbook/prepared", methods=["POST"])
def spellbook_prepared():
    cid = _require_edit_form_creature()
    set_prepared(cid, request.form.get("slug", ""), request.form.get("prepared") == "1")
    if _is_fetch():
        return _spells_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/spellbook/slot", methods=["POST"])
def spellbook_slot():
    """Spend or recover one spell slot of a given level (casting / a quick refill).
    Edit-permission gated, so a player manages only their own PC's slots."""
    cid = _require_edit_form_creature()
    level = request.form.get("slot_level", type=int)
    if level:
        if request.form.get("action") == "restore":
            restore_slot(cid, level)
        elif not spend_slot(cid, level):
            flash(f"No level-{level} slots left.")
        else:
            # Casting a concentration spell starts (and replaces) concentration.
            conc = (request.form.get("concentration") or "").strip()
            if conc:
                set_concentration(cid, conc)
                flash(f"Concentrating on {conc}.")
    if _is_fetch():
        return _spells_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/spellbook/concentrate", methods=["POST"])
def spellbook_concentrate():
    """Set or drop the concentration spell a caster is maintaining (without spending
    a slot — e.g. you cast last turn, or you let it go). Edit-gated to the owner/DM."""
    cid = _require_edit_form_creature()
    if request.form.get("action") == "drop":
        drop_concentration(cid)
    else:
        set_concentration(cid, request.form.get("label", ""))
    if _is_fetch():
        return _spells_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


# Rests are DM-managed on the Party tab (party_rest_route), which restores HP +
# spell slots + class resources for the whole party. The old per-PC sheet rest
# endpoints (spellbook_rest / resources_rest) were removed so a player can't rest
# their own PC — only the DM rests.


# Class-resource mutations (Rage, Ki, Channel Divinity, …). Keyed by a form
# `creature_id` + `key`, edit-gated like the spellbook, AJAX-rerender #resources.

@app.route("/resources/adjust", methods=["POST"])
def resources_adjust():
    """Spend or restore some of a class resource (action 'spend' | 'restore', an
    optional `amount` for pool resources like Lay on Hands)."""
    cid = _require_edit_form_creature()
    creature = get_creature(cid)
    key = request.form.get("key", "")
    amount = max(1, request.form.get("amount", 1, type=int) or 1)
    if request.form.get("action") == "restore":
        restore_resource(creature, key, amount)
    else:
        spend_resource(creature, key, amount)
    if _is_fetch():
        return _resources_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/asi/adjust", methods=["POST"])
def asi_adjust():
    """Raise or lower one ability's Ability Score Improvement bump (delta ±1), within
    the class+level budget and the 20 cap. Edit-gated to the creature's owner/DM.
    A full redirect, since a bump ripples into AC / saves / skills / spell DCs all
    over the sheet — re-rendering one panel would leave the rest stale."""
    cid = _require_edit_form_creature()
    delta = 1 if request.form.get("delta", type=int) and request.form.get("delta", type=int) > 0 else -1
    adjust_asi(get_creature(cid), request.form.get("ability", ""), delta)
    return redirect(_safe_next(request.form.get("next"),
                               url_for("character_detail", creature_id=cid)))


# --- Actions & abilities (on the character/monster sheet) -----------------
# Free-form, creature-attached (CLAUDE.md: distinct from SRD spells). Keyed by
# the form's creature_id + `next`, mirroring the spellbook routes.

@app.route("/actions/add", methods=["POST"])
def actions_add():
    """Add an action to a creature. The primary path grabs a premade entry from
    the action book (a `slug`, copied onto the creature like loot); a `slug` of
    '' falls back to a hand-written custom action from the form fields.
    """
    cid = _require_edit_form_creature()
    entry = get_catalog_action(request.form.get("slug", ""))
    if entry:
        add_action(cid, entry["name"], entry["description"],
                   entry["dice"], entry["category"])
        flash(f"Added {entry['name']}.")
    elif (request.form.get("name") or "").strip():
        add_action(
            cid,
            request.form.get("name", ""),
            request.form.get("description", ""),
            request.form.get("dice", ""),
            request.form.get("category", "action"),
        )
        flash("Custom action added.")
    if _is_fetch():
        return _actions_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/actions/<int:action_id>/remove", methods=["POST"])
def actions_remove(action_id):
    action = get_action(action_id)
    if action is None:
        return redirect(url_for("character"))
    cid = action["creature_id"]
    if not can_edit_creature(get_creature(cid)):
        abort(403)
    remove_action(action_id)
    flash("Action removed.")
    if _is_fetch():
        return _actions_fragment(cid)
    return redirect(_safe_next(
        request.form.get("next"),
        url_for("character_detail", creature_id=cid),
    ))


@app.route("/actions/<int:action_id>/hidden", methods=["POST"])
def actions_hidden(action_id):
    """Toggle an action's hidden flag (soft delete / declutter; survives class
    re-syncs). Edit-gated by the action's creature."""
    action = get_action(action_id)
    if action is None:
        return redirect(url_for("character"))
    cid = action["creature_id"]
    if not can_edit_creature(get_creature(cid)):
        abort(403)
    set_action_hidden(action_id, not action["hidden"])
    if _is_fetch():
        return _actions_fragment(cid)
    return redirect(_safe_next(
        request.form.get("next"),
        url_for("character_detail", creature_id=cid),
    ))


# --- Feats (on the character sheet; skeleton — tracked, no mechanics) ------
# Keyed by the form's creature_id + `next`, mirroring the actions routes.

@app.route("/feats/add", methods=["POST"])
def feats_add():
    """Add a feat to a creature. The primary path grabs a catalog entry (a `slug`,
    copied onto the creature); a blank `slug` falls back to a custom feat from the
    form fields."""
    cid = _require_edit_form_creature()
    entry = get_catalog_feat(request.form.get("slug", ""))
    if entry:
        add_feat(cid, entry["name"], entry["description"], entry.get("prerequisite", ""))
        flash(f"Added {entry['name']}.")
    elif (request.form.get("name") or "").strip():
        add_feat(cid, request.form.get("name", ""),
                 request.form.get("description", ""),
                 request.form.get("prerequisite", ""))
        flash("Custom feat added.")
    if _is_fetch():
        return _feats_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/feats/<int:feat_id>/remove", methods=["POST"])
def feats_remove(feat_id):
    feat = get_feat(feat_id)
    if feat is None:
        return redirect(url_for("character"))
    cid = feat["creature_id"]
    if not can_edit_creature(get_creature(cid)):
        abort(403)
    remove_feat(feat_id)
    flash("Feat removed.")
    if _is_fetch():
        return _feats_fragment(cid)
    return redirect(_safe_next(
        request.form.get("next"),
        url_for("character_detail", creature_id=cid),
    ))


# --- World narrative layer: Locations (Phase 9a) ---------------------------

@app.route("/locations")
def locations():
    """The world's places. The DM manages all; players see the ones revealed to
    them (visibility='visible'), mirroring the NPC fog of war."""
    places = list_locations() if is_dm() else visible_locations()
    return render_template(
        "locations.html", active="locations", title="Locations",
        locations=places, kind_label=location_kind_label,
    )


@app.route("/locations/<int:location_id>")
def location_detail(location_id):
    loc = get_location(location_id)
    if not can_view_entity(loc):
        abort(404)
    here = [c for c in creatures_at(location_id) if can_view_creature(c)]
    subs = [s for s in children_of(location_id) if can_view_entity(s)]
    maps = [m for m in maps_for_location(location_id) if can_view_entity(m)]
    return render_template(
        "location_detail.html", active="locations", title=loc["name"],
        loc=loc, parent=get_location(loc["parent_id"]),
        here=here, subs=subs, maps=maps, kind_label=location_kind_label,
        mentioned_in=_mentioned_in("location", location_id),
    )


@app.route("/locations/new", methods=["GET", "POST"])
def location_new():
    if request.method == "POST":
        new_id = create_location(request.form)
        flash("Location created." if new_id else "A location needs a name.")
        return redirect(url_for("location_detail", location_id=new_id) if new_id
                        else url_for("location_new"))
    return render_template(
        "location_form.html", active="locations", title="New Location",
        loc=None, kinds=LOCATION_KINDS, parents=list_locations(),
    )


@app.route("/locations/<int:location_id>/edit", methods=["GET", "POST"])
def location_edit(location_id):
    loc = get_location(location_id)
    if loc is None:
        abort(404)
    if request.method == "POST":
        update_location(location_id, request.form)
        flash("Location updated.")
        return redirect(url_for("location_detail", location_id=location_id))
    return render_template(
        "location_form.html", active="locations", title="Edit Location",
        loc=loc, kinds=LOCATION_KINDS,
        # A location can't be its own parent.
        parents=[p for p in list_locations() if p["id"] != location_id],
    )


@app.route("/locations/<int:location_id>/visibility", methods=["POST"])
def location_visibility(location_id):
    set_location_visibility(location_id, request.form.get("visibility"))
    return redirect(_safe_next_or(url_for("location_detail", location_id=location_id)))


@app.route("/locations/<int:location_id>/delete", methods=["POST"])
def location_delete(location_id):
    delete_location(location_id)
    flash("Location deleted.")
    return redirect(url_for("locations"))


# --- World narrative layer: Factions (Phase 9a) ----------------------------

@app.route("/factions")
def factions():
    """The world's organizations. DM manages all; players see revealed ones."""
    groups = list_factions() if is_dm() else visible_factions()
    return render_template(
        "factions.html", active="factions", title="Factions", factions=groups,
    )


@app.route("/factions/<int:faction_id>")
def faction_detail(faction_id):
    fac = get_faction(faction_id)
    if not can_view_entity(fac):
        abort(404)
    members = [c for c in members_of(faction_id) if can_view_creature(c)]
    return render_template(
        "faction_detail.html", active="factions", title=fac["name"],
        fac=fac, members=members,
        mentioned_in=_mentioned_in("faction", faction_id),
    )


@app.route("/factions/new", methods=["GET", "POST"])
def faction_new():
    if request.method == "POST":
        new_id = create_faction(request.form)
        flash("Faction created." if new_id else "A faction needs a name.")
        return redirect(url_for("faction_detail", faction_id=new_id) if new_id
                        else url_for("faction_new"))
    return render_template(
        "faction_form.html", active="factions", title="New Faction",
        fac=None, dispositions=DISPOSITIONS,
    )


@app.route("/factions/<int:faction_id>/edit", methods=["GET", "POST"])
def faction_edit(faction_id):
    fac = get_faction(faction_id)
    if fac is None:
        abort(404)
    if request.method == "POST":
        update_faction(faction_id, request.form)
        flash("Faction updated.")
        return redirect(url_for("faction_detail", faction_id=faction_id))
    return render_template(
        "faction_form.html", active="factions", title="Edit Faction",
        fac=fac, dispositions=DISPOSITIONS,
    )


@app.route("/factions/<int:faction_id>/visibility", methods=["POST"])
def faction_visibility(faction_id):
    set_faction_visibility(faction_id, request.form.get("visibility"))
    return redirect(_safe_next_or(url_for("faction_detail", faction_id=faction_id)))


@app.route("/factions/<int:faction_id>/delete", methods=["POST"])
def faction_delete(faction_id):
    delete_faction(faction_id)
    flash("Faction deleted.")
    return redirect(url_for("factions"))


# --- Quest / objective log (Phase 9c) --------------------------------------

def _visible_objectives(quest_id):
    """A quest's objectives the current viewer may see (DM sees hidden ones too)."""
    objs = objectives_for(quest_id)
    return objs if is_dm() else [o for o in objs if o["visibility"] == "visible"]


def _require_quest(quest_id):
    """Fetch a quest, 404 if the viewer can't see it (players: visible only)."""
    quest = get_quest(quest_id)
    if not can_view_entity(quest):
        abort(404)
    return quest


def _objective_quest_id(objective_id):
    """The quest id owning an objective, or abort 404."""
    obj = get_objective(objective_id)
    if obj is None:
        abort(404)
    return obj["quest_id"]


@app.route("/quests")
def quests():
    """The quest log. DM sees all; players see revealed quests. Grouped by status."""
    rows = list_quests() if is_dm() else visible_quests()
    quest_list = []
    for q in rows:
        done, total = objective_progress(_visible_objectives(q["id"]))
        quest_list.append({"q": q, "done": done, "total": total})
    return render_template(
        "quests.html", active="quests", title="Quests",
        active_quests=[x for x in quest_list if x["q"]["status"] == "active"],
        done_quests=[x for x in quest_list if x["q"]["status"] == "completed"],
        failed_quests=[x for x in quest_list if x["q"]["status"] == "failed"],
    )


@app.route("/quests/<int:quest_id>")
def quest_detail(quest_id):
    quest = _require_quest(quest_id)
    return render_template(
        "quest_detail.html", active="quests", title=quest["title"],
        quest=quest, objectives=_visible_objectives(quest_id),
        statuses=QUEST_STATUSES,
    )


@app.route("/quests/new", methods=["GET", "POST"])
def quest_new():
    if request.method == "POST":
        new_id = create_quest(request.form)
        flash("Quest created." if new_id else "A quest needs a title.")
        return redirect(url_for("quest_detail", quest_id=new_id) if new_id
                        else url_for("quest_new"))
    return render_template("quest_form.html", active="quests", title="New Quest",
                           quest=None, statuses=QUEST_STATUSES)


@app.route("/quests/<int:quest_id>/edit", methods=["GET", "POST"])
def quest_edit(quest_id):
    quest = get_quest(quest_id)
    if quest is None:
        abort(404)
    if request.method == "POST":
        update_quest(quest_id, request.form)
        flash("Quest updated.")
        return redirect(url_for("quest_detail", quest_id=quest_id))
    return render_template("quest_form.html", active="quests", title="Edit Quest",
                           quest=quest, statuses=QUEST_STATUSES)


@app.route("/quests/<int:quest_id>/status", methods=["POST"])
def quest_status(quest_id):
    set_quest_status(quest_id, request.form.get("status"))
    return redirect(_safe_next_or(url_for("quest_detail", quest_id=quest_id)))


@app.route("/quests/<int:quest_id>/visibility", methods=["POST"])
def quest_visibility(quest_id):
    set_quest_visibility(quest_id, request.form.get("visibility"))
    return redirect(_safe_next_or(url_for("quest_detail", quest_id=quest_id)))


@app.route("/quests/<int:quest_id>/delete", methods=["POST"])
def quest_delete(quest_id):
    delete_quest(quest_id)
    flash("Quest deleted.")
    return redirect(url_for("quests"))


@app.route("/quests/<int:quest_id>/objective/new", methods=["POST"])
def objective_new(quest_id):
    add_objective(quest_id, request.form.get("description"),
                  request.form.get("visibility", "visible"))
    return redirect(url_for("quest_detail", quest_id=quest_id))


@app.route("/objective/<int:objective_id>/status", methods=["POST"])
def objective_status(objective_id):
    quest_id = _objective_quest_id(objective_id)
    set_objective_status(objective_id, request.form.get("status"))
    return redirect(url_for("quest_detail", quest_id=quest_id))


@app.route("/objective/<int:objective_id>/edit", methods=["POST"])
def objective_edit(objective_id):
    quest_id = _objective_quest_id(objective_id)
    update_objective(objective_id, request.form.get("description"))
    return redirect(url_for("quest_detail", quest_id=quest_id))


@app.route("/objective/<int:objective_id>/visibility", methods=["POST"])
def objective_visibility(objective_id):
    quest_id = _objective_quest_id(objective_id)
    set_objective_visibility(objective_id, request.form.get("visibility"))
    return redirect(url_for("quest_detail", quest_id=quest_id))


@app.route("/objective/<int:objective_id>/delete", methods=["POST"])
def objective_delete(objective_id):
    quest_id = _objective_quest_id(objective_id)
    delete_objective(objective_id)
    return redirect(url_for("quest_detail", quest_id=quest_id))


# --- Maps (Phase 10) -------------------------------------------------------

def _apply_map_image(map_id):
    """Apply a background-image change from the map form, if any. Mirrors
    `_apply_avatar`: an uploaded file wins; else an explicit 'remove' clears it;
    otherwise the existing image is left untouched (a plain save never wipes it).
    """
    file = request.files.get("image_file")
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext in ALLOWED_MAP_EXT:
            os.makedirs(MAP_DIR, exist_ok=True)
            fname = secure_filename(f"{map_id}{ext}")
            file.save(os.path.join(MAP_DIR, fname))
            set_map_image(map_id, url_for("static", filename=f"maps/{fname}"))
            return
    if request.form.get("remove_image"):
        set_map_image(map_id, "")


@app.route("/map")
def map():
    """The maps list. The DM manages all; players see only revealed maps
    (visibility='visible'), mirroring the location fog of war."""
    maps = list_maps() if is_dm() else visible_maps()
    return render_template("map.html", active="map", title="Map", maps=maps)


@app.route("/map/<int:map_id>")
def map_detail(map_id):
    m = get_map(map_id)
    if not can_view_entity(m):
        abort(404)
    # Entity choices for the DM's marker-placement form (omit this very map so a
    # marker can't drill down to itself).
    targets = None
    if is_dm():
        targets = {
            "creatures": list_roster(),
            "locations": list_locations(),
            "factions": list_factions(),
            "maps": [x for x in list_maps() if x["id"] != map_id],
        }
    return render_template(
        "map_detail.html", active="map", title=m["name"],
        map=m, location=get_location(m["location_id"]),
        markers=_resolved_markers(map_id), targets=targets,
    )


@app.route("/map/new", methods=["GET", "POST"])
def map_new():
    if request.method == "POST":
        new_id = create_map(request.form)
        if new_id:
            _apply_map_image(new_id)
        flash("Map created." if new_id else "A map needs a name.")
        return redirect(url_for("map_detail", map_id=new_id) if new_id
                        else url_for("map_new"))
    return render_template(
        "map_form.html", active="map", title="New Map",
        map=None, locations=list_locations(),
    )


@app.route("/map/<int:map_id>/edit", methods=["GET", "POST"])
def map_edit(map_id):
    m = get_map(map_id)
    if m is None:
        abort(404)
    if request.method == "POST":
        update_map(map_id, request.form)
        _apply_map_image(map_id)
        flash("Map updated.")
        return redirect(url_for("map_detail", map_id=map_id))
    return render_template(
        "map_form.html", active="map", title="Edit Map",
        map=m, locations=list_locations(),
    )


@app.route("/map/<int:map_id>/visibility", methods=["POST"])
def map_visibility(map_id):
    set_map_visibility(map_id, request.form.get("visibility"))
    return redirect(_safe_next_or(url_for("map_detail", map_id=map_id)))


@app.route("/map/<int:map_id>/delete", methods=["POST"])
def map_delete(map_id):
    delete_map(map_id)
    flash("Map deleted.")
    return redirect(url_for("map"))


# --- Map markers (Phase 10b) -----------------------------------------------

def _require_map(map_id):
    """Fetch a map or 404. Used by marker mutations (already DM-gated)."""
    m = get_map(map_id)
    if m is None:
        abort(404)
    return m


@app.route("/map/<int:map_id>/marker/new", methods=["POST"])
def marker_new(map_id):
    _require_map(map_id)
    create_marker(map_id, request.form)
    flash("Marker placed.")
    return redirect(url_for("map_detail", map_id=map_id))


@app.route("/map/<int:map_id>/marker/<int:marker_id>/move", methods=["POST"])
def marker_move(map_id, marker_id):
    marker = get_marker(marker_id)
    if marker is None or marker["map_id"] != map_id:
        abort(404)
    move_marker(marker_id, request.form.get("x"), request.form.get("y"))
    return ("", 204)


@app.route("/map/<int:map_id>/marker/<int:marker_id>/edit", methods=["POST"])
def marker_edit(map_id, marker_id):
    marker = get_marker(marker_id)
    if marker is None or marker["map_id"] != map_id:
        abort(404)
    update_marker(marker_id, request.form)
    flash("Marker updated.")
    return redirect(url_for("map_detail", map_id=map_id))


@app.route("/map/<int:map_id>/marker/<int:marker_id>/visibility", methods=["POST"])
def marker_visibility(map_id, marker_id):
    marker = get_marker(marker_id)
    if marker is None or marker["map_id"] != map_id:
        abort(404)
    set_marker_visibility(marker_id, request.form.get("visibility"))
    return redirect(_safe_next_or(url_for("map_detail", map_id=map_id)))


@app.route("/map/<int:map_id>/marker/<int:marker_id>/delete", methods=["POST"])
def marker_delete(map_id, marker_id):
    marker = get_marker(marker_id)
    if marker is None or marker["map_id"] != map_id:
        abort(404)
    delete_marker(marker_id)
    flash("Marker removed.")
    return redirect(url_for("map_detail", map_id=map_id))


# --- Campaign journal (Phase 9b) -------------------------------------------

def _require_folder(folder_id, *, edit=False):
    """Fetch a folder, 404 if the viewer can't see it, 403 if edit needed and
    they're not the owner/DM. Returns the folder row."""
    folder = get_folder(folder_id)
    if not can_view_folder(folder):
        abort(404)
    if edit and not can_edit_folder(folder):
        abort(403)
    return folder


def _require_note(note_id, *, edit=False):
    note = get_note(note_id)
    if not can_view_note(note):
        abort(404)
    if edit and not can_edit_note(note):
        abort(403)
    return note


@app.route("/journal")
def journal():
    """The campaign journal home: folders split into the viewer's own and those
    shared by the rest of the party (the DM sees everyone's)."""
    folders = [f for f in list_folders() if can_view_folder(f)]
    me = _my_user_id()
    mine = [f for f in folders if f["owner_id"] == me]
    others = [f for f in folders if f["owner_id"] != me]
    # Show each folder's count *as the viewer sees it* (not the raw total).
    counts = {f["id"]: len(_visible_notes(f["id"])) for f in folders}
    return render_template(
        "journal.html", active="journal", title="Journal",
        mine=mine, others=others, counts=counts,
    )


@app.route("/journal/folder/new", methods=["GET", "POST"])
def journal_folder_new():
    if request.method == "POST":
        new_id = create_folder(_my_user_id(), request.form.get("title"),
                               request.form.get("description"))
        flash("Folder created." if new_id else "A folder needs a title.")
        return redirect(url_for("journal_folder", folder_id=new_id) if new_id
                        else url_for("journal_folder_new"))
    return render_template("journal_folder_form.html", active="journal",
                           title="New Folder", folder=None)


@app.route("/journal/folder/<int:folder_id>")
def journal_folder(folder_id):
    folder = _require_folder(folder_id)
    return render_template(
        "journal_folder.html", active="journal", title=folder["title"],
        folder=folder, notes=_visible_notes(folder_id),
        can_edit=can_edit_folder(folder),
    )


@app.route("/journal/folder/<int:folder_id>/edit", methods=["GET", "POST"])
def journal_folder_edit(folder_id):
    folder = _require_folder(folder_id, edit=True)
    if request.method == "POST":
        update_folder(folder_id, request.form.get("title"),
                      request.form.get("description"))
        flash("Folder updated.")
        return redirect(url_for("journal_folder", folder_id=folder_id))
    return render_template("journal_folder_form.html", active="journal",
                           title="Edit Folder", folder=folder)


@app.route("/journal/folder/<int:folder_id>/delete", methods=["POST"])
def journal_folder_delete(folder_id):
    _require_folder(folder_id, edit=True)
    delete_folder(folder_id)
    flash("Folder deleted.")
    return redirect(url_for("journal"))


@app.route("/journal/folder/<int:folder_id>/note/new", methods=["GET", "POST"])
def journal_note_new(folder_id):
    folder = _require_folder(folder_id, edit=True)
    if request.method == "POST":
        new_id = create_note(folder_id, _my_user_id(), request.form.get("title"),
                             request.form.get("body"),
                             request.form.get("visibility", "private"))
        if new_id:
            set_mentions(new_id, _form_mentions(request.form))
        flash("Note saved." if new_id else "A note needs a title.")
        return redirect(url_for("journal_note", note_id=new_id) if new_id
                        else url_for("journal_note_new", folder_id=folder_id))
    return render_template("journal_note_form.html", active="journal",
                           title="New Note", folder=folder, note=None,
                           mention_options=_mention_options(), selected_mentions=set())


@app.route("/journal/note/<int:note_id>")
def journal_note(note_id):
    note = _require_note(note_id)
    return render_template(
        "journal_note.html", active="journal", title=note["title"],
        note=note, can_edit=can_edit_note(note),
        mentions=_note_mention_links(note_id),
    )


@app.route("/journal/note/<int:note_id>/edit", methods=["GET", "POST"])
def journal_note_edit(note_id):
    note = _require_note(note_id, edit=True)
    if request.method == "POST":
        update_note(note_id, request.form.get("title"), request.form.get("body"),
                    request.form.get("visibility"))
        set_mentions(note_id, _form_mentions(request.form))
        flash("Note updated.")
        return redirect(url_for("journal_note", note_id=note_id))
    # Pre-select the note's current mentions in the picker ("type:id" keys).
    selected = {"%s:%d" % (m["entity_type"], m["entity_id"])
                for m in mentions_for_note(note_id)}
    return render_template("journal_note_form.html", active="journal",
                           title="Edit Note", folder=get_folder(note["folder_id"]),
                           note=note, mention_options=_mention_options(),
                           selected_mentions=selected)


@app.route("/journal/note/<int:note_id>/visibility", methods=["POST"])
def journal_note_visibility(note_id):
    _require_note(note_id, edit=True)
    set_note_visibility(note_id, request.form.get("visibility"))
    return redirect(_safe_next_or(url_for("journal_note", note_id=note_id)))


@app.route("/journal/note/<int:note_id>/delete", methods=["POST"])
def journal_note_delete(note_id):
    note = _require_note(note_id, edit=True)
    folder_id = note["folder_id"]
    delete_note(note_id)
    flash("Note deleted.")
    return redirect(url_for("journal_folder", folder_id=folder_id))


# --- Friendly error pages (no more bare white screens on 403/404) ----------

@app.errorhandler(403)
def _forbidden(_e):
    return render_template(
        "error.html", title="Not allowed", code="403",
        message="You don't have access to that — it's a DM-only or read-only area.",
    ), 403


@app.errorhandler(404)
def _not_found(_e):
    return render_template(
        "error.html", title="Not found", code="404",
        message="That page doesn't exist, or isn't visible to you.",
    ), 404


if __name__ == "__main__":
    # Local dev only. Migrations already ran at import (see init_db() above).
    # Production is served by gunicorn (see Dockerfile), which never reaches here.
    app.run(debug=True, port=5002)
