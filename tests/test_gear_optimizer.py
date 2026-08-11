import sqlite3
import json
from pathlib import Path

import pytest
import missions
from build_gear_catalog import (
    build as build_catalog,
    lsb_item_latent_stats,
    lsb_item_stats,
    parse_level_scaling,
)
from missions import create_app, normalize_horizon_item, parse_gear_stats


def gear_app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "gear.db"),
        "SECRET_KEY": "test",
        "AUTH_DISABLED": True,
    })


def sign_in(client, member_id=1):
    with client.session_transaction() as session:
        session["member_id"] = member_id
        session["is_editor"] = True


def horizon_item(item_id=13014, name="Leaping Boots", key="leaping_boots"):
    return {
        "id": item_id,
        "key": key,
        "name": name,
        "desc": "DEF:3 DEX+3 AGI+3",
        "sprite": {
            "name": name,
            "description": "DEF:3 DEX+3 AGI+3",
            "jobs": "WAR/RDM/THF",
            "level": 7,
            "slot": "Feet",
            "weaponType": "",
            "rare": True,
            "ex": False,
        },
    }


def test_parse_gear_stats_ignores_conditional_suffixes():
    stats = parse_gear_stats(
        "DEF:12 STR+3 DEX-1 Accuracy+5 Haste+2% Latent effect: Attack+20"
    )
    assert stats == {"DEF": 12, "STR": 3, "DEX": -1, "Accuracy": 5, "Haste": 2}


def test_parse_gear_stats_supports_elemental_resistance():
    assert parse_gear_stats("Lightning Resistance+7 Water Resistance-2 Fire -3 Dark +4") == {
        "Lightning Resistance": 7, "Water Resistance": -2,
        "Fire Resistance": -3, "Dark Resistance": 4,
    }


def test_parse_gear_stats_supports_quoted_combat_stats():
    assert parse_gear_stats(
        '"Double Attack"+2% "Triple Attack"+1% '
        '"Magic Def. Bonus"+3 "Cure" potency +10% Weapon Skill Accuracy+5'
    ) == {
        "Double Attack": 2,
        "Triple Attack": 1,
        "Magic Defense Bonus": 3,
        "Cure Potency": 10,
        "Weapon Skill Accuracy": 5,
    }


def test_parse_gear_stats_supports_abbreviated_magic_attack_bonus():
    assert parse_gear_stats('"Magic Atk. Bonus"+7') == {"Magic Attack Bonus": 7}


def test_lsb_item_stats_supplies_hidden_numeric_effect_values():
    stats = lsb_item_stats(
        "INSERT INTO `item_mods` VALUES (14813,288,5);\n"
        "INSERT INTO `item_mods` VALUES (14813,369,1);\n"
        "INSERT INTO `item_mods` VALUES (14813,370,2);\n"
        "INSERT INTO `item_mods` VALUES (14813,374,10);\n"
        "INSERT INTO `item_mods` VALUES (14813,48,7);"
    )
    assert stats[14813] == {
        "Double Attack": 5,
        "Refresh": 1,
        "Regen": 2,
        "Cure Potency": 10,
        "Weapon Skill Accuracy": 7,
    }


def test_lsb_magic_attack_bonus_and_latents_are_searchable():
    direct = lsb_item_stats("INSERT INTO `item_mods` VALUES (14808,28,7);")
    latent = lsb_item_latent_stats(
        "INSERT INTO `item_latents` VALUES (13289,28,10,2,76);\n"
        "INSERT INTO `item_latents` VALUES (13145,28,8,4,51);"
    )
    assert direct[14808] == {"Magic Attack Bonus": 7}
    assert latent[13289] == {"Magic Attack Bonus": 10}
    assert latent[13145] == {"Magic Attack Bonus": 8}


