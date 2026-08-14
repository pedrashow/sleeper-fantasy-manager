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


@router.get("/")
def player_page(request: Request, q: str = ""):
    if not q:
        return templates.TemplateResponse(request, "player.html", {"q": "", "results": [], "player": None})

    conn = get_db()
    results = conn.execute(
        "SELECT player_id, full_name, position, team, age, status, injury_status, years_exp "
        "FROM players WHERE full_name LIKE ? AND position IN ('QB','RB','WR','TE') "
        "ORDER BY CASE WHEN full_name LIKE ? THEN 0 ELSE 1 END, full_name LIMIT 20",
        (f"%{q}%", f"{q}%"),
    ).fetchall()

    player = None
    if results:
        player = get_player_detail(conn, results[0]["player_id"])

    conn.close()
    return templates.TemplateResponse(request, "player.html", {
        "q": q,
        "results": [dict(r) for r in results],
        "player": player,
    })


@router.get("/detail/{player_id}")
def player_detail(request: Request, player_id: str):
    conn = get_db()
    player = get_player_detail(conn, player_id)
    conn.close()
    if not player:
        return templates.TemplateResponse(request, "player_detail.html", {"player": None})
    return templates.TemplateResponse(request, "player_detail.html", {"player": player})


def get_player_detail(conn, player_id):
    p = conn.execute(
        "SELECT player_id, full_name, position, team, age, status, injury_status, years_exp "
        "FROM players WHERE player_id = ?",
        (player_id,),
    ).fetchone()
    if not p:
        return None

    player = dict(p)

    fp = conn.execute(
        "SELECT ranking_type, format, rank, position_rank, tier, avg_adp, best, worst, bye_week "
        "FROM rankings WHERE player_id = ? AND week = 0 ORDER BY ranking_type DESC, format",
        (player_id,),
    ).fetchall()
    player["fp_rankings"] = [dict(r) for r in fp]

    fp_best = None
    for r in fp:
        if fp_best is None or r["rank"] < fp_best["rank"]:
            fp_best = dict(r)
    player["fp_best"] = fp_best

    lb = conn.execute(
        "SELECT pos_rank, overall_rank, tier, tier_name, notes "
        "FROM longbuild_rankings WHERE player_id = ?",
        (player_id,),
    ).fetchone()
    player["lb"] = dict(lb) if lb else None

    wn = conn.execute(
        "SELECT pos_rank, overall_rank, tier, tier_name, notes "
        "FROM winnow_rankings WHERE player_id = ?",
        (player_id,),
    ).fetchone()
    player["wn"] = dict(wn) if wn else None

    tvs = conn.execute(
        "SELECT format, value, overall_rank, position_rank, trend_30day "
        "FROM trade_values WHERE player_id = ? ORDER BY format",
        (player_id,),
    ).fetchall()
    player["trade_values"] = [dict(r) for r in tvs]

    tv_best = None
    for tv in tvs:
        if "dynasty" in tv["format"] and (tv_best is None or tv["value"] > tv_best["value"]):
            tv_best = dict(tv)
    if tv_best is None and tvs:
        tv_best = dict(tvs[0])
    player["tv_best"] = tv_best

    my_user = conn.execute(
        "SELECT user_id FROM users WHERE display_name = ? LIMIT 1",
        (USERNAME,),
    ).fetchone()

    leagues = conn.execute(
        "SELECT l.league_id, l.name, l.league_type, l.scoring_type, l.is_superflex "
        "FROM leagues l "
        "JOIN users u ON l.league_id = u.league_id "
        "WHERE u.display_name = ? ORDER BY l.name",
        (USERNAME,),
    ).fetchall()

    rostered_in = []
    available_in = []

    for lg in leagues:
        rp = conn.execute(
            "SELECT rp.slot, u.display_name as owner "
            "FROM roster_players rp "
            "JOIN users u ON rp.roster_id = u.roster_id AND rp.league_id = u.league_id "
            "WHERE rp.player_id = ? AND rp.league_id = ?",
            (player_id, lg["league_id"]),
        ).fetchone()

        if rp:
            rostered_in.append({
                "league": lg["name"],
                "type": lg["league_type"],
                "owner": rp["owner"],
                "slot": rp["slot"],
                "is_mine": rp["owner"] == USERNAME,
            })
        else:
            available_in.append({
                "league": lg["name"],
                "type": lg["league_type"],
            })

    player["rostered_in"] = rostered_in
    player["available_in"] = available_in

    return player
