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
    Flask, abort, flash, g, redirect, render_template, request, session, url_for,
)
from markupsafe import Markup, escape
from werkzeug.utils import secure_filename

from db import init_db
from models.creature import (
    ABILITIES,
    ALIGNMENTS,
    DISPOSITIONS,
    KINDS,
    MAX_LEVEL,
    MONSTER_KINDS,
    ability_modifier,
    alignment_label,
    create_creature,
    delete_creature,
    adjust_hp,
    format_modifier,
    get_creature,
    level_from_xp,
    list_monsters,
    list_party,
    list_roster,
    party_rest,
    update_creature,
    xp_to_next,
)
from models.dice import DiceError, parse_and_roll
from models.glossary import define
from models.roll_log import add_roll, clear_rolls, delete_roll, recent_rolls
from models.inventory import (
    SLOT_LABELS,
    SLOTS,
    add_item,
    adjust_quantity,
    equip_item,
    equipment_panel,
    get_item,
    list_items,
    remove_item,
    unequip_item,
)
from models.items import all_item_defs, get_item_def
from models.loot import (
    add_loot,
    area_loot,
    clear_area_loot,
    create_area,
    current_area_id,
    delete_area,
    get_area,
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
    list_actions,
    remove_action,
)
from models.action_catalog import all_catalog_actions, get_catalog_action
from models.combat import (
    CONDITIONS,
    add_creature as combat_add_creature,
    apply_hp,
    create_combat,
    delete_combat,
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
)
from models.encounters import (
    add_member,
    create_encounter,
    delete_encounter,
    encounter_members,
    get_encounter,
    list_encounters,
    remove_member,
    rename_encounter,
    set_member_quantity,
)
from models.spells import all_spells, get_spell, level_label, search_spells
from models.user import (
    create_user,
    delete_user,
    get_signup_code,
    get_user,
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
    remove_spell,
    set_prepared,
)

# Quick-roll die buttons on the dice page.
DICE_BUTTONS = [4, 6, 8, 10, 12, 20, 100]

# A pause longer than this between rolls starts a new visual group in the log.
ROLL_GAP_SECONDS = 5 * 60

app = Flask(__name__)
app.secret_key = "dnd-campaign-tracker-local-only"  # local dev only; not a secret
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024  # cap uploads (avatars) at 3 MB

# Uploaded character portraits live under static/avatars (served by Flask's
# static route). Kept out of git; the dir is created on demand.
AVATAR_DIR = os.path.join(app.static_folder, "avatars")
ALLOWED_AVATAR_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Exposed as a Jinja global (not a context processor) so imported macros — which
# don't receive template context — can still look up glossary terms.
app.jinja_env.globals["define"] = define

# The top-level tabs. `endpoint` is the Flask view name; `label` is what the
# navigation renders. Single source of truth so nav and routes can't drift.
TABS = [
    {"endpoint": "character", "label": "Character Sheet"},
    {"endpoint": "party", "label": "Party"},
    {"endpoint": "bestiary", "label": "Bestiary", "dm_only": True},
    {"endpoint": "combat", "label": "Combat"},
    {"endpoint": "loot", "label": "Loot", "dm_only": True},
    {"endpoint": "spells", "label": "Spells & Actions"},
    {"endpoint": "dice", "label": "Dice"},
    {"endpoint": "map", "label": "Map"},
    {"endpoint": "blog", "label": "Campaign Blog"},
    {"endpoint": "users", "label": "Users", "dm_only": True},
]


@app.context_processor
def inject_nav():
    """Make the tab list available to every template (the base layout uses it)."""
    return {"tabs": TABS}


def current_user():
    """The logged-in user row for this request, or None. Cached on flask.g."""
    if "user" not in g:
        uid = session.get("user_id")
        g.user = get_user(uid) if uid else None
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
    "bestiary", "monster_new", "monster_inspect", "monster_reveal",
    "encounter_detail", "encounter_new", "encounter_rename", "encounter_delete",
    "encounter_add_member", "encounter_member_quantity", "encounter_member_remove",
    "encounter_start_combat",
    "combat_new", "combat_end", "combat_reopen",
    "combat_delete", "combat_add", "combat_load_encounter",
    "combat_roll_initiative", "combat_next_turn",
    "combatant_initiative", "combatant_hp", "combatant_temp",
    "combatant_condition", "combatant_remove",
    "loot", "loot_area_new", "loot_area_switch", "loot_area_delete",
    "loot_area_clear", "loot_spawn", "loot_create", "loot_give", "loot_remove",
    "party_rest_route", "party_hp",
    "users", "users_set_code", "users_set_character", "users_reset_password",
    "users_set_color", "users_delete",
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


