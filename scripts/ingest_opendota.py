#!/usr/bin/env python3
"""Pull OpenDota data into a local SQLite database.

The database intentionally stores raw JSON responses first. Derived tables are
kept small and convenient, so the app can evolve without re-fetching history.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "player-ids.json"
DEFAULT_DB = ROOT / "data" / "opendota.sqlite"
BASE_URL = "https://api.opendota.com/api"
SSL_CONTEXT = ssl.create_default_context()

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass

FULL_PLAYER_ENDPOINTS = (
    "profile",
    "wl",
    "wlTurbo",
    "recentMatches",
    "totals",
    "totalsTurbo",
    "counts",
)

REGULAR_PLAYER_ENDPOINTS = ("recentMatches",)


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fetch_json(
    path: str,
    params: dict[str, Any] | None = None,
    delay: float = 1.15,
    method: str = "GET",
    attempts: int = 3,
) -> Any:
    query = dict(params or {})
    api_key = os.getenv("OPENDOTA_API_KEY")
    if api_key:
        query["api_key"] = api_key

    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"

    req = Request(url, headers={"User-Agent": "dotafifa-ingest/0.1"}, method=method)
    body = ""
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(req, timeout=60, context=SSL_CONTEXT) as response:
                body = response.read().decode("utf-8")
            break
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < attempts:
                retry_after = exc.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after and retry_after.isdigit() else 65.0
                print(f"  OpenDota rate limit reached; retrying in {wait_seconds:.0f}s", flush=True)
                time.sleep(wait_seconds)
                continue
            if exc.code < 500 or attempt == attempts:
                raise RuntimeError(f"OpenDota HTTP {exc.code} for {url}: {body[:300]}") from exc
        except (TimeoutError, socket.timeout, URLError) as exc:
            if attempt == attempts:
                raise RuntimeError(f"OpenDota request failed for {url}: {exc}") from exc
            time.sleep(2 * attempt)

    if delay:
        time.sleep(delay)

    if not body:
        return None
    return json.loads(body)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ingestion_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          since TEXT NOT NULL,
          source TEXT NOT NULL,
          player_count INTEGER NOT NULL,
          match_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tracked_players (
          account_id INTEGER PRIMARY KEY,
          added_at TEXT NOT NULL,
          label TEXT
        );

        CREATE TABLE IF NOT EXISTS raw_player_endpoints (
          account_id INTEGER NOT NULL,
          endpoint TEXT NOT NULL,
          fetched_at TEXT NOT NULL,
          since TEXT,
          request_path TEXT NOT NULL,
          request_params TEXT NOT NULL,
          raw_json TEXT NOT NULL,
          PRIMARY KEY (account_id, endpoint)
        );

        CREATE TABLE IF NOT EXISTS player_match_index (
          account_id INTEGER NOT NULL,
          match_id INTEGER NOT NULL,
          start_time INTEGER NOT NULL,
          hero_id INTEGER,
          player_slot INTEGER,
          radiant_win INTEGER,
          game_mode INTEGER,
          lobby_type INTEGER,
          kills INTEGER,
          deaths INTEGER,
          assists INTEGER,
          raw_json TEXT NOT NULL,
          PRIMARY KEY (account_id, match_id)
        );

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

        CREATE TABLE IF NOT EXISTS raw_matches (
          match_id INTEGER PRIMARY KEY,
          fetched_at TEXT NOT NULL,
          start_time INTEGER,
          duration INTEGER,
          radiant_win INTEGER,
          parsed_version INTEGER,
          raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS parse_requests (
          match_id INTEGER PRIMARY KEY,
          requested_at TEXT NOT NULL,
          job_id TEXT,
          raw_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS match_players (
          match_id INTEGER NOT NULL,
          account_id INTEGER,
          player_slot INTEGER NOT NULL,
          hero_id INTEGER,
          is_tracked INTEGER NOT NULL DEFAULT 0,
          win INTEGER,
          kills INTEGER,
          deaths INTEGER,
          assists INTEGER,
          gold_per_min INTEGER,
          xp_per_min INTEGER,
          hero_damage INTEGER,
          tower_damage INTEGER,
          hero_healing INTEGER,
          last_hits INTEGER,
          raw_json TEXT NOT NULL,
          PRIMARY KEY (match_id, player_slot)
        );

        CREATE INDEX IF NOT EXISTS idx_player_match_index_start
          ON player_match_index (start_time);
        CREATE INDEX IF NOT EXISTS idx_match_players_account
          ON match_players (account_id);
        CREATE INDEX IF NOT EXISTS idx_recent_player_matches_match
          ON recent_player_matches (match_id);
        """
    )
    conn.commit()


