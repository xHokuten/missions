import json
import sqlite3
from pathlib import Path

from build_blue_spell_farming import (
    HORIZON_SPELL_CARD_SOURCE, blue_magic_cap, build, parse_blue_metadata, parse_combat_metadata,
    parse_magic_element, parse_physical_damage_type, parse_spell_description, parse_spell_effects,
)
from missions import blue_magic_point_limit, create_app


def test_horizon_blue_magic_point_limits_include_learned_spell_bonus():
    assert blue_magic_point_limit(64, 50) == 40
    assert blue_magic_point_limit(64, 51) == 41
    assert blue_magic_point_limit(64, 60) == 41
    assert blue_magic_point_limit(64, 61) == 42
    assert blue_magic_point_limit(75, 91) == 50


def test_blue_magic_skill_threshold_uses_level_75_cap():
    assert blue_magic_cap(1) == 6
    assert blue_magic_cap(50) == 153
    assert blue_magic_cap(70) == 248
    assert blue_magic_cap(75) == 276


def test_catalog_excludes_post_toau_zones_and_derives_minimum_skill():
    payload = build([
        {"spell_level": 75, "name": "Vertical Cleave", "monster_name": "Euvhi",
         "zone": "Al'Taieu", "min_level": "74", "max_level": "76", "link": ""},
        {"spell_level": 61, "name": "Bad Breath", "monster_name": "Morbol",
         "zone": "Abyssea - La Theine", "min_level": "80", "max_level": "82", "link": ""},
    ])
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["minimum_skill"] == 247


def test_horizon_spell_cards_override_retail_blue_magic_metadata():
    metadata = {
        "blood saber": {"set_points": 2, "set_stats": ["HP-5", "MP+5"],
                        "trait": None, "trait_weight": 0},
        "geist wall": {"set_points": 3, "set_stats": ["HP-5", "MP+10"],
                       "trait": None, "trait_weight": 0},
        "occultation": {"set_points": 3, "set_stats": ["VIT+2"],
                        "trait": None, "trait_weight": 0},
    }
    payload = build([
        {"spell_level": 48, "name": "Blood Saber", "monster_name": "Skeleton",
         "zone": "Gusgen Mines", "min_level": "20", "max_level": "24"},
        {"spell_level": 46, "name": "Geist Wall", "monster_name": "Lizard",
         "zone": "Yhoator Jungle", "min_level": "30", "max_level": "34"},
        {"spell_level": 88, "name": "Occultation", "monster_name": "Seether",
         "zone": "Promyvion - Dem", "min_level": "31", "max_level": "38"},
    ], metadata)
    spells = {row["spell"]: row for row in payload["rows"]}
    assert spells["Blood Saber"]["set_points"] == 3
    assert spells["Blood Saber"]["trait"] == "Auto Refresh"
    assert spells["Blood Saber"]["trait_weight"] == 4
    assert spells["Geist Wall"]["trait"] == "Auto Refresh"
    assert spells["Geist Wall"]["trait_weight"] == 4
    assert spells["Occultation"]["spell_level"] == 38
    assert spells["Occultation"]["trait"] == "Evasion Bonus"
    assert payload["horizon_spell_card_source"] == HORIZON_SPELL_CARD_SOURCE


def test_promyvion_vahzl_horizon_spells_are_kept_with_their_learning_targets():
    metadata = {
        "quadratic continuum": {"set_points": 4, "set_stats": ["DEX+3", "CHR-2"],
                                "trait": "Dual Wield", "trait_weight": 1},
        "winds of promyvion": {"set_points": 5, "set_stats": ["MND+3", "CHR-2"],
                                "trait": "Auto Refresh", "trait_weight": 4},
    }
    payload = build([
        {"spell_level": 89, "name": "Quadratic Continuum", "monster_name": "Gorger",
         "zone": "Promyvion - Vahzl", "min_level": "52", "max_level": "60"},
        {"spell_level": 89, "name": "Winds of Promyvion", "monster_name": "Thinker",
         "zone": "Promyvion - Vahzl", "min_level": "52", "max_level": "60"},
    ], metadata)
    spells = {row["spell"]: row for row in payload["rows"]}
    assert spells["Quadratic Continuum"]["spell_level"] == 54
    assert spells["Quadratic Continuum"]["trait"] == "Defense Bonus"
    assert spells["Quadratic Continuum"]["monster"] == "Gorger"
    assert spells["Winds of Promyvion"]["spell_level"] == 56
    assert spells["Winds of Promyvion"]["monster"] == "Thinker"
    assert spells["Winds of Promyvion"]["zone"] == "Promyvion - Vahzl"


