"""Build the local level-75 Blue Magic farming catalog.

Source rows are factual spell/mob/zone data published by ffxibluemage.com.
The generated catalog removes post-ToAU zones and derives the minimum learning
skill from the HorizonXI rule that the caster may be at most 29 skill below cap.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

SOURCE = "https://ffxibluemage.com/blue_magic_data.json"
LSB_SQL_BASE = "https://raw.githubusercontent.com/LandSandBoat/server/base/sql"
BLUE_SPELL_LIST_SOURCE = f"{LSB_SQL_BASE}/blue_spell_list.sql"
BLUE_SPELL_MODS_SOURCE = f"{LSB_SQL_BASE}/blue_spell_mods.sql"
BLUE_TRAITS_SOURCE = f"{LSB_SQL_BASE}/blue_traits.sql"
BLUE_SPELL_SCRIPTS_API = "https://api.github.com/repos/LandSandBoat/server/contents/scripts/actions/spells/blue?ref=base"
OUTPUT = Path("static/blue_spell_farming.json")
HORIZON_SPELL_CARD_SOURCE = (
    "https://drive.google.com/drive/folders/"
    "1ywDWD8cixd0L-JW-pVmWa3EeHlF_R70s"
)

# Horizon's ToAU spell cards are newer than the retail/LSB metadata used to
# seed this catalog. Values here intentionally win whenever the sources differ.
# Normal traits use LSB's internal weight (card value / 4); Auto Refresh keeps
# its raw card weight, matching the special scale used by blue_spellbook.js.
HORIZON_SPELL_OVERRIDES = {
    "auroral drape": {
        "spell_level": 42, "set_points": 4, "set_stats": ["INT+1"],
        "trait": "Fast Cast", "trait_weight": 1,
    },
    "blank gaze": {"trait": "Magic Attack Bonus", "trait_weight": 1},
    "blitzstrahl": {"trait": "Magic Accuracy Bonus", "trait_weight": 1},
    "blood drain": {"trait": "Conserve MP", "trait_weight": 1},
    "blood saber": {
        "set_points": 3, "trait": "Auto Refresh", "trait_weight": 4,
    },
    "bomb toss": {"trait": "Magic Accuracy Bonus", "trait_weight": 1},
    "empty thrash": {
        "spell_level": 34, "set_points": 3, "set_stats": ["STR+1"],
        "trait": "Max HP Boost", "trait_weight": 1,
    },
    "geist wall": {"trait": "Auto Refresh", "trait_weight": 4},
    "infrasonics": {"trait": "Magic Accuracy Bonus", "trait_weight": 1},
    "metallic body": {
        "set_points": 3, "set_stats": [], "trait": "Conserve MP",
        "trait_weight": 1,
    },
    "occultation": {
        "spell_level": 38, "set_points": 3, "set_stats": [],
        "trait": "Evasion Bonus", "trait_weight": 1,
    },
    "quadratic continuum": {
        "spell_level": 54, "trait": "Defense Bonus", "trait_weight": 1,
    },
    "vanity dive": {
        "spell_level": 28, "set_points": 4, "set_stats": ["AGI+1"],
        "trait": "Accuracy Bonus", "trait_weight": 1,
    },
    "winds of promyvion": {
        "spell_level": 56,
    },
}

HORIZON_COMBAT_OVERRIDES = {
    "vanity dive": {
        "spell_type": "Physical",
        "element": None,
        "stat_modifiers": ["STR (fSTR)", "DEX 50%"],
        "physical_damage_type": "Slashing",
        "description": "Damage varies with TP.",
    },
    "winds of promyvion": {
        "spell_type": "Magical",
        "element": "Light",
        "stat_modifiers": ["Fixed potency"],
        "physical_damage_type": None,
        "description": "Erases one beneficial magic effect from an enemy.",
    },
}

DENIED_ZONE_PARTS = (
    "abyssea", "escha", "reisenjima", "ceizak", "yahse", "foret de hennetiel",
    "morimar", "marjami", "kamihr", "yorcia", "ra'kaznar", "dho gates",
    "moh gates", "sih gates", "woh gates", "crawler's nest [s]", " (s)",
    "everbloom hollow", "maze voucher", "walk of echoes",
)

ZONE_FIXES = {
    "Boyahda Tree": "The Boyahda Tree",
    "Crawlers' Nest": "Crawler's Nest",
    "Eldieme Necropolis": "The Eldieme Necropolis",
    "Lower Delkfutt Tower": "Lower Delkfutt's Tower",
    "Lower Delkfutts Tower": "Lower Delkfutt's Tower",
    "Middle Delkfutt Tower": "Middle Delkfutt's Tower",
    "Riverne - Site A01": "Riverne - Site #A01",
    "Riverne Site #B01": "Riverne - Site #B01",
    "Sanctuary of Zi'Tah": "The Sanctuary of Zi'Tah",
}


def blue_magic_cap(level: int) -> int:
    """Return the classic A+ Blue Magic skill cap at a job level."""
    if level <= 50:
        return level * 3 + 3
    if level <= 60:
        return 153 + (level - 50) * 5
    if level <= 70:
        return 203 + int((level - 60) * 4.5)
    return 248 + round((level - 70) * 5.6)


def clean_level(value: object) -> int | None:
    match = re.match(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def clean_zone(value: object) -> str | None:
    zone = " ".join(str(value or "").split()).strip()
    if not zone or len(zone) > 70 or zone.startswith("**"):
        return None
    lower = zone.lower()
    if any(part in lower for part in DENIED_ZONE_PARTS):
        return None
    return ZONE_FIXES.get(zone, zone)


def parse_blue_metadata(spell_list_sql: str, spell_mods_sql: str,
                        blue_traits_sql: str) -> dict[str, dict]:
    """Parse set cost, equipped stats, and trait categories from LSB SQL."""
    trait_names = {}
    for match in re.finditer(
        r"INSERT INTO `blue_traits` VALUES \((\d+),[^;]+;\s*--\s*(.+?)\s*\(\d+\)",
        blue_traits_sql,
    ):
        trait_names.setdefault(int(match.group(1)), match.group(2).strip())

    modifiers: dict[int, list[str]] = {}
    for match in re.finditer(
        r"INSERT INTO `blue_spell_mods` VALUES \((\d+),\d+,-?\d+\);\s*--\s*(.+)",
        spell_mods_sql,
    ):
        modifier = match.group(2).strip()
        modifiers.setdefault(int(match.group(1)), []).append(modifier)

    metadata = {}
    for match in re.finditer(
        r"INSERT INTO `blue_spell_list` VALUES "
        r"\((\d+),\d+,(\d+),(\d+),(\d+),[^;]+;\s*--\s*(.+)",
        spell_list_sql,
    ):
        spell_id, set_points, trait_category, trait_weight = map(
            int, match.groups()[:4]
        )
        spell = match.group(5).strip()
        stats = [value for value in modifiers.get(spell_id, []) if value != "No Stats"]
        metadata[spell.casefold()] = {
            "set_points": set_points,
            "set_stats": stats,
            "trait": trait_names.get(trait_category),
            "trait_weight": trait_weight if trait_category else 0,
        }
    return metadata


def parse_combat_metadata(script: str) -> tuple[str, list[str]]:
    """Extract spell category and damage-scaling stats from an LSB spell script."""
    if "useCuringSpell" in script:
        spell_type = "Magical"
        # Blue cures use getCurePowerOld: (3 * MND) + VIT +
        # (3 * floor(Blue Magic skill / 5)).
        modifiers = ["MND x3", "VIT x1", "3 x floor(Blue Magic Skill / 5)"]
    elif "usePhysicalSpell" in script:
        spell_type = "Physical"
        modifiers = ["STR (fSTR)"]
    elif "useBreathSpell" in script:
        spell_type = "Magical (Breath)"
        modifiers = ["Current HP", "Main Level"]
    elif "useDrainSpell" in script:
        spell_type = "Magical"
        modifiers = ["Blue Magic Skill"]
    elif "useEnfeeblingSpell" in script:
        spell_type = "Magical"
        modifiers = ["Fixed potency", "INT (accuracy)", "Blue Magic Skill (accuracy)"]
    elif "useMagicalSpell" in script or "useDrainSpell" in script:
        spell_type = "Magical"
        modifiers = []
    else:
        type_comment = re.search(r"--\s*Spell Type:\s*([^\r\n]+)", script, re.I)
        detail = type_comment.group(1).strip() if type_comment else "Support"
        if re.search(r"physical", detail, re.I):
            spell_type = "Physical"
        elif re.search(r"breath", detail, re.I):
            spell_type = "Magical (Breath)"
        elif re.search(r"magical", detail, re.I):
            spell_type = "Magical"
        else:
            spell_type = "Support"
        modifiers = []

    # These spells bypass the standard helpers and carry misleading, unused
    # parameter blocks in their scripts. Describe the formula that is actually
    # executed rather than parsing those unused fields.
    if re.search(r"--\s*Spell:\s*1000 Needles\b", script, re.I):
        return "Magical", ["Fixed 1000 damage", "INT (accuracy)", "Blue Magic Skill (accuracy)"]
    if re.search(r"--\s*Spell:\s*Self-Destruct\b", script, re.I):
        return "Magical", ["Current HP"]

    attribute = re.search(r"params\.attribute\s*=\s*xi\.mod\.(STR|DEX|VIT|AGI|INT|MND|CHR)", script)
    if attribute:
        stat = attribute.group(1)
        if "useMagicalSpell" in script:
            label = stat
        elif "usePhysicalSpell" in script:
            label = f"{stat} (effect accuracy)"
        else:
            label = f"{stat} (accuracy)"
        if label not in modifiers:
            modifiers.append(label)
    for stat, coefficient in re.findall(
        r"params\.(str|dex|vit|agi|int|mnd|chr)_wsc\s*=\s*(-?\d+(?:\.\d+)?)",
        script,
        re.I,
    ):
        value = float(coefficient)
        if value:
            label = f"{stat.upper()} {value * 100:g}%"
            if label not in modifiers:
                modifiers.append(label)

    if "useMagicalSpell" not in script and "usePhysicalSpell" not in script:
        if re.search(r"getSkillLevel\(xi\.skill\.BLUE_MAGIC\)", script) and "Blue Magic Skill" not in modifiers:
            modifiers.append("Blue Magic Skill")
        if re.search(r"actorStat\s*=\s*xi\.mod\.INT", script):
            for label in ("INT (accuracy)", "Blue Magic Skill (accuracy)"):
                if label not in modifiers:
                    modifiers.append(label)
        if not modifiers:
            modifiers.append("Fixed potency")
    return spell_type, modifiers


def parse_magic_element(script: str) -> str | None:
    """Return a magical Blue Magic spell's listed elemental alignment.

    LandSandBoat's spell headers use ``Magical (Fire)`` (and the other seven
    elements), which is the player-facing element needed when choosing a
    Magic Burst. Keep it separate from ``spell_type`` so existing category
    filters continue to work.
    """
    match = re.search(
        r"--\s*Spell Type:\s*Magical\s*\((Fire|Ice|Wind|Earth|Lightning|Water|Light|Dark)\)",
        script,
        re.I,
    )
    return match.group(1).title() if match else None


def parse_physical_damage_type(script: str) -> str | None:
    """Return the physical damage family advertised or used by a spell script."""
    comment = re.search(r"--\s*Spell Type:\s*Physical\s*\(([^)]+)\)", script, re.I)
    if comment:
        value = comment.group(1).strip().title()
        if value in {"Blunt", "Slashing", "Piercing"}:
            return value
    damage = re.search(r"params\.damageType\s*=\s*xi\.damageType\.([A-Z_]+)", script)
    if not damage:
        return None
    value = damage.group(1)
    if value in {"HAND_TO_HAND", "BLUNT"}:
        return "Blunt"
    if value in {"PIERCING", "RANGED"}:
        return "Piercing"
    if value == "SLASHING":
        return "Slashing"
    return None


def parse_spell_description(script: str) -> str:
    """Extract the concise player-facing effect summary from a spell header."""
    lines = [re.sub(r"^\s*--\s?", "", line).strip() for line in script.splitlines()]
    spell_index = next((index for index, line in enumerate(lines)
                        if line.casefold().startswith("spell:")), -1)
    ignored = ("spell cost:", "monster type:", "spell type:", "blue magic points:",
               "stat bonus:", "level:", "casting time:", "recast time:",
               "duration:", "skillchain element", "combos:")
    descriptions = []
    for line in lines[spell_index + 1:]:
        if not line or set(line) == {"-"}:
            if descriptions:
                break
            continue
        if line.casefold().startswith(ignored):
            if descriptions:
                break
            continue
        descriptions.append(line)
    return " ".join(descriptions).strip()


EFFECT_PATTERNS = (
    ("HP Drain", r"steals? (?:an enemy's |)hp"), ("MP Drain", r"steals? (?:an amount of enemy's |an enemy's |)mp"),
    ("Stun", r"\bstun\b|prevented from acting"), ("Slow", r"\bslow\b|reduces? the attack speed of enemies"),
    ("Poison", r"\bpoison(?:s|ed)?\b"), ("Sleep", r"\bsleep\b"), ("Bind", r"\bbind\b"),
    ("Paralyze", r"\bparalysis\b"), ("Blind", r"\bblind(?:ness|s)?\b"), ("Silence", r"\bsilence[ds]?\b"),
    ("Dispel", r"removes? one beneficial magic effect|steals? an enemy's buff"),
    ("Defense Down", r"weakens? defense|lowers? the defense"),
    ("Magic Defense Down", r"lowers? .*magical defense"), ("Attack Down", r"weakens? attacks"),
    ("Accuracy Down", r"lowers? (?:the |)accuracy"), ("Evasion Down", r"lowers? the evasion"),
    ("STR Down", r"\bstr down\b|lowers? strength"), ("DEX Down", r"\bdex down\b"),
    ("VIT Down", r"\bvit(?:ality)? down\b|lowers? vitality"), ("AGI Down", r"lowers? agility"),
    ("INT Down", r"lowers? intelligence"), ("Weight", r"\bweight\b"),
    ("Disease", r"\bdisease\b"), ("TP Down", r"reduces? an enemy's tp"), ("Fear", r"\bfear\b"),
    ("Cure", r"restores? hp"), ("Stoneskin", r"\bstoneskin\b|absorbs? an? certain amount of damage"),
    ("Haste", r"increases? attack speed"), ("Defense Boost", r"enhances? defense"),
    ("Magic Attack Boost", r"enhances? magic attack"), ("Magic Defense Boost", r"enhances? magic defense"),
    ("Evasion Boost", r"enhances? evasion"), ("Accuracy Boost", r"enhances? accuracy"),
    ("Blink", r"shadow images"), ("Spikes", r"magical .* spikes"),
)


def parse_spell_effects(description: str) -> list[str]:
    """Map Blue Magic wording to familiar player-facing spell/effect goals."""
    return [name for name, pattern in EFFECT_PATTERNS if re.search(pattern, description, re.I)]


def fetch_combat_metadata() -> dict[str, dict]:
    """Download and parse the current LSB Blue Magic action scripts."""
    with urlopen(BLUE_SPELL_SCRIPTS_API, timeout=30) as response:
        files = [row for row in json.load(response) if row.get("name", "").endswith(".lua")]

    def load(row: dict) -> tuple[str, str]:
        with urlopen(row["download_url"], timeout=30) as response:
            return row["name"], response.read().decode("utf-8")

    metadata = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        for filename, script in executor.map(load, files):
            name_match = re.search(r"--\s*Spell:\s*([^\r\n]+)", script, re.I)
            spell = name_match.group(1).strip() if name_match else filename[:-4].replace("_", " ")
            spell_type, modifiers = parse_combat_metadata(script)
            metadata[spell.casefold()] = {
                "spell_type": spell_type,
                "element": parse_magic_element(script) if spell_type == "Magical" else None,
                "stat_modifiers": modifiers,
                "physical_damage_type": parse_physical_damage_type(script),
                "description": parse_spell_description(script),
            }
    return metadata


def build(rows: list[dict], metadata: dict[str, dict] | None = None,
          combat_metadata: dict[str, dict] | None = None) -> dict:
    metadata = metadata or {}
    combat_metadata = combat_metadata or {}
    catalog = []
    seen = set()
    for row in rows:
        spell = " ".join(str(row.get("name") or "").split())
        horizon_override = HORIZON_SPELL_OVERRIDES.get(spell.casefold(), {})
        spell_level = horizon_override.get("spell_level", clean_level(row.get("spell_level")))
        zone = clean_zone(row.get("zone"))
        monster = " ".join(str(row.get("monster_name") or "").split())
        if not spell_level or spell_level > 75 or not zone or not spell or not monster:
            continue
        minimum = clean_level(row.get("min_level"))
        maximum = clean_level(row.get("max_level"))
        key = (spell.lower(), monster.lower(), zone.lower(), minimum, maximum)
        if key in seen:
            continue
        seen.add(key)
        cap = blue_magic_cap(spell_level)
        spell_metadata = {
            **metadata.get(spell.casefold(), {}),
            **{key: value for key, value in horizon_override.items()
               if key != "spell_level"},
        }
        combat = {
            **combat_metadata.get(spell.casefold(), {}),
            **HORIZON_COMBAT_OVERRIDES.get(spell.casefold(), {}),
        }
        catalog.append({
            "spell": spell,
            "spell_level": spell_level,
            "skill_cap": cap,
            "minimum_skill": max(0, cap - 29),
            "monster": monster,
            "zone": zone,
            "monster_min": minimum,
            "monster_max": maximum,
            "source": row.get("link") or "",
            "set_points": spell_metadata.get("set_points"),
            "set_stats": spell_metadata.get("set_stats", []),
            "trait": spell_metadata.get("trait"),
            "trait_weight": spell_metadata.get("trait_weight", 0),
            "spell_type": combat.get("spell_type", "Support"),
            "element": combat.get("element"),
            "stat_modifiers": combat.get("stat_modifiers", []),
            "physical_damage_type": combat.get("physical_damage_type"),
            "description": combat.get("description", ""),
            "effects": parse_spell_effects(combat.get("description", "")),
        })
    catalog.sort(key=lambda item: (item["spell_level"], item["spell"], item["zone"], item["monster"]))
    return {
        "source": SOURCE,
        "horizon_rule_source": "https://horizonffxi.wiki/Category:Blue_Magic",
        "horizon_spell_card_source": HORIZON_SPELL_CARD_SOURCE,
        "blue_metadata_source": BLUE_SPELL_LIST_SOURCE,
        "combat_metadata_source": BLUE_SPELL_SCRIPTS_API,
        "era": "Original through Treasures of Aht Urhgan; level cap 75",
        "rows": catalog,
    }


def main() -> None:
    with urlopen(SOURCE, timeout=30) as response:
        rows = json.load(response)
    with urlopen(BLUE_SPELL_LIST_SOURCE, timeout=30) as response:
        spell_list_sql = response.read().decode("utf-8")
    with urlopen(BLUE_SPELL_MODS_SOURCE, timeout=30) as response:
        spell_mods_sql = response.read().decode("utf-8")
    with urlopen(BLUE_TRAITS_SOURCE, timeout=30) as response:
        blue_traits_sql = response.read().decode("utf-8")
    metadata = parse_blue_metadata(spell_list_sql, spell_mods_sql, blue_traits_sql)
    combat_metadata = fetch_combat_metadata()
    payload = build(rows, metadata, combat_metadata)
    OUTPUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    spells = {row["spell"] for row in payload["rows"]}
    print(f"Wrote {len(payload['rows'])} farming targets for {len(spells)} spells to {OUTPUT}")


if __name__ == "__main__":
    main()