def test_parse_level_scaling_handles_promathia_rings():
    assert parse_level_scaling('STR+2～5 DEX+2～5 "Store TP"+5', 30) == {
        "STR": {"min": 2, "max": 5, "min_level": 30, "max_level": 75, "tier_levels": 15},
        "DEX": {"min": 2, "max": 5, "min_level": 30, "max_level": 75, "tier_levels": 15},
    }


def test_catalog_builds_job_race_slot_and_resistance_filters():
    items = (
        '[13522] = {id=13522,en="Storm Ring",category="Armor",flags=0,'
        'jobs=8388606,level=14,races=510,slots=24576,type=5},\n'
    )
    descriptions = '[13522] = {id=13522,en="STR+2 \\ue004+7"},\n'.replace("\\ue004", "\ue004")
    payload = build_catalog(items, descriptions, {13522: "storm_ring"})
    item = payload["rows"][0]
    assert item["item_key"] == "storm_ring"
    assert item["slots"] == ["Ring"]
    assert item["races"] == [
        "Hume Male", "Hume Female", "Elvaan Male", "Elvaan Female",
        "Tarutaru Male", "Tarutaru Female", "Mithra", "Galka",
    ]
    assert item["stats"]["Lightning Resistance"] == 7
    assert item["ah_category"] == "rings"
    assert item["rare"] is False
    assert item["ex"] is False


def test_catalog_decodes_rare_and_ex_item_flags():
    items = (
        '[13014] = {id=13014,en="Leaping Boots",category="Armor",flags=34820,'
        'jobs=8388606,level=7,races=510,slots=256,type=5},\n'
        '[13939] = {id=13939,en="Optical Hat",category="Armor",flags=63572,'
        'jobs=8388606,level=70,races=510,slots=16,type=5},\n'
    )
    descriptions = (
        '[13014] = {id=13014,en="DEF:3"},\n'
        '[13939] = {id=13939,en="Accuracy+10"},\n'
    )
    rows = {item["name"]: item for item in build_catalog(items, descriptions, {}).get("rows", [])}
    assert rows["Leaping Boots"]["rare"] is True
    assert rows["Leaping Boots"]["ex"] is False
    assert rows["Optical Hat"]["rare"] is True
    assert rows["Optical Hat"]["ex"] is True


def test_catalog_assigns_psxi_auction_house_categories():
    items = (
        '[18254] = {id=18254,en="Tiphia Sting",category="Weapon",flags=34820,'
        'jobs=8388606,level=58,races=510,skill=0,slots=8,type=4},\n'
        '[17440] = {id=17440,en="Kraken Club",category="Weapon",flags=34816,'
        'jobs=65534,level=63,races=510,skill=11,slots=3,type=4},\n'
    )
    descriptions = (
        '[18254] = {id=18254,en="HP-25 Accuracy+2"},\n'
        '[17440] = {id=17440,en="Occasionally attacks 2 to 8 times"},\n'
    )
    rows = {item["name"]: item for item in build_catalog(items, descriptions, {}).get("rows", [])}
    assert rows["Tiphia Sting"]["ah_category"] == "ammo-misc"
    assert rows["Kraken Club"]["ah_category"] == "clubs"


def test_bundled_catalog_has_level_75_gear_and_searchable_stats():
    payload = json.loads(Path("static/gear_catalog.json").read_text(encoding="utf-8"))
    assert len(payload["rows"]) > 6000
    assert "Lightning Resistance" in payload["stats"]
    lightning_items = [
        item for item in payload["rows"]
        if item["stats"].get("Lightning Resistance")
    ]
    assert len(lightning_items) > 100
    assert all(1 <= item["level"] <= 75 for item in payload["rows"])
    assert all(item["jobs"] and item["races"] and item["slots"] for item in payload["rows"])


def test_normalize_horizon_item_uses_live_metadata():
    item = normalize_horizon_item(13014, horizon_item())
    assert item["name"] == "Leaping Boots"
    assert item["slot"] == "Feet"
    assert item["stats"] == {"DEF": 3, "DEX": 3, "AGI": 3}