def can_view_creature(creature):
    """DM sees everyone. A player sees only their own PC. (Discovered NPCs /
    locations reach players through the entity sidebar + blog in Phase 9; the
    `visibility` flag already gates those server-side when they land.)"""
    if is_dm():
        return True
    return creature is not None and creature["id"] == _my_pc_id()


def can_edit_creature(creature):
    """DM edits anyone; a player edits only their own PC."""
    if is_dm():
        return True
    return creature is not None and creature["id"] == _my_pc_id()


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


@app.template_filter("action_category")
def _action_category_filter(value):
    """Jinja filter: action category code -> label (e.g. 'bonus' -> 'Bonus Action')."""
    return action_category_label(value)


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


# Vocab the character form needs; injected so the form template stays declarative.
def _form_vocab():
    return {"abilities": ABILITIES, "kinds": KINDS,
            "dispositions": DISPOSITIONS, "alignments": ALIGNMENTS}


@app.route("/")
def index():
    return redirect(url_for("character"))


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
            session["user_id"] = new_id
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
            session["user_id"] = user["id"]
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
            new_id = create_user(request.form.get("username", ""),
                                  request.form.get("password", ""), role="player")
            if new_id:
                session.clear()
                session["user_id"] = new_id
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
        delete_user(user_id)
        flash("User removed.")
    return redirect(url_for("users"))


# --- Character Sheet tab --------------------------------------------------

@app.route("/character")
def character():
    return render_template(
        "character.html",
        active="character",
        title="Character Sheet",
        roster=visible_roster(),
    )


