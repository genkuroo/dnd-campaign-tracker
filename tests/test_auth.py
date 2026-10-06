"""Login, first-run setup, and signup-code registration."""
from models.user import set_signup_code

from tests.conftest import login, make_dm


def test_first_run_setup_creates_dm_and_logs_in(client):
    resp = client.post(
        "/setup", data={"username": "dm", "password": "dmpass123"}
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/character")

    # The new DM is already logged in via the setup redirect.
    resp = client.get("/users")
    assert resp.status_code == 200


def test_setup_disabled_once_a_user_exists(client):
    make_dm()
    resp = client.get("/setup")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_login_with_wrong_password_fails(client):
    make_dm("dm", "dmpass123")
    resp = login(client, "dm", "wrong-password")
    assert resp.status_code == 200  # re-renders the login form with a flash
    resp = client.get("/users")
    assert resp.status_code == 302  # never got a session


def test_login_with_correct_password_succeeds(client):
    make_dm("dm", "dmpass123")
    resp = login(client, "dm", "dmpass123")
    assert resp.status_code == 302
    resp = client.get("/users")
    assert resp.status_code == 200


def test_logout_clears_session(client):
    make_dm("dm", "dmpass123")
    login(client, "dm", "dmpass123")
    client.post("/logout")
    resp = client.get("/users")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_register_blocked_without_a_signup_code(client):
    make_dm()
    resp = client.get("/register")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_register_with_valid_code_creates_a_player(client):
    make_dm()
    set_signup_code("letmein")
    resp = client.post(
        "/register",
        data={"code": "letmein", "username": "newplayer", "password": "playerpass123"},
    )
    assert resp.status_code == 302
    # The new account is logged in and has no character yet.
    resp = client.get("/character")
    assert resp.status_code == 200


def test_register_with_wrong_code_is_rejected(client):
    make_dm()
    set_signup_code("letmein")
    resp = client.post(
        "/register",
        data={"code": "nope", "username": "newplayer", "password": "playerpass123"},
    )
    assert resp.status_code == 200  # re-renders register with a flash, no account
    resp = client.get("/character")
    assert resp.status_code == 302  # no session was created
