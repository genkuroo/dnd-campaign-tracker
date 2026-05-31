"""D&D Campaign Tracker — Flask entry point.

Phase 0: the application shell. Tab navigation (Character / Spells & Actions /
Map / Blog) and the known-entity sidebar are in place as placeholders; no real
campaign data yet. See CLAUDE.md for the full phased plan.
"""
from flask import Flask, redirect, render_template, url_for

from db import init_db

app = Flask(__name__)
app.secret_key = "dnd-campaign-tracker-local-only"  # local dev only; not a secret

# The top-level tabs. `endpoint` is the Flask view name; `label` is what the
# navigation renders. Kept here as the single source of truth so the nav and the
# routes can't drift apart.
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


@app.route("/")
def index():
    return redirect(url_for("character"))


@app.route("/character")
def character():
    return render_template(
        "character.html",
        active="character",
        title="Character Sheet",
    )


@app.route("/spells")
def spells():
    return render_template(
        "spells.html",
        active="spells",
        title="Spells & Actions",
    )


@app.route("/map")
def map():
    return render_template(
        "map.html",
        active="map",
        title="Map",
    )


@app.route("/blog")
def blog():
    return render_template(
        "blog.html",
        active="blog",
        title="Campaign Blog",
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5002)
