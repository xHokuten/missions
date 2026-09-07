import sqlite3

import pytest

from missions import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "alliances.db"),
                       "SECRET_KEY": "test", "AUTH_DISABLED": True})


def add_roster(app):
    with app.app_context():
        database = sqlite3.connect(app.config["DATABASE"])
        maven = database.execute("SELECT id FROM members WHERE name='Imaven'").fetchone()[0]
        lion = database.execute("SELECT id FROM members WHERE name='Shiru'").fetchone()[0]
        database.executemany(
            "INSERT INTO member_jobs(member_id,job,level) VALUES(?,?,?)",
            [(maven, "PLD", 75), (maven, "WAR", 60), (lion, "WHM", 75)],
        )
        database.commit()
        database.close()
    return maven, lion


def identify(client, member_id):
    with client.session_transaction() as session:
        session["is_editor"] = True
        session["member_id"] = member_id


def test_alliance_builder_supports_two_three_party_alliances(app):
    maven, _lion = add_roster(app)
    client = app.test_client()
    identify(client, maven)
    page = client.get("/alliance-builder")
    assert page.status_code == 200
    assert b"Alliance Party Maker" in page.data
    assert page.data.count(b'class="alliance-party"') == 6
    assert page.data.count(b'class="party-slot"') == 36
    assert b"Add Second Alliance" in page.data
    assert b'"PLD": 75' in page.data and b'"WHM": 75' in page.data
    assert b"Alliance Builder" in page.data
    assert b"+ Load Saved Alliance" in page.data
    assert b'class="available-roster-table"' in page.data
    assert b'name="name" maxlength="80" required' in page.data
    assert b"Find Characters" not in page.data
    assert b"Character search" not in page.data
    assert b'class="roster-inline-filters"' in page.data
    assert b'id="alliance-rsvp-status"' in page.data
    assert b'id="alliance-assignment"' in page.data
    assert b'id="allow-alliance-duplicates"' in page.data
    assert b'id="alliance-character-search"' in page.data
    assert page.data.count(b'class="add-custom-slot"') == 36
    assert b'id="custom-alliance-dialog"' in page.data
    assert b"Alliance name <i>Required</i>" in page.data
    assert b'id="pick-event-date"' in page.data
    assert b'class="native-date-input"' in page.data
    assert b"Minimum level" not in page.data
    assert b"Level 75 Jobs" in page.data
    script = client.get("/static/alliance_builder.js")
    assert b"dragstart" in script.data and b"drag-over" in script.data
    assert b"selected-member" in script.data
    assert b"No RSVP - available roster jobs below" in script.data
    assert b"(!signedUp||signedUp.has" not in script.data


def test_event_admin_can_sync_events_from_alliance_builder(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "alliance-event-sync.db"),
        "SECRET_KEY": "test",
        "AUTH_DISABLED": False,
        "HOKUTEN_EVENT_BOT_API_URL": "https://events.example.test",
        "HOKUTEN_EVENT_BOT_API_TOKEN": "secret",
    })
    client = app.test_client()
    with client.session_transaction() as session:
        session["is_editor"] = True
        session["is_admin"] = True
        session["member_id"] = 1
        session["csrf_token"] = "token"

    page = client.get("/alliance-builder")

    assert page.status_code == 200
    actions = page.data.split(b'class="alliance-hero-actions"', 1)[1].split(b"</div>", 1)[0]
    assert b"+ Load Saved Alliance" in actions
    assert b"Sync Events &amp; Signups" in actions
    assert actions.index(b"+ Load Saved Alliance") < actions.index(b"Sync Events &amp; Signups")
    assert b'action="/endgame/events/sync-discord"' in actions
    assert b'name="next" value="alliance_builder"' in actions


