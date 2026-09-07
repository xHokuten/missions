import pytest
import json
import re
import sqlite3

import missions
from missions import MISSION_OPTIONS, create_app, mission_wiki_url


def test_mission_wiki_url_links_directly_and_removes_display_notes():
    assert mission_wiki_url("One to Be Feared") == "https://www.bg-wiki.com/ffxi/One_to_Be_Feared"
    assert mission_wiki_url("Garden of Antiquity (Chapter transition)") == "https://www.bg-wiki.com/ffxi/Garden_of_Antiquity"
    assert mission_wiki_url("Campaign complete") == ""


@pytest.fixture()
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db"), "SECRET_KEY": "test", "AUTH_DISABLED": True})
    return app.test_client()


def test_updates_require_shared_password(tmp_path):
    app = create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "auth.db"),
        "SECRET_KEY": "test", "EDIT_PASSWORD": "shell-secret",
    })
    client = app.test_client()
    response = client.get("/members/new")
    assert response.status_code == 302
    assert "/login?next=/members/new" in response.location

    client.get("/login")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    wrong = client.post("/login", data={"password": "wrong", "csrf_token": token})
    assert b"Incorrect linkshell password" in wrong.data
    signed_in = client.post("/login", data={
        "password": "shell-secret", "csrf_token": token, "next": "/members/new",
    })
    assert signed_in.status_code == 302
    assert signed_in.location == "/members/new"
    assert client.get("/members/new").status_code == 200


def test_login_asks_for_character_before_password(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "login-order.db"),
                      "SECRET_KEY": "test", "AUTH_DISABLED": False})
    page = app.test_client().get("/login").data
    assert page.index(b'name="member_id"') < page.index(b'name="password"')


def test_cop_chapters_six_and_seven_follow_horizon_mission_order():
    cop_missions = [mission for _chapter, entries in MISSION_OPTIONS["COP"] for mission, _ in entries]
    start = cop_missions.index("CoP 6-1 – For Whom the Verse Is Sung")
    assert cop_missions[start:start + 9] == [
        "CoP 6-1 – For Whom the Verse Is Sung",
        "CoP 6-2 – A Place to Return",
        "CoP 6-3 – More Questions Than Answers",
        "CoP 6-4 – One to Be Feared",
        "CoP 7-1 – Chains and Bonds",
        "CoP 7-2 – Flames in the Darkness",
        "CoP 7-3 – Fire in the Eyes of Men",
        "CoP 7-4 – Calm Before the Storm",
        "CoP 7-5 – The Warrior's Path",
    ]


def test_cop_chapter_four_and_five_follow_the_return_home_progression():
    cop_missions = [mission for _chapter, entries in MISSION_OPTIONS["COP"] for mission, _ in entries]
    start = cop_missions.index("CoP 4-4 – Slanderous Utterings")
    assert cop_missions[start:start + 8] == [
        "CoP 4-4 – Slanderous Utterings",
        "The Return Home",
        "CoP 5-1 – The Enduring Tumult of War",
        "CoP 5-2 – Desires of Emptiness",
        "CoP 5-3 – Three Paths",
        "Louverance's Path",
        "Tenzen's Path",
        "Ulmia's Path",
    ]

    assert missions.split_mission("COP", "Louverance's Path") == ("CoP 5-3", "Louverance's Path")


