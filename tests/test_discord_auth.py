import sqlite3
from urllib.parse import parse_qs, urlparse

import missions
from missions import create_app


def discord_app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "discord.db"),
        "SECRET_KEY": "test",
        "AUTH_DISABLED": False,
        "DISCORD_CLIENT_ID": "client-id",
        "DISCORD_CLIENT_SECRET": "client-secret",
        "DISCORD_GUILD_ID": "hokuten-guild",
        "DISCORD_REDIRECT_URI": "https://example.test/discord/callback",
        "DISCORD_ADMIN_USER_ID": "discord-123",
    })


def begin_discord_login(client):
    client.get("/discord/connect")
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    response = client.post("/discord/login", data={"csrf_token": csrf})
    assert response.status_code == 302
    query = parse_qs(urlparse(response.location).query)
    assert query["scope"] == ["identify guilds.members.read"]
    assert "prompt" not in query
    return query["state"][0]


def mock_discord(monkeypatch, nickname, user_id="discord-123", global_name="Discord User"):
    monkeypatch.setattr(missions, "discord_exchange_code", lambda *_args: {"access_token": "token"})
    monkeypatch.setattr(
        missions, "discord_get",
        lambda _token, path: ({"id": user_id, "username": "discord-user", "global_name": global_name}
                              if path == "/users/@me" else {"nick": nickname}),
    )


def test_discord_connect_is_a_simple_direct_sign_in(tmp_path):
    client = discord_app(tmp_path).test_client()
    page = client.get("/discord/connect")
    assert b"Sign in with Discord" in page.data
    assert b"Continue with Discord" in page.data
    assert b"control of the existing character" in page.data
    assert b"added as a new member" in page.data
    assert b"Match your character name" not in page.data
    assert b"Discord server nickname must be" not in page.data
    assert b"Administrator access" not in page.data


def test_local_admin_bypass_signs_in_as_imaven_without_discord(tmp_path):
    app = discord_app(tmp_path)
    app.config["LOCAL_ADMIN_BYPASS"] = True
    app.config["ALLOW_LOCAL_ADMIN_BYPASS_FOR_TESTS"] = True
    client = app.test_client()

    response = client.get("/endgame")
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert session["is_editor"] is True
        assert session["is_admin"] is True
        imaven_id = session["member_id"]
    database = sqlite3.connect(app.config["DATABASE"])
    assert database.execute("SELECT name FROM members WHERE id=?", (imaven_id,)).fetchone() == ("Imaven",)
    database.close()
    assert client.get("/login?next=/endgame").location.endswith("/endgame")


def test_www_redirects_to_canonical_host_before_discord_session_starts(tmp_path):
    client = discord_app(tmp_path).test_client()
    response = client.get(
        "/discord/connect?next=/help-requests",
        base_url="https://www.hokutenknights.com",
    )
    assert response.status_code == 308
    assert response.location == "https://hokutenknights.com/discord/connect?next=/help-requests"
    assert "session=" not in response.headers.get("Set-Cookie", "")


def test_existing_character_is_linked_without_duplicate(monkeypatch, tmp_path):
    app = discord_app(tmp_path)
    client = app.test_client()
    state = begin_discord_login(client)
    mock_discord(monkeypatch, "imaven")
    response = client.get(f"/discord/callback?code=valid&state={state}", follow_redirects=True)
    assert b"Signed in with Discord as Imaven" in response.data
    assert b"Linkshell Help Requests" in response.data
    assert b"Alliance Builder" in response.data
    assert b">Members</a>" not in response.data
    with client.session_transaction() as session:
        assert session["is_admin"] is True
    database = sqlite3.connect(app.config["DATABASE"])
    assert database.execute("SELECT COUNT(*) FROM members WHERE name='Imaven'").fetchone()[0] == 1
    assert database.execute("SELECT discord_user_id FROM members WHERE name='Imaven'").fetchone()[0] == "discord-123"
    database.close()


def test_new_discord_nickname_creates_and_signs_in_character(monkeypatch, tmp_path):
    app = discord_app(tmp_path)
    client = app.test_client()
    state = begin_discord_login(client)
    mock_discord(monkeypatch, "Newhero", "discord-456")
    response = client.get(f"/discord/callback?code=valid&state={state}")
    assert response.status_code == 302 and "/members/" in response.location
    assert "Expires=" in response.headers["Set-Cookie"]
    database = sqlite3.connect(app.config["DATABASE"])
    member = database.execute(
        "SELECT id,discord_user_id FROM members WHERE name='Newhero'"
    ).fetchone()
    assert member and member[1] == "discord-456"
    database.close()
    with client.session_transaction() as session:
        assert session["member_id"] == member[0]
        assert session["is_editor"] is True
        assert session["is_admin"] is False
        assert session.permanent is True


def test_existing_non_admin_character_is_linked_without_admin(monkeypatch, tmp_path):
    app = discord_app(tmp_path)
    client = app.test_client()
    state = begin_discord_login(client)
    mock_discord(monkeypatch, "Sexualpotato", "discord-friend")
    response = client.get(f"/discord/callback?code=valid&state={state}")
    assert response.status_code == 302
    database = sqlite3.connect(app.config["DATABASE"])
    members = database.execute(
        "SELECT id,discord_user_id,discord_admin FROM members WHERE name=? COLLATE NOCASE",
        ("Sexualpotato",),
    ).fetchall()
    database.close()
    assert len(members) == 1
    assert members[0][1:] == ("discord-friend", 0)
    with client.session_transaction() as session:
        assert session["member_id"] == members[0][0]
        assert session["is_admin"] is False