def purge_matches_before(conn: sqlite3.Connection, since_ts: int) -> tuple[int, int]:
    old_match_ids = [
        int(row["match_id"])
        for row in conn.execute("SELECT match_id FROM raw_matches WHERE start_time < ?", (since_ts,)).fetchall()
    ]
    if old_match_ids:
        placeholders = ",".join("?" for _ in old_match_ids)
        conn.execute(f"DELETE FROM match_players WHERE match_id IN ({placeholders})", tuple(old_match_ids))
        conn.execute(f"DELETE FROM raw_matches WHERE match_id IN ({placeholders})", tuple(old_match_ids))

    old_links = int(
        conn.execute("SELECT COUNT(*) FROM player_match_index WHERE start_time < ?", (since_ts,)).fetchone()[0]
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
        (since_ts,),
    )
    conn.execute("DELETE FROM player_match_index WHERE start_time < ?", (since_ts,))
    conn.execute(
        """
        UPDATE recent_sync_state
        SET match_count = (
          SELECT COUNT(*) FROM recent_player_matches recent
          WHERE recent.account_id = recent_sync_state.account_id
        )
        """
    )

    has_ledger = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='season_mmr_events'"
    ).fetchone()
    if has_ledger:
        conn.execute("DELETE FROM season_mmr_events WHERE start_time < ?", (since_ts,))

    for row in conn.execute(
        "SELECT account_id, raw_json FROM raw_player_endpoints WHERE endpoint = 'recentMatches'"
    ).fetchall():
        payload = json.loads(row["raw_json"])
        if not isinstance(payload, list):
            continue
        filtered = [match for match in payload if int(match.get("start_time") or 0) >= since_ts][:20]
        conn.execute(
            "UPDATE raw_player_endpoints SET raw_json = ? WHERE account_id = ? AND endpoint = 'recentMatches'",
            (json_dumps(filtered), int(row["account_id"])),
        )
    conn.commit()
    return old_links, len(old_match_ids)


def upsert_raw_endpoint(
    conn: sqlite3.Connection,
    account_id: int,
    endpoint: str,
    path: str,
    params: dict[str, Any],
    since: str | None,
    payload: Any,
) -> None:
    conn.execute(
        """
        INSERT INTO raw_player_endpoints
          (account_id, endpoint, fetched_at, since, request_path, request_params, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, endpoint) DO UPDATE SET
          fetched_at=excluded.fetched_at,
          since=excluded.since,
          request_path=excluded.request_path,
          request_params=excluded.request_params,
          raw_json=excluded.raw_json
        """,
        (
            account_id,
            endpoint,
            now_utc().isoformat(),
            since,
            path,
            json_dumps(params),
            json_dumps(payload),
        ),
    )