def test_header_uses_single_yellow_account_control(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "account-header.db"),
                      "SECRET_KEY": "test", "AUTH_DISABLED": False})
    client = app.test_client()
    signed_out = client.get("/")
    assert b'class="button account-button public-signin"' not in signed_out.data
    assert b'class="landing-discord-signin"' in signed_out.data
    assert b"Sign in with Discord</a>" in signed_out.data
    assert b"Sign in to update" not in signed_out.data
    assert b'class="site-nav"' not in signed_out.data
    assert b'class="brand"' not in signed_out.data
    assert signed_out.data.count(b'data-name="') == 13
    assert b'class="landing-script">Hokuten Knights' in signed_out.data
    assert b"public_landing.js" in signed_out.data
    assert b"Enter the Linkshell" not in signed_out.data
    assert b"public_landing_controls.css" in signed_out.data
    assert b"public_landing_alignment.css?v=3" in signed_out.data
    landing_script = client.get("/static/public_landing.js")
    assert b"audio.duration/scenes.length" in landing_script.data
    assert b'id="landing-audio"' in signed_out.data
    assert b'id="soundtrack-volume"' in signed_out.data
    assert b"We Depart For Distant Shores" in signed_out.data
    assert client.get("/static/landing/we-depart-for-distant-shores.mp3").status_code == 200

    with client.session_transaction() as session:
        session["is_editor"] = True
        session["member_id"] = 1
    signed_in = client.get("/")
    assert b"Sign Out (Imaven)" in signed_in.data
    assert b'href="https://www.paypal.com/ncp/payment/NML5WB6PTNTAE"' in signed_in.data
    assert b'class="button donate-button"' in signed_in.data
    assert b'target="_blank" rel="noopener noreferrer"' in signed_in.data
    assert b"HorizonXI Linkshell Progress" not in signed_in.data
    assert b"Add or Update Progress" in signed_in.data
    nav = signed_in.data.split(b'<nav class="site-nav"', 1)[1].split(b"</nav>", 1)[0]
    assert [nav.index(label) for label in (
        b"Requests", b"Missions", b"Loot Tables",
        b"Job Roster", b"Alliance Builder",
    )] == sorted(nav.index(label) for label in (
        b"Requests", b"Missions", b"Loot Tables",
        b"Job Roster", b"Alliance Builder",
    ))
    assert b"Help Requests" not in nav
    assert b"My Requests" not in nav
    assert b'class="nav-section-break"' not in nav
    assert b">Operations</span>" not in nav
    assert b">Members</a>" not in nav

    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    signed_out_again = client.post(
        "/logout", data={"csrf_token": csrf}, follow_redirects=True,
    )
    assert b'class="public-landing"' in signed_out_again.data
    assert b"Sign in with Discord</a>" in signed_out_again.data
    assert b"Add or Update Progress" not in signed_out_again.data
    assert b"You are signed out" not in signed_out_again.data


def test_post_rejects_missing_csrf_token(tmp_path):
    app = create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "csrf.db"),
        "SECRET_KEY": "test", "EDIT_PASSWORD": "shell-secret",
    })
    response = app.test_client().post("/login", data={"password": "shell-secret"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Your sign-in page expired" in response.data


def test_non_login_post_still_rejects_missing_csrf_token(tmp_path):
    app = create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "csrf-other.db"),
        "SECRET_KEY": "test", "EDIT_PASSWORD": "shell-secret",
    })
    assert app.test_client().post("/identity", data={"member_id": "1"}).status_code == 400


def test_roster_refresh_api_requires_machine_token_and_updates_only_valid_members(tmp_path):
    app = create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "refresh-api.db"),
        "SECRET_KEY": "test", "ROSTER_REFRESH_TOKEN": "daily-refresh-secret",
    })
    client = app.test_client()
    with app.app_context():
        database = missions.sqlite3.connect(app.config["DATABASE"])
        database.execute("INSERT INTO member_jobs(member_id,job,level) VALUES (1,'WAR',10)")
        database.commit()
        database.close()

    assert client.post("/api/job-roster/refresh", json={"players": {}}).status_code == 401
    response = client.post(
        "/api/job-roster/refresh",
        headers={"Authorization": "Bearer daily-refresh-secret"},
        json={"players": {
            "Imaven": {"WAR": 75, "PLD": 24},
            "NotRegistered": {"RDM": 75},
            "Vlathgar": {"RDM": 99},
        }},
    )
    assert response.status_code == 200
    assert response.get_json()["updated"] == 1
    assert set(response.get_json()["skipped"]) == {"NotRegistered", "Vlathgar"}
    with app.app_context():
        database = missions.sqlite3.connect(app.config["DATABASE"])
        assert database.execute(
            "SELECT job,level FROM member_jobs WHERE member_id=1 ORDER BY job"
        ).fetchall() == [("PLD", 24), ("WAR", 75)]
        database.close()


def test_roster_member_feed_returns_every_registered_character(tmp_path):
    app = create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "member-feed.db"),
        "SECRET_KEY": "test",
    })
    response = app.test_client().get("/api/job-roster/members")
    assert response.status_code == 200
    assert "Imaven" in response.get_json()["members"]
    assert response.headers["Cache-Control"] == "no-store"


def test_empty_board_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Chains of Promathia" in response.data
    assert b"Rise of the Zilart" in response.data
    assert b"Not selected" in response.data


def test_ifrit_map_name_uses_calibrated_zone_id(client):
    response = client.get("/api/map-assets?zone=Ifrits%20Cauldron")
    assert response.status_code == 200
    maps = response.get_json()["maps"]
    assert len(maps) == 8
    assert maps[0]["url"].startswith("/calibrated-map-assets/205/")


