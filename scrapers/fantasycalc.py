import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.db import get_db, init_db, upsert_many

API_URL = "https://api.fantasycalc.com/values/current"

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "trade_values")

FORMATS = {
    "dynasty_sf_half": {"isDynasty": "true", "numQbs": 2, "ppr": 0.5},
    "dynasty_sf_ppr": {"isDynasty": "true", "numQbs": 2, "ppr": 1},
    "dynasty_1qb_half": {"isDynasty": "true", "numQbs": 1, "ppr": 0.5},
    "dynasty_1qb_ppr": {"isDynasty": "true", "numQbs": 1, "ppr": 1},
    "redraft_sf_half": {"isDynasty": "false", "numQbs": 2, "ppr": 0.5},
    "redraft_sf_ppr": {"isDynasty": "false", "numQbs": 2, "ppr": 1},
    "redraft_1qb_half": {"isDynasty": "false", "numQbs": 1, "ppr": 0.5},
    "redraft_1qb_ppr": {"isDynasty": "false", "numQbs": 1, "ppr": 1},
}

REQUEST_DELAY = 2


def fetch_values(format_key, num_teams=12):
    params = FORMATS.get(format_key)
    if not params:
        print(f"Unknown format: {format_key}")
        print(f"Available: {list(FORMATS.keys())}")
        return []

    query = {
        "isDynasty": params["isDynasty"],
        "numQbs": params["numQbs"],
        "numTeams": num_teams,
        "ppr": params["ppr"],
    }

    print(f"  Fetching: {API_URL}?{'&'.join(f'{k}={v}' for k,v in query.items())}")
    resp = requests.get(API_URL, params=query, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_response(data, format_key):
    players = []
    for item in data:
        p = item.get("player", {})
        sleeper_id = p.get("sleeperId")
        if not sleeper_id:
            continue

        players.append({
            "player_id": str(sleeper_id),
            "player_name": p.get("name", ""),
            "source": "fantasycalc",
            "format": format_key,
            "value": item.get("value", 0),
            "overall_rank": item.get("overallRank"),
            "position_rank": item.get("positionRank"),
            "position": p.get("position", ""),
            "team": p.get("maybeTeam", ""),
            "age": p.get("maybeAge"),
            "trend_30day": item.get("trend30Day"),
        })
    return players


def save_json(players, format_key):
    os.makedirs(DATA_DIR, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    filepath = os.path.join(DATA_DIR, f"fantasycalc_{format_key}.json")

    data = {
        "source": "fantasycalc",
        "format": format_key,
        "fetched_at": now,
        "count": len(players),
        "players": players,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"  Saved to {filepath}")


def save_to_db(players, format_key):
    init_db()
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for p in players:
        rows.append({
            "player_id": p["player_id"],
            "player_name": p["player_name"],
            "source": "fantasycalc",
            "format": format_key,
            "value": p["value"],
            "overall_rank": p["overall_rank"],
            "position_rank": p["position_rank"],
            "position": p["position"],
            "team": p["team"],
            "age": p["age"],
            "trend_30day": p["trend_30day"],
            "fetched_at": now,
        })

    with get_db() as conn:
        conn.execute(
            "DELETE FROM trade_values WHERE source = ? AND format = ?",
            ("fantasycalc", format_key),
        )
        upsert_many(conn, "trade_values", rows, ["player_id", "source", "format"])

    print(f"  Inserted {len(rows)} trade values into DB")


def run(format_key, num_teams=12):
    print(f"\n[FANTASYCALC] {format_key} ({num_teams} teams)")
    data = fetch_values(format_key, num_teams)
    if not data:
        print("  No data returned")
        return

    players = parse_response(data, format_key)
    print(f"  Parsed {len(players)} players with sleeper IDs")

    save_json(players, format_key)
    save_to_db(players, format_key)
    print("  Done!")


def run_all(num_teams=12):
    print("=" * 60)
    print("FETCHING ALL FANTASYCALC TRADE VALUES")
    print("=" * 60)

    for format_key in FORMATS:
        run(format_key, num_teams)
        time.sleep(REQUEST_DELAY)

    print("\n" + "=" * 60)
    print("ALL TRADE VALUES UPDATED")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch FantasyCalc trade values")
    parser.add_argument(
        "--format",
        choices=list(FORMATS.keys()),
        help="Specific format to fetch",
    )
    parser.add_argument(
        "--teams",
        type=int,
        default=12,
        choices=[10, 12, 14],
        help="Number of teams (default: 12)",
    )
    parser.add_argument("--all", action="store_true", help="Fetch all formats")
    args = parser.parse_args()

    if args.all:
        run_all(args.teams)
    elif args.format:
        run(args.format, args.teams)
    else:
        parser.print_help()
