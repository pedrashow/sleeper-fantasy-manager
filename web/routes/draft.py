import json
import math
import random
import sqlite3
from pathlib import Path

import requests
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fantasy.db"
SLEEPER_API = "https://api.sleeper.app/v1"

POS_COLORS = {"QB": "#e74c6f", "RB": "#4caf8a", "WR": "#4a9bd9", "TE": "#e8a838", "K": "#9b7fc4", "DEF": "#7f8c8d"}
POS_PASTEL = {"QB": "#fce4e4", "RB": "#e0f5e0", "WR": "#ddeeff", "TE": "#fef0dd", "K": "#ede0f5", "DEF": "#e5e8ea"}

_draft_cache = {}


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def sleeper_get(path):
    resp = requests.get(f"{SLEEPER_API}{path}", timeout=15)
    resp.raise_for_status()
    return resp.json()


def detect_ranking_type(league, live_rounds=None):
    lt = league.get("league_type", "redraft")
    dr = live_rounds or league.get("draft_rounds") or 0
    if lt == "dynasty":
        return "rookie" if dr <= 6 else "startup"
    return "redraft"


def map_ranking_format(league, ranking_type=None):
    if ranking_type is None:
        ranking_type = detect_ranking_type(league)
    if ranking_type in ("rookie", "startup", "dynasty"):
        return "sf" if league.get("is_superflex") else "1qb"
    scoring = league.get("scoring_type", "half_ppr")
    scoring_map = {"ppr": "ppr", "half_ppr": "half", "standard": "std"}
    sc = scoring_map.get(scoring, "half")
    if league.get("is_superflex"):
        return f"sf_{sc}"
    return sc


def tv_format_for_league(lg):
    lt = "dynasty" if lg.get("league_type") == "dynasty" else "redraft"
    sf = "sf" if lg.get("is_superflex") else "1qb"
    sc = {"ppr": "ppr", "half_ppr": "half", "standard": "half"}.get(lg.get("scoring_type", ""), "half")
    return f"{lt}_{sf}_{sc}"


def format_adp(adp, num_teams):
    if adp is None or num_teams <= 0:
        return ""
    try:
        adp = float(adp)
    except (TypeError, ValueError):
        return ""
    if adp <= 0:
        return ""
    rd = int(math.ceil(adp / num_teams))
    pick = int(((adp - 1) % num_teams) + 1)
    return f"{rd}.{pick:02d}"


def count_position_needs(drafted_positions, roster_positions_json):
    roster_positions = json.loads(roster_positions_json) if isinstance(roster_positions_json, str) else roster_positions_json
    slots = {}
    for pos in roster_positions:
        if pos in ("BN", "IR"):
            continue
        slots[pos] = slots.get(pos, 0) + 1
    counts = {}
    for pos in drafted_positions:
        counts[pos] = counts.get(pos, 0) + 1
    needs = {}
    for slot, required in slots.items():
        if slot in ("FLEX", "SUPER_FLEX", "REC_FLEX", "WRRB_FLEX"):
            continue
        filled = counts.get(slot, 0)
        if filled < required:
            needs[slot] = required - filled
    return needs, counts


def load_favorites(conn, draft_id):
    targets = set()
    avoids = set()
    try:
        rows = conn.execute(
            "SELECT player_id, type FROM draft_favorites WHERE draft_id = ?",
            (draft_id,)
        ).fetchall()
        for r in rows:
            if r["type"] == "target":
                targets.add(r["player_id"])
            elif r["type"] == "avoid":
                avoids.add(r["player_id"])
    except Exception:
        pass
    return targets, avoids