@app.route("/character/new", methods=["GET", "POST"])
def character_new():
    if request.method == "POST":
        new_id = create_creature(_form_to_data(request.form))
        _apply_avatar(new_id)
        flash("Character created.")
        return redirect(url_for("character_detail", creature_id=new_id))
    return render_template(
        "character_form.html",
        active="character",
        title="New Character",
        creature=None,
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
    known = creature_spells(creature_id)
    known_slugs = {s["slug"] for s in known}
    next_level = xp_to_next(creature["xp"])
    return render_template(
        "character_detail.html",
        active="bestiary" if creature["kind"] == "monster" else "character",
        title=creature["name"],
        can_edit=can_edit_creature(creature),
        abilities=ABILITIES,
        dispositions=DISPOSITIONS,
        creature=creature,
        spells=known,
        addable_spells=[s for s in all_spells() if s["slug"] not in known_slugs],
        next_level=next_level,                         # (level, xp_to_go) or None
        xp_level=level_from_xp(creature["xp"]),         # level the XP implies
        items=list_items(creature_id),
        slot_labels=SLOT_LABELS,
        slots=SLOTS,
        panel=equipment_panel(creature_id),
        actions=list_actions(creature_id),
        action_categories=ACTION_CATEGORIES,
        action_book=all_catalog_actions(),
    )


@app.route("/character/<int:creature_id>/edit", methods=["GET", "POST"])
def character_edit(creature_id):
    creature = _require_edit(creature_id)
    if request.method == "POST":
        update_creature(creature_id, _form_to_data(request.form))
        _apply_avatar(creature_id)
        flash("Character updated.")
        return redirect(url_for("character_detail", creature_id=creature_id))
    vocab = _form_vocab()
    if creature["kind"] == "monster":
        vocab["kinds"] = MONSTER_KINDS  # keep the Type field as Monster, not pc/npc
    return render_template(
        "character_form.html",
        active="bestiary" if creature["kind"] == "monster" else "character",
        title=f"Edit {creature['name']}",
        creature=creature,
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
        flash(f"Leveled up to {new_level}." + (f" +{hp_gain} HP." if hp_gain else ""))
    return redirect(url_for("character_detail", creature_id=creature_id))


@app.route("/character/<int:creature_id>/delete", methods=["POST"])
def character_delete(creature_id):
    delete_creature(creature_id)
    flash("Character deleted.")
    return redirect(url_for("character"))


# --- Bestiary tab (monsters) ----------------------------------------------
# Monsters reuse the creature engine wholesale — the editable sheet is the same
# character_detail view, and create/edit/delete go through the shared character
# routes. The Bestiary only adds a monster-scoped list, a create entry point, and
# the BG3-style read-only inspector with its DM-gated stat reveal.

@app.route("/bestiary")
def bestiary():
    return render_template(
        "bestiary.html",
        active="bestiary",
        title="Bestiary",
        monsters=list_monsters(),
        encounters=list_encounters(),
    )


@app.route("/bestiary/new", methods=["GET", "POST"])
def monster_new():
    if request.method == "POST":
        data = _form_to_data(request.form)
        data["kind"] = "monster"  # the Bestiary only makes monsters
        new_id = create_creature(data)
        _apply_avatar(new_id)
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
    if creature is None or creature["kind"] != "monster":
        abort(404)
    return render_template(
        "inspector.html",
        active="bestiary",
        title=f"Inspect {creature['name']}",
        creature=creature,
        abilities=ABILITIES,
        revealed=bool(creature["stats_revealed"]),
        spells=[s for s in creature_spells(creature_id) if s["prepared"]],
        actions=list_actions(creature_id),
    )


@app.route("/bestiary/<int:creature_id>/reveal", methods=["POST"])
def monster_reveal(creature_id):
    """Toggle whether a monster's stat block is revealed to players (the inspector
    masks the numbers until then). DM-only, live from the inspector."""
    creature = get_creature(creature_id)
    if creature and creature["kind"] == "monster":
        update_creature(creature_id, {"stats_revealed": 0 if creature["stats_revealed"] else 1})
    return redirect(url_for("monster_inspect", creature_id=creature_id))


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
        roster=list_roster(),
        encounters=list_encounters(),
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
        roster=list_roster(),
        encounters=list_encounters(),
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
        if amount:
            delta = -amount if request.form.get("mode") == "damage" else amount
            apply_hp(combatant_id, delta)
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
    return render_template(
        "party.html", active="party", title="Party", party=list_party(),
    )


@app.route("/party/rest", methods=["POST"])
def party_rest_route():
    if not is_dm():  # DM-only: a player shouldn't rest the whole party (Phase 7)
        abort(403)
    kind = request.form.get("kind")
    if kind in ("short", "long"):
        party_rest(kind)
        flash("Long rest — party restored to full HP." if kind == "long"
              else "Short rest — party recovered some HP.")
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
    return data


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
        return render_template(
            "_gear.html",
            creature=get_creature(creature_id),
            items=list_items(creature_id),
            slot_labels=SLOT_LABELS,
            slots=SLOTS,
            panel=equipment_panel(creature_id),
        )
    return redirect(target)


def _spells_fragment(creature_id):
    """Render the spellbook section for a creature (the #spells AJAX fragment)."""
    known = creature_spells(creature_id)
    known_slugs = {s["slug"] for s in known}
    return render_template(
        "_spells.html",
        creature=get_creature(creature_id),
        spells=known,
        addable_spells=[s for s in all_spells() if s["slug"] not in known_slugs],
    )


def _actions_fragment(creature_id):
    """Render the actions section for a creature (the #actions AJAX fragment)."""
    return render_template(
        "_actions.html",
        creature=get_creature(creature_id),
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
             hands=2 if request.form.get("two_handed") else 1)
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


# --- Loot tab -------------------------------------------------------------

@app.route("/loot")
def loot():
    area_id = current_area_id()
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
    )


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
                 item["description"], slot=item["slot"], hands=item["hands"])
        flash(f"Spawned {item['name']}.")
    return redirect(url_for("loot"))


@app.route("/loot/create", methods=["POST"])
def loot_create():
    aid = request.form.get("area_id", type=int)
    if aid and get_area(aid):
        add_loot(aid, request.form.get("name", ""),
                 request.form.get("quantity", 1, type=int) or 1,
                 request.form.get("description", ""),
                 slot=request.form.get("slot", ""),
                 hands=2 if request.form.get("two_handed") else 1)
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
    try:
        result = parse_and_roll(request.form.get("expression", ""))
    except DiceError as err:
        flash(str(err))
        return redirect(target)

    u = current_user()
    add_roll(result, label, user_id=u["id"] if u else None)
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


@app.route("/spellbook/prepared", methods=["POST"])
def spellbook_prepared():
    cid = _require_edit_form_creature()
    set_prepared(cid, request.form.get("slug", ""), request.form.get("prepared") == "1")
    if _is_fetch():
        return _spells_fragment(cid)
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


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


@app.route("/map")
def map():
    return render_template("map.html", active="map", title="Map")


@app.route("/blog")
def blog():
    return render_template("blog.html", active="blog", title="Campaign Blog")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5002)
