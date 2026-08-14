import json

from core.config import POS_COLORS, POS_PASTEL
from core.formats import (
    detect_ranking_type,
    map_ranking_format,
    tv_format_for_league,
    ranking_type_for_db,
    ranking_type_label,
)
from core.league_repo import get_user_id
from core.sleeper import get_draft, get_draft_picks


def load_favorites(conn, draft_id):
    targets = set()
    avoids = set()
    try:
        rows = conn.execute(
            "SELECT player_id, type FROM draft_favorites WHERE draft_id = ?",
            (draft_id,),
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


def count_position_needs(drafted_positions, roster_positions_json):
    roster_positions = (
        json.loads(roster_positions_json)
        if isinstance(roster_positions_json, str)
        else roster_positions_json
    )
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
        recs["bpa"] = {
            "name": bpa["player_name"],
            "pos": bpa["pos"],
            "rank": bpa["rank"],
            "pos_rank": bpa.get("position_rank", ""),
        }
    recs["needs"] = {}
    for pos in ["QB", "RB", "WR", "TE"]:
        if needs.get(pos, 0) > 0:
            for p in available:
                if p["pos"] == pos:
                    recs["needs"][pos] = {
                        "name": p["player_name"],
                        "rank": p["rank"],
                        "pos_rank": p.get("position_rank", ""),
                        "shortfall": needs[pos],
                    }
                    break
    return recs


def get_draft_context(conn, league):
    draft_id = league["draft_id"]
    if not draft_id:
        return None

    my_user_id = get_user_id()
    draft = get_draft(draft_id)
    picks = get_draft_picks(draft_id)

    draft_status = draft.get("status", "unknown")
    draft_type = draft.get("type", "snake")
    num_rounds = draft.get("settings", {}).get("rounds", league.get("draft_rounds") or 4)
    num_teams = league.get("total_rosters", 12)

    ranking_type = detect_ranking_type(league, live_rounds=num_rounds)
    ranking_format = map_ranking_format(league, ranking_type)
    rt_db = ranking_type_for_db(ranking_type)

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

    my_drafted_positions = [
        p.get("metadata", {}).get("position", "")
        for p in my_picks
        if p.get("metadata", {}).get("position")
    ]
    needs, pos_counts = count_position_needs(
        my_drafted_positions, league.get("roster_positions", "[]")
    )

    next_pick = len(picks) + 1
    my_next_pick = None
    if my_slot and draft_status != "complete":
        for pick_num in range(next_pick, num_rounds * num_teams + 1):
            rd = ((pick_num - 1) // num_teams) + 1
            if draft_type == "snake":
                slot = (
                    num_teams - ((pick_num - 1) % num_teams)
                    if rd % 2 == 0
                    else ((pick_num - 1) % num_teams) + 1
                )
            else:
                slot = ((pick_num - 1) % num_teams) + 1
            if slot == my_slot:
                my_next_pick = pick_num
                break

    tv_format = tv_format_for_league(league)
    targets, avoids = load_favorites(conn, draft_id)
    available = get_available_players(
        conn, rt_db, ranking_format, tv_format, picked_ids, picked_names, avoids
    )
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
    for p in picks:
        pick_no = p.get("pick_no", 0)
        rd = p.get("round", 1)
        if draft_type == "snake":
            slot = (
                num_teams - ((pick_no - 1) % num_teams)
                if rd % 2 == 0
                else ((pick_no - 1) % num_teams) + 1
            )
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

    adp_lookup = {}
    adp_rows = conn.execute(
        "SELECT player_name, avg_adp FROM rankings "
        "WHERE ranking_type = ? AND format = ? AND week = 0 AND avg_adp IS NOT NULL",
        (rt_db, ranking_format),
    ).fetchall()
    for row in adp_rows:
        adp_lookup[row["player_name"]] = row["avg_adp"]

    return {
        "draft_id": draft_id,
        "draft_status": draft_status,
        "draft_type": draft_type,
        "num_rounds": num_rounds,
        "num_teams": num_teams,
        "ranking_type": ranking_type,
        "rt_label": ranking_type_label(ranking_type),
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