def test_display_name_is_used_when_server_nickname_is_missing(monkeypatch, tmp_path):
    app = discord_app(tmp_path)
    client = app.test_client()
    state = begin_discord_login(client)
    mock_discord(
        monkeypatch, None, "discord-no-server-nick", global_name="Sexualpotato"
    )
    response = client.get(f"/discord/callback?code=valid&state={state}")
    assert response.status_code == 302
    database = sqlite3.connect(app.config["DATABASE"])
    member = database.execute(
        "SELECT discord_user_id FROM members WHERE name='Sexualpotato' COLLATE NOCASE"
    ).fetchone()
    database.close()
    assert member == ("discord-no-server-nick",)
    with client.session_transaction() as session:
        assert session["is_admin"] is False


def test_bot_membership_lookup_falls_back_when_oauth_member_lookup_fails(monkeypatch, tmp_path):
    app = discord_app(tmp_path)
    app.config["DISCORD_BOT_TOKEN"] = "bot-token"
    client = app.test_client()
    state = begin_discord_login(client)
    monkeypatch.setattr(missions, "discord_exchange_code", lambda *_args: {"access_token": "token"})
    monkeypatch.setattr(
        missions, "discord_get",
        lambda _token, path: {"id": "discord-fallback", "username": "user", "global_name": "Sexualpotato"}
        if path == "/users/@me" else (_ for _ in ()).throw(ValueError("member lookup unavailable")),
    )
    bot_calls = []
    monkeypatch.setattr(
        missions, "discord_bot_request",
        lambda token, method, path: bot_calls.append((token, method, path)) or {"nick": "Sexualpotato"},
    )

    response = client.get(f"/discord/callback?code=valid&state={state}")
    assert response.status_code == 302
    assert bot_calls == [
        ("bot-token", "GET", "/guilds/hokuten-guild/members/discord-fallback")
    ]
    with client.session_transaction() as session:
        assert session["is_editor"] is True


def test_non_admin_discord_account_cannot_claim_imaven(monkeypatch, tmp_path):
    app = discord_app(tmp_path)
    client = app.test_client()
    state = begin_discord_login(client)
    mock_discord(monkeypatch, "Imaven", "discord-attacker")
    response = client.get(f"/discord/callback?code=valid&state={state}", follow_redirects=True)
    assert b"reserved for its verified Discord account" in response.data
    database = sqlite3.connect(app.config["DATABASE"])
    linked_id = database.execute(
        "SELECT discord_user_id FROM members WHERE name='Imaven'"
    ).fetchone()[0]
    database.close()
    assert linked_id == ""
    with client.session_transaction() as session:
        assert session.get("is_admin") is not True


def test_invalid_or_decorated_nickname_is_not_linked(monkeypatch, tmp_path):
    app = discord_app(tmp_path)
    client = app.test_client()
    state = begin_discord_login(client)
    mock_discord(monkeypatch, "Imaven | RDM", "discord-decorated")
    response = client.get(f"/discord/callback?code=valid&state={state}", follow_redirects=True)
    assert b"2\xe2\x80\x9315 letters only" in response.data
    database = sqlite3.connect(app.config["DATABASE"])
    assert database.execute("SELECT COUNT(*) FROM members WHERE discord_user_id<>''").fetchone()[0] == 0
    database.close()


def test_discord_callback_rejects_invalid_state(tmp_path):
    client = discord_app(tmp_path).test_client()
    assert client.get("/discord/callback?code=valid&state=forged").status_code == 400


def test_shared_member_password_is_disabled_when_discord_is_configured(tmp_path):
    app = discord_app(tmp_path)
    client = app.test_client()
    page = client.get("/login", follow_redirects=True)
    assert b"Continue with Discord" in page.data
    assert b'name="member_id"' not in page.data
    assert b'name="password"' not in page.data
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    rejected = client.post("/login", data={
        "csrf_token": csrf, "password": "Hokuten", "action": "sign_in",
    })
    assert rejected.status_code == 302
    assert "/discord/connect" in rejected.location


def test_startup_limits_admin_access_to_verified_admin_characters(tmp_path):
    app = discord_app(tmp_path)
    database = sqlite3.connect(app.config["DATABASE"])
    database.execute("UPDATE members SET discord_admin=1")
    database.execute(
        "UPDATE members SET discord_user_id='discord-123' WHERE name='Imaven'"
    )
    database.execute(
        "UPDATE members SET discord_user_id='discord-sexualpotato' WHERE name='Sexualpotato'"
    )
    database.execute(
        "UPDATE members SET discord_user_id='discord-vlathgar' WHERE name='Vlathgar'"
    )
    database.commit()
    database.close()

    discord_app(tmp_path)
    database = sqlite3.connect(app.config["DATABASE"])
    admins = database.execute(
        "SELECT name FROM members WHERE discord_admin=1 ORDER BY name"
    ).fetchall()
    database.close()
    assert admins == [("Imaven",), ("Sexualpotato",), ("Vlathgar",)]


def test_linked_privileged_character_signs_in_as_admin(monkeypatch, tmp_path):
    app = discord_app(tmp_path)
    database = sqlite3.connect(app.config["DATABASE"])
    database.execute(
        "UPDATE members SET discord_user_id='discord-vlathgar' WHERE name='Vlathgar'"
    )
    database.commit()
    database.close()

    client = app.test_client()
    state = begin_discord_login(client)
    mock_discord(monkeypatch, "Vlathgar", "discord-vlathgar")
    response = client.get(f"/discord/callback?code=valid&state={state}")
    assert response.status_code == 302
    assert response.location.endswith("/help-requests")
    with client.session_transaction() as session:
        assert session["is_admin"] is True
