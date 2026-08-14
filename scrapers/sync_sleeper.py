import argparse
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.db import init_db, get_db, upsert_many
from core.sleeper import (
    get_user,
    get_user_leagues,
    get_league,
    get_rosters,
    get_users,
    get_traded_picks,
    get_all_players,
    classify_league,
)


def sync_players(conn):
    print("Fetching NFL players database (~10k records)...")
    all_players = get_all_players()

    rows = []
    for pid, p in all_players.items():
        if p.get("position") not in ("QB", "RB", "WR", "TE", "K", "DEF"):
            continue
        rows.append({
            "player_id": str(pid),
            "full_name": p.get("full_name", ""),
            "first_name": p.get("first_name", ""),
            "last_name": p.get("last_name", ""),
            "position": p.get("position", ""),
            "team": p.get("team") or "FA",
            "age": p.get("age"),
            "status": p.get("status", ""),
            "injury_status": p.get("injury_status") or "",
            "years_exp": p.get("years_exp"),
        })

    upsert_many(conn, "players", rows, ["player_id"])
    print(f"  Synced {len(rows)} players")


def sync_league(conn, league_data):
    classification = classify_league(league_data)
    settings = league_data.get("settings", {})

    row = {
        "league_id": league_data["league_id"],
        "name": league_data.get("name", ""),
        "season": league_data.get("season", ""),
        "league_type": classification["league_type"],
        "scoring_type": classification["scoring_type"],
        "is_superflex": classification["is_superflex"],
        "is_tep": classification["is_tep"],
        "has_kicker": classification["has_kicker"],
        "has_dst": classification["has_dst"],
        "roster_positions": json.dumps(league_data.get("roster_positions", [])),
        "scoring_settings": json.dumps(league_data.get("scoring_settings", {})),
        "total_rosters": league_data.get("total_rosters", 0),
        "draft_id": league_data.get("draft_id", ""),
        "draft_rounds": settings.get("draft_rounds", 0),
        "taxi_slots": settings.get("taxi_slots", 0),
        "reserve_slots": settings.get("reserve_slots", 0),
        "ranking_format": classification["ranking_format"],
    }
    upsert_many(conn, "leagues", [row], ["league_id"])


def sync_users(conn, league_id):
    users_data = get_users(league_id)
    rosters_data = get_rosters(league_id)

    owner_to_roster = {}
    for r in rosters_data:
        if r.get("owner_id"):
            owner_to_roster[r["owner_id"]] = r["roster_id"]

    rows = []
    for u in users_data:
        uid = u["user_id"]
        rows.append({
            "user_id": uid,
            "league_id": league_id,
            "display_name": u.get("display_name", ""),
            "team_name": (u.get("metadata") or {}).get("team_name", ""),
            "avatar": u.get("avatar", ""),
            "roster_id": owner_to_roster.get(uid),
        })
    upsert_many(conn, "users", rows, ["user_id", "league_id"])
    print(f"  Synced {len(rows)} users")


def sync_rosters(conn, league_id):
    rosters_data = get_rosters(league_id)

    roster_rows = []
    player_rows = []

    conn.execute(
        "DELETE FROM roster_players WHERE league_id = ?", (league_id,)
    )

    for r in rosters_data:
        rid = r["roster_id"]
        settings = r.get("settings", {})

        roster_rows.append({
            "roster_id": rid,
            "league_id": league_id,
            "owner_id": r.get("owner_id", ""),
            "wins": settings.get("wins", 0),
            "losses": settings.get("losses", 0),
            "ties": settings.get("ties", 0),
            "fpts": settings.get("fpts", 0),
            "fpts_against": settings.get("fpts_against", 0),
            "waiver_position": settings.get("waiver_position", 0),
            "waiver_budget_used": settings.get("waiver_budget_used", 0),
        })

        starters = set(r.get("starters") or [])
        taxi = set(r.get("taxi") or [])
        reserve = set(r.get("reserve") or [])
        all_players = r.get("players") or []

        for pid in all_players:
            if pid == "0":
                continue
            if pid in starters:
                slot = "starter"
            elif pid in taxi:
                slot = "taxi"
            elif pid in reserve:
                slot = "reserve"
            else:
                slot = "bench"

            player_rows.append({
                "league_id": league_id,
                "roster_id": rid,
                "player_id": str(pid),
                "slot": slot,
            })

    upsert_many(conn, "rosters", roster_rows, ["roster_id", "league_id"])
    upsert_many(conn, "roster_players", player_rows, ["league_id", "roster_id", "player_id"])
    print(f"  Synced {len(roster_rows)} rosters, {len(player_rows)} player slots")


def sync_traded_picks(conn, league_id):
    picks_data = get_traded_picks(league_id)

    conn.execute("DELETE FROM traded_picks WHERE league_id = ?", (league_id,))

    rows = []
    for p in picks_data:
        rows.append({
            "league_id": league_id,
            "round": p["round"],
            "season": p["season"],
            "roster_id": p["roster_id"],
            "original_owner_id": p.get("previous_owner_id", ""),
            "current_owner_id": p["owner_id"],
        })
    upsert_many(conn, "traded_picks", rows, ["league_id", "round", "season", "roster_id"])
    print(f"  Synced {len(rows)} traded picks")


def run_sync(username, season="2026", skip_players=False):
    init_db()

    with get_db() as conn:
        if not skip_players:
            sync_players(conn)

        print(f"\nFetching leagues for {username} ({season})...")
        user = get_user(username)
        user_id = user["user_id"]
        leagues = get_user_leagues(user_id, season)
        print(f"Found {len(leagues)} leagues\n")

        for lg in leagues:
            league_id = lg["league_id"]
            league_detail = get_league(league_id)
            classification = classify_league(league_detail)

            print(f"--- {lg.get('name', league_id)} ---")
            print(f"  Type: {classification['league_type']} | "
                  f"Scoring: {classification['scoring_type']} | "
                  f"Format: {classification['ranking_format']} | "
                  f"TEP: {'yes' if classification['is_tep'] else 'no'}")

            sync_league(conn, league_detail)
            sync_users(conn, league_id)
            sync_rosters(conn, league_id)
            sync_traded_picks(conn, league_id)

        print(f"\nSync complete. {len(leagues)} leagues synced.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Sleeper data to SQLite")
    parser.add_argument("username", help="Sleeper username")
    parser.add_argument("--season", default="2026", help="NFL season (default: 2026)")
    parser.add_argument("--skip-players", action="store_true", help="Skip full player database sync")
    args = parser.parse_args()

    run_sync(args.username, args.season, args.skip_players)
