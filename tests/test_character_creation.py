"""Creating a character: the DM's authoring path and a player's self-service
path (`/character/create-mine`), which forces `kind='pc'` and `visibility=
'visible'` regardless of what's posted, since a player can't hide themselves
from the DM.
"""
from models.creature import get_creature

from tests.conftest import login, make_dm, make_player


def test_dm_creates_a_pc(client):
    make_dm("dm", "dmpass123")
    login(client, "dm", "dmpass123")
    resp = client.post("/character/new", data={"name": "Thalia", "kind": "pc"})
    assert resp.status_code == 302
    location = resp.headers["Location"]
    creature_id = int(location.rstrip("/").rsplit("/", 1)[-1])
    creature = get_creature(creature_id)
    assert creature["name"] == "Thalia"
    assert creature["kind"] == "pc"


def test_dm_creates_a_hidden_npc(client):
    make_dm("dm", "dmpass123")
    login(client, "dm", "dmpass123")
    resp = client.post(
        "/character/new", data={"name": "Shadow Broker", "kind": "npc", "hidden": "1"}
    )
    assert resp.status_code == 302
    creature_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    creature = get_creature(creature_id)
    assert creature["visibility"] == "hidden"


def test_player_self_creates_their_character(client):
    make_dm("dm", "dmpass123")
    make_player("player1", "playerpass123")  # no creature_id yet
    login(client, "player1", "playerpass123")

    resp = client.post("/character/create-mine", data={"name": "Rook", "kind": "monster"})
    assert resp.status_code == 302
    creature_id = int(resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1])
    creature = get_creature(creature_id)
    # Forced server-side regardless of what was posted: a player can only ever
    # make a visible PC, never a hidden creature or a monster/NPC.
    assert creature["kind"] == "pc"
    assert creature["visibility"] == "visible"


def test_player_with_a_character_already_is_redirected_to_it(client):
    make_dm("dm", "dmpass123")
    make_player("player1", "playerpass123")
    login(client, "player1", "playerpass123")
    client.post("/character/create-mine", data={"name": "Rook"})

    # A second attempt doesn't create a second character — it bounces to the
    # existing one.
    resp = client.get("/character/create-mine")
    assert resp.status_code == 302
    first_id = resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1]

    resp = client.post("/character/create-mine", data={"name": "Second Try"})
    assert resp.status_code == 302
    assert resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1] == first_id
