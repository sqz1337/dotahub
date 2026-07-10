#!/usr/bin/env python3
"""Build the first dashboard JSON from the local OpenDota SQLite database."""

from __future__ import annotations

import argparse
import json
import ssl
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "opendota.sqlite"
OUTPUT_PATH = ROOT / "data" / "dashboard.json"
CONSTANTS_DIR = ROOT / "data" / "constants"
ROLE_OVERRIDES_PATH = ROOT / "data" / "player-role-overrides.json"
SOURCE_URL = "https://api.opendota.com/api"
STEAM_CDN = "https://cdn.cloudflare.steamstatic.com"
SSL_CONTEXT = ssl.create_default_context()

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass

GAME_MODES = {
    1: "All Pick",
    2: "Captains Mode",
    3: "Random Draft",
    4: "Single Draft",
    5: "All Random",
    12: "Least Played",
    16: "Captains Draft",
    18: "Ability Draft",
    22: "Ranked",
    23: "Turbo",
}

HERO_FALLBACKS = {
    7: "Earthshaker",
    8: "Juggernaut",
    25: "Lina",
    31: "Lich",
    35: "Sniper",
    36: "Necrophos",
    42: "Wraith King",
    52: "Leshrac",
    56: "Clinkz",
    62: "Bounty Hunter",
    71: "Spirit Breaker",
    79: "Shadow Demon",
    84: "Ogre Magi",
    99: "Bristleback",
    123: "Hoodwink",
    145: "Kez",
}

CONSTANT_RESOURCES = ("heroes", "game_mode", "lobby_type")

# The existing card targets are the Legend/normal-game baseline. Higher medals
# use tougher targets; Turbo uses its own targets instead of inflating farm
# stats against the normal-game scale. Keep these multipliers here so tuning
# the balance does not require changing the card formulas below.
RANK_TARGET_MULTIPLIERS = {
    1: 0.72,  # Herald
    2: 0.78,  # Guardian
    3: 0.85,  # Crusader
    4: 0.92,  # Archon
    5: 1.00,  # Legend
    6: 1.07,  # Ancient
    7: 1.14,  # Divine
    8: 1.21,  # Immortal
}

TURBO_TARGET_MULTIPLIERS = {
    "kda": 1.04,
    "kills": 1.18,
    "deaths": 1.16,
    "assists": 1.16,
    "gpm": 1.42,
    "xpm": 1.48,
    "heroDamage": 1.14,
    "towerDamage": 1.22,
    "healing": 1.12,
    "lastHits": 1.12,
    "economy": 1.45,
}