def test_add_and_filter_member(client):
    response = client.post("/members/new", data={
        "name": "Aldo", "discord_name": "aldo", "timezone": "Central",
        "availability": "Friday evenings", "job_PLD": "75", "job_WHM": "60",
        "COP_chapter": "Chapter 2", "COP_mission": "The Mothercrystals",
        "COP_status": "Ready for help", "COP_details": "Promyvion-Mea",
        "ZILART_chapter": "ZM4", "ZILART_mission": "The Temple of Uggalepih",
        "ZILART_status": "In progress", "ZILART_details": "Need keys",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Saved Aldo" in response.data
    assert b"The Mothercrystals" in response.data
    assert b"PLD 75" in response.data
    assert b"The Temple of Uggalepih" in response.data

    filtered = client.get("/?campaign=COP&job=PLD&status=Ready+for+help")
    assert b"The Mothercrystals" in filtered.data
    assert b"Need keys" not in filtered.data


def test_requires_a_job(client):
    response = client.post("/members/new", data={"name": "Lion"})
    assert response.status_code == 200
    assert b"Add at least one job" in response.data


def test_horizon_job_lookup(client, monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({
                "name": "Akaldok",
                "jobs": {"WAR": 37, "RDM": 75, "NIN": 75, "SMN": 0},
            }).encode()

    monkeypatch.setattr(missions, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    response = client.get("/api/horizon-player/Akaldok")
    assert response.status_code == 200
    assert response.json == {"name": "Akaldok", "jobs": {"WAR": 37, "RDM": 75, "NIN": 75}}


def test_horizon_lookup_rejects_invalid_name(client):
    response = client.get("/api/horizon-player/not-a-name")
    assert response.status_code == 400


def test_mission_form_uses_grouped_dropdowns(client):
    response = client.get("/members/new")
    assert response.status_code == 200
    assert b"Look up jobs" not in response.data
    assert b"Enter your current job levels" in response.data
    assert b'optgroup label="Chapter 1' in response.data
    assert "CoP 1-3 – The Mothercrystals".encode() in response.data
    assert "ZM1 – The New Frontier".encode() in response.data
    assert "ZM14 – Ark Angels".encode() in response.data
    assert "ZM18 – The Last Verse".encode() in response.data
    assert b'data-chapter-input="COP"' in response.data
    cop_complete = response.data.index(b'value="Complete"', response.data.index(b'data-mission-select="COP"'))
    assert cop_complete > response.data.index("CoP 8-5".encode())


def test_progress_form_selects_registered_member_and_populates_jobs(client):
    client.post("/members/new", data={
        "name": "Prishe", "job_WHM": "75", "job_BRD": "60",
    })

    chooser = client.get("/members/new")
    assert b'id="progress-member-select"' in chooser.data
    assert b'>Prishe</option>' in chooser.data

    member_id = re.search(rb'/members/(\d+)/edit[^>]*>Prishe</option>', chooser.data).group(1).decode()
    edit_form = client.get(f"/members/{member_id}/edit")
    assert b'value="75" placeholder=' in edit_form.data
    assert b'value="60" placeholder=' in edit_form.data
    assert edit_form.data.count(b'name="bring_jobs"') == len(missions.JOBS)
    assert len(re.findall(rb'name="bring_jobs" value="[A-Z]+" checked', edit_form.data)) == 2


def test_mission_jobs_to_bring_persist_through_a_roster_refresh(tmp_path):
    app = create_app({
        "TESTING": True, "DATABASE": str(tmp_path / "mission-jobs.db"), "SECRET_KEY": "test",
        "AUTH_DISABLED": True, "ROSTER_REFRESH_TOKEN": "daily-refresh-secret",
    })
    client = app.test_client()
    client.post("/members/new", data={
        "name": "Prishe", "job_WHM": "75", "job_BRD": "60", "job_BLM": "50",
        "bring_jobs_present": "1", "bring_jobs": ["WHM", "BRD"],
    })
    member_id = sqlite3.connect(client.application.config["DATABASE"]).execute(
        "SELECT id FROM members WHERE name='Prishe'"
    ).fetchone()[0]
    refreshed = client.post("/api/job-roster/refresh", json={
        "players": {"Prishe": {"WHM": 75, "BRD": 60, "BLM": 50}}
    }, headers={"Authorization": "Bearer daily-refresh-secret"})
    assert refreshed.status_code == 200
    database = sqlite3.connect(client.application.config["DATABASE"])
    assert database.execute(
        "SELECT job,bring FROM member_jobs WHERE member_id=? ORDER BY job", (member_id,)
    ).fetchall() == [("BLM", 0), ("BRD", 1), ("WHM", 1)]
    database.close()


def test_dashboard_groups_members_by_mission(client):
    client.post("/members/new", data={
        "name": "Tarantula", "job_NIN": "75", "job_WAR": "37",
        "COP_chapter": "Chapter 1 – Ancient Flames Beckon",
        "COP_mission": "CoP 1-3 – The Mothercrystals",
        "COP_status": "Ready for help",
        "COP_details": "Cutscenes done",
        "ZILART_mission": "ZM14 – Ark Angels", "ZILART_chapter": "ZM14",
        "ZILART_status": "In progress",
    })
    response = client.get("/")
    assert b'<table class="progress-table">' in response.data
    assert b"CoP 1-3" in response.data
    assert b"Tarantula" in response.data
    assert b"Jobs:</b> NIN 75, WAR 37" in response.data
    assert b"Status:</b> Ready for help" in response.data
    assert b"Extra notes:</b> Cutscenes done" in response.data
    assert b'class="availability"' in response.data
    assert b"ZM14" in response.data


def test_old_zilart_numbering_is_migrated_without_losing_progress(tmp_path):
    database = str(tmp_path / "migration.db")
    config = {"TESTING": True, "DATABASE": database, "SECRET_KEY": "test", "AUTH_DISABLED": True}
    first_client = create_app(config).test_client()
    first_client.post("/members/new", data={
        "name": "Lion", "job_THF": "75", "COP_status": "Not started",
        "ZILART_mission": "ZM9 – Ark Angels", "ZILART_chapter": "ZM9",
        "ZILART_status": "Ready for help",
    })

    migrated_client = create_app(config).test_client()
    response = migrated_client.get("/")
    assert b"ZM14" in response.data
    assert b"Ark Angels" in response.data
    assert b">Lion<span" in response.data


def test_add_progress_updates_an_existing_character(client):
    client.post("/members/new", data={
        "name": "Lion", "job_WHM": "50",
        "COP_mission": "CoP 1-2 – Below the Arks",
        "COP_chapter": "Chapter 1 – Ancient Flames Beckon",
        "COP_status": "In progress",
        "ZILART_status": "Not started",
    })
    response = client.post("/members/new", data={
        "name": "lion", "job_WHM": "60", "job_BLM": "40",
        "COP_mission": "CoP 1-3 – The Mothercrystals",
        "COP_chapter": "Chapter 1 – Ancient Flames Beckon",
        "COP_status": "Ready for help",
        "ZILART_status": "Not started",
    }, follow_redirects=True)
    assert response.status_code == 200
    # One appearance in each campaign table, not duplicate roster records.
    assert response.data.count(b'>lion<span class="member-tooltip">') == 6
    assert b"CoP 1-3" in response.data
    assert b"BLM 40, WHM 60" in response.data
    assert b"CoP 1-2" in response.data  # The standard empty mission row still exists.


def test_complete_selection_places_member_in_final_helper_row(client):
    response = client.post("/members/new", data={
        "name": "Prishe", "job_MNK": "75",
        "COP_mission": "Complete", "COP_chapter": "Complete",
        "COP_status": "In progress", "ZILART_status": "Not started",
    }, follow_redirects=True)
    assert b"Campaign complete" in response.data
    assert b">Prishe<span" in response.data
    assert b"Status:</b> Complete" in response.data


def test_summary_counts_dreamlands_and_each_campaign_clear(client):
    client.post("/members/new", data={
        "name": "Tenzen", "job_SAM": "75",
        "COP_mission": "CoP 4-1 – Sheltering Doubt", "COP_status": "In progress",
        "ZILART_mission": "Complete", "ZILART_status": "Complete",
    })
    client.post("/members/new", data={
        "name": "Ulmia", "job_BRD": "75",
        "COP_mission": "Complete", "COP_status": "Complete",
        "ZILART_status": "Not started",
    })
    response = client.get("/")
    assert b"2</strong><span>Dynamis Dreamlands" in response.data
    assert b"1</strong><span>CoP cleared" in response.data
    assert b"1</strong><span>ZM cleared" in response.data


def test_dashboard_includes_toau_and_three_city_mission_tables(client):
    response = client.get("/")
    for heading in ("Treasures of Aht Urhgan", "San d&#39;Oria Missions",
                    "Bastok Missions", "Windurst Missions"):
        assert heading.encode() in response.data
    assert b"ToAU 01" in response.data
    assert b"San d&#39;Oria 1-1" in response.data
    assert b"Bastok 1-1" in response.data
    assert b"Windurst 1-1" in response.data
    headings = [response.data.index(name) for name in (
        b"Rise of the Zilart", b"Chains of Promathia", b"Treasures of Aht Urhgan",
        b"Windurst Missions", b"San d&#39;Oria Missions", b"Bastok Missions",
    )]
    assert headings == sorted(headings)