def upsert_player_match(conn: sqlite3.Connection, account_id: int, match: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO player_match_index
          (account_id, match_id, start_time, hero_id, player_slot, radiant_win,
           game_mode, lobby_type, kills, deaths, assists, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, match_id) DO UPDATE SET
          start_time=excluded.start_time,
          hero_id=excluded.hero_id,
          player_slot=excluded.player_slot,
          radiant_win=excluded.radiant_win,
          game_mode=excluded.game_mode,
          lobby_type=excluded.lobby_type,
          kills=excluded.kills,
          deaths=excluded.deaths,
          assists=excluded.assists,
          raw_json=excluded.raw_json
        """,
        (
            account_id,
            match["match_id"],
            match.get("start_time") or 0,
            match.get("hero_id"),
            match.get("player_slot"),
            int(match["radiant_win"]) if match.get("radiant_win") is not None else None,
            match.get("game_mode"),
            match.get("lobby_type"),
            match.get("kills"),
            match.get("deaths"),
            match.get("assists"),
            json_dumps(match),
        ),
    )


def replace_recent_player_matches(
    conn: sqlite3.Connection,
    account_id: int,
    matches: list[dict[str, Any]],
    synced_at: str,
) -> set[int]:
    recent = matches[:20]
    conn.execute("DELETE FROM recent_player_matches WHERE account_id = ?", (account_id,))
    for ordinal, match in enumerate(recent):
        upsert_player_match(conn, account_id, match)
        conn.execute(
            """
            INSERT INTO recent_player_matches (account_id, match_id, ordinal, synced_at)
            VALUES (?, ?, ?, ?)
            """,
            (account_id, int(match["match_id"]), ordinal, synced_at),
        )
    conn.execute(
        """
        INSERT INTO recent_sync_state (account_id, synced_at, match_count)
        VALUES (?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
          synced_at=excluded.synced_at,
          match_count=excluded.match_count
        """,
        (account_id, synced_at, len(recent)),
    )
    return {int(match["match_id"]) for match in recent}


def upsert_match(conn: sqlite3.Connection, match_id: int, payload: dict[str, Any], tracked_ids: set[int]) -> None:
    conn.execute(
        """
        INSERT INTO raw_matches
          (match_id, fetched_at, start_time, duration, radiant_win, parsed_version, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id) DO UPDATE SET
          fetched_at=excluded.fetched_at,
          start_time=excluded.start_time,
          duration=excluded.duration,
          radiant_win=excluded.radiant_win,
          parsed_version=excluded.parsed_version,
          raw_json=excluded.raw_json
        """,
        (
            match_id,
            now_utc().isoformat(),
            payload.get("start_time"),
            payload.get("duration"),
            int(payload["radiant_win"]) if payload.get("radiant_win") is not None else None,
            payload.get("version"),
            json_dumps(payload),
        ),
    )

    for player in payload.get("players") or []:
        slot = player.get("player_slot")
        if slot is None:
            continue
        account_id = player.get("account_id")
        conn.execute(
            """
            INSERT INTO match_players
              (match_id, account_id, player_slot, hero_id, is_tracked, win,
               kills, deaths, assists, gold_per_min, xp_per_min, hero_damage,
               tower_damage, hero_healing, last_hits, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, player_slot) DO UPDATE SET
              account_id=excluded.account_id,
              hero_id=excluded.hero_id,
              is_tracked=excluded.is_tracked,
              win=excluded.win,
              kills=excluded.kills,
              deaths=excluded.deaths,
              assists=excluded.assists,
              gold_per_min=excluded.gold_per_min,
              xp_per_min=excluded.xp_per_min,
              hero_damage=excluded.hero_damage,
              tower_damage=excluded.tower_damage,
              hero_healing=excluded.hero_healing,
              last_hits=excluded.last_hits,
              raw_json=excluded.raw_json
            """,
            (
                match_id,
                account_id,
                slot,
                player.get("hero_id"),
                int(account_id in tracked_ids) if account_id is not None else 0,
                player.get("win"),
                player.get("kills"),
                player.get("deaths"),
                player.get("assists"),
                player.get("gold_per_min"),
                player.get("xp_per_min"),
                player.get("hero_damage"),
                player.get("tower_damage"),
                player.get("hero_healing"),
                player.get("last_hits"),
                json_dumps(player),
            ),
        )


def backfill_tracked_player_matches(conn: sqlite3.Connection, tracked_ids: set[int]) -> int:
    """Index tracked players found in cached shared matches.

    This keeps private match histories useful when another tracked player's
    public recentMatches response led us to the same match.
    """
    inserted = 0
    rows = conn.execute("SELECT raw_json FROM raw_matches ORDER BY start_time, match_id").fetchall()
    for row in rows:
        match = json.loads(row["raw_json"])
        for player in match.get("players") or []:
            account_id = player.get("account_id")
            if account_id not in tracked_ids:
                continue
            existed = conn.execute(
                "SELECT 1 FROM player_match_index WHERE account_id = ? AND match_id = ?",
                (account_id, match.get("match_id")),
            ).fetchone()
            indexed = {
                **player,
                "match_id": match.get("match_id"),
                "start_time": match.get("start_time"),
                "radiant_win": match.get("radiant_win"),
                "game_mode": match.get("game_mode"),
                "lobby_type": match.get("lobby_type"),
            }
            upsert_player_match(conn, int(account_id), indexed)
            inserted += int(existed is None)
    if tracked_ids:
        placeholders = ",".join("?" for _ in tracked_ids)
        conn.execute(
            f"UPDATE match_players SET is_tracked = 1 WHERE account_id IN ({placeholders})",
            tuple(sorted(tracked_ids)),
        )
    conn.commit()
    return inserted


def upsert_parse_request(conn: sqlite3.Connection, match_id: int, payload: Any) -> None:
    job_id = None
    if isinstance(payload, dict):
        job_id = payload.get("job", {}).get("jobId") or payload.get("jobId") or payload.get("id")
    conn.execute(
        """
        INSERT INTO parse_requests (match_id, requested_at, job_id, raw_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(match_id) DO UPDATE SET
          requested_at=excluded.requested_at,
          job_id=excluded.job_id,
          raw_json=excluded.raw_json
        """,
        (match_id, now_utc().isoformat(), job_id, json_dumps(payload)),
    )


def load_config(path: Path) -> tuple[list[int], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    players = [int(player) for player in data["players"]]
    since = data.get("since", "2026-07-01")
    return players, since


def fetch_player_endpoint(account_id: int, endpoint: str) -> tuple[str, dict[str, Any], Any]:
    if endpoint == "profile":
        path = f"/players/{account_id}"
        params: dict[str, Any] = {}
    elif endpoint in {"wlTurbo", "totalsTurbo"}:
        path = f"/players/{account_id}/{endpoint.removesuffix('Turbo')}"
        params = {"game_mode": 23}
    else:
        path = f"/players/{account_id}/{endpoint}"
        params = {}
    return path, params, fetch_json(path, params)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest OpenDota data for tracked players.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--since", help="UTC date in YYYY-MM-DD format. Defaults to data/player-ids.json.")
    parser.add_argument("--skip-match-details", action="store_true")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also refresh profile and all-time aggregate endpoints.",
    )
    parser.add_argument(
        "--only-card-aggregates",
        action="store_true",
        help="Refresh only profile, win/loss and total-stat endpoints used by card ratings.",
    )
    parser.add_argument(
        "--request-parse-missing",
        action="store_true",
        help="Submit OpenDota parse jobs for fetched matches whose detail payload is not parsed.",
    )
    parser.add_argument(
        "--only-request-parses",
        action="store_true",
        help="Skip player/match fetching and only request parses for existing unparsed raw_matches.",
    )
    args = parser.parse_args()

    players, config_since = load_config(args.config)
    since_text = args.since or config_since
    since = parse_date(since_text)
    since_ts = int(since.timestamp())
    tracked_ids = set(players)
    aggregate_endpoints = ("profile", "wl", "wlTurbo", "totals", "totalsTurbo", "counts")
    if args.only_card_aggregates:
        endpoints = aggregate_endpoints
    else:
        endpoints = FULL_PLAYER_ENDPOINTS if args.full else REGULAR_PLAYER_ENDPOINTS

    conn = connect(args.db)
    migrate(conn)
    removed_links, removed_details = purge_matches_before(conn, since_ts)
    if removed_links or removed_details:
        print(
            f"removed pre-season data: {removed_links} player-match links, {removed_details} detailed matches",
            flush=True,
        )

    run_started = now_utc().isoformat()
    match_ids: set[int] = set()
    failures: list[str] = []
    recent_syncs: set[int] = set()
    run_id = None

    if args.only_request_parses:
        rows = conn.execute(
            "SELECT match_id FROM raw_matches WHERE start_time >= ? ORDER BY match_id",
            (since_ts,),
        ).fetchall()
        match_ids = {int(row["match_id"]) for row in rows}
    else:
        cursor = conn.execute(
            "INSERT INTO ingestion_runs (started_at, since, source, player_count) VALUES (?, ?, ?, ?)",
            (run_started, since_text, BASE_URL, len(players)),
        )
        run_id = cursor.lastrowid
        conn.commit()

        for account_id in players:
            print(f"player {account_id}: fetching endpoints", flush=True)
            conn.execute(
                "INSERT OR IGNORE INTO tracked_players (account_id, added_at) VALUES (?, ?)",
                (account_id, run_started),
            )

            for endpoint in endpoints:
                try:
                    path, params, payload = fetch_player_endpoint(account_id, endpoint)
                except RuntimeError as exc:
                    print(f"  {endpoint} failed: {exc}", flush=True)
                    failures.append(f"player {account_id} {endpoint}")
                    continue
                if endpoint == "recentMatches" and isinstance(payload, list):
                    payload = [match for match in payload if int(match.get("start_time") or 0) >= since_ts][:20]
                upsert_raw_endpoint(
                    conn,
                    account_id,
                    endpoint,
                    path,
                    params,
                    since_text if endpoint == "matches" else None,
                    payload,
                )

                if endpoint == "recentMatches" and isinstance(payload, list):
                    recent_ids = replace_recent_player_matches(conn, account_id, payload, run_started)
                    match_ids.update(recent_ids)
                    recent_syncs.add(account_id)
                    print(f"  recentMatches since {since_text}: {len(recent_ids)}", flush=True)
                else:
                    print(f"  {endpoint}", flush=True)

                conn.commit()

    if not args.only_request_parses and not args.only_card_aggregates and len(recent_syncs) != len(players):
        missing_players = sorted(tracked_ids - recent_syncs)
        print(f"recent match sync incomplete for players: {missing_players}", flush=True)
        failures.extend(f"player {account_id} recent sync" for account_id in missing_players)

    if not args.skip_match_details and match_ids:
        placeholders = ",".join("?" for _ in match_ids)
        rows = conn.execute(
            f"""
            SELECT recent.match_id
            FROM (SELECT DISTINCT match_id FROM recent_player_matches WHERE match_id IN ({placeholders})) recent
            LEFT JOIN raw_matches rm ON rm.match_id = recent.match_id
            LEFT JOIN match_players mp ON mp.match_id = recent.match_id
            GROUP BY recent.match_id, rm.match_id
            HAVING rm.match_id IS NULL OR COUNT(mp.player_slot) < 10
            ORDER BY recent.match_id
            """,
            tuple(sorted(match_ids)),
        ).fetchall()
        detail_ids = [int(row["match_id"]) for row in rows]
        cached_count = len(match_ids) - len(detail_ids)
        print(
            f"fetching {len(detail_ids)} new/missing match detail payloads "
            f"({cached_count} cached, {len(match_ids)} recent unique)",
            flush=True,
        )
        for index, match_id in enumerate(detail_ids, 1):
            try:
                payload = fetch_json(f"/matches/{match_id}")
            except RuntimeError as exc:
                print(f"  {index}/{len(detail_ids)} match {match_id} failed: {exc}", flush=True)
                failures.append(f"match {match_id}")
                continue
            if isinstance(payload, dict) and "error" not in payload:
                upsert_match(conn, match_id, payload, tracked_ids)
                conn.commit()
            print(f"  {index}/{len(detail_ids)} match {match_id}", flush=True)

    if args.request_parse_missing:
        rows = conn.execute(
            """
            SELECT match_id
            FROM raw_matches
            WHERE match_id IN (%s)
              AND (parsed_version IS NULL OR parsed_version = '')
            ORDER BY match_id
            """
            % ",".join("?" for _ in match_ids),
            tuple(sorted(match_ids)),
        ).fetchall() if match_ids else []
        print(f"requesting parses for {len(rows)} unparsed matches", flush=True)
        for index, row in enumerate(rows, 1):
            match_id = int(row["match_id"])
            try:
                payload = fetch_json(f"/request/{match_id}", method="POST")
            except RuntimeError as exc:
                print(f"  {index}/{len(rows)} request {match_id} failed: {exc}", flush=True)
                continue
            upsert_parse_request(conn, match_id, payload)
            conn.commit()
            print(f"  {index}/{len(rows)} requested match {match_id}: {payload}", flush=True)

    if not args.only_request_parses:
        backfilled = backfill_tracked_player_matches(conn, tracked_ids)
        if backfilled:
            print(f"backfilled {backfilled} tracked player-match links from cached shared matches", flush=True)

    if run_id is not None:
        conn.execute(
            "UPDATE ingestion_runs SET finished_at=?, match_count=? WHERE id=?",
            (now_utc().isoformat(), len(match_ids), run_id),
        )
        conn.commit()

    print(f"done: {args.db} ({len(players)} players, {len(match_ids)} recent unique matches)")
    if failures:
        print(f"refresh incomplete: {len(failures)} request(s) failed", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        raise SystemExit(130)