def test_gear_optimizer_uses_catalog_without_loading_character_equipment(monkeypatch, tmp_path):
    app = gear_app(tmp_path)
    client = app.test_client()
    sign_in(client)
    monkeypatch.setattr(
        missions, "fetch_horizon_equipment",
        lambda _name: pytest.fail("live character equipment should not be loaded"),
    )
    monkeypatch.setattr(
        missions, "horizon_json",
        lambda _path, timeout=20: pytest.fail("live character profile should not be loaded"),
    )
    page = client.get("/gear-optimizer")
    assert page.status_code == 200
    assert b"Gear Optimizer" in page.data
    assert b"Equipment Setup" in page.data
    assert b"Import Gear" in page.data
    assert b'id="gear-import-collapse"' in page.data
    assert b"Copy XML" in page.data
    assert b"Copy Lua" in page.data
    assert b'id="gear-negative"' in page.data
    assert b">BLU</option>" in page.data
    assert b">PUP</option>" in page.data
    assert b'<option value="" selected disabled>Select One</option>' in page.data
    assert b'<option value="" selected>None</option>' in page.data
    assert b"gear_select.css?v=1" in page.data
    assert b"gear_optimizer.js?v=20" in page.data
    assert b"Owned Gear" not in page.data
    assert b"Add Equipment You Own" not in page.data
    assert b"Game-wide equipment index" in page.data
    assert b"Tarutaru Female" in page.data
    assert b"Gear Optimizer</a>" in page.data

    optimizer_script = client.get("/static/gear_optimizer.js").data
    assert b"if (item.rare) return false" in optimizer_script
    assert b"copiesAlreadyUsed < (ownedCounts.get" in optimizer_script
    assert b"Object.entries(item.level_scaling || {})" in optimizer_script


def test_owned_gear_is_saved_per_character(monkeypatch, tmp_path):
    app = gear_app(tmp_path)
    client = app.test_client()
    sign_in(client)
    monkeypatch.setattr(missions, "horizon_json", lambda _path, timeout=20: horizon_item())
    response = client.post(
        "/gear-optimizer/owned", data={"item_key": "leaping_boots"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    database = sqlite3.connect(app.config["DATABASE"])
    assert database.execute(
        "SELECT member_id,item_id,name FROM gear_ownership"
    ).fetchall() == [(1, 13014, "Leaping Boots")]
    database.close()

    sign_in(client, 2)
    page = client.get("/gear-optimizer")
    assert b'"owned_gear"' not in page.data


def test_imported_inventory_is_archived_per_character(tmp_path):
    app = gear_app(tmp_path)
    client = app.test_client()
    sign_in(client)
    response = client.post(
        "/api/gear/inventory",
        data={"inventory": json.dumps({"13014": 1, "13915": 2, "999999": 4})},
    )
    assert response.status_code == 200
    assert response.get_json() == {"saved": 2, "quantity": 3}
    database = sqlite3.connect(app.config["DATABASE"])
    assert database.execute(
        "SELECT item_id,quantity FROM gear_ownership WHERE member_id=1 ORDER BY item_id"
    ).fetchall() == [(13014, 1), (13915, 2)]
    database.close()
    page = client.get("/gear-optimizer")
    assert b'"13014": 1' in page.data or b'"13014":1' in page.data
    assert b"Import Successful" in page.data


def test_horizon_item_search_returns_equipment(monkeypatch, tmp_path):
    app = gear_app(tmp_path)
    client = app.test_client()
    sign_in(client)

    def fake_horizon(path, timeout=20):
        if path.startswith("items?"):
            return {"items": [{"id": 13014, "key": "leaping_boots"}]}
        return horizon_item()

    monkeypatch.setattr(missions, "horizon_json", fake_horizon)
    response = client.get("/api/gear/items?q=leaping")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["items"][0]["name"] == "Leaping Boots"
    assert payload["items"][0]["stats"]["DEX"] == 3