def test_blue_metadata_parser_adds_set_cost_stats_and_trait():
    spell_list = (
        "INSERT INTO `blue_spell_list` VALUES "
        "(524,426,2,6,1,0,0,0,NULL); -- Sandspin"
    )
    spell_mods = (
        "INSERT INTO `blue_spell_mods` VALUES (524,12,1); -- VIT+1\n"
        "INSERT INTO `blue_spell_mods` VALUES (524,13,-1); -- MND-1"
    )
    traits = (
        "INSERT INTO `blue_traits` VALUES (6,2,30,28,10,1,0); "
        "-- Magic Attack Bonus (1)"
    )
    metadata = parse_blue_metadata(spell_list, spell_mods, traits)
    assert metadata["sandspin"] == {
        "set_points": 2,
        "set_stats": ["VIT+1", "MND-1"],
        "trait": "Magic Attack Bonus",
        "trait_weight": 1,
    }


def test_combat_metadata_parser_distinguishes_damage_type_and_wsc():
    physical = """-- Spell Type: Physical (Blunt)
params.str_wsc = 0.0
params.chr_wsc = 0.3
return xi.spells.blue.usePhysicalSpell(caster, target, spell, params)
"""
    assert parse_combat_metadata(physical) == (
        "Physical", ["STR (fSTR)", "CHR 30%"]
    )
    assert parse_physical_damage_type(physical) == "Blunt"
    assert parse_magic_element("-- Spell Type: Magical (Fire)") == "Fire"
    assert parse_magic_element("-- Spell Type: Magical (Lightning)") == "Lightning"
    assert parse_magic_element("-- Spell Type: Magical (Breath)") is None


def test_spell_description_uses_effect_summary_from_script_header():
    script = """-----------------------------------
-- Spell: Head Butt
-- Damage varies with TP. Additional effect: \"Stun\"
-- Spell cost: 12 MP
-- Monster Type: Beastmen
-----------------------------------
"""
    assert parse_spell_description(script) == 'Damage varies with TP. Additional effect: "Stun"'
    assert parse_spell_effects('Damage varies with TP. Additional effect: "Stun"') == ["Stun"]
    assert parse_spell_effects("Steals an enemy's HP. Ineffective against undead") == ["HP Drain"]
    magical = """params.attribute = xi.mod.INT
params.int_wsc = 0.2
return xi.spells.blue.useMagicalSpell(caster, target, spell, params)
"""
    assert parse_combat_metadata(magical) == ("Magical", ["INT", "INT 20%"])

    physical_effect = """params.attribute = xi.mod.INT
params.vit_wsc = 0.5
return xi.spells.blue.usePhysicalSpell(caster, target, spell, params)
"""
    assert parse_combat_metadata(physical_effect) == (
        "Physical", ["STR (fSTR)", "INT (effect accuracy)", "VIT 50%"]
    )

    healing = """-- Spell: Healing Breeze
-- Spell Type: Magical (Wind)
return xi.spells.blue.useCuringSpell(caster, target, spell, params)
"""
    assert parse_combat_metadata(healing) == (
        "Magical", ["MND x3", "VIT x1", "3 x floor(Blue Magic Skill / 5)"]
    )


