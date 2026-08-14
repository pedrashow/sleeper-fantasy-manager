from core.league_repo import get_user_id


def search_players(conn, query):
    return conn.execute(
        "SELECT player_id, full_name, position, team, age, status, injury_status, years_exp "
        "FROM players WHERE full_name LIKE ? AND position IN ('QB','RB','WR','TE') "
        "ORDER BY CASE WHEN full_name LIKE ? THEN 0 ELSE 1 END, full_name LIMIT 20",
        (f"%{query}%", f"{query}%"),
    ).fetchall()


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

    user_id = get_user_id()

    leagues = conn.execute(
        "SELECT l.league_id, l.name, l.league_type, l.scoring_type, l.is_superflex "
        "FROM leagues l "
        "JOIN users u ON l.league_id = u.league_id "
        "WHERE u.user_id = ? ORDER BY l.name",
        (user_id,),
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
            owner_is_me = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ? AND league_id = ? AND roster_id = ("
                "  SELECT rp2.roster_id FROM roster_players rp2 "
                "  JOIN users u2 ON rp2.roster_id = u2.roster_id AND rp2.league_id = u2.league_id "
                "  WHERE rp2.player_id = ? AND rp2.league_id = ? LIMIT 1"
                ")",
                (user_id, lg["league_id"], player_id, lg["league_id"]),
            ).fetchone()

            rostered_in.append({
                "league": lg["name"],
                "type": lg["league_type"],
                "owner": rp["owner"],
                "slot": rp["slot"],
                "is_mine": owner_is_me is not None,
            })
        else:
            available_in.append({
                "league": lg["name"],
                "type": lg["league_type"],
            })

    player["rostered_in"] = rostered_in
    player["available_in"] = available_in

    return player
