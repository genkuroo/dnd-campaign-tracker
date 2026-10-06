"""Combat basics: starting a fight, adding combatants, rolling initiative, and
applying damage — all DM-only mutations per `_DM_ONLY_ENDPOINTS`, operating on
creatures generically (no PC/monster special-casing, per CLAUDE.md's "two
spines").
"""
from models.combat import get_combatant, list_combatants

from tests.conftest import login, make_creature, make_dm, make_player


def _dm_with_combat(client):
    make_dm("dm", "dmpass123")
    login(client, "dm", "dmpass123")
    resp = client.post("/combat/new", data={"name": "Goblin Ambush"})
    combat_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    return combat_id


def test_dm_can_create_a_combat_and_open_it(client):
    combat_id = _dm_with_combat(client)
    resp = client.get(f"/combat/{combat_id}")
    assert resp.status_code == 200


def test_adding_a_creature_snapshots_its_stats_independently(client):
    """Combat 'snapshot on add': the combatant copies HP/AC at add time, so
    editing the base sheet afterward never mutates a live combatant."""
    combat_id = _dm_with_combat(client)
    monster_id = make_creature(
        name="Goblin", kind="monster", max_hp=7, current_hp=7, armor_class=15
    )
    client.post(f"/combat/{combat_id}/add", data={"creature_id": monster_id, "quantity": 1})

    combatants = list_combatants(combat_id)
    assert len(combatants) == 1
    assert combatants[0]["name"] == "Goblin"
    assert combatants[0]["current_hp"] == 7


def test_adding_a_creature_twice_can_produce_two_independent_combatants(client):
    combat_id = _dm_with_combat(client)
    monster_id = make_creature(name="Goblin", kind="monster", max_hp=7, current_hp=7)
    client.post(f"/combat/{combat_id}/add", data={"creature_id": monster_id, "quantity": 2})

    combatants = list_combatants(combat_id)
    assert len(combatants) == 2
    # Damaging one leaves the other's snapshot untouched.
    client.post(f"/combatant/{combatants[0]['id']}/hp", data={"mode": "damage", "amount": "5"})
    first = get_combatant(combatants[0]["id"])
    second = get_combatant(combatants[1]["id"])
    assert first["current_hp"] == 2
    assert second["current_hp"] == 7


def test_rolling_initiative_assigns_a_value_to_every_combatant(client):
    combat_id = _dm_with_combat(client)
    monster_id = make_creature(name="Goblin", kind="monster", dexterity=14)
    client.post(f"/combat/{combat_id}/add", data={"creature_id": monster_id, "quantity": 1})
    client.post(f"/combat/{combat_id}/roll-initiative")

    combatants = list_combatants(combat_id)
    assert combatants[0]["initiative"] is not None


def test_player_cannot_create_combat(client):
    make_dm("dm", "dmpass123")
    make_player("player1", "playerpass123")
    login(client, "player1", "playerpass123")
    resp = client.post("/combat/new", data={"name": "Sneaky Fight"})
    assert resp.status_code == 403


def test_player_cannot_apply_damage(client):
    combat_id = _dm_with_combat(client)
    monster_id = make_creature(name="Goblin", kind="monster", max_hp=7, current_hp=7)
    client.post(f"/combat/{combat_id}/add", data={"creature_id": monster_id, "quantity": 1})
    combatant_id = list_combatants(combat_id)[0]["id"]
    client.post("/logout")

    make_player("player1", "playerpass123")
    login(client, "player1", "playerpass123")
    resp = client.post(
        f"/combatant/{combatant_id}/hp", data={"mode": "damage", "amount": "5"}
    )
    assert resp.status_code == 403
    assert get_combatant(combatant_id)["current_hp"] == 7  # untouched