def test_combat_metadata_parser_covers_non_nuke_magic_formulas():
    assert parse_combat_metadata("""-- Spell: Bad Breath
return xi.spells.blue.useBreathSpell(caster, target, spell, params)
""") == ("Magical (Breath)", ["Current HP", "Main Level"])
    assert parse_combat_metadata("""-- Spell: Sheep Song
return xi.spells.blue.useEnfeeblingSpell(caster, target, spell, params)
""") == (
        "Magical",
        ["Fixed potency", "INT (accuracy)", "Blue Magic Skill (accuracy)"],
    )
    assert parse_combat_metadata("""-- Spell: Metallic Body
local blueSkill = caster:getSkillLevel(xi.skill.BLUE_MAGIC)
""") == ("Support", ["Blue Magic Skill"])
    assert parse_combat_metadata("""-- Spell: Cocoon
local power = 50
""") == ("Support", ["Fixed potency"])
    assert parse_combat_metadata("""-- Spell: 1000 Needles
params.int_wsc = 2.0
""") == (
        "Magical",
        ["Fixed 1000 damage", "INT (accuracy)", "Blue Magic Skill (accuracy)"],
    )


def test_spell_farming_page_and_generated_catalog(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "spell.db"),
                      "SECRET_KEY": "test", "AUTH_DISABLED": True})
    client = app.test_client()
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["is_editor"] = True
    page = client.get("/spell-farming")
    assert page.status_code == 200
    assert b"Spell Farming" in page.data
    assert b'id="spell-current-skill"' in page.data
    assert b"<b>Spell Farming</b>" in page.data
    assert b"My Learned Spells" in page.data
    assert b"Changes automatically save to Imaven" in page.data

    payload = json.loads(Path("static/blue_spell_farming.json").read_text(encoding="utf-8"))
    assert len(payload["rows"]) > 500
    assert len({row["spell"] for row in payload["rows"]}) == 105
    assert all(row["spell_level"] <= 75 for row in payload["rows"])
    assert all(row["set_points"] is not None for row in payload["rows"])
    foot_kick = next(row for row in payload["rows"] if row["spell"] == "Foot Kick")
    assert foot_kick["set_points"] == 2
    assert foot_kick["set_stats"] == ["AGI+1"]
    assert foot_kick["trait"] == "Lizard Killer"
    blood_saber = next(row for row in payload["rows"] if row["spell"] == "Blood Saber")
    assert blood_saber["set_points"] == 3
    assert blood_saber["trait"] == "Auto Refresh"
    assert blood_saber["trait_weight"] == 4
    assert {"Auroral Drape", "Empty Thrash", "Occultation"} <= {
        row["spell"] for row in payload["rows"]
    }
    assert {"Quadratic Continuum", "Winds of Promyvion"} <= {
        row["spell"] for row in payload["rows"]
    }
    head_butt = next(row for row in payload["rows"] if row["spell"] == "Head Butt")
    assert "Stun" in head_butt["description"]
    assert head_butt["effects"] == ["Stun"]
    bomb_toss = next(row for row in payload["rows"] if row["spell"] == "Bomb Toss")
    assert bomb_toss["spell_type"] == "Magical"
    assert bomb_toss["element"] == "Fire"
    assert not any("Abyssea" in row["zone"] or " (S)" in row["zone"]
                   for row in payload["rows"])


def test_member_can_save_and_reopen_learned_spells(tmp_path):
    database_path = tmp_path / "learned.db"
    app = create_app({"TESTING": True, "DATABASE": str(database_path),
                      "SECRET_KEY": "test", "AUTH_DISABLED": True})
    client = app.test_client()
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["is_editor"] = True
    response = client.post("/spell-farming/ownership", data={
        "spells": ["Pollen", "Head Butt"],
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Saved 2 learned Blue Magic spells" in response.data
    assert b'window.LEARNED_BLUE_SPELLS=["Head Butt", "Pollen"]' in response.data
    database = sqlite3.connect(database_path)
    assert database.execute(
        "SELECT spell FROM blue_spell_ownership ORDER BY spell"
    ).fetchall() == [("Head Butt",), ("Pollen",)]
    database.close()


def test_spell_ownership_rejects_unknown_spells(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "invalid.db"),
                      "SECRET_KEY": "test", "AUTH_DISABLED": True})
    client = app.test_client()
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["is_editor"] = True
    assert client.post("/spell-farming/ownership", data={"spells": "Meteor II"}).status_code == 400