def save_favorite(conn, draft_id, player_id, fav_type):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS draft_favorites (
            draft_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'target',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (draft_id, player_id)
        )
    """)
    conn.execute(
        "INSERT OR REPLACE INTO draft_favorites (draft_id, player_id, type) VALUES (?, ?, ?)",
        (draft_id, player_id, fav_type),
    )
    conn.commit()


def remove_favorite(conn, draft_id, player_id):
    conn.execute(
        "DELETE FROM draft_favorites WHERE draft_id = ? AND player_id = ?",
        (draft_id, player_id),
    )
    conn.commit()


def get_available_players(conn, ranking_type_db, ranking_format, tv_format, picked_ids, picked_names, avoid_ids):
    rows = conn.execute("""
        SELECT r.rank, r.player_name, COALESCE(r.position, p.position, '') as pos,
            COALESCE(r.team, p.team, '') as team, r.tier, r.pos_tier, r.avg_adp, r.best, r.worst,
            r.bye_week, r.position_rank, r.owned_pct,
            COALESCE(p.player_id, '') as player_id,
            tv.tv_value, tv.tv_trend,
            lb.lb_rank, lb.lb_tier,
            wn.wn_rank, wn.wn_tier
        FROM rankings r
        LEFT JOIN players p ON r.player_id = p.player_id
        LEFT JOIN (
            SELECT player_id, value as tv_value, trend_30day as tv_trend
            FROM trade_values
            WHERE source = 'fantasycalc' AND format = ?
            GROUP BY player_id
        ) tv ON r.player_id = tv.player_id
        LEFT JOIN (
            SELECT player_id, pos_rank as lb_rank, tier as lb_tier
            FROM longbuild_rankings
            GROUP BY player_id
        ) lb ON p.player_id = lb.player_id
        LEFT JOIN (
            SELECT player_id, pos_rank as wn_rank, tier as wn_tier
            FROM winnow_rankings
            GROUP BY player_id
        ) wn ON p.player_id = wn.player_id
        WHERE r.ranking_type = ? AND r.format = ? AND r.week = 0
        ORDER BY r.rank
    """, (tv_format, ranking_type_db, ranking_format)).fetchall()

    available = []
    for r in rows:
        pid = r["player_id"]
        name = r["player_name"]
        if pid in picked_ids or name in picked_names or pid in avoid_ids:
            continue
        available.append(dict(r))
    return available


def compute_recommendations(available, needs):
    recs = {}
    if available:
        bpa = available[0]
        recs["bpa"] = {"name": bpa["player_name"], "pos": bpa["pos"], "rank": bpa["rank"], "pos_rank": bpa.get("position_rank", "")}
    recs["needs"] = {}
    for pos in ["QB", "RB", "WR", "TE"]:
        if needs.get(pos, 0) > 0:
            for p in available:
                if p["pos"] == pos:
                    recs["needs"][pos] = {"name": p["player_name"], "rank": p["rank"], "pos_rank": p.get("position_rank", ""), "shortfall": needs[pos]}
                    break
    return recs


def get_draft_context(conn, league, username="pedrashow"):
    draft_id = league["draft_id"]
    if not draft_id:
        return None

    draft = sleeper_get(f"/draft/{draft_id}")
    picks = sleeper_get(f"/draft/{draft_id}/picks")
    user_info = sleeper_get(f"/user/{username}")
    my_user_id = user_info["user_id"]

    draft_status = draft.get("status", "unknown")
    draft_type = draft.get("type", "snake")
    num_rounds = draft.get("settings", {}).get("rounds", league.get("draft_rounds") or 4)
    num_teams = league.get("total_rosters", 12)

    ranking_type = detect_ranking_type(league, live_rounds=num_rounds)
    ranking_format = map_ranking_format(league, ranking_type)
    ranking_type_db = "dynasty" if ranking_type == "startup" else ranking_type

    slot_to_roster = draft.get("slot_to_roster_id", {})
    draft_order = draft.get("draft_order", {})

    my_roster_id = None
    roster_row = conn.execute(
        "SELECT roster_id FROM users WHERE user_id = ? AND league_id = ?",
        (my_user_id, league["league_id"]),
    ).fetchone()
    if roster_row:
        my_roster_id = roster_row["roster_id"]

    my_slot = None
    if my_roster_id and draft_order:
        for uid, slot in draft_order.items():
            user_roster = conn.execute(
                "SELECT roster_id FROM users WHERE user_id = ? AND league_id = ?",
                (uid, league["league_id"]),
            ).fetchone()
            if user_roster and user_roster["roster_id"] == my_roster_id:
                my_slot = slot
                break

    picked_ids = set()
    picked_names = set()
    my_picks = []

    for p in picks:
        pid = p.get("player_id")
        if pid:
            picked_ids.add(str(pid))
        meta = p.get("metadata", {})
        name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        if name:
            picked_names.add(name)
        if p.get("roster_id") == my_roster_id:
            my_picks.append(p)

    my_drafted_positions = [p.get("metadata", {}).get("position", "") for p in my_picks if p.get("metadata", {}).get("position")]
    needs, pos_counts = count_position_needs(my_drafted_positions, league.get("roster_positions", "[]"))

    next_pick = len(picks) + 1
    my_next_pick = None
    if my_slot and draft_status != "complete":
        for pick_num in range(next_pick, num_rounds * num_teams + 1):
            rd = ((pick_num - 1) // num_teams) + 1
            if draft_type == "snake":
                slot = num_teams - ((pick_num - 1) % num_teams) if rd % 2 == 0 else ((pick_num - 1) % num_teams) + 1
            else:
                slot = ((pick_num - 1) % num_teams) + 1
            if slot == my_slot:
                my_next_pick = pick_num
                break

    tv_format = tv_format_for_league(league)
    targets, avoids = load_favorites(conn, draft_id)
    available = get_available_players(conn, ranking_type_db, ranking_format, tv_format, picked_ids, picked_names, avoids)
    recs = compute_recommendations(available, needs)

    slot_names = {}
    for slot_str, rid in slot_to_roster.items():
        slot_num = int(slot_str)
        owner_row = conn.execute(
            "SELECT display_name FROM users WHERE roster_id = ? AND league_id = ?",
            (rid, league["league_id"]),
        ).fetchone()
        slot_names[slot_num] = owner_row["display_name"] if owner_row else f"Slot {slot_num}"

    board = {}
    adp_lookup = {}
    for p in picks:
        pick_no = p.get("pick_no", 0)
        rd = p.get("round", 1)
        if draft_type == "snake":
            slot = num_teams - ((pick_no - 1) % num_teams) if rd % 2 == 0 else ((pick_no - 1) % num_teams) + 1
        else:
            slot = ((pick_no - 1) % num_teams) + 1
        meta = p.get("metadata", {})
        if rd not in board:
            board[rd] = {}
        board[rd][slot] = {
            "first": meta.get("first_name", ""),
            "last": meta.get("last_name", ""),
            "pos": meta.get("position", ""),
            "pick_no": pick_no,
        }

    adp_rows = conn.execute(
        "SELECT player_name, avg_adp FROM rankings WHERE ranking_type = ? AND format = ? AND week = 0 AND avg_adp IS NOT NULL",
        (ranking_type_db, ranking_format),
    ).fetchall()
    for row in adp_rows:
        adp_lookup[row["player_name"]] = row["avg_adp"]

    rt_label = {"rookie": "Rookie", "startup": "Startup", "redraft": "Redraft"}.get(ranking_type, ranking_type)

    return {
        "draft_id": draft_id,
        "draft_status": draft_status,
        "draft_type": draft_type,
        "num_rounds": num_rounds,
        "num_teams": num_teams,
        "ranking_type": ranking_type,
        "rt_label": rt_label,
        "slot_to_roster": slot_to_roster,
        "slot_names": slot_names,
        "my_roster_id": my_roster_id,
        "my_slot": my_slot,
        "next_pick": next_pick,
        "my_next_pick": my_next_pick,
        "picks": picks,
        "my_picks": my_picks,
        "board": board,
        "adp_lookup": adp_lookup,
        "available": available,
        "targets": targets,
        "avoids": avoids,
        "needs": needs,
        "pos_counts": pos_counts,
        "recs": recs,
        "pos_colors": POS_COLORS,
        "pos_pastel": POS_PASTEL,
    }


@router.get("/")
def draft_page(request: Request, league_id: str = "", username: str = "pedrashow"):
    conn = get_db()
    leagues = conn.execute(
        "SELECT league_id, name, league_type, scoring_type, is_superflex, is_tep, total_rosters, ranking_format, draft_id, draft_rounds, roster_positions, has_kicker, has_dst FROM leagues ORDER BY name"
    ).fetchall()

    if not leagues:
        conn.close()
        return templates.TemplateResponse(request, "draft.html", {"leagues": [], "ctx": None, "league_id": ""})

    if not league_id:
        league_id = leagues[0]["league_id"]

    league = None
    for lg in leagues:
        if lg["league_id"] == league_id:
            league = dict(lg)
            break
    if not league:
        league = dict(leagues[0])
        league_id = league["league_id"]

    ctx = None
    error = None
    try:
        ctx = get_draft_context(conn, league, username)
    except Exception as e:
        error = str(e)

    conn.close()

    return templates.TemplateResponse(request, "draft.html", {
        "leagues": [dict(lg) for lg in leagues],
        "league_id": league_id,
        "league": league,
        "username": username,
        "ctx": ctx,
        "error": error,
        "format_adp": format_adp,
    })


@router.post("/favorite")
def toggle_favorite(
    request: Request,
    draft_id: str = Form(...),
    player_id: str = Form(...),
    action: str = Form(...),
):
    conn = get_db()
    if action == "remove":
        remove_favorite(conn, draft_id, player_id)
    else:
        save_favorite(conn, draft_id, player_id, action)
    conn.close()
    return HTMLResponse('<span class="status-ok">✓</span>')
