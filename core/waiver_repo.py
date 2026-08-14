from core.formats import map_ranking_format, tv_format_for_league
from core.league_repo import get_my_roster_id, get_roster_with_values, get_free_agents_ranked


def get_position_window(conn, league_id, my_roster_id, pos, r_type, r_format, tv_format, week=0):
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

    fa_list_raw = get_free_agents_ranked(conn, league_id, r_type, r_format, tv_format, pos, week)

    my_list = [dict(r) | {"is_mine": True} for r in my_players]
    fa_list = [dict(r) | {"is_mine": False} for r in fa_list_raw]

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
    my_roster_id = get_my_roster_id(conn, lg_id)

    positions = []
    for pos in pos_list:
        window = get_position_window(
            conn, lg_id, my_roster_id, pos, r_type, r_format, tv_format, week
        )
        pos_rank = get_my_pos_rank(conn, lg_id, my_roster_id, pos, tv_format)
        positions.append({"pos": pos, "players": window, "my_rank": pos_rank})

    return {
        "league": league,
        "positions": positions,
        "is_dynasty": is_dynasty,
    }


def get_waivers_data(conn, leagues, tab, ranking_mode, week, show_kdst):
    dynasty_data = []
    redraft_data = []

    for lg in leagues:
        league = dict(lg)
        is_dynasty = league["league_type"] == "dynasty"
        r_format = map_ranking_format(league, "dynasty" if is_dynasty else "redraft")

        if is_dynasty:
            pos_list = ["QB", "RB", "WR", "TE"]
            dynasty_data.append(
                build_league_data(conn, league, "dynasty", r_format, 0, pos_list)
            )
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

            redraft_data.append(
                build_league_data(conn, league, r_type, r_format, r_week, pos_list)
            )

    return dynasty_data, redraft_data
