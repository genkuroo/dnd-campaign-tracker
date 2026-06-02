"""D&D Campaign Tracker — Flask entry point.

Phase 1: the creature engine + working character sheets. The Character Sheet tab
lists, views, creates, and edits player characters (ability scores + modifiers,
HP, AC, resistances). DM-only for now; player logins arrive in Phase 7.
See CLAUDE.md for the full phased plan.
"""
from flask import (
    Flask, abort, flash, redirect, render_template, request, url_for,
)

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
    list_roster,
    update_creature,
)

app = Flask(__name__)
app.secret_key = "dnd-campaign-tracker-local-only"  # local dev only; not a secret

# The top-level tabs. `endpoint` is the Flask view name; `label` is what the
# navigation renders. Single source of truth so nav and routes can't drift.
TABS = [
    {"endpoint": "character", "label": "Character Sheet"},
    {"endpoint": "spells", "label": "Spells & Actions"},
    {"endpoint": "map", "label": "Map"},
    {"endpoint": "blog", "label": "Campaign Blog"},
]


@app.context_processor
def inject_nav():
    """Make the tab list available to every template (the base layout uses it)."""
    return {"tabs": TABS}


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
    return render_template(
        "character_detail.html",
        active="character",
        title=creature["name"],
        abilities=ABILITIES,
        dispositions=DISPOSITIONS,
        creature=creature,
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


# --- Placeholder tabs (filled in later phases) ----------------------------

@app.route("/spells")
def spells():
    return render_template("spells.html", active="spells", title="Spells & Actions")


@app.route("/map")
def map():
    return render_template("map.html", active="map", title="Map")


@app.route("/blog")
def blog():
    return render_template("blog.html", active="blog", title="Campaign Blog")


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5002)
