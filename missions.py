import os
import sqlite3
import json
import hmac
import html
import re
import secrets
import calendar
import threading
from datetime import date, datetime, time, timedelta
from functools import lru_cache, wraps
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for


@lru_cache(maxsize=2)
def gear_required_levels(catalog_path):
    """Return item-name equipment levels from the generated Horizon gear catalog."""
    try:
        payload = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    levels = {
        str(item.get("name", "")): int(item.get("level") or 1)
        for item in payload.get("rows", []) if item.get("name")
    }
    # The UI uses readable full names for several abbreviated in-game DAT names.
    levels.update({
        "Crimson Finger Gauntlets": 73,
        "Shura Zunari Kabuto": 73,
        "Hecatomb Leggings": 73,
        "Genbu's Shield": 74,
        "Koenig Handschuhs": 73,
        "Temperance Torque": 73,
    })
    return levels


@lru_cache(maxsize=2)
def gear_catalog_by_name(catalog_path):
    try:
        rows = json.loads(Path(catalog_path).read_text(encoding="utf-8")).get("rows", [])
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return {str(item.get("name", "")).casefold(): item for item in rows if item.get("name")}


def load_local_env():
    """Load an ignored local .env file without overriding host-provided variables."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


load_local_env()


ENDGAME_PRIORITY_ITEMS = (
    {"area": "Sky", "source": "Byakko", "name": "Byakko's Haidate", "p1": ("NIN", "WAR", "SAM", "MNK"), "p2": ("BST", "BRD"), "p3": ()},
    {"area": "Sky", "source": "Byakko", "name": "Byakko's Axe", "p1": ("WAR",), "p2": (), "p3": ()},
    {"area": "Sky", "source": "Byakko", "name": "Hecatomb Mittens", "p1": ("THF", "WAR", "DRG"), "p2": ("DRK",), "p3": ("BRD",)},
    {"area": "Sky", "source": "Byakko", "name": "Shura Haidate", "p1": ("SAM", "PUP"), "p2": ("MNK", "NIN"), "p3": ()},
    {"area": "Sky", "source": "Byakko", "name": "Adaman Sollerets", "p1": ("WAR",), "p2": ("DRK", "BST"), "p3": ()},
    {"area": "Sky", "source": "Byakko", "name": "Zenith Crown", "p1": ("BLM",), "p2": ("RDM", "WHM", "SMN"), "p3": ("BRD",)},
    {"area": "Sky", "source": "Seiryu", "name": "Seiryu's Kote", "p1": ("RNG",), "p2": ("SAM", "NIN"), "p3": ()},
    {"area": "Sky", "source": "Seiryu", "name": "Seiryu's Sword", "p1": (), "p2": (), "p3": (), "freelot": True},
    {"area": "Sky", "source": "Seiryu", "name": "Crimson Finger Gauntlets", "p1": ("COR", "RNG"), "p2": ("RDM",), "p3": ("DRK",)},
    {"area": "Sky", "source": "Seiryu", "name": "Zenith Slacks", "p1": ("BLM", "WHM"), "p2": ("RDM", "SMN"), "p3": ("BRD",)},
    {"area": "Sky", "source": "Seiryu", "name": "Shura Zunari Kabuto", "p1": ("SAM", "PUP"), "p2": ("MNK", "NIN"), "p3": ()},
    {"area": "Sky", "source": "Seiryu", "name": "Koenig Schaller", "p1": ("PLD",), "p2": ("WAR",), "p3": ()},
    {"area": "Sky", "source": "Suzaku", "name": "Suzaku's Sune-Ate", "p1": ("BRD",), "p2": ("RNG", "SAM", "NIN"), "p3": ()},
    {"area": "Sky", "source": "Suzaku", "name": "Zenith Slacks", "p1": ("BLM", "WHM"), "p2": ("RDM", "SMN"), "p3": ("BRD",)},
    {"area": "Sky", "source": "Suzaku", "name": "Hecatomb Leggings", "p1": ("THF", "DRK", "WAR", "DRG"), "p2": ("BRD",), "p3": ()},
    {"area": "Sky", "source": "Suzaku", "name": "Shura Kote", "p1": ("MNK", "SAM", "NIN", "PUP"), "p2": (), "p3": ()},
    {"area": "Sky", "source": "Suzaku", "name": "Adaman Celata", "p1": ("WAR",), "p2": ("DRK", "BST"), "p3": ()},
    {"area": "Sky", "source": "Genbu", "name": "Genbu's Shield", "p1": ("RDM",), "p2": ("WHM", "BLU"), "p3": ()},
    {"area": "Sky", "source": "Genbu", "name": "Genbu's Kabuto", "p1": ("WAR", "MNK"), "p2": ("BRD",), "p3": ()},
    {"area": "Sky", "source": "Genbu", "name": "Zenith Mitts", "p1": ("BLM",), "p2": ("RDM",), "p3": ("SMN", "WHM")},
    {"area": "Sky", "source": "Genbu", "name": "Koenig Handschuhs", "p1": ("PLD",), "p2": ("WAR",), "p3": ()},
    {"area": "Sky", "source": "Genbu", "name": "Crimson Greaves", "p1": ("PLD",), "p2": ("RDM", "RNG"), "p3": ()},
    {"area": "Sky", "source": "Kirin", "name": "Kirin's Osode", "p1": ("RNG", "SAM"), "p2": ("WAR",), "p3": ("BRD", "NIN")},
    {"area": "Sky", "source": "Kirin", "name": "Kirin's Pole", "p1": ("BLM",), "p2": ("RDM",), "p3": ("MNK",)},
    {"area": "Sky", "source": "Kirin", "name": "Shura Togi", "p1": ("MNK", "PUP"), "p2": ("SAM",), "p3": ()},
    {"area": "Sky", "source": "Kirin", "name": "Hecatomb Harness", "p1": ("THF", "DRK", "DRG"), "p2": ("WAR",), "p3": ()},
    {"area": "Sky", "source": "Kirin", "name": "Crimson Cuisses", "p1": ("PLD",), "p2": ("RDM",), "p3": ("RNG", "COR")},
    {"area": "Sea", "source": "Jailer of Faith", "name": "Faith Torque", "p1": ("MNK",), "p2": ("RNG", "COR"), "p3": ("THF", "WHM")},
    {"area": "Sea", "source": "Jailer of Justice", "name": "Justice Torque", "p1": ("DRK", "SAM"), "p2": (), "p3": ()},
    {"area": "Sea", "source": "Jailer of Hope", "name": "Hope Torque", "p1": ("NIN", "RNG"), "p2": ("THF",), "p3": ("SAM",)},
    {"area": "Sea", "source": "Jailer of Prudence", "name": "Prudence Torque", "p1": ("DRK", "BLM"), "p2": ("RDM",), "p3": ("BLU",)},
    {"area": "Sea", "source": "Jailer of Fortitude", "name": "Fortitude Torque", "p1": ("WAR",), "p2": ("DRK", "BLU"), "p3": ("RDM",)},
    {"area": "Sea", "source": "Jailer of Temperance", "name": "Temperance Torque", "p1": ("BST",), "p2": ("WAR",), "p3": ()},
    {"area": "Sea", "source": "Jailer of Love", "name": "Love Torque", "p1": ("DRG", "THF"), "p2": ("COR",), "p3": ("BRD",)},
    {"area": "Sea", "source": "Jailer of Love", "name": "Novio Earring", "p1": ("BLM",), "p2": ("RDM", "BLU", "NIN", "COR"), "p3": ()},
    {"area": "Sea", "source": "Jailer of Love", "name": "Novia Earring", "p1": ("WHM",), "p2": ("PLD", "THF", "NIN"), "p3": ("RDM", "SMN")},
)

# Non-priority Sky equipment still belongs in the auction pool so it can be
# confirmed as Freelot when it drops.
ENDGAME_AUCTION_EXTRA_DROPS = (
    {"area": "Sky", "source": "Suzaku", "name": "Suzaku's Scythe", "p1": (), "p2": (), "p3": ()},
    {"area": "Sky", "source": "Genbu", "name": "Dryadic Abjuration: Feet", "p1": ("PUP",), "p2": (), "p3": ()},
)

ENDGAME_BASELINE_ATTENDANCE = {
    "sexualpotato": 2, "vlathgar": 2, "soyabean": 2, "chickenbanana": 2,
    "alecy": 1, "rhode": 1, "shiru": 0, "venenua": 2, "teeje": 2, "mygas": 2,
    "starnack": 0, "hmp": 0, "ivalin": 2, "cartuja": 2, "thorkell": 0,
    "shurgajoe": 2, "zanth": 0, "zaelin": 0, "kaeru": 1, "firewater": 2,
    "anonym": 2, "ramenwarrior": 2, "kalindra": 0, "eunos": 1, "brewski": 0,
    "bodom": 2, "werx": 0, "hikari": 2, "gravekeeper": 1, "boshu": 2,
    "chonk": 1, "desier": 1, "wizzaro": 1, "anshul": 1, "escii": 1,
    "imaven": 2, "tarantula": 2,
}

MEMBER_NAME_ALIASES = {
    "kb": "Killboi",
    "kb&#x20;": "Killboi",
    "soya": "Soyabean",
}

# The generated catalog retains a few original DAT names rather than their
# player-facing names used by the Sky auction rules.
AUCTION_TOOLTIP_ITEM_ALIASES = {
    "Crimson Finger Gauntlets": "Crimson Fng. Gnt.",
}

# Some valid Horizon-era items are missing from the generated DAT catalog.
# Keep auction tooltips complete without mistaking an abjuration for its gear.
AUCTION_TOOLTIP_OVERRIDES = {
    "Hecatomb Leggings": {
        "item_id": 14180,
        "name": "Hecatomb Leggings",
        "level": 73,
        "slots": ["Feet"],
        "jobs": ["WAR", "THF", "PLD", "DRK", "BST", "BRD", "DRG"],
        "description": 'DEF:22 HP+7 STR+6 DEX+3\n"Slow" +4%',
        "rare": True,
        "ex": True,
    },
}

# Keeps early-event auctions meaningful while the regular highest-minus-average
# calculation naturally takes over as DKP balances grow.
ENDGAME_MINIMUM_BID_CAP = 20


def discord_bot_request(bot_token, method, path, payload=None):
    """Call Discord's bot REST API and decode its JSON response."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    api_request = Request(
        f"https://discord.com/api/v10{path}", data=body, method=method,
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://hokutenknights.com, 1.0)",
        },
    )
    with urlopen(api_request, timeout=20) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else None


def hokuten_event_bot_request(base_url, api_token, method, path, payload=None):
    """Call the private Hokuten Event Bot API."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    api_request = Request(
        f"{base_url.rstrip('/')}{path}", data=body, method=method,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "HokutenKnightsDashboard/1.0",
        },
    )
    with urlopen(api_request, timeout=25) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else None


JOBS = (
    "WAR", "MNK", "WHM", "BLM", "RDM", "THF", "PLD", "DRK", "BST",
    "BRD", "RNG", "SAM", "NIN", "DRG", "SMN", "BLU", "COR", "PUP",
)
CAMPAIGNS = ("ZILART", "COP", "TOAU", "WINDURST", "SANDORIA", "BASTOK")
CAMPAIGN_NAMES = {
    "COP": "Chains of Promathia", "ZILART": "Rise of the Zilart",
    "TOAU": "Treasures of Aht Urhgan", "SANDORIA": "San d'Oria Missions",
    "BASTOK": "Bastok Missions", "WINDURST": "Windurst Missions",
}
STATUSES = ("Not started", "In progress", "Ready for help", "Complete")
HELP_SECTIONS = {
    "🏰 Missions": (
        "City Missions", "Rise of the Zilart Missions", "Chains of Promathia Missions",
        "Treasures of Aht Urhgan Missions",
    ),
    "⚔️ Quests": ("Limit Break Quest", "Artifact Quests", "Other Quest Help", "Weapon Skill Quest"),
    "👹 Notorious Monsters": ("Lottery NM", "Timed NM", "Trigger NM", "Pop Item Farm"),
    "☁️ Sky": ("Sky Pop Farm",),
    "🌊 Sea": ("Organ Farm", "Chip Farm", "Sea Cape Farm"),
    "🏛️ Limbus": ("Temenos", "Apollyon"),
    "🏯 Aht Urhgan": (
        "Assault", "Nyzul Isle", "Salvage", "Besieged", "Imperial Standing Farm", "Mythic Milestone",
    ),
    "⚡ Battlefields": ("BCNM", "KSNM", "ENM", "Avatar Fights", "Divine Might", "Ark Angels"),
    "📈 Character Progression": ("Merit Party", "Skillup Party", "WeaponSkill Latent Break", "Testimony Farm"),
}
HELP_CATEGORIES = tuple(activity for activities in HELP_SECTIONS.values() for activity in activities)
BF_ZONES = (
    "Balga's Dais", "Horlais Peak", "Waughroon Shrine", "Ghelsba Outpost", "Qu'Bia Arena",
    "Chamber of Oracles", "Sacrificial Chamber", "Throne Room", "Monarch Linn",
    "Sealion's Den", "Riverne Site A01", "Riverne Site B01", "Bearclaw Pinnacle",
    "Boneyard Gully", "Mine Shaft #2716", "Full Moon Fountain", "Celestial Nexus",
    "La'Loff Amphitheater", "Empyreal Paradox", "The Shrouded Maw",
)
PARTY_ROLES = ("Tank", "DD", "Healer", "Support")
ALLIANCE_ROLE_JOBS = {
    "Tank": ("PLD", "NIN", "WAR"),
    "Damage": ("WAR", "MNK", "BLM", "THF", "DRK", "BST", "RNG", "SAM", "NIN", "DRG", "SMN"),
    "Healer": ("WHM", "RDM", "SMN"),
    "Support": ("BRD", "RDM", "WHM", "SMN"),
}
REGION_ZONES = {
    "Ronfaure": ("West Ronfaure", "East Ronfaure", "Ghelsba Outpost", "Fort Ghelsba", "Yughott Grotto"),
    "Zulkheim": ("La Theine Plateau", "Valkurm Dunes", "Konschtat Highlands", "Gusgen Mines"),
    "Gustaberg": ("North Gustaberg", "South Gustaberg", "Dangruf Wadi", "Zeruhn Mines", "Palborough Mines"),
    "Derfland": ("Pashhow Marshlands", "Rolanberry Fields", "Beadeaux", "Crawler's Nest"),
    "Sarutabaruta": ("West Sarutabaruta", "East Sarutabaruta", "Giddeus", "Inner Horutoto Ruins", "Outer Horutoto Ruins", "Central Horutoto Ruins"),
    "Kolshushu": ("Tahrongi Canyon", "Buburimu Peninsula", "Maze of Shakhrami", "Bibiki Bay", "Manaclipper"),
    "Aragoneu": ("Meriphataud Mountains", "Castle Oztroja"),
    "Norvallen": ("Jugner Forest", "Batallia Downs", "Davoi", "Eldieme Necropolis"),
    "Qufim": ("Qufim Island", "Lower Delkfutt's Tower", "Middle Delkfutt's Tower", "Upper Delkfutt's Tower"),
    "Li'Telor": ("The Sanctuary of Zi'Tah", "Ro'Maeve", "Hall of the Gods"),
    "Kuzotz": ("Eastern Altepa Desert", "Western Altepa Desert", "Rabao", "Quicksand Caves"),
    "Vollbow": ("Sauromugue Champaign", "Garlaige Citadel", "Cape Teriggan", "Valley of Sorrows"),
    "Elshimo Lowlands": ("Yuhtunga Jungle", "Temple of Uggalepih", "Den of Rancor"),
    "Elshimo Uplands": ("Yhoator Jungle", "Ifrit's Cauldron"),
    "Fauregandi": ("Beaucedine Glacier", "Fei'Yin"),
    "Valdeaunia": ("Xarcabard", "Castle Zvahl Baileys", "Castle Zvahl Keep"),
    "Tu'Lia (Sky)": ("Ru'Aun Gardens", "Shrine of Ru'Avitau", "Ve'Lugannon Palace"),
    "Tavnazian Archipelago": ("Lufaise Meadows", "Misareaux Coast", "Phomiuna Aqueducts", "Sacrarium", "Riverne - Site #A01", "Riverne - Site #B01"),
    "Movalpolos": ("Oldton Movalpolos", "Newton Movalpolos"),
    "Lumoria (Sea)": ("Al'Taieu", "Grand Palace of Hu'Xzoi", "The Garden of Ru'Hmet"),
}
HELP_ZONES = {
    activity: ({"Battlefields": BF_ZONES} if activity in ("BCNM", "KSNM", "ENM") else REGION_ZONES)
    for activity in HELP_CATEGORIES
}
HELP_STATUSES = ("Open", "Forming", "Full", "Completed", "Cancelled", "Expired")
ACTIVE_HELP_STATUSES = ("Open", "Forming", "Full")
LOGIN_CHARACTERS = (
    "Imaven", "Sexualpotato", "Vlathgar", "Soyabean", "Chickenbanana",
    "Alecy", "Rhode", "Shiru", "Venenua", "Teeje", "Mygas", "Starnack",
    "HMP", "Ivalin", "Cartuja", "Throkell", "Shurgajoe", "Zanth", "Zaelin",
    "Kaeru", "Firewater", "Anonym", "Ramenwarrior", "Kalindra", "Eunos",
    "Brewski", "Bodom", "Werx", "Palumbo", "Hikari", "Gravekeeper",
)
DISCORD_ADMIN_CHARACTERS = ("Imaven", "Sexualpotato", "Vlathgar", "Cartuja", "Ramenwarrior", "Chickenbanana")
AVAILABILITY_MODES = {
    "now": "Today/Now — PM Me",
    "after": "Any Time After",
    "fixed": "Specific Date/Time",
}
HELP_STATUS_TRANSITIONS = {
    "Open": {"Forming", "Full", "Completed", "Cancelled"},
    "Forming": {"Open", "Full", "Completed", "Cancelled"},
    "Full": {"Open", "Forming", "Completed", "Cancelled"},
    "Completed": set(), "Cancelled": {"Open"}, "Expired": {"Open"},
}
EASTERN_TIME = ZoneInfo("America/New_York")
HORIZON_API = "https://api.horizonxi.com/api/v1"
PSXI_MARKET_API = "https://www.psxi.gg/api/v1/market/horizonxi"
PSXI_MARKET_TTL = 60 * 60
_market_cache_lock = threading.Lock()
MAP_ZONE_ID_OVERRIDES = {"Ifrits Cauldron": 205}
GEAR_SLOTS = (
    "main", "sub", "ranged", "ammo", "head", "body", "hands", "legs",
    "feet", "neck", "waist", "ear1", "ear2", "ring1", "ring2", "back",
)
GEAR_JOBS = JOBS
GEAR_STAT_ALIASES = {
    "def": "DEF", "defense": "DEF", "hp": "HP", "mp": "MP",
    "str": "STR", "dex": "DEX", "vit": "VIT", "agi": "AGI",
    "int": "INT", "mnd": "MND", "chr": "CHR", "accuracy": "Accuracy",
    "attack": "Attack", "evasion": "Evasion", "haste": "Haste",
    "enmity": "Enmity", "store tp": "Store TP", "double attack": "Double Attack",
    "triple attack": "Triple Attack", "ranged accuracy": "Ranged Accuracy",
    "ranged attack": "Ranged Attack", "magic accuracy": "Magic Accuracy",
    "magic attack bonus": "Magic Attack Bonus", "magic atk. bonus": "Magic Attack Bonus",
    "magic atk bonus": "Magic Attack Bonus", "magic defense bonus": "Magic Defense Bonus",
    "magic def. bonus": "Magic Defense Bonus",
    "cure potency": "Cure Potency", "refresh": "Refresh", "regen": "Regen",
    "fire resistance": "Fire Resistance", "ice resistance": "Ice Resistance",
    "wind resistance": "Wind Resistance", "earth resistance": "Earth Resistance",
    "lightning resistance": "Lightning Resistance", "water resistance": "Water Resistance",
    "light resistance": "Light Resistance", "dark resistance": "Dark Resistance",
    "fire": "Fire Resistance", "ice": "Ice Resistance", "wind": "Wind Resistance",
    "earth": "Earth Resistance", "lightning": "Lightning Resistance",
    "water": "Water Resistance", "light": "Light Resistance", "dark": "Dark Resistance",
    "critical hit rate": "Critical Hit Rate", "weapon skill accuracy": "Weapon Skill Accuracy",
    "damage taken": "Damage Taken", "physical damage taken": "Physical Damage Taken",
    "magic damage taken": "Magic Damage Taken", "breath damage taken": "Breath Damage Taken",
    "hp recovered while healing": "HP Recovered While Healing",
    "mp recovered while healing": "MP Recovered While Healing",
    "movement speed": "Movement Speed", "avatar perpetuation cost": "Avatar Perpetuation Cost",
    "hand-to-hand skill": "Hand-to-Hand Skill", "dagger skill": "Dagger Skill",
    "sword skill": "Sword Skill", "great sword skill": "Great Sword Skill",
    "axe skill": "Axe Skill", "great axe skill": "Great Axe Skill",
    "scythe skill": "Scythe Skill", "polearm skill": "Polearm Skill",
    "katana skill": "Katana Skill", "great katana skill": "Great Katana Skill",
    "club skill": "Club Skill", "staff skill": "Staff Skill",
    "archery skill": "Archery Skill", "marksmanship skill": "Marksmanship Skill",
    "throwing skill": "Throwing Skill", "shield skill": "Shield Skill",
    "parrying skill": "Parrying Skill", "guarding skill": "Guarding Skill",
    "evasion skill": "Evasion Skill", "healing magic skill": "Healing Magic Skill",
    "divine magic skill": "Divine Magic Skill", "enhancing magic skill": "Enhancing Magic Skill",
    "enfeebling magic skill": "Enfeebling Magic Skill", "elemental magic skill": "Elemental Magic Skill",
    "dark magic skill": "Dark Magic Skill", "summoning magic skill": "Summoning Magic Skill",
    "ninjutsu skill": "Ninjutsu Skill", "singing skill": "Singing Skill",
    "string instrument skill": "String Instrument Skill", "wind instrument skill": "Wind Instrument Skill",
    "blue magic skill": "Blue Magic Skill",
}
HORIZON_AVATAR_RACES = {
    "Hm": "Hume Male", "Hf": "Hume Female", "Em": "Elvaan Male",
    "Ef": "Elvaan Female", "Tm": "Tarutaru Male", "Tf": "Tarutaru Female",
    "Mi": "Mithra", "Ga": "Galka",
}


def horizon_json(path, timeout=20):
    api_request = Request(
        f"{HORIZON_API}/{path.lstrip('/')}",
        headers={"Accept": "application/json", "User-Agent": "HokutenGearOptimizer/1.0"},
    )
    with urlopen(api_request, timeout=timeout) as response:
        return json.load(response)


def compact_market_snapshot(payload):
    """Reduce the PSXI bulk response to the fields used by loot-table price cells."""
    prices = {}
    for item in payload.get("data", []):
        item_id = item.get("itemId")
        if not isinstance(item_id, int):
            continue
        auction = item.get("ah") or {}
        single = auction.get("single") or {}
        stack = auction.get("stack") or {}
        bazaar = item.get("bazaar") or item.get("bazaars") or {}
        bazaar_lowest = next((bazaar.get(key) for key in (
            "lowest", "lowestPrice", "lowestBazaar", "minPrice", "min"
        ) if isinstance(bazaar, dict) and bazaar.get(key) is not None), None)
        prices[str(item_id)] = {
            "name": item.get("itemName") or "",
            "as_of": item.get("asOf"),
            "stock": auction.get("currentStock"),
            "stack_stock": auction.get("currentStackStock"),
            "single_last": single.get("lastSale"),
            "single_median": single.get("median"),
            "single_volume": single.get("volume"),
            "stack_last": stack.get("lastSale"),
            "stack_median": stack.get("median"),
            "stack_volume": stack.get("volume"),
            "bazaar_lowest": bazaar_lowest,
            "single_recent_average": next((single.get(key) for key in (
                "lastThreeAverage", "last_three_average", "recentAverage"
            ) if single.get(key) is not None), None),
            "single_average": single.get("avg"),
        }
    return {"generated_at": (payload.get("meta") or {}).get("generatedAt"), "prices": prices}


def market_snapshot(cache_path, token="", now=None, force_refresh=False):
    """Return an hourly file-backed PSXI market snapshot without exposing credentials."""
    cache_path = Path(cache_path)
    current_time = datetime.now().timestamp() if now is None else float(now)
    with _market_cache_lock:
        cached = None
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if not force_refresh and current_time - cache_path.stat().st_mtime < PSXI_MARKET_TTL:
                return cached
        headers = {"Accept": "application/json", "User-Agent": "HokutenMarketCache/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request_data = Request(PSXI_MARKET_API, headers=headers)
        try:
            with urlopen(request_data, timeout=45) as response:
                snapshot = compact_market_snapshot(json.load(response))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            if cached is not None:
                return cached
            raise
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(f"{cache_path.suffix}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf-8")
        temporary.replace(cache_path)
        return snapshot


def parse_gear_stats(description):
    """Extract common unconditional equipment stats from a Horizon item description."""
    text = " ".join(
        str(description or "").replace("\n", " ").replace('"', "")
        .replace("“", "").replace("”", "").split()
    )
    unconditional = re.split(
        r"\b(?:Latent effect|Set|Assault|Salvage|Campaign|Besieged|Daytime|Nighttime):",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    names = sorted(GEAR_STAT_ALIASES, key=len, reverse=True)
    pattern = re.compile(
        rf"(?<![A-Za-z])({'|'.join(re.escape(name) for name in names)})\s*[: ]?\s*([+-]?\d+)(%)?",
        re.IGNORECASE,
    )
    stats = {}
    for match in pattern.finditer(unconditional):
        name = GEAR_STAT_ALIASES[match.group(1).casefold()]
        value = int(match.group(2))
        if name == "DEF" and value >= 0 and match.group(1).casefold() == "def":
            value = abs(value)
        stats[name] = stats.get(name, 0) + value
    return stats


def normalize_horizon_item(item_id, metadata, *, key=""):
    sprite = metadata.get("sprite") or metadata
    description = sprite.get("description") or metadata.get("desc") or ""
    return {
        "item_id": int(item_id),
        "item_key": key or metadata.get("key") or "",
        "name": sprite.get("name") or metadata.get("name") or f"Item {item_id}",
        "slot": sprite.get("slot") or "",
        "description": description,
        "jobs": sprite.get("jobs") or "",
        "level": int(sprite.get("level") or 0),
        "weapon_type": sprite.get("weaponType") or "",
        "rare": bool(sprite.get("rare", metadata.get("rare", False))),
        "ex": bool(sprite.get("ex", metadata.get("ex", False))),
        "stats": parse_gear_stats(description),
    }


def fetch_horizon_equipment(character_name):
    payload = horizon_json(f"chars/{quote(character_name)}/equip")
    metadata = payload.get("itemMetadata") or {}
    equipment = {}
    for slot in GEAR_SLOTS:
        equipped = (payload.get("equip") or {}).get(slot) or {}
        item_id = equipped.get("itemid")
        if not item_id or str(item_id) not in metadata:
            equipment[slot] = None
            continue
        equipment[slot] = normalize_horizon_item(
            item_id, metadata[str(item_id)], key=equipped.get("name", "")
        )
    return equipment

DYNAMIS_RELIC = {
    "WAR": (("Warrior's Mask", "Head", "Dynamis - Windurst"), ("Warrior's Lorica", "Body", "Dynamis - Xarcabard"), ("Warrior's Mufflers", "Hands", "Dynamis - Jeuno"), ("Warrior's Cuisses", "Legs", "Dynamis - Beaucedine"), ("Warrior's Calligae", "Feet", "Dynamis - San d'Oria")),
    "MNK": (("Melee Crown", "Head", "Dynamis - Xarcabard"), ("Melee Cyclas", "Body", "Dynamis - Beaucedine"), ("Melee Gloves", "Hands", "Dynamis - Jeuno"), ("Melee Hose", "Legs", "Dynamis - San d'Oria"), ("Melee Gaiters", "Feet", "Dynamis - Bastok")),
    "WHM": (("Cleric's Cap", "Head", "Dynamis - San d'Oria"), ("Cleric's Bliaut", "Body", "Dynamis - Beaucedine"), ("Cleric's Mitts", "Hands", "Dynamis - Xarcabard"), ("Cleric's Pantaloons", "Legs", "Dynamis - Jeuno"), ("Cleric's Duckbills", "Feet", "Dynamis - Windurst")),
    "BLM": (("Sorcerer's Petasos", "Head", "Dynamis - Xarcabard"), ("Sorcerer's Coat", "Body", "Dynamis - Beaucedine"), ("Sorcerer's Gloves", "Hands", "Dynamis - Windurst"), ("Sorcerer's Tonban", "Legs", "Dynamis - Bastok"), ("Sorcerer's Sabots", "Feet", "Dynamis - Jeuno")),
    "RDM": (("Duelist's Chapeau", "Head", "Dynamis - Xarcabard"), ("Duelist's Tabard", "Body", "Dynamis - Beaucedine"), ("Duelist's Gloves", "Hands", "Dynamis - Bastok"), ("Duelist's Tights", "Legs", "Dynamis - Jeuno"), ("Duelist's Boots", "Feet", "Dynamis - San d'Oria")),
    "THF": (("Assassin's Bonnet", "Head", "Dynamis - Windurst"), ("Assassin's Vest", "Body", "Dynamis - Bastok"), ("Assassin's Armlets", "Hands", "Dynamis - Xarcabard"), ("Assassin's Culottes", "Legs", "Dynamis - Beaucedine"), ("Assassin's Poulaines", "Feet", "Dynamis - Jeuno")),
    "PLD": (("Valor Coronet", "Head", "Dynamis - Bastok"), ("Valor Surcoat", "Body", "Dynamis - Xarcabard"), ("Valor Gauntlets", "Hands", "Dynamis - San d'Oria"), ("Valor Breeches", "Legs", "Dynamis - Beaucedine"), ("Valor Leggings", "Feet", "Dynamis - Windurst")),
    "DRK": (("Abyss Burgeonet", "Head", "Dynamis - Xarcabard"), ("Abyss Cuirass", "Body", "Dynamis - Beaucedine"), ("Abyss Gauntlets", "Hands", "Dynamis - Windurst"), ("Abyss Flanchard", "Legs", "Dynamis - Jeuno"), ("Abyss Sollerets", "Feet", "Dynamis - Bastok")),
    "BST": (("Monster Helm", "Head", "Dynamis - Windurst"), ("Monster Jackcoat", "Body", "Dynamis - Bastok"), ("Monster Gloves", "Hands", "Dynamis - Xarcabard"), ("Monster Trousers", "Legs", "Dynamis - San d'Oria"), ("Monster Gaiters", "Feet", "Dynamis - Beaucedine")),
    "BRD": (("Bard's Roundlet", "Head", "Dynamis - San d'Oria"), ("Bard's Justaucorps", "Body", "Dynamis - Beaucedine"), ("Bard's Cuffs", "Hands", "Dynamis - Bastok"), ("Bard's Cannions", "Legs", "Dynamis - Xarcabard"), ("Bard's Slippers", "Feet", "Dynamis - Jeuno")),
    "RNG": (("Scout's Beret", "Head", "Dynamis - Jeuno"), ("Scout's Jerkin", "Body", "Dynamis - Xarcabard"), ("Scout's Bracers", "Hands", "Dynamis - Windurst"), ("Scout's Braccae", "Legs", "Dynamis - San d'Oria"), ("Scout's Socks", "Feet", "Dynamis - Beaucedine")),
    "SAM": (("Saotome Kabuto", "Head", "Dynamis - Beaucedine"), ("Saotome Domaru", "Body", "Dynamis - Xarcabard"), ("Saotome Kote", "Hands", "Dynamis - Bastok"), ("Saotome Haidate", "Legs", "Dynamis - Windurst"), ("Saotome Sune-Ate", "Feet", "Dynamis - Jeuno")),
    "NIN": (("Koga Hatsuburi", "Head", "Dynamis - Windurst"), ("Koga Chainmail", "Body", "Dynamis - Beaucedine"), ("Koga Tekko", "Hands", "Dynamis - Xarcabard"), ("Koga Hakama", "Legs", "Dynamis - San d'Oria"), ("Koga Kyahan", "Feet", "Dynamis - Jeuno")),
    "DRG": (("Wyrm Armet", "Head", "Dynamis - Xarcabard"), ("Wyrm Mail", "Body", "Dynamis - Beaucedine"), ("Wyrm Finger Gauntlets", "Hands", "Dynamis - Jeuno"), ("Wyrm Brais", "Legs", "Dynamis - Bastok"), ("Wyrm Greaves", "Feet", "Dynamis - San d'Oria")),
    "SMN": (("Summoner's Horn", "Head", "Dynamis - Xarcabard"), ("Summoner's Doublet", "Body", "Dynamis - Beaucedine"), ("Summoner's Bracers", "Hands", "Dynamis - Bastok"), ("Summoner's Spats", "Legs", "Dynamis - Windurst"), ("Summoner's Pigaches", "Feet", "Dynamis - San d'Oria")),
    "BLU": (("Mirage Keffiyeh", "Head", "Dynamis - Xarcabard"), ("Mirage Jubbah", "Body", "Dynamis - Beaucedine"), ("Mirage Bazubands", "Hands", "Dynamis - San d'Oria"), ("Mirage Shalwar", "Legs", "Dynamis - Bastok"), ("Mirage Charuqs", "Feet", "Dynamis - Windurst")),
    "COR": (("Commodore Tricorne", "Head", "Dynamis - Xarcabard"), ("Commodore Frac", "Body", "Dynamis - Beaucedine"), ("Commodore Gants", "Hands", "Dynamis - Jeuno"), ("Commodore Culottes", "Legs", "Dynamis - San d'Oria"), ("Commodore Bottes", "Feet", "Dynamis - Bastok")),
    "PUP": (("Pantin Taj", "Head", "Dynamis - Xarcabard"), ("Pantin Tobe", "Body", "Dynamis - Beaucedine"), ("Pantin Dastanas", "Hands", "Dynamis - Windurst"), ("Pantin Churidars", "Legs", "Dynamis - Jeuno"), ("Pantin Babouches", "Feet", "Dynamis - San d'Oria")),
}
LIMBUS_LOOT = {
    "Proto-Omega": (("Omega's Eye", "Homam Zucchetto", "Head"), ("Omega's Heart", "Homam Corazza", "Body"), ("Omega's Foreleg", "Homam Manopolas", "Hands"), ("Omega's Hind Leg", "Homam Cosciales", "Legs"), ("Omega's Tail", "Homam Gambieras", "Feet")),
    "Proto-Ultima": (("Ultima's Cerebrum", "Nashira Turban", "Head"), ("Ultima's Heart", "Nashira Manteel", "Body"), ("Ultima's Claw", "Nashira Gages", "Hands"), ("Ultima's Leg", "Nashira Seraweels", "Legs"), ("Ultima's Tail", "Nashira Crackows", "Feet")),
}
LIMBUS_AF1 = {
    "WAR": {"temenos": ("Ecarlate Cloth", "North F2/F4 · West F1/F2/F4/F5/F7"), "apollyon": ("Argyro Rivet", "NE F3 · NW F1/F4/F5 · SE F4 · SW F2/F3"), "pieces": ("Fighter's Mask +1", "Fighter's Lorica +1", "Fighter's Mufflers +1", "Fighter's Cuisses +1", "Fighter's Calligae +1")},
    "MNK": {"temenos": ("Utopian Gold Thread", "North F1/F2/F3/F5/F7 · West F5/F6"), "apollyon": ("Ancient Brass", "NE F1-F4 · NW F3-F5 · SE F3 · SW F4"), "pieces": ("Temple Crown +1", "Temple Cyclas +1", "Temple Gloves +1", "Temple Hose +1", "Temple Gaiters +1")},
    "WHM": {"temenos": ("Benedict Silk", "North F1/F3/F4/F5/F7 · West F2/F6"), "apollyon": ("Benedict Yarn", "NE F1 · NW F1/F4/F5 · SE F4 · SW F1/F3"), "pieces": ("Healer's Cap +1", "Healer's Bliaut +1", "Healer's Mitts +1", "Healer's Pantaloons +1", "Healer's Duckbills +1")},
    "BLM": {"temenos": ("Diabolic Silk", "North F3/F4/F6 · East F1/F2/F6/F7"), "apollyon": ("Diabolic Yarn", "NE F2 · NW F1/F5 · SE F4 · SW F1-F3"), "pieces": ("Wizard's Petasos +1", "Wizard's Coat +1", "Wizard's Gloves +1", "Wizard's Tonban +1", "Wizard's Sabots +1")},
    "RDM": {"temenos": ("Ruby Silk Thread", "West F1/F2/F4-F7 · East F2/F3/F5"), "apollyon": ("Cardinal Cloth", "NE F1/F3 · NW F4/F5 · SE F1 · SW F4"), "pieces": ("Warlock's Chapeau +1", "Warlock's Tabard +1", "Warlock's Gloves +1", "Warlock's Tights +1", "Warlock's Boots +1")},
    "THF": {"temenos": ("Supple Skin", "North F1/F3-F5/F7 · East F3-F6"), "apollyon": ("Light Filament", "NE F2/F3 · NW F3-F5 · SE F1/F4 · SW F4"), "pieces": ("Rogue's Bonnet +1", "Rogue's Vest +1", "Rogue's Armlets +1", "Rogue's Culottes +1", "Rogue's Poulaines +1")},
    "PLD": {"temenos": ("Snowy Cermet", "North F5/F6 · East F1-F3/F7"), "apollyon": ("White Rivet", "NE F1/F2 · NW F1/F3/F5 · SE F2/F4 · SW F4"), "pieces": ("Gallant Coronet +1", "Gallant Surcoat +1", "Gallant Gauntlets +1", "Gallant Breeches +1", "Gallant Leggings +1")},
    "DRK": {"temenos": ("Dark Orichalcum", "West F2/F4 · East F1/F4/F5/F7"), "apollyon": ("Black Rivet", "NE F4 · NW F2/F4/F5 · SE F1/F3 · SW F1"), "pieces": ("Chaos Burgeonet +1", "Chaos Cuirass +1", "Chaos Gauntlets +1", "Chaos Flanchard +1", "Chaos Sollerets +1")},
    "BST": {"temenos": ("Smalt Leather", "West F3/F5 · East F1/F2/F6/F7"), "apollyon": ("Fetid Lanolin", "NE F1/F2 · NW F3-F5 · SE F2 · SW F3/F4"), "pieces": ("Beast Helm +1", "Beast Jackcoat +1", "Beast Gloves +1", "Beast Trousers +1", "Beast Gaiters +1")},
    "BRD": {"temenos": ("Coiled Yarn", "West F1-F3/F6/F7 · East F3/F6"), "apollyon": ("Brown Doeskin", "NE F4 · NW F2/F4/F5 · SE F3 · SW F1"), "pieces": ("Choral Roundlet +1", "Choral Justaucorps +1", "Choral Cuffs +1", "Choral Cannions +1", "Choral Slippers +1")},
    "RNG": {"temenos": ("Chameleon Yarn", "North F2/F6 · East F1/F3-F5/F7"), "apollyon": ("Charcoal Cotton", "NE F4 · NW F2/F5 · SE F1-F3 · SW F2"), "pieces": ("Hunter's Beret +1", "Hunter's Jerkin +1", "Hunter's Bracers +1", "Hunter's Braccae +1", "Hunter's Socks +1")},
    "SAM": {"temenos": ("Scarlet Odoshi", "West F1-F4/F6/F7 · East F3/F4"), "apollyon": ("Kurogane", "NE F1/F5 · NW F1/F5 · SE F4 · SW F2/F3"), "pieces": ("Myochin Kabuto +1", "Myochin Domaru +1", "Myochin Kote +1", "Myochin Haidate +1", "Myochin Sune-Ate +1")},
    "NIN": {"temenos": ("Plaited Cord", "North F1/F2/F6/F7 · West F3-F6"), "apollyon": ("Ebony Lacquer", "NE F4 · NW F2/F5 · SE F2/F3 · SW F2/F3"), "pieces": ("Ninja Hatsuburi +1", "Ninja Chainmail +1", "Ninja Tekko +1", "Ninja Hakama +1", "Ninja Kyahan +1")},
    "DRG": {"temenos": ("Cobalt Mythril Sheet", "North F1-F3/F6/F7 · East F5/F6"), "apollyon": ("Blue Rivet", "NE F2 · NW F1/F5 · SE F4 · SW F1"), "pieces": ("Drachen Armet +1", "Drachen Mail +1", "Drachen Finger Gauntlets +1", "Drachen Brais +1", "Drachen Greaves +1")},
    "SMN": {"temenos": ("Glittering Yarn", "North F3-F5 · West F1/F4-F7"), "apollyon": ("Astral Leather", "NE F4 · NW F2/F4/F5 · SE F1-F3 · SW F2"), "pieces": ("Evoker's Horn +1", "Evoker's Doublet +1", "Evoker's Bracers +1", "Evoker's Spats +1", "Evoker's Pigaches +1")},
}
AF1_SLOTS = ("Head", "Body", "Hands", "Legs", "Feet")
DYNAMIS_ACCESSORIES = {
    "WAR": ("Warrior's Stone", "Waist", ("Dynamis - Valkurm", "Dynamis - Buburimu")),
    "MNK": ("Melee Cape", "Back", ("Dynamis - Buburimu", "Dynamis - Qufim")),
    "WHM": ("Cleric's Belt", "Waist", ("Dynamis - Valkurm", "Dynamis - Qufim")),
    "BLM": ("Sorcerer's Belt", "Waist", ("Dynamis - Valkurm", "Dynamis - Buburimu")),
    "RDM": ("Duelist's Belt", "Waist", ("Dynamis - Buburimu", "Dynamis - Qufim")),
    "THF": ("Assassin's Cape", "Back", ("Dynamis - Valkurm", "Dynamis - Qufim")),
    "PLD": ("Valor Cape", "Back", ("Dynamis - Valkurm", "Dynamis - Buburimu")),
    "DRK": ("Abyss Cape", "Back", ("Dynamis - Buburimu", "Dynamis - Qufim")),
    "BST": ("Monster Belt", "Waist", ("Dynamis - Valkurm", "Dynamis - Qufim")),
    "BRD": ("Bard's Cape", "Back", ("Dynamis - Valkurm", "Dynamis - Buburimu")),
    "RNG": ("Scout's Belt", "Waist", ("Dynamis - Buburimu", "Dynamis - Qufim")),
    "SAM": ("Saotome Koshi-Ate", "Waist", ("Dynamis - Valkurm", "Dynamis - Qufim")),
    "NIN": ("Koga Sarashi", "Waist", ("Dynamis - Valkurm", "Dynamis - Buburimu")),
    "DRG": ("Wyrm Belt", "Waist", ("Dynamis - Buburimu", "Dynamis - Qufim")),
    "SMN": ("Summoner's Cape", "Back", ("Dynamis - Valkurm", "Dynamis - Qufim")),
    "BLU": ("Mirage Mantle", "Back", ("Dynamis - Buburimu", "Dynamis - Valkurm")),
    "COR": ("Commodore Belt", "Waist", ("Dynamis - Qufim",)),
    "PUP": ("Pantin Cape", "Back", ("Dynamis - Buburimu", "Dynamis - Qufim")),
}
JOB_COLORS = {
    "WAR": "#b84b42", "MNK": "#d47a3f", "WHM": "#e8e3d5", "BLM": "#7456a8",
    "RDM": "#c44f62", "THF": "#d5b84a", "PLD": "#6e9ed2", "DRK": "#654078",
    "BST": "#8b6848", "BRD": "#d47aaa", "RNG": "#4f9a68", "SAM": "#9c493f",
    "NIN": "#58617d", "DRG": "#6659a8", "SMN": "#4f9b92",
    "BLU": "#3b9cc5", "COR": "#c08442", "PUP": "#bc6f9e",
}


def dynamis_catalog():
    pieces = []
    for job, relic_pieces in DYNAMIS_RELIC.items():
        for item, slot, area in relic_pieces:
            pieces.append({"key": f"dynamis:{job}:{slot.lower()}", "job": job,
                           "item": item, "slot": slot, "area": area, "kind": "Relic armor"})
        by_slot = {slot: item for item, slot, _area in relic_pieces}
        dream_slots = {"Head": "Dynamis - Valkurm", "Hands": "Dynamis - Buburimu",
                       "Feet": "Dynamis - Qufim", "Body": "Dynamis - Tavnazia",
                       "Legs": "Dynamis - Tavnazia"}
        for slot, area in dream_slots.items():
            pieces.append({"key": f"dynamis:dream:{job}:{slot.lower()}", "job": job,
                           "item": f"{by_slot[slot]} -1", "slot": slot, "area": area,
                           "kind": "Relic armor -1"})
        item, slot, areas = DYNAMIS_ACCESSORIES[job]
        for area in areas:
            pieces.append({"key": f"dynamis:accessory:{job}", "job": job, "item": item,
                           "slot": slot, "area": area, "kind": "Relic accessory"})
    return pieces

MISSION_OPTIONS = {
    "ZILART": [
        ("Rise of the Zilart", [
            ("ZM1 – The New Frontier", "ZM1"),
            ("ZM2 – Welcome t'Norg", "ZM2"),
            ("ZM3 – Kazham's Chieftainess", "ZM3"),
            ("ZM4 – The Temple of Uggalepih", "ZM4"),
            ("ZM5 – Headstone Pilgrimage", "ZM5"),
            ("ZM6 – Through the Quicksand Caves", "ZM6"),
            ("ZM7 – The Chamber of Oracles", "ZM7"),
            ("ZM8 – Return to Delkfutt's Tower", "ZM8"),
            ("ZM9 – Ro'Maeve", "ZM9"),
            ("ZM10 – The Temple of Desolation", "ZM10"),
            ("ZM11 – The Hall of the Gods", "ZM11"),
            ("ZM12 – The Mithra and the Crystal", "ZM12"),
            ("ZM13 – The Gate of the Gods", "ZM13"),
            ("ZM14 – Ark Angels", "ZM14"),
            ("ZM15 – The Sealed Shrine", "ZM15"),
            ("ZM16 – The Celestial Nexus", "ZM16"),
            ("ZM17 – Awakening", "ZM17"),
            ("ZM18 – The Last Verse (epilogue shared with CoP after Apocalypse Nigh)", "ZM18"),
            ("Complete", "Complete"),
        ]),
    ],
    "COP": [
        ("Chapter 1 – Ancient Flames Beckon", [
            ("CoP 1-1 – The Rites of Life", "Chapter 1 – Ancient Flames Beckon"),
            ("CoP 1-2 – Below the Arks", "Chapter 1 – Ancient Flames Beckon"),
            ("CoP 1-3 – The Mothercrystals", "Chapter 1 – Ancient Flames Beckon"),
        ]),
        ("Chapter 2 – The Isle of Forgotten Saints", [
            ("CoP 2-1 – An Invitation West", "Chapter 2 – The Isle of Forgotten Saints"),
            ("CoP 2-2 – The Lost City", "Chapter 2 – The Isle of Forgotten Saints"),
            ("CoP 2-3 – Distant Beliefs", "Chapter 2 – The Isle of Forgotten Saints"),
            ("CoP 2-4 – An Eternal Melody", "Chapter 2 – The Isle of Forgotten Saints"),
            ("CoP 2-5 – Ancient Vows", "Chapter 2 – The Isle of Forgotten Saints"),
        ]),
        ("Chapter 3 – A Transient Dream", [
            ("CoP 3-1 – The Call of the Wyrmking", "Chapter 3 – A Transient Dream"),
            ("CoP 3-2 – A Vessel Without a Captain", "Chapter 3 – A Transient Dream"),
            ("CoP 3-3 – The Road Forks", "Chapter 3 – A Transient Dream"),
            ("CoP 3-4 – Tending Aged Wounds", "Chapter 3 – A Transient Dream"),
            ("CoP 3-5 – Darkness Named", "Chapter 3 – A Transient Dream"),
        ]),
        ("Chapter 4 – Dawn", [
            ("CoP 4-1 – Sheltering Doubt", "Chapter 4 – Dawn"),
            ("CoP 4-2 – The Savage", "Chapter 4 – Dawn"),
            ("CoP 4-3 – The Secrets of Worship", "Chapter 4 – Dawn"),
            ("CoP 4-4 – Slanderous Utterings", "Chapter 4 – Dawn"),
            ("The Return Home", "Chapter 4 – Dawn"),
        ]),
        ("Chapter 5 – The Return Home to Jeuno", [
            ("CoP 5-1 – The Enduring Tumult of War", "Chapter 5 – The Return Home to Jeuno"),
            ("CoP 5-2 – Desires of Emptiness", "Chapter 5 – The Return Home to Jeuno"),
            ("CoP 5-3 – Three Paths", "Chapter 5 – The Return Home to Jeuno"),
            ("Louverance's Path", "Chapter 5 – The Return Home to Jeuno"),
            ("Tenzen's Path", "Chapter 5 – The Return Home to Jeuno"),
            ("Ulmia's Path", "Chapter 5 – The Return Home to Jeuno"),
        ]),
        ("Chapter 6 – Echoes of Time", [
            ("CoP 6-1 – For Whom the Verse Is Sung", "Chapter 6 – Echoes of Time"),
            ("CoP 6-2 – A Place to Return", "Chapter 6 – Echoes of Time"),
            ("CoP 6-3 – More Questions Than Answers", "Chapter 6 – Echoes of Time"),
            ("CoP 6-4 – One to Be Feared", "Chapter 6 – Echoes of Time"),
        ]),
        ("Chapter 7 – In the Light of the Crystal", [
            ("CoP 7-1 – Chains and Bonds", "Chapter 7 – In the Light of the Crystal"),
            ("CoP 7-2 – Flames in the Darkness", "Chapter 7 – In the Light of the Crystal"),
            ("CoP 7-3 – Fire in the Eyes of Men", "Chapter 7 – In the Light of the Crystal"),
            ("CoP 7-4 – Calm Before the Storm", "Chapter 7 – In the Light of the Crystal"),
            ("CoP 7-5 – The Warrior's Path", "Chapter 7 – In the Light of the Crystal"),
        ]),
        ("Chapter 8 – Emptiness Bleeds", [
            ("CoP 8-1 – Garden of Antiquity", "Chapter 8 – Emptiness Bleeds"),
            ("CoP 8-2 – A Fate Decided", "Chapter 8 – Emptiness Bleeds"),
            ("CoP 8-3 – When Angels Fall", "Chapter 8 – Emptiness Bleeds"),
            ("CoP 8-4 – Dawn", "Chapter 8 – Emptiness Bleeds"),
            ("CoP 8-5 – The Last Verse (shared ZM/CoP epilogue)", "Chapter 8 – Emptiness Bleeds"),
            ("Complete", "Complete"),
        ]),
    ],
}

CITY_MISSIONS = {
    "SANDORIA": (
        ("1-1", "Smash the Orcish Scouts"), ("1-2", "Bat Hunt"), ("1-3", "Save the Children"),
        ("2-1", "The Rescue Drill"), ("2-2", "The Davoi Report"), ("2-3", "Journey Abroad"),
        ("3-1", "Infiltrate Davoi"), ("3-2", "The Crystal Spring"), ("3-3", "Appointment to Jeuno"),
        ("4-1", "Magicite"), ("5-1", "The Ruins of Fei'Yin"), ("5-2", "The Shadow Lord"),
        ("6-1", "Leaute's Last Wishes"), ("6-2", "Ranperre's Final Rest"),
        ("7-1", "Prestige of the Papsque"), ("7-2", "Secret Weapon"),
        ("8-1", "Coming of Age"), ("8-2", "Lightbringer"),
        ("9-1", "Breaking Barriers"), ("9-2", "The Heir to the Light"),
    ),
    "BASTOK": (
        ("1-1", "The Zeruhn Report"), ("1-2", "A Geological Survey"), ("1-3", "Fetichism"),
        ("2-1", "The Crystal Line"), ("2-2", "Wading Beasts"), ("2-3", "The Emissary"),
        ("3-1", "The Four Musketeers"), ("3-2", "To the Forsaken Mines"), ("3-3", "Jeuno"),
        ("4-1", "Magicite"), ("5-1", "Darkness Rising"), ("5-2", "Xarcabard, Land of Truths"),
        ("6-1", "Return of the Talekeeper"), ("6-2", "The Pirates' Cove"),
        ("7-1", "The Final Image"), ("7-2", "On My Way"),
        ("8-1", "The Chains That Bind Us"), ("8-2", "Enter the Talekeeper"),
        ("9-1", "The Salt of the Earth"), ("9-2", "Where Two Paths Converge"),
    ),
    "WINDURST": (
        ("1-1", "The Horutoto Ruins Experiment"), ("1-2", "The Heart of the Matter"), ("1-3", "The Price of Peace"),
        ("2-1", "Lost for Words"), ("2-2", "A Testing Time"), ("2-3", "The Three Kingdoms"),
        ("3-1", "To Each His Own Right"), ("3-2", "Written in the Stars"), ("3-3", "A New Journey"),
        ("4-1", "Magicite"), ("5-1", "The Final Seal"), ("5-2", "The Shadow Awaits"),
        ("6-1", "Full Moon Fountain"), ("6-2", "Saintly Invitation"),
        ("7-1", "The Sixth Ministry"), ("7-2", "Awakening of the Gods"),
        ("8-1", "Vain"), ("8-2", "The Jester Who'd Be King"),
        ("9-1", "Doll of the Dead"), ("9-2", "Moon Reading"),
    ),
}
for campaign, missions in CITY_MISSIONS.items():
    city_name = {"SANDORIA": "San d'Oria", "BASTOK": "Bastok", "WINDURST": "Windurst"}[campaign]
    MISSION_OPTIONS[campaign] = [
        (f"Rank {rank}", [(f"{city_name} {number} – {title}", f"Rank {rank}")
                          for number, title in missions if number.startswith(f"{rank}-")])
        for rank in range(1, 10)
    ] + [("Rank 10", [("Complete", "Complete")])]

TOAU_TITLES = (
    "Land of Sacred Serpents", "Immortal Sentries", "President Salaheem", "Knight of Gold",
    "Confessions of Royalty", "Easterly Winds", "Westerly Winds", "A Mercenary Life",
    "Undersea Scouting", "Astral Waves", "Imperial Schemes", "Royal Puppeteer",
    "Lost Kingdom", "The Dolphin Crest", "The Black Coffin", "Ghosts of the Past",
    "Guests of the Empire", "Passing Glory", "Sweets for the Soul", "Teahouse Tumult",
    "Finders Keepers", "Shield of Diplomacy", "Social Graces", "Foiled Ambition",
    "Playing the Part", "Seal of the Serpent", "Misplaced Nobility", "Bastion of Knowledge",
    "Puppet in Peril", "Prevalence of Pirates", "Shades of Vengeance", "In the Blood",
    "Sentinels' Honor", "Testing the Waters", "Legacy of the Lost", "Gaze of the Saboteur",
    "Path of Darkness", "Fangs of the Lion", "Nashmeira's Plea", "The Rider Cometh",
    "Unraveling Reason", "Light of Judgment", "Path of Blood", "Stirrings of War",
    "The Final Battle", "The Wyrm God", "Eternal Mercenary", "Imperial Coronation",
)
MISSION_OPTIONS["TOAU"] = [
    ("Treasures of Aht Urhgan", [(f"ToAU {number:02d} – {title}", f"ToAU {number:02d}")
                                  for number, title in enumerate(TOAU_TITLES, 1)] + [("Complete", "Complete")])
]

ZILART_MISSION_MIGRATIONS = {
    "ZM1 – Through the Quicksand Caves": "ZM6 – Through the Quicksand Caves",
    "ZM2 – The Chamber of Oracles": "ZM7 – The Chamber of Oracles",
    "ZM3 – Return to Delkfutt's Tower": "ZM8 – Return to Delkfutt's Tower",
    "ZM4 – Ro'Maeve": "ZM9 – Ro'Maeve",
    "ZM5 – The Temple of Desolation": "ZM10 – The Temple of Desolation",
    "ZM6 – Hall of the Gods": "ZM11 – The Hall of the Gods",
    "ZM7 – The Mithra and the Crystal": "ZM12 – The Mithra and the Crystal",
    "ZM8 – The Gate of the Gods": "ZM13 – The Gate of the Gods",
    "ZM9 – Ark Angels": "ZM14 – Ark Angels",
    "ZM10 – The Sealed Shrine": "ZM15 – The Sealed Shrine",
    "ZM11 – The Celestial Nexus": "ZM16 – The Celestial Nexus",
    "ZM12 – Awakening": "ZM17 – Awakening",
    "ZM13 – The Last Verse (epilogue shared with CoP after Apocalypse Nigh)":
        "ZM18 – The Last Verse (epilogue shared with CoP after Apocalypse Nigh)",
}

COP_MISSION_MIGRATIONS = {
    "CoP 7-1 – One to Be Feared":
        ("CoP 6-4 – One to Be Feared", "Chapter 6 – Echoes of Time"),
    "CoP 7-2 – Chains and Bonds":
        ("CoP 7-1 – Chains and Bonds", "Chapter 7 – In the Light of the Crystal"),
    "CoP 7-3 – Flames in the Darkness":
        ("CoP 7-2 – Flames in the Darkness", "Chapter 7 – In the Light of the Crystal"),
}


def fetch_horizon_player(name):
    """Fetch a public character profile without exposing arbitrary URLs."""
    if not re.fullmatch(r"[A-Za-z]{2,15}", name):
        raise ValueError("Enter a valid HorizonXI character name.")
    req = Request(
        f"{HORIZON_API}/chars/{quote(name)}",
        headers={"Accept": "application/json", "User-Agent": "MissionsLinkshellRoster/1.0"},
    )
    with urlopen(req, timeout=6) as response:
        return json.load(response)


def split_mission(campaign, mission, chapter=""):
    """Return a compact mission number and readable mission title."""
    if mission == "Complete":
        return "Complete", "Campaign complete"
    if " – " in mission:
        number, title = mission.split(" – ", 1)
        return number, title
    if campaign == "COP" and mission.endswith("Path"):
        return "CoP 5-3", mission
    return chapter or campaign, mission


def mission_wiki_url(title):
    """Return the direct BG Wiki page for a displayed mission title."""
    if title in {"Not selected", "Campaign complete"}:
        return ""
    page_title = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
    page_slug = quote(page_title.replace(" ", "_"), safe="()'_")
    return f"https://www.bg-wiki.com/ffxi/{page_slug}"


def build_progress_board(campaign, rows):
    by_mission = {}
    for row in rows:
        by_mission.setdefault(row["mission"], []).append(row)

    board = [{
        "number": "—",
        "title": "Not selected",
        "wiki_url": "",
        "members": by_mission.get("", []),
    }]
    known = set()
    for _group, options in MISSION_OPTIONS[campaign]:
        for mission, chapter in options:
            known.add(mission)
            number, title = split_mission(campaign, mission, chapter)
            board.append({
                "number": number,
                "title": title,
                "wiki_url": mission_wiki_url(title),
                "members": by_mission.get(mission, []),
            })

    # Preserve older/custom entries rather than hiding their members.
    for mission, members in by_mission.items():
        if mission and mission not in known:
            number, title = split_mission(campaign, mission, members[0]["chapter"])
            board.append({"number": number, "title": title, "wiki_url": mission_wiki_url(title), "members": members})
    return board


def parse_local_datetime(value):
    """Parse an HTML local datetime into the app's consistently stored ISO form."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(second=0, microsecond=0)
    except ValueError:
        return None


def normalize_event_bot_listing(payload):
    """Return event dictionaries from the private bot's supported list envelopes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("events", "data", "results"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        if isinstance(items, dict):
            return [
                {"message_id": identifier, **item}
                for identifier, item in items.items() if isinstance(item, dict)
            ]
    if isinstance(payload.get("event"), dict):
        return [payload["event"]]
    return []


def event_bot_channel(record):
    """Extract a Discord channel name or ID from an event-bot response."""
    if not isinstance(record, dict):
        return ""
    nested = record.get("event") if isinstance(record.get("event"), dict) else {}
    item = {**record, **nested}
    value = item.get("channel_name") or item.get("channel") or item.get("channel_id") or ""
    if isinstance(value, dict):
        value = value.get("name") or value.get("id") or ""
    return str(value).strip()[:100]


def parse_event_bot_record(record):
    """Normalize an event-bot record into the website's guild-event fields."""
    nested = record.get("event") if isinstance(record.get("event"), dict) else {}
    item = {**record, **nested}
    message_id = str(
        item.get("discord_message_id") or item.get("message_id") or
        item.get("messageId") or ""
    ).strip()
    discord_event_id = str(
        item.get("discord_event_id") or item.get("scheduled_event_id") or
        item.get("scheduledEventId") or item.get("event_id") or ""
    ).strip()
    name = str(item.get("name") or item.get("event_name") or item.get("title") or "").strip()
    name = re.sub(r"[*_`]", "", name)
    name = re.sub(r"^\s*[^\w]*Hokuten Knights\s*[—–-]\s*", "", name, flags=re.I).strip()
    name = re.sub(r"\s+\d{1,2}:\d{2}\s*(?:AM|PM)(?:\s*(?:EST|EDT|ET))?\s*$", "", name, flags=re.I)

    start_value = str(
        item.get("start_at") or item.get("start") or item.get("starts_at") or
        item.get("scheduled_start_time") or item.get("datetime") or ""
    ).strip()
    start_at = None
    if start_value:
        try:
            parsed = datetime.fromisoformat(start_value.replace("Z", "+00:00"))
            start_at = parsed.astimezone(EASTERN_TIME).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            start_at = None
    if not start_at:
        date_value = str(item.get("date") or item.get("event_date") or "").strip()
        time_value = str(item.get("time") or item.get("event_time") or "").strip()
        combined = f"{date_value} {time_value}".strip()
        for pattern in (
            "%A %B %d %Y %I:%M %p", "%B %d %Y %I:%M %p",
            "%A, %B %d, %Y %I:%M %p", "%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M",
        ):
            try:
                start_at = datetime.strptime(combined, pattern)
                break
            except ValueError:
                continue
    if not name or not start_at:
        return None
    end_at = None
    end_value = str(
        item.get("end_at") or item.get("end") or item.get("ends_at") or
        item.get("scheduled_end_time") or ""
    ).strip()
    if end_value:
        try:
            parsed_end = datetime.fromisoformat(end_value.replace("Z", "+00:00"))
            end_at = parsed_end.astimezone(EASTERN_TIME).replace(tzinfo=None) if parsed_end.tzinfo else parsed_end
        except ValueError:
            end_at = None
    if not end_at:
        try:
            duration_hours = float(item.get("duration") or item.get("duration_hours") or 3)
        except (TypeError, ValueError):
            duration_hours = 3
        end_at = start_at + timedelta(hours=max(.25, min(duration_hours, 24)))
    duration_hours = max(0, (end_at - start_at).total_seconds() / 3600)
    dkp_value = max(1, int(duration_hours + .5))
    description = str(item.get("description") or item.get("details") or "").strip()[:1000]
    location = str(
        item.get("location") or item.get("gather_location") or item.get("gatherLocation") or
        "Hokuten Knights"
    ).strip()[:100]
    channel = event_bot_channel(record) or "endgame-events-only"
    return {
        "name": name[:100], "description": description,
        "start_at": start_at.replace(second=0, microsecond=0),
        "end_at": end_at.replace(second=0, microsecond=0),
        "dkp_value": dkp_value,
        "location": location or "Hokuten Knights",
        "discord_event_id": discord_event_id, "discord_message_id": message_id,
        "discord_channel": channel,
    }


def eastern_today():
    return datetime.now(EASTERN_TIME).date()


def eastern_now_naive():
    """Return the linkshell's current Eastern time for naive event timestamps."""
    return datetime.now(EASTERN_TIME).replace(tzinfo=None, second=0, microsecond=0)


def request_occurs_on(help_request, day):
    """Return whether a request appears on a day without materializing occurrences."""
    if help_request["status"] not in ACTIVE_HELP_STATUSES:
        return False
    expires = parse_local_datetime(help_request["expires_at"])
    if expires and datetime.combine(day, time.max) > expires and day > expires.date():
        return False
    start = parse_local_datetime(help_request["start_at"])
    end = parse_local_datetime(help_request["end_at"])
    mode = help_request["availability_mode"]
    today = eastern_today()
    if mode == "now":
        return day == today
    if mode == "fixed":
        return bool(start and day == start.date())
    if mode == "range":
        return bool(start and end and start.date() <= day <= end.date())
    first_day = start.date() if start else today
    if mode == "after" and day > today + timedelta(days=6):
        return False
    return first_day <= day and (not expires or day <= expires.date())


def discord_exchange_code(client_id, client_secret, code, redirect_uri):
    payload = urlencode({
        "client_id": client_id, "client_secret": client_secret,
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": redirect_uri,
    }).encode("utf-8")
    oauth_request = Request(
        "https://discord.com/api/v10/oauth2/token", data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "HokutenKnightsDashboard/1.0"},
    )
    with urlopen(oauth_request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def discord_get(access_token, path):
    api_request = Request(
        f"https://discord.com/api/v10{path}",
        headers={"Authorization": f"Bearer {access_token}",
                 "User-Agent": "HokutenKnightsDashboard/1.0"},
    )
    with urlopen(api_request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
        DATABASE=os.path.join(app.instance_path, "missions.db"),
        EDIT_PASSWORD=os.environ.get("EDIT_PASSWORD", "Hokuten"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "Idonthave1"),
        DISCORD_CLIENT_ID=os.environ.get("DISCORD_CLIENT_ID", ""),
        DISCORD_CLIENT_SECRET=os.environ.get("DISCORD_CLIENT_SECRET", ""),
        DISCORD_GUILD_ID=os.environ.get("DISCORD_GUILD_ID", ""),
        DISCORD_REDIRECT_URI=os.environ.get("DISCORD_REDIRECT_URI", ""),
        DISCORD_ADMIN_USER_ID=os.environ.get("DISCORD_ADMIN_USER_ID", ""),
        DISCORD_BOT_TOKEN=os.environ.get("DISCORD_BOT_TOKEN", ""),
        DISCORD_EVENT_CHANNEL_ID=os.environ.get("DISCORD_EVENT_CHANNEL_ID", ""),
        HOKUTEN_EVENT_BOT_API_URL=os.environ.get("HOKUTEN_EVENT_BOT_API_URL", ""),
        HOKUTEN_EVENT_BOT_API_TOKEN=os.environ.get("HOKUTEN_EVENT_BOT_API_TOKEN", ""),
        CANONICAL_HOST=os.environ.get("CANONICAL_HOST", "hokutenknights.com"),
        ROSTER_REFRESH_TOKEN=os.environ.get("ROSTER_REFRESH_TOKEN", ""),
        PSXI_API_TOKEN=os.environ.get("PSXI_API_TOKEN", ""),
        PSXI_MARKET_CACHE=os.path.join(app.instance_path, "psxi_market_snapshot.json"),
        LOCAL_ADMIN_BYPASS=os.environ.get("LOCAL_ADMIN_BYPASS", "").lower() in {"1", "true", "yes"},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
    )
    if test_config:
        app.config.update(test_config)
        if test_config.get("TESTING"):
            for key in ("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_GUILD_ID", "DISCORD_REDIRECT_URI", "DISCORD_ADMIN_USER_ID", "DISCORD_BOT_TOKEN", "DISCORD_EVENT_CHANNEL_ID", "HOKUTEN_EVENT_BOT_API_URL", "HOKUTEN_EVENT_BOT_API_TOKEN"):
                if key not in test_config:
                    app.config[key] = ""
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    @app.before_request
    def redirect_www_to_canonical_host():
        canonical_host = str(app.config.get("CANONICAL_HOST", "")).strip().lower()
        request_host = request.host.partition(":")[0].lower()
        if canonical_host and request_host == f"www.{canonical_host}":
            target = f"https://{canonical_host}{request.path}"
            if request.query_string:
                target += f"?{request.query_string.decode('latin-1')}"
            return redirect(target, code=308)

    def local_admin_bypass_enabled():
        """Allow the opted-in local development server to act as Imaven only."""
        return bool(
            app.config.get("LOCAL_ADMIN_BYPASS")
            and (not app.config.get("TESTING") or app.config.get("ALLOW_LOCAL_ADMIN_BYPASS_FOR_TESTS"))
            and request.remote_addr in {"127.0.0.1", "::1"}
        )

    @app.before_request
    def sign_in_local_admin():
        if not local_admin_bypass_enabled():
            return None
        imaven = get_db().execute(
            "SELECT id FROM members WHERE name='Imaven' COLLATE NOCASE"
        ).fetchone()
        if imaven:
            session["member_id"] = imaven["id"]
            session["is_editor"] = True
            session["is_admin"] = True
            csrf_token()

    def is_editor():
        if app.config.get("AUTH_DISABLED"):
            return True
        if not (session.get("is_editor") or session.get("is_admin")):
            return False
        member_id = current_member_id()
        return bool(member_id and get_db().execute(
            "SELECT 1 FROM members WHERE id=?", (member_id,)
        ).fetchone())

    def is_admin():
        if app.config.get("AUTH_DISABLED") and current_member_id() is None:
            return True
        member_id = current_member_id()
        if not member_id:
            return False
        member = get_db().execute(
            "SELECT name, discord_user_id, discord_admin FROM members WHERE id=?",
            (member_id,),
        ).fetchone()
        return bool(member and (session.get("is_admin") or (discord_ready() and (
            member["discord_admin"]
            or (member["discord_user_id"] and member["name"].casefold() in {
                name.casefold() for name in DISCORD_ADMIN_CHARACTERS
            })
        ))))

    def discord_ready():
        return all(app.config.get(key) for key in (
            "DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_GUILD_ID",
            "DISCORD_ADMIN_USER_ID",
        ))

    def current_member_id():
        value = session.get("member_id")
        return int(value) if value is not None else None

    def current_member_name():
        member_id = current_member_id()
        if not member_id:
            return "Administrator" if is_admin() else ""
        member = get_db().execute("SELECT name FROM members WHERE id=?", (member_id,)).fetchone()
        return member["name"] if member else ("Administrator" if is_admin() else "")

    def can_create_guild_events():
        return bool(
            is_admin()
            and current_member_id()
            and current_member_name().casefold() in {
                name.casefold() for name in DISCORD_ADMIN_CHARACTERS
            }
        )

    def editor_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not is_editor():
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not is_admin():
                abort(403, description="Administrator access is required.")
            return view(*args, **kwargs)
        return wrapped

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals.update(
        csrf_token=csrf_token, is_editor=is_editor, is_admin=is_admin,
        current_member_id=current_member_id, current_member_name=current_member_name,
        discord_ready=discord_ready, can_create_guild_events=can_create_guild_events,
    )

    @app.before_request
    def protect_posts():
        if (request.method == "POST" and request.endpoint != "refresh_job_roster_api"
                and not app.config.get("AUTH_DISABLED")):
            supplied = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(supplied, expected):
                if request.endpoint == "login":
                    destination = request.form.get("next", "")
                    session.clear()
                    flash("Your sign-in page expired. Please enter your password again.", "error")
                    return redirect(url_for("login", next=destination))
                abort(400, description="Invalid or expired form token. Go back, refresh, and try again.")

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if local_admin_bypass_enabled():
            destination = request.values.get("next", "")
            return redirect(destination if destination.startswith("/") and not destination.startswith("//") else url_for("help_board"))
        if discord_ready():
            return redirect(url_for("discord_connect", next=request.values.get("next", "")))
        if request.method == "POST":
            configured = app.config.get("EDIT_PASSWORD", "")
            admin_password = app.config.get("ADMIN_PASSWORD", "")
            supplied = request.form.get("password", "")
            admin_login = bool(admin_password and hmac.compare_digest(supplied, admin_password))
            member_login = bool(not discord_ready() and (
                hmac.compare_digest(supplied, "Hokuten")
                or (configured and hmac.compare_digest(supplied, configured))
            ))
            if admin_login or member_login:
                session.clear()
                session["is_admin"] = admin_login
                session["is_editor"] = member_login
                member_id = request.form.get("member_id", "")
                if member_login and request.form.get("action") == "add_player":
                    name = request.form.get("new_member_name", "").strip()
                    if not re.fullmatch(r"[A-Za-z]{2,15}", name):
                        flash("Enter a valid HorizonXI character name (2–15 letters).", "error")
                        session.clear()
                        return redirect(url_for("login", next=request.form.get("next", "")))
                    db = get_db()
                    existing = db.execute("SELECT id, name FROM members WHERE name=?", (name,)).fetchone()
                    if existing:
                        session["member_id"] = existing["id"]
                        name = existing["name"]
                    else:
                        cursor = db.execute("INSERT INTO members(name) VALUES (?)", (name,))
                        db.commit()
                        session["member_id"] = cursor.lastrowid
                    flash(f"Added and signed in as {name}.", "success")
                elif member_login and member_id.isdigit():
                    session["member_id"] = int(member_id)
                elif member_login and request.form.get("action") == "sign_in":
                    session.clear()
                    flash("Choose your character or add a new player.", "error")
                    return redirect(url_for("login", next=request.form.get("next", "")))
                csrf_token()
                destination = request.form.get("next", "")
                if not destination.startswith("/") or destination.startswith("//"):
                    destination = url_for("help_board")
                return redirect(destination)
            flash("Incorrect linkshell password.", "error")
        members = get_db().execute(
            f"""SELECT id, name FROM members
                ORDER BY CASE name {''.join(f'WHEN ? THEN {index} ' for index in range(len(LOGIN_CHARACTERS)))}
                ELSE {len(LOGIN_CHARACTERS)} END, name COLLATE NOCASE""",
            LOGIN_CHARACTERS,
        ).fetchall()
        return render_template(
            "login.html", next=request.args.get("next", ""), members=members,
            discord_enabled=discord_ready(),
        )

    @app.get("/discord/connect")
    def discord_connect():
        return render_template(
            "discord_connect.html", next=request.args.get("next", ""),
            oauth_available=discord_ready(),
        )

    @app.post("/discord/login")
    def discord_login():
        if not discord_ready():
            flash("Discord sign-in has not been configured yet.", "error")
            return redirect(url_for("discord_connect"))
        state = secrets.token_urlsafe(32)
        session["discord_oauth_state"] = state
        destination = request.form.get("next", "")
        session["discord_oauth_next"] = destination if destination.startswith("/") and not destination.startswith("//") else ""
        redirect_uri = app.config.get("DISCORD_REDIRECT_URI") or url_for("discord_callback", _external=True)
        query = urlencode({
            "response_type": "code",
            "client_id": app.config["DISCORD_CLIENT_ID"],
            "scope": "identify guilds.members.read",
            "state": state,
            "redirect_uri": redirect_uri,
            "prompt": "consent",
        })
        return redirect(f"https://discord.com/oauth2/authorize?{query}")

    @app.get("/discord/callback")
    def discord_callback():
        supplied_state = request.args.get("state", "")
        expected_state = session.pop("discord_oauth_state", "")
        if not supplied_state or not expected_state or not hmac.compare_digest(supplied_state, expected_state):
            abort(400, description="Invalid or expired Discord sign-in state. Please try again.")
        code = request.args.get("code", "")
        if not code:
            flash("Discord sign-in was cancelled.", "error")
            return redirect(url_for("discord_connect"))
        redirect_uri = app.config.get("DISCORD_REDIRECT_URI") or url_for("discord_callback", _external=True)
        try:
            token = discord_exchange_code(
                app.config["DISCORD_CLIENT_ID"], app.config["DISCORD_CLIENT_SECRET"],
                code, redirect_uri,
            )
            access_token = token["access_token"]
            discord_user = discord_get(access_token, "/users/@me")
        except HTTPError as error:
            app.logger.warning("Discord account verification failed with HTTP %s", error.code)
            flash(
                f"Discord could not verify your account (HTTP {error.code}). "
                "Check the Discord Client Secret and callback URL, then try again.",
                "error",
            )
            return redirect(url_for("discord_connect"))
        except (URLError, KeyError, ValueError, json.JSONDecodeError) as error:
            error_kind = type(error).__name__
            app.logger.warning("Discord account verification failed: %s", error_kind)
            flash(
                f"Discord could not verify your account ({error_kind}). "
                "Please try signing in again.",
                "error",
            )
            return redirect(url_for("discord_connect"))

        try:
            guild_member = discord_get(
                access_token,
                f"/users/@me/guilds/{app.config['DISCORD_GUILD_ID']}/member",
            )
        except (HTTPError, URLError, KeyError, ValueError, json.JSONDecodeError):
            bot_token = app.config.get("DISCORD_BOT_TOKEN", "")
            if not bot_token:
                flash("Discord could not verify your Hokuten membership. Make sure you joined the server and try again.", "error")
                return redirect(url_for("discord_connect"))
            try:
                guild_member = discord_bot_request(
                    bot_token, "GET",
                    f"/guilds/{app.config['DISCORD_GUILD_ID']}/members/{discord_user['id']}",
                )
            except (HTTPError, URLError, KeyError, ValueError, json.JSONDecodeError):
                flash("Discord could not verify your Hokuten membership. Make sure you joined the server and try again.", "error")
                return redirect(url_for("discord_connect"))

        discord_user_id = str(discord_user.get("id", ""))
        nickname = (
            guild_member.get("nick")
            or discord_user.get("global_name")
            or discord_user.get("username")
            or ""
        ).strip()
        if not discord_user_id:
            flash("Discord did not return a valid account ID.", "error")
            return redirect(url_for("discord_connect"))
        admin_discord_user_id = str(app.config["DISCORD_ADMIN_USER_ID"])
        is_discord_admin = discord_user_id == admin_discord_user_id
        if nickname.casefold() == "imaven" and not is_discord_admin:
            flash("The Imaven character is reserved for its verified Discord account.", "error")
            return redirect(url_for("discord_connect"))
        db = get_db()
        member = db.execute(
            "SELECT * FROM members WHERE discord_user_id=?", (discord_user_id,)
        ).fetchone()
        linked_member_before_login = member is not None
        if member and member["name"].casefold() == "imaven" and not is_discord_admin:
            flash("The Imaven character is reserved for its verified Discord account.", "error")
            return redirect(url_for("discord_connect"))
        created = False
        if is_discord_admin:
            imaven = db.execute(
                "SELECT * FROM members WHERE name='Imaven' COLLATE NOCASE"
            ).fetchone()
            if member and member["id"] != imaven["id"]:
                db.execute(
                    "UPDATE members SET discord_user_id='', discord_admin=0 WHERE id=?",
                    (member["id"],),
                )
            discord_label = discord_user.get("global_name") or discord_user.get("username") or "Imaven"
            db.execute(
                "UPDATE members SET discord_user_id=?, discord_name=?, discord_admin=1, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (discord_user_id, discord_label, imaven["id"]),
            )
            db.commit()
            member = db.execute("SELECT * FROM members WHERE id=?", (imaven["id"],)).fetchone()
        if member is None:
            if not re.fullmatch(r"[A-Za-z]{2,15}", nickname):
                flash(
                    "Set your Hokuten server nickname or Discord display name to your exact HorizonXI character name "
                    "(2–15 letters only), then try again.", "error",
                )
                return redirect(url_for("discord_connect"))
            member = db.execute(
                "SELECT * FROM members WHERE name=? COLLATE NOCASE", (nickname,)
            ).fetchone()
            if member and member["discord_user_id"]:
                flash("That character is already linked to another Discord account.", "error")
                return redirect(url_for("discord_connect"))
            discord_label = discord_user.get("global_name") or discord_user.get("username") or nickname
            if member:
                db.execute(
                    "UPDATE members SET discord_user_id=?, discord_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (discord_user_id, discord_label, member["id"]),
                )
            else:
                cursor = db.execute(
                    "INSERT INTO members(name,discord_name,discord_user_id) VALUES(?,?,?)",
                    (nickname, discord_label, discord_user_id),
                )
                member = db.execute("SELECT * FROM members WHERE id=?", (cursor.lastrowid,)).fetchone()
                created = True
            db.commit()
            member = db.execute("SELECT * FROM members WHERE id=?", (member["id"],)).fetchone()

        is_discord_admin = bool(
            is_discord_admin or (
                linked_member_before_login
                and
                member["discord_user_id"]
                and member["name"].casefold()
                in {name.casefold() for name in DISCORD_ADMIN_CHARACTERS[1:]}
            )
        )
        db.execute("UPDATE members SET discord_admin=? WHERE id=?",
                   (int(is_discord_admin), member["id"]))
        db.commit()

        destination = session.pop("discord_oauth_next", "")
        session.clear()
        session["is_editor"] = True
        session["is_admin"] = is_discord_admin
        session["member_id"] = member["id"]
        csrf_token()
        if created:
            flash(f"Welcome, {member['name']}! Your roster entry was created. Add your jobs and progress.", "success")
            return redirect(url_for("member_form", member_id=member["id"]))
        flash(f"Signed in with Discord as {member['name']}.", "success")
        return redirect(destination or url_for("help_board"))

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.post("/identity")
    @editor_required
    def set_identity():
        member_id = request.form.get("member_id", "")
        member = get_db().execute("SELECT id FROM members WHERE id=?", (member_id,)).fetchone()
        if not member:
            abort(400, description="Choose a valid linkshell character.")
        session["member_id"] = member["id"]
        destination = request.form.get("next", "")
        if not destination.startswith("/") or destination.startswith("//"):
            destination = url_for("help_board")
        return redirect(destination)

    @app.post("/identity/new")
    @editor_required
    def add_identity():
        name = request.form.get("name", "").strip()
        if not re.fullmatch(r"[A-Za-z]{2,15}", name):
            flash("Enter a valid HorizonXI character name (2–15 letters).", "error")
            return redirect(url_for("help_board"))
        db = get_db()
        try:
            cursor = db.execute("INSERT INTO members(name) VALUES (?)", (name,))
            db.commit()
            session["member_id"] = cursor.lastrowid
            flash(f"Added and selected {name}.", "success")
        except sqlite3.IntegrityError:
            db.rollback()
            existing = db.execute("SELECT id, name FROM members WHERE name=?", (name,)).fetchone()
            if existing:
                session["member_id"] = existing["id"]
                flash(f"Selected existing character {existing['name']}.", "success")
            else:
                flash("That character could not be added.", "error")
        return redirect(url_for("help_board"))

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        with app.open_resource("schema.sql") as schema:
            get_db().executescript(schema.read().decode("utf8"))
        member_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(members)")
        }
        if "discord_user_id" not in member_columns:
            get_db().execute("ALTER TABLE members ADD COLUMN discord_user_id TEXT NOT NULL DEFAULT ''")
        if "discord_admin" not in member_columns:
            get_db().execute("ALTER TABLE members ADD COLUMN discord_admin INTEGER NOT NULL DEFAULT 0")
        member_job_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(member_jobs)")
        }
        if "bring" not in member_job_columns:
            get_db().execute("ALTER TABLE member_jobs ADD COLUMN bring INTEGER NOT NULL DEFAULT 1")
        guild_event_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(guild_events)")
        }
        if "discord_message_id" not in guild_event_columns:
            get_db().execute(
                "ALTER TABLE guild_events ADD COLUMN discord_message_id TEXT NOT NULL DEFAULT ''"
            )
        if "discord_channel" not in guild_event_columns:
            get_db().execute(
                "ALTER TABLE guild_events ADD COLUMN discord_channel TEXT NOT NULL DEFAULT 'endgame-events-only'"
            )
        if "dkp_value" not in guild_event_columns:
            get_db().execute(
                "ALTER TABLE guild_events ADD COLUMN dkp_value REAL NOT NULL DEFAULT 3"
            )
        loot_award_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(endgame_loot_awards)")
        }
        if "dkp_cost" not in loot_award_columns:
            get_db().execute(
                "ALTER TABLE endgame_loot_awards ADD COLUMN dkp_cost REAL NOT NULL DEFAULT 0"
            )
        if "auction_id" not in loot_award_columns:
            get_db().execute("ALTER TABLE endgame_loot_awards ADD COLUMN auction_id INTEGER")
        if "auction_item_id" not in loot_award_columns:
            get_db().execute("ALTER TABLE endgame_loot_awards ADD COLUMN auction_item_id INTEGER")
        payout_columns = {row["name"] for row in get_db().execute("PRAGMA table_info(dynamis_payouts)")}
        for column, definition in {
            "zone": "TEXT NOT NULL DEFAULT ''",
            "whiteshell_quantity": "INTEGER NOT NULL DEFAULT 0",
            "bronzepiece_quantity": "INTEGER NOT NULL DEFAULT 0",
            "byne_single_quantity": "INTEGER NOT NULL DEFAULT 0",
            "whiteshell_market_value": "INTEGER NOT NULL DEFAULT 0",
            "bronzepiece_market_value": "INTEGER NOT NULL DEFAULT 0",
            "byne_single_market_value": "INTEGER NOT NULL DEFAULT 0",
            "whiteshell_actual_sale": "INTEGER",
            "bronzepiece_actual_sale": "INTEGER",
            "byne_single_actual_sale": "INTEGER",
        }.items():
            if payout_columns and column not in payout_columns:
                get_db().execute(f"ALTER TABLE dynamis_payouts ADD COLUMN {column} {definition}")
        bank_columns = {row["name"] for row in get_db().execute("PRAGMA table_info(ls_bank_items)")}
        if bank_columns and "sale_channel" not in bank_columns:
            get_db().execute("ALTER TABLE ls_bank_items ADD COLUMN sale_channel TEXT NOT NULL DEFAULT ''")
        if bank_columns and "used_event_id" not in bank_columns:
            get_db().execute("ALTER TABLE ls_bank_items ADD COLUMN used_event_id INTEGER")
        if bank_columns and "purchaser_member_id" not in bank_columns:
            get_db().execute("ALTER TABLE ls_bank_items ADD COLUMN purchaser_member_id INTEGER")
            get_db().execute(
                """UPDATE ls_bank_items SET purchaser_member_id=holder_member_id
                   WHERE acquisition_kind NOT IN ('Event Drop','Donation')"""
            )
        get_db().execute(
            """UPDATE ls_bank_items SET status='Held'
               WHERE status='Purchased' AND used_event_id IS NULL AND notes NOT LIKE '%Used:%'"""
        )
        bank_table_sql = (get_db().execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='ls_bank_items'"
        ).fetchone() or {"sql": ""})["sql"] or ""
        if bank_columns and ("Purchased" not in bank_table_sql or "'Pop Item'" in bank_table_sql or "'Mercenary'" not in bank_table_sql):
            # SQLite cannot alter a CHECK constraint in place.  Preserve every
            # treasury row while widening the status/source choices.
            get_db().execute("DROP INDEX IF EXISTS idx_ls_bank_status")
            get_db().execute("ALTER TABLE ls_bank_items RENAME TO ls_bank_items_legacy")
            get_db().execute(
                """CREATE TABLE ls_bank_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, item TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
                    acquisition_kind TEXT NOT NULL CHECK(acquisition_kind IN ('Event Drop','Auction House','Bazaar','Donation','Other','Mercenary')),
                    status TEXT NOT NULL DEFAULT 'Held' CHECK(status IN ('Held','Purchased','Sold')),
                    purchase_gil INTEGER NOT NULL DEFAULT 0 CHECK(purchase_gil >= 0),
                    sale_gil INTEGER NOT NULL DEFAULT 0 CHECK(sale_gil >= 0),
                    sale_channel TEXT NOT NULL DEFAULT '' CHECK(sale_channel IN ('','Auction House','Bazaar')),
                    holder_member_id INTEGER, purchaser_member_id INTEGER, used_event_id INTEGER, acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, sold_at TEXT,
                    notes TEXT NOT NULL DEFAULT '', recorded_by INTEGER, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (event_id) REFERENCES guild_events(id) ON DELETE SET NULL,
                    FOREIGN KEY (holder_member_id) REFERENCES members(id) ON DELETE SET NULL,
                    FOREIGN KEY (purchaser_member_id) REFERENCES members(id) ON DELETE SET NULL,
                    FOREIGN KEY (used_event_id) REFERENCES guild_events(id) ON DELETE SET NULL,
                    FOREIGN KEY (recorded_by) REFERENCES members(id) ON DELETE SET NULL
                )"""
            )
            get_db().execute(
                """INSERT INTO ls_bank_items(id,event_id,item,quantity,acquisition_kind,status,purchase_gil,sale_gil,
                                                sale_channel,holder_member_id,purchaser_member_id,used_event_id,acquired_at,sold_at,notes,recorded_by,updated_at)
                   SELECT id,event_id,item,quantity,CASE acquisition_kind
                              WHEN 'Purchase' THEN 'Auction House' WHEN 'Pop Item' THEN 'Other'
                              WHEN 'Timeless Hourglass' THEN 'Other' WHEN 'Merc Sell' THEN 'Mercenary'
                              WHEN 'Manual' THEN 'Other' ELSE acquisition_kind END,status,purchase_gil,sale_gil,
                          COALESCE(sale_channel,''),holder_member_id,COALESCE(purchaser_member_id,holder_member_id),used_event_id,acquired_at,sold_at,notes,recorded_by,updated_at
                   FROM ls_bank_items_legacy"""
            )
            get_db().execute("DROP TABLE ls_bank_items_legacy")
            get_db().execute("CREATE INDEX IF NOT EXISTS idx_ls_bank_status ON ls_bank_items(status, acquired_at DESC)")
        # Timeless Hourglasses are purchased inventory, not event drops.  Also
        # keep true event drops from carrying purchase-only accounting.
        get_db().execute(
            """UPDATE ls_bank_items SET acquisition_kind='Other',event_id=NULL
               WHERE (lower(item) LIKE '%timeless%hourglass%'
                      OR lower(item) LIKE '%timeless%hrglass%')
                 AND (acquisition_kind<>'Other' OR event_id IS NOT NULL)"""
        )
        get_db().execute(
            """UPDATE ls_bank_items SET purchase_gil=0,purchaser_member_id=NULL
               WHERE acquisition_kind='Event Drop'"""
        )
        get_db().execute(
            """UPDATE endgame_loot_awards AS award SET auction_id=(
                   SELECT auction.id FROM endgame_auction_items item
                   JOIN endgame_auctions auction ON auction.id=item.auction_id
                   WHERE auction.event_id=award.event_id AND item.item=award.item
                   ORDER BY auction.id DESC LIMIT 1
               ) WHERE auction_id IS NULL"""
        )
        get_db().execute(
            """UPDATE endgame_loot_awards SET item=CASE lower(item)
                   WHEN 'w hands' THEN 'Crimson Finger Gauntlets'
                   WHEN 'n hands' THEN 'Hecatomb Mittens'
                   WHEN 'd legs' THEN 'Shura Haidate'
               END
               WHERE event_id IN (SELECT id FROM guild_events WHERE substr(start_at,1,10)='2026-08-20')
               AND lower(item) IN ('w hands','n hands','d legs')"""
        )
        get_db().execute(
            """UPDATE endgame_loot_awards AS award SET auction_item_id=(
                   SELECT item.id FROM endgame_auction_items item
                   WHERE item.auction_id=award.auction_id
                     AND (item.item=award.item OR item.target_item=award.item)
                   ORDER BY item.id LIMIT 1
               ) WHERE auction_id IS NOT NULL AND auction_item_id IS NULL"""
        )
        auction_item_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(endgame_auction_items)")
        }
        if auction_item_columns and "target_item" not in auction_item_columns:
            get_db().execute(
                "ALTER TABLE endgame_auction_items ADD COLUMN target_item TEXT NOT NULL DEFAULT ''"
            )
        auction_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(endgame_auctions)")
        }
        if auction_columns and "paused_at" not in auction_columns:
            get_db().execute("ALTER TABLE endgame_auctions ADD COLUMN paused_at TEXT")
        signup_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(guild_event_signups)")
        }
        for column, definition in (
            ("rsvp_status", "TEXT NOT NULL DEFAULT 'going'"),
            ("selected_job", "TEXT NOT NULL DEFAULT ''"),
            ("discord_name", "TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in signup_columns:
                get_db().execute(f"ALTER TABLE guild_event_signups ADD COLUMN {column} {definition}")
        get_db().execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_members_discord_user_id "
            "ON members(discord_user_id) WHERE discord_user_id<>''"
        )
        progress_sql = get_db().execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='progress'"
        ).fetchone()["sql"]
        if "CHECK(campaign IN" in progress_sql:
            get_db().executescript(
                """ALTER TABLE progress RENAME TO progress_legacy;
                   CREATE TABLE progress (
                       member_id INTEGER NOT NULL,
                       campaign TEXT NOT NULL,
                       chapter TEXT NOT NULL DEFAULT '',
                       mission TEXT NOT NULL DEFAULT '',
                       status TEXT NOT NULL DEFAULT 'Not started'
                           CHECK(status IN ('Not started','In progress','Ready for help','Complete')),
                       details TEXT NOT NULL DEFAULT '',
                       PRIMARY KEY (member_id, campaign),
                       FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
                   );
                   INSERT INTO progress SELECT * FROM progress_legacy;
                   DROP TABLE progress_legacy;"""
            )
        role_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(help_request_roles)")
        }
        if "kind" not in role_columns:
            get_db().execute("ALTER TABLE help_request_roles ADD COLUMN kind TEXT NOT NULL DEFAULT 'job'")
        if "quantity" not in role_columns:
            get_db().execute("ALTER TABLE help_request_roles ADD COLUMN quantity INTEGER")
        alliance_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(alliance_events)")
        }
        if "owner_member_id" not in alliance_columns:
            get_db().execute("ALTER TABLE alliance_events ADD COLUMN owner_member_id INTEGER")
        if "guild_event_id" not in alliance_columns:
            get_db().execute("ALTER TABLE alliance_events ADD COLUMN guild_event_id INTEGER")
        for column, definition in (
            ("share_token", "TEXT NOT NULL DEFAULT ''"),
            ("share_enabled", "INTEGER NOT NULL DEFAULT 0"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
        ):
            if column not in alliance_columns:
                get_db().execute(f"ALTER TABLE alliance_events ADD COLUMN {column} {definition}")
        get_db().execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_alliance_events_share_token "
            "ON alliance_events(share_token) WHERE share_token<>''"
        )
        slot_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(alliance_slots)")
        }
        if "custom_name" not in slot_columns:
            get_db().executescript(
                """ALTER TABLE alliance_slots RENAME TO alliance_slots_legacy;
                   CREATE TABLE alliance_slots (
                       event_id INTEGER NOT NULL,
                       party_number INTEGER NOT NULL CHECK(party_number BETWEEN 1 AND 6),
                       slot_number INTEGER NOT NULL CHECK(slot_number BETWEEN 1 AND 6),
                       member_id INTEGER,
                       custom_name TEXT NOT NULL DEFAULT '',
                       job TEXT NOT NULL,
                       PRIMARY KEY (event_id, party_number, slot_number),
                       UNIQUE (event_id, member_id),
                       FOREIGN KEY (event_id) REFERENCES alliance_events(id) ON DELETE CASCADE,
                       FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
                   );
                   INSERT INTO alliance_slots(event_id,party_number,slot_number,member_id,job)
                   SELECT event_id,party_number,slot_number,member_id,job FROM alliance_slots_legacy;
                   DROP TABLE alliance_slots_legacy;"""
            )
        slot_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(alliance_slots)")
        }
        if "updated_by" not in slot_columns:
            get_db().execute("ALTER TABLE alliance_slots ADD COLUMN updated_by INTEGER")
        if "updated_at" not in slot_columns:
            get_db().execute("ALTER TABLE alliance_slots ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        slot_definition = get_db().execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='alliance_slots'"
        ).fetchone()["sql"] or ""
        if "BETWEEN 1 AND 3" in slot_definition:
            get_db().executescript(
                """ALTER TABLE alliance_slots RENAME TO alliance_slots_legacy;
                   CREATE TABLE alliance_slots (
                       event_id INTEGER NOT NULL,
                       party_number INTEGER NOT NULL CHECK(party_number BETWEEN 1 AND 6),
                       slot_number INTEGER NOT NULL CHECK(slot_number BETWEEN 1 AND 6),
                       member_id INTEGER,
                       custom_name TEXT NOT NULL DEFAULT '',
                       job TEXT NOT NULL,
                       updated_by INTEGER,
                       updated_at TEXT NOT NULL DEFAULT '',
                       PRIMARY KEY (event_id, party_number, slot_number),
                       UNIQUE (event_id, member_id),
                       FOREIGN KEY (event_id) REFERENCES alliance_events(id) ON DELETE CASCADE,
                       FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
                       FOREIGN KEY (updated_by) REFERENCES members(id) ON DELETE SET NULL
                   );
                   INSERT INTO alliance_slots
                       (event_id,party_number,slot_number,member_id,custom_name,job,updated_by,updated_at)
                   SELECT event_id,party_number,slot_number,member_id,custom_name,job,updated_by,updated_at
                   FROM alliance_slots_legacy;
                   DROP TABLE alliance_slots_legacy;"""
            )
        gear_columns = {
            row["name"] for row in get_db().execute("PRAGMA table_info(gear_ownership)")
        }
        if "quantity" not in gear_columns:
            get_db().execute(
                "ALTER TABLE gear_ownership ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1"
            )
        get_db().execute(
            "CREATE INDEX IF NOT EXISTS idx_alliance_events_owner ON alliance_events(owner_member_id, updated_at)"
        )
        get_db().executemany(
            "INSERT OR IGNORE INTO members(name) VALUES (?)",
            [(name,) for name in LOGIN_CHARACTERS],
        )
        # Fold retired character labels into their current in-game names. These
        # aliases also remain active during Discord signup matching below.
        for former_name, canonical_name in MEMBER_NAME_ALIASES.items():
            former = get_db().execute(
                "SELECT * FROM members WHERE name=? COLLATE NOCASE", (former_name,)
            ).fetchone()
            canonical = get_db().execute(
                "SELECT * FROM members WHERE name=? COLLATE NOCASE", (canonical_name,)
            ).fetchone()
            if not former:
                continue
            # Killboi was not part of the seeded roster, so a site which only
            # contains the old KB entry must rename that member in place. That
            # preserves every foreign-keyed signup, attendance, award, and DKP
            # record without requiring a second member row to exist first.
            if not canonical:
                get_db().execute(
                    "UPDATE members SET name=? WHERE id=?", (canonical_name, former["id"])
                )
                continue
            if former["id"] == canonical["id"]:
                continue
            former_id, canonical_id = former["id"], canonical["id"]
            for table, columns in (
                ("guild_event_signups", "event_id,source,rsvp_status,selected_job,discord_name,updated_at"),
                ("guild_event_attendance", "event_id,attended,updated_by,updated_at"),
                ("endgame_event_job_snapshots", "event_id,main_job,secondary_job,created_at"),
            ):
                get_db().execute(
                    f"INSERT OR IGNORE INTO {table}(member_id,{columns}) "
                    f"SELECT ?,{columns} FROM {table} WHERE member_id=?",
                    (canonical_id, former_id),
                )
            get_db().execute(
                "UPDATE endgame_loot_awards SET recipient_member_id=? WHERE recipient_member_id=?",
                (canonical_id, former_id),
            )
            get_db().execute(
                "UPDATE guild_events SET creator_member_id=? WHERE creator_member_id=?",
                (canonical_id, former_id),
            )
            get_db().execute(
                "UPDATE endgame_auctions SET created_by=? WHERE created_by=?",
                (canonical_id, former_id),
            )
            if not canonical["discord_user_id"] and former["discord_user_id"]:
                # The Discord ID is unique. Release it from the retired row
                # before assigning it to the canonical member.
                get_db().execute(
                    "UPDATE members SET discord_user_id='' WHERE id=?", (former_id,)
                )
                get_db().execute(
                    "UPDATE members SET discord_user_id=?,discord_name=? WHERE id=?",
                    (former["discord_user_id"], former["discord_name"], canonical_id),
                )
            get_db().execute("DELETE FROM members WHERE id=?", (former_id,))
        archive_events = (
            ("Sky Operations", "Imported historical event", "2026-08-06T20:00", "2026-08-06T23:00", "Ru'Aun Gardens"),
            ("Sky Operations", "Imported historical event", "2026-08-13T20:00", "2026-08-13T23:00", "Ru'Aun Gardens"),
        )
        creator_id = get_db().execute(
            "SELECT id FROM members WHERE name='Imaven' COLLATE NOCASE"
        ).fetchone()["id"]
        created_archive_events = set()
        for event_name, event_description, start_at, end_at, location in archive_events:
            if not get_db().execute(
                "SELECT 1 FROM guild_events WHERE name=? AND start_at=?", (event_name, start_at)
            ).fetchone():
                get_db().execute(
                    """INSERT INTO guild_events
                       (creator_member_id,name,description,start_at,end_at,location,status)
                       VALUES(?,?,?,?,?,?,'Completed')""",
                    (creator_id, event_name, event_description, start_at, end_at, location),
                )
                created_archive_events.add(start_at)
        archive_attendance = {
            "2026-08-06T20:00": ("Sexualpotato", "Vlathgar", "Chickenbanana", "Alecy", "Rhode", "Shiru", "Venenua", "Teeje", "Mygas", "Ivalin", "Cartuja", "Shurgajoe", "Firewater", "Anonym", "Ramenwarrior", "Hikari"),
            "2026-08-13T20:00": ("Sexualpotato", "Vlathgar", "Chickenbanana", "Alecy", "Rhode", "Shiru", "Venenua", "Teeje", "Mygas", "Ivalin", "Cartuja", "Shurgajoe", "Kaeru", "Firewater", "Anonym", "Ramenwarrior", "Eunos", "Hikari", "Gravekeeper"),
        }
        for start_at, names in archive_attendance.items():
            if start_at not in created_archive_events:
                continue
            event_id = get_db().execute(
                "SELECT id FROM guild_events WHERE name='Sky Operations' AND start_at=?", (start_at,)
            ).fetchone()["id"]
            placeholders = ",".join("?" for _ in names)
            member_ids = get_db().execute(
                f"SELECT id FROM members WHERE name IN ({placeholders})", names
            ).fetchall()
            get_db().executemany(
                """INSERT OR IGNORE INTO guild_event_attendance
                   (event_id,member_id,attended,updated_by) VALUES(?,?,1,?)""",
                [(event_id, row["id"], creator_id) for row in member_ids],
            )
        archive_loot = (
            ("2026-08-06T20:00", "Chickenbanana", "Dryadic Abjuration: Hands", "MNK", "Hands", "Main priority", "Major Loot"),
            ("2026-08-06T20:00", "Ivalin", "Aquarian Abjuration: Hands", "BLM", "Hands", "Main priority", "Major Loot"),
            ("2026-08-06T20:00", "Anonym", "Martial Abjuration: Hands", "PLD", "Hands", "Main priority", "Major Loot"),
            ("2026-08-13T20:00", "Ramenwarrior", "Martial Abjuration: Hands", "PLD", "Hands", "Main priority", "Major Loot"),
            ("2026-08-13T20:00", "Cartuja", "Genbu's Kabuto", "NIN", "Head", "Main priority", "Major Loot"),
            ("2026-08-13T20:00", "Chickenbanana", "Dryadic Abjuration: Feet", "MNK", "Feet", "Main priority", "Major Loot"),
            ("2026-08-13T20:00", "Wizzaro", "Genbu's Shield", "RDM", "Other", "Freelot", "Standard"),
            ("2026-08-13T20:00", "Vlathgar", "Aquarian Abjuration: Legs", "SMN", "Legs", "Main priority", "Major Loot"),
            ("2026-08-13T20:00", "Ramenwarrior", "Martial Abjuration: Head", "PLD", "Head", "Main priority", "Major Loot"),
        )
        for start_at, member_name, item, job, family, distribution, classification in archive_loot:
            event_id = get_db().execute(
                "SELECT id FROM guild_events WHERE name='Sky Operations' AND start_at=?", (start_at,)
            ).fetchone()["id"]
            member_id = get_db().execute(
                "SELECT id FROM members WHERE name=? COLLATE NOCASE", (member_name,)
            ).fetchone()
            if member_id and not get_db().execute(
                "SELECT 1 FROM endgame_loot_awards WHERE event_id=? AND recipient_member_id=? AND item=?",
                (event_id, member_id["id"], item),
            ).fetchone():
                get_db().execute(
                    """INSERT INTO endgame_loot_awards
                       (event_id,recipient_member_id,item,job,family,distribution,classification,recorded_by)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (event_id, member_id["id"], item, job, family, distribution, classification, creator_id),
                )
        get_db().execute(
            """UPDATE endgame_loot_awards SET distribution=''
               WHERE event_id IN (
                   SELECT id FROM guild_events WHERE start_at < '2026-08-20T00:00'
               )"""
        )
        past_test_events = get_db().execute(
            """SELECT id,name FROM guild_events
               WHERE datetime(start_at) < datetime('now')
                 AND lower(trim(name)) LIKE 'test%'"""
        ).fetchall()
        if past_test_events:
            get_db().executemany(
                "DELETE FROM guild_events WHERE id=?",
                [(row["id"],) for row in past_test_events],
            )
            get_db().execute(
                "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
                (creator_id, "Event Calendar", "Past test events removed",
                 ", ".join(row["name"] for row in past_test_events)),
            )
        # Normalize the pre-DKP event archive once. Going forward, channel origin
        # remains stable so completed Endgame events retain their DKP history.
        get_db().execute(
            """UPDATE guild_events SET discord_channel='events-posting-and-signup-only'
               WHERE start_at < '2026-08-19T00:00'
                 AND NOT (name='Sky Operations' AND substr(start_at,1,10) IN ('2026-08-06','2026-08-13'))"""
        )
        extra_admins = tuple(name.casefold() for name in DISCORD_ADMIN_CHARACTERS[1:])
        get_db().execute(
            f"UPDATE members SET discord_admin=CASE "
            f"WHEN name='Imaven' COLLATE NOCASE AND discord_user_id=? THEN 1 "
            f"WHEN lower(name) IN ({','.join('?' for _ in extra_admins)}) "
            f"AND discord_user_id<>'' THEN 1 ELSE 0 END",
            (str(app.config.get("DISCORD_ADMIN_USER_ID", "")), *extra_admins),
        )
        for old_mission, new_mission in ZILART_MISSION_MIGRATIONS.items():
            get_db().execute(
                "UPDATE progress SET mission=?, chapter=? WHERE campaign='ZILART' AND mission=?",
                (new_mission, new_mission.split(" – ", 1)[0], old_mission),
            )
        for old_mission, (new_mission, chapter) in COP_MISSION_MIGRATIONS.items():
            get_db().execute(
                "UPDATE progress SET mission=?, chapter=? WHERE campaign='COP' AND mission=?",
                (new_mission, chapter, old_mission),
            )
        for campaign in CAMPAIGNS:
            get_db().execute(
                """INSERT OR IGNORE INTO progress(member_id,campaign)
                   SELECT m.id, ? FROM members m
                   WHERE EXISTS(SELECT 1 FROM member_jobs j WHERE j.member_id=m.id)""",
                (campaign,),
            )
        get_db().commit()

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("Initialized the database.")

    def member_rows(campaign="", mission="", job="", status=""):
        db = get_db()
        clauses, params = [], []
        if campaign:
            clauses.append("p.campaign = ?")
            params.append(campaign)
        if mission:
            clauses.append("p.mission LIKE ?")
            params.append(f"%{mission}%")
        if status:
            clauses.append("p.status = ?")
            params.append(status)
        if job:
            clauses.append("EXISTS (SELECT 1 FROM member_jobs j2 WHERE j2.member_id=m.id AND j2.job=? AND j2.bring=1)")
            params.append(job)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = db.execute(
            f"""
            SELECT m.*, p.campaign, p.chapter, p.mission, p.status, p.details,
                   GROUP_CONCAT(j.job || ' ' || j.level, ', ') AS jobs
            FROM members m
            JOIN progress p ON p.member_id = m.id
            LEFT JOIN member_jobs j ON j.member_id = m.id AND j.bring=1
            {where}
            GROUP BY m.id, p.campaign
            ORDER BY CASE p.status WHEN 'Ready for help' THEN 0 WHEN 'In progress' THEN 1
                     WHEN 'Not started' THEN 2 ELSE 3 END, p.mission, m.name
            """,
            params,
        ).fetchall()
        return rows

    @app.route("/")
    def index():
        filters = {
            "campaign": request.args.get("campaign", "").upper(),
            "mission": request.args.get("mission", "").strip(),
            "job": request.args.get("job", "").upper(),
            "status": request.args.get("status", ""),
        }
        rows = member_rows(**filters)
        boards = {
            campaign: build_progress_board(
                campaign, [row for row in rows if row["campaign"] == campaign]
            )
            for campaign in CAMPAIGNS
        }
        db = get_db()
        basic_counts = db.execute(
            """SELECT (SELECT COUNT(*) FROM members) members,
                      SUM(status='Ready for help') ready,
                      COUNT(DISTINCT CASE WHEN campaign='COP' AND mission='Complete' THEN member_id END) cop_complete,
                      COUNT(DISTINCT CASE WHEN campaign='ZILART' AND mission='Complete' THEN member_id END) zilart_complete
               FROM progress"""
        ).fetchone()
        cop_order = [
            mission
            for _group, options in MISSION_OPTIONS["COP"]
            for mission, _chapter in options
        ]
        dreamlands_threshold = cop_order.index("CoP 3-5 – Darkness Named")
        dreamlands_members = {
            progress["member_id"]
            for progress in db.execute(
                "SELECT member_id, mission FROM progress WHERE campaign='COP'"
            ).fetchall()
            if progress["mission"] in cop_order
            and cop_order.index(progress["mission"]) > dreamlands_threshold
        }
        counts = dict(basic_counts)
        counts["dreamlands"] = len(dreamlands_members)
        return render_template(
            "index.html", rows=rows, counts=counts, filters=filters,
            jobs=JOBS, campaigns=CAMPAIGNS, statuses=STATUSES, boards=boards,
            campaign_names=CAMPAIGN_NAMES,
        )

    @app.route("/members/new", methods=("GET", "POST"))
    @app.route("/members/<int:member_id>/edit", methods=("GET", "POST"))
    @editor_required
    def member_form(member_id=None):
        db = get_db()
        registered_members = db.execute(
            "SELECT id, name FROM members ORDER BY name COLLATE NOCASE"
        ).fetchall()
        if member_id is None and current_member_id() is not None and not is_admin():
            member_id = current_member_id()
        if member_id is not None and not is_admin() and current_member_id() != member_id:
            abort(403, description="You may only update your own mission progress.")
        member = db.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone() if member_id else None
        if member_id and member is None:
            return ("Member not found", 404)
        existing_jobs = {
            row["job"]: row["level"]
            for row in db.execute("SELECT * FROM member_jobs WHERE member_id=?", (member_id,)).fetchall()
        } if member_id else {}
        existing_bring_jobs = {
            row["job"] for row in db.execute(
                "SELECT job FROM member_jobs WHERE member_id=? AND bring=1", (member_id,)
            ).fetchall()
        } if member_id else set()
        existing_progress = {
            row["campaign"]: row
            for row in db.execute("SELECT * FROM progress WHERE member_id=?", (member_id,)).fetchall()
        } if member_id else {}

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            selected_jobs = {}
            for job in JOBS:
                raw = request.form.get(f"job_{job}", "").strip()
                if raw:
                    try:
                        level = int(raw)
                    except ValueError:
                        level = 0
                    if not 1 <= level <= 75:
                        flash(f"{job} level must be from 1 to 75.", "error")
                        break
                    selected_jobs[job] = level
            else:
                submitted_bring_jobs = set(request.form.getlist("bring_jobs"))
                if request.form.get("bring_jobs_present"):
                    submitted_bring_jobs &= set(selected_jobs)
                else:
                    submitted_bring_jobs = set(selected_jobs)
                if not name:
                    flash("Character name is required.", "error")
                elif not selected_jobs:
                    flash("Add at least one job and level.", "error")
                else:
                    try:
                        target_member_id = member_id
                        if target_member_id is None:
                            existing_member = db.execute(
                                "SELECT id FROM members WHERE name=?", (name,)
                            ).fetchone()
                            if existing_member:
                                target_member_id = existing_member["id"]

                        if not is_admin():
                            own_member_id = current_member_id()
                            if own_member_id is not None and target_member_id not in (None, own_member_id):
                                abort(403, description="You may only update your own mission progress.")
                            if own_member_id is None and target_member_id is not None:
                                abort(403, description="Select your character before updating progress.")

                        if target_member_id:
                            target_member = db.execute(
                                "SELECT discord_user_id FROM members WHERE id=?",
                                (target_member_id,),
                            ).fetchone()
                            linked_discord_user_id = (
                                target_member["discord_user_id"] if target_member else ""
                            )
                            db.execute(
                                """UPDATE members SET name=?, discord_name=?, timezone=?, availability=?,
                                   notes=?, discord_admin=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                                (name, request.form.get("discord_name", "").strip(),
                                 request.form.get("timezone", "").strip(),
                                 request.form.get("availability", "").strip(),
                                 request.form.get("notes", "").strip(),
                                int(bool(linked_discord_user_id) and (
                                     (name.casefold() == "imaven" and linked_discord_user_id
                                      == str(app.config.get("DISCORD_ADMIN_USER_ID", "")))
                                     or name.casefold() in {
                                         value.casefold() for value in DISCORD_ADMIN_CHARACTERS[1:]
                                     }
                                 )),
                                 target_member_id),
                            )
                        else:
                            cursor = db.execute(
                                """INSERT INTO members (name, discord_name, timezone, availability, notes)
                                   VALUES (?, ?, ?, ?, ?)""",
                                (name, request.form.get("discord_name", "").strip(),
                                 request.form.get("timezone", "").strip(),
                                 request.form.get("availability", "").strip(),
                                 request.form.get("notes", "").strip()),
                            )
                            target_member_id = cursor.lastrowid
                            if not is_admin():
                                session["member_id"] = target_member_id
                        db.execute("DELETE FROM member_jobs WHERE member_id=?", (target_member_id,))
                        db.executemany(
                            "INSERT INTO member_jobs (member_id, job, level, bring) VALUES (?, ?, ?, ?)",
                            [(target_member_id, job, level, int(job in submitted_bring_jobs))
                             for job, level in selected_jobs.items()],
                        )
                        for campaign in CAMPAIGNS:
                            mission_value = request.form.get(f"{campaign}_mission", "").strip()
                            status_value = request.form.get(f"{campaign}_status", "Not started")
                            if mission_value == "Complete":
                                status_value = "Complete"
                            db.execute(
                                """INSERT INTO progress (member_id, campaign, chapter, mission, status, details)
                                   VALUES (?, ?, ?, ?, ?, ?)
                                   ON CONFLICT(member_id, campaign) DO UPDATE SET
                                   chapter=excluded.chapter, mission=excluded.mission,
                                   status=excluded.status, details=excluded.details""",
                                (target_member_id, campaign,
                                 request.form.get(f"{campaign}_chapter", "").strip(),
                                 mission_value,
                                 status_value,
                                 request.form.get(f"{campaign}_details", "").strip()),
                            )
                        db.commit()
                        flash(f"Saved {name}'s mission progress.", "success")
                        return redirect(url_for("index"))
                    except sqlite3.IntegrityError:
                        db.rollback()
                        flash("That character name is already registered.", "error")

        return render_template(
            "member_form.html", member=member, existing_jobs=existing_jobs,
            existing_bring_jobs=existing_bring_jobs,
            progress=existing_progress, jobs=JOBS, campaigns=CAMPAIGNS, statuses=STATUSES,
            mission_options=MISSION_OPTIONS, campaign_names=CAMPAIGN_NAMES,
            registered_members=registered_members,
        )

    @app.get("/members")
    @admin_required
    def members_admin():
        members = get_db().execute(
            """SELECT m.*,
                      GROUP_CONCAT(DISTINCT j.job || ' ' || j.level) jobs,
                      GROUP_CONCAT(DISTINCT p.campaign || ': ' ||
                          COALESCE(NULLIF(p.mission, ''), 'Not selected')) progress_summary
               FROM members m
               LEFT JOIN member_jobs j ON j.member_id=m.id
               LEFT JOIN progress p ON p.member_id=m.id
               GROUP BY m.id ORDER BY m.name COLLATE NOCASE"""
        ).fetchall()
        return render_template("members_admin.html", members=members)

    @app.get("/alliance-builder")
    @app.get("/alliance-builder/shared/<share_token>")
    @editor_required
    def alliance_builder(share_token=""):
        owner = require_member_identity()
        db = get_db()
        events = db.execute(
            """SELECT e.*, COUNT(s.event_id) member_count
               FROM alliance_events e LEFT JOIN alliance_slots s ON s.event_id=e.id
               WHERE e.owner_member_id=?
               GROUP BY e.id ORDER BY COALESCE(e.event_at, e.created_at) DESC, e.id DESC"""
            , (owner["id"],)
        ).fetchall()
        event = None
        shared_mode = bool(share_token)
        if shared_mode:
            event = db.execute(
                """SELECT e.*,m.name owner_name FROM alliance_events e
                   JOIN members m ON m.id=e.owner_member_id
                   WHERE e.share_token=? AND e.share_enabled=1""", (share_token,),
            ).fetchone()
            if not event:
                abort(404)
        else:
            event_id = request.args.get("event", "")
            if event_id.isdigit():
                event = db.execute(
                    "SELECT e.*,m.name owner_name FROM alliance_events e JOIN members m ON m.id=e.owner_member_id WHERE e.id=? AND e.owner_member_id=?",
                    (event_id, owner["id"]),
                ).fetchone()
                if not event:
                    abort(404)
        slot_rows = db.execute(
            """SELECT s.party_number,s.slot_number,s.member_id,s.custom_name,s.job,
                      s.updated_by,s.updated_at,m.name updated_by_name
               FROM alliance_slots s LEFT JOIN members m ON m.id=s.updated_by
               WHERE s.event_id=?""",
            (event["id"],),
        ).fetchall() if event else []
        assignments = {
            f"{row['party_number']}-{row['slot_number']}": {
                "member_id": row["member_id"] or "", "custom_name": row["custom_name"],
                "job": row["job"], "updated_by": row["updated_by"] or "",
                "updated_by_name": row["updated_by_name"] or "", "updated_at": row["updated_at"],
            }
            for row in slot_rows
        }
        member_rows = db.execute(
            """SELECT m.id,m.name,j.job,j.level FROM members m
               JOIN member_jobs j ON j.member_id=m.id
               ORDER BY m.name COLLATE NOCASE,j.level DESC,j.job"""
        ).fetchall()
        roster = {}
        for row in member_rows:
            roster.setdefault(row["id"], {"id": row["id"], "name": row["name"], "jobs": {}})
            roster[row["id"]]["jobs"][row["job"]] = row["level"]
        guild_events = []
        for row in db.execute(
            "SELECT id,name,start_at,location FROM guild_events WHERE status='Scheduled' ORDER BY start_at"
        ).fetchall():
            item = dict(row)
            event_start = parse_local_datetime(item["start_at"])
            item["is_upcoming"] = bool(
                event_start and event_start >= eastern_now_naive()
            )
            signups = db.execute(
                """SELECT member_id,rsvp_status,selected_job,discord_name
                   FROM guild_event_signups WHERE event_id=?""", (row["id"],)
            ).fetchall()
            item["signup_ids"] = [signup["member_id"] for signup in signups
                                  if signup["rsvp_status"] in ("going", "maybe")]
            item["signup_details"] = {
                str(signup["member_id"]): {
                    "status": signup["rsvp_status"], "job": signup["selected_job"],
                    "discord_name": signup["discord_name"],
                }
                for signup in signups if signup["rsvp_status"] in ("going", "maybe")
            }
            guild_events.append(item)
        guild_events = (
            sorted((item for item in guild_events if item["is_upcoming"]), key=lambda item: item["start_at"])
            + sorted((item for item in guild_events if not item["is_upcoming"]),
                     key=lambda item: item["start_at"], reverse=True)
        )
        change_history = [dict(row) for row in db.execute(
            """SELECT l.action,l.details,l.created_at,COALESCE(m.name,'Unknown member') actor
               FROM alliance_change_log l LEFT JOIN members m ON m.id=l.actor_member_id
               WHERE l.event_id=? ORDER BY l.id DESC LIMIT 20""", (event["id"],),
        ).fetchall()] if event else []
        share_url = url_for("alliance_builder", share_token=event["share_token"], _external=True) \
            if event and event["share_enabled"] and event["share_token"] else ""
        return render_template(
            "alliance_builder.html", events=events, event=event,
            assignments=assignments, roster=list(roster.values()), jobs=JOBS,
            role_jobs=ALLIANCE_ROLE_JOBS, owner=owner, guild_events=guild_events,
            shared_mode=shared_mode, share_url=share_url, change_history=change_history,
            has_second_alliance=any(row["party_number"] > 3 for row in slot_rows),
            event_bot_sync_enabled=bool(
                app.config.get("HOKUTEN_EVENT_BOT_API_URL") and
                app.config.get("HOKUTEN_EVENT_BOT_API_TOKEN")
            ),
        )

    @app.post("/alliance-builder/save")
    @editor_required
    def save_alliance():
        owner = require_member_identity()
        name = request.form.get("name", "").strip()
        if not name or len(name) > 80:
            abort(400, description="Enter an event name up to 80 characters.")
        event_at_value = request.form.get("event_at", "").strip()
        event_at = parse_local_datetime(event_at_value)
        if event_at_value and (not event_at or event_at.minute % 15):
            abort(400, description="Choose an event time in a 15-minute interval.")
        notes = request.form.get("notes", "").strip()[:1000]
        db = get_db()
        guild_event_value = request.form.get("guild_event_id", "").strip()
        guild_event_id = None
        if guild_event_value:
            if not guild_event_value.isdigit() or not db.execute(
                "SELECT 1 FROM guild_events WHERE id=?", (guild_event_value,)
            ).fetchone():
                abort(400, description="Choose a valid guild event.")
            guild_event_id = int(guild_event_value)
        event_id = request.form.get("event_id", "")
        share_token = request.form.get("share_token", "").strip()
        event_version = request.form.get("version", "")
        if event_id:
            if not event_id.isdigit() or not event_version.isdigit():
                abort(404)
            existing = db.execute(
                "SELECT * FROM alliance_events WHERE id=?", (event_id,)
            ).fetchone()
            if not existing or not (
                existing["owner_member_id"] == owner["id"]
                or (share_token and existing["share_enabled"] and
                    hmac.compare_digest(existing["share_token"], share_token))
            ):
                abort(404)
            updated = db.execute(
                """UPDATE alliance_events SET name=?,event_at=?,notes=?,guild_event_id=?,
                          version=version+1,updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND version=?""",
                (name, event_at.isoformat(timespec="minutes") if event_at else None, notes, guild_event_id,
                 event_id, int(event_version)),
            )
            if updated.rowcount != 1:
                db.rollback()
                flash("This shared alliance changed after you opened it. Reloaded the newest version; review it before saving again.", "error")
                if share_token:
                    return redirect(url_for("alliance_builder", share_token=share_token))
                return redirect(url_for("alliance_builder", event=event_id))
            event_id = int(event_id)
        else:
            event_id = db.execute(
                "INSERT INTO alliance_events(owner_member_id,guild_event_id,name,event_at,notes) VALUES(?,?,?,?,?)",
                (owner["id"], guild_event_id, name, event_at.isoformat(timespec="minutes") if event_at else None, notes),
            ).lastrowid

        roster_jobs = {
            (row["member_id"], row["job"]): row["level"]
            for row in db.execute("SELECT member_id,job,level FROM member_jobs")
        }
        selected_members = set()
        slots = []
        for party_number in range(1, 7):
            for slot_number in range(1, 7):
                member_value = request.form.get(f"member_{party_number}_{slot_number}", "").strip()
                custom_name = request.form.get(f"custom_name_{party_number}_{slot_number}", "").strip()
                job = request.form.get(f"job_{party_number}_{slot_number}", "").strip().upper()
                if not member_value and not custom_name and not job:
                    continue
                if custom_name:
                    if member_value or not job or len(custom_name) > 40 or job not in JOBS:
                        abort(400, description="Enter a valid custom character name and job.")
                    slots.append((event_id, party_number, slot_number, None, custom_name, job, owner["id"]))
                    continue
                if not member_value.isdigit():
                    abort(400, description="Choose a valid roster member for every occupied slot.")
                member_id = int(member_value)
                if (member_id, job) not in roster_jobs:
                    abort(400, description="The selected member does not have that job in the roster.")
                if member_id in selected_members:
                    abort(400, description="A character can only occupy one alliance slot.")
                selected_members.add(member_id)
                slots.append((event_id, party_number, slot_number, member_id, "", job, owner["id"]))
        try:
            db.execute("DELETE FROM alliance_slots WHERE event_id=?", (event_id,))
            db.executemany(
                """INSERT INTO alliance_slots
                   (event_id,party_number,slot_number,member_id,custom_name,job,updated_by,updated_at)
                   VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                slots,
            )
            db.execute(
                """INSERT INTO alliance_change_log(event_id,actor_member_id,action,details)
                   VALUES(?,?,?,?)""",
                (event_id, owner["id"], "Layout saved", f"{len(slots)} of 36 slots assigned"),
            )
            db.commit()
        except sqlite3.DatabaseError:
            db.rollback()
            raise
        flash(f"Saved alliance layout for {name}.", "success")
        if share_token:
            return redirect(url_for("alliance_builder", share_token=share_token))
        return redirect(url_for("alliance_builder", event=event_id))

    @app.post("/alliance-builder/<int:event_id>/share")
    @editor_required
    def share_alliance(event_id):
        owner = require_member_identity()
        db = get_db()
        event = db.execute(
            "SELECT * FROM alliance_events WHERE id=? AND owner_member_id=?",
            (event_id, owner["id"]),
        ).fetchone()
        if not event:
            abort(404)
        token = event["share_token"]
        if not token:
            while True:
                token = secrets.token_urlsafe(9)
                if not db.execute(
                    "SELECT 1 FROM alliance_events WHERE share_token=?", (token,)
                ).fetchone():
                    break
        db.execute(
            "UPDATE alliance_events SET share_token=?,share_enabled=1 WHERE id=?",
            (token, event_id),
        )
        db.execute(
            """INSERT INTO alliance_change_log(event_id,actor_member_id,action,details)
               VALUES(?,?,?,?)""", (event_id, owner["id"], "Sharing enabled", "Collaborative link created"),
        )
        db.commit()
        flash("Collaborative link enabled. Anyone signed into the linkshell site with the link can edit this layout.", "success")
        return redirect(url_for("alliance_builder", share_token=token))

    @app.post("/alliance-builder/<int:event_id>/share/revoke")
    @editor_required
    def revoke_alliance_share(event_id):
        owner = require_member_identity()
        db = get_db()
        event = db.execute(
            "SELECT name FROM alliance_events WHERE id=? AND owner_member_id=?",
            (event_id, owner["id"]),
        ).fetchone()
        if not event:
            abort(404)
        db.execute(
            "UPDATE alliance_events SET share_enabled=0,share_token='' WHERE id=?", (event_id,)
        )
        db.execute(
            """INSERT INTO alliance_change_log(event_id,actor_member_id,action,details)
               VALUES(?,?,?,?)""", (event_id, owner["id"], "Sharing revoked", "Collaborative link disabled"),
        )
        db.commit()
        flash("Collaborative access was revoked. The old link no longer works.", "success")
        return redirect(url_for("alliance_builder", event=event_id))

    @app.post("/alliance-builder/shared/<share_token>/duplicate")
    @editor_required
    def duplicate_shared_alliance(share_token):
        owner = require_member_identity()
        db = get_db()
        source = db.execute(
            "SELECT * FROM alliance_events WHERE share_token=? AND share_enabled=1", (share_token,),
        ).fetchone()
        if not source:
            abort(404)
        event_id = db.execute(
            """INSERT INTO alliance_events(owner_member_id,guild_event_id,name,event_at,notes)
               VALUES(?,?,?,?,?)""",
            (owner["id"], source["guild_event_id"], f"Copy of {source['name']}"[:80],
             source["event_at"], source["notes"]),
        ).lastrowid
        db.execute(
            """INSERT INTO alliance_slots
               (event_id,party_number,slot_number,member_id,custom_name,job,updated_by,updated_at)
               SELECT ?,party_number,slot_number,member_id,custom_name,job,?,CURRENT_TIMESTAMP
               FROM alliance_slots WHERE event_id=?""", (event_id, owner["id"], source["id"]),
        )
        db.execute(
            """INSERT INTO alliance_change_log(event_id,actor_member_id,action,details)
               VALUES(?,?,?,?)""", (event_id, owner["id"], "Layout duplicated", f"Copied from {source['name']}"),
        )
        db.commit()
        flash("Created a private copy in your saved layouts.", "success")
        return redirect(url_for("alliance_builder", event=event_id))

    def alliance_live_payload(db, event_id):
        event = db.execute("SELECT version FROM alliance_events WHERE id=?", (event_id,)).fetchone()
        slots = [dict(row) for row in db.execute(
            """SELECT s.party_number,s.slot_number,s.member_id,s.custom_name,s.job,
                      s.updated_by,s.updated_at,COALESCE(m.name,'') updated_by_name
               FROM alliance_slots s LEFT JOIN members m ON m.id=s.updated_by
               WHERE s.event_id=? ORDER BY s.party_number,s.slot_number""", (event_id,),
        ).fetchall()]
        active = [dict(row) for row in db.execute(
            """SELECT p.member_id,m.name,p.last_seen FROM alliance_presence p
               JOIN members m ON m.id=p.member_id
               WHERE p.event_id=? AND p.last_seen>=datetime('now','-15 seconds')
               ORDER BY m.name COLLATE NOCASE""", (event_id,),
        ).fetchall()]
        return {"version": event["version"], "slots": slots, "active_editors": active}

    @app.get("/alliance-builder/shared/<share_token>/live")
    @editor_required
    def shared_alliance_live(share_token):
        member = require_member_identity()
        db = get_db()
        event = db.execute(
            "SELECT id FROM alliance_events WHERE share_token=? AND share_enabled=1", (share_token,),
        ).fetchone()
        if not event:
            abort(404)
        db.execute(
            """INSERT INTO alliance_presence(event_id,member_id,last_seen)
               VALUES(?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(event_id,member_id) DO UPDATE SET last_seen=CURRENT_TIMESTAMP""",
            (event["id"], member["id"]),
        )
        db.execute("DELETE FROM alliance_presence WHERE last_seen<datetime('now','-1 day')")
        db.commit()
        return jsonify(alliance_live_payload(db, event["id"]))

    @app.post("/alliance-builder/shared/<share_token>/live")
    @editor_required
    def save_shared_alliance_live(share_token):
        actor = require_member_identity()
        db = get_db()
        event = db.execute(
            "SELECT id,version FROM alliance_events WHERE share_token=? AND share_enabled=1",
            (share_token,),
        ).fetchone()
        if not event:
            abort(404)
        db.execute(
            """INSERT INTO alliance_presence(event_id,member_id,last_seen)
               VALUES(?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(event_id,member_id) DO UPDATE SET last_seen=CURRENT_TIMESTAMP""",
            (event["id"], actor["id"]),
        )
        payload = request.get_json(silent=True) or {}
        expected_version = payload.get("version")
        submitted = payload.get("slots")
        if not isinstance(expected_version, int) or not isinstance(submitted, list) or len(submitted) > 36:
            abort(400, description="Invalid collaborative alliance update.")
        roster_jobs = {
            (row["member_id"], row["job"]) for row in db.execute(
                "SELECT member_id,job FROM member_jobs"
            )
        }
        desired = {}
        selected_members = set()
        for item in submitted:
            if not isinstance(item, dict):
                abort(400, description="Invalid alliance slot.")
            party = item.get("party_number")
            slot = item.get("slot_number")
            member_value = str(item.get("member_id") or "").strip()
            custom_name = str(item.get("custom_name") or "").strip()
            job = str(item.get("job") or "").strip().upper()
            if not isinstance(party, int) or party not in range(1, 7) or not isinstance(slot, int) or slot not in range(1, 7):
                abort(400, description="Invalid alliance position.")
            if custom_name:
                if member_value or len(custom_name) > 40 or job not in JOBS:
                    abort(400, description="Invalid custom alliance member.")
                value = (None, custom_name, job)
            else:
                if not member_value.isdigit():
                    abort(400, description="Invalid roster member.")
                member_id = int(member_value)
                if (member_id, job) not in roster_jobs or member_id in selected_members:
                    abort(400, description="Invalid or duplicate roster assignment.")
                selected_members.add(member_id)
                value = (member_id, "", job)
            if (party, slot) in desired:
                abort(400, description="Duplicate alliance position.")
            desired[(party, slot)] = value
        current = {
            (row["party_number"], row["slot_number"]):
                (row["member_id"], row["custom_name"], row["job"])
            for row in db.execute(
                "SELECT party_number,slot_number,member_id,custom_name,job FROM alliance_slots WHERE event_id=?",
                (event["id"],),
            )
        }
        changed = {position for position in set(current) | set(desired)
                   if current.get(position) != desired.get(position)}
        if not changed:
            return jsonify(alliance_live_payload(db, event["id"]))
        updated = db.execute(
            """UPDATE alliance_events SET version=version+1,updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND version=?""", (event["id"], expected_version),
        )
        if updated.rowcount != 1:
            db.rollback()
            latest = alliance_live_payload(db, event["id"])
            return jsonify({**latest, "conflict": True}), 409
        db.executemany(
            "DELETE FROM alliance_slots WHERE event_id=? AND party_number=? AND slot_number=?",
            [(event["id"], party, slot) for party, slot in changed],
        )
        additions = [
            (event["id"], party, slot, *desired[(party, slot)], actor["id"])
            for party, slot in changed if (party, slot) in desired
        ]
        if additions:
            db.executemany(
                """INSERT INTO alliance_slots
                   (event_id,party_number,slot_number,member_id,custom_name,job,updated_by,updated_at)
                   VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""", additions,
            )
        db.execute(
            """INSERT INTO alliance_change_log(event_id,actor_member_id,action,details)
               VALUES(?,?,?,?)""",
            (event["id"], actor["id"], "Live party update", f"Changed {len(changed)} slot(s)"),
        )
        db.commit()
        return jsonify(alliance_live_payload(db, event["id"]))

    @app.post("/alliance-builder/<int:event_id>/delete")
    @editor_required
    def delete_alliance(event_id):
        owner = require_member_identity()
        db = get_db()
        event = db.execute(
            "SELECT name FROM alliance_events WHERE id=? AND owner_member_id=?",
            (event_id, owner["id"]),
        ).fetchone()
        if not event:
            abort(404)
        db.execute("DELETE FROM alliance_events WHERE id=? AND owner_member_id=?",
                   (event_id, owner["id"]))
        db.commit()
        flash(f"Deleted alliance layout for {event['name']}.", "success")
        return redirect(url_for("alliance_builder"))

    @app.get("/job-roster")
    def job_roster():
        db = get_db()
        members = list(db.execute(
            """SELECT m.id, m.name, m.updated_at FROM members m
               WHERE EXISTS(SELECT 1 FROM member_jobs j WHERE j.member_id=m.id)
               ORDER BY m.name COLLATE NOCASE"""
        ).fetchall())
        levels = {
            member["id"]: {
                row["job"]: row["level"]
                for row in db.execute(
                    "SELECT job, level FROM member_jobs WHERE member_id=?", (member["id"],)
                ).fetchall()
            }
            for member in members
        }
        level_75_counts = {
            job: sum(levels[member["id"]].get(job) == 75 for member in members)
            for job in JOBS
        }
        filter_job = request.args.get("job", "").upper()
        if filter_job not in JOBS:
            filter_job = ""
        try:
            min_level = int(request.args.get("min_level", "1"))
            if not 1 <= min_level <= 75:
                raise ValueError
        except ValueError:
            min_level = 1
        if filter_job:
            members = [
                member for member in members
                if levels[member["id"]].get(filter_job, 0) >= min_level
            ]
        sort_job = request.args.get("sort", "").upper()
        if sort_job not in JOBS:
            sort_job = filter_job
        direction = "asc" if request.args.get("direction") == "asc" else "desc"
        if sort_job:
            members.sort(
                key=lambda member: (
                    levels[member["id"]].get(sort_job, 0), member["name"].casefold()
                ),
                reverse=direction == "desc",
            )
        elif request.args.get("sort") == "name" and direction == "desc":
            members.reverse()
        return render_template(
            "job_roster.html", members=members, levels=levels,
            jobs=JOBS, filter_job=filter_job, min_level=min_level,
            sort_job=sort_job, direction=direction, level_75_counts=level_75_counts,
        )

    def is_dynamis_payout_event(event):
        """Whether an Endgame calendar event can have a Dynamis payout sheet."""
        return bool(
            event and is_endgame_guild_event(event) and "dynamis" in " ".join(
                str(event.get(field, "")) for field in ("name", "location", "description")
            ).casefold()
        )

    def dynamis_payout_market_values():
        """Get per-item PSXI estimates without making the payout tracker depend on a live request."""
        names = ("Lungo-Nango Jadeshell", "Montiont Silverpiece", "100 Byne Bill",
                 "T. Whiteshell", "O. Bronzepiece", "Byne Bill")
        # PSXI abbreviates the two Dynamis 100 currencies and calls the
        # single denomination "1 Byne Bill" in its market feed.
        market_names = {
            "Lungo-Nango Jadeshell": {"Lungo-Nango Jadeshell", "L. Jadeshell"},
            "Montiont Silverpiece": {"Montiont Silverpiece", "M. Silverpiece"},
            "100 Byne Bill": {"100 Byne Bill"},
            "T. Whiteshell": {"T. Whiteshell"},
            "O. Bronzepiece": {"O. Bronzepiece"},
            "Byne Bill": {"Byne Bill", "1 Byne Bill"},
        }
        values = {name: 0 for name in names}
        try:
            snapshot = market_snapshot(
                app.config["PSXI_MARKET_CACHE"], app.config.get("PSXI_API_TOKEN", "")
            )
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            return values
        for price in snapshot.get("prices", {}).values():
            name = str(price.get("name", ""))
            payout_name = next((key for key, aliases in market_names.items() if name in aliases), None)
            if not payout_name:
                continue
            for candidate in (price.get("bazaar_lowest"), price.get("single_recent_average"), price.get("single_average"), price.get("single_last")):
                try:
                    numeric = int(float(candidate))
                except (TypeError, ValueError):
                    continue
                if numeric >= 0:
                    values[payout_name] = numeric
                    break
        return values

    def payout_gil_value(raw, allow_blank=False):
        raw = str(raw if raw is not None else "").strip()
        if allow_blank and not raw:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return -1
        return value if 0 <= value <= 2_000_000_000 else -1

    @app.get("/endgame")
    @editor_required
    def endgame_dashboard():
        """Interactive prototype for the linkshell's endgame operations hub."""
        roster_source = (
            ("Sexualpotato", "BLM", "", 2, 2), ("Vlathgar", "SMN", "MNK", 2, 2),
            ("Soyabean", "BST", "", 2, 2), ("Chickenbanana", "MNK", "", 2, 2),
            ("Alecy", "RDM", "", 2, 1), ("Rhode", "WAR", "DRK", 2, 1),
            ("Shiru", "SMN", "RDM", 2, 0), ("Venenua", "RNG", "", 2, 2),
            ("Teeje", "BRD", "", 2, 2), ("Mygas", "THF", "NIN", 2, 2),
            ("Starnack", "WHM", "SMN", 2, 0), ("HMP", "RDM", "", 2, 0),
            ("Ivalin", "BLM", "THF", 2, 2), ("Cartuja", "NIN", "BLM", 2, 2),
            ("Thorkell", "MNK", "", 2, 0), ("Shurgajoe", "NIN", "PLD", 2, 2),
            ("Zanth", "BLM", "", 2, 0), ("Zaelin", "PLD", "DRG", 2, 0),
            ("Kaeru", "NIN", "THF", 2, 1), ("Firewater", "RNG", "", 2, 2),
            ("Anonym", "PLD", "", 2, 2), ("Ramenwarrior", "PLD", "", 2, 2),
            ("Kalindra", "SMN", "", 2, 0), ("Eunos", "THF", "BRD", 2, 1),
            ("Brewski", "BLM", "DRG", 2, 0), ("Bodom", "SAM", "", 2, 2),
            ("Werx", "BST", "", 2, 0), ("Hikari", "DRG", "WHM", 2, 2),
            ("Gravekeeper", "WAR", "", 2, 1), ("Boshu", "RNG", "", 2, 2),
            ("Chonk", "RDM", "BLM", 2, 1), ("Desier", "WHM", "", 2, 1),
            ("Wizzaro", "RDM", "", 2, 1), ("Anshul", "", "", 2, 1),
            ("Escii", "BRD", "THF", 2, 1), ("Imaven", "", "", 2, 2),
            ("Tarantula", "", "", 2, 2),
        )
        wins = {
            "Chickenbanana": (2, "08/13/2026", True),
            "Ramenwarrior": (2, "08/13/2026", True),
            "Vlathgar": (1, "08/13/2026", True),
            "Cartuja": (1, "08/13/2026", True),
            "Ivalin": (1, "08/06/2026", False),
            "Anonym": (1, "08/06/2026", False),
        }
        registration_overrides = {
            row["name"].casefold(): (row["main_job"], row["secondary_job"])
            for row in get_db().execute(
                """SELECT m.name,r.main_job,r.secondary_job FROM endgame_job_registrations r
                   JOIN members m ON m.id=r.member_id"""
            ).fetchall()
        }
        job_change_reviews = {
            row["member_id"]: row["reviewed_at"]
            for row in get_db().execute(
                """SELECT member_id,MAX(reviewed_at) reviewed_at
                   FROM endgame_job_change_requests
                   WHERE status='Approved' AND reviewed_at>=datetime('now','-30 days')
                   GROUP BY member_id"""
            ).fetchall()
        }
        dynamis_registrations = {
            row["member_id"]: (row["main_job"], row["secondary_job"])
            for row in get_db().execute(
                "SELECT member_id,main_job,secondary_job FROM dynamis_lot_registrations"
            ).fetchall()
        }
        dynamis_change_reviews = {
            row["member_id"]: row["reviewed_at"]
            for row in get_db().execute(
                """SELECT member_id,MAX(reviewed_at) reviewed_at
                   FROM dynamis_lot_change_requests
                   WHERE status='Approved' AND reviewed_at>=datetime('now','-30 days')
                   GROUP BY member_id"""
            ).fetchall()
        }
        roster_job_levels = {}
        for row in get_db().execute("SELECT member_id,job,level FROM member_jobs").fetchall():
            roster_job_levels.setdefault(row["member_id"], {})[row["job"]] = row["level"]
        prototype_roster = []
        for name, main_job, secondary_job, eligible, attended in roster_source:
            main_job, secondary_job = registration_overrides.get(
                name.casefold(), (main_job, secondary_job)
            )
            percentage = round(attended * 100 / eligible) if eligible else 0
            major_wins, last_win, cooldown = wins.get(name, (0, "—", False))
            member_row = get_db().execute(
                "SELECT id FROM members WHERE name=? COLLATE NOCASE", (name,)
            ).fetchone()
            if not member_row:
                # Historical attendance defaults are not membership records.
                # Once an officer removes a member, never let this legacy list
                # recreate them in Member Detail or the Dynamis directory.
                continue
            member_id = member_row["id"]
            reviewed_at = job_change_reviews.get(member_id)
            job_cooldown_until = ""
            job_cooldown_label = ""
            if reviewed_at:
                expires_at = datetime.fromisoformat(reviewed_at) + timedelta(days=30)
                remaining_seconds = max(0, int((expires_at - datetime.utcnow()).total_seconds()))
                if remaining_seconds:
                    days, remainder = divmod(remaining_seconds, 86400)
                    hours = remainder // 3600
                    job_cooldown_until = expires_at.isoformat(timespec="seconds") + "Z"
                    job_cooldown_label = f"Job change: {days}d {hours}h remaining"
            prototype_roster.append({
                "id": member_id,
                "name": name, "main_job": main_job, "secondary_job": secondary_job,
                "eligible": eligible, "attended": attended, "attendance": percentage,
                "tier": 1 if percentage >= 75 else 2 if percentage >= 50 else 3,
                "major_wins": major_wins, "last_major_win": last_win,
                "cooldown": cooldown, "job_cooldown_until": job_cooldown_until,
                "job_cooldown_label": job_cooldown_label,
                "job_levels": roster_job_levels.get(member_id, {}),
            })
        # Dynamis is built from the complete member table.  Keep Member Detail
        # in sync by adding any member absent from the historical baseline
        # roster (for example, members added after that snapshot).
        roster_member_ids = {member["id"] for member in prototype_roster if member["id"]}
        for member_row in get_db().execute("SELECT id,name FROM members ORDER BY name COLLATE NOCASE").fetchall():
            if member_row["id"] in roster_member_ids:
                continue
            main_job, secondary_job = registration_overrides.get(member_row["name"].casefold(), ("", ""))
            prototype_roster.append({
                "id": member_row["id"], "name": member_row["name"],
                "main_job": main_job, "secondary_job": secondary_job,
                "eligible": 0, "attended": 0, "attendance": 0, "tier": 3,
                "major_wins": 0, "last_major_win": "â€”", "cooldown": False,
                "job_cooldown_until": "", "job_cooldown_label": "",
                "job_levels": roster_job_levels.get(member_row["id"], {}),
            })
        prototype_roster.sort(key=lambda member: member["name"].casefold())
        prototype_loot = (
            {"date": "08/06/2026", "player": "Chickenbanana", "item": "Dryadic Abjuration: Hands", "family": "Hands", "major": True, "job": "MNK", "award": "Main priority"},
            {"date": "08/06/2026", "player": "Ivalin", "item": "Aquarian Abjuration: Hands", "family": "Hands", "major": True, "job": "BLM", "award": "Main priority"},
            {"date": "08/06/2026", "player": "Anonym", "item": "Martial Abjuration: Hands", "family": "Hands", "major": True, "job": "PLD", "award": "Main priority"},
            {"date": "08/13/2026", "player": "Ramenwarrior", "item": "Martial Abjuration: Hands", "family": "Hands", "major": True, "job": "PLD", "award": "Main priority"},
            {"date": "08/13/2026", "player": "Cartuja", "item": "Genbu's Kabuto", "family": "Head", "major": True, "job": "NIN", "award": "Main priority"},
            {"date": "08/13/2026", "player": "Chickenbanana", "item": "Dryadic Abjuration: Feet", "family": "Feet", "major": True, "job": "MNK", "award": "Main priority"},
            {"date": "08/13/2026", "player": "Wizzaro", "item": "Genbu's Shield", "family": "Other", "major": False, "job": "RDM", "award": "Freelot"},
            {"date": "08/13/2026", "player": "Vlathgar", "item": "Aquarian Abjuration: Legs", "family": "Legs", "major": True, "job": "SMN", "award": "Main priority"},
            {"date": "08/13/2026", "player": "Ramenwarrior", "item": "Martial Abjuration: Head", "family": "Head", "major": True, "job": "PLD", "award": "Main priority"},
        )
        pop_items = (
            {"key": "gem-east", "area": "Sky", "name": "Gem of the East", "source": "Steam Cleaner"},
            {"key": "springstone", "area": "Sky", "name": "Springstone", "source": "Mother Globe"},
            {"key": "gem-south", "area": "Sky", "name": "Gem of the South", "source": "Brigandish Blade"},
            {"key": "summerstone", "area": "Sky", "name": "Summerstone", "source": "Faust"},
            {"key": "gem-west", "area": "Sky", "name": "Gem of the West", "source": "Despot"},
            {"key": "autumnstone", "area": "Sky", "name": "Autumnstone", "source": "Ullikummi"},
            {"key": "gem-north", "area": "Sky", "name": "Gem of the North", "source": "Zipacna"},
            {"key": "winterstone", "area": "Sky", "name": "Winterstone", "source": "Olla Grande"},
            {"key": "seal-seiryu", "area": "Sky", "name": "Seal of Seiryu", "source": "Seiryu"},
            {"key": "seal-suzaku", "area": "Sky", "name": "Seal of Suzaku", "source": "Suzaku"},
            {"key": "seal-byakko", "area": "Sky", "name": "Seal of Byakko", "source": "Byakko"},
            {"key": "seal-genbu", "area": "Sky", "name": "Seal of Genbu", "source": "Genbu"},
            {"key": "curtana", "area": "Sky", "name": "Curtana", "source": "Treasure Coffer"},
            {"key": "diorite", "area": "Sky", "name": "Diorite", "source": "Aura Statue"},
            {"key": "romeave-water", "area": "Sky", "name": "Ro'Maeve Water", "source": "Aura Pot"},
            {"key": "ghrah-chip", "area": "Sea", "name": "Ghrah M Chip", "source": "Ghrah", "bundle": 12},
            {"key": "hq-euvhi", "area": "Sea", "name": "High-Quality Euvhi Organ", "source": "Euvhi"},
            {"key": "first-virtue", "area": "Sea", "name": "First Virtue", "source": "Jailer of Temperance"},
            {"key": "second-virtue", "area": "Sea", "name": "Second Virtue", "source": "Jailer of Fortitude"},
            {"key": "third-virtue", "area": "Sea", "name": "Third Virtue", "source": "Jailer of Faith"},
            {"key": "deed-moderation", "area": "Sea", "name": "Deed of Moderation", "source": "Ix'aern (DRK)"},
            {"key": "deed-placidity", "area": "Sea", "name": "Deed of Placidity", "source": "Ix'aern (MNK)"},
            {"key": "deed-sensibility", "area": "Sea", "name": "Deed of Sensibility", "source": "Ix'aern (DRG)"},
            {"key": "hq-xzomit", "area": "Sea", "name": "High-Quality Xzomit Organ", "source": "Xzomit"},
            {"key": "hq-phuabo", "area": "Sea", "name": "High-Quality Phuabo Organ", "source": "Phuabo"},
            {"key": "hq-hpemde", "area": "Sea", "name": "High-Quality Hpemde Organ", "source": "Hpemde"},
            {"key": "fourth-virtue", "area": "Sea", "name": "Fourth Virtue", "source": "Jailer of Justice"},
            {"key": "fifth-virtue", "area": "Sea", "name": "Fifth Virtue", "source": "Jailer of Hope"},
            {"key": "sixth-virtue", "area": "Sea", "name": "Sixth Virtue", "source": "Jailer of Prudence"},
        )
        pop_targets = (
            {"area": "Sky", "name": "Seiryu", "requires": ("gem-east", "springstone")},
            {"area": "Sky", "name": "Suzaku", "requires": ("gem-south", "summerstone")},
            {"area": "Sky", "name": "Byakko", "requires": ("gem-west", "autumnstone")},
            {"area": "Sky", "name": "Genbu", "requires": ("gem-north", "winterstone")},
            {"area": "Sky", "name": "Kirin", "requires": ("seal-seiryu", "seal-suzaku", "seal-byakko", "seal-genbu")},
            {"area": "Sea", "name": "Jailer of Fortitude", "requires": ("ghrah-chip:12",)},
            {"area": "Sea", "name": "Jailer of Faith", "requires": ("hq-euvhi",)},
            {"area": "Sea", "name": "Jailer of Justice", "requires": ("second-virtue", "deed-moderation", "hq-xzomit")},
            {"area": "Sea", "name": "Jailer of Hope", "requires": ("first-virtue", "deed-placidity", "hq-phuabo")},
            {"area": "Sea", "name": "Jailer of Prudence", "requires": ("third-virtue", "deed-sensibility", "hq-hpemde")},
            {"area": "Sea", "name": "Jailer of Love", "requires": ("fourth-virtue", "fifth-virtue", "sixth-virtue")},
        )
        priority_items = [dict(item) for item in ENDGAME_PRIORITY_ITEMS]
        item_families = {
            "Byakko's Haidate": "Legs", "Byakko's Axe": "Weapons", "Hecatomb Mittens": "Hands", "Shura Haidate": "Legs",
            "Zenith Crown": "Head", "Seiryu's Kote": "Hands", "Seiryu's Sword": "Weapons", "Crimson Finger Gauntlets": "Hands",
            "Zenith Slacks": "Legs", "Shura Zunari Kabuto": "Head", "Koenig Schaller": "Head", "Suzaku's Sune-Ate": "Feet",
            "Hecatomb Leggings": "Feet", "Shura Kote": "Hands", "Adaman Celata": "Head", "Adaman Sollerets": "Feet", "Genbu's Shield": "Other",
            "Genbu's Kabuto": "Head", "Zenith Mitts": "Hands", "Koenig Handschuhs": "Hands", "Crimson Greaves": "Feet",
            "Kirin's Osode": "Body", "Kirin's Pole": "Weapons", "Shura Togi": "Body", "Hecatomb Harness": "Body", "Crimson Cuisses": "Legs",
        }
        for priority_item in priority_items:
            priority_item["family"] = item_families.get(priority_item["name"], "Accessories")
        required_levels = gear_required_levels(
            str(Path(app.root_path) / "static" / "gear_catalog.json")
        )
        for priority_item in priority_items:
            priority_item["required_level"] = required_levels.get(priority_item["name"], 1)
        loot_catalog = sorted(
            [dict(item) for item in (*ENDGAME_PRIORITY_ITEMS, *ENDGAME_AUCTION_EXTRA_DROPS)],
            key=lambda item: (item["area"], item["source"], item["name"]),
        )
        for item in loot_catalog:
            item["family"] = item_families.get(item["name"], auction_item_family(item["name"]))
        guild_events = []
        for row in get_db().execute(
            """SELECT e.*, m.name creator_name,
                      COUNT(DISTINCT s.member_id) signup_count,
                      COUNT(DISTINCT CASE WHEN s.rsvp_status='going' THEN s.member_id END) going_count,
                      COUNT(DISTINCT CASE WHEN s.rsvp_status='maybe' THEN s.member_id END) maybe_count,
                      COUNT(DISTINCT CASE WHEN a.attended=1 THEN a.member_id END) attendance_count
               FROM guild_events e JOIN members m ON m.id=e.creator_member_id
               LEFT JOIN guild_event_signups s ON s.event_id=e.id
               LEFT JOIN guild_event_attendance a ON a.event_id=e.id
               GROUP BY e.id ORDER BY e.start_at, e.id"""
        ).fetchall():
            event_data = dict(row)
            event_start = parse_local_datetime(event_data["start_at"])
            event_data["is_upcoming"] = bool(
                event_start and event_start >= eastern_now_naive()
            )
            event_data["event_kind"] = "Endgame" if is_endgame_guild_event(event_data) else "User"
            event_data["signups"] = [dict(item) for item in get_db().execute(
                """SELECT m.id,m.name,s.rsvp_status,s.selected_job,s.discord_name
                   FROM guild_event_signups s JOIN members m ON m.id=s.member_id
                   WHERE s.event_id=? ORDER BY m.name COLLATE NOCASE""", (row["id"],)
            ).fetchall()]
            role_groups = (
                ("Tanks", ("NIN", "PLD")),
                ("Damage Dealers", ("WAR", "SAM", "MNK", "DRK", "BST", "DRG")),
                ("Ranged DD", ("RNG",)),
                ("Healing", ("WHM", "RDM")),
                ("Magic Damage", ("BLM",)),
                ("Support", ("BRD",)),
                ("Utility", ("SMN", "COR", "PUP", "BLU")),
                ("Treasure Hunter", ("THF",)),
                ("Job Not Selected", ("",)),
            )
            active_signups = [
                signup for signup in event_data["signups"]
                if signup["rsvp_status"] in ("going", "maybe")
            ]
            event_data["signup_groups"] = [
                {"name": group_name, "members": [
                    signup for signup in active_signups if signup["selected_job"] in group_jobs
                ]}
                for group_name, group_jobs in role_groups
            ]
            event_data["declined_signups"] = [
                signup for signup in event_data["signups"] if signup["rsvp_status"] == "cant"
            ]
            event_data["attendance"] = [item["member_id"] for item in get_db().execute(
                "SELECT member_id FROM guild_event_attendance WHERE event_id=? AND attended=1", (row["id"],)
            ).fetchall()]
            event_data["attendees"] = [dict(item) for item in get_db().execute(
                """SELECT m.id,m.name FROM guild_event_attendance a JOIN members m ON m.id=a.member_id
                   WHERE a.event_id=? AND a.attended=1 ORDER BY m.name COLLATE NOCASE""", (row["id"],)
            ).fetchall()]
            event_data["loot"] = [dict(item) for item in get_db().execute(
                """SELECT l.id,l.item,m.name player,l.job,l.family,l.distribution award,l.dkp_cost,l.auction_id,
                          l.classification='Major Loot' major
                   FROM endgame_loot_awards l JOIN members m ON m.id=l.recipient_member_id
                WHERE l.event_id=? ORDER BY l.id""", (row["id"],)
            ).fetchall()]
            event_data["auctions"] = [dict(item) for item in get_db().execute(
                """SELECT a.id,a.area,a.boss,a.status,a.ends_at,a.confirmed_at,
                          COUNT(l.id) award_count
                   FROM endgame_auctions a
                   LEFT JOIN endgame_loot_awards l ON l.auction_id=a.id
                   WHERE a.event_id=? GROUP BY a.id ORDER BY a.id DESC""",
                (row["id"],),
            ).fetchall()]
            guild_events.append(event_data)
        guild_events = (
            sorted(
                (event for event in guild_events if event["is_upcoming"]),
                key=lambda event: (event["start_at"], event["id"]),
            )
            + sorted(
                (event for event in guild_events if not event["is_upcoming"]),
                key=lambda event: (event["start_at"], event["id"]),
                reverse=True,
            )
        )
        # The Google roster is the authoritative two-event baseline through 2026-08-13.
        # Only explicitly completed events after that snapshot extend the calculation.
        completed_events = [
            event for event in guild_events
            if event["status"] == "Completed" and event["event_kind"] == "Endgame"
            and event["start_at"] > "2026-08-13T23:59"
        ]
        spent_by_member = {
            row["recipient_member_id"]: float(row["spent"] or 0)
            for row in get_db().execute(
                """SELECT recipient_member_id,SUM(dkp_cost) spent
                   FROM endgame_loot_awards GROUP BY recipient_member_id"""
            ).fetchall()
        }
        attendance_adjustments = {
            row["member_id"]: float(row["delta"] or 0)
            for row in get_db().execute(
                """SELECT member_id,SUM(dkp_delta) delta
                   FROM endgame_attendance_dkp_adjustments GROUP BY member_id"""
            ).fetchall()
        }
        for member in prototype_roster:
            baseline_attended = member["attended"]
            eligible = member["eligible"] + len(completed_events)
            attended = member["attended"] + sum(
                member["id"] in event["attendance"] for event in completed_events
            )
            lifetime_earned = baseline_attended * 3 + attendance_adjustments.get(member["id"], 0) + sum(
                float(event["dkp_value"])
                for event in completed_events if member["id"] in event["attendance"]
            )
            total_spent = int(round(spent_by_member.get(member["id"], 0)))
            last_event = max(
                (event["start_at"] for event in guild_events
                 if member["id"] in event["attendance"]),
                default="",
            )
            percentage = round(attended * 100 / eligible) if eligible else 0
            member.update({
                "eligible": eligible,
                "attended": attended,
                "attendance": percentage,
                "tier": 1 if percentage >= 75 else 2 if percentage >= 50 else 3,
                "lifetime_earned": int(round(lifetime_earned)),
                "total_spent": total_spent,
                "dkp": int(round(lifetime_earned - total_spent)),
                "last_event": last_event[:10] if last_event else "—",
            })
        dkp_values = [member["dkp"] for member in prototype_roster]
        dkp_highest = int(round(max(dkp_values, default=0)))
        dkp_average = int(round(sum(dkp_values) / len(dkp_values))) if dkp_values else 0
        dkp_bid_cap = max(ENDGAME_MINIMUM_BID_CAP, dkp_highest - dkp_average)
        persistent_loot = [dict(row) for row in get_db().execute(
            """SELECT substr(e.start_at,6,2)||'/'||substr(e.start_at,9,2)||'/'||substr(e.start_at,1,4) date,
                      m.name player,l.item,l.family,l.classification='Major Loot' major,
                      l.job,l.distribution award,l.dkp_cost,l.auction_id,e.name event_name,e.id event_id,
                       l.recipient_member_id,l.id
               FROM endgame_loot_awards l JOIN guild_events e ON e.id=l.event_id
               JOIN members m ON m.id=l.recipient_member_id ORDER BY e.start_at DESC,l.id DESC"""
        ).fetchall()]
        pending_job_requests = [dict(row) for row in get_db().execute(
            """SELECT r.*,m.name member_name FROM endgame_job_change_requests r
               JOIN members m ON m.id=r.member_id WHERE r.status='Pending'
               ORDER BY r.requested_at"""
        ).fetchall()]
        dynamis_defaults = {
            member["id"]: (member["main_job"], member["secondary_job"])
            for member in prototype_roster if member["id"]
        }
        imaven = next(
            (member for member in prototype_roster if member["name"].casefold() == "imaven"),
            None,
        )
        if imaven and imaven["id"]:
            dynamis_defaults[imaven["id"]] = ("BLU", "NIN")
        dynamis_members = []
        for member in get_db().execute(
            "SELECT id,name FROM members ORDER BY name COLLATE NOCASE"
        ).fetchall():
            default_jobs = dynamis_defaults.get(member["id"], ("", ""))
            main_job, secondary_job = dynamis_registrations.get(member["id"], default_jobs)
            profile_jobs = roster_job_levels.get(member["id"], {})
            eligible_jobs = {
                job: level for job, level in profile_jobs.items()
                if job in DYNAMIS_RELIC and level >= 71
            }
            reviewed_at = dynamis_change_reviews.get(member["id"])
            cooldown_until = ""
            if reviewed_at:
                expires_at = datetime.fromisoformat(reviewed_at) + timedelta(days=30)
                if expires_at > datetime.utcnow():
                    cooldown_until = expires_at.isoformat(timespec="seconds") + "Z"
            dynamis_members.append({
                "id": member["id"], "name": member["name"], "main_job": main_job,
                "secondary_job": secondary_job, "eligible_jobs": eligible_jobs,
                "has_registration": member["id"] in dynamis_registrations,
                "cooldown_until": cooldown_until,
            })
        dynamis_members.sort(key=lambda member: member["name"].casefold())
        dynamis_by_member = {member["id"]: member for member in dynamis_members}
        for member in prototype_roster:
            selection = dynamis_by_member.get(member["id"], {})
            member["dynamis_main"] = selection.get("main_job", "")
            member["dynamis_secondary"] = selection.get("secondary_job", "")
            member["dynamis_eligible_jobs"] = selection.get("eligible_jobs", {})
        dynamis_drops = dynamis_catalog()
        gear_catalog = gear_catalog_by_name(str(Path(app.root_path) / "static" / "gear_catalog.json"))
        for drop in dynamis_drops:
            tooltip_item = gear_catalog.get(drop["item"].casefold())
            if not tooltip_item and drop["item"].endswith(" -1"):
                tooltip_item = gear_catalog.get(drop["item"][:-3].casefold())
            drop["tooltip"] = {
                "item_id": tooltip_item.get("item_id") if tooltip_item else None,
                "name": (tooltip_item or {}).get("name", drop["item"]),
                "level": (tooltip_item or {}).get("level", 71),
                "slots": (tooltip_item or {}).get("slots", [drop["slot"]]),
                "jobs": (tooltip_item or {}).get("jobs", [drop["job"]]),
                "description": (tooltip_item or {}).get("description", "No item stats are available yet."),
                "rare": bool((tooltip_item or {}).get("rare")),
                "ex": bool((tooltip_item or {}).get("ex")),
            }
        dynamis_areas = tuple(dict.fromkeys(drop["area"] for drop in dynamis_drops))
        pending_dynamis_requests = [dict(row) for row in get_db().execute(
            """SELECT r.*,m.name member_name FROM dynamis_lot_change_requests r
               JOIN members m ON m.id=r.member_id WHERE r.status='Pending'
               ORDER BY r.requested_at"""
        ).fetchall()]
        own_dynamis_request = get_db().execute(
            "SELECT * FROM dynamis_lot_change_requests WHERE member_id=? ORDER BY id DESC LIMIT 1",
            (current_member_id(),),
        ).fetchone()
        own_job_request = get_db().execute(
            """SELECT * FROM endgame_job_change_requests WHERE member_id=?
               ORDER BY id DESC LIMIT 1""", (current_member_id(),)
        ).fetchone()
        calendar_members = [dict(row) for row in get_db().execute(
            "SELECT id,name FROM members ORDER BY name COLLATE NOCASE"
        ).fetchall()]
        persistent_audit = [dict(row) for row in get_db().execute(
            """SELECT l.created_at at,COALESCE(m.name,'Administrator') actor,l.area,l.action,l.details
               FROM admin_change_log l LEFT JOIN members m ON m.id=l.actor_member_id
               ORDER BY l.id DESC LIMIT 250"""
        ).fetchall()]
        persistent_audit.reverse()
        get_db().executemany(
            """INSERT OR IGNORE INTO endgame_event_job_snapshots
               (event_id,member_id,main_job,secondary_job) VALUES(?,?,?,?)""",
            [
                (event["id"], member["id"], member["main_job"], member["secondary_job"])
                for event in guild_events for member in prototype_roster if member["id"]
            ],
        )
        get_db().commit()
        job_snapshots = {
            (row["event_id"], row["member_id"]): (row["main_job"], row["secondary_job"])
            for row in get_db().execute(
                "SELECT event_id,member_id,main_job,secondary_job FROM endgame_event_job_snapshots"
            ).fetchall()
        }
        member_details = {}
        for member in prototype_roster:
            if not member["id"]:
                continue
            event_history = []
            loot_history = []
            earned_history = []
            for event in guild_events:
                if event["event_kind"] != "Endgame":
                    continue
                attended = member["id"] in event["attendance"]
                signup = next(
                    (row for row in event["signups"] if row["id"] == member["id"]), None
                )
                signed_up = bool(
                    signup and signup["rsvp_status"] in ("going", "maybe")
                )
                event_main, event_secondary = job_snapshots.get(
                    (event["id"], member["id"]), (member["main_job"], member["secondary_job"])
                )
                event_history.append({
                    "id": event["id"], "name": event["name"], "start_at": event["start_at"],
                    "attended": attended, "is_upcoming": event["is_upcoming"],
                    "signed_up": signed_up, "main_job": event_main,
                    "secondary_job": event_secondary,
                })
                earns_baseline_dkp = event["start_at"] in (
                    "2026-08-06T20:00", "2026-08-13T20:00"
                )
                earns_current_dkp = (
                    event["status"] == "Completed" and event["start_at"] > "2026-08-13T23:59"
                )
                if attended and (earns_baseline_dkp or earns_current_dkp):
                    earned_history.append({
                        "id": event["id"], "name": event["name"],
                        "date": event["start_at"][:10],
                        "dkp": 3 if earns_baseline_dkp else int(round(float(event["dkp_value"]))),
                    })
                for award in event["loot"]:
                    if award["player"].casefold() == member["name"].casefold():
                        loot_history.append({
                            **award, "event_id": event["id"], "event_name": event["name"],
                            "event_date": event["start_at"][:10],
                            "main_job": event_main, "secondary_job": event_secondary,
                        })
            attendance_adjustment = int(round(attendance_adjustments.get(member["id"], 0)))
            if attendance_adjustment:
                earned_history.append({
                    "id": None, "name": "Attendance adjustment", "date": "—",
                    "dkp": attendance_adjustment,
                })
            member_details[str(member["id"])] = {
                "id": member["id"], "name": member["name"],
                "main_job": member["main_job"], "secondary_job": member["secondary_job"],
                "dynamis_main": member["dynamis_main"],
                "dynamis_secondary": member["dynamis_secondary"],
                "dynamis_eligible_jobs": member["dynamis_eligible_jobs"],
                "job_levels": member["job_levels"],
                "dkp": member["dkp"], "total_spent": member["total_spent"],
                "lifetime_earned": member["lifetime_earned"],
                "last_event": member["last_event"],
                "events": event_history, "loot": loot_history,
                "earned_events": earned_history,
            }
        bank_items = [dict(row) for row in get_db().execute(
            """SELECT b.*,e.name event_name,e.start_at event_start,h.name holder_name,p.name purchaser_name,
                      u.name used_event_name,u.start_at used_event_start
               FROM ls_bank_items b
               LEFT JOIN guild_events e ON e.id=b.event_id
               LEFT JOIN members h ON h.id=b.holder_member_id
               LEFT JOIN members p ON p.id=b.purchaser_member_id
               LEFT JOIN guild_events u ON u.id=b.used_event_id
               ORDER BY CASE b.status WHEN 'Held' THEN 0 WHEN 'Purchased' THEN 1 ELSE 2 END,b.acquired_at DESC,b.id DESC"""
        ).fetchall()]
        officer_names = {name.casefold() for name in DISCORD_ADMIN_CHARACTERS}
        if is_admin() and current_member_name():
            officer_names.add(current_member_name().casefold())
        bank_officers = [dict(row) for row in get_db().execute(
            "SELECT id,name FROM members WHERE discord_admin=1 OR name COLLATE NOCASE IN ({}) ORDER BY name COLLATE NOCASE".format(
                ",".join("?" for _ in officer_names) or "''"
            ), tuple(officer_names)
        ).fetchall()]
        gil_transfers = [dict(row) for row in get_db().execute(
            """SELECT t.*,sender.name from_name,recipient.name to_name,recorder.name recorded_by_name
               FROM ls_gil_transfers t
               JOIN members sender ON sender.id=t.from_member_id
               JOIN members recipient ON recipient.id=t.to_member_id
               LEFT JOIN members recorder ON recorder.id=t.recorded_by
               ORDER BY t.transferred_at DESC,t.id DESC LIMIT 250"""
        ).fetchall()]
        bank_summary = dict(get_db().execute(
            """SELECT COALESCE(SUM(CASE WHEN acquisition_kind NOT IN ('Event Drop','Donation')
                                         THEN purchase_gil ELSE 0 END),0) purchases,
                      COALESCE(SUM(CASE WHEN acquisition_kind='Donation'
                                         THEN purchase_gil ELSE 0 END),0) donations,
                      COALESCE(SUM(sale_gil),0) sales,
                      SUM(CASE WHEN status='Held' THEN 1 ELSE 0 END) held_count,
                      SUM(CASE WHEN status='Purchased' THEN 1 ELSE 0 END) purchased_count,
                      SUM(CASE WHEN status='Sold' THEN 1 ELSE 0 END) sold_count
               FROM ls_bank_items"""
        ).fetchone())
        bank_summary["sales"] += bank_summary["donations"]
        dynamis_payout_events = [
            event for event in guild_events if is_dynamis_payout_event(event)
        ]
        dynamis_payout_events.sort(key=lambda event: (event["start_at"], event["id"]), reverse=True)
        selected_payout_event_id = request.args.get("payout_event", "").strip()
        if not selected_payout_event_id.isdigit() and dynamis_payout_events:
            selected_payout_event_id = str(dynamis_payout_events[0]["id"])
        selected_payout_event = next(
            (event for event in dynamis_payout_events if str(event["id"]) == selected_payout_event_id), None
        )
        dynamis_payout = None
        dynamis_payout_attendees = []
        dynamis_payout_items = []
        if selected_payout_event:
            payout_row = get_db().execute(
                "SELECT * FROM dynamis_payouts WHERE event_id=?", (selected_payout_event["id"],)
            ).fetchone()
            if payout_row:
                dynamis_payout = dict(payout_row)
                dynamis_payout_attendees = [dict(row) for row in get_db().execute(
                    """SELECT a.*,m.name FROM dynamis_payout_attendance a
                       JOIN members m ON m.id=a.member_id WHERE a.payout_id=?
                       ORDER BY a.attended DESC,m.name COLLATE NOCASE""", (payout_row["id"],)
                ).fetchall()]
                attendee_count = sum(bool(row["attended"]) for row in dynamis_payout_attendees)
                dynamis_payout["attendee_count"] = attendee_count
                dynamis_payout["entry_per_person"] = round(dynamis_payout["entry_cost"] / attendee_count) if attendee_count else 0
                currency_fields = (
                    ("Lungo-Nango Jadeshell", "lungo", "Lungo", "Hundreds"),
                    ("Montiont Silverpiece", "montiont", "Montiont", "Hundreds"),
                    ("100 Byne Bill", "byne", "100 Byne", "Hundreds"),
                    ("T. Whiteshell", "whiteshell", "T. Whiteshell", "Singles"),
                    ("O. Bronzepiece", "bronzepiece", "O. Bronzepiece", "Singles"),
                    ("Byne Bill", "byne_single", "Byne Bill", "Singles"),
                )
                for item_name, key, label, group in currency_fields:
                    quantity = dynamis_payout[f"{key}_quantity"]
                    market_total = quantity * dynamis_payout[f"{key}_market_value"]
                    actual_sale = dynamis_payout[f"{key}_actual_sale"]
                    effective_total = actual_sale if actual_sale is not None else market_total
                    dynamis_payout_items.append({
                        "name": item_name, "label": label, "key": key, "group": group, "quantity": quantity,
                        "market_value": dynamis_payout[f"{key}_market_value"],
                        "market_total": market_total, "actual_sale": actual_sale,
                        "effective_total": effective_total,
                        "market_url": f"https://www.psxi.gg/s/horizonxi/?item={quote(item_name)}",
                    })
                sold_loot_total = get_db().execute(
                    "SELECT COALESCE(SUM(sale_gil),0) total FROM dynamis_payout_sales WHERE payout_id=? AND sold=1",
                    (payout_row["id"],),
                ).fetchone()["total"]
                dynamis_payout["sold_loot_total"] = sold_loot_total
                dynamis_payout["total_value"] = sum(item["effective_total"] for item in dynamis_payout_items) + sold_loot_total
                dynamis_payout["payout_per_person"] = round(dynamis_payout["total_value"] / attendee_count) if attendee_count else 0
                dynamis_payout["net_per_person"] = dynamis_payout["payout_per_person"] - dynamis_payout["entry_per_person"]
        payout_member_choices = [dict(row) for row in get_db().execute(
            "SELECT id,name FROM members ORDER BY name COLLATE NOCASE"
        ).fetchall()]
        dynamis_payout_zones = tuple(dict.fromkeys(drop["area"] for drop in dynamis_catalog()))
        dynamis_payout_sale_items = []
        if dynamis_payout:
            dynamis_payout_sale_items = [dict(row) for row in get_db().execute(
                """SELECT s.*,m.name buyer_name FROM dynamis_payout_sales s
                   LEFT JOIN members m ON m.id=s.buyer_member_id WHERE s.payout_id=? ORDER BY s.id DESC""",
                (dynamis_payout["id"],),
            ).fetchall()]
        return render_template(
            "endgame_dashboard.html", roster=prototype_roster,
            loot=persistent_loot, pop_items=pop_items, pop_targets=pop_targets,
            priority_items=priority_items, jobs=JOBS, guild_events=guild_events,
            loot_catalog=loot_catalog,
            calendar_members=calendar_members,
            pending_job_requests=pending_job_requests,
            own_job_request=dict(own_job_request) if own_job_request else None,
            dynamis_members=dynamis_members,
            dynamis_catalog=dynamis_drops,
            dynamis_areas=dynamis_areas,
            pending_dynamis_requests=pending_dynamis_requests,
            own_dynamis_request=dict(own_dynamis_request) if own_dynamis_request else None,
            discord_events_enabled=bool(
                app.config.get("HOKUTEN_EVENT_BOT_API_URL") and
                app.config.get("HOKUTEN_EVENT_BOT_API_TOKEN")
            ) or bool(app.config.get("DISCORD_BOT_TOKEN")),
            event_bot_sync_enabled=bool(
                app.config.get("HOKUTEN_EVENT_BOT_API_URL") and
                app.config.get("HOKUTEN_EVENT_BOT_API_TOKEN")
            ),
            discord_announcements_enabled=bool(app.config.get("DISCORD_EVENT_CHANNEL_ID")),
            persistent_audit=persistent_audit,
            member_details=member_details,
            bank_items=bank_items,
            bank_officers=bank_officers,
            gil_transfers=gil_transfers,
            bank_summary=dict(bank_summary),
            dynamis_payout_events=dynamis_payout_events,
            selected_payout_event=selected_payout_event,
            dynamis_payout=dynamis_payout,
            dynamis_payout_attendees=dynamis_payout_attendees,
            dynamis_payout_items=dynamis_payout_items,
            dynamis_payout_zones=dynamis_payout_zones,
            dynamis_payout_sale_items=dynamis_payout_sale_items,
            payout_member_choices=payout_member_choices,
            dkp_highest=dkp_highest, dkp_average=dkp_average,
            dkp_bid_cap=dkp_bid_cap,
        )

    @app.post("/endgame/dynamis-lot-requests")
    @editor_required
    def request_dynamis_lot_change():
        member = require_member_identity()
        main_job = request.form.get("main_job", "").strip().upper()
        secondary_job = request.form.get("secondary_job", "").strip().upper()
        eligible_jobs = {
            row["job"] for row in get_db().execute(
                "SELECT job FROM member_jobs WHERE member_id=? AND level>=71", (member["id"],)
            ).fetchall() if row["job"] in DYNAMIS_RELIC
        }
        if (main_job not in eligible_jobs
                or (secondary_job and secondary_job not in eligible_jobs)
                or (secondary_job and main_job == secondary_job)):
            abort(400, description="Choose a main Dynamis job and, optionally, a different secondary job at level 71 or higher on your roster.")
        db = get_db()
        if db.execute("SELECT 1 FROM dynamis_lot_change_requests WHERE member_id=? AND status='Pending'", (member["id"],)).fetchone():
            abort(400, description="You already have a pending Dynamis lotting request.")
        if db.execute(
            """SELECT 1 FROM dynamis_lot_change_requests WHERE member_id=? AND status='Approved'
               AND reviewed_at>=datetime('now','-30 days')""", (member["id"],)
        ).fetchone():
            abort(400, description="Approved Dynamis lotting jobs can only be changed once every 30 days.")
        db.execute(
            "INSERT INTO dynamis_lot_change_requests(member_id,requested_main,requested_secondary) VALUES(?,?,?)",
            (member["id"], main_job, secondary_job),
        )
        db.commit()
        flash("Your Dynamis lotting job request was sent to officers.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="dynamis"))

    @app.post("/endgame/dynamis-lot-requests/<int:request_id>/review")
    @admin_required
    def review_dynamis_lot_change(request_id):
        decision = request.form.get("decision", "")
        if decision not in {"Approved", "Denied"}:
            abort(400, description="Choose approve or deny.")
        db = get_db()
        change = db.execute(
            "SELECT * FROM dynamis_lot_change_requests WHERE id=? AND status='Pending'", (request_id,)
        ).fetchone()
        if not change:
            abort(404)
        reviewer = require_member_identity()
        member = db.execute("SELECT name FROM members WHERE id=?", (change["member_id"],)).fetchone()
        if decision == "Approved":
            db.execute(
                """INSERT INTO dynamis_lot_registrations(member_id,main_job,secondary_job,updated_at)
                   VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(member_id) DO UPDATE SET
                   main_job=excluded.main_job,secondary_job=excluded.secondary_job,updated_at=CURRENT_TIMESTAMP""",
                (change["member_id"], change["requested_main"], change["requested_secondary"]),
            )
        db.execute(
            "UPDATE dynamis_lot_change_requests SET status=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (decision, reviewer["id"], request_id),
        )
        db.execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (reviewer["id"], "Dynamis Lotting", f"Request {decision.lower()}",
             f"{member['name']}: {change['requested_main']} / {change['requested_secondary']} ({decision})"),
        )
        db.commit()
        flash(f"{member['name']}'s Dynamis lotting request was {decision.lower()}.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="dynamis"))

    @app.post("/endgame/dynamis-lot-registrations/<int:member_id>")
    @admin_required
    def update_dynamis_lot_registration(member_id):
        db = get_db()
        member = db.execute("SELECT id,name FROM members WHERE id=?", (member_id,)).fetchone()
        if not member:
            abort(404)
        main_job = request.form.get("main_job", "").strip().upper()
        secondary_job = request.form.get("secondary_job", "").strip().upper()
        eligible_jobs = {
            row["job"] for row in db.execute(
                "SELECT job FROM member_jobs WHERE member_id=? AND level>=71", (member_id,)
            ).fetchall() if row["job"] in DYNAMIS_RELIC
        }
        selected_jobs = {job for job in (main_job, secondary_job) if job}
        if (main_job and secondary_job and main_job == secondary_job) or not selected_jobs <= eligible_jobs:
            abort(400, description="Choose distinct level 71+ Dynamis-eligible jobs from this member's roster.")
        if selected_jobs:
            db.execute(
                """INSERT INTO dynamis_lot_registrations(member_id,main_job,secondary_job,updated_at)
                   VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(member_id) DO UPDATE SET
                   main_job=excluded.main_job,secondary_job=excluded.secondary_job,updated_at=CURRENT_TIMESTAMP""",
                (member_id, main_job, secondary_job),
            )
        else:
            db.execute("DELETE FROM dynamis_lot_registrations WHERE member_id=?", (member_id,))
        actor = require_member_identity()
        db.execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "Dynamis Lotting", "Officer registration update",
             f"{member['name']}: {main_job or 'Unassigned'} / {secondary_job or 'Unassigned'}"),
        )
        db.commit()
        flash(f"Updated {member['name']}'s Dynamis lotting jobs.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="jobs"))

    def dynamis_payout_redirect(event_id):
        return redirect(url_for("endgame_dashboard", payout_event=event_id, _anchor="dynamis-payout"))

    def dynamis_payout_event_or_404(event_id):
        event = get_db().execute("SELECT * FROM guild_events WHERE id=?", (event_id,)).fetchone()
        if not event or not is_dynamis_payout_event(dict(event)):
            abort(404, description="Choose a Dynamis Endgame event.")
        return event

    @app.post("/endgame/dynamis-payouts/<int:event_id>/create")
    @admin_required
    def create_dynamis_payout(event_id):
        event = dynamis_payout_event_or_404(event_id)
        db = get_db()
        existing = db.execute("SELECT id FROM dynamis_payouts WHERE event_id=?", (event_id,)).fetchone()
        if existing:
            return dynamis_payout_redirect(event_id)
        prices = dynamis_payout_market_values()
        actor = require_member_identity()
        cursor = db.execute(
            """INSERT INTO dynamis_payouts(event_id,lungo_market_value,montiont_market_value,byne_market_value,
               whiteshell_market_value,bronzepiece_market_value,byne_single_market_value,created_by)
               VALUES(?,?,?,?,?,?,?,?)""",
            (event_id, prices["Lungo-Nango Jadeshell"], prices["Montiont Silverpiece"],
             prices["100 Byne Bill"], prices["T. Whiteshell"], prices["O. Bronzepiece"],
             prices["Byne Bill"], actor["id"]),
        )
        attendance_ids = {
            row["member_id"] for row in db.execute(
                "SELECT member_id FROM guild_event_attendance WHERE event_id=? AND attended=1", (event_id,)
            ).fetchall()
        }
        signup_ids = [row["member_id"] for row in db.execute(
            """SELECT member_id FROM guild_event_signups WHERE event_id=?
               AND rsvp_status IN ('going','maybe') ORDER BY member_id""", (event_id,)
        ).fetchall()]
        attendee_ids = list(attendance_ids) + [member_id for member_id in signup_ids if member_id not in attendance_ids]
        # A Dynamis alliance can contain at most 36 participants.
        for member_id in attendee_ids[:36]:
            db.execute(
                """INSERT INTO dynamis_payout_attendance(payout_id,member_id,attended,added_manually)
                   VALUES(?,?,?,0)""",
                (cursor.lastrowid, member_id, int(member_id in attendance_ids or not attendance_ids)),
            )
        db.execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "Dynamis Payout", "Tracker created", f"{event['name']} ({len(attendee_ids[:36])} seeded attendees)"),
        )
        db.commit()
        flash("Created the Dynamis payout tracker from the event roster.", "success")
        return dynamis_payout_redirect(event_id)

    @app.post("/endgame/dynamis-payouts/<int:event_id>/settings")
    @admin_required
    def update_dynamis_payout(event_id):
        dynamis_payout_event_or_404(event_id)
        db = get_db()
        payout = db.execute("SELECT id FROM dynamis_payouts WHERE event_id=?", (event_id,)).fetchone()
        if not payout:
            abort(404)
        fields = ("entry_cost", "lungo_quantity", "montiont_quantity", "byne_quantity",
                  "whiteshell_quantity", "bronzepiece_quantity", "byne_single_quantity")
        values = [payout_gil_value(request.form.get(field)) for field in fields]
        actual_values = [payout_gil_value(request.form.get(f"{key}_actual_sale"), allow_blank=True)
                         for key in ("lungo", "montiont", "byne", "whiteshell", "bronzepiece", "byne_single")]
        zone = request.form.get("zone", "").strip()
        valid_zones = {drop["area"] for drop in dynamis_catalog()}
        if (any(value < 0 for value in values) or any(value is not None and value < 0 for value in actual_values)
                or zone not in valid_zones):
            abort(400, description="Enter valid non-negative gil amounts and drop quantities.")
        actor = require_member_identity()
        db.execute(
            """UPDATE dynamis_payouts SET zone=?,entry_cost=?,lungo_quantity=?,montiont_quantity=?,byne_quantity=?,
               whiteshell_quantity=?,bronzepiece_quantity=?,byne_single_quantity=?,lungo_actual_sale=?,montiont_actual_sale=?,byne_actual_sale=?,
               whiteshell_actual_sale=?,bronzepiece_actual_sale=?,byne_single_actual_sale=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (zone, *values, *actual_values, payout["id"]),
        )
        db.execute("INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
                   (actor["id"], "Dynamis Payout", "Payout values updated", str(event_id)))
        db.commit()
        flash("Saved Dynamis currency values and payout totals.", "success")
        return dynamis_payout_redirect(event_id)

    @app.post("/endgame/dynamis-payouts/<int:event_id>/refresh-market")
    @admin_required
    def refresh_dynamis_payout_market(event_id):
        dynamis_payout_event_or_404(event_id)
        prices = dynamis_payout_market_values()
        get_db().execute(
            """UPDATE dynamis_payouts SET lungo_market_value=?,montiont_market_value=?,byne_market_value=?,
               whiteshell_market_value=?,bronzepiece_market_value=?,byne_single_market_value=?,updated_at=CURRENT_TIMESTAMP WHERE event_id=?""",
            (prices["Lungo-Nango Jadeshell"], prices["Montiont Silverpiece"], prices["100 Byne Bill"],
             prices["T. Whiteshell"], prices["O. Bronzepiece"], prices["Byne Bill"], event_id),
        )
        get_db().commit()
        if request.accept_mimetypes.best == "application/json":
            return jsonify(ok=True, member_id=member["id"], member_name=member["name"])
        return dynamis_payout_redirect(event_id)

    @app.post("/endgame/dynamis-payouts/<int:event_id>/sales")
    @admin_required
    def record_dynamis_payout_sale(event_id):
        dynamis_payout_event_or_404(event_id)
        payout = get_db().execute("SELECT id FROM dynamis_payouts WHERE event_id=?", (event_id,)).fetchone()
        item = request.form.get("item", "").strip()[:120]
        buyer_id = request.form.get("buyer_member_id", "").strip()
        sale_gil = payout_gil_value(request.form.get("sale_gil"))
        buyer = get_db().execute("SELECT id FROM members WHERE id=?", (buyer_id,)).fetchone() if buyer_id.isdigit() else None
        if not payout or not item or sale_gil < 0 or (buyer_id and not buyer):
            abort(400, description="Choose an item and valid buyer and sale value.")
        get_db().execute("INSERT INTO dynamis_payout_sales(payout_id,item,buyer_member_id,sale_gil,sold) VALUES(?,?,?,?,?)",
                         (payout["id"], item, buyer["id"] if buyer else None, sale_gil, int(request.form.get("sold") == "1")))
        get_db().commit()
        return dynamis_payout_redirect(event_id)

    @app.post("/endgame/dynamis-payouts/<int:event_id>/sales/<int:sale_id>")
    @admin_required
    def update_dynamis_payout_sale(event_id, sale_id):
        dynamis_payout_event_or_404(event_id)
        payout = get_db().execute("SELECT id FROM dynamis_payouts WHERE event_id=?", (event_id,)).fetchone()
        if not payout:
            abort(404)
        if request.form.get("remove") == "1":
            get_db().execute("DELETE FROM dynamis_payout_sales WHERE id=? AND payout_id=?", (sale_id, payout["id"]))
        else:
            get_db().execute("UPDATE dynamis_payout_sales SET sold=? WHERE id=? AND payout_id=?",
                             (int(request.form.get("sold") == "1"), sale_id, payout["id"]))
        get_db().commit()
        return dynamis_payout_redirect(event_id)

    @app.post("/endgame/dynamis-payouts/<int:event_id>/attendance/add")
    @admin_required
    def add_dynamis_payout_attendee(event_id):
        dynamis_payout_event_or_404(event_id)
        member_id = request.form.get("member_id", "").strip()
        payout = get_db().execute("SELECT id FROM dynamis_payouts WHERE event_id=?", (event_id,)).fetchone()
        member = get_db().execute("SELECT id,name FROM members WHERE id=?", (member_id,)).fetchone() if member_id.isdigit() else None
        already_listed = bool(payout and get_db().execute(
            "SELECT 1 FROM dynamis_payout_attendance WHERE payout_id=? AND member_id=?", (payout["id"], member["id"])
        ).fetchone()) if member else False
        current_count = get_db().execute("SELECT COUNT(*) count FROM dynamis_payout_attendance WHERE payout_id=?", (payout["id"],)).fetchone()["count"] if payout else 0
        if not payout or not member or (current_count >= 36 and not already_listed):
            abort(400, description="Choose a valid member; a Dynamis payout roster is limited to 36 slots.")
        get_db().execute(
            """INSERT INTO dynamis_payout_attendance(payout_id,member_id,attended,added_manually)
               VALUES(?,?,1,1) ON CONFLICT(payout_id,member_id) DO UPDATE SET attended=1,added_manually=1""",
            (payout["id"], member["id"]),
        )
        get_db().commit()
        if request.accept_mimetypes.best == "application/json":
            return jsonify(ok=True, member_id=member["id"], member_name=member["name"])
        return dynamis_payout_redirect(event_id)

    @app.post("/endgame/dynamis-payouts/<int:event_id>/attendance/<int:member_id>")
    @admin_required
    def update_dynamis_payout_attendee(event_id, member_id):
        dynamis_payout_event_or_404(event_id)
        payout = get_db().execute("SELECT id FROM dynamis_payouts WHERE event_id=?", (event_id,)).fetchone()
        if not payout:
            abort(404)
        remove_member_id = request.form.get("remove_member_id", "").strip()
        if member_id == 0:
            if remove_member_id.isdigit():
                get_db().execute("DELETE FROM dynamis_payout_attendance WHERE payout_id=? AND member_id=?", (payout["id"], int(remove_member_id)))
            else:
                attendee_rows = get_db().execute("SELECT member_id FROM dynamis_payout_attendance WHERE payout_id=?", (payout["id"],)).fetchall()
                for attendee in attendee_rows:
                    attendee_id = attendee["member_id"]
                    get_db().execute(
                        "UPDATE dynamis_payout_attendance SET attended=?,entry_paid=?,payout_paid=? WHERE payout_id=? AND member_id=?",
                        (int(request.form.get(f"attended_{attendee_id}") == "1"),
                         int(request.form.get(f"entry_paid_{attendee_id}") == "1"),
                         int(request.form.get(f"payout_paid_{attendee_id}") == "1"), payout["id"], attendee_id),
                    )
        elif request.form.get("remove") == "1":
            get_db().execute("DELETE FROM dynamis_payout_attendance WHERE payout_id=? AND member_id=?", (payout["id"], member_id))
        else:
            get_db().execute(
                """UPDATE dynamis_payout_attendance SET attended=?,entry_paid=?,payout_paid=?
                   WHERE payout_id=? AND member_id=?""",
                (int(request.form.get("attended") == "1"), int(request.form.get("entry_paid") == "1"),
                 int(request.form.get("payout_paid") == "1"), payout["id"], member_id),
            )
        get_db().commit()
        if request.accept_mimetypes.best == "application/json":
            return jsonify(ok=True, removed_member_id=int(remove_member_id) if member_id == 0 and remove_member_id.isdigit() else None)
        return dynamis_payout_redirect(event_id)

    def current_dkp_balances():
        """Calculate available DKP from endgame attendance minus recorded awards."""
        members = get_db().execute("SELECT id,name FROM members ORDER BY name COLLATE NOCASE").fetchall()
        earned = {
            row["id"]: ENDGAME_BASELINE_ATTENDANCE.get(row["name"].casefold(), 0) * 3
            for row in members
        }
        for adjustment in get_db().execute(
            """SELECT member_id,SUM(dkp_delta) delta
               FROM endgame_attendance_dkp_adjustments GROUP BY member_id"""
        ).fetchall():
            earned[adjustment["member_id"]] = earned.get(adjustment["member_id"], 0) + int(round(adjustment["delta"] or 0))
        completed_events = {
            event["id"]: int(round(event["dkp_value"]))
            for event in get_db().execute(
                "SELECT * FROM guild_events WHERE status='Completed' AND start_at>'2026-08-13T23:59'"
            ).fetchall()
            if is_endgame_guild_event(event)
        }
        if completed_events:
            event_marks = ",".join("?" for _ in completed_events)
            for attendee in get_db().execute(
                f"""SELECT event_id,member_id FROM guild_event_attendance
                     WHERE attended=1 AND event_id IN ({event_marks})""",
                list(completed_events),
            ).fetchall():
                earned[attendee["member_id"]] = (
                    earned.get(attendee["member_id"], 0)
                    + completed_events[attendee["event_id"]]
                )
        spent = {
            row["member_id"]: int(round(row["spent"] or 0))
            for row in get_db().execute(
                "SELECT recipient_member_id member_id,SUM(dkp_cost) spent FROM endgame_loot_awards GROUP BY recipient_member_id"
            ).fetchall()
        }
        return {
            row["id"]: {"name": row["name"], "balance": earned.get(row["id"], 0) - spent.get(row["id"], 0)}
            for row in members
        }

    def current_bid_cap(balances):
        values = [entry["balance"] for entry in balances.values()]
        highest = max(values, default=0)
        average = int(round(sum(values) / len(values))) if values else 0
        return {"highest": highest, "average": average,
                "cap": max(ENDGAME_MINIMUM_BID_CAP, highest - average)}

    def auction_item_family(name):
        lowered = name.casefold()
        for family, words in {
            "Weapons": ("axe", "sword", "pole"), "Head": ("crown", "kabuto", "celata", "schaller"),
            "Hands": ("mittens", "kote", "gauntlets", "handschuhs", "mitts"),
            "Body": ("osode", "togi", "harness"), "Legs": ("haidate", "slacks", "cuisses"),
            "Feet": ("leggings", "sune-ate", "sollerets", "greaves"), "Accessories": ("torque", "earring"),
        }.items():
            if any(word in lowered for word in words):
                return family
        return "Other"

    def manual_loot_family(item_name):
        catalog_names = {
            item["name"]: auction_item_family(item["name"])
            for item in (*ENDGAME_PRIORITY_ITEMS, *ENDGAME_AUCTION_EXTRA_DROPS)
        }
        return catalog_names.get(item_name)

    def auction_drop_name(item_name):
        abjurations = {
            "Hecatomb Mittens": "Neptunal Abjuration: Hands", "Shura Haidate": "Dryadic Abjuration: Legs",
            "Adaman Sollerets": "Earthen Abjuration: Feet", "Zenith Crown": "Aquarian Abjuration: Head",
            "Crimson Finger Gauntlets": "Wyrmal Abjuration: Hands", "Zenith Slacks": "Aquarian Abjuration: Legs",
            "Shura Zunari Kabuto": "Dryadic Abjuration: Head", "Koenig Schaller": "Martial Abjuration: Head",
            "Hecatomb Leggings": "Neptunal Abjuration: Feet", "Shura Kote": "Dryadic Abjuration: Hands",
            "Adaman Celata": "Earthen Abjuration: Head", "Zenith Mitts": "Aquarian Abjuration: Hands",
            "Koenig Handschuhs": "Martial Abjuration: Hands", "Crimson Greaves": "Wyrmal Abjuration: Feet",
            "Shura Togi": "Dryadic Abjuration: Body", "Hecatomb Harness": "Neptunal Abjuration: Body",
            "Crimson Cuisses": "Wyrmal Abjuration: Legs",
        }
        return abjurations.get(item_name, item_name)

    def auction_priority_tier(item, job):
        for tier in (1, 2, 3):
            if job in tuple(filter(None, str(item[f"p{tier}"] or "").split(","))):
                return tier
        return 4 if not any(item[f"p{tier}"] for tier in (1, 2, 3)) else None

    def refresh_auction_statuses():
        db = get_db()
        now = datetime.utcnow().isoformat(timespec="seconds")
        expired = db.execute(
            "SELECT 1 FROM endgame_auctions WHERE status='Active' AND paused_at IS NULL AND ends_at<=? LIMIT 1",
            (now,),
        ).fetchone()
        if not expired:
            return False
        db.execute(
            "UPDATE endgame_auctions SET status='Closed' WHERE status='Active' AND paused_at IS NULL AND ends_at<=?",
            (now,),
        )
        db.commit()
        return True

    def auction_payload():
        refresh_auction_statuses()
        balances = current_dkp_balances()
        cap = current_bid_cap(balances)
        actor_id = current_member_id()
        catalog = gear_catalog_by_name(str(Path(app.root_path) / "static" / "gear_catalog.json"))
        actor_levels = {}
        if actor_id:
            actor_levels = {
                row["job"]: row["level"] for row in get_db().execute(
                    "SELECT job,level FROM member_jobs WHERE member_id=?", (actor_id,)
                ).fetchall()
            }
        my_reserved = 0
        if actor_id:
            reserved = get_db().execute(
                """SELECT COALESCE(SUM(b.amount),0) reserved FROM endgame_auction_bids b
                   JOIN endgame_auction_items i ON i.id=b.auction_item_id
                   JOIN endgame_auctions a ON a.id=i.auction_id
                   WHERE b.member_id=? AND a.status='Active'""", (actor_id,)
            ).fetchone()
            my_reserved = int(reserved["reserved"] or 0)
        auctions = []
        rows = get_db().execute(
            """SELECT a.*,e.name event_name,COUNT(l.id) award_count
               FROM endgame_auctions a JOIN guild_events e ON e.id=a.event_id
               LEFT JOIN endgame_loot_awards l ON l.auction_id=a.id
               WHERE a.status IN ('Active','Closed','Confirmed')
               GROUP BY a.id ORDER BY a.id DESC LIMIT 32"""
        ).fetchall()
        auction_ids = [row["id"] for row in rows]
        items_by_auction = {}
        awards_by_auction = {}
        bids_by_item = {}
        if auction_ids:
            auction_marks = ",".join("?" for _ in auction_ids)
            item_rows = get_db().execute(
                f"SELECT * FROM endgame_auction_items WHERE auction_id IN ({auction_marks}) ORDER BY id",
                auction_ids,
            ).fetchall()
            for item_row in item_rows:
                items_by_auction.setdefault(item_row["auction_id"], []).append(item_row)

            for award_row in get_db().execute(
                f"""SELECT l.id,l.auction_id,l.auction_item_id,l.item,l.job,l.family,l.distribution,
                           l.classification,l.dkp_cost,l.recipient_member_id,m.name recipient
                    FROM endgame_loot_awards l JOIN members m ON m.id=l.recipient_member_id
                    WHERE l.auction_id IN ({auction_marks}) ORDER BY l.id""",
                auction_ids,
            ).fetchall():
                auction_awards = awards_by_auction.setdefault(award_row["auction_id"], {})
                award = dict(award_row)
                award.pop("auction_id", None)
                auction_awards.setdefault(award_row["auction_item_id"], []).append(award)

            item_ids = [item_row["id"] for item_row in item_rows]
            if item_ids:
                item_marks = ",".join("?" for _ in item_ids)
                for bid_row in get_db().execute(
                    f"""SELECT b.*,m.name FROM endgame_auction_bids b
                         JOIN members m ON m.id=b.member_id
                         WHERE b.auction_item_id IN ({item_marks})""",
                    item_ids,
                ).fetchall():
                    bids_by_item.setdefault(bid_row["auction_item_id"], []).append(bid_row)
        for row in rows:
            auction = dict(row)
            auction["paused"] = bool(auction.get("paused_at"))
            auction["items"] = []
            awards_by_item = awards_by_auction.get(row["id"], {})
            legacy_auction_awards = awards_by_item.get(None, [])
            for item_row in items_by_auction.get(row["id"], []):
                item = dict(item_row)
                item["awards"] = list(awards_by_item.get(item["id"], []))
                # Legacy awards made before auction-item links existed still appear with their auction.
                item["awards"].extend(
                    award for award in legacy_auction_awards
                    if award["item"] in {item["item"], item.get("target_item")}
                )
                tooltip_source_name = item.get("target_item") or item["item"]
                tooltip_name = AUCTION_TOOLTIP_ITEM_ALIASES.get(tooltip_source_name, tooltip_source_name)
                tooltip_item = AUCTION_TOOLTIP_OVERRIDES.get(
                    tooltip_source_name,
                    catalog.get(tooltip_name.casefold(), {}),
                )
                item["tooltip"] = {
                    "item_id": tooltip_item.get("item_id"), "name": tooltip_item.get("name") or item.get("target_item") or item["item"],
                    "level": tooltip_item.get("level") or item["required_level"], "slots": tooltip_item.get("slots", []),
                    "jobs": tooltip_item.get("jobs", []), "description": tooltip_item.get("description", "No item stats available."),
                    "rare": bool(tooltip_item.get("rare")), "ex": bool(tooltip_item.get("ex")),
                }
                bids = []
                for bid_row in bids_by_item.get(item["id"], []):
                    bid = dict(bid_row)
                    bid["tier"] = auction_priority_tier(item, bid["job"])
                    bid["balance"] = balances.get(bid["member_id"], {}).get("balance", 0)
                    bids.append(bid)
                # Priority eligibility always comes before bid amount: P1, P2, P3, then Freelot.
                bids.sort(key=lambda bid: (bid["tier"] or 99, -bid["amount"], -bid["balance"], bid["updated_at"]))
                item["bids"] = bids
                item["suggested_winner_id"] = bids[0]["member_id"] if bids else None
                item["my_bid"] = next((bid for bid in bids if bid["member_id"] == actor_id), None)
                current_amount = item["my_bid"]["amount"] if item["my_bid"] else 0
                actor_balance = balances.get(actor_id, {}).get("balance", 0)
                item["max_bid"] = max(0, min(cap["cap"], actor_balance))
                eligible_jobs = []
                if actor_id:
                    for job, level in actor_levels.items():
                        tier = auction_priority_tier(item, job)
                        if tier and level >= item["required_level"]:
                            eligible_jobs.append({"job": job, "level": level, "tier": tier})
                item["eligible_jobs"] = sorted(eligible_jobs, key=lambda entry: (entry["tier"], entry["job"]))
                auction["items"].append(item)
            auctions.append(auction)
        recent = [dict(row) for row in get_db().execute(
            """SELECT b.amount,b.job,b.updated_at,m.name,i.item,a.boss,a.status
               FROM endgame_auction_bids b JOIN members m ON m.id=b.member_id
               JOIN endgame_auction_items i ON i.id=b.auction_item_id
               JOIN endgame_auctions a ON a.id=i.auction_id
               ORDER BY b.updated_at DESC,b.id DESC LIMIT 20"""
        ).fetchall()]
        my_balance = balances.get(actor_id, {}).get("balance", 0)
        current_auctions = [auction for auction in auctions if auction["status"] in ("Active", "Closed")]
        past_auctions = [auction for auction in auctions if auction["status"] == "Confirmed"]
        return {"auctions": auctions, "current_auctions": current_auctions,
                "past_auctions": past_auctions, "recent_bids": recent, "dkp": cap,
                "my_balance": my_balance, "my_reserved": my_reserved,
                "my_available": max(0, my_balance - my_reserved),
                "is_admin": can_create_guild_events(), "server_time": datetime.utcnow().isoformat(timespec="seconds") + "Z"}

    @app.get("/api/endgame/auctions")
    @editor_required
    def get_endgame_auctions():
        return jsonify(auction_payload())

    def endgame_pop_inventory_payload():
        rows = get_db().execute(
            """SELECT m.name,i.item_key,i.quantity FROM endgame_pop_inventory i
               JOIN members m ON m.id=i.member_id WHERE i.quantity > 0"""
        ).fetchall()
        inventory = {}
        for row in rows:
            inventory.setdefault(row["name"], {})[row["item_key"]] = row["quantity"]
        return {"inventory": inventory}

    @app.get("/api/endgame/pops")
    @editor_required
    def get_endgame_pop_inventory():
        return jsonify(endgame_pop_inventory_payload())

    @app.post("/api/endgame/pops")
    @editor_required
    def update_endgame_pop_inventory():
        actor = require_member_identity()
        payload = request.get_json(silent=True) or request.form
        holder_name = str(payload.get("holder", "")).strip()
        item_key = str(payload.get("item_key", "")).strip()
        try:
            delta = int(payload.get("delta", 0))
        except (TypeError, ValueError):
            abort(400, description="Pop quantity changes must be whole items.")
        if not holder_name or not re.fullmatch(r"[a-z0-9-]{2,80}", item_key, re.I) or delta not in (-1, 1):
            abort(400, description="Invalid pop inventory update.")
        holder = get_db().execute(
            "SELECT id,name FROM members WHERE name=? COLLATE NOCASE", (holder_name,)
        ).fetchone()
        if not holder:
            abort(404, description="Selected holder was not found.")
        existing = get_db().execute(
            "SELECT quantity FROM endgame_pop_inventory WHERE member_id=? AND item_key=?",
            (holder["id"], item_key),
        ).fetchone()
        quantity = max(0, int(existing["quantity"] if existing else 0) + delta)
        if quantity:
            get_db().execute(
                """INSERT INTO endgame_pop_inventory(member_id,item_key,quantity,updated_by,updated_at)
                   VALUES(?,?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(member_id,item_key) DO UPDATE SET quantity=excluded.quantity,
                   updated_by=excluded.updated_by,updated_at=CURRENT_TIMESTAMP""",
                (holder["id"], item_key, quantity, actor["id"]),
            )
        else:
            get_db().execute(
                "DELETE FROM endgame_pop_inventory WHERE member_id=? AND item_key=?",
                (holder["id"], item_key),
            )
        get_db().commit()
        return jsonify(endgame_pop_inventory_payload())

    @app.post("/endgame/auctions")
    @admin_required
    def create_endgame_auction():
        if not can_create_guild_events():
            abort(403)
        event_id = request.form.get("event_id", type=int)
        boss = request.form.get("boss", "").strip()
        duration_minutes = request.form.get("duration_minutes", type=int)
        if duration_minutes not in range(3, 11):
            abort(400, description="Choose an auction duration between 3 and 10 minutes.")
        boss_items = [dict(item) for item in (*ENDGAME_PRIORITY_ITEMS, *ENDGAME_AUCTION_EXTRA_DROPS)
                      if item["source"] == boss]
        event = get_db().execute("SELECT * FROM guild_events WHERE id=?", (event_id,)).fetchone()
        if not event or not is_endgame_guild_event(event) or not boss_items:
            abort(400, description="Choose an Endgame event and a valid Sky or Sea boss.")
        refresh_auction_statuses()
        if get_db().execute("SELECT 1 FROM endgame_auctions WHERE status='Active'").fetchone():
            abort(400, description="Finish the current auction before starting another.")
        actor = require_member_identity()
        now = datetime.utcnow()
        cursor = get_db().execute(
            """INSERT INTO endgame_auctions(event_id,area,boss,starts_at,ends_at,created_by)
               VALUES(?,?,?,?,?,?)""",
            (event_id, boss_items[0]["area"], boss, now.isoformat(timespec="seconds"),
             (now + timedelta(minutes=duration_minutes)).isoformat(timespec="seconds"), actor["id"]),
        )
        auction_id = cursor.lastrowid
        required_levels = gear_required_levels(str(Path(app.root_path) / "static" / "gear_catalog.json"))
        for item in boss_items:
            get_db().execute(
                """INSERT INTO endgame_auction_items(auction_id,item,target_item,family,p1,p2,p3,required_level)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (auction_id, auction_drop_name(item["name"]), item["name"], auction_item_family(item["name"]),
                 ",".join(item["p1"]), ",".join(item["p2"]), ",".join(item["p3"]),
                 required_levels.get(item["name"], 1)),
            )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "DKP Auction", "Auction started", f"{boss} / {event['name']} / {duration_minutes} minutes"),
        )
        get_db().commit()
        flash(f"Started a {duration_minutes}-minute {boss} auction.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="bidding-live"))

    @app.post("/api/endgame/auction-items/<int:item_id>/bid")
    @editor_required
    def place_endgame_bid(item_id):
        member = require_member_identity()
        payload = request.get_json(silent=True) or request.form
        try:
            amount = int(payload.get("amount", 0))
        except (TypeError, ValueError):
            abort(400, description="Enter a whole-number DKP bid.")
        job = str(payload.get("job", "")).strip().upper()
        item = get_db().execute(
            """SELECT i.*,a.status,a.ends_at,a.paused_at FROM endgame_auction_items i
               JOIN endgame_auctions a ON a.id=i.auction_id WHERE i.id=?""", (item_id,)
        ).fetchone()
        if not item or item["status"] != "Active" or item["paused_at"] or item["ends_at"] <= datetime.utcnow().isoformat(timespec="seconds"):
            abort(400, description="Bidding for this item is closed.")
        level = get_db().execute(
            "SELECT level FROM member_jobs WHERE member_id=? AND job=?", (member["id"], job)
        ).fetchone()
        tier = auction_priority_tier(item, job)
        if not level or level["level"] < item["required_level"] or not tier:
            abort(403, description="You do not have an eligible job leveled high enough to equip this item.")
        balances = current_dkp_balances()
        bid_cap = current_bid_cap(balances)["cap"]
        balance = balances.get(member["id"], {}).get("balance", 0)
        maximum = min(balance, bid_cap)
        if amount < 1 or amount > maximum:
            abort(400, description=f"Your bid must be between 1 and {max(0, maximum)} DKP.")
        get_db().execute(
            """INSERT INTO endgame_auction_bids(auction_item_id,member_id,job,amount)
               VALUES(?,?,?,?) ON CONFLICT(auction_item_id,member_id) DO UPDATE SET
               job=excluded.job,amount=excluded.amount,updated_at=CURRENT_TIMESTAMP""",
            (item_id, member["id"], job, amount),
        )
        active_bids = get_db().execute(
            """SELECT b.id,b.auction_item_id,b.amount,i.item FROM endgame_auction_bids b
               JOIN endgame_auction_items i ON i.id=b.auction_item_id
               JOIN endgame_auctions a ON a.id=i.auction_id
               WHERE b.member_id=? AND a.status='Active' ORDER BY b.updated_at DESC,b.id DESC""",
            (member["id"],),
        ).fetchall()
        overflow = max(0, sum(row["amount"] for row in active_bids) - balance)
        adjusted = []
        for other in active_bids:
            if not overflow or other["auction_item_id"] == item_id:
                continue
            reduction = min(overflow, other["amount"])
            next_amount = other["amount"] - reduction
            if next_amount:
                get_db().execute(
                    "UPDATE endgame_auction_bids SET amount=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (next_amount, other["id"]),
                )
            else:
                get_db().execute("DELETE FROM endgame_auction_bids WHERE id=?", (other["id"],))
            adjusted.append({"item": other["item"], "from": other["amount"], "to": next_amount})
            overflow -= reduction
        get_db().commit()
        return jsonify({"ok": True, "adjusted": adjusted, "auction": auction_payload()})

    @app.post("/endgame/auctions/<int:auction_id>/pause")
    @admin_required
    def toggle_endgame_auction_pause(auction_id):
        if not can_create_guild_events():
            abort(403)
        refresh_auction_statuses()
        auction = get_db().execute(
            "SELECT * FROM endgame_auctions WHERE id=?", (auction_id,)
        ).fetchone()
        if not auction or auction["status"] != "Active":
            abort(400, description="Only an active auction can be paused or resumed.")
        actor = require_member_identity()
        now = datetime.utcnow()
        if auction["paused_at"]:
            paused_at = datetime.fromisoformat(auction["paused_at"])
            ends_at = datetime.fromisoformat(auction["ends_at"]) + (now - paused_at)
            get_db().execute(
                "UPDATE endgame_auctions SET paused_at=NULL,ends_at=? WHERE id=?",
                (ends_at.isoformat(timespec="seconds"), auction_id),
            )
            action = "Auction resumed"
        else:
            get_db().execute(
                "UPDATE endgame_auctions SET paused_at=? WHERE id=?",
                (now.isoformat(timespec="seconds"), auction_id),
            )
            action = "Auction paused"
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "DKP Auction", action, auction["boss"]),
        )
        get_db().commit()
        return redirect(url_for("endgame_dashboard", _anchor="bidding-live"))

    @app.post("/endgame/auctions/<int:auction_id>/complete")
    @admin_required
    def complete_endgame_auction(auction_id):
        """End bidding immediately; winners are still reviewed before DKP changes."""
        if not can_create_guild_events():
            abort(403)
        auction = get_db().execute(
            "SELECT * FROM endgame_auctions WHERE id=?", (auction_id,)
        ).fetchone()
        if not auction or auction["status"] != "Active":
            abort(400, description="Only an active auction can be completed early.")
        actor = require_member_identity()
        get_db().execute(
            "UPDATE endgame_auctions SET status='Closed',ends_at=?,paused_at=NULL WHERE id=?",
            (datetime.utcnow().isoformat(timespec="seconds"), auction_id),
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "DKP Auction", "Auction completed early", auction["boss"]),
        )
        get_db().commit()
        flash(f"Stopped bidding for {auction['boss']}. Review winners before deducting DKP.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="bidding-live"))

    @app.post("/endgame/auctions/<int:auction_id>/reopen")
    @admin_required
    def reopen_endgame_auction(auction_id):
        """Restore a completed auction to active bidding so its results can be corrected."""
        if not can_create_guild_events():
            abort(403)
        auction = get_db().execute(
            "SELECT * FROM endgame_auctions WHERE id=?", (auction_id,)
        ).fetchone()
        if not auction or auction["status"] not in ("Closed", "Confirmed"):
            abort(400, description="Only a closed or completed auction can be reopened.")
        if get_db().execute("SELECT 1 FROM endgame_auctions WHERE status='Active'").fetchone():
            abort(400, description="Finish the current auction before reopening another one.")
        actor = require_member_identity()
        restored_awards = get_db().execute(
            "SELECT COUNT(*) count FROM endgame_loot_awards WHERE auction_id=?", (auction_id,)
        ).fetchone()["count"]
        get_db().execute("DELETE FROM endgame_loot_awards WHERE auction_id=?", (auction_id,))
        get_db().execute(
            """UPDATE endgame_auctions
               SET status='Active',starts_at=?,ends_at=?,paused_at=NULL,confirmed_at=NULL WHERE id=?""",
            (datetime.utcnow().isoformat(timespec="seconds"),
             (datetime.utcnow() + timedelta(minutes=5)).isoformat(timespec="seconds"), auction_id),
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "DKP Auction", "Auction reopened for editing",
             f"{auction['boss']} / restored {restored_awards} awards"),
        )
        get_db().commit()
        flash(f"Reopened {auction['boss']} for five minutes. {restored_awards} DKP awards were restored.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="bidding-live"))

    @app.post("/endgame/auctions/<int:auction_id>/confirm")
    @admin_required
    def confirm_endgame_auction(auction_id):
        if not can_create_guild_events():
            abort(403)
        refresh_auction_statuses()
        auction = get_db().execute("SELECT * FROM endgame_auctions WHERE id=?", (auction_id,)).fetchone()
        if not auction or auction["status"] != "Closed":
            abort(400, description="Wait for the countdown to finish before confirming winners.")
        actor = require_member_identity()
        balances = current_dkp_balances()
        awards = 0
        for item in get_db().execute("SELECT * FROM endgame_auction_items WHERE auction_id=?", (auction_id,)).fetchall():
            winner_id = request.form.get(f"winner_{item['id']}", type=int)
            if not winner_id:
                continue
            bid = get_db().execute(
                "SELECT * FROM endgame_auction_bids WHERE auction_item_id=? AND member_id=?",
                (item["id"], winner_id),
            ).fetchone()
            if not bid or bid["amount"] > balances.get(winner_id, {}).get("balance", 0):
                abort(400, description=f"The selected winner for {item['item']} no longer has enough DKP.")
            tier = auction_priority_tier(item, bid["job"])
            get_db().execute(
                """INSERT INTO endgame_loot_awards
                   (event_id,recipient_member_id,item,job,family,distribution,classification,dkp_cost,auction_id,auction_item_id,recorded_by)
                   VALUES(?,?,?,?,?,?, 'Major Loot',?,?,?,?)""",
                (auction["event_id"], winner_id, item["item"], bid["job"], item["family"],
                 f"{'Freelot' if tier == 4 else f'P{tier}'}", bid["amount"], auction_id, item["id"], actor["id"]),
            )
            balances[winner_id]["balance"] -= bid["amount"]
            awards += 1
        get_db().execute(
            "UPDATE endgame_auctions SET status='Confirmed',confirmed_at=CURRENT_TIMESTAMP WHERE id=?", (auction_id,)
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "DKP Auction", "Winners confirmed", f"{auction['boss']}: {awards} loot awards"),
        )
        get_db().commit()
        flash(f"Confirmed {awards} auction awards and deducted the winning DKP.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="bidding-live"))

    @app.post("/endgame/auctions/<int:auction_id>/delete")
    @admin_required
    def delete_endgame_auction(auction_id):
        if not can_create_guild_events():
            abort(403)
        refresh_auction_statuses()
        auction = get_db().execute("SELECT * FROM endgame_auctions WHERE id=?", (auction_id,)).fetchone()
        if not auction or auction["status"] not in ("Active", "Closed", "Confirmed"):
            abort(400, description="Only an auction record can be discarded.")
        actor = require_member_identity()
        confirmed_awards = get_db().execute(
            "SELECT COUNT(*) count FROM endgame_loot_awards WHERE auction_id=?", (auction_id,)
        ).fetchone()["count"]
        # DKP balances are derived from awards, so deleting a confirmed auction
        # and its linked awards restores the deducted DKP automatically.
        get_db().execute("DELETE FROM endgame_loot_awards WHERE auction_id=?", (auction_id,))
        get_db().execute("DELETE FROM endgame_auctions WHERE id=?", (auction_id,))
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "DKP Auction", "Auction discarded", f"{auction['boss']} / reversed {confirmed_awards} awards"),
        )
        get_db().commit()
        flash(f"Discarded the {auction['boss']} auction and reversed {confirmed_awards} linked DKP awards.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="bidding-live"))

    def is_endgame_guild_event(event):
        """Classify an event by its Discord source while preserving the two archives."""
        name = str(event["name"] or "")
        start_at = str(event["start_at"] or "")
        source_channel = str(event["discord_channel"] or "").strip()
        channel_key = re.sub(r"[^a-z0-9]+", "-", source_channel.casefold()).strip("-")
        if name == "Sky Operations" and start_at[:10] in {"2026-08-06", "2026-08-13"}:
            return True
        if re.search(
            r"chains?\s+of\s+prom[ae]thia.*(?:4[- ]3|chapter\s*4.*mission\s*3)",
            name, re.I,
        ):
            return False
        if channel_key in {"events-posting-and-signup-only", "event-posting-and-signup-only"}:
            return False
        configured_endgame = str(app.config.get("DISCORD_EVENT_CHANNEL_ID", "")).strip().casefold()
        return bool(
            not source_channel or channel_key == "endgame-events-only"
            or source_channel.casefold() == configured_endgame
        )

    def event_bot_signup_users(payload):
        event_result = payload.get("event", payload) if isinstance(payload, dict) else {}
        players = event_result.get("players", {}) if isinstance(event_result, dict) else {}
        if isinstance(players, dict):
            return [
                {"display_name": name, "status": details.get("status"), "job": details.get("job")}
                for name, details in players.items() if isinstance(details, dict)
            ]
        if isinstance(players, list):
            return [item for item in players if isinstance(item, dict)]
        return []

    def replace_event_bot_signups(db, event_id, payload):
        users = event_bot_signup_users(payload)
        members_by_name = {
            row["name"].casefold(): row for row in db.execute("SELECT id,name FROM members")
        }
        matched = []
        for item in users:
            display_name = html.unescape(str(
                item.get("display_name") or item.get("name") or item.get("discord_name") or ""
            )).strip()
            canonical_name = MEMBER_NAME_ALIASES.get(display_name.casefold(), display_name)
            member = members_by_name.get(canonical_name.casefold())
            status = str(item.get("status") or "").strip().casefold()
            status = {"yes": "going", "no": "cant", "can't": "cant", "cannot": "cant"}.get(status, status)
            job = str(item.get("job") or item.get("selected_job") or "").strip().upper()
            if member and status in ("going", "maybe", "cant"):
                matched.append((event_id, member["id"], status, job if job in JOBS else "", display_name))
        db.execute("DELETE FROM guild_event_signups WHERE event_id=? AND source='Discord'", (event_id,))
        if matched:
            db.executemany(
                """INSERT OR REPLACE INTO guild_event_signups
                   (event_id,member_id,source,rsvp_status,selected_job,discord_name,updated_at)
                   VALUES(?,?,'Discord',?,?,?,CURRENT_TIMESTAMP)""", matched,
            )
        return len(users), len(matched)

    @app.post("/endgame/events/sync-discord")
    @admin_required
    def sync_discord_events():
        if not can_create_guild_events():
            abort(403, description="Only designated event administrators can import Discord events.")
        return_to_alliance = request.form.get("next", "").strip() == "alliance_builder"
        def sync_redirect():
            if return_to_alliance:
                return redirect(url_for("alliance_builder"))
            return redirect(url_for("endgame_dashboard", _anchor="event-calendar"))

        api_url = str(app.config.get("HOKUTEN_EVENT_BOT_API_URL", "")).strip()
        api_token = str(app.config.get("HOKUTEN_EVENT_BOT_API_TOKEN", "")).strip()
        if not api_url or not api_token:
            abort(400, description="Hokuten Event Bot event sync is not configured.")
        try:
            response = hokuten_event_bot_request(api_url, api_token, "GET", "/api/events") or {}
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            flash("Hokuten Event Bot events could not be retrieved.", "error")
            return sync_redirect()

        actor = require_member_identity()
        db = get_db()
        imported = linked = skipped = 0
        for raw_event in normalize_event_bot_listing(response):
            event = parse_event_bot_record(raw_event)
            if not event:
                skipped += 1
                continue
            existing = None
            if event["discord_message_id"]:
                existing = db.execute(
                    "SELECT id,discord_event_id,discord_message_id,discord_channel FROM guild_events WHERE discord_message_id=?",
                    (event["discord_message_id"],),
                ).fetchone()
            if not existing and event["discord_event_id"]:
                existing = db.execute(
                    "SELECT id,discord_event_id,discord_message_id,discord_channel FROM guild_events WHERE discord_event_id=?",
                    (event["discord_event_id"],),
                ).fetchone()
            start_iso = event["start_at"].isoformat(timespec="minutes")
            if not existing:
                existing = db.execute(
                    """SELECT id,discord_event_id,discord_message_id,discord_channel
                       FROM guild_events WHERE name=? COLLATE NOCASE AND start_at=?""",
                    (event["name"], start_iso),
                ).fetchone()
            if existing:
                newly_linked = bool(
                    (not existing["discord_event_id"] and event["discord_event_id"]) or
                    (not existing["discord_message_id"] and event["discord_message_id"])
                )
                db.execute(
                    """UPDATE guild_events SET
                           discord_event_id=CASE WHEN discord_event_id='' THEN ? ELSE discord_event_id END,
                           discord_message_id=CASE WHEN discord_message_id='' THEN ? ELSE discord_message_id END,
                           discord_channel=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (event["discord_event_id"], event["discord_message_id"],
                     event["discord_channel"], existing["id"]),
                )
                linked += int(newly_linked)
                continue
            db.execute(
                """INSERT INTO guild_events
                   (creator_member_id,name,description,start_at,end_at,location,
                    discord_event_id,discord_message_id,discord_channel,dkp_value)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (actor["id"], event["name"], event["description"], start_iso,
                 event["end_at"].isoformat(timespec="minutes"), event["location"],
                 event["discord_event_id"], event["discord_message_id"], event["discord_channel"],
                 event["dkp_value"]),
            )
            imported += 1
        db.execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "Event Calendar", "Discord events synchronized",
             f"{imported} imported / {linked} linked / {skipped} skipped"),
        )
        db.commit()

        signup_events = responses = matched_members = failed_signups = 0
        connected_events = db.execute(
            "SELECT id,discord_message_id FROM guild_events WHERE discord_message_id<>'' ORDER BY id"
        ).fetchall()
        for connected in connected_events:
            try:
                signup_payload = hokuten_event_bot_request(
                    api_url, api_token, "GET", f"/api/events/{connected['discord_message_id']}"
                ) or {}
                detail_channel = event_bot_channel(signup_payload)
                if detail_channel:
                    db.execute(
                        "UPDATE guild_events SET discord_channel=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (detail_channel, connected["id"]),
                    )
                event_responses, event_matches = replace_event_bot_signups(
                    db, connected["id"], signup_payload,
                )
                signup_events += 1
                responses += event_responses
                matched_members += event_matches
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
                failed_signups += 1
        db.execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "Event Calendar", "All Discord signups synchronized",
             f"{signup_events} events / {responses} responses / {matched_members} matched / {failed_signups} failed"),
        )
        db.commit()
        flash(
            f"Discord event sync complete: {imported} imported, {linked} linked, "
            f"{skipped} skipped; refreshed signups for {signup_events} event(s) "
            f"and matched {matched_members} roster response(s)"
            f"{' (' + str(failed_signups) + ' failed)' if failed_signups else ''}.", "success",
        )
        return sync_redirect()

    @app.post("/endgame/events/new")
    @admin_required
    def create_guild_event():
        if not can_create_guild_events():
            abort(403, description="Only designated event administrators can create guild events.")
        creator = require_member_identity()
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()[:1000]
        location = request.form.get("location", "").strip()[:100] or "Hokuten Knights"
        start_at = parse_local_datetime(request.form.get("start_at", ""))
        if not name or len(name) > 100 or not start_at or start_at.minute % 15:
            abort(400, description="Enter an event name and choose a start time in a 15-minute interval.")
        if start_at.replace(tzinfo=EASTERN_TIME) <= datetime.now(EASTERN_TIME):
            abort(400, description="Choose an event date and time in the future.")
        # Discord requires an end timestamp for external scheduled events.
        # Keep that implementation detail out of the form and use a standard window.
        end_at = start_at + timedelta(hours=3)
        discord_event_id = ""
        discord_message_id = ""
        token = app.config.get("DISCORD_BOT_TOKEN", "")
        channel_id = str(app.config.get("DISCORD_EVENT_CHANNEL_ID", "")).strip()
        event_bot_api_url = str(app.config.get("HOKUTEN_EVENT_BOT_API_URL", "")).strip()
        event_bot_api_token = str(app.config.get("HOKUTEN_EVENT_BOT_API_TOKEN", "")).strip()
        if event_bot_api_url and event_bot_api_token:
            api_payload = {
                "name": name,
                "description": description,
                "date": start_at.strftime("%A %B %d %Y"),
                "time": start_at.strftime("%I:%M %p").lstrip("0"),
                "duration": "3",
                "host": creator["name"],
                "channel": "endgame-events-only",
            }
            try:
                api_event = hokuten_event_bot_request(
                    event_bot_api_url, event_bot_api_token, "POST", "/api/events", api_payload,
                ) or {}
                api_result = api_event.get("event", api_event)
                discord_event_id = str(
                    api_result.get("discord_event_id") or api_result.get("scheduled_event_id") or
                    api_result.get("event_id") or ""
                )
                discord_message_id = str(
                    api_result.get("discord_message_id") or api_result.get("message_id") or ""
                )
                if not discord_message_id:
                    raise ValueError("The event bot response did not include a message ID.")
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
                flash("The website event was saved, but Hokuten Event Bot could not register it.", "error")
        elif token:
            payload = {
                "name": name, "description": description or None,
                "privacy_level": 2, "entity_type": 3, "channel_id": None,
                "entity_metadata": {"location": location},
                "scheduled_start_time": start_at.replace(tzinfo=EASTERN_TIME).isoformat(),
                "scheduled_end_time": end_at.replace(tzinfo=EASTERN_TIME).isoformat(),
            }
            try:
                discord_event = discord_bot_request(
                    token, "POST", f"/guilds/{app.config['DISCORD_GUILD_ID']}/scheduled-events", payload,
                )
                discord_event_id = str(discord_event.get("id", ""))
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
                flash("The website event was saved, but Discord could not create its scheduled event.", "error")
            if discord_event_id and channel_id:
                event_url = f"https://discord.com/events/{app.config['DISCORD_GUILD_ID']}/{discord_event_id}"
                local_start = start_at.replace(tzinfo=EASTERN_TIME)
                empty_group = "No players have selected this role yet."
                signup_payload = {
                    "allowed_mentions": {"parse": []},
                    "embeds": [{
                        "title": f"⚔️ Hokuten Knights — {name}"[:256],
                        "description": "━━━━━━━━━━━━━━━━━━━━━━",
                        "color": 15844367,
                        "fields": [
                            {"name": "📅 Date", "value": local_start.strftime("%A %B %d %Y"), "inline": True},
                            {"name": "🕒 Time", "value": local_start.strftime("%I:%M %p").lstrip("0"), "inline": True},
                            {"name": "⏳ Duration", "value": "3", "inline": True},
                            {"name": "👑 Hosted By", "value": creator["name"], "inline": False},
                            {"name": "📍 Gather Location", "value": location, "inline": False},
                            {"name": "📜 Description / Requirements", "value": description or "No additional requirements.", "inline": False},
                            {"name": "📆 Discord Event", "value": f"[Open Server Calendar Event]({event_url})", "inline": False},
                            {"name": "📊 Confirmed Alliance Setup", "value": "🛡️ Tanks: **0**\n✨ Healers: **0**\n🎵 Support: **0**\n⚔️ Damage Dealers: **0**", "inline": False},
                            {"name": "🛡️ Tanks (0 confirmed)", "value": empty_group, "inline": False},
                            {"name": "✨ Healers (0 confirmed)", "value": empty_group, "inline": False},
                            {"name": "🎵 Support (0 confirmed)", "value": empty_group, "inline": False},
                            {"name": "⚔️ Damage Dealers (0 confirmed)", "value": empty_group, "inline": False},
                            {"name": "✅ Going (0)", "value": "No responses yet.", "inline": False},
                            {"name": "❓ Maybe (0)", "value": "No responses yet.", "inline": False},
                            {"name": "❌ Can't Attend (0)", "value": "No responses yet.", "inline": False},
                        ],
                        "footer": {"text": "Hokuten Knights Event Board • Maybe players are not included in confirmed totals"},
                    }],
                    "components": [{"type": 1, "components": [
                        {"type": 2, "custom_id": "hokuten_event_going", "style": 3, "label": "Going", "emoji": {"name": "✅"}},
                        {"type": 2, "custom_id": "hokuten_event_maybe", "style": 2, "label": "Maybe", "emoji": {"name": "❓"}},
                        {"type": 2, "custom_id": "hokuten_event_cant", "style": 4, "label": "Can't Attend", "emoji": {"name": "❌"}},
                        {"type": 2, "custom_id": "hokuten_event_choose_job", "style": 1, "label": "Choose Job", "emoji": {"name": "⚔️"}},
                        {"type": 2, "custom_id": "hokuten_event_edit", "style": 2, "label": "Edit Event", "emoji": {"name": "✏️"}},
                    ]}],
                }
                try:
                    announcement_message = discord_bot_request(
                        token, "POST", f"/channels/{channel_id}/messages",
                        signup_payload,
                    )
                    discord_message_id = str((announcement_message or {}).get("id", ""))
                except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
                    flash("The Discord event was created, but its channel announcement could not be posted.", "error")
        event_id = get_db().execute(
            """INSERT INTO guild_events
               (creator_member_id,name,description,start_at,end_at,location,discord_event_id,discord_message_id)
               VALUES(?,?,?,?,?,?,?,?)""",
            (creator["id"], name, description, start_at.isoformat(timespec="minutes"),
             end_at.isoformat(timespec="minutes"), location, discord_event_id, discord_message_id),
        ).lastrowid
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (creator["id"], "Event Calendar", "Event created", f"{name} / {start_at.isoformat(timespec='minutes')}"),
        )
        get_db().commit()
        flash(f"Created {name}{' in Discord and on the website' if (discord_event_id or discord_message_id) else ' on the website'}.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="event-calendar"))

    @app.post("/endgame/events/<int:event_id>/dkp")
    @admin_required
    def update_guild_event_dkp(event_id):
        if not can_create_guild_events():
            abort(403, description="Only designated event administrators can update event DKP.")
        event = get_db().execute(
            "SELECT id,name,start_at,discord_channel,dkp_value FROM guild_events WHERE id=?", (event_id,)
        ).fetchone()
        if not event:
            abort(404)
        if not is_endgame_guild_event(event):
            abort(400, description="User Events do not award DKP.")
        try:
            requested_dkp = float(request.form.get("dkp_value", ""))
        except ValueError:
            abort(400, description="Enter a valid DKP amount.")
        if not requested_dkp.is_integer() or not 0 <= requested_dkp <= 24:
            abort(400, description="Event DKP must be a whole number between 0 and 24.")
        dkp_value = int(requested_dkp)
        editor = require_member_identity()
        get_db().execute(
            "UPDATE guild_events SET dkp_value=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (dkp_value, event_id),
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (editor["id"], "Event DKP", "DKP value updated",
             f"{event['name']} / Event #{event_id}: {event['dkp_value']} to {dkp_value} DKP"),
        )
        get_db().commit()
        flash(f"Updated {event['name']} to {dkp_value:g} DKP per attendee.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="event-calendar"))

    @app.post("/endgame/events/<int:event_id>/delete")
    @admin_required
    def delete_guild_event(event_id):
        if not can_create_guild_events():
            abort(403, description="Only designated event administrators can delete events.")
        event = get_db().execute("SELECT * FROM guild_events WHERE id=?", (event_id,)).fetchone()
        if not event:
            abort(404)
        if event["discord_event_id"] and app.config.get("DISCORD_BOT_TOKEN"):
            try:
                token = app.config["DISCORD_BOT_TOKEN"]
                channel_id = str(app.config.get("DISCORD_EVENT_CHANNEL_ID", "")).strip()
                message_id = event["discord_message_id"]
                if not message_id and channel_id:
                    # Older events predate announcement-ID tracking. Locate their bot post
                    # by the unique scheduled-event URL before deleting the event itself.
                    event_url = f"discord.com/events/{app.config['DISCORD_GUILD_ID']}/{event['discord_event_id']}"
                    messages = discord_bot_request(
                        token, "GET", f"/channels/{channel_id}/messages?limit=100",
                    ) or []
                    match = next(
                        (message for message in messages if event_url in message.get("content", "")), None,
                    )
                    message_id = str((match or {}).get("id", ""))
                if message_id and channel_id:
                    try:
                        discord_bot_request(
                            token, "DELETE", f"/channels/{channel_id}/messages/{message_id}",
                        )
                    except HTTPError as error:
                        # Discord returns Unknown Message when a previous partial deletion
                        # already removed the post. Continue with the scheduled event.
                        if error.code != 404:
                            raise
                try:
                    discord_bot_request(
                        token, "DELETE",
                        f"/guilds/{app.config['DISCORD_GUILD_ID']}/scheduled-events/{event['discord_event_id']}",
                    )
                except HTTPError as error:
                    # Deletion is idempotent: an already-removed Discord event is success.
                    if error.code != 404:
                        raise
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
                flash("Discord could not remove the full event and channel post, so the website event was preserved.", "error")
                return redirect(url_for("endgame_dashboard", _anchor="event-calendar"))
        actor = require_member_identity()
        get_db().execute("DELETE FROM guild_events WHERE id=?", (event_id,))
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "Event Calendar", "Event deleted", f"{event['name']} / Event #{event_id}"),
        )
        get_db().commit()
        flash(f"Deleted {event['name']} from the website and Discord.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="event-calendar"))

    @app.post("/endgame/events/<int:event_id>/sync")
    @admin_required
    def sync_guild_event(event_id):
        if not can_create_guild_events():
            abort(403, description="Only designated event administrators can synchronize guild events.")
        event = get_db().execute("SELECT * FROM guild_events WHERE id=?", (event_id,)).fetchone()
        if not event:
            abort(404)
        api_ready = bool(
            event["discord_message_id"]
            and app.config.get("HOKUTEN_EVENT_BOT_API_URL")
            and app.config.get("HOKUTEN_EVENT_BOT_API_TOKEN")
        )
        discord_ready_for_sync = bool(event["discord_event_id"] and app.config.get("DISCORD_BOT_TOKEN"))
        if not api_ready and not discord_ready_for_sync:
            abort(400, description="This event is not connected to Discord.")
        try:
            if api_ready:
                api_result = hokuten_event_bot_request(
                    app.config["HOKUTEN_EVENT_BOT_API_URL"],
                    app.config["HOKUTEN_EVENT_BOT_API_TOKEN"], "GET",
                    f"/api/events/{event['discord_message_id']}",
                ) or {}
                users = event_bot_signup_users(api_result)
            else:
                users = discord_bot_request(
                    app.config["DISCORD_BOT_TOKEN"], "GET",
                    f"/guilds/{app.config['DISCORD_GUILD_ID']}/scheduled-events/{event['discord_event_id']}/users?limit=100&with_member=true",
                ) or []
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            flash("Discord signups could not be refreshed.", "error")
            return redirect(url_for("endgame_dashboard", _anchor="event-calendar"))
        matched = []
        if api_ready:
            _response_count, matched_count = replace_event_bot_signups(get_db(), event_id, api_result)
        else:
            get_db().execute("DELETE FROM guild_event_signups WHERE event_id=? AND source='Discord'", (event_id,))
            discord_ids = [str(item.get("user", {}).get("id", "")) for item in users]
            placeholders = ",".join("?" for _ in discord_ids)
            members = get_db().execute(
                f"SELECT id,name FROM members WHERE discord_user_id IN ({placeholders})", discord_ids
            ).fetchall() if discord_ids else []
            matched = [(event_id, row["id"], "going", "", row["name"]) for row in members]
        if not api_ready and matched:
            get_db().executemany(
                """INSERT OR REPLACE INTO guild_event_signups
                   (event_id,member_id,source,rsvp_status,selected_job,discord_name,updated_at)
                   VALUES(?,?,'Discord',?,?,?,CURRENT_TIMESTAMP)""", matched,
            )
        actor = require_member_identity()
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "Event Calendar", "Discord signups synced",
             f"Event #{event_id}: {len(users)} responses, {matched_count if api_ready else len(matched)} matched members"),
        )
        get_db().commit()
        flash(f"Synced {len(users)} Discord response(s); matched {matched_count if api_ready else len(matched)} roster member(s).", "success")
        return redirect(url_for("endgame_dashboard", _anchor="event-calendar"))

    @app.post("/endgame/events/<int:event_id>/attendance")
    @admin_required
    def update_guild_event_attendance(event_id):
        if not can_create_guild_events():
            abort(403, description="Only designated event administrators can update attendance.")
        event = get_db().execute(
            "SELECT * FROM guild_events WHERE id=?", (event_id,)
        ).fetchone()
        if not event:
            abort(404)
        updater = require_member_identity()
        member_ids = {int(value) for value in request.form.getlist("member_ids") if value.isdigit()}
        valid_ids = {row["id"] for row in get_db().execute("SELECT id FROM members").fetchall()}
        member_ids &= valid_ids
        previous_ids = {row["member_id"] for row in get_db().execute(
            "SELECT member_id FROM guild_event_attendance WHERE event_id=? AND attended=1", (event_id,),
        ).fetchall()}
        changed_ids = sorted(member_ids ^ previous_ids)
        changed_names = {
            row["id"]: row["name"] for row in get_db().execute(
                f"SELECT id,name FROM members WHERE id IN ({','.join('?' for _ in changed_ids)})",
                changed_ids,
            ).fetchall()
        } if changed_ids else {}
        added = [changed_names[item] for item in sorted(member_ids - previous_ids)]
        removed = [changed_names[item] for item in sorted(previous_ids - member_ids)]
        get_db().execute("DELETE FROM guild_event_attendance WHERE event_id=?", (event_id,))
        get_db().executemany(
            "INSERT INTO guild_event_attendance(event_id,member_id,attended,updated_by) VALUES(?,?,1,?)",
            [(event_id, member_id, updater["id"]) for member_id in sorted(member_ids)],
        )
        if is_endgame_guild_event(event) and event["start_at"] <= "2026-08-13T23:59":
            dkp_value = float(event["dkp_value"])
            get_db().executemany(
                """INSERT INTO endgame_attendance_dkp_adjustments(event_id,member_id,dkp_delta)
                   VALUES(?,?,?) ON CONFLICT(event_id,member_id) DO UPDATE SET
                   dkp_delta=dkp_delta+excluded.dkp_delta,updated_at=CURRENT_TIMESTAMP""",
                [(event_id, member_id, dkp_value) for member_id in member_ids - previous_ids]
                + [(event_id, member_id, -dkp_value) for member_id in previous_ids - member_ids],
            )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (updater["id"], "Event Attendance", "Attendance updated",
             f"Event #{event_id}: added {', '.join(added) or 'none'}; removed {', '.join(removed) or 'none'}; {len(member_ids)} attended"),
        )
        event_start = parse_local_datetime(event["start_at"])
        if event_start and event_start < eastern_now_naive():
            get_db().execute("UPDATE guild_events SET status='Completed' WHERE id=?", (event_id,))
        get_db().commit()
        flash("Event attendance updated.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="event-calendar"))

    @app.post("/endgame/events/<int:event_id>/attendance/from-signups")
    @admin_required
    def sync_attendance_from_signups(event_id):
        if not can_create_guild_events():
            abort(403, description="Only designated event administrators can update attendance.")
        db = get_db()
        event = db.execute(
            "SELECT * FROM guild_events WHERE id=?", (event_id,)
        ).fetchone()
        if not event:
            abort(404)
        going_ids = {
            row["member_id"] for row in db.execute(
                """SELECT member_id FROM guild_event_signups
                   WHERE event_id=? AND rsvp_status='going'""", (event_id,),
            ).fetchall()
        }
        missing_ids = {
            int(value) for value in request.form.getlist("missing_ids") if value.isdigit()
        } & going_ids
        attended_ids = going_ids - missing_ids
        previous_ids = {
            row["member_id"] for row in db.execute(
                "SELECT member_id FROM guild_event_attendance WHERE event_id=? AND attended=1",
                (event_id,),
            ).fetchall()
        }
        updater = require_member_identity()
        db.execute("DELETE FROM guild_event_attendance WHERE event_id=?", (event_id,))
        if attended_ids:
            db.executemany(
                """INSERT INTO guild_event_attendance(event_id,member_id,attended,updated_by)
                   VALUES(?,?,1,?)""",
                [(event_id, member_id, updater["id"]) for member_id in sorted(attended_ids)],
            )
        if is_endgame_guild_event(event) and event["start_at"] <= "2026-08-13T23:59":
            dkp_value = float(event["dkp_value"])
            db.executemany(
                """INSERT INTO endgame_attendance_dkp_adjustments(event_id,member_id,dkp_delta)
                   VALUES(?,?,?) ON CONFLICT(event_id,member_id) DO UPDATE SET
                   dkp_delta=dkp_delta+excluded.dkp_delta,updated_at=CURRENT_TIMESTAMP""",
                [(event_id, member_id, dkp_value) for member_id in attended_ids - previous_ids]
                + [(event_id, member_id, -dkp_value) for member_id in previous_ids - attended_ids],
            )
        names = {row["id"]: row["name"] for row in db.execute("SELECT id,name FROM members")}
        added = [names[item] for item in sorted(attended_ids - previous_ids) if item in names]
        removed = [names[item] for item in sorted(previous_ids - attended_ids) if item in names]
        missing = [names[item] for item in sorted(missing_ids) if item in names]
        db.execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (updater["id"], "Event Attendance", "Attendance synced from Discord signups",
             f"{event['name']} / Event #{event_id}: attended {len(attended_ids)}; "
             f"missing {', '.join(missing) or 'none'}; added {', '.join(added) or 'none'}; "
             f"removed {', '.join(removed) or 'none'}"),
        )
        event_start = parse_local_datetime(event["start_at"])
        if event_start and event_start < eastern_now_naive():
            db.execute("UPDATE guild_events SET status='Completed' WHERE id=?", (event_id,))
        db.commit()
        flash(
            f"Attendance synced: {len(attended_ids)} attending, {len(missing_ids)} marked missing.",
            "success",
        )
        return redirect(url_for("endgame_dashboard", _anchor="event-calendar"))

    @app.post("/endgame/job-change-requests")
    @editor_required
    def request_endgame_job_change():
        member = require_member_identity()
        main_job = request.form.get("main_job", "").strip().upper()
        secondary_job = request.form.get("secondary_job", "").strip().upper()
        if main_job not in JOBS or (secondary_job and secondary_job not in JOBS):
            abort(400, description="Choose valid main and secondary jobs.")
        if main_job == secondary_job:
            abort(400, description="Main and secondary jobs must be different.")
        if get_db().execute(
            "SELECT 1 FROM endgame_job_change_requests WHERE member_id=? AND status='Pending'",
            (member["id"],),
        ).fetchone():
            abort(400, description="You already have a pending job-change request.")
        recent = get_db().execute(
            """SELECT 1 FROM endgame_job_change_requests WHERE member_id=? AND status='Approved'
               AND reviewed_at >= datetime('now','-30 days')""", (member["id"],)
        ).fetchone()
        if recent:
            abort(400, description="Approved job selections can only be changed once every 30 days.")
        get_db().execute(
            """INSERT INTO endgame_job_change_requests(member_id,requested_main,requested_secondary)
               VALUES(?,?,?)""", (member["id"], main_job, secondary_job),
        )
        get_db().commit()
        flash("Your job-selection request was sent to leadership.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="jobs"))

    @app.post("/endgame/job-change-requests/<int:request_id>/review")
    @admin_required
    def review_endgame_job_change(request_id):
        if not can_create_guild_events():
            abort(403, description="Only designated administrators can review job changes.")
        decision = request.form.get("decision", "")
        if decision not in {"Approved", "Denied"}:
            abort(400, description="Choose approve or deny.")
        change = get_db().execute(
            "SELECT * FROM endgame_job_change_requests WHERE id=? AND status='Pending'", (request_id,)
        ).fetchone()
        if not change:
            abort(404)
        reviewer = require_member_identity()
        member = get_db().execute("SELECT name FROM members WHERE id=?", (change["member_id"],)).fetchone()
        if decision == "Approved":
            get_db().execute(
                """INSERT INTO endgame_job_registrations(member_id,main_job,secondary_job,updated_at)
                   VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(member_id) DO UPDATE SET
                   main_job=excluded.main_job,secondary_job=excluded.secondary_job,
                   updated_at=CURRENT_TIMESTAMP""",
                (change["member_id"], change["requested_main"], change["requested_secondary"]),
            )
        get_db().execute(
            """UPDATE endgame_job_change_requests SET status=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP
               WHERE id=?""", (decision, reviewer["id"], request_id),
        )
        details = f"{member['name']}: {change['requested_main']} / {change['requested_secondary'] or 'None'} ({decision})"
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (reviewer["id"], "Job Selections", f"Request {decision.lower()}", details),
        )
        get_db().commit()
        flash(f"{member['name']}'s job-selection request was {decision.lower()}.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="jobs"))

    @app.post("/endgame/loot")
    @admin_required
    def record_endgame_loot():
        if not can_create_guild_events():
            abort(403, description="Only designated administrators can record loot.")
        event_id = request.form.get("event_id", "")
        member_id = request.form.get("member_id", "")
        item = request.form.get("item", "").strip()[:120]
        job = request.form.get("job", "").strip().upper()
        family = manual_loot_family(item)
        distribution = request.form.get("distribution", "").strip()
        classification = request.form.get("classification", "").strip()
        try:
            requested_cost = float(request.form.get("dkp_cost", "0") or 0)
            dkp_cost = int(requested_cost) if requested_cost.is_integer() else -1
        except ValueError:
            dkp_cost = -1
        if not event_id.isdigit() or not get_db().execute(
            "SELECT 1 FROM guild_events WHERE id=?", (event_id,)
        ).fetchone():
            abort(400, description="Choose a valid current or past event.")
        recipient = get_db().execute(
            "SELECT id,name FROM members WHERE id=?", (member_id,)
        ).fetchone() if member_id.isdigit() else None
        if (not recipient or not item or job not in JOBS or family not in
                {"Weapons", "Head", "Body", "Hands", "Legs", "Feet", "Accessories", "Other"}
                or distribution not in {"P1", "P2", "P3", "Freelot"}
                or classification not in {"Major Loot", "Standard"} or not 0 <= dkp_cost <= 999):
            abort(400, description="Complete the loot award using valid selections.")
        recorder = require_member_identity()
        get_db().execute(
            """INSERT INTO endgame_loot_awards
               (event_id,recipient_member_id,item,job,family,distribution,classification,dkp_cost,recorded_by)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (int(event_id), recipient["id"], item, job, family, distribution,
             classification, dkp_cost, recorder["id"]),
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (recorder["id"], "Linkshell Loot", "Award recorded",
             f"{item} to {recipient['name']} ({job}, {distribution}, {classification})"),
        )
        get_db().commit()
        flash(f"Recorded {item} for {recipient['name']}.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="loot"))

    def bank_gil_value(raw):
        try:
            value = int(str(raw or "0").strip())
        except (TypeError, ValueError):
            return -1
        return value if 0 <= value <= 2_000_000_000 else -1

    def ls_bank_officer_ids():
        names = tuple(name.casefold() for name in DISCORD_ADMIN_CHARACTERS)
        rows = get_db().execute(
            "SELECT id FROM members WHERE discord_admin=1 OR lower(name) IN ({})".format(
                ",".join("?" for _ in names)
            ), names,
        ).fetchall()
        officer_ids = {row["id"] for row in rows}
        if is_admin() and current_member_id():
            officer_ids.add(current_member_id())
        return officer_ids

    def bank_saved_response(message, **payload):
        """Keep in-place LS Bank controls from forcing a dashboard reload."""
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"ok": True, "message": message, **payload})
        flash(message, "success")
        return redirect(url_for("endgame_dashboard", _anchor="bank"))

    @app.post("/endgame/bank")
    @admin_required
    def record_ls_bank_item():
        item = request.form.get("item", "").strip()[:120]
        event_id = request.form.get("event_id", "").strip()
        holder_id = request.form.get("holder_member_id", "").strip()
        purchaser_id = request.form.get("purchaser_member_id", "").strip()
        acquisition_kind = request.form.get("acquisition_kind", "").strip()
        status = request.form.get("status", "Held").strip()
        status = "Held" if status == "Drop" else status
        notes = request.form.get("notes", "").strip()[:500]
        try:
            quantity = int(request.form.get("quantity", "1"))
        except (TypeError, ValueError):
            quantity = 0
        purchase_gil = bank_gil_value(request.form.get("purchase_gil"))
        if "timeless" in item.casefold() and ("hourglass" in item.casefold() or "hrglass" in item.casefold()):
            acquisition_kind, event_id = "Other", ""
        acquisition_kind = {
            "Purchase": "Auction House", "Pop Item": "Other",
            "Timeless Hourglass": "Other", "Manual": "Other", "Merc Sell": "Mercenary",
        }.get(acquisition_kind, acquisition_kind)
        if acquisition_kind == "Donation" and not item and purchase_gil > 0:
            item = "Gil Donation"
        if acquisition_kind == "Event Drop":
            purchase_gil, purchaser_id = 0, ""
        elif not purchaser_id:
            purchaser_id = holder_id
        event = get_db().execute("SELECT id FROM guild_events WHERE id=?", (event_id,)).fetchone() if event_id.isdigit() else None
        holder = get_db().execute("SELECT id,name FROM members WHERE id=?", (holder_id,)).fetchone() if holder_id.isdigit() else None
        purchaser = get_db().execute("SELECT id,name FROM members WHERE id=?", (purchaser_id,)).fetchone() if purchaser_id.isdigit() else None
        sale_gil = 0
        if acquisition_kind == "Mercenary":
            status, sale_gil, purchase_gil = "Sold", purchase_gil, 0
        if (not item or not 1 <= quantity <= 9999 or purchase_gil < 0
                or acquisition_kind not in {"Event Drop", "Auction House", "Bazaar", "Donation", "Other", "Mercenary", "Purchase", "Pop Item", "Timeless Hourglass", "Merc Sell", "Manual"}
                or status not in {"Held", "Purchased", "Sold"}
                or (acquisition_kind == "Mercenary" and sale_gil <= 0)
                or (event_id and not event) or (holder_id and not holder) or (purchaser_id and not purchaser)
                or (acquisition_kind == "Donation" and (not purchaser or not holder))
                or (acquisition_kind not in {"Event Drop", "Donation"}
                    and (not purchaser or purchaser["id"] not in ls_bank_officer_ids()))):
            abort(400, description="Complete the LS Bank item using valid values.")
        actor = require_member_identity()
        get_db().execute(
            """INSERT INTO ls_bank_items(event_id,item,quantity,acquisition_kind,status,purchase_gil,sale_gil,holder_member_id,purchaser_member_id,notes,recorded_by)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (event["id"] if event else None, item, quantity, acquisition_kind, status, purchase_gil, sale_gil,
             holder["id"] if holder else None, purchaser["id"] if purchaser else None, notes, actor["id"]),
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "LS Bank", "Item recorded", f"{quantity}x {item} / {acquisition_kind}"),
        )
        get_db().commit()
        return bank_saved_response(f"Added {quantity}x {item} to the LS Bank.")

    @app.post("/endgame/bank/gil-transfer")
    @admin_required
    def record_ls_gil_transfer():
        from_id = request.form.get("from_member_id", "").strip()
        to_id = request.form.get("to_member_id", "").strip()
        notes = request.form.get("notes", "").strip()[:500]
        try:
            amount_gil = int(request.form.get("amount_gil", "0"))
        except (TypeError, ValueError):
            amount_gil = 0
        sender = get_db().execute(
            "SELECT id,name FROM members WHERE id=?", (from_id,)
        ).fetchone() if from_id.isdigit() else None
        recipient = get_db().execute(
            "SELECT id,name FROM members WHERE id=?", (to_id,)
        ).fetchone() if to_id.isdigit() else None
        actor = require_member_identity()
        officer_ids = {row["id"] for row in get_db().execute(
            "SELECT id FROM members WHERE discord_admin=1 OR name COLLATE NOCASE IN ({})".format(
                ",".join("?" for _ in DISCORD_ADMIN_CHARACTERS)
            ), DISCORD_ADMIN_CHARACTERS,
        ).fetchall()}
        officer_ids.add(actor["id"])
        if (not sender or not recipient or sender["id"] == recipient["id"]
                or sender["id"] not in officer_ids or recipient["id"] not in officer_ids
                or not 1 <= amount_gil <= 2_000_000_000):
            abort(400, description="Choose two different officers and enter a valid gil amount.")
        get_db().execute(
            """INSERT INTO ls_gil_transfers
               (from_member_id,to_member_id,amount_gil,notes,recorded_by)
               VALUES(?,?,?,?,?)""",
            (sender["id"], recipient["id"], amount_gil, notes, actor["id"]),
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "LS Bank", "Gil transferred",
             f"{amount_gil:,}g / {sender['name']} to {recipient['name']}"),
        )
        get_db().commit()
        flash(f"Recorded {amount_gil:,}g transfer from {sender['name']} to {recipient['name']}.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="bank"))

    @app.post("/endgame/bank/gil-transfer/<int:transfer_id>/update")
    @admin_required
    def update_ls_gil_transfer(transfer_id):
        transfer = get_db().execute(
            "SELECT * FROM ls_gil_transfers WHERE id=?", (transfer_id,)
        ).fetchone()
        if not transfer:
            abort(404)
        from_id = request.form.get("from_member_id", "").strip()
        to_id = request.form.get("to_member_id", "").strip()
        notes = request.form.get("notes", "").strip()[:500]
        try:
            amount_gil = int(request.form.get("amount_gil", "0"))
        except (TypeError, ValueError):
            amount_gil = 0
        sender = get_db().execute("SELECT id,name FROM members WHERE id=?", (from_id,)).fetchone() if from_id.isdigit() else None
        recipient = get_db().execute("SELECT id,name FROM members WHERE id=?", (to_id,)).fetchone() if to_id.isdigit() else None
        officer_ids = ls_bank_officer_ids()
        if (not sender or not recipient or sender["id"] == recipient["id"]
                or sender["id"] not in officer_ids or recipient["id"] not in officer_ids
                or not 1 <= amount_gil <= 2_000_000_000):
            abort(400, description="Choose two different officers and enter a valid gil amount.")
        actor = require_member_identity()
        get_db().execute(
            """UPDATE ls_gil_transfers SET from_member_id=?,to_member_id=?,amount_gil=?,notes=?
               WHERE id=?""",
            (sender["id"], recipient["id"], amount_gil, notes, transfer_id),
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "LS Bank", "Gil transfer updated",
             f"Transfer #{transfer_id}: {amount_gil:,}g / {sender['name']} to {recipient['name']}"),
        )
        get_db().commit()
        flash("Gil transfer updated.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="bank"))

    @app.post("/endgame/bank/gil-transfer/<int:transfer_id>/delete")
    @admin_required
    def delete_ls_gil_transfer(transfer_id):
        transfer = get_db().execute(
            """SELECT t.*,sender.name from_name,recipient.name to_name
               FROM ls_gil_transfers t
               JOIN members sender ON sender.id=t.from_member_id
               JOIN members recipient ON recipient.id=t.to_member_id WHERE t.id=?""",
            (transfer_id,),
        ).fetchone()
        if not transfer:
            abort(404)
        actor = require_member_identity()
        get_db().execute("DELETE FROM ls_gil_transfers WHERE id=?", (transfer_id,))
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "LS Bank", "Gil transfer removed",
             f"Transfer #{transfer_id}: {transfer['amount_gil']:,}g / {transfer['from_name']} to {transfer['to_name']}"),
        )
        get_db().commit()
        flash("Gil transfer removed.", "success")
        return redirect(url_for("endgame_dashboard", _anchor="bank"))

    @app.post("/endgame/bank/<int:bank_item_id>/update")
    @admin_required
    def update_ls_bank_item(bank_item_id):
        entry = get_db().execute("SELECT * FROM ls_bank_items WHERE id=?", (bank_item_id,)).fetchone()
        if not entry:
            abort(404)
        holder_id = request.form.get("holder_member_id", "").strip()
        purchaser_id = request.form.get("purchaser_member_id", "").strip()
        status = request.form.get("status", "").strip()
        acquisition_kind = request.form.get("acquisition_kind", entry["acquisition_kind"]).strip()
        event_id = request.form.get("event_id", "").strip()
        raw_purchase_gil = request.form.get("purchase_gil")
        purchase_gil = entry["purchase_gil"] if raw_purchase_gil is None else bank_gil_value(raw_purchase_gil)
        if "timeless" in entry["item"].casefold() and ("hourglass" in entry["item"].casefold() or "hrglass" in entry["item"].casefold()):
            acquisition_kind, event_id = "Other", ""
        acquisition_kind = {
            "Purchase": "Auction House", "Pop Item": "Other",
            "Timeless Hourglass": "Other", "Manual": "Other", "Merc Sell": "Mercenary",
        }.get(acquisition_kind, acquisition_kind)
        if acquisition_kind == "Event Drop":
            purchase_gil, purchaser_id = 0, ""
        elif not purchaser_id:
            purchaser_id = holder_id
        raw_sale_gil = request.form.get("sale_gil")
        sale_gil = (entry["sale_gil"] if status == "Sold" and not str(raw_sale_gil or "").strip()
                    else (0 if not str(raw_sale_gil or "").strip() else bank_gil_value(raw_sale_gil)))
        sale_channel = request.form.get("sale_channel", entry["sale_channel"]).strip()
        submitted_notes = request.form.get("notes")
        notes = entry["notes"] if not (submitted_notes or "").strip() else submitted_notes.strip()[:500]
        holder = get_db().execute("SELECT id,name FROM members WHERE id=?", (holder_id,)).fetchone() if holder_id.isdigit() else None
        purchaser = get_db().execute("SELECT id,name FROM members WHERE id=?", (purchaser_id,)).fetchone() if purchaser_id.isdigit() else None
        event = get_db().execute("SELECT id FROM guild_events WHERE id=?", (event_id,)).fetchone() if event_id.isdigit() else None
        if acquisition_kind == "Mercenary":
            status, sale_gil, purchase_gil = "Sold", purchase_gil, 0
        if (status not in {"Held", "Purchased", "Sold"} or sale_gil < 0 or purchase_gil < 0 or (holder_id and not holder) or (purchaser_id and not purchaser)
                or acquisition_kind not in {"Event Drop", "Auction House", "Bazaar", "Donation", "Other", "Mercenary", "Purchase", "Pop Item", "Timeless Hourglass", "Merc Sell", "Manual"}
                or (acquisition_kind == "Mercenary" and sale_gil <= 0)
                or (event_id and not event)
                or (status == "Sold" and sale_channel not in {"", "Auction House", "Bazaar"})
                or (status != "Sold" and sale_channel)
                or (acquisition_kind == "Donation" and (not purchaser or not holder))
                or (acquisition_kind not in {"Event Drop", "Donation"}
                    and (not purchaser or purchaser["id"] not in ls_bank_officer_ids()))):
            abort(400, description="Use a valid holder, sale status, and gil amount.")
        actor = require_member_identity()
        sale_gil = sale_gil if status == "Sold" else 0
        get_db().execute(
            """UPDATE ls_bank_items SET event_id=?,acquisition_kind=?,purchase_gil=?,holder_member_id=?,purchaser_member_id=?,status=?,sale_gil=?,sale_channel=?,notes=?,
                       sold_at=CASE WHEN ?='Sold' THEN COALESCE(sold_at,CURRENT_TIMESTAMP) ELSE NULL END,
                       updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (event["id"] if event else None, acquisition_kind, purchase_gil, holder["id"] if holder else None, purchaser["id"] if purchaser else None,
             status, sale_gil, sale_channel, notes, status, bank_item_id),
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "LS Bank", "Item updated", f"{entry['quantity']}x {entry['item']} / {status}"),
        )
        get_db().commit()
        return bank_saved_response("LS Bank item updated.", status=status, sale_gil=sale_gil,
                                   purchase_gil=purchase_gil, source=acquisition_kind)

    @app.post("/endgame/bank/<int:bank_item_id>/use")
    @admin_required
    def use_ls_bank_item(bank_item_id):
        entry = get_db().execute("SELECT * FROM ls_bank_items WHERE id=?", (bank_item_id,)).fetchone()
        used_event_id = request.form.get("used_event_id", "").strip()
        event = get_db().execute("SELECT id,name FROM guild_events WHERE id=?", (used_event_id,)).fetchone() if used_event_id.isdigit() else None
        if not entry or entry["status"] not in {"Held", "Purchased"} or (used_event_id not in {"other", ""} and not event):
            abort(400, description="Choose a valid event or Other before using an LS Bank item.")
        use_note = f"Used: {event['name'] if event else 'Other'}"
        notes = f"{entry['notes']} · {use_note}".strip(" ·")[:500]
        actor = require_member_identity()
        get_db().execute(
            "UPDATE ls_bank_items SET status='Purchased',used_event_id=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (event["id"] if event else None, notes, bank_item_id),
        )
        get_db().execute("INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
                         (actor["id"], "LS Bank", "Item used", f"{entry['quantity']}x {entry['item']} / {use_note}"))
        get_db().commit()
        return bank_saved_response(f"Marked {entry['item']} as used for {event['name'] if event else 'Other'}.", status="Used")

    @app.post("/endgame/bank/<int:bank_item_id>/reopen")
    @admin_required
    def reopen_ls_bank_item(bank_item_id):
        entry = get_db().execute("SELECT * FROM ls_bank_items WHERE id=?", (bank_item_id,)).fetchone()
        if not entry or entry["status"] != "Sold":
            abort(400, description="Only sold LS Bank items can be returned to held inventory.")
        actor = require_member_identity()
        get_db().execute(
            """UPDATE ls_bank_items SET status='Held',sale_gil=0,sale_channel='',sold_at=NULL,
                       updated_at=CURRENT_TIMESTAMP WHERE id=?""", (bank_item_id,)
        )
        get_db().execute("INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
                         (actor["id"], "LS Bank", "Sale reopened", f"{entry['quantity']}x {entry['item']}"))
        get_db().commit()
        return bank_saved_response(f"Returned {entry['item']} to held inventory and cleared its sale value.", status="Held")

    @app.post("/endgame/bank/bulk-update")
    @admin_required
    def bulk_update_ls_bank_items():
        ids = request.form.getlist("entry_id")
        holders = request.form.getlist("holder_member_id")
        purchasers = request.form.getlist("purchaser_member_id")
        if not purchasers:
            purchasers = list(holders)
        statuses = request.form.getlist("status")
        sales = request.form.getlist("sale_gil")
        sources = request.form.getlist("acquisition_kind")
        events = request.form.getlist("event_id")
        purchases = request.form.getlist("purchase_gil")
        notes_list = request.form.getlist("notes")
        if not ids or not (len(ids) == len(holders) == len(purchasers) == len(statuses) == len(sales) == len(sources) == len(events) == len(purchases) == len(notes_list)):
            abort(400, description="The LS Bank rows could not be saved together.")
        updates = []
        for entry_id, holder_id, purchaser_id, status, raw_sale_gil, acquisition_kind, event_id, raw_purchase_gil, notes in zip(ids, holders, purchasers, statuses, sales, sources, events, purchases, notes_list):
            if not entry_id.isdigit():
                abort(400, description="The LS Bank row is invalid.")
            entry = get_db().execute("SELECT id,item,quantity,sale_gil FROM ls_bank_items WHERE id=?", (entry_id,)).fetchone()
            holder = get_db().execute("SELECT id FROM members WHERE id=?", (holder_id,)).fetchone() if holder_id.isdigit() else None
            purchaser_id = purchaser_id or holder_id
            purchaser = get_db().execute("SELECT id FROM members WHERE id=?", (purchaser_id,)).fetchone() if purchaser_id.isdigit() else None
            event = get_db().execute("SELECT id FROM guild_events WHERE id=?", (event_id,)).fetchone() if event_id.isdigit() else None
            sale_gil = entry["sale_gil"] if entry and status == "Sold" and not str(raw_sale_gil).strip() else (0 if not str(raw_sale_gil).strip() else bank_gil_value(raw_sale_gil))
            purchase_gil = bank_gil_value(raw_purchase_gil)
            if "timeless" in entry["item"].casefold() and ("hourglass" in entry["item"].casefold() or "hrglass" in entry["item"].casefold()):
                acquisition_kind, event_id = "Other", ""
            acquisition_kind = {
                "Purchase": "Auction House", "Pop Item": "Other",
                "Timeless Hourglass": "Other", "Manual": "Other", "Merc Sell": "Mercenary",
            }.get(acquisition_kind, acquisition_kind)
            if acquisition_kind == "Event Drop":
                purchase_gil, purchaser_id = 0, ""
                purchaser = None
            # A filled sale price is the quick bulk-sale action; a blank field
            # leaves the selected state intact.
            if status in {"Held", "Purchased"} and str(raw_sale_gil).strip() and sale_gil > 0:
                status = "Sold"
            if acquisition_kind == "Mercenary":
                status, sale_gil, purchase_gil = "Sold", purchase_gil, 0
            if (not entry or sale_gil < 0 or purchase_gil < 0 or status not in {"Held", "Purchased", "Sold"}
                    or acquisition_kind not in {"Event Drop", "Auction House", "Bazaar", "Donation", "Other", "Mercenary", "Purchase", "Pop Item", "Timeless Hourglass", "Merc Sell", "Manual"}
                    or (acquisition_kind == "Mercenary" and sale_gil <= 0)
                    or (event_id and not event) or (holder_id and not holder) or (purchaser_id and not purchaser)
                    or (acquisition_kind == "Donation" and (not purchaser or not holder))
                    or (acquisition_kind not in {"Event Drop", "Donation"}
                        and (not purchaser or purchaser["id"] not in ls_bank_officer_ids()))):
                abort(400, description="Use valid LS Bank values before saving all rows.")
            updates.append((event["id"] if event else None, acquisition_kind, purchase_gil, holder["id"] if holder else None, purchaser["id"] if purchaser else None, status, sale_gil if status == "Sold" else 0,
                            notes.strip()[:500], status, entry["id"], entry["item"], entry["quantity"]))
        actor = require_member_identity()
        for event_id, acquisition_kind, purchase_gil, holder_id, purchaser_id, status, sale_gil, notes, sold_status, entry_id, item, quantity in updates:
            get_db().execute(
                """UPDATE ls_bank_items SET event_id=?,acquisition_kind=?,purchase_gil=?,holder_member_id=?,purchaser_member_id=?,status=?,sale_gil=?,sale_channel='',notes=?,
                           sold_at=CASE WHEN ?='Sold' THEN COALESCE(sold_at,CURRENT_TIMESTAMP) ELSE NULL END,
                           updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (event_id, acquisition_kind, purchase_gil, holder_id, purchaser_id, status, sale_gil, notes, sold_status, entry_id),
            )
            get_db().execute(
                "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
                (actor["id"], "LS Bank", "Item updated", f"{quantity}x {item} / {status}"),
            )
        get_db().commit()
        return bank_saved_response(f"Saved {len(updates)} LS Bank entries.", count=len(updates))

    @app.post("/endgame/bank/<int:bank_item_id>/delete")
    @admin_required
    def delete_ls_bank_item(bank_item_id):
        entry = get_db().execute("SELECT * FROM ls_bank_items WHERE id=?", (bank_item_id,)).fetchone()
        if not entry:
            abort(404)
        actor = require_member_identity()
        get_db().execute("DELETE FROM ls_bank_items WHERE id=?", (bank_item_id,))
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "LS Bank", "Item removed", f"{entry['quantity']}x {entry['item']}"),
        )
        get_db().commit()
        return bank_saved_response("Removed the LS Bank entry.", deleted=True)

    @app.get("/endgame/bank/purchasers")
    @admin_required
    def ls_bank_purchasers():
        rows = get_db().execute(
            "SELECT id,purchaser_member_id FROM ls_bank_items"
        ).fetchall()
        return jsonify({"purchasers": {str(row["id"]): row["purchaser_member_id"] for row in rows}})

    @app.post("/endgame/loot/<int:award_id>/update")
    @admin_required
    def update_endgame_loot(award_id):
        if not can_create_guild_events():
            abort(403, description="Only designated administrators can edit loot.")
        award = get_db().execute(
            "SELECT * FROM endgame_loot_awards WHERE id=?", (award_id,)
        ).fetchone()
        if not award:
            abort(404)
        member_id = request.form.get("member_id", "")
        recipient = get_db().execute(
            "SELECT id,name FROM members WHERE id=?", (member_id,)
        ).fetchone() if member_id.isdigit() else None
        item = request.form.get("item", "").strip()[:120]
        job = request.form.get("job", "").strip().upper()
        family = manual_loot_family(item) or request.form.get("family", "").strip()
        distribution = request.form.get("distribution", "").strip()
        classification = request.form.get("classification", "").strip()
        try:
            requested_cost = float(request.form.get("dkp_cost", str(award["dkp_cost"])) or 0)
            dkp_cost = int(requested_cost) if requested_cost.is_integer() else -1
        except ValueError:
            dkp_cost = -1
        if (not recipient or not item or job not in JOBS or family not in
                {"Weapons", "Head", "Body", "Hands", "Legs", "Feet", "Accessories", "Other"}
                or distribution not in {"P1", "P2", "P3", "Freelot"}
                or classification not in {"Major Loot", "Standard"} or not 0 <= dkp_cost <= 999):
            abort(400, description="Complete the loot award using valid selections.")
        editor = require_member_identity()
        get_db().execute(
            """UPDATE endgame_loot_awards SET recipient_member_id=?,item=?,job=?,family=?,
                       distribution=?,classification=?,dkp_cost=?,recorded_by=? WHERE id=?""",
            (recipient["id"], item, job, family, distribution, classification, dkp_cost, editor["id"], award_id),
        )
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (editor["id"], "Event Loot", "Award updated", f"Award #{award_id}: {item} to {recipient['name']}"),
        )
        get_db().commit()
        flash("Loot award updated.", "success")
        return_to = request.form.get("return_to")
        anchor = "loot" if return_to == "loot" else "bidding-live" if return_to == "bidding" else "events"
        return redirect(url_for("endgame_dashboard", _anchor=anchor))

    @app.post("/endgame/loot/<int:award_id>/delete")
    @admin_required
    def delete_endgame_loot(award_id):
        if not can_create_guild_events():
            abort(403, description="Only designated administrators can remove loot.")
        award = get_db().execute(
            """SELECT l.item,l.dkp_cost,m.name FROM endgame_loot_awards l
               JOIN members m ON m.id=l.recipient_member_id WHERE l.id=?""", (award_id,)
        ).fetchone()
        if not award:
            abort(404)
        editor = require_member_identity()
        get_db().execute("DELETE FROM endgame_loot_awards WHERE id=?", (award_id,))
        get_db().execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (editor["id"], "Event Loot", "Award removed", f"Award #{award_id}: {award['item']}"),
        )
        get_db().commit()
        flash(f"Removed {award['item']} and restored {int(round(award['dkp_cost']))} DKP to {award['name']}.", "success")
        return_to = request.form.get("return_to")
        anchor = "loot" if return_to == "loot" else "bidding-live" if return_to == "bidding" else "events"
        return redirect(url_for("endgame_dashboard", _anchor=anchor))

    @app.get("/api/job-roster/members")
    def job_roster_members_api():
        """Return registered character names for the external refresh worker."""
        names = [row["name"] for row in get_db().execute(
            "SELECT name FROM members ORDER BY name COLLATE NOCASE"
        ).fetchall()]
        response = jsonify({"members": names})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/job-roster/refresh")
    def refresh_job_roster_api():
        """Apply validated HorizonXI job results from the scheduled GitHub worker."""
        expected = app.config.get("ROSTER_REFRESH_TOKEN", "")
        supplied = request.headers.get("Authorization", "")
        if not expected:
            return jsonify({"error": "Roster refresh is not configured."}), 503
        if not supplied.startswith("Bearer ") or not hmac.compare_digest(
                supplied.removeprefix("Bearer "), expected):
            return jsonify({"error": "Unauthorized."}), 401
        if request.content_length and request.content_length > 256 * 1024:
            return jsonify({"error": "Refresh payload is too large."}), 413

        payload = request.get_json(silent=True)
        players = payload.get("players") if isinstance(payload, dict) else None
        if not isinstance(players, dict) or len(players) > 250:
            return jsonify({"error": "Expected a players object."}), 400

        db = get_db()
        registered = {
            row["name"].casefold(): (row["id"], row["name"])
            for row in db.execute("SELECT id, name FROM members").fetchall()
        }
        updates = []
        skipped = []
        for submitted_name, submitted_jobs in players.items():
            member = registered.get(str(submitted_name).casefold())
            if not member or not isinstance(submitted_jobs, dict):
                skipped.append(str(submitted_name))
                continue
            jobs = {}
            invalid = False
            for job, level in submitted_jobs.items():
                if (job not in JOBS or isinstance(level, bool)
                        or not isinstance(level, (int, float))
                        or int(level) != level or not 1 <= int(level) <= 75):
                    invalid = True
                    break
                jobs[job] = int(level)
            if invalid or not jobs:
                skipped.append(member[1])
                continue
            updates.append((member[0], member[1], jobs))

        try:
            for member_id, _name, jobs in updates:
                existing_bring_jobs = {
                    row["job"]: row["bring"] for row in db.execute(
                        "SELECT job,bring FROM member_jobs WHERE member_id=?", (member_id,)
                    ).fetchall()
                }
                db.execute("DELETE FROM member_jobs WHERE member_id=?", (member_id,))
                db.executemany(
                    "INSERT INTO member_jobs(member_id,job,level,bring) VALUES (?,?,?,?)",
                    [(member_id, job, level, existing_bring_jobs.get(job, 1))
                     for job, level in jobs.items()],
                )
                db.execute(
                    "UPDATE members SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (member_id,)
                )
            db.commit()
        except sqlite3.DatabaseError:
            db.rollback()
            raise
        return jsonify({
            "updated": len(updates),
            "updated_members": [name for _member_id, name, _jobs in updates],
            "skipped": skipped,
        })

    @app.get("/loot-tables")
    def loot_tables():
        mode = request.args.get("mode", "general")
        if mode not in {"general", "dynamis", "limbus"}:
            mode = "general"
        view = request.args.get("view", "area")
        if view not in {"area", "job"}:
            view = "area"
        db = get_db()
        members = db.execute("SELECT id,name FROM members ORDER BY name COLLATE NOCASE").fetchall()
        target_id = current_member_id()
        if is_admin() and request.args.get("member_id", "").isdigit():
            target_id = int(request.args["member_id"])
        target = db.execute("SELECT id,name FROM members WHERE id=?", (target_id,)).fetchone() if target_id else None
        owned = {
            row["item_key"] for row in db.execute(
                "SELECT item_key FROM loot_ownership WHERE member_id=?", (target_id,)
            ).fetchall()
        } if target else set()
        dynamis_by_area = {}
        dynamis_by_job = {job: [] for job in sorted(DYNAMIS_RELIC)}
        job_keys = set()
        for piece in dynamis_catalog():
            dynamis_by_area.setdefault(piece["area"], []).append(piece)
            if piece["key"] not in job_keys:
                dynamis_by_job[piece["job"]].append(dict(piece))
                job_keys.add(piece["key"])
            elif piece["kind"] == "Relic accessory":
                tracked = next(row for row in dynamis_by_job[piece["job"]]
                               if row["key"] == piece["key"])
                tracked["area"] += f" / {piece['area'].replace('Dynamis - ', '')}"
        area_order = ("Dynamis - San d'Oria", "Dynamis - Bastok", "Dynamis - Windurst",
                      "Dynamis - Jeuno", "Dynamis - Beaucedine", "Dynamis - Xarcabard",
                      "Dynamis - Valkurm", "Dynamis - Buburimu", "Dynamis - Qufim",
                      "Dynamis - Tavnazia")
        dynamis_by_area = {
            area: sorted(dynamis_by_area.get(area, []), key=lambda piece: (piece["job"], piece["kind"], piece["slot"]))
            for area in area_order
        }
        catalog_by_key = {piece["key"]: piece for piece in dynamis_catalog()}
        dynamis_job_rows = {}
        for job in sorted(DYNAMIS_RELIC):
            rows = []
            for _item, slot, _area in DYNAMIS_RELIC[job]:
                rows.append({"main": catalog_by_key[f"dynamis:{job}:{slot.lower()}"],
                             "minus": catalog_by_key[f"dynamis:dream:{job}:{slot.lower()}"]})
            accessory = next(piece for piece in dynamis_by_job[job]
                             if piece["kind"] == "Relic accessory")
            dynamis_job_rows[job] = {"armor": rows, "accessory": accessory,
                                      "color": JOB_COLORS[job]}
        limbus_groups = {
            boss: [{"key": f"limbus:{boss.lower()}:{slot.lower()}", "component": component,
                    "item": item, "slot": slot} for component, item, slot in pieces]
            for boss, pieces in LIMBUS_LOOT.items()
        }
        limbus_af1 = []
        for job, group in sorted(LIMBUS_AF1.items()):
            materials = []
            for zone in ("apollyon", "temenos"):
                item, floors = group[zone]
                materials.append({"key": f"limbus:af1:{job}:{zone}", "zone": zone.title(),
                                  "item": item, "floors": floors})
            pieces = [
                {"key": f"limbus:af1:{job}:{slot.lower()}", "slot": slot, "item": item}
                for slot, item in zip(AF1_SLOTS, group["pieces"])
            ]
            limbus_af1.append({"job": job, "color": JOB_COLORS[job],
                               "materials": materials, "pieces": pieces})
        return render_template(
            "loot_tables.html", mode=mode, tracker_view=view, members=members,
            target_member=target, owned=owned, dynamis_relic=DYNAMIS_RELIC,
            dynamis_by_job=dynamis_by_job,
            dynamis_job_rows=dynamis_job_rows, job_colors=JOB_COLORS,
            dynamis_by_area=dynamis_by_area, limbus_groups=limbus_groups,
            limbus_af1=limbus_af1,
        )

    @app.get("/api/market-prices")
    def market_prices_api():
        """Return a compact hourly cached HorizonXI AH snapshot."""
        force_refresh = request.args.get("refresh") == "1"
        if force_refresh and not is_admin():
            abort(403, description="Only officers can refresh market values.")
        try:
            snapshot = market_snapshot(
                app.config["PSXI_MARKET_CACHE"], app.config.get("PSXI_API_TOKEN", ""),
                force_refresh=True,
            ) if force_refresh else market_snapshot(
                app.config["PSXI_MARKET_CACHE"], app.config.get("PSXI_API_TOKEN", "")
            )
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            return jsonify({"error": "Market prices are temporarily unavailable."}), 503
        response = jsonify(snapshot)
        response.headers["Cache-Control"] = "public, max-age=300"
        return response

    @app.get("/gear-optimizer")
    @editor_required
    def gear_optimizer():
        member = require_member_identity()
        profile_jobs = member_jobs(member["id"])
        archived_gear = {
            str(row["item_id"]): row["quantity"]
            for row in get_db().execute(
                "SELECT item_id,quantity FROM gear_ownership WHERE member_id=?",
                (member["id"],),
            )
        }
        default_job = max(profile_jobs, key=profile_jobs.get) if profile_jobs else "WAR"
        return render_template(
            "gear_optimizer.html", member=member, jobs=GEAR_JOBS,
            gear_slots=GEAR_SLOTS, gear_stats=tuple(dict.fromkeys(GEAR_STAT_ALIASES.values())),
            default_job=default_job,
            default_race="",
            archived_gear=archived_gear,
        )

    @app.post("/api/gear/inventory")
    @editor_required
    def archive_gear_inventory():
        member = require_member_identity()
        try:
            submitted = json.loads(request.form.get("inventory", "{}"))
        except json.JSONDecodeError:
            abort(400, description="The imported inventory is not valid.")
        if not isinstance(submitted, dict) or len(submitted) > 7000:
            abort(400, description="The imported inventory is too large.")
        catalog_path = Path(app.root_path) / "static" / "gear_catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["rows"]
        by_id = {str(item["item_id"]): item for item in catalog}
        rows = []
        for item_id, raw_quantity in submitted.items():
            item = by_id.get(str(item_id))
            if not item or isinstance(raw_quantity, bool):
                continue
            try:
                quantity = int(raw_quantity)
            except (TypeError, ValueError):
                continue
            if not 1 <= quantity <= 9999:
                continue
            rows.append((
                member["id"], item["item_id"], item.get("item_key", ""), item["name"],
                "/".join(item.get("slots", [])), item.get("description", ""),
                "/".join(item.get("jobs", [])), item.get("level", 0), quantity,
            ))
        db = get_db()
        db.execute("DELETE FROM gear_ownership WHERE member_id=?", (member["id"],))
        db.executemany(
            """INSERT INTO gear_ownership
               (member_id,item_id,item_key,name,slot,description,jobs,level,quantity)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        db.commit()
        return jsonify(saved=len(rows), quantity=sum(row[-1] for row in rows))

    @app.get("/api/gear/items")
    @editor_required
    def gear_item_search():
        query = request.args.get("q", "").strip()
        if len(query) < 2 or len(query) > 60:
            return jsonify({"items": []})
        try:
            matches = horizon_json(f"items?{urlencode({'search': query, 'limit': 12})}").get("items", [])
            items = []
            for match in matches[:10]:
                key = match.get("key", "")
                if not key:
                    continue
                try:
                    detail = horizon_json(f"items/{quote(key)}", timeout=10)
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                    continue
                item = normalize_horizon_item(match["id"], detail, key=key)
                if item["slot"]:
                    items.append(item)
            return jsonify({"items": items})
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return jsonify({"error": "HorizonXI item search is temporarily unavailable."}), 502

    @app.post("/gear-optimizer/owned")
    @editor_required
    def add_owned_gear():
        member = require_member_identity()
        item_key = request.form.get("item_key", "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_+?'.-]{1,100}", item_key):
            abort(400, description="Choose a valid HorizonXI item.")
        try:
            detail = horizon_json(f"items/{quote(item_key)}")
            item_id = detail.get("id")
            item = normalize_horizon_item(item_id, detail, key=item_key)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, TypeError, ValueError):
            abort(502, description="HorizonXI could not verify that item.")
        if not item["slot"]:
            abort(400, description="Choose an equippable item.")
        get_db().execute(
            """INSERT INTO gear_ownership
               (member_id,item_id,item_key,name,slot,description,jobs,level)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(member_id,item_id) DO UPDATE SET
               item_key=excluded.item_key,name=excluded.name,slot=excluded.slot,
               description=excluded.description,jobs=excluded.jobs,level=excluded.level""",
            (member["id"], item["item_id"], item["item_key"], item["name"],
             item["slot"], item["description"], item["jobs"], item["level"]),
        )
        get_db().commit()
        flash(f"Added {item['name']} to {member['name']}'s owned gear.", "success")
        return redirect(url_for("gear_optimizer"))

    @app.post("/gear-optimizer/owned/<int:item_id>/delete")
    @editor_required
    def delete_owned_gear(item_id):
        member = require_member_identity()
        get_db().execute(
            "DELETE FROM gear_ownership WHERE member_id=? AND item_id=?",
            (member["id"], item_id),
        )
        get_db().commit()
        flash("Removed the item from your owned gear.", "success")
        return redirect(url_for("gear_optimizer"))

    @app.get("/spell-farming")
    @editor_required
    def spell_farming():
        member = require_member_identity()
        view = request.args.get("view", "farming")
        if view not in {"farming", "spellbook"}:
            view = "farming"
        learned = [row["spell"] for row in get_db().execute(
            "SELECT spell FROM blue_spell_ownership WHERE member_id=?",
            (member["id"],),
        )]
        db = get_db()
        templates = db.execute(
            """SELECT t.*,m.name owner_name FROM blue_spell_templates t
               JOIN members m ON m.id=t.owner_member_id
               WHERE t.owner_member_id=?
               ORDER BY t.updated_at DESC,t.name COLLATE NOCASE""",
            (member["id"],),
        ).fetchall()
        selected_template = None
        if request.args.get("template", "").isdigit():
            template_id = int(request.args["template"])
            selected_template = next((row for row in templates if row["id"] == template_id), None)
        return render_template(
            "spell_farming.html", learned_spells=learned, member=member, view=view,
            spell_templates=templates, selected_template=selected_template,
            selected_template_spells=(json.loads(selected_template["spells_json"])
                                      if selected_template else []),
        )

    @app.get("/skillchain-calculator")
    @editor_required
    def skillchain_calculator():
        return render_template("skillchain_calculator.html")

    @app.post("/spell-farming/ownership")
    @editor_required
    def update_spell_ownership():
        member = require_member_identity()
        data_path = Path(app.root_path) / "static" / "blue_spell_farming.json"
        with data_path.open(encoding="utf-8") as spell_file:
            valid_spells = {row["spell"] for row in json.load(spell_file)["rows"]}
        selected = {spell.strip() for spell in request.form.getlist("spells")}
        if not selected.issubset(valid_spells):
            abort(400, description="Choose valid Blue Magic spells.")
        db = get_db()
        try:
            db.execute("DELETE FROM blue_spell_ownership WHERE member_id=?", (member["id"],))
            db.executemany(
                "INSERT INTO blue_spell_ownership(member_id,spell) VALUES(?,?)",
                [(member["id"], spell) for spell in sorted(selected)],
            )
            db.commit()
        except sqlite3.DatabaseError:
            db.rollback()
            raise
        flash(f"Saved {len(selected)} learned Blue Magic spells for {member['name']}.", "success")
        return redirect(url_for("spell_farming"))

    @app.post("/blue-mage-tools/templates")
    @editor_required
    def save_blue_spell_template():
        member = require_member_identity()
        name = " ".join(request.form.get("name", "").split())[:60]
        if not name:
            abort(400, description="Give the spell template a name.")
        try:
            blue_level = int(request.form.get("blue_level", "75"))
        except ValueError:
            abort(400, description="Choose a valid Blue Mage level.")
        if not 1 <= blue_level <= 75:
            abort(400, description="Blue Mage level must be between 1 and 75.")
        data_path = Path(app.root_path) / "static" / "blue_spell_farming.json"
        with data_path.open(encoding="utf-8") as spell_file:
            rows = json.load(spell_file)["rows"]
        spell_levels = {row["spell"]: row["spell_level"] for row in rows}
        spell_costs = {row["spell"]: int(row.get("set_points") or 0) for row in rows}
        spells = list(dict.fromkeys(request.form.getlist("spells")))
        if any(spell not in spell_levels or spell_levels[spell] > blue_level for spell in spells):
            abort(400, description="The template contains a spell unavailable at that level.")
        point_limit = 10 + ((blue_level - 1) // 10) * 5
        slot_limit = min(20, 6 + ((blue_level - 1) // 10) * 2)
        if len(spells) > slot_limit or sum(spell_costs[spell] for spell in spells) > point_limit:
            abort(400, description="The template exceeds the spell-slot or Blue Magic point limit.")
        template_id = request.form.get("template_id", "")
        db = get_db()
        if template_id.isdigit():
            existing = db.execute(
                "SELECT id FROM blue_spell_templates WHERE id=? AND owner_member_id=?",
                (int(template_id), member["id"]),
            ).fetchone()
        else:
            existing = None
        values = (name, blue_level, json.dumps(spells), 0)
        if existing:
            db.execute(
                """UPDATE blue_spell_templates SET name=?,blue_level=?,spells_json=?,is_shared=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (*values, existing["id"]),
            )
            saved_id = existing["id"]
        else:
            cursor = db.execute(
                """INSERT INTO blue_spell_templates
                   (owner_member_id,name,blue_level,spells_json,is_shared)
                   VALUES (?,?,?,?,?)""",
                (member["id"], *values),
            )
            saved_id = cursor.lastrowid
        db.commit()
        flash(f"Saved Blue Mage template {name}.", "success")
        return redirect(url_for("spell_farming", view="spellbook", template=saved_id))

    @app.post("/blue-mage-tools/templates/<int:template_id>/delete")
    @editor_required
    def delete_blue_spell_template(template_id):
        member = require_member_identity()
        cursor = get_db().execute(
            "DELETE FROM blue_spell_templates WHERE id=? AND owner_member_id=?",
            (template_id, member["id"]),
        )
        get_db().commit()
        if not cursor.rowcount:
            abort(404)
        flash("Deleted the Blue Mage spell template.", "success")
        return redirect(url_for("spell_farming", view="spellbook"))

    @app.post("/loot-tables/ownership")
    @editor_required
    def update_loot_ownership():
        catalog = request.form.get("catalog", "")
        if catalog not in {"dynamis", "limbus"}:
            abort(400, description="Choose a valid loot tracker.")
        target_id = current_member_id()
        if is_admin() and request.form.get("member_id", "").isdigit():
            target_id = int(request.form["member_id"])
        if not target_id:
            abort(403, description="Select your linkshell character before updating loot.")
        db = get_db()
        target = db.execute("SELECT id,name FROM members WHERE id=?", (target_id,)).fetchone()
        if not target or (not is_admin() and target_id != current_member_id()):
            abort(403, description="You can only update your own loot tracker.")
        valid = set()
        if catalog == "dynamis":
            valid = {piece["key"] for piece in dynamis_catalog()}
        else:
            valid = {f"limbus:{boss.lower()}:{slot.lower()}" for boss, pieces in LIMBUS_LOOT.items()
                     for _component, _item, slot in pieces}
            valid.update(
                f"limbus:af1:{job}:{part}"
                for job in LIMBUS_AF1
                for part in ("apollyon", "temenos", "head", "body", "hands", "legs", "feet")
            )
        selected = set(request.form.getlist("owned")) & valid
        db.execute("DELETE FROM loot_ownership WHERE member_id=? AND item_key LIKE ?",
                   (target_id, f"{catalog}:%"))
        db.executemany("INSERT INTO loot_ownership(member_id,item_key) VALUES (?,?)",
                       [(target_id, key) for key in sorted(selected)])
        db.commit()
        flash(f"Updated {target['name']}'s {catalog.title()} loot tracker.", "success")
        destination = url_for("loot_tables", mode=catalog, view=request.form.get("view", "area"))
        if is_admin():
            destination += f"&member_id={target_id}"
        return redirect(destination)

    @app.get("/api/map-assets")
    def map_assets():
        requested_zone = request.args.get("zone", "").strip().casefold()
        requested_mob = request.args.get("mob", "").strip().casefold()
        calibration_path = Path(app.root_path) / "static" / "map_calibrations.json"
        loot_path = Path(app.root_path) / "static" / "loot_tables.json"
        if requested_zone and calibration_path.exists() and loot_path.exists():
            calibrations = json.loads(calibration_path.read_text(encoding="utf-8"))
            zone_name = next((name for name in calibrations if name.casefold() == requested_zone), None)
            if zone_name:
                map_rows = [row for row in calibrations[zone_name] if row.get("image")]
                normalized = re.sub(r"[^a-z0-9]", "", requested_mob)
                normalized = re.sub(r"(?:war|mnk|whm|blm|rdm|thf|pld|drk|bst|brd|rng|sam|nin|drg|smn)$", "", normalized)
                loot = json.loads(loot_path.read_text(encoding="utf-8"))
                points = loot.get("spawns", {}).get(f"{zone_name}\t{normalized}", {}).get("p", [])
                markers = []
                for x, map_y, elevation in points:
                    for map_row in map_rows:
                        if any(box[0] <= x <= box[3] and box[1] <= map_y <= box[4]
                               and box[2] <= elevation <= box[5] for box in map_row["boxes"]):
                            markers.append({"map_id": map_row["id"],
                                            "left": round((x * map_row["mult"] + map_row["xoff"]) / 512 * 100, 3),
                                            "top": round((-map_y * map_row["mult"] + map_row["yoff"]) / 512 * 100, 3)})
                            break
                zone_id = loot.get("zone_ids", {}).get(zone_name) or MAP_ZONE_ID_OVERRIDES.get(zone_name)
                if not zone_id:
                    return jsonify({"maps": []})
                maps = [{"map_id": row["id"], "label": f"Map {row['id']}",
                         "url": url_for("calibrated_map_asset", zone_id=zone_id,
                                        filename=f"map_{row['id']:02d}.png")}
                        for row in map_rows]
                return jsonify({"maps": maps, "preferred_map": markers[0]["map_id"] if markers else maps[0]["map_id"],
                                "markers": markers})
        wiki_root = Path(app.root_path) / "map-dats" / "wiki-packs"
        slug = re.sub(r"[^a-z0-9]+", "_", requested_zone).strip("_")
        wiki_maps = []
        for image_path in wiki_root.rglob(f"{slug}*.png") if wiki_root.exists() else ():
            stem = image_path.stem
            match = re.fullmatch(rf"{re.escape(slug)}(?:_(\d+))?", stem)
            if not match:
                continue
            page = int(match.group(1) or 1)
            pack = image_path.parent.name
            wiki_maps.append({"map_id": page, "label": f"Map {page}",
                              "url": url_for("wiki_map_asset", pack=pack, filename=image_path.name)})
        if wiki_maps:
            map_key = (requested_zone, requested_mob)
            preferred = {("maze of shakhrami", "argus"): 2,
                         ("maze of shakhrami", "leech king"): 2,
                         ("sea serpent grotto", "charybdis"): 4,
                         ("the boyahda tree", "ancient goobbue"): 3}.get(map_key, 1)
            marker = {
                ("maze of shakhrami", "argus"): {"map_id": 2, "left": 66.35, "top": 51.25},
                ("maze of shakhrami", "leech king"): {"map_id": 2, "left": 66.35, "top": 51.25},
                ("sea serpent grotto", "charybdis"): {"map_id": 4, "left": 50, "top": 68.75},
                ("the boyahda tree", "ancient goobbue"): {"map_id": 3, "left": 43.75, "top": 56.25},
            }.get(map_key)
            return jsonify({"maps": sorted(wiki_maps, key=lambda row: row["map_id"]),
                            "preferred_map": preferred, "marker": marker})
        manifest_path = Path(app.root_path) / "map-dats" / "map_manifest.json"
        if not requested_zone or not manifest_path.exists():
            return jsonify({"maps": []})
        records = json.loads(manifest_path.read_text(encoding="utf-8"))
        maps = [{"map_id": row["map_id"],
                 "url": url_for("map_asset", zone_id=row["zone_id"], filename=Path(row["image"]).name)}
                for row in records
                if row.get("zone", "").casefold() == requested_zone and row.get("image")]
        return jsonify({"maps": sorted(maps, key=lambda row: row["map_id"])})

    @app.get("/travel-planner")
    @editor_required
    def travel_planner():
        return render_template("travel_planner.html")

    @app.get("/wiki-map-assets/<pack>/<path:filename>")
    def wiki_map_asset(pack, filename):
        if not re.fullmatch(r"remapster-wiki-pack-[12]-1024", pack):
            abort(404)
        directory = Path(app.root_path) / "map-dats" / "wiki-packs" / pack
        return send_from_directory(directory, filename, mimetype="image/png")

    @app.get("/calibrated-map-assets/<int:zone_id>/<path:filename>")
    def calibrated_map_asset(zone_id, filename):
        directory = Path(app.root_path) / "static" / "calibrated_maps" / str(zone_id)
        return send_from_directory(directory, filename, mimetype="image/png")

    @app.get("/map-assets/<int:zone_id>/<path:filename>")
    def map_asset(zone_id, filename):
        directory = Path(app.root_path) / "map-dats" / "extracted" / str(zone_id)
        return send_from_directory(directory, filename, mimetype="image/webp")

    def require_member_identity():
        member_id = current_member_id()
        if member_id is None and app.config.get("AUTH_DISABLED"):
            raw = request.form.get("requester_id") or request.form.get("member_id")
            member_id = int(raw) if raw and raw.isdigit() else None
        if member_id is None:
            abort(403, description="Select your linkshell character before continuing.")
        member = get_db().execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
        if not member:
            abort(403, description="Your selected character no longer exists.")
        return member

    def member_jobs(member_id):
        return {
            row["job"]: row["level"]
            for row in get_db().execute(
                "SELECT job, level FROM member_jobs WHERE member_id=? ORDER BY job", (member_id,)
            ).fetchall()
        }

    def help_request_or_404(request_id):
        row = get_db().execute(
            """SELECT h.*, m.name requester_name, m.discord_name
               FROM help_requests h JOIN members m ON m.id=h.requester_id WHERE h.id=?""",
            (request_id,),
        ).fetchone()
        if not row:
            abort(404)
        return row

    def can_manage(help_request):
        return bool(is_admin() or (
            is_editor() and current_member_id() == help_request["requester_id"]
        ))

    def expire_requests():
        now = datetime.now().isoformat(timespec="minutes")
        get_db().execute(
            """UPDATE help_requests SET status='Expired', updated_at=CURRENT_TIMESTAMP
               WHERE status IN ('Open','Forming','Full') AND expires_at IS NOT NULL AND expires_at < ?""",
            (now,),
        )
        get_db().commit()

    def validate_help_form(form):
        values = {key: form.get(key, "").strip() for key in (
            "title", "category", "zone", "description", "availability_mode",
            "start_at", "available_after", "end_at", "expires_at", "requirements", "notes",
        )}
        errors = []
        if not values["title"]:
            errors.append("Request title is required.")
        if values["category"] not in HELP_CATEGORIES:
            errors.append("Choose a valid category.")
        elif values["category"] in HELP_ZONES:
            valid_zones = {
                zone for zones in HELP_ZONES[values["category"]].values() for zone in zones
            }
            if values["zone"] not in valid_zones:
                errors.append("Choose a valid region and zone for this activity.")
        if values["availability_mode"] not in AVAILABILITY_MODES:
            errors.append("Choose a valid availability mode.")
        try:
            values["helpers_needed"] = int(form.get("helpers_needed", "1"))
            if not 1 <= values["helpers_needed"] <= 17:
                raise ValueError
        except ValueError:
            errors.append("Helpers needed must be from 1 to 17.")
            values["helpers_needed"] = 1
        raw_cap = form.get("level_cap", "").strip()
        try:
            values["level_cap"] = int(raw_cap) if raw_cap else None
            if values["level_cap"] is not None and not 1 <= values["level_cap"] <= 75:
                raise ValueError
        except ValueError:
            errors.append("Level cap must be from 1 to 75 or uncapped.")
            values["level_cap"] = None
        parsed = {key: parse_local_datetime(values[key]) for key in ("start_at", "end_at", "expires_at")}
        if values["availability_mode"] == "after" and not values["available_after"]:
            errors.append("Enter the time you are available after.")
        if values["availability_mode"] == "fixed" and not parsed["start_at"]:
            errors.append("Fixed requests require a start date and time.")
        if parsed["expires_at"] and parsed["expires_at"] <= datetime.now():
            errors.append("Expiration must be in the future.")
        return values, errors

    def requested_party(form):
        specs, errors = [], []
        for kind, field, allowed in (
            ("job", "requested_jobs", JOBS), ("role", "requested_party_roles", PARTY_ROLES),
        ):
            for name in set(form.getlist(field)):
                if name not in allowed:
                    errors.append("Choose only valid requested jobs or party roles.")
                    continue
                raw = form.get(f"requested_count_{kind}_{name}", "").strip()
                try:
                    quantity = int(raw) if raw else None
                    if quantity is not None and not 1 <= quantity <= 5:
                        raise ValueError
                except ValueError:
                    errors.append(f"Requested {name} count must be Any or from 1 to 5.")
                    continue
                specs.append((name, kind, quantity))
        return specs, errors

    @app.get("/help-requests")
    def help_board():
        expire_requests()
        db = get_db()
        filters = {key: request.args.get(key, "").strip() for key in (
            "q", "category", "level_cap", "status", "availability", "sort",
        )}
        clauses, params = [], []
        if filters["q"]:
            term = f"%{filters['q']}%"
            clauses.append("(h.title LIKE ? OR h.zone LIKE ? OR h.description LIKE ? OR m.name LIKE ?)")
            params.extend([term] * 4)
        if filters["category"].startswith("section:"):
            section = filters["category"].removeprefix("section:")
            activities = HELP_SECTIONS.get(section)
            if activities:
                placeholders = ",".join("?" for _ in activities)
                clauses.append(f"h.category IN ({placeholders})")
                params.extend(activities)
        elif filters["category"] in HELP_CATEGORIES:
            clauses.append("h.category=?"); params.append(filters["category"])
        if filters["level_cap"] == "uncapped":
            clauses.append("h.level_cap IS NULL")
        elif filters["level_cap"].isdigit():
            clauses.append("h.level_cap=?"); params.append(int(filters["level_cap"]))
        if filters["status"] in HELP_STATUSES:
            clauses.append("h.status=?"); params.append(filters["status"])
        else:
            clauses.append("h.status IN ('Open','Forming','Full')")
        if filters["availability"] in AVAILABILITY_MODES:
            clauses.append("h.availability_mode=?"); params.append(filters["availability"])
        order = {
            "recent": "h.created_at DESC", "now": "CASE WHEN h.availability_mode='now' THEN 0 ELSE 1 END, h.created_at DESC",
            "requester": "m.name COLLATE NOCASE", "soonest": "COALESCE(h.start_at, h.created_at)",
        }.get(filters["sort"], "COALESCE(h.start_at, h.created_at)")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = db.execute(
            f"""SELECT h.*, m.name requester_name,
                GROUP_CONCAT(j.job || ':' || j.level) requester_jobs
                FROM help_requests h JOIN members m ON m.id=h.requester_id
                LEFT JOIN member_jobs j ON j.member_id=m.id {where}
                GROUP BY h.id ORDER BY {order}, h.id""", params,
        ).fetchall()
        requests_data = []
        for row in rows:
            item = dict(row)
            selected_requester_jobs = {
                selected["job"] for selected in db.execute(
                    "SELECT job FROM help_request_jobs WHERE request_id=?", (item["id"],)
                ).fetchall()
            }
            jobs = []
            for pair in (item.pop("requester_jobs") or "").split(","):
                if pair:
                    job, level = pair.split(":")
                    eligible = item["level_cap"] is None or int(level) >= item["level_cap"]
                    if job in selected_requester_jobs and eligible:
                        jobs.append((job, int(level), True))
            item["jobs"] = jobs
            item["requested_party"] = [
                dict(spec) for spec in db.execute(
                    """SELECT role, kind, quantity FROM help_request_roles
                       WHERE request_id=? ORDER BY kind, role""", (item["id"],)
                ).fetchall()
            ]
            requests_data.append(item)
        try:
            year, month = map(int, request.args.get("month", "").split("-"))
            if not 1 <= month <= 12: raise ValueError
        except (ValueError, TypeError):
            year, month = date.today().year, date.today().month
        first = date(year, month, 1)
        cells = list(calendar.Calendar(firstweekday=6).itermonthdates(year, month))
        active = [item for item in requests_data if item["status"] in ACTIVE_HELP_STATUSES]
        calendar_days = [(day, [item for item in active if request_occurs_on(item, day)]) for day in cells]
        previous = first - timedelta(days=1)
        following = (date(year + (month == 12), 1 if month == 12 else month + 1, 1))
        members = db.execute(
            f"""SELECT id, name FROM members
                ORDER BY CASE name {''.join(f'WHEN ? THEN {index} ' for index in range(len(LOGIN_CHARACTERS)))}
                ELSE {len(LOGIN_CHARACTERS)} END, name COLLATE NOCASE""",
            LOGIN_CHARACTERS,
        ).fetchall()
        current_member = db.execute(
            "SELECT id, name FROM members WHERE id=?", (current_member_id(),)
        ).fetchone() if current_member_id() else None
        counts = db.execute("""SELECT COUNT(*) active,
            SUM(availability_mode='now') going_now,
            SUM(start_at BETWEEN datetime('now') AND datetime('now','+7 days')) scheduled
            FROM help_requests WHERE status IN ('Open','Forming','Full')""").fetchone()
        return render_template(
            "help_board.html", help_requests=requests_data, calendar_days=calendar_days,
            month_name=first.strftime("%B %Y"), month_key=first.strftime("%Y-%m"),
            previous_month=previous.strftime("%Y-%m"), next_month=following.strftime("%Y-%m"),
            categories=HELP_CATEGORIES, help_sections=HELP_SECTIONS, help_statuses=HELP_STATUSES,
            availability_modes=AVAILABILITY_MODES, filters=filters, counts=counts,
            members=members, current_member=current_member,
        )

    @app.route("/help-requests/new", methods=("GET", "POST"))
    @editor_required
    def create_help_request():
        member = require_member_identity()
        jobs = member_jobs(member["id"])
        if request.method == "POST":
            values, errors = validate_help_form(request.form)
            party_specs, party_errors = requested_party(request.form)
            errors.extend(party_errors)
            selected_jobs = {job for job in request.form.getlist("requester_jobs") if job in jobs}
            eligible = {job for job, level in jobs.items() if values["level_cap"] is None or level >= values["level_cap"]}
            if not selected_jobs:
                errors.append("Choose at least one job you are willing to bring.")
            elif not selected_jobs <= eligible:
                errors.append("Selected requester jobs must meet the level cap.")
            if not errors:
                db = get_db()
                cursor = db.execute(
                    """INSERT INTO help_requests
                    (requester_id,title,category,zone,description,level_cap,helpers_needed,
                     availability_mode,start_at,available_after,end_at,expires_at,requirements,notes)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (member["id"], values["title"], values["category"], values["zone"],
                     values["description"], values["level_cap"], values["helpers_needed"],
                     values["availability_mode"], values["start_at"] or None,
                     values["available_after"] or None, values["end_at"] or None,
                     values["expires_at"] or None, values["requirements"], values["notes"]),
                )
                request_id = cursor.lastrowid
                db.executemany("INSERT INTO help_request_jobs VALUES (?,?)", [(request_id, job) for job in selected_jobs])
                db.executemany(
                    "INSERT INTO help_request_roles(request_id,role,kind,quantity) VALUES (?,?,?,?)",
                    [(request_id, name, kind, quantity) for name, kind, quantity in party_specs],
                )
                db.commit()
                flash("Help request published.", "success")
                return redirect(url_for("help_request_detail", request_id=request_id))
            for error in errors: flash(error, "error")
        return render_template("help_request_form.html", help_request=None, member=member, member_jobs=jobs,
                               categories=HELP_CATEGORIES, help_sections=HELP_SECTIONS,
                               availability_modes=AVAILABILITY_MODES, help_zones=HELP_ZONES, all_jobs=JOBS,
                               party_roles=PARTY_ROLES, requested_specs={},
                               selected_jobs=set())

    @app.route("/help-requests/<int:request_id>/edit", methods=("GET", "POST"))
    @editor_required
    def edit_help_request(request_id):
        item = help_request_or_404(request_id)
        if not can_manage(item): abort(403)
        member = get_db().execute("SELECT * FROM members WHERE id=?", (item["requester_id"],)).fetchone()
        jobs = member_jobs(member["id"])
        selected_jobs = {r["job"] for r in get_db().execute("SELECT job FROM help_request_jobs WHERE request_id=?", (request_id,))}
        if request.method == "POST":
            values, errors = validate_help_form(request.form)
            party_specs, party_errors = requested_party(request.form)
            errors.extend(party_errors)
            submitted_jobs = {job for job in request.form.getlist("requester_jobs") if job in jobs}
            eligible = {job for job, level in jobs.items() if values["level_cap"] is None or level >= values["level_cap"]}
            if not submitted_jobs: errors.append("Choose at least one job you are willing to bring.")
            elif not submitted_jobs <= eligible: errors.append("Selected requester jobs must meet the level cap.")
            if not errors:
                db = get_db()
                db.execute("""UPDATE help_requests SET title=?,category=?,zone=?,description=?,level_cap=?,
                    helpers_needed=?,availability_mode=?,start_at=?,available_after=?,end_at=?,expires_at=?,
                    requirements=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (values["title"],values["category"],values["zone"],values["description"],values["level_cap"],
                     values["helpers_needed"],values["availability_mode"],values["start_at"] or None,
                     values["available_after"] or None,values["end_at"] or None,values["expires_at"] or None,
                     values["requirements"],values["notes"],request_id))
                db.execute("DELETE FROM help_request_jobs WHERE request_id=?", (request_id,))
                db.executemany("INSERT INTO help_request_jobs VALUES (?,?)", [(request_id, job) for job in submitted_jobs])
                db.execute("DELETE FROM help_request_roles WHERE request_id=?", (request_id,))
                db.executemany(
                    "INSERT INTO help_request_roles(request_id,role,kind,quantity) VALUES (?,?,?,?)",
                    [(request_id, name, kind, quantity) for name, kind, quantity in party_specs],
                )
                reactivated = item["status"] == "Cancelled" and request.form.get("reactivate") == "1"
                if reactivated:
                    db.execute(
                        "UPDATE help_requests SET status='Open',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (request_id,),
                    )
                db.commit(); flash("Help request updated.", "success")
                if reactivated:
                    flash("The cancelled request was reactivated and is open again.", "success")
                return redirect(url_for("help_request_detail", request_id=request_id))
            selected_jobs = submitted_jobs
            for error in errors: flash(error, "error")
        requested_specs = {
            (r["kind"], r["role"]): r["quantity"]
            for r in get_db().execute(
                "SELECT role, kind, quantity FROM help_request_roles WHERE request_id=?", (request_id,)
            )
        }
        return render_template("help_request_form.html", help_request=item, member=member, member_jobs=jobs,
                               categories=HELP_CATEGORIES, help_sections=HELP_SECTIONS,
                               availability_modes=AVAILABILITY_MODES, help_zones=HELP_ZONES, all_jobs=JOBS,
                               party_roles=PARTY_ROLES, selected_jobs=selected_jobs,
                               requested_specs=requested_specs)

    @app.get("/help-requests/<int:request_id>")
    def help_request_detail(request_id):
        expire_requests()
        item = help_request_or_404(request_id)
        db = get_db()
        requester_jobs = member_jobs(item["requester_id"])
        chosen = {r["job"] for r in db.execute("SELECT job FROM help_request_jobs WHERE request_id=?", (request_id,))}
        roles = db.execute(
            "SELECT role, kind, quantity FROM help_request_roles WHERE request_id=? ORDER BY kind, role",
            (request_id,),
        ).fetchall()
        volunteers = db.execute(
            """SELECT v.*, m.name, GROUP_CONCAT(j.job) jobs FROM help_volunteers v
               JOIN members m ON m.id=v.member_id LEFT JOIN help_volunteer_jobs j ON j.volunteer_id=v.id
               WHERE v.request_id=? GROUP BY v.id ORDER BY v.selected DESC, v.created_at""", (request_id,)
        ).fetchall()
        viewer_interest = db.execute(
            "SELECT * FROM help_volunteers WHERE request_id=? AND member_id=?",
            (request_id, current_member_id()),
        ).fetchone() if current_member_id() else None
        viewer_interest_jobs = {
            row["job"] for row in db.execute(
                "SELECT job FROM help_volunteer_jobs WHERE volunteer_id=?",
                (viewer_interest["id"],),
            )
        } if viewer_interest else set()
        viewer_jobs = member_jobs(current_member_id()) if current_member_id() else {}
        eligible_viewer_jobs = {job: level for job, level in viewer_jobs.items() if item["level_cap"] is None or level >= item["level_cap"]}
        return render_template("help_request_detail.html", help_request=item, requester_jobs=requester_jobs,
                               selected_jobs=chosen, roles=roles, volunteers=volunteers,
                               viewer_interest=viewer_interest, viewer_interest_jobs=viewer_interest_jobs,
                               viewer_jobs=eligible_viewer_jobs, can_manage=can_manage(item),
                               help_statuses=HELP_STATUSES, transitions=HELP_STATUS_TRANSITIONS.get(item["status"], set()),
                               availability_modes=AVAILABILITY_MODES)

    @app.post("/help-requests/<int:request_id>/volunteer")
    @editor_required
    def volunteer(request_id):
        member = require_member_identity(); item = help_request_or_404(request_id)
        if item["status"] not in ACTIVE_HELP_STATUSES or member["id"] == item["requester_id"]:
            abort(400)
        jobs = member_jobs(member["id"])
        eligible = {job for job, level in jobs.items() if item["level_cap"] is None or level >= item["level_cap"]}
        selected = {job for job in request.form.getlist("jobs") if job in eligible}
        db = get_db()
        db.execute("""INSERT INTO help_volunteers(request_id,member_id,note) VALUES(?,?,?)
            ON CONFLICT(request_id,member_id) DO UPDATE SET note=excluded.note,updated_at=CURRENT_TIMESTAMP""",
                   (request_id, member["id"], request.form.get("note", "").strip()))
        response = db.execute("SELECT id FROM help_volunteers WHERE request_id=? AND member_id=?", (request_id, member["id"])).fetchone()
        db.execute("DELETE FROM help_volunteer_jobs WHERE volunteer_id=?", (response["id"],))
        db.executemany("INSERT INTO help_volunteer_jobs VALUES (?,?)", [(response["id"], job) for job in selected])
        db.commit(); flash("You are listed as interested in helping.", "success")
        return redirect(url_for("help_request_detail", request_id=request_id))

    @app.post("/help-requests/<int:request_id>/withdraw")
    @editor_required
    def withdraw_volunteer(request_id):
        member = require_member_identity()
        get_db().execute("DELETE FROM help_volunteers WHERE request_id=? AND member_id=?", (request_id, member["id"]))
        get_db().commit(); flash("You withdrew from this request.", "success")
        return redirect(url_for("help_request_detail", request_id=request_id))

    @app.post("/help-requests/<int:request_id>/status")
    @editor_required
    def change_help_status(request_id):
        item = help_request_or_404(request_id)
        if not can_manage(item): abort(403)
        new_status = request.form.get("status", "")
        if new_status not in HELP_STATUS_TRANSITIONS.get(item["status"], set()): abort(400)
        get_db().execute("UPDATE help_requests SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_status, request_id))
        get_db().commit(); flash(f"Request marked {new_status.lower()}.", "success")
        return redirect(url_for("help_request_detail", request_id=request_id))

    @app.post("/help-requests/<int:request_id>/delete")
    @admin_required
    def delete_help_request(request_id):
        item = help_request_or_404(request_id)
        get_db().execute("DELETE FROM help_requests WHERE id=?", (request_id,))
        get_db().commit()
        flash(f"Removed help request “{item['title']}”.", "success")
        return redirect(url_for("help_board"))

    @app.post("/help-requests/<int:request_id>/volunteers/<int:volunteer_id>/select")
    @editor_required
    def select_volunteer(request_id, volunteer_id):
        item = help_request_or_404(request_id)
        if not can_manage(item): abort(403)
        selected = 1 if request.form.get("selected") == "1" else 0
        get_db().execute("UPDATE help_volunteers SET selected=? WHERE id=? AND request_id=?", (selected, volunteer_id, request_id))
        get_db().commit()
        return redirect(url_for("help_request_detail", request_id=request_id))

    @app.get("/my-help-requests")
    @editor_required
    def my_help_requests():
        member = require_member_identity()
        db = get_db()
        created_requests = db.execute(
            """SELECT h.*, m.name requester_name,
                      (SELECT COUNT(*) FROM help_volunteers v WHERE v.request_id=h.id) volunteer_count
               FROM help_requests h
               JOIN members m ON m.id=h.requester_id
               WHERE h.requester_id=?
               ORDER BY h.created_at DESC""",
            (member["id"],),
        ).fetchall()
        volunteered_requests = db.execute(
            """SELECT h.*, m.name requester_name, v.selected volunteer_selected,
                      v.note volunteer_note, GROUP_CONCAT(vj.job) volunteer_jobs
               FROM help_volunteers v
               JOIN help_requests h ON h.id=v.request_id
               JOIN members m ON m.id=h.requester_id
               LEFT JOIN help_volunteer_jobs vj ON vj.volunteer_id=v.id
               WHERE v.member_id=? AND h.requester_id<>?
               GROUP BY h.id, v.id
               ORDER BY v.updated_at DESC, h.created_at DESC""",
            (member["id"], member["id"]),
        ).fetchall()
        return render_template(
            "my_help_requests.html",
            created_requests=created_requests,
            volunteered_requests=volunteered_requests,
            member=member,
        )

    @app.get("/api/horizon-player/<name>")
    def horizon_player(name):
        try:
            player = fetch_horizon_player(name)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except HTTPError as error:
            if error.code == 404:
                return jsonify(error="Character not found on HorizonXI."), 404
            return jsonify(error="HorizonXI could not complete the lookup."), 502
        except (URLError, TimeoutError, json.JSONDecodeError):
            return jsonify(error="HorizonXI is temporarily unavailable. You can enter levels manually."), 502

        jobs = {
            job: int(level)
            for job, level in player.get("jobs", {}).items()
            if job in JOBS and isinstance(level, (int, float)) and 1 <= int(level) <= 75
        }
        return jsonify(name=player.get("name", name), jobs=jobs)

    @app.post("/members/<int:member_id>/delete")
    @admin_required
    def delete_member(member_id):
        db = get_db()
        target = db.execute("SELECT id,name FROM members WHERE id=?", (member_id,)).fetchone()
        if not target:
            abort(404)
        actor = require_member_identity()
        if target["id"] == actor["id"] or target["name"].casefold() == "imaven":
            abort(400, description="You cannot remove the administrator account or your own account.")
        db.execute(
            "INSERT INTO admin_change_log(actor_member_id,area,action,details) VALUES(?,?,?,?)",
            (actor["id"], "Members", "Member removed", target["name"]),
        )
        db.execute("DELETE FROM members WHERE id=?", (member_id,))
        db.commit()
        flash(f"{target['name']} was removed and their website access was revoked.", "success")
        return redirect(request.referrer or url_for("index"))

    with app.app_context():
        init_db()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
