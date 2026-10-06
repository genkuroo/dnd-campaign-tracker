"""Shared pytest fixtures for the dnd-campaign-tracker test suite.

Each test gets its own throwaway SQLite file via `db.DB_PATH` (the same
single-DB escape hatch `seed_test_db.py` uses) so tests never touch a real
campaign and never see each other's data.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import db as db_module
import app as app_module
from models.creature import create_creature
from models.user import create_user, set_signup_code


@pytest.fixture
def client(tmp_path):
    db_module.DB_PATH = str(tmp_path / "test_campaign.db")
    db_module.init_db()
    app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with app_module.app.test_client() as c:
        yield c


def make_dm(username="dm", password="dmpass123"):
    """Seed a DM account directly (bypasses the one-time /setup flow)."""
    return create_user(username, password, role="dm")


def make_player(username, password="playerpass123", creature_id=None):
    return create_user(username, password, role="player", creature_id=creature_id)


def make_creature(**overrides):
    data = {"name": "Test Creature", "kind": "pc", "visibility": "visible"}
    data.update(overrides)
    return create_creature(data)


def login(client, username, password):
    return client.post(
        "/login", data={"username": username, "password": password}
    )