# These describe the expected shape of a role, not an OVR bonus. A lower farm
# target for supports/offlaners prevents core farming benchmarks from dragging
# down their card, while their OVR role weights still reward utility and impact.
ROLE_TARGET_MULTIPLIERS = {
    "CRY": {"gpm": 1.12, "xpm": 1.04, "lastHits": 1.15, "kills": 1.03, "deaths": 0.96, "assists": 0.85, "heroDamage": 1.03, "towerDamage": 1.12, "healing": 0.70, "economy": 1.08, "kda": 1.00},
    "MID": {"gpm": 1.02, "xpm": 1.10, "lastHits": 1.00, "kills": 1.10, "deaths": 0.98, "assists": 0.90, "heroDamage": 1.10, "towerDamage": 1.00, "healing": 0.75, "economy": 1.06, "kda": 1.05},
    "OFF": {"gpm": 0.88, "xpm": 0.95, "lastHits": 0.78, "kills": 0.98, "deaths": 1.08, "assists": 1.04, "heroDamage": 1.00, "towerDamage": 0.92, "healing": 1.10, "economy": 0.91, "kda": 0.97},
    "SUP": {"gpm": 0.72, "xpm": 0.84, "lastHits": 0.52, "kills": 0.80, "deaths": 1.12, "assists": 1.20, "heroDamage": 0.88, "towerDamage": 0.72, "healing": 1.25, "economy": 0.78, "kda": 0.92},
    "FLX": {},
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_json(path: str) -> Any:
    req = Request(f"{SOURCE_URL}{path}", headers={"User-Agent": "dotafifa-dashboard-data/0.1"})
    try:
        with urlopen(req, timeout=45, context=SSL_CONTEXT) as response:
            return json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch {path}: {exc}") from exc


def load_constants(refresh: bool = False) -> dict[str, dict[str, Any]]:
    CONSTANTS_DIR.mkdir(parents=True, exist_ok=True)
    constants = {}
    for resource in CONSTANT_RESOURCES:
        path = CONSTANTS_DIR / f"{resource}.json"
        if refresh or not path.exists():
            payload = fetch_json(f"/constants/{resource}")
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        constants[resource] = json.loads(path.read_text(encoding="utf-8"))
    return constants


def prettify_constant_name(name: str | None, prefix: str) -> str:
    if not name:
        return "Unknown"
    if name.startswith(prefix):
        name = name[len(prefix) :]
    overrides = {
        "all_pick": "All Pick",
        "captains_mode": "Captains Mode",
        "random_draft": "Random Draft",
        "single_draft": "Single Draft",
        "all_random": "All Random",
        "ranked_all_pick": "Ranked All Pick",
        "turbo": "Turbo",
        "normal": "Normal",
        "ranked": "Ranked",
        "ranked_solo_mm": "Ranked Solo",
        "ranked_team_mm": "Ranked Team",
    }
    return overrides.get(name, name.replace("_", " ").title())


def constant_by_id(constants: dict[str, Any], resource: str, item_id: int | None) -> dict[str, Any] | None:
    if item_id is None:
        return None
    value = constants.get(resource, {}).get(str(item_id))
    return value if isinstance(value, dict) else None


def load_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


def iso_from_ts(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def duration_label(seconds: int | None) -> str:
    if not seconds:
        return "00:00"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def hero_name(hero_id: int | None, constants: dict[str, Any]) -> str:
    if hero_id is None:
        return "Unknown Hero"
    hero = constant_by_id(constants, "heroes", hero_id)
    if hero:
        return hero.get("localized_name") or HERO_FALLBACKS.get(hero_id, f"Hero {hero_id}")
    return HERO_FALLBACKS.get(hero_id, f"Hero {hero_id}")


def hero_image(hero_id: int | None, constants: dict[str, Any], kind: str = "icon") -> str | None:
    if hero_id is None:
        return None
    hero = constant_by_id(constants, "heroes", hero_id)
    if not hero:
        return None
    path = hero.get(kind) or hero.get("icon") or hero.get("img")
    if not path:
        return None
    return f"{STEAM_CDN}{path.rstrip('?')}"


def game_mode_name(game_mode: int | None, constants: dict[str, Any]) -> str:
    if game_mode is None:
        return "Unknown"
    mode = constant_by_id(constants, "game_mode", game_mode)
    if mode:
        return prettify_constant_name(mode.get("name"), "game_mode_")
    return GAME_MODES.get(game_mode, f"Mode {game_mode}")


def lobby_type_name(lobby_type: int | None, constants: dict[str, Any]) -> str:
    if lobby_type is None:
        return "Unknown"
    lobby = constant_by_id(constants, "lobby_type", lobby_type)
    if lobby:
        return prettify_constant_name(lobby.get("name"), "lobby_type_")
    return f"Lobby {lobby_type}"


def is_win(row: sqlite3.Row) -> bool:
    slot = row["player_slot"]
    radiant_win = row["radiant_win"]
    if slot is None or radiant_win is None:
        return False
    return (slot < 128 and radiant_win == 1) or (slot >= 128 and radiant_win == 0)


def clamp_score(value: float, low: int = 35, high: int = 99) -> int:
    return max(low, min(high, round(value)))


def metric_score(value: float, target: float, low: int = 40, high: int = 99) -> int:
    if target <= 0:
        return low
    return clamp_score(low + (high - low) * min(max(value, 0) / target, 1), low, high)


def contextual_metric_score(
    value: float,
    target: float,
    metric: str,
    rank_tier: int | None,
    mode: str,
    position: str,
    low: int = 40,
    high: int = 99,
) -> int:
    medal = rank_medal(rank_tier)["medal"]
    multiplier = RANK_TARGET_MULTIPLIERS.get(medal, RANK_TARGET_MULTIPLIERS[5])
    if mode == "turbo":
        multiplier *= TURBO_TARGET_MULTIPLIERS.get(metric, 1.0)
    multiplier *= ROLE_TARGET_MULTIPLIERS.get(position, ROLE_TARGET_MULTIPLIERS["FLX"]).get(metric, 1.0)
    return metric_score(value, target * multiplier, low, high)


def rank_medal(rank_tier: int | None) -> dict[str, Any]:
    medal = 1
    stars = 1
    if rank_tier:
        medal = max(1, min(8, int(rank_tier) // 10))
        stars = int(rank_tier) % 10
        if medal >= 8:
            stars = 1
        else:
            stars = max(1, min(5, stars or 1))
    template_by_medal = {
        1: "archon",
        2: "archon",
        3: "archon",
        4: "archon",
        5: "legend",
        6: "ancient",
        7: "divine",
        8: "immortal",
    }
    return {"medal": medal, "stars": stars, "template": template_by_medal.get(medal, "archon")}


def detailed_match_stats(conn: sqlite3.Connection, account_id: int, matches: list[sqlite3.Row]) -> list[dict[str, Any]]:
    details = {
        int(row["match_id"]): row
        for row in conn.execute(
            """
            SELECT *
            FROM match_players
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchall()
    }
    stats = []
    for match in matches:
        detail = details.get(int(match["match_id"]))
        raw = load_json(match["raw_json"], {})
        # Parsed match details (match_players) carry the reliable lane_role; the
        # aggregated matches list only has it for a fraction of games, so prefer
        # the detail payload and fall back to the list value.
        detail_raw = load_json(detail["raw_json"], {}) if detail else {}
        lane_role = detail_raw.get("lane_role")
        if lane_role is None:
            lane_role = raw.get("lane_role")
        stats.append(
            {
                "matchId": match["match_id"],
                "gameMode": match["game_mode"],
                "win": is_win(match),
                "kills": (detail["kills"] if detail else match["kills"]) or 0,
                "deaths": (detail["deaths"] if detail else match["deaths"]) or 0,
                "assists": (detail["assists"] if detail else match["assists"]) or 0,
                "gpm": (detail["gold_per_min"] if detail else raw.get("gold_per_min")) or 0,
                "xpm": (detail["xp_per_min"] if detail else raw.get("xp_per_min")) or 0,
                "heroDamage": (detail["hero_damage"] if detail else raw.get("hero_damage")) or 0,
                "towerDamage": (detail["tower_damage"] if detail else raw.get("tower_damage")) or 0,
                "healing": (detail["hero_healing"] if detail else raw.get("hero_healing")) or 0,
                "lastHits": (detail["last_hits"] if detail else raw.get("last_hits")) or 0,
                "laneRole": lane_role,
            }
        )
    return stats


def infer_position(stats: list[dict[str, Any]]) -> str:
    """Resolve the player's role from the parsed OpenDota lane_role.

    lane_role is Dota's real lane indicator (1=safelane, 2=mid, 3=offlane,
    4=jungle). It maps directly to MID/OFF, while safelane and offlane still
    hold two roles each (core vs support), so those two are split by farm
    priority (last hits / GPM) rather than guessed from scratch.
    """
    games = max(1, len(stats))
    avg_last_hits = sum(item["lastHits"] for item in stats) / games

    lane_roles = [item["laneRole"] for item in stats if item.get("laneRole")]
    if lane_roles:
        role = Counter(lane_roles).most_common(1)[0][0]
        if role == 2:
            return "MID"
        if role == 4:
            return "SUP"
        # Safelane and offlane each hold a core and a support. Split by last
        # hits, the clearest farm signal — GPM is unreliable here because a
        # support's GPM is inflated by kill gold despite barely farming creeps.
        if role == 3:
            return "OFF" if avg_last_hits >= 100 else "SUP"
        # role == 1 (safelane): position 1 carry vs position 5 hard support.
        return "CRY" if avg_last_hits >= 130 else "SUP"

    # No parsed lane data for any game — fall back to a farm/impact heuristic.
    avg_gpm = sum(item["gpm"] for item in stats) / games
    avg_kills = sum(item["kills"] for item in stats) / games
    avg_xpm = sum(item["xpm"] for item in stats) / games
    avg_hero_damage = sum(item["heroDamage"] for item in stats) / games
    avg_tower_damage = sum(item["towerDamage"] for item in stats) / games
    avg_assists = sum(item["assists"] for item in stats) / games
    avg_healing = sum(item["healing"] for item in stats) / games

    if avg_last_hits >= 200 and avg_tower_damage >= 4500:
        return "CRY"
    if avg_assists >= 16 and avg_last_hits <= 130 and avg_tower_damage < 3200:
        return "SUP"

    scores = {
        "CRY": 0.34 * min(avg_last_hits / 260, 1) + 0.26 * min(avg_tower_damage / 7000, 1) + 0.25 * min(avg_gpm / 760, 1) + 0.15 * min(avg_kills / 12, 1),
        "MID": 0.32 * min(avg_kills / 13, 1) + 0.26 * min(avg_xpm / 950, 1) + 0.25 * min(avg_hero_damage / 36000, 1) + 0.17 * min(avg_last_hits / 220, 1),
        "OFF": 0.27 * min(avg_assists / 18, 1) + 0.25 * min(avg_hero_damage / 30000, 1) + 0.23 * min(avg_tower_damage / 5200, 1) + 0.25 * min((avg_kills + avg_assists) / 24, 1),
        "SUP": 0.42 * min(avg_assists / 22, 1) + 0.22 * min(avg_healing / 3500, 1) + 0.2 * max(0, 1 - avg_last_hits / 180) + 0.16 * max(0, 1 - avg_gpm / 620),
    }
    return max(scores, key=scores.get)


def weighted_overall(position: str, rows: list[dict[str, Any]]) -> int:
    values = {row["label"]: row["value"] for row in rows}
    weights = {
        "CRY": {"IMP": 0.2, "FRM": 0.25, "FGT": 0.2, "SUR": 0.1, "OBJ": 0.24, "UTL": 0.01},
        "MID": {"IMP": 0.25, "FRM": 0.18, "FGT": 0.25, "SUR": 0.12, "OBJ": 0.1, "UTL": 0.1},
        "OFF": {"IMP": 0.25, "FRM": 0.1, "FGT": 0.2, "SUR": 0.2, "OBJ": 0.15, "UTL": 0.1},
        "SUP": {"IMP": 0.25, "FRM": 0.05, "FGT": 0.1, "SUR": 0.15, "OBJ": 0.1, "UTL": 0.35},
        "FLX": {"IMP": 0.2, "FRM": 0.16, "FGT": 0.18, "SUR": 0.16, "OBJ": 0.14, "UTL": 0.16},
    }
    role_weights = weights.get(position, weights["FLX"])
    return clamp_score(sum(values[key] * weight for key, weight in role_weights.items()))


def build_card_from_averages(
    *,
    position: str,
    rank_tier: int | None,
    mode: str,
    games: int,
    wins: int,
    recent_winrate: float | None,
    avg_kills: float,
    avg_deaths: float,
    avg_assists: float,
    avg_gpm: float,
    avg_xpm: float,
    avg_hero_damage: float,
    avg_tower_damage: float,
    avg_healing: float,
    avg_last_hits: float,
) -> dict[str, Any]:
    games = max(1, games)
    winrate = wins / games * 100
    kda = (avg_kills + avg_assists) / max(1, avg_deaths)

    score = lambda value, target, metric, low=40, high=99: contextual_metric_score(value, target, metric, rank_tier, mode, position, low, high)
    impact = 0.28 * winrate + 0.28 * score(kda, 4, "kda") + 0.20 * score(avg_assists, 18, "assists") + 0.24 * score(avg_hero_damage, 28000, "heroDamage")
    farm = 0.5 * score(avg_gpm, 760, "gpm") + 0.3 * score(avg_last_hits, 260, "lastHits") + 0.2 * score(avg_xpm, 950, "xpm")
    fighting = 0.42 * score(avg_kills, 15, "kills") + 0.38 * score(avg_hero_damage, 40000, "heroDamage") + 0.2 * score(avg_assists, 20, "assists")
    survival = 0.58 * (99 - score(avg_deaths, 12, "deaths", 0, 64)) + 0.42 * score(kda, 5.0, "kda")
    objective = 0.68 * score(avg_tower_damage, 7000, "towerDamage") + 0.32 * score(avg_last_hits, 250, "lastHits")
    utility = 0.4 * score(avg_assists, 20, "assists") + 0.35 * score(avg_healing, 3500, "healing") + 0.25 * score((avg_gpm + avg_xpm) / 2, 900, "economy")
    rows = [
        {"label": "IMP", "value": clamp_score(impact)},
        {"label": "FRM", "value": clamp_score(farm)},
        {"label": "FGT", "value": clamp_score(fighting)},
        {"label": "SUR", "value": clamp_score(survival)},
        {"label": "OBJ", "value": clamp_score(objective)},
        {"label": "UTL", "value": clamp_score(utility)},
    ]
    overall = weighted_overall(position, rows)
    return {
        "overall": overall,
        "position": position,
        "rows": rows,
        "source": {
            "games": games,
            "mode": mode,
            "benchmarkMedal": rank_medal(rank_tier)["medal"],
            "benchmarkRole": position,
            "winrate": round(winrate, 1),
            "recentWinrate": round(recent_winrate, 1) if recent_winrate is not None else None,
            "avgKills": round(avg_kills, 1),
            "avgDeaths": round(avg_deaths, 1),
            "avgAssists": round(avg_assists, 1),
            "avgGpm": round(avg_gpm, 1),
            "avgXpm": round(avg_xpm, 1),
            "avgHeroDamage": round(avg_hero_damage),
            "avgTowerDamage": round(avg_tower_damage),
            "avgHealing": round(avg_healing),
            "avgLastHits": round(avg_last_hits, 1),
            "roleWeights": position,
        },
    }


def build_card_for_stat_rows(
    stats: list[dict[str, Any]],
    *,
    position: str,
    rank_tier: int | None,
    mode: str,
    recent_winrate: float | None = None,
) -> dict[str, Any]:
    games = max(1, len(stats))
    return build_card_from_averages(
        position=position,
        rank_tier=rank_tier,
        mode=mode,
        games=games,
        wins=sum(1 for item in stats if item["win"]),
        recent_winrate=recent_winrate,
        avg_kills=sum(item["kills"] for item in stats) / games,
        avg_deaths=sum(item["deaths"] for item in stats) / games,
        avg_assists=sum(item["assists"] for item in stats) / games,
        avg_gpm=sum(item["gpm"] for item in stats) / games,
        avg_xpm=sum(item["xpm"] for item in stats) / games,
        avg_hero_damage=sum(item["heroDamage"] for item in stats) / games,
        avg_tower_damage=sum(item["towerDamage"] for item in stats) / games,
        avg_healing=sum(item["healing"] for item in stats) / games,
        avg_last_hits=sum(item["lastHits"] for item in stats) / games,
    )


def merge_mode_cards(position: str, cards: list[dict[str, Any]], source: dict[str, Any]) -> dict[str, Any]:
    total_games = sum(card["source"]["games"] for card in cards)
    rows = []
    for label in ("IMP", "FRM", "FGT", "SUR", "OBJ", "UTL"):
        value = sum(
            next(row["value"] for row in card["rows"] if row["label"] == label) * card["source"]["games"]
            for card in cards
        ) / max(1, total_games)
        rows.append({"label": label, "value": clamp_score(value)})
    source = {
        **source,
        "mode": "mixed" if len(cards) > 1 else cards[0]["source"]["mode"],
        "modeBreakdown": [
            {"mode": card["source"]["mode"], "games": card["source"]["games"]}
            for card in cards
        ],
    }
    return {"overall": weighted_overall(position, rows), "position": position, "rows": rows, "source": source}


def build_card(
    conn: sqlite3.Connection,
    player: dict[str, Any],
    matches: list[sqlite3.Row],
    position_override: str | None = None,
) -> dict[str, Any]:
    stats = detailed_match_stats(conn, int(player["accountId"]), matches)
    position = position_override or infer_position(stats)
    recent = matches[:10]
    source_card = build_card_for_stat_rows(
        stats,
        position=position,
        rank_tier=player.get("rankTier"),
        mode="normal",
        recent_winrate=sum(1 for row in recent if is_win(row)) / max(1, len(recent)) * 100,
    )
    by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in stats:
        by_mode["turbo" if item["gameMode"] == 23 else "normal"].append(item)
    mode_cards = [
        build_card_for_stat_rows(group, position=position, rank_tier=player.get("rankTier"), mode=mode)
        for mode, group in by_mode.items()
    ]
    return merge_mode_cards(position, mode_cards, source_card["source"])


def endpoint_payload(conn: sqlite3.Connection, account_id: int, endpoint: str, default: Any) -> Any:
    row = conn.execute(
        "SELECT raw_json FROM raw_player_endpoints WHERE account_id = ? AND endpoint = ?",
        (account_id, endpoint),
    ).fetchone()
    return load_json(row["raw_json"], default) if row else default


def load_role_overrides() -> dict[int, str]:
    if not ROLE_OVERRIDES_PATH.exists():
        return {}
    payload = load_json(ROLE_OVERRIDES_PATH.read_text(encoding="utf-8"), {})
    valid_roles = {"CRY", "MID", "OFF", "SUP", "FLX"}
    return {
        int(account_id): role
        for account_id, role in payload.items()
        if str(account_id).isdigit() and role in valid_roles
    }


def infer_all_time_position(lane_counts: dict[str, Any], avg_last_hits: float, stats: dict[str, float]) -> str:
    lanes = [
        (int(lane), int(values.get("games") or 0))
        for lane, values in lane_counts.items()
        if lane in {"1", "2", "3", "4"} and isinstance(values, dict)
    ]
    if lanes:
        lane = max(lanes, key=lambda entry: entry[1])[0]
        if lane == 2:
            return "MID"
        if lane == 4:
            return "SUP"
        if lane == 3:
            return "OFF" if avg_last_hits >= 100 else "SUP"
        return "CRY" if avg_last_hits >= 130 else "SUP"

    return infer_position(
        [{
            "laneRole": None,
            "lastHits": avg_last_hits,
            "gpm": stats["gpm"],
            "kills": stats["kills"],
            "xpm": stats["xpm"],
            "heroDamage": stats["heroDamage"],
            "towerDamage": stats["towerDamage"],
            "assists": stats["assists"],
            "healing": stats["healing"],
        }]
    )


CARD_TOTAL_FIELDS = {
    "kills": "kills",
    "deaths": "deaths",
    "assists": "assists",
    "gpm": "gold_per_min",
    "xpm": "xp_per_min",
    "heroDamage": "hero_damage",
    "towerDamage": "tower_damage",
    "healing": "hero_healing",
    "lastHits": "last_hits",
}


def average_total_stats(totals: list[dict[str, Any]]) -> dict[str, float]:
    by_field = {item.get("field"): item for item in totals if isinstance(item, dict)}
    result = {}
    for stat, field in CARD_TOTAL_FIELDS.items():
        item = by_field.get(field, {})
        count = item.get("n") or 0
        result[stat] = float(item.get("sum") or 0) / count if count else 0.0
    return result


def subtract_totals(all_totals: list[dict[str, Any]], turbo_totals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    all_by_field = {item.get("field"): item for item in all_totals if isinstance(item, dict)}
    turbo_by_field = {item.get("field"): item for item in turbo_totals if isinstance(item, dict)}
    return [
        {
            "field": field,
            "n": max(0, int((item or {}).get("n") or 0) - int(turbo_by_field.get(field, {}).get("n") or 0)),
            "sum": float((item or {}).get("sum") or 0) - float(turbo_by_field.get(field, {}).get("sum") or 0),
        }
        for field, item in all_by_field.items()
    ]


def build_all_time_card(
    conn: sqlite3.Connection,
    account_id: int,
    rank_tier: int | None,
    position_override: str | None = None,
) -> dict[str, Any]:
    """Build a card from OpenDota's all-time normal/Turbo aggregates."""
    totals = endpoint_payload(conn, account_id, "totals", [])
    wl = endpoint_payload(conn, account_id, "wl", {})
    counts = endpoint_payload(conn, account_id, "counts", {})
    turbo_totals = endpoint_payload(conn, account_id, "totalsTurbo", [])
    turbo_wl = endpoint_payload(conn, account_id, "wlTurbo", {})
    stats = average_total_stats(totals)
    position = position_override or infer_all_time_position(counts.get("lane_role", {}), stats["lastHits"], stats)
    wins = int(wl.get("win") or 0)
    losses = int(wl.get("lose") or 0)

    source_card = build_card_from_averages(
        position=position,
        rank_tier=rank_tier,
        mode="normal",
        games=wins + losses,
        wins=wins,
        recent_winrate=None,
        avg_kills=stats["kills"],
        avg_deaths=stats["deaths"],
        avg_assists=stats["assists"],
        avg_gpm=stats["gpm"],
        avg_xpm=stats["xpm"],
        avg_hero_damage=stats["heroDamage"],
        avg_tower_damage=stats["towerDamage"],
        avg_healing=stats["healing"],
        avg_last_hits=stats["lastHits"],
    )

    turbo_games = int(turbo_wl.get("win") or 0) + int(turbo_wl.get("lose") or 0)
    if not turbo_totals or turbo_games <= 0:
        return merge_mode_cards(position, [source_card], source_card["source"])

    normal_totals = subtract_totals(totals, turbo_totals)
    normal_stats = average_total_stats(normal_totals)
    normal_wins = max(0, wins - int(turbo_wl.get("win") or 0))
    normal_losses = max(0, losses - int(turbo_wl.get("lose") or 0))
    turbo_stats = average_total_stats(turbo_totals)
    mode_cards = []
    if normal_wins + normal_losses:
        mode_cards.append(
            build_card_from_averages(
                position=position,
                rank_tier=rank_tier,
                mode="normal",
                games=normal_wins + normal_losses,
                wins=normal_wins,
                recent_winrate=None,
                avg_kills=normal_stats["kills"], avg_deaths=normal_stats["deaths"], avg_assists=normal_stats["assists"],
                avg_gpm=normal_stats["gpm"], avg_xpm=normal_stats["xpm"], avg_hero_damage=normal_stats["heroDamage"],
                avg_tower_damage=normal_stats["towerDamage"], avg_healing=normal_stats["healing"], avg_last_hits=normal_stats["lastHits"],
            )
        )
    mode_cards.append(
        build_card_from_averages(
            position=position,
            rank_tier=rank_tier,
            mode="turbo",
            games=turbo_games,
            wins=int(turbo_wl.get("win") or 0),
            recent_winrate=None,
            avg_kills=turbo_stats["kills"], avg_deaths=turbo_stats["deaths"], avg_assists=turbo_stats["assists"],
            avg_gpm=turbo_stats["gpm"], avg_xpm=turbo_stats["xpm"], avg_hero_damage=turbo_stats["heroDamage"],
            avg_tower_damage=turbo_stats["towerDamage"], avg_healing=turbo_stats["healing"], avg_last_hits=turbo_stats["lastHits"],
        )
    )
    return merge_mode_cards(position, mode_cards, source_card["source"])


def profile_for(conn: sqlite3.Connection, account_id: int) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT raw_json
        FROM raw_player_endpoints
        WHERE account_id = ? AND endpoint = 'profile'
        """,
        (account_id,),
    ).fetchone()
    payload = load_json(row["raw_json"], {}) if row else {}
    profile = payload.get("profile") or payload
    return {
        "accountId": account_id,
        "name": profile.get("personaname") or f"Player {account_id}",
        "avatar": profile.get("avatarfull") or profile.get("avatarmedium") or profile.get("avatar"),
        "rankTier": payload.get("rank_tier"),
        "leaderboardRank": payload.get("leaderboard_rank"),
        "computedMmr": payload.get("computed_mmr"),
    }


def load_player_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM player_match_index
        ORDER BY start_time DESC, match_id DESC
        """
    ).fetchall()


def build_players(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    by_player: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_player[int(row["account_id"])].append(row)

    role_overrides = load_role_overrides()
    players = []
    for account_id in sorted(by_player):
        matches = by_player[account_id]
        wins = sum(1 for row in matches if is_win(row))
        kills = sum(row["kills"] or 0 for row in matches)
        deaths = sum(row["deaths"] or 0 for row in matches)
        assists = sum(row["assists"] or 0 for row in matches)
        profile = profile_for(conn, account_id)
        profile.update(
            {
                "matches": len(matches),
                "wins": wins,
                "losses": len(matches) - wins,
                "winRate": round(wins / len(matches) * 100, 1) if matches else 0,
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "kda": round((kills + assists) / max(1, deaths), 2),
            }
        )
        profile["medal"] = rank_medal(profile.get("rankTier"))
        role_override = role_overrides.get(account_id)
        profile["roleOverride"] = role_override
        profile["card"] = build_card(conn, profile, matches, role_override)
        profile["allTimeCard"] = build_all_time_card(conn, account_id, profile.get("rankTier"), role_override)
        players.append(profile)
    return players


def attach_profile_data(
    conn: sqlite3.Connection,
    players: list[dict[str, Any]],
    rows: list[sqlite3.Row],
    constants: dict[str, Any],
) -> None:
    """Attach player-owned feed and match history for the Reborn-style profile page."""
    match_meta = {
        int(row["match_id"]): row
        for row in conn.execute("SELECT match_id, duration FROM raw_matches").fetchall()
    }
    by_player: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_player[int(row["account_id"])].append(row)

    for player in players:
        player_rows = by_player[player["accountId"]]
        recent_games = []
        for row in player_rows[:20]:
            meta = match_meta.get(int(row["match_id"]))
            recent_games.append(
                {
                    "matchId": row["match_id"],
                    "startedAt": iso_from_ts(row["start_time"]),
                    "heroName": hero_name(row["hero_id"], constants),
                    "heroImage": hero_image(row["hero_id"], constants, "portrait"),
                    "result": "WIN" if is_win(row) else "LOSS",
                    "durationLabel": duration_label(meta["duration"] if meta else None),
                    "modeName": game_mode_name(row["game_mode"], constants),
                    "lobbyTypeName": lobby_type_name(row["lobby_type"], constants),
                    "kills": row["kills"] or 0,
                    "deaths": row["deaths"] or 0,
                    "assists": row["assists"] or 0,
                }
            )
        first_match = min((row["start_time"] for row in player_rows if row["start_time"]), default=None)
        player["profile"] = {
            "firstMatchAt": iso_from_ts(first_match),
            "recentGames": recent_games,
            "activityFeed": build_feed(player_rows, players, constants),
        }


def build_leaderboard(players: list[dict[str, Any]], rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    latest_by_player: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        latest_by_player[int(row["account_id"])].append(row)

    ranking = sorted(players, key=lambda p: (p["wins"], p["winRate"], p["kda"]), reverse=True)
    result = []
    for place, player in enumerate(ranking, 1):
        recent = latest_by_player[player["accountId"]][:5]
        form = ["W" if is_win(row) else "L" for row in recent]
        result.append(
            {
                "rank": place,
                "accountId": player["accountId"],
                "name": player["name"],
                "avatar": player["avatar"],
                "matches": player["matches"],
                "wins": player["wins"],
                "losses": player["losses"],
                "winRate": player["winRate"],
                "kda": player["kda"],
                "form": form,
            }
        )
    return result


def build_squad_pulse(
    rows: list[sqlite3.Row], leaderboard: list[dict[str, Any]], constants: dict[str, Any]
) -> dict[str, Any]:
    wins = sum(1 for row in rows if is_win(row))
    losses = len(rows) - wins
    turbo = sum(1 for row in rows if row["game_mode"] == 23)
    best = leaderboard[0] if leaderboard else None
    cursed_counter = Counter(row["hero_id"] for row in rows if not is_win(row) and row["hero_id"] is not None)
    cursed_hero_id = cursed_counter.most_common(1)[0][0] if cursed_counter else None
    return {
        "record": {"wins": wins, "losses": losses, "label": f"{wins}W-{losses}L"},
        "trackedPlayerMatches": len(rows),
        "turboMatches": turbo,
        "bestPerformer": best,
        "cursedPick": {
            "heroId": cursed_hero_id,
            "heroName": hero_name(cursed_hero_id, constants),
            "heroImage": hero_image(cursed_hero_id, constants),
            "losses": cursed_counter.get(cursed_hero_id, 0) if cursed_hero_id is not None else 0,
        },
    }


def build_recent_games(conn: sqlite3.Connection, constants: dict[str, Any]) -> list[dict[str, Any]]:
    matches = conn.execute(
        """
        SELECT *
        FROM raw_matches
        ORDER BY start_time DESC
        LIMIT 20
        """
    ).fetchall()
    games = []
    for match in matches:
        player_rows = conn.execute(
            """
            SELECT *
            FROM player_match_index
            WHERE match_id = ?
            ORDER BY player_slot
            """,
            (match["match_id"],),
        ).fetchall()
        tracked = []
        result_wins = 0
        for row in player_rows:
            profile = profile_for(conn, int(row["account_id"]))
            won = is_win(row)
            result_wins += int(won)
            tracked.append(
                {
                    "accountId": row["account_id"],
                    "name": profile["name"],
                    "avatar": profile["avatar"],
                    "heroId": row["hero_id"],
                    "heroName": hero_name(row["hero_id"], constants),
                    "heroImage": hero_image(row["hero_id"], constants),
                    "kills": row["kills"] or 0,
                    "deaths": row["deaths"] or 0,
                    "assists": row["assists"] or 0,
                    "won": won,
                }
            )
        game_mode = player_rows[0]["game_mode"] if player_rows else None
        raw = load_json(match["raw_json"], {})
        games.append(
            {
                "matchId": match["match_id"],
                "startedAt": iso_from_ts(match["start_time"]),
                "duration": match["duration"],
                "durationLabel": duration_label(match["duration"]),
                "mode": game_mode,
                "modeName": game_mode_name(game_mode, constants),
                "lobbyType": player_rows[0]["lobby_type"] if player_rows else None,
                "lobbyTypeName": lobby_type_name(player_rows[0]["lobby_type"], constants) if player_rows else "Unknown",
                "radiantWin": bool(match["radiant_win"]) if match["radiant_win"] is not None else None,
                "radiantScore": raw.get("radiant_score"),
                "direScore": raw.get("dire_score"),
                "trackedPlayers": tracked,
                "heroes": [
                    {
                        "heroId": player["heroId"],
                        "heroName": player["heroName"],
                        "heroImage": player["heroImage"],
                    }
                    for player in tracked
                ],
                "result": "WIN" if result_wins >= max(1, len(tracked) / 2) else "LOSS",
                "highlight": max(tracked, key=lambda p: (p["kills"] + p["assists"], -p["deaths"])) if tracked else None,
            }
        )
    return games


def build_squad_meta(rows: list[sqlite3.Row], constants: dict[str, Any]) -> dict[str, Any]:
    hero_counts = Counter(row["hero_id"] for row in rows if row["hero_id"] is not None)
    hero_wins: Counter[int] = Counter()
    hero_games: Counter[int] = Counter()
    for row in rows:
        hero_id = row["hero_id"]
        if hero_id is None:
            continue
        hero_games[hero_id] += 1
        if is_win(row):
            hero_wins[hero_id] += 1

    most_picked_id = hero_counts.most_common(1)[0][0] if hero_counts else None
    qualified = [hero_id for hero_id, games in hero_games.items() if games >= 2]
    best_id = max(qualified, key=lambda h: (hero_wins[h] / hero_games[h], hero_games[h]), default=None)
    cursed_id = min(qualified, key=lambda h: (hero_wins[h] / hero_games[h], -hero_games[h]), default=None)
    fastest_win = min((row for row in rows if is_win(row)), key=lambda row: load_json(row["raw_json"], {}).get("duration", 10**9), default=None)

    def hero_stat(hero_id: int | None) -> dict[str, Any]:
        games = hero_games.get(hero_id, 0) if hero_id is not None else 0
        wins = hero_wins.get(hero_id, 0) if hero_id is not None else 0
        return {
            "heroId": hero_id,
            "heroName": hero_name(hero_id, constants),
            "heroImage": hero_image(hero_id, constants),
            "games": games,
            "wins": wins,
            "winRate": round(wins / games * 100, 1) if games else 0,
        }

    fastest_payload = load_json(fastest_win["raw_json"], {}) if fastest_win else {}
    return {
        "mostPickedHero": hero_stat(most_picked_id),
        "bestHero": hero_stat(best_id),
        "cursedHero": hero_stat(cursed_id),
        "fastestWin": {
            "matchId": fastest_win["match_id"] if fastest_win else None,
            "duration": fastest_payload.get("duration"),
            "durationLabel": duration_label(fastest_payload.get("duration")),
            "heroName": hero_name(fastest_win["hero_id"], constants) if fastest_win else None,
        },
    }


def build_feed(rows: list[sqlite3.Row], players: list[dict[str, Any]], constants: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = {player["accountId"]: player for player in players}
    events = []
    for row in sorted(rows, key=lambda item: item["start_time"], reverse=True):
        player = profiles.get(row["account_id"], {"name": f"Player {row['account_id']}", "avatar": None})
        kills = row["kills"] or 0
        deaths = row["deaths"] or 0
        assists = row["assists"] or 0
        if deaths >= 10:
            message = f"{player['name']} died {deaths} times and still called it space creation"
            kind = "lowlight"
        elif kills >= 15:
            message = f"{player['name']} dropped {kills} kills on {hero_name(row['hero_id'], constants)}"
            kind = "highlight"
        elif assists >= 30:
            message = f"{player['name']} farmed {assists} assists and pretended it was charity"
            kind = "support"
        else:
            continue
        events.append(
            {
                "type": kind,
                "severity": "high" if deaths >= 12 or kills >= 18 else "medium",
                "accountId": row["account_id"],
                "player": player["name"],
                "avatar": player.get("avatar"),
                "matchId": row["match_id"],
                "message": message,
                "icon": "skull" if kind == "lowlight" else "crown" if kind == "highlight" else "eye",
                "createdAt": iso_from_ts(row["start_time"]),
                "stats": {"kills": kills, "deaths": deaths, "assists": assists},
            }
        )
        if len(events) >= 8:
            break
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dashboard JSON from SQLite and cached OpenDota constants.")
    parser.add_argument("--refresh-constants", action="store_true", help="Re-download OpenDota constants before building.")
    args = parser.parse_args()

    conn = connect()
    constants = load_constants(refresh=args.refresh_constants)
    rows = load_player_rows(conn)
    players = build_players(conn, rows)
    attach_profile_data(conn, players, rows, constants)
    leaderboard = build_leaderboard(players, rows)
    raw_match_count = conn.execute("SELECT COUNT(*) FROM raw_matches").fetchone()[0]
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "api": SOURCE_URL,
            "database": DB_PATH.relative_to(ROOT).as_posix(),
        },
        "summary": {
            "trackedPlayers": len(players),
            "playerMatches": len(rows),
            "rawMatches": raw_match_count,
            "constants": sorted(CONSTANT_RESOURCES),
        },
        "players": players,
        "squadPulse": build_squad_pulse(rows, leaderboard, constants),
        "leaderboard": leaderboard,
        "recentPartyGames": build_recent_games(conn, constants),
        "squadMeta": build_squad_meta(rows, constants),
        "feed": build_feed(rows, players, constants),
    }

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH.relative_to(ROOT)}")
    print(
        f"players={len(players)} player_matches={len(rows)} "
        f"raw_matches={raw_match_count} recent_games={len(payload['recentPartyGames'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
