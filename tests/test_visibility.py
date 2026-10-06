"""The fog-of-war spine: the DM sees everything, players see only their own PC
and whatever's been revealed. Visibility must be enforced server-side (404 for
anything a player can't see, 403 for anything they can see but not edit) — this
is the rule CLAUDE.md calls out as never-CSS/JS-only, so it's worth pinning down
with a real test rather than trusting every new route to remember it by hand.
"""
from models.user import get_user_by_username, set_user_character

from tests.conftest import login, make_creature, make_dm, make_player


def _dm_and_player(client):
    make_dm("dm", "dmpass123")
    pc_id = make_creature(name="Playerchar", kind="pc", visibility="visible")
    make_player("player1", "playerpass123", creature_id=pc_id)
    return pc_id


def test_dm_sees_a_hidden_npc(client):
    make_dm("dm", "dmpass123")
    npc_id = make_creature(name="Secret Villain", kind="npc", visibility="hidden")
    login(client, "dm", "dmpass123")
    resp = client.get(f"/character/{npc_id}")
    assert resp.status_code == 200


def test_player_cannot_view_a_hidden_npc(client):
    _dm_and_player(client)
    hidden_id = make_creature(name="Secret Villain", kind="npc", visibility="hidden")
    login(client, "player1", "playerpass123")
    resp = client.get(f"/character/{hidden_id}")
    assert resp.status_code == 404  # not 403 — existence itself is hidden


def test_player_can_view_a_revealed_npc(client):
    _dm_and_player(client)
    revealed_id = make_creature(name="Friendly Innkeep", kind="npc", visibility="visible")
    login(client, "player1", "playerpass123")
    resp = client.get(f"/character/{revealed_id}")
    assert resp.status_code == 200


def test_player_can_view_their_own_character(client):
    pc_id = _dm_and_player(client)
    login(client, "player1", "playerpass123")
    resp = client.get(f"/character/{pc_id}")
    assert resp.status_code == 200


def test_player_can_view_but_not_edit_a_party_members_pc(client):
    pc_id = _dm_and_player(client)
    other_pc_id = make_creature(name="Other Hero", kind="pc", visibility="visible")
    make_player("player2", "playerpass123", creature_id=other_pc_id)

    login(client, "player1", "playerpass123")
    # Read-only inspect of a fellow party member is allowed...
    resp = client.get(f"/character/{other_pc_id}")
    assert resp.status_code == 200
    # ...but editing someone else's sheet is not.
    resp = client.get(f"/character/{other_pc_id}/edit")
    assert resp.status_code == 403


def test_player_can_edit_their_own_character(client):
    pc_id = _dm_and_player(client)
    login(client, "player1", "playerpass123")
    resp = client.get(f"/character/{pc_id}/edit")
    assert resp.status_code == 200


def test_dm_only_route_is_blocked_for_players(client):
    _dm_and_player(client)
    login(client, "player1", "playerpass123")
    # character_new is in _DM_ONLY_ENDPOINTS — players create their own PC through
    # /character/create-mine instead, never the DM authoring route.
    resp = client.get("/character/new")
    assert resp.status_code == 403


def test_dm_only_route_is_reachable_for_the_dm(client):
    make_dm("dm", "dmpass123")
    login(client, "dm", "dmpass123")
    resp = client.get("/character/new")
    assert resp.status_code == 200


def test_player_reassignment_does_not_leak_the_old_characters_visibility(client):
    """Guards against a stale `_my_pc_id()` read: once the DM reassigns a player
    to a different character, the old one goes back to being just another PC —
    visible if visibility='visible' says so, not because it was ever theirs."""
    pc_id = _dm_and_player(client)
    new_pc_id = make_creature(name="Reassigned Hero", kind="pc", visibility="hidden")
    set_user_character(_user_id(client, "player1"), new_pc_id)

    login(client, "player1", "playerpass123")
    # Hidden PC assigned to them now — still viewable because it's their own.
    resp = client.get(f"/character/{new_pc_id}")
    assert resp.status_code == 200
    # The old PC is just another visible-by-default party member now — viewable
    # (it's a visible PC) but no longer editable (it's not theirs anymore).
    resp = client.get(f"/character/{pc_id}")
    assert resp.status_code == 200
    resp = client.get(f"/character/{pc_id}/edit")
    assert resp.status_code == 403


def _user_id(client, username):
    return get_user_by_username(username)["id"]
