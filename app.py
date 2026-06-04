"""D&D Campaign Tracker — Flask entry point.

Phase 1: the creature engine + working character sheets. The Character Sheet tab
lists, views, creates, and edits player characters (ability scores + modifiers,
HP, AC, resistances). DM-only for now; player logins arrive in Phase 7.
See CLAUDE.md for the full phased plan.
"""
import re
from datetime import datetime, timezone

from flask import (
    Flask, abort, flash, redirect, render_template, request, url_for,
)
from markupsafe import Markup, escape

from db import init_db
from models.creature import (
    ABILITIES,
    ALIGNMENTS,
    DISPOSITIONS,
    KINDS,
    ability_modifier,
    alignment_label,
    create_creature,
    delete_creature,
    format_modifier,
    get_creature,
    level_from_xp,
    list_roster,
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
from models.spells import all_spells, get_spell, level_label, search_spells
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

# Exposed as a Jinja global (not a context processor) so imported macros — which
# don't receive template context — can still look up glossary terms.
app.jinja_env.globals["define"] = define

# The top-level tabs. `endpoint` is the Flask view name; `label` is what the
# navigation renders. Single source of truth so nav and routes can't drift.
TABS = [
    {"endpoint": "character", "label": "Character Sheet"},
    {"endpoint": "loot", "label": "Loot"},
    {"endpoint": "spells", "label": "Spells & Actions"},
    {"endpoint": "dice", "label": "Dice"},
    {"endpoint": "map", "label": "Map"},
    {"endpoint": "blog", "label": "Campaign Blog"},
]


@app.context_processor
def inject_nav():
    """Make the tab list available to every template (the base layout uses it)."""
    return {"tabs": TABS}


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


# --- Character Sheet tab --------------------------------------------------

@app.route("/character")
def character():
    return render_template(
        "character.html",
        active="character",
        title="Character Sheet",
        roster=list_roster(),
    )


@app.route("/character/new", methods=["GET", "POST"])
def character_new():
    if request.method == "POST":
        new_id = create_creature(_form_to_data(request.form))
        flash("Character created.")
        return redirect(url_for("character_detail", creature_id=new_id))
    return render_template(
        "character_form.html",
        active="character",
        title="New Character",
        creature=None,
        **_form_vocab(),
    )


@app.route("/character/<int:creature_id>")
def character_detail(creature_id):
    creature = get_creature(creature_id)
    if creature is None:
        abort(404)
    known = creature_spells(creature_id)
    known_slugs = {s["slug"] for s in known}
    next_level = xp_to_next(creature["xp"])
    return render_template(
        "character_detail.html",
        active="character",
        title=creature["name"],
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
    )


@app.route("/character/<int:creature_id>/edit", methods=["GET", "POST"])
def character_edit(creature_id):
    creature = get_creature(creature_id)
    if creature is None:
        abort(404)
    if request.method == "POST":
        update_creature(creature_id, _form_to_data(request.form))
        flash("Character updated.")
        return redirect(url_for("character_detail", creature_id=creature_id))
    return render_template(
        "character_form.html",
        active="character",
        title=f"Edit {creature['name']}",
        creature=creature,
        **_form_vocab(),
    )


@app.route("/character/<int:creature_id>/disposition", methods=["POST"])
def character_set_disposition(creature_id):
    """Quick live toggle of a creature's disposition (for NPCs/monsters)."""
    value = request.form.get("disposition")
    if value in DISPOSITIONS:
        update_creature(creature_id, {"disposition": value})
        flash(f"Disposition set to {value}.")
    return redirect(url_for("character_detail", creature_id=creature_id))


@app.route("/character/<int:creature_id>/delete", methods=["POST"])
def character_delete(creature_id):
    delete_creature(creature_id)
    flash("Character deleted.")
    return redirect(url_for("character"))


def _form_to_data(form):
    """Normalize a submitted character form into a data dict for the model.

    The `hidden` checkbox maps onto the visibility spine: checked = DM-only.
    `kind` is constrained to the values the form offers (pc | npc).
    """
    data = form.to_dict()
    data["visibility"] = "hidden" if form.get("hidden") else "visible"
    data["kind"] = form.get("kind") if form.get("kind") in {"pc", "npc"} else "pc"
    return data


# --- Inventory (on the character sheet) -----------------------------------

def _item_owner_next(item_id):
    """Return ((item, redirect_target)) for an item, or (None, character list)."""
    item = get_item(item_id)
    if item is None:
        return None, url_for("character")
    return item, url_for("character_detail", creature_id=item["creature_id"])


def _gear_response(creature_id, target):
    """Re-render just the gear fragment for fetch requests; else full redirect."""
    if request.headers.get("X-Requested-With") == "fetch":
        return render_template(
            "_gear.html",
            creature=get_creature(creature_id),
            items=list_items(creature_id),
            slot_labels=SLOT_LABELS,
            slots=SLOTS,
            panel=equipment_panel(creature_id),
        )
    return redirect(target)


@app.route("/inventory/add", methods=["POST"])
def inventory_add():
    """Manual item entry — used by the DM on NPC sheets (PCs get items via loot)."""
    cid = request.form.get("creature_id", type=int)
    creature = get_creature(cid) if cid else None
    if creature is None:
        return redirect(url_for("character"))
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
            "clock": ts.astimezone().strftime("%I:%M %p").lstrip("0"),
            "relative": _relative((now - ts).total_seconds()),
            "break_after": gap_label,   # truthy gap string, or None
        })
    return items


@app.route("/dice")
def dice():
    return render_template(
        "dice.html",
        active="dice",
        title="Dice",
        die_buttons=DICE_BUTTONS,
        rolls=_decorate_rolls(recent_rolls()),
    )


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

    add_roll(result, label)
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
    # Full list; search + type/casting filters are applied client-side.
    return render_template(
        "spells.html",
        active="spells",
        title="Spells & Actions",
        spells=all_spells(),
    )


@app.route("/spells/<slug>")
def spell_detail(slug):
    spell = get_spell(slug)
    if spell is None:
        abort(404)
    # PCs/NPCs this spell could be added to, flagged with whether they have it.
    roster = [
        {"id": c["id"], "name": c["name"],
         "has": spell["slug"] in creature_spell_slugs(c["id"])}
        for c in list_roster()
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
    cid = request.form.get("creature_id", type=int)
    slug = request.form.get("slug", "")
    if cid and get_creature(cid) and get_spell(slug):
        add_spell(cid, slug)
        flash("Spell added.")
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/spellbook/remove", methods=["POST"])
def spellbook_remove():
    cid = request.form.get("creature_id", type=int)
    slug = request.form.get("slug", "")
    if cid:
        remove_spell(cid, slug)
        flash("Spell removed.")
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/spellbook/prepared", methods=["POST"])
def spellbook_prepared():
    cid = request.form.get("creature_id", type=int)
    slug = request.form.get("slug", "")
    if cid:
        set_prepared(cid, slug, request.form.get("prepared") == "1")
    return redirect(_safe_next(request.form.get("next"), url_for("character")))


@app.route("/map")
def map():
    return render_template("map.html", active="map", title="Map")


@app.route("/blog")
def blog():
    return render_template("blog.html", active="blog", title="Campaign Blog")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5002)
