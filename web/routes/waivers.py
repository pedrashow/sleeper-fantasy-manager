import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fantasy.db"
USERNAME = "pedrashow"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def ranking_format_for_league(lg):
    if lg["league_type"] == "dynasty":
        return "sf" if lg["is_superflex"] else "1qb"
    scoring = lg.get("scoring_type", "half_ppr")
    sc = {"ppr": "ppr", "half_ppr": "half", "standard": "std"}.get(scoring, "half")
    return f"sf_{sc}" if lg["is_superflex"] else sc


def tv_format_for_league(lg):
    lt = "dynasty" if lg["league_type"] == "dynasty" else "redraft"
    sf = "sf" if lg["is_superflex"] else "1qb"
    sc = {"ppr": "ppr", "half_ppr": "half", "standard": "half"}.get(lg.get("scoring_type", ""), "half")
    return f"{lt}_{sf}_{sc}"


def get_position_window(conn, league_id, my_roster_id, pos, r_type, r_format, tv_format, week=0, is_dynasty=True):
    my_players = conn.execute("""
        SELECT rp.player_id, p.full_name, p.position, p.team, p.injury_status,
            r.rank as fp_rank, r.position_rank as fp_pos_rank,
            tv.value as tv_value, tv.trend_30day as tv_trend,
            lb.pos_rank as lb_rank, wn.pos_rank as wn_rank
        FROM roster_players rp
        JOIN players p ON rp.player_id = p.player_id
        LEFT JOIN rankings r ON rp.player_id = r.player_id
            AND r.ranking_type = ? AND r.format = ? AND r.week = ?
        LEFT JOIN trade_values tv ON rp.player_id = tv.player_id AND tv.format = ?
        LEFT JOIN longbuild_rankings lb ON rp.player_id = lb.player_id
        LEFT JOIN winnow_rankings wn ON rp.player_id = wn.player_id
        WHERE rp.league_id = ? AND rp.roster_id = ? AND p.position = ?
        ORDER BY COALESCE(r.rank, 9999)
    """, (r_type, r_format, week, tv_format, league_id, my_roster_id, pos)).fetchall()

    rostered_ids = set(r["player_id"] for r in conn.execute(
        "SELECT player_id FROM roster_players WHERE league_id = ?", (league_id,)
    ).fetchall())

    fa_params = [tv_format, r_type, r_format, week, pos] + list(rostered_ids)
    free_agents = conn.execute("""
        SELECT r.player_id, r.player_name as full_name, COALESCE(r.position, p.position, '') as position,
            COALESCE(r.team, p.team, '') as team, p.injury_status,
            r.rank as fp_rank, r.position_rank as fp_pos_rank,
            tv.value as tv_value, tv.trend_30day as tv_trend,
            lb.pos_rank as lb_rank, wn.pos_rank as wn_rank
        FROM rankings r
        LEFT JOIN players p ON r.player_id = p.player_id
        LEFT JOIN trade_values tv ON r.player_id = tv.player_id AND tv.format = ?
        LEFT JOIN longbuild_rankings lb ON r.player_id = lb.player_id
        LEFT JOIN winnow_rankings wn ON r.player_id = wn.player_id
        WHERE r.ranking_type = ? AND r.format = ? AND r.week = ?
            AND COALESCE(r.position, p.position, '') = ?
            AND r.player_id IS NOT NULL
            AND r.player_id NOT IN ({})
        ORDER BY r.rank
    """.format(",".join("?" * len(rostered_ids))), fa_params).fetchall()

    my_list = [dict(r) | {"is_mine": True} for r in my_players]
    fa_list = [dict(r) | {"is_mine": False} for r in free_agents]

    if len(my_list) < 2:
        return my_list + fa_list[:8]

    all_ranked = sorted(my_list + fa_list, key=lambda x: x.get("fp_rank") or 9999)

    second_worst_rank = my_list[-2].get("fp_rank") or 9999
    worst_rank = my_list[-1].get("fp_rank") or 9999
    best_fa_rank = fa_list[0].get("fp_rank") or 9999 if fa_list else 9999

    start_rank = min(best_fa_rank, second_worst_rank)

    window = []
    past_worst = False
    for p in all_ranked:
        r = p.get("fp_rank") or 9999
        if r < start_rank:
            continue
        window.append(p)
        if p.get("is_mine") and r >= worst_rank:
            past_worst = True
        if past_worst and r > worst_rank:
            break

    return window if window else my_list[-3:] + fa_list[:5]


