from core.config import SLEEPER_USERNAME
from core.sleeper import get_user

_user_id_cache = None


def get_user_id():
    global _user_id_cache
    if _user_id_cache:
        return _user_id_cache
    user = get_user(SLEEPER_USERNAME)
    _user_id_cache = user["user_id"]
    return _user_id_cache


def get_my_roster_id(conn, league_id):
    user_id = get_user_id()
    row = conn.execute(
        "SELECT roster_id FROM users WHERE user_id = ? AND league_id = ?",
        (user_id, league_id),
    ).fetchone()
    return row["roster_id"] if row else None


def get_my_leagues(conn):
    user_id = get_user_id()
    return conn.execute(
        "SELECT l.league_id, l.name, l.league_type, l.scoring_type, l.is_superflex, "
        "l.is_tep, l.total_rosters, l.ranking_format, l.draft_id, l.draft_rounds, "
        "l.roster_positions, l.has_kicker, l.has_dst "
        "FROM leagues l "
        "JOIN users u ON l.league_id = u.league_id "
        "WHERE u.user_id = ? ORDER BY l.name",
        (user_id,),
    ).fetchall()


def get_all_leagues(conn):
    return conn.execute(
        "SELECT league_id, name, league_type, scoring_type, is_superflex, "
        "is_tep, total_rosters, ranking_format, draft_id, draft_rounds, "
        "roster_positions, has_kicker, has_dst "
        "FROM leagues ORDER BY name"
    ).fetchall()


def get_roster_with_values(conn, league_id, roster_id, r_type, r_format, tv_format, week=0):
    return conn.execute("""
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
        WHERE rp.league_id = ? AND rp.roster_id = ? 
        ORDER BY COALESCE(r.rank, 9999)
    """, (r_type, r_format, week, tv_format, league_id, roster_id)).fetchall()


def get_rostered_ids(conn, league_id):
    rows = conn.execute(
        "SELECT player_id FROM roster_players WHERE league_id = ?", (league_id,)
    ).fetchall()
    return set(r["player_id"] for r in rows)


def get_free_agents_ranked(conn, league_id, r_type, r_format, tv_format, position, week=0):
    rostered_ids = get_rostered_ids(conn, league_id)
    if not rostered_ids:
        rostered_ids = {"__none__"}

    params = [tv_format, r_type, r_format, week, position] + list(rostered_ids)
    return conn.execute("""
        SELECT r.player_id, r.player_name as full_name, 
            COALESCE(r.position, p.position, '') as position,
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
    """.format(",".join("?" * len(rostered_ids))), params).fetchall()
