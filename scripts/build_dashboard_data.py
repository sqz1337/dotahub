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
MATCHES_OUTPUT_PATH = ROOT / "data" / "matches.json"
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

CONSTANT_RESOURCES = ("heroes", "items", "game_mode", "lobby_type")

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

# Turbo awards accelerated passive gold/XP and its games are shorter. Convert
# the three farm inputs back to normal-match equivalents before rating FRM.
# This keeps 900-1000 Turbo GPM for a support near 350-420 normal GPM instead
# of turning it into an elite farming score.
TURBO_FARM_EQUIVALENCE = {
    "gpm": 2.4,
    "xpm": 3.0,
    "lastHits": 0.75,
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

CARD_ROLE_WEIGHTS = {
    "CRY": {"IMP": 0.2, "FRM": 0.25, "FGT": 0.2, "SUR": 0.1, "OBJ": 0.24, "UTL": 0.01},
    "MID": {"IMP": 0.25, "FRM": 0.18, "FGT": 0.25, "SUR": 0.12, "OBJ": 0.1, "UTL": 0.1},
    "OFF": {"IMP": 0.25, "FRM": 0.1, "FGT": 0.2, "SUR": 0.2, "OBJ": 0.15, "UTL": 0.1},
    "SUP": {"IMP": 0.25, "FRM": 0.05, "FGT": 0.1, "SUR": 0.15, "OBJ": 0.1, "UTL": 0.35},
    "FLX": {"IMP": 0.2, "FRM": 0.16, "FGT": 0.18, "SUR": 0.16, "OBJ": 0.14, "UTL": 0.16},
}

SEASON_START_AT = datetime(2026, 7, 1, tzinfo=timezone.utc)
SEASON_START_TS = int(SEASON_START_AT.timestamp())
SEASON_START_MMR = 3000


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_derived_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS recent_player_matches (
          account_id INTEGER NOT NULL,
          match_id INTEGER NOT NULL,
          ordinal INTEGER NOT NULL,
          synced_at TEXT NOT NULL,
          PRIMARY KEY (account_id, match_id)
        );

        CREATE TABLE IF NOT EXISTS recent_sync_state (
          account_id INTEGER PRIMARY KEY,
          synced_at TEXT NOT NULL,
          match_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS season_mmr_events (
          account_id INTEGER NOT NULL,
          match_id INTEGER NOT NULL,
          start_time INTEGER NOT NULL,
          mode TEXT NOT NULL,
          result TEXT NOT NULL,
          impact_score REAL NOT NULL,
          impact_factor REAL NOT NULL,
          impact_axes TEXT NOT NULL,
          mmr_change INTEGER NOT NULL,
          mmr_after INTEGER NOT NULL,
          position TEXT NOT NULL,
          computed_at TEXT NOT NULL,
          PRIMARY KEY (account_id, match_id)
        );

        CREATE INDEX IF NOT EXISTS idx_recent_player_matches_match
          ON recent_player_matches (match_id);
        """
    )

    # Existing databases predate the rolling recent-match table. Seed it once
    # from the newest indexed games so a standalone build remains safe.
    account_ids = [int(row[0]) for row in conn.execute("SELECT account_id FROM tracked_players ORDER BY account_id")]
    seeded_at = now_utc_iso()
    for account_id in account_ids:
        exists = conn.execute(
            "SELECT 1 FROM recent_sync_state WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if exists:
            continue
        rows = conn.execute(
            """
            SELECT match_id
            FROM player_match_index
            WHERE account_id = ? AND start_time >= ?
            ORDER BY start_time DESC, match_id DESC
            LIMIT 20
            """,
            (account_id, SEASON_START_TS),
        ).fetchall()
        for ordinal, row in enumerate(rows):
            conn.execute(
                "INSERT OR IGNORE INTO recent_player_matches (account_id, match_id, ordinal, synced_at) VALUES (?, ?, ?, ?)",
                (account_id, int(row["match_id"]), ordinal, seeded_at),
            )
        conn.execute(
            "INSERT INTO recent_sync_state (account_id, synced_at, match_count) VALUES (?, ?, ?)",
            (account_id, seeded_at, len(rows)),
        )
    conn.commit()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def purge_preseason_matches(conn: sqlite3.Connection) -> tuple[int, int]:
    old_match_ids = [
        int(row["match_id"])
        for row in conn.execute("SELECT match_id FROM raw_matches WHERE start_time < ?", (SEASON_START_TS,)).fetchall()
    ]
    if old_match_ids:
        placeholders = ",".join("?" for _ in old_match_ids)
        conn.execute(f"DELETE FROM match_players WHERE match_id IN ({placeholders})", tuple(old_match_ids))
        conn.execute(f"DELETE FROM raw_matches WHERE match_id IN ({placeholders})", tuple(old_match_ids))

    old_links = int(
        conn.execute(
            "SELECT COUNT(*) FROM player_match_index WHERE start_time < ?",
            (SEASON_START_TS,),
        ).fetchone()[0]
    )
    conn.execute(
        """
        DELETE FROM recent_player_matches
        WHERE EXISTS (
          SELECT 1 FROM player_match_index p
          WHERE p.account_id = recent_player_matches.account_id
            AND p.match_id = recent_player_matches.match_id
            AND p.start_time < ?
        )
        """,
        (SEASON_START_TS,),
    )
    conn.execute("DELETE FROM player_match_index WHERE start_time < ?", (SEASON_START_TS,))
    conn.execute("DELETE FROM season_mmr_events WHERE start_time < ?", (SEASON_START_TS,))
    conn.execute(
        """
        UPDATE recent_sync_state
        SET match_count = (
          SELECT COUNT(*) FROM recent_player_matches recent
          WHERE recent.account_id = recent_sync_state.account_id
        )
        """
    )

    for row in conn.execute(
        "SELECT account_id, raw_json FROM raw_player_endpoints WHERE endpoint = 'recentMatches'"
    ).fetchall():
        payload = load_json(row["raw_json"], [])
        if not isinstance(payload, list):
            continue
        filtered = [match for match in payload if int(match.get("start_time") or 0) >= SEASON_START_TS][:20]
        conn.execute(
            "UPDATE raw_player_endpoints SET raw_json = ? WHERE account_id = ? AND endpoint = 'recentMatches'",
            (json.dumps(filtered, ensure_ascii=False, sort_keys=True, separators=(",", ":")), int(row["account_id"])),
        )
    conn.commit()
    return old_links, len(old_match_ids)


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
    # OpenDota ships /constants/items keyed by internal name ("blink"), while
    # match payloads reference items by numeric id. Re-key by id so
    # constant_by_id can resolve item_0..item_5 and item_neutral slots.
    items = constants.get("items")
    if isinstance(items, dict):
        constants["items"] = {
            str(item["id"]): {"name": name, **item}
            for name, item in items.items()
            if isinstance(item, dict) and item.get("id")
        }
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
    # Hero constants only carry "img" (full portrait) and "icon" (tiny pixel
    # minimap icon); map the semantic "portrait" kind onto the full image.
    key = "img" if kind == "portrait" else kind
    path = hero.get(key) or hero.get("icon") or hero.get("img")
    if not path:
        return None
    return f"{STEAM_CDN}{path.rstrip('?')}"


def item_payload(item_id: int | None, constants: dict[str, Any]) -> dict[str, Any] | None:
    if not item_id:
        return None
    item = constant_by_id(constants, "items", item_id)
    if not item:
        return {"id": item_id, "name": f"Item {item_id}", "image": None}
    path = item.get("img")
    return {
        "id": item_id,
        "name": item.get("dname") or prettify_constant_name(item.get("name"), "item_"),
        "image": f"{STEAM_CDN}{path.rstrip('?')}" if path else None,
    }


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


def farm_metric_score(value: float, target: float, metric: str, rank_tier: int | None, mode: str) -> int:
    """Rate farm on one normal-game scale, independent of the player's role."""
    medal = rank_medal(rank_tier)["medal"]
    normalized = value
    if mode == "turbo":
        normalized /= TURBO_FARM_EQUIVALENCE[metric]
    return metric_score(normalized, target * RANK_TARGET_MULTIPLIERS.get(medal, RANK_TARGET_MULTIPLIERS[5]))


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


def build_match_impact_contexts(conn: sqlite3.Connection) -> dict[int, list[dict[str, Any]]]:
    """Load the ten-player scoreboards used for stable within-match percentiles."""
    by_match: dict[int, list[dict[str, Any]]] = defaultdict(list)
    rows = conn.execute(
        """
        SELECT mp.*
        FROM match_players mp
        JOIN raw_matches rm ON rm.match_id = mp.match_id
        WHERE rm.start_time >= ?
        ORDER BY mp.match_id, mp.player_slot
        """,
        (SEASON_START_TS,),
    ).fetchall()
    for row in rows:
        raw = load_json(row["raw_json"], {})
        obs = raw.get("obs_placed")
        sentries = raw.get("sen_placed")
        wards = None if obs is None and sentries is None else float(obs or 0) + float(sentries or 0)
        stuns = raw.get("stuns")
        by_match[int(row["match_id"])].append(
            {
                "playerSlot": int(row["player_slot"]),
                "team": "radiant" if int(row["player_slot"]) < 128 else "dire",
                "kills": float(row["kills"] or 0),
                "deaths": float(row["deaths"] or 0),
                "assists": float(row["assists"] or 0),
                "gpm": float(row["gold_per_min"] or 0),
                "xpm": float(row["xp_per_min"] or 0),
                "heroDamage": float(row["hero_damage"] or 0),
                "towerDamage": float(row["tower_damage"] or 0),
                "healing": float(row["hero_healing"] or 0),
                "lastHits": float(row["last_hits"] or 0),
                "stuns": float(stuns) if isinstance(stuns, (int, float)) else None,
                "wards": wards,
            }
        )

    for players in by_match.values():
        for player in players:
            teammates = [item for item in players if item["team"] == player["team"]]
            team_kills = sum(item["kills"] for item in teammates)
            team_damage = sum(item["heroDamage"] for item in teammates)
            player["killParticipation"] = min(1.0, (player["kills"] + player["assists"]) / max(1.0, team_kills))
            player["damageShare"] = player["heroDamage"] / max(1.0, team_damage)
            player["kda"] = (player["kills"] + player["assists"]) / max(1.0, player["deaths"])
    return dict(by_match)


def match_percentile(players: list[dict[str, Any]], player: dict[str, Any], field: str, higher_is_better: bool = True) -> float | None:
    value = player.get(field)
    if not isinstance(value, (int, float)):
        return None
    values = [item[field] for item in players if isinstance(item.get(field), (int, float))]
    if len(values) <= 1:
        return 50.0
    if not higher_is_better:
        value = -value
        values = [-item for item in values]
    below = sum(1 for item in values if item < value)
    tied = sum(1 for item in values if item == value)
    return 100.0 * (below + 0.5 * (tied - 1)) / (len(values) - 1)


def weighted_available(scores: list[tuple[float | None, float]]) -> float:
    available = [(score, weight) for score, weight in scores if score is not None]
    total_weight = sum(weight for _, weight in available)
    if total_weight <= 0:
        return 50.0
    return sum(float(score) * weight for score, weight in available) / total_weight


def calculate_match_impact(players: list[dict[str, Any]] | None, player_slot: int | None, position: str) -> tuple[float, dict[str, float]]:
    if not players or player_slot is None:
        return 50.0, {label: 50.0 for label in CARD_ROLE_WEIGHTS["FLX"]}
    player = next((item for item in players if item["playerSlot"] == int(player_slot)), None)
    if player is None:
        return 50.0, {label: 50.0 for label in CARD_ROLE_WEIGHTS["FLX"]}

    pct = lambda field, higher=True: match_percentile(players, player, field, higher)
    axes = {
        "IMP": weighted_available([(pct("killParticipation"), 0.6), (pct("damageShare"), 0.4)]),
        "FRM": weighted_available([(pct("gpm"), 0.45), (pct("lastHits"), 0.3), (pct("xpm"), 0.25)]),
        "FGT": weighted_available([(pct("heroDamage"), 0.4), (pct("kills"), 0.3), (pct("assists"), 0.3)]),
        "SUR": weighted_available([(pct("deaths", False), 0.6), (pct("kda"), 0.4)]),
        "OBJ": weighted_available([(pct("towerDamage"), 1.0)]),
        "UTL": weighted_available([(pct("assists"), 0.35), (pct("healing"), 0.25), (pct("stuns"), 0.2), (pct("wards"), 0.2)]),
    }
    role_weights = CARD_ROLE_WEIGHTS.get(position, CARD_ROLE_WEIGHTS["FLX"])
    impact = sum(axes[label] * weight for label, weight in role_weights.items())
    return round(max(0.0, min(100.0, impact)), 1), {label: round(value, 1) for label, value in axes.items()}


def normalized_impact(impact_score: float) -> float:
    centered = max(-1.0, min(1.0, (impact_score - 50.0) / 35.0))
    return (1 if centered >= 0 else -1) * abs(centered) ** 1.25


def round_mmr(value: float) -> int:
    return int(value + 0.5) if value >= 0 else -int(abs(value) + 0.5)


def rated_match_mode(row: sqlite3.Row) -> str | None:
    if int(row["game_mode"] or 0) == 23:
        return "turbo"
    if int(row["lobby_type"] or 0) == 7:
        return "ranked"
    return None


def match_mmr_delta(won: bool, mode: str, impact: float) -> int:
    if mode == "turbo":
        return round_mmr((13 if won else -13) + 7 * impact)
    if won:
        return round_mmr(30 + (30 if impact >= 0 else 20) * impact)
    return round_mmr(-20 + 10 * impact)


def calculate_season_mmr(
    conn: sqlite3.Connection,
    player: dict[str, Any],
    matches: list[sqlite3.Row],
    contexts: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    current_mmr = SEASON_START_MMR
    history = []
    position = player["card"]["position"]
    cached_events = {
        int(row["match_id"]): row
        for row in conn.execute(
            "SELECT * FROM season_mmr_events WHERE account_id = ?",
            (int(player["accountId"]),),
        ).fetchall()
    }
    for row in sorted(matches, key=lambda item: (int(item["start_time"] or 0), int(item["match_id"]))):
        if int(row["start_time"] or 0) < SEASON_START_TS:
            continue
        mode = rated_match_mode(row)
        if mode is None:
            continue
        match_id = int(row["match_id"])
        context = contexts.get(match_id)
        cached = cached_events.get(match_id)
        if cached:
            impact_score = float(cached["impact_score"])
            impact = float(cached["impact_factor"])
            axes = load_json(cached["impact_axes"], {})
            delta = int(cached["mmr_change"])
        elif context:
            impact_score, axes = calculate_match_impact(context, row["player_slot"], position)
            impact = normalized_impact(impact_score)
            delta = match_mmr_delta(is_win(row), mode, impact)
        else:
            # Never invent a neutral-impact result for a match whose details
            # have not arrived yet. A later refresh will calculate and persist it.
            continue
        current_mmr = max(0, current_mmr + delta)
        result = "WIN" if is_win(row) else "LOSS"
        event = {
            "matchId": match_id,
            "startedAt": iso_from_ts(row["start_time"]),
            "mode": mode,
            "result": result,
            "impactScore": round(impact_score, 1),
            "impactFactor": round(impact, 3),
            "impactAxes": axes,
            "change": delta,
            "mmrAfter": current_mmr,
        }
        history.append(event)
        conn.execute(
            """
            INSERT INTO season_mmr_events
              (account_id, match_id, start_time, mode, result, impact_score,
               impact_factor, impact_axes, mmr_change, mmr_after, position, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, match_id) DO UPDATE SET
              start_time=excluded.start_time,
              mode=excluded.mode,
              result=excluded.result,
              impact_score=excluded.impact_score,
              impact_factor=excluded.impact_factor,
              impact_axes=excluded.impact_axes,
              mmr_change=excluded.mmr_change,
              mmr_after=excluded.mmr_after,
              position=excluded.position,
              computed_at=excluded.computed_at
            """,
            (
                int(player["accountId"]), match_id, int(row["start_time"] or 0), mode, result,
                event["impactScore"], event["impactFactor"], json.dumps(axes, ensure_ascii=False, separators=(",", ":")), delta,
                current_mmr, position, now_utc_iso(),
            ),
        )
    conn.commit()
    return {
        "startedAt": SEASON_START_AT.isoformat().replace("+00:00", "Z"),
        "startMmr": SEASON_START_MMR,
        "currentMmr": current_mmr,
        "change": current_mmr - SEASON_START_MMR,
        "ratedMatches": len(history),
        "history": history,
    }


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
    role_weights = CARD_ROLE_WEIGHTS.get(position, CARD_ROLE_WEIGHTS["FLX"])
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
    farm = (
        0.5 * farm_metric_score(avg_gpm, 760, "gpm", rank_tier, mode)
        + 0.3 * farm_metric_score(avg_last_hits, 260, "lastHits", rank_tier, mode)
        + 0.2 * farm_metric_score(avg_xpm, 950, "xpm", rank_tier, mode)
    )
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


def normal_equivalent_source_averages(stats: list[dict[str, Any]]) -> dict[str, float]:
    """Return display averages with Turbo economy converted to normal-game pace."""
    games = max(1, len(stats))
    return {
        "avgGpm": round(sum(
            item["gpm"] / TURBO_FARM_EQUIVALENCE["gpm"] if item["gameMode"] == 23 else item["gpm"]
            for item in stats
        ) / games, 1),
        "avgXpm": round(sum(
            item["xpm"] / TURBO_FARM_EQUIVALENCE["xpm"] if item["gameMode"] == 23 else item["xpm"]
            for item in stats
        ) / games, 1),
    }


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
    source = {**source_card["source"], **normal_equivalent_source_averages(stats)}
    return merge_mode_cards(position, mode_cards or [source_card], source)


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
        "computedMmr": SEASON_START_MMR,
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
    account_ids = [
        int(row["account_id"])
        for row in conn.execute("SELECT account_id FROM tracked_players ORDER BY account_id").fetchall()
    ]
    for account_id in account_ids:
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
        profile["card"] = build_card(conn, profile, matches[:20], role_override)
        profile["allTimeCard"] = build_all_time_card(conn, account_id, profile.get("rankTier"), role_override)
        players.append(profile)

    impact_contexts = build_match_impact_contexts(conn)
    for player in players:
        season_mmr = calculate_season_mmr(conn, player, by_player[player["accountId"]], impact_contexts)
        player["computedMmr"] = season_mmr["currentMmr"]
        player["seasonMmr"] = season_mmr
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
        mmr_by_match = {
            int(entry["matchId"]): entry
            for entry in player["seasonMmr"]["history"]
        }
        recent_games = []
        for row in player_rows[:20]:
            meta = match_meta.get(int(row["match_id"]))
            mmr_entry = mmr_by_match.get(int(row["match_id"]))
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
                    "impactScore": mmr_entry["impactScore"] if mmr_entry else None,
                    "mmrChange": mmr_entry["change"] if mmr_entry else 0,
                    "mmrAfter": mmr_entry["mmrAfter"] if mmr_entry else None,
                }
            )
        first_match = min((row["start_time"] for row in player_rows if row["start_time"]), default=None)
        player["profile"] = {
            "firstMatchAt": iso_from_ts(first_match),
            "recentGames": recent_games,
            "activityFeed": build_feed(player_rows, players, constants),
        }


def build_leaderboard(players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranking = sorted(players, key=lambda p: (p["computedMmr"], p["winRate"], p["kda"]), reverse=True)
    result = []
    for player in ranking:
        result.append(
            {
                "accountId": player["accountId"],
                "name": player["name"],
                "avatar": player["avatar"],
                "mmr": player["computedMmr"],
                "position": player["card"]["position"],
                "matches": player["matches"],
                "wins": player["wins"],
                "losses": player["losses"],
                "winRate": player["winRate"],
                "kda": player["kda"],
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


def build_match_details(
    conn: sqlite3.Connection,
    players: list[dict[str, Any]],
    constants: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build a compact static scoreboard payload for every cached recent match.

    This intentionally uses only fields available from the normal match response.
    Parsed replay logs and timelines do not leak into the page contract.
    """
    tracked_profiles = {int(player["accountId"]): player for player in players}
    contexts = build_match_impact_contexts(conn)
    result = []
    matches = conn.execute("SELECT * FROM raw_matches ORDER BY start_time DESC, match_id DESC").fetchall()

    for match in matches:
        match_id = int(match["match_id"])
        raw = load_json(match["raw_json"], {})
        indexed_rows = {
            int(row["player_slot"]): row
            for row in conn.execute(
                "SELECT * FROM player_match_index WHERE match_id = ? ORDER BY player_slot",
                (match_id,),
            ).fetchall()
        }
        mmr_events = {
            int(row["account_id"]): row
            for row in conn.execute(
                "SELECT * FROM season_mmr_events WHERE match_id = ?",
                (match_id,),
            ).fetchall()
        }
        scoreboard = []
        for ordinal, raw_player in enumerate(raw.get("players") or []):
            slot = int(raw_player.get("player_slot", ordinal if ordinal < 5 else ordinal + 123))
            indexed = indexed_rows.get(slot)
            account_id = int(indexed["account_id"]) if indexed else raw_player.get("account_id")
            account_id = int(account_id) if account_id is not None else None
            profile = tracked_profiles.get(account_id) if account_id is not None else None
            tracked = profile is not None
            event = mmr_events.get(account_id) if account_id is not None else None
            impact_score = None
            impact_axes = None
            if tracked:
                if event:
                    impact_score = round_mmr(float(event["impact_score"]))
                    impact_axes = load_json(event["impact_axes"], {})
                else:
                    calculated, impact_axes = calculate_match_impact(
                        contexts.get(match_id),
                        slot,
                        profile["card"]["position"],
                    )
                    impact_score = round_mmr(calculated)

            hero_id = int(indexed["hero_id"]) if indexed and indexed["hero_id"] is not None else raw_player.get("hero_id")
            items = [
                item_payload(raw_player.get(f"item_{index}"), constants)
                for index in range(6)
            ]
            scoreboard.append(
                {
                    "playerSlot": slot,
                    "team": "radiant" if slot < 128 else "dire",
                    "accountId": account_id,
                    "tracked": tracked,
                    "name": profile["name"] if profile else raw_player.get("personaname") or raw_player.get("name") or "Anonymous",
                    "avatar": profile.get("avatar") if profile else None,
                    "position": profile["card"]["position"] if profile else None,
                    "heroId": hero_id,
                    "heroName": hero_name(hero_id, constants),
                    "heroImage": hero_image(hero_id, constants, "portrait"),
                    "level": raw_player.get("level") or 0,
                    "kills": raw_player.get("kills") or 0,
                    "deaths": raw_player.get("deaths") or 0,
                    "assists": raw_player.get("assists") or 0,
                    "netWorth": raw_player.get("net_worth") or raw_player.get("total_gold") or 0,
                    "lastHits": raw_player.get("last_hits") or 0,
                    "denies": raw_player.get("denies") or 0,
                    "gpm": raw_player.get("gold_per_min") or 0,
                    "xpm": raw_player.get("xp_per_min") or 0,
                    "heroDamage": raw_player.get("hero_damage") or 0,
                    "heroHealing": raw_player.get("hero_healing") or 0,
                    "towerDamage": raw_player.get("tower_damage") or 0,
                    "items": items,
                    "neutralItem": item_payload(raw_player.get("item_neutral"), constants),
                    "impact": impact_score,
                    "impactAxes": impact_axes,
                    "mmrChange": int(event["mmr_change"]) if event else None,
                }
            )

        tracked_impact = [player for player in scoreboard if player["tracked"] and player["impact"] is not None]
        result.append(
            {
                "matchId": match_id,
                "startedAt": iso_from_ts(match["start_time"]),
                "duration": match["duration"] or raw.get("duration") or 0,
                "durationLabel": duration_label(match["duration"] or raw.get("duration")),
                "gameMode": raw.get("game_mode"),
                "gameModeName": game_mode_name(raw.get("game_mode"), constants),
                "lobbyType": raw.get("lobby_type"),
                "lobbyTypeName": lobby_type_name(raw.get("lobby_type"), constants),
                "radiantWin": bool(match["radiant_win"]),
                "radiantScore": raw.get("radiant_score") or 0,
                "direScore": raw.get("dire_score") or 0,
                "firstBloodTime": raw.get("first_blood_time"),
                "region": raw.get("region"),
                "patch": raw.get("patch"),
                "scoreboard": scoreboard,
                "highestImpactSlot": max(tracked_impact, key=lambda player: player["impact"])["playerSlot"] if tracked_impact else None,
            }
        )
    return result


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


def prune_match_details_to_recent(conn: sqlite3.Connection) -> tuple[int, int]:
    tracked = int(conn.execute("SELECT COUNT(*) FROM tracked_players").fetchone()[0])
    synced = int(conn.execute("SELECT COUNT(*) FROM recent_sync_state").fetchone()[0])
    recent_count = int(conn.execute("SELECT COUNT(DISTINCT match_id) FROM recent_player_matches").fetchone()[0])
    if tracked == 0 or synced < tracked or recent_count == 0:
        raise RuntimeError(
            f"Refusing to prune match details: recent sync covers {synced}/{tracked} players and {recent_count} matches."
        )

    missing_ledger = conn.execute(
        """
        SELECT p.account_id, p.match_id
        FROM player_match_index p
        JOIN raw_matches rm ON rm.match_id = p.match_id
        LEFT JOIN recent_player_matches recent
          ON recent.account_id = p.account_id AND recent.match_id = p.match_id
        LEFT JOIN season_mmr_events event
          ON event.account_id = p.account_id AND event.match_id = p.match_id
        WHERE p.start_time >= ?
          AND (p.game_mode = 23 OR p.lobby_type = 7)
          AND recent.match_id IS NULL
          AND event.match_id IS NULL
        LIMIT 1
        """,
        (SEASON_START_TS,),
    ).fetchone()
    if missing_ledger:
        raise RuntimeError(
            "Refusing to prune match details before every older rated match has an MMR ledger entry."
        )

    before = int(conn.execute("SELECT COUNT(*) FROM raw_matches").fetchone()[0])
    conn.execute(
        "DELETE FROM match_players WHERE match_id NOT IN (SELECT DISTINCT match_id FROM recent_player_matches)"
    )
    conn.execute(
        "DELETE FROM raw_matches WHERE match_id NOT IN (SELECT DISTINCT match_id FROM recent_player_matches)"
    )
    conn.commit()
    after = int(conn.execute("SELECT COUNT(*) FROM raw_matches").fetchone()[0])
    return before - after, after


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dashboard JSON from SQLite and cached OpenDota constants.")
    parser.add_argument("--refresh-constants", action="store_true", help="Re-download OpenDota constants before building.")
    parser.add_argument(
        "--prune-details",
        action="store_true",
        help="Keep detailed payloads only for each player's latest 20 matches after persisting the MMR ledger.",
    )
    args = parser.parse_args()

    conn = connect()
    migrate_derived_schema(conn)
    removed_links, removed_details = purge_preseason_matches(conn)
    if removed_links or removed_details:
        print(
            f"removed pre-season data: {removed_links} player-match links, {removed_details} detailed matches"
        )
    constants = load_constants(refresh=args.refresh_constants)
    rows = load_player_rows(conn)
    players = build_players(conn, rows)
    if args.prune_details:
        removed, remaining = prune_match_details_to_recent(conn)
        print(f"pruned {removed} old detailed matches; {remaining} recent unique matches remain")
    attach_profile_data(conn, players, rows, constants)
    leaderboard = build_leaderboard(players)
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
            "seasonStartedAt": SEASON_START_AT.isoformat().replace("+00:00", "Z"),
            "seasonStartMmr": SEASON_START_MMR,
            "constants": sorted(CONSTANT_RESOURCES),
        },
        "players": players,
        "squadPulse": build_squad_pulse(rows, leaderboard, constants),
        "leaderboard": leaderboard,
        "recentPartyGames": build_recent_games(conn, constants),
        "squadMeta": build_squad_meta(rows, constants),
        "feed": build_feed(rows, players, constants),
    }

    match_details = build_match_details(conn, players, constants)
    matches_payload = {
        "generatedAt": payload["generatedAt"],
        "source": payload["source"],
        "matches": match_details,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MATCHES_OUTPUT_PATH.write_text(
        json.dumps(matches_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH.relative_to(ROOT)}")
    print(f"wrote {MATCHES_OUTPUT_PATH.relative_to(ROOT)} ({len(match_details)} matches)")
    print(
        f"players={len(players)} player_matches={len(rows)} "
        f"raw_matches={raw_match_count} recent_games={len(payload['recentPartyGames'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