def test_learned_spells_are_isolated_to_signed_in_character(tmp_path):
    database_path = tmp_path / "per-member.db"
    app = create_app({"TESTING": True, "DATABASE": str(database_path),
                      "SECRET_KEY": "test", "AUTH_DISABLED": True})
    client = app.test_client()
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["is_editor"] = True
    client.post("/spell-farming/ownership", data={"spells": ["Pollen", "Head Butt"]})

    with client.session_transaction() as session:
        session["member_id"] = 2
    second_member_page = client.get("/spell-farming")
    assert b"Changes automatically save to Sexualpotato" in second_member_page.data
    assert b"window.LEARNED_BLUE_SPELLS=[]" in second_member_page.data

    client.post("/spell-farming/ownership", data={"spells": "Cocoon"})
    database = sqlite3.connect(database_path)
    ownership = database.execute(
        "SELECT member_id,spell FROM blue_spell_ownership ORDER BY member_id,spell"
    ).fetchall()
    database.close()
    assert ownership == [(1, "Head Butt"), (1, "Pollen"), (2, "Cocoon")]


def test_spellbook_saves_a_private_named_template(tmp_path):
    database_path = tmp_path / "spellbook.db"
    app = create_app({"TESTING": True, "DATABASE": str(database_path),
                      "SECRET_KEY": "test", "AUTH_DISABLED": True})
    client = app.test_client()
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["is_editor"] = True
    response = client.post("/blue-mage-tools/templates", data={
        "name": "Nyzul Utility", "blue_level": "75",
        "spells": ["Head Butt", "Cocoon"],
    })
    assert response.status_code == 302
    client.get(response.headers["Location"])
    with client.session_transaction() as session:
        session["member_id"] = 2
    page = client.get("/spell-farming?view=spellbook")
    assert page.status_code == 200
    assert b"Nyzul Utility" not in page.data
    assert b"Share with the linkshell" not in page.data
    assert b"Save This Spell Book" in page.data
    assert b'id="trait-priority"' in page.data
    assert b'id="book-skillchain-filter"' in page.data
    assert b'id="book-damage-filter"' in page.data
    assert b'id="goal-skillchains"' not in page.data
    assert b'id="goal-damage-types"' not in page.data
    assert b'id="clear-goals"' in page.data
    assert b'class="spellbook-three-column"' in page.data
    assert b'id="spell-picker-modal"' in page.data
    assert b'id="spell-detail-modal"' in page.data
    builder_script = client.get("/static/blue_spellbook.js").data
    assert b'goal-effects' in builder_script
    assert b'HP Drain (Drain)' in builder_script
    assert b'active-effects' in builder_script
    assert b'effectTooltip(spell)' in builder_script
    assert b'Additional Effect / Spell Equivalent' in builder_script
    assert b'book-skillchain-element-filter' in builder_script
    assert b'spellbook-right-rail' in builder_script
    assert b'Chain Affinity Skillchains &amp; Damage' not in builder_script
    assert b'Self Skillchain &amp; Burst Planner' in builder_script
    assert b'book-skillchain-filter' in builder_script
    assert b'goal-damage-types' not in builder_script
    assert b'skillchain_catalog.json' in builder_script
    assert b'event.preventDefault()' in builder_script
    assert b'equipped.delete(remove.dataset.remove)' in builder_script
    assert builder_script.index(b'if (remove)') < builder_script.index(b'const view =')
    assert b'learned.size} learned' in builder_script
    farming_script = client.get("/static/spell_farming.js").data
    assert b'if (!hasUnsavedChanges) return' in farming_script
    assert b'await saveLearned(++saveVersion)' in farming_script


def test_spellbook_rejects_level_invalid_template(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "invalid-book.db"),
                      "SECRET_KEY": "test", "AUTH_DISABLED": True})
    client = app.test_client()
    with client.session_transaction() as session:
        session["member_id"] = 1
        session["is_editor"] = True
    response = client.post("/blue-mage-tools/templates", data={
        "name": "Too Early", "blue_level": "10", "spells": ["Head Butt"],
    })
    assert response.status_code == 400