def test_member_can_save_and_reopen_own_alliance_layout(app):
    maven, lion = add_roster(app)
    client = app.test_client()
    identify(client, maven)
    response = client.post("/alliance-builder/save", data={
        "name": "Dynamis - Xarcabard", "event_at": "2026-08-08T20:00",
        "notes": "Gather in Ru'Lude Gardens",
        "member_1_1": str(maven), "job_1_1": "PLD",
        "member_2_1": str(lion), "job_2_1": "WHM",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Saved alliance layout for Dynamis - Xarcabard" in response.data
    assert f'data-member="{maven}"'.encode() in response.data and b'data-job="PLD"' in response.data
    assert f'data-member="{lion}"'.encode() in response.data and b'data-job="WHM"' in response.data
    with app.app_context():
        database = sqlite3.connect(app.config["DATABASE"])
        assert database.execute("SELECT COUNT(*) FROM alliance_events").fetchone()[0] == 1
        assert database.execute("SELECT COUNT(*) FROM alliance_slots").fetchone()[0] == 2
        database.close()


def test_custom_character_assignment_is_saved_and_reopened(app):
    maven, _lion = add_roster(app)
    client = app.test_client()
    identify(client, maven)
    response = client.post("/alliance-builder/save", data={
        "name": "Guest Layout", "custom_name_3_6": "Guestplayer", "job_3_6": "BRD",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'data-custom-name="Guestplayer"' in response.data
    assert b'data-job="BRD"' in response.data
    with app.app_context():
        database = sqlite3.connect(app.config["DATABASE"])
        slot = database.execute(
            "SELECT member_id,custom_name,job FROM alliance_slots"
        ).fetchone()
        assert slot == (None, "Guestplayer", "BRD")
        database.close()


def test_second_alliance_slots_are_saved_and_reopened(app):
    maven, _lion = add_roster(app)
    client = app.test_client()
    identify(client, maven)
    response = client.post("/alliance-builder/save", data={
        "name": "Dynamis Second Alliance",
        "member_4_1": str(maven), "job_4_1": "PLD",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'id="second-alliance" open' in response.data
    with app.app_context():
        database = sqlite3.connect(app.config["DATABASE"])
        slot = database.execute(
            "SELECT party_number,slot_number,member_id,job FROM alliance_slots"
        ).fetchone()
        assert slot == (4, 1, maven, "PLD")
        database.close()


def test_alliance_save_rejects_duplicate_members_and_unrostered_jobs(app):
    maven, _lion = add_roster(app)
    client = app.test_client()
    identify(client, maven)
    duplicate = client.post("/alliance-builder/save", data={
        "name": "Duplicate Test",
        "member_1_1": str(maven), "job_1_1": "PLD",
        "member_2_1": str(maven), "job_2_1": "WAR",
    })
    assert duplicate.status_code == 400
    forged = client.post("/alliance-builder/save", data={
        "name": "Forged Job", "member_1_1": str(maven), "job_1_1": "WHM",
    })
    assert forged.status_code == 400


def test_alliance_two_can_allow_and_highlight_cross_alliance_duplicates(app):
    maven, _lion = add_roster(app)
    client = app.test_client()
    identify(client, maven)
    response = client.post("/alliance-builder/save", data={
        "name": "Two Run Event", "allow_second_alliance_duplicates": "1",
        "member_1_1": str(maven), "job_1_1": "PLD",
        "member_4_1": str(maven), "job_4_1": "PLD",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'id="allow-alliance-duplicates"' in response.data
    assert b'name="allow_second_alliance_duplicates" value="1" checked' in response.data
    with app.app_context():
        database = sqlite3.connect(app.config["DATABASE"])
        assert database.execute("SELECT allow_second_alliance_duplicates FROM alliance_events").fetchone()[0] == 1
        assert database.execute("SELECT COUNT(*) FROM alliance_slots WHERE member_id=?", (maven,)).fetchone()[0] == 2
        database.close()
    script = client.get("/static/alliance_builder.js").data
    assert b"cross-alliance-duplicate" in script
    assert b"alliance-rsvp-status" in script

    same_alliance = client.post("/alliance-builder/save", data={
        "name": "Invalid Same Run", "allow_second_alliance_duplicates": "1",
        "member_1_1": str(maven), "job_1_1": "PLD",
        "member_2_1": str(maven), "job_2_1": "PLD",
    })
    assert same_alliance.status_code == 400


def test_alliance_builder_requires_member_sign_in_not_administrator(tmp_path):
    secured_app = create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "secured.db"),
        "SECRET_KEY": "test", "AUTH_DISABLED": False,
    })
    client = secured_app.test_client()
    assert client.get("/alliance-builder").status_code == 302
    with client.session_transaction() as session:
        session["is_editor"] = True
        session["member_id"] = 1
    assert client.get("/alliance-builder").status_code == 200
    with client.session_transaction() as session:
        session.pop("member_id", None)
        session["is_admin"] = True
    assert client.get("/alliance-builder").status_code == 403


def test_saved_alliances_are_private_and_deletable_from_loader(app):
    maven, lion = add_roster(app)
    client = app.test_client()
    identify(client, maven)
    created = client.post("/alliance-builder/save", data={
        "name": "Maven's Layout", "member_1_1": str(maven), "job_1_1": "PLD",
    }, follow_redirects=False)
    event_id = int(created.location.split("event=")[-1])
    owner_page = client.get("/alliance-builder")
    assert b"Maven&#39;s Layout" in owner_page.data
    assert f'/alliance-builder/{event_id}/delete'.encode() in owner_page.data

    identify(client, lion)
    assert b"Maven&#39;s Layout" not in client.get("/alliance-builder").data
    assert client.get(f"/alliance-builder?event={event_id}").status_code == 404
    assert client.post(f"/alliance-builder/{event_id}/delete").status_code == 404

    identify(client, maven)
    deleted = client.post(f"/alliance-builder/{event_id}/delete", follow_redirects=True)
    assert deleted.status_code == 200
    assert b"Deleted alliance layout" in deleted.data
    with app.app_context():
        database = sqlite3.connect(app.config["DATABASE"])
        assert database.execute("SELECT COUNT(*) FROM alliance_events").fetchone()[0] == 0
        database.close()


def test_collaborative_link_supports_shared_edits_copy_revoke_and_conflict_protection(app):
    maven, lion = add_roster(app)
    client = app.test_client()
    identify(client, maven)
    created = client.post("/alliance-builder/save", data={
        "name": "Shared Dynamis", "member_1_1": str(maven), "job_1_1": "PLD",
    })
    event_id = int(created.location.split("event=")[-1])

    shared = client.post(f"/alliance-builder/{event_id}/share")
    assert shared.status_code == 302
    assert "/alliance-builder/shared/" in shared.location
    token = shared.location.rsplit("/", 1)[-1]
    owner_shared_page = client.get(shared.location)
    assert b"Shared layout is active" in owner_shared_page.data
    assert b"Copy Link" in owner_shared_page.data

    identify(client, lion)
    collaborator_page = client.get(shared.location)
    assert collaborator_page.status_code == 200
    assert b"Shared by Imaven" in collaborator_page.data
    assert b"Duplicate to My Layouts" in collaborator_page.data
    assert f'name="share_token" value="{token}"'.encode() in collaborator_page.data

    edited = client.post("/alliance-builder/save", data={
        "event_id": str(event_id), "version": "1", "share_token": token,
        "name": "Shared Dynamis - Updated",
        "member_2_1": str(lion), "job_2_1": "WHM",
    })
    assert edited.status_code == 302 and f"/shared/{token}" in edited.location

    stale = client.post("/alliance-builder/save", data={
        "event_id": str(event_id), "version": "1", "share_token": token,
        "name": "Stale overwrite",
    }, follow_redirects=True)
    assert b"changed after you opened it" in stale.data

    duplicated = client.post(f"/alliance-builder/shared/{token}/duplicate")
    assert duplicated.status_code == 302 and "event=" in duplicated.location
    with app.app_context():
        database = sqlite3.connect(app.config["DATABASE"])
        assert database.execute(
            "SELECT name,version FROM alliance_events WHERE id=?", (event_id,)
        ).fetchone() == ("Shared Dynamis - Updated", 2)
        assert database.execute(
            "SELECT COUNT(*) FROM alliance_events WHERE owner_member_id=?", (lion,)
        ).fetchone()[0] == 1
        assert database.execute(
            "SELECT COUNT(*) FROM alliance_change_log WHERE event_id=?", (event_id,)
        ).fetchone()[0] >= 3
        database.close()

    identify(client, maven)
    revoked = client.post(f"/alliance-builder/{event_id}/share/revoke")
    assert revoked.status_code == 302
    assert client.get(f"/alliance-builder/shared/{token}").status_code == 404


def test_shared_alliance_live_sync_tracks_presence_attribution_and_conflicts(app):
    maven, lion = add_roster(app)
    client = app.test_client()
    identify(client, maven)
    created = client.post("/alliance-builder/save", data={
        "name": "Live Dynamis", "member_1_1": str(maven), "job_1_1": "PLD",
    })
    event_id = int(created.location.split("event=")[-1])
    shared = client.post(f"/alliance-builder/{event_id}/share")
    token = shared.location.rsplit("/", 1)[-1]

    first = client.get(f"/alliance-builder/shared/{token}/live").get_json()
    assert first["version"] == 1
    assert first["active_editors"][0]["name"] == "Imaven"

    identify(client, lion)
    live_page = client.get(f"/alliance-builder/shared/{token}")
    assert b'"enabled": true' in live_page.data
    assert b'id="alliance-live-indicator"' in live_page.data

    update = client.post(
        f"/alliance-builder/shared/{token}/live",
        headers={"X-CSRF-Token": "test-token"},
        json={
            "version": 1,
            "slots": [
                {"party_number": 1, "slot_number": 1, "member_id": maven,
                 "custom_name": "", "job": "PLD"},
                {"party_number": 2, "slot_number": 1, "member_id": lion,
                 "custom_name": "", "job": "WHM"},
            ],
        },
    )
    assert update.status_code == 200
    payload = update.get_json()
    assert payload["version"] == 2
    changed = next(slot for slot in payload["slots"] if slot["party_number"] == 2)
    assert changed["updated_by"] == lion
    assert changed["updated_by_name"] == "Shiru"

    stale = client.post(
        f"/alliance-builder/shared/{token}/live",
        json={"version": 1, "slots": []},
    )
    assert stale.status_code == 409
    assert stale.get_json()["conflict"] is True
    assert stale.get_json()["version"] == 2

    identify(client, maven)
    presence = client.get(f"/alliance-builder/shared/{token}/live").get_json()
    assert {editor["name"] for editor in presence["active_editors"]} == {"Imaven", "Shiru"}
    with app.app_context():
        database = sqlite3.connect(app.config["DATABASE"])
        assert database.execute(
            "SELECT updated_by FROM alliance_slots WHERE event_id=? AND party_number=2",
            (event_id,),
        ).fetchone()[0] == lion
        assert database.execute(
            "SELECT COUNT(*) FROM alliance_change_log WHERE event_id=? AND action='Live party update'",
            (event_id,),
        ).fetchone()[0] == 1
        database.close()