def get_my_pos_rank(conn, league_id, my_roster_id, pos, tv_format):
    all_teams = conn.execute("""
        SELECT u.roster_id, COALESCE(SUM(tv.value), 0) as pos_tv
        FROM users u
        LEFT JOIN roster_players rp ON u.roster_id = rp.roster_id AND u.league_id = rp.league_id
        LEFT JOIN players p ON rp.player_id = p.player_id AND p.position = ?
        LEFT JOIN trade_values tv ON rp.player_id = tv.player_id AND tv.format = ?
        WHERE u.league_id = ?
        GROUP BY u.roster_id
        ORDER BY pos_tv DESC
    """, (pos, tv_format, league_id)).fetchall()
    for i, t in enumerate(all_teams):
        if t["roster_id"] == my_roster_id:
            return i + 1
    return 0


def build_league_data(conn, league, r_type, r_format, week, pos_list):
    lg_id = league["league_id"]
    tv_format = tv_format_for_league(league)
    is_dynasty = league["league_type"] == "dynasty"

    my_user = conn.execute(
        "SELECT roster_id FROM users WHERE display_name = ? AND league_id = ?",
        (USERNAME, lg_id),
    ).fetchone()
    my_roster_id = my_user["roster_id"] if my_user else None

    positions = []
    for pos in pos_list:
        window = get_position_window(conn, lg_id, my_roster_id, pos, r_type, r_format, tv_format, week, is_dynasty)
        pos_rank = get_my_pos_rank(conn, lg_id, my_roster_id, pos, tv_format)
        positions.append({"pos": pos, "players": window, "my_rank": pos_rank})

    return {
        "league": league,
        "positions": positions,
        "is_dynasty": is_dynasty,
    }


@router.get("/")
def waivers_page(request: Request, tab: str = "dynasty", ranking_mode: str = "season", week: int = 1, show_kdst: str = ""):
    conn = get_db()

    leagues = conn.execute(
        "SELECT l.league_id, l.name, l.league_type, l.scoring_type, l.is_superflex, "
        "l.total_rosters, l.ranking_format, l.roster_positions, l.is_tep, l.has_kicker, l.has_dst "
        "FROM leagues l JOIN users u ON l.league_id = u.league_id "
        "WHERE u.display_name = ? ORDER BY l.name",
        (USERNAME,),
    ).fetchall()

    dynasty_data = []
    redraft_data = []

    for lg in leagues:
        league = dict(lg)
        is_dynasty = league["league_type"] == "dynasty"
        r_format = ranking_format_for_league(league)

        if is_dynasty:
            r_type = "dynasty"
            r_week = 0
            pos_list = ["QB", "RB", "WR", "TE"]
            dynasty_data.append(build_league_data(conn, league, r_type, r_format, r_week, pos_list))
        else:
            if ranking_mode == "weekly":
                r_type = "weekly"
                r_week = week
            elif ranking_mode == "ros":
                r_type = "ros"
                r_week = 0
            else:
                r_type = "redraft"
                r_week = 0
            pos_list = ["QB", "RB", "WR", "TE"]
            if show_kdst:
                if league.get("has_kicker"):
                    pos_list.append("K")
                if league.get("has_dst"):
                    pos_list.append("DEF")
            redraft_data.append(build_league_data(conn, league, r_type, r_format, r_week, pos_list))

    conn.close()

    return templates.TemplateResponse(request, "waivers.html", {
        "dynasty_data": dynasty_data,
        "redraft_data": redraft_data,
        "tab": tab,
        "ranking_mode": ranking_mode,
        "week": week,
        "show_kdst": show_kdst,
    })
