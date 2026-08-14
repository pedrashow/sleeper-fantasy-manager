import streamlit as st
import sqlite3
import requests
import os
import sys
import math
import json
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from style import setup
setup("Draft Assistant", "🎯")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fantasy.db")
SLEEPER_API = "https://api.sleeper.app/v1"

POS_COLORS = {
    "QB": "#e74c6f",
    "RB": "#4caf8a",
    "WR": "#4a9bd9",
    "TE": "#e8a838",
    "K": "#9b7fc4",
    "DEF": "#7f8c8d",
    "DST": "#7f8c8d",
}

POS_PASTEL = {
    "QB": "#fce4e4",
    "RB": "#e0f5e0",
    "WR": "#ddeeff",
    "TE": "#fef0dd",
    "K": "#ede0f5",
    "DEF": "#e5e8ea",
    "DST": "#e5e8ea",
}

if not os.path.exists(DB_PATH):
    st.error("Banco não encontrado.")
    st.stop()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def sleeper_get(path):
    resp = requests.get(f"{SLEEPER_API}{path}", timeout=15)
    resp.raise_for_status()
    return resp.json()


def normal_sf(x, mu, sigma):
    if sigma <= 0:
        return 0.0 if x >= mu else 1.0
    return 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))


def pick_availability(pick_number, avg_adp, best, worst):
    if avg_adp is None or best is None or worst is None:
        return None
    try:
        avg_adp = float(avg_adp)
        best = float(best)
        worst = float(worst)
    except (TypeError, ValueError):
        return None
    std = (worst - best) / 4
    if std <= 0:
        std = 1.0
    prob = 1.0 - normal_sf(pick_number, avg_adp, std)
    return round(prob * 100, 1)


import random

def get_intermediate_picks(next_pick, my_next_pick, draft_type, num_teams):
    intermediate = []
    for pick_num in range(next_pick, my_next_pick):
        rd = ((pick_num - 1) // num_teams) + 1
        if draft_type == "snake":
            slot = num_teams - ((pick_num - 1) % num_teams) if rd % 2 == 0 else ((pick_num - 1) % num_teams) + 1
        else:
            slot = ((pick_num - 1) % num_teams) + 1
        intermediate.append({"pick_num": pick_num, "slot": slot})
    return intermediate


def get_team_drafted_positions(picks, slot_to_roster, draft_type, num_teams):
    team_positions = {}
    for p in picks:
        pick_no = p.get("pick_no", 0)
        rd = p.get("round", 1)
        if draft_type == "snake":
            slot = num_teams - ((pick_no - 1) % num_teams) if rd % 2 == 0 else ((pick_no - 1) % num_teams) + 1
        else:
            slot = ((pick_no - 1) % num_teams) + 1
        rid = slot_to_roster.get(str(slot))
        if rid is None:
            continue
        pos = p.get("metadata", {}).get("position", "")
        if rid not in team_positions:
            team_positions[rid] = []
        if pos:
            team_positions[rid].append(pos)
    return team_positions


def compute_team_need_multiplier(pos, team_drafted, roster_positions_json):
    roster_positions = json.loads(roster_positions_json) if isinstance(roster_positions_json, str) else roster_positions_json
    required = {}
    for rp in roster_positions:
        if rp in ("BN", "IR"):
            continue
        if rp in ("FLEX", "SUPER_FLEX", "REC_FLEX", "WRRB_FLEX"):
            continue
        required[rp] = required.get(rp, 0) + 1

    counts = {}
    for dp in team_drafted:
        counts[dp] = counts.get(dp, 0) + 1

    filled = counts.get(pos, 0)
    needed = required.get(pos, 0)

    if filled < needed:
        return 2.0
    total_drafted = len(team_drafted)
    if total_drafted < 3:
        return 1.2
    return 1.0


def simulate_picks_monte_carlo(
    next_pick, my_next_pick, draft_type, num_teams,
    slot_to_roster, picks, available_df, roster_positions_json,
    n_simulations=1000, top_n_candidates=30
):
    if not my_next_pick or my_next_pick <= next_pick:
        return {}

    intermediate = get_intermediate_picks(next_pick, my_next_pick, draft_type, num_teams)
    if not intermediate:
        return {}

    team_positions = get_team_drafted_positions(picks, slot_to_roster, draft_type, num_teams)

    candidates = available_df.head(top_n_candidates)
    player_names = candidates["player_name"].tolist()
    player_pos = candidates["pos"].tolist()
    player_ranks = candidates["rank"].tolist()
    player_tiers = candidates["pos_tier"].tolist()

    max_rank = max(player_ranks) if player_ranks else 1

    tier_counts = {}
    for i, name in enumerate(player_names):
        pos = player_pos[i]
        tier = player_tiers[i]
        key = (pos, tier)
        tier_counts[key] = tier_counts.get(key, 0) + 1

    survived = {name: 0 for name in player_names}

    for _ in range(n_simulations):
        pool_available = list(range(len(player_names)))
        sim_team_positions = {rid: list(positions) for rid, positions in team_positions.items()}
        remaining_tier_counts = dict(tier_counts)

        for step in intermediate:
            if not pool_available:
                break

            slot = step["slot"]
            rid = slot_to_roster.get(str(slot))
            if rid is None:
                continue

            team_drafted = sim_team_positions.get(rid, [])

            scores = []
            for idx in pool_available:
                pos = player_pos[idx]
                rank = player_ranks[idx]
                tier = player_tiers[idx]

                rank_score = (max_rank - rank + 1) / max_rank

                need_mult = compute_team_need_multiplier(pos, team_drafted, roster_positions_json)

                tier_key = (pos, tier)
                remaining = remaining_tier_counts.get(tier_key, 0)
                tier_bonus = 1.3 if remaining <= 2 and remaining > 0 else 1.0

                score = rank_score * need_mult * tier_bonus
                scores.append(max(score, 0.01))

            total = sum(scores)
            weights = [s / total for s in scores]

            chosen_idx = random.choices(pool_available, weights=weights, k=1)[0]

            chosen_pos = player_pos[chosen_idx]
            chosen_tier = player_tiers[chosen_idx]
            tier_key = (chosen_pos, chosen_tier)
            if tier_key in remaining_tier_counts:
                remaining_tier_counts[tier_key] = max(0, remaining_tier_counts[tier_key] - 1)

            if rid not in sim_team_positions:
                sim_team_positions[rid] = []
            sim_team_positions[rid].append(chosen_pos)

            pool_available.remove(chosen_idx)

        for idx in pool_available:
            survived[player_names[idx]] += 1

    result = {}
    for name, count in survived.items():
        result[name] = round(count / n_simulations * 100, 1)

    return result


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


def count_position_needs(drafted_positions, roster_positions_json):
    roster_positions = json.loads(roster_positions_json)
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


def load_targets(conn, draft_id):
    try:
        rows = conn.execute(
            "SELECT player_id, type FROM draft_targets WHERE draft_id = ?",
            (draft_id,)
        ).fetchall()
        targets = set()
        avoids = set()
        for r in rows:
            if r["type"] == "target":
                targets.add(r["player_id"])
            elif r["type"] == "avoid":
                avoids.add(r["player_id"])
        return targets, avoids
    except Exception:
        return set(), set()


def save_targets(conn, draft_id, targets, avoids):
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS draft_targets (
                draft_id TEXT,
                player_id TEXT,
                type TEXT,
                PRIMARY KEY (draft_id, player_id, type)
            )
        """)
        conn.execute("DELETE FROM draft_targets WHERE draft_id = ?", (draft_id,))
        for pid in targets:
            conn.execute(
                "INSERT OR IGNORE INTO draft_targets (draft_id, player_id, type) VALUES (?, ?, ?)",
                (draft_id, pid, "target")
            )
        for pid in avoids:
            conn.execute(
                "INSERT OR IGNORE INTO draft_targets (draft_id, player_id, type) VALUES (?, ?, ?)",
                (draft_id, pid, "avoid")
            )
        conn.commit()
    except Exception as e:
        st.error(f"Erro ao salvar targets: {e}")


def compute_recommendations(available_df, needs, pos_counts):
    recs = {}

    if not available_df.empty:
        bpa = available_df.iloc[0]
        recs["bpa"] = {
            "name": bpa.get("player_name", ""),
            "pos": bpa.get("pos", ""),
            "rank": bpa.get("rank", ""),
            "pos_rank": bpa.get("position_rank", ""),
        }

    for pos in ["QB", "RB", "WR", "TE"]:
        if needs.get(pos, 0) > 0:
            pos_available = available_df[available_df["pos"] == pos]
            if not pos_available.empty:
                top = pos_available.iloc[0]
                if pos not in recs.get("needs", {}):
                    if "needs" not in recs:
                        recs["needs"] = {}
                    recs["needs"][pos] = {
                        "name": top.get("player_name", ""),
                        "rank": top.get("rank", ""),
                        "pos_rank": top.get("position_rank", ""),
                        "shortfall": needs[pos],
                    }
    return recs


def compute_scarcity(available_df):
    alerts = []
    for pos in ["QB", "RB", "WR", "TE"]:
        pos_df = available_df[available_df["pos"] == pos]
        if pos_df.empty:
            continue

        tiers = pos_df["pos_tier"].dropna().unique()
        for tier in sorted(tiers)[:3]:
            tier_count = len(pos_df[pos_df["pos_tier"] == tier])
            if tier_count <= 3 and tier_count > 0:
                tier_players = pos_df[pos_df["pos_tier"] == tier]["player_name"].tolist()
                alerts.append({
                    "pos": pos,
                    "tier": int(tier),
                    "count": tier_count,
                    "players": tier_players,
                })
    return alerts


def render_intelligence_panel(recs, scarcity, needs):
    html = '<div style="border:1px solid #444;border-radius:8px;padding:12px;margin-bottom:16px;background:#1a1a2e;">'
    html += '<div style="color:#e8a838;font-weight:bold;font-size:14px;margin-bottom:8px;">💡 RECOMENDAÇÃO</div>'

    if "bpa" in recs:
        bpa = recs["bpa"]
        color = POS_COLORS.get(bpa["pos"], "#888")
        html += f'<div style="font-size:13px;padding:2px 0;"><span style="color:#aaa;">BPA:</span> '
        html += f'<span style="background:{color};color:#fff;padding:1px 4px;border-radius:3px;font-size:9px;font-weight:bold;">{bpa["pos"]}</span> '
        html += f'<span style="color:#eee;font-weight:bold;">{bpa["name"]}</span> '
        html += f'<span style="color:#888;">#{bpa["rank"]} ({bpa["pos_rank"]})</span></div>'

    if recs.get("needs"):
        for pos, info in recs["needs"].items():
            color = POS_COLORS.get(pos, "#888")
            html += f'<div style="font-size:13px;padding:2px 0;"><span style="color:#e74c6f;">NEED {pos} (falta {info["shortfall"]}):</span> '
            html += f'<span style="color:#eee;font-weight:bold;">{info["name"]}</span> '
            html += f'<span style="color:#888;">#{info["rank"]} ({info["pos_rank"]})</span></div>'

    if scarcity:
        html += '<div style="margin-top:6px;border-top:1px solid #333;padding-top:6px;">'
        for alert in scarcity:
            color = POS_COLORS.get(alert["pos"], "#888")
            players_str = ", ".join(alert["players"][:3])
            html += f'<div style="font-size:12px;padding:1px 0;color:#e8a838;">⚠️ {alert["pos"]} Tier {alert["tier"]}: '
            html += f'restam {alert["count"]} — {players_str}</div>'
        html += '</div>'

    if not recs.get("needs") and "bpa" in recs:
        html += '<div style="font-size:12px;color:#4caf8a;margin-top:4px;">✅ Starters completos. Foco em BPA.</div>'

    html += '</div>'
    return html


def render_board_html(picks, slot_to_roster, draft_type, num_rounds, num_teams, league_id, conn, my_roster_id, adp_lookup=None):
    slot_names = {}
    for slot_str, rid in slot_to_roster.items():
        slot_num = int(slot_str)
        owner_row = conn.execute(
            "SELECT display_name FROM users WHERE roster_id = ? AND league_id = ?",
            (rid, league_id),
        ).fetchone()
        slot_names[slot_num] = owner_row["display_name"] if owner_row else f"Slot {slot_num}"

    board = {}
    for p in picks:
        pick_no = p.get("pick_no", 0)
        rd = p.get("round", 1)
        if draft_type == "snake":
            slot = num_teams - ((pick_no - 1) % num_teams) if rd % 2 == 0 else ((pick_no - 1) % num_teams) + 1
        else:
            slot = ((pick_no - 1) % num_teams) + 1
        meta = p.get("metadata", {})
        player_name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        if rd not in board:
            board[rd] = {}
        board[rd][slot] = {
            "first": meta.get("first_name", ""),
            "last": meta.get("last_name", ""),
            "pos": meta.get("position", ""),
            "pick_no": pick_no,
            "player_name": player_name,
        }

    all_slots = sorted(slot_names.keys()) if slot_names else list(range(1, num_teams + 1))

    css = """<style>
    .board-table {border-collapse:collapse;width:100%;font-size:14px;table-layout:fixed;}
    .board-table th {padding:10px 4px;color:#aaa;text-align:center;background:#1a1a2e;font-size:11px;border:1px solid #111;overflow:hidden;text-overflow:ellipsis;}
    .board-table td {padding:12px 6px;vertical-align:middle;border:1px solid #111;}
    .board-table .my-th {background:#2a2a4e;color:#e8c84a;font-weight:bold;}
    .board-table .my-border {outline:2px solid #e8c84a;outline-offset:-2px;}
    .board-empty {background:#1e1e2e;text-align:center;color:#333;}
    .board-empty-mine {background:#2a2a4e;text-align:center;color:#555;}
    </style>"""

    html = css + '<div style="overflow-x:auto;"><table class="board-table"><tr>'
    for slot in all_slots:
        name = slot_names.get(slot, f"S{slot}")
        rid = slot_to_roster.get(str(slot))
        cls = ' class="my-th"' if rid == my_roster_id else ""
        html += f"<th{cls}>{name}</th>"
    html += "</tr>"

    for rd in range(1, num_rounds + 1):
        html += "<tr>"
        for slot in all_slots:
            rid = slot_to_roster.get(str(slot))
            is_mine = rid == my_roster_id
            pick = board.get(rd, {}).get(slot)
            if pick:
                pos = pick["pos"]
                bg = POS_PASTEL.get(pos, "#e5e8ea")
                mine_cls = ' class="my-border"' if is_mine else ""

                tooltip = ""
                left_border = ""
                if adp_lookup and pick.get("player_name") in adp_lookup:
                    adp = adp_lookup[pick["player_name"]]
                    if adp and adp > 0:
                        diff = int(adp - pick["pick_no"])
                        if diff >= 4:
                            left_border = "border-left:3px solid #2e8b57;"
                            tooltip = f' title="STEAL ↑{diff} (ADP {adp:.0f}, Pick {pick["pick_no"]})"'
                        elif diff <= -4:
                            left_border = "border-left:3px solid #c0392b;"
                            tooltip = f' title="REACH ↓{abs(diff)} (ADP {adp:.0f}, Pick {pick["pick_no"]})"'
                        else:
                            tooltip = f' title="ADP {adp:.0f}, Pick {pick["pick_no"]}"'

                html += f'<td{mine_cls} style="background:{bg};{left_border}"{tooltip}>'
                html += f'<span style="color:#1a1a1a;font-size:11px;display:block;line-height:1.2;">{pick["first"]}</span>'
                html += f'<span style="color:#1a1a1a;font-weight:bold;font-size:14px;display:block;line-height:1.2;">{pick["last"]}</span>'
                html += "</td>"
            else:
                cls = "board-empty-mine" if is_mine else "board-empty"
                html += f'<td class="{cls}">-</td>'
        html += "</tr>"

    html += "</table></div>"
    return html


def render_rankings_main(df, targets, my_next_pick=None, num_teams=12, use_pos_tier=False):
    css = """<style>
    .rl {width:100%;}
    .rl-row {padding:5px 4px;border-bottom:1px solid #ccc;border-radius:4px;margin-bottom:2px;}
    .rl-tgt {outline:2px solid #c9a227;outline-offset:-1px;}
    .rl-n {color:#1a1a1a;font-weight:bold;font-size:15px;}
    .rl-n a:hover {text-decoration:underline !important;}
    .rl-d {display:flex;align-items:center;gap:6px;margin-top:2px;font-size:14px;}
    .rl-rk {color:#555;}
    .rl-pb {color:#fff;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:bold;}
    .rl-tm {color:#555;}
    .rl-fp {color:#333;font-size:13px;font-weight:bold;}
    .rl-meta {color:#555;}
    .rl-tv {color:#333;}
    .rl-lb {color:#8b6914;font-size:13px;font-weight:bold;}
    .rl-av {font-weight:bold;margin-left:auto;}
    .rl-hi {color:#2e7d32;} .rl-md {color:#e65100;} .rl-lo {color:#c62828;}
    .rl-sep {border-bottom:3px solid #999;height:2px;margin:2px 0;}
    </style>"""

    tier_field = "pos_tier" if use_pos_tier else "tier"

    POS_BG = {
        "QB": "#fce4e4",
        "RB": "#e0f5e0",
        "WR": "#ddeeff",
        "TE": "#fef0dd",
    }

    html = css + '<div style="overflow-y:auto;max-height:700px;">'
    current_tier = None

    for _, row in df.iterrows():
        tier = row.get(tier_field)
        if pd.notna(tier) and tier != current_tier:
            if current_tier is not None:
                html += '<div class="rl-sep"></div>'
            current_tier = tier

        pos = str(row.get("pos", ""))
        color = POS_COLORS.get(pos, "#888")
        name = str(row.get("player_name", ""))
        team = str(row.get("team", ""))
        fp_pos_rank = str(row.get("position_rank", "")) if pd.notna(row.get("position_rank")) else ""

        is_target = name in targets
        row_cls = "rl-row rl-tgt" if is_target else "rl-row"
        pos_bg = POS_BG.get(pos, "transparent")
        row_style = f' style="background:{pos_bg};"'

        tv_val = row.get("tv_value")
        tv_str = f'<span class="rl-tv">{int(tv_val)}</span>' if pd.notna(tv_val) and tv_val else ""

        lb_rank = row.get("lb_pos_rank")
        lb_str = ""
        if pd.notna(lb_rank) and lb_rank:
            lb_str = f' / <span class="rl-lb">{lb_rank}</span>'

        avail = row.get("avail_pct")
        avail_str = ""
        if pd.notna(avail) and avail is not None:
            v = float(avail)
            cls = "rl-hi" if v >= 70 else "rl-md" if v >= 40 else "rl-lo"
            avail_str = f'<span class="rl-av {cls}">{v:.0f}%</span>'

        html += f'<div class="{row_cls}"{row_style}>'
        star_icon = "⭐" if is_target else ""
        html += f'<div class="rl-n">{star_icon} {name}</div>'
        html += f'<div class="rl-d">'
        html += f'<span class="rl-fp">{fp_pos_rank}</span>'
        html += lb_str
        html += f'<span class="rl-tm">{team}</span>'
        adp = format_adp(row.get("avg_adp"), num_teams)
        if adp:
            html += f'<span class="rl-meta">{adp}</span>'
        html += tv_str
        html += avail_str
        html += '</div></div>'

    html += '</div>'
    return html


# === SESSION STATE ===

if "targets" not in st.session_state:
    st.session_state.targets = set()
if "avoids" not in st.session_state:
    st.session_state.avoids = set()

conn = get_db()

leagues = conn.execute(
    "SELECT league_id, name, league_type, scoring_type, is_superflex, is_tep, total_rosters, ranking_format, draft_id, draft_rounds, roster_positions, has_kicker, has_dst FROM leagues ORDER BY name"
).fetchall()

if not leagues:
    st.warning("Nenhuma liga encontrada. Faça o Sync primeiro.")
    st.stop()

# === SIDEBAR — apenas seleção de liga ===

league_options = {f"{lg['name']} ({lg['league_type']} {lg['scoring_type']})": dict(lg) for lg in leagues}
selected_label = st.sidebar.selectbox("Liga", list(league_options.keys()))
league = league_options[selected_label]

username = st.sidebar.text_input("Username Sleeper", value="pedrashow")

draft_id = league.get("draft_id")
if not draft_id:
    st.error("Essa liga não tem draft configurado.")
    st.stop()

if st.sidebar.button("🔄 Atualizar Draft", use_container_width=True) or "draft_data" not in st.session_state:
    try:
        st.session_state.draft_data = sleeper_get(f"/draft/{draft_id}")
        st.session_state.draft_picks = sleeper_get(f"/draft/{draft_id}/picks")
        user_info = sleeper_get(f"/user/{username}")
        st.session_state.my_user_id = user_info["user_id"]
    except Exception as e:
        st.error(f"Erro ao conectar com Sleeper: {e}")
        st.stop()

draft = st.session_state.draft_data
picks = st.session_state.draft_picks
my_user_id = st.session_state.get("my_user_id")

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
if my_user_id:
    roster_row = conn.execute(
        "SELECT roster_id FROM users WHERE user_id = ? AND league_id = ?",
        (my_user_id, league.get("league_id")),
    ).fetchone()
    if roster_row:
        my_roster_id = roster_row["roster_id"]

my_slot = None
if my_roster_id and draft_order:
    for uid, slot in draft_order.items():
        user_roster = conn.execute(
            "SELECT roster_id FROM users WHERE user_id = ? AND league_id = ?",
            (uid, league.get("league_id")),
        ).fetchone()
        if user_roster and user_roster["roster_id"] == my_roster_id:
            my_slot = slot
            break

# Picks processing
picked_player_ids = set()
picked_player_names = set()
my_picks = []

for p in picks:
    pid = p.get("player_id")
    if pid:
        picked_player_ids.add(str(pid))
    name = f"{p.get('metadata', {}).get('first_name', '')} {p.get('metadata', {}).get('last_name', '')}".strip()
    if name:
        picked_player_names.add(name)
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

all_available_df = pd.read_sql_query("""
    SELECT r.rank, r.player_name, COALESCE(p.position, '') as pos,
        COALESCE(p.team, '') as team, r.tier, r.pos_tier, r.avg_adp, r.best, r.worst,
        r.bye_week, r.position_rank, r.owned_pct,
        COALESCE(p.player_id, '') as player_id,
        tv.tv_value, tv.tv_trend,
        lb.lb_rank, lb.lb_tier,
        CASE WHEN lb.lb_rank IS NOT NULL THEN COALESCE(p.position,'') || lb.lb_rank ELSE NULL END as lb_pos_rank,
        wn.wn_rank, wn.wn_tier,
        CASE WHEN wn.wn_rank IS NOT NULL THEN COALESCE(p.position,'') || wn.wn_rank ELSE NULL END as wn_pos_rank
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
""", conn, params=[tv_format, ranking_type_db, ranking_format])

all_available_df = all_available_df[
    ~all_available_df["player_id"].isin(picked_player_ids) &
    ~all_available_df["player_name"].isin(picked_player_names)
]

all_available_df["adp_fmt"] = all_available_df["avg_adp"].apply(lambda x: format_adp(x, num_teams))

name_to_id = dict(zip(all_available_df["player_name"], all_available_df["player_id"]))
id_to_name = dict(zip(all_available_df["player_id"], all_available_df["player_name"]))

db_targets, db_avoids = load_targets(conn, draft_id)

if "targets_initialized" not in st.session_state or st.session_state.get("targets_draft_id") != draft_id:
    st.session_state.targets = db_targets
    st.session_state.avoids = db_avoids
    st.session_state.targets_initialized = True
    st.session_state.targets_draft_id = draft_id

target_names = {id_to_name.get(pid, pid) for pid in st.session_state.targets if id_to_name.get(pid)}
avoid_names = {id_to_name.get(pid, pid) for pid in st.session_state.avoids if id_to_name.get(pid)}

all_available_df = all_available_df[~all_available_df["player_id"].isin(st.session_state.avoids)]
all_names = all_available_df["player_name"].tolist()

# === MAIN CONTENT ===

rt_label = {"rookie": "Rookie", "startup": "Startup", "redraft": "Redraft"}.get(ranking_type, ranking_type)
status_emoji = {"pre_draft": "⏳", "drafting": "🟢", "complete": "✅"}.get(draft_status, "")

current_pick_fmt = format_adp(next_pick, num_teams)

recs = compute_recommendations(all_available_df, needs, pos_counts)
scarcity = compute_scarcity(all_available_df)

bpa_text = ""
need_text = ""
if recs.get("bpa"):
    b = recs["bpa"]
    bpa_text = f'BPA: <strong>{b["name"]}</strong> #{b["rank"]} ({b.get("pos_rank","")})'
if recs.get("needs"):
    first_need = list(recs["needs"].values())[0]
    need_text = f'NEED: <strong>{first_need["name"]}</strong> #{first_need["rank"]} ({first_need.get("pos_rank","")})'

if my_next_pick:
    picks_until = my_next_pick - next_pick
    my_pick_fmt = format_adp(my_next_pick, num_teams)
    if picks_until == 0:
        clock_text = f'<span style="color:#4caf8a;font-weight:bold;font-size:16px;">🟢 SUA VEZ! Pick {current_pick_fmt}</span>'
    else:
        clock_text = f'<strong>{current_pick_fmt}</strong> → <span style="color:#e8c84a;">{my_pick_fmt}</span> ({picks_until})'
else:
    clock_text = f'<strong>{current_pick_fmt}</strong>'

header_html = f'''<div style="display:flex;align-items:center;gap:12px;padding:6px 10px;background:#1a1a2e;border-radius:6px;margin-bottom:8px;flex-wrap:wrap;">
<span style="font-size:14px;color:#eee;">{clock_text}</span>
<span style="color:#555;">|</span>
<span style="font-size:12px;color:#888;">{status_emoji} {rt_label} · {len(picks)}/{num_rounds * num_teams} · {draft_type} {num_teams}t</span>
<span style="color:#555;">|</span>
<span style="font-size:12px;color:#4a9bd9;">{bpa_text}</span>
<span style="font-size:12px;color:#e8a838;">{need_text}</span>
</div>'''

col_header, col_refresh = st.columns([6, 1])
with col_header:
    st.markdown(header_html, unsafe_allow_html=True)
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        try:
            st.session_state.draft_data = sleeper_get(f"/draft/{draft_id}")
            st.session_state.draft_picks = sleeper_get(f"/draft/{draft_id}/picks")
            st.rerun()
        except Exception as e:
            st.error(f"Erro: {e}")

adp_lookup = {}
adp_rows = conn.execute(
    "SELECT player_name, avg_adp FROM rankings WHERE ranking_type = ? AND format = ? AND week = 0 AND avg_adp IS NOT NULL",
    (ranking_type_db, ranking_format)
).fetchall()
for row in adp_rows:
    adp_lookup[row["player_name"]] = row["avg_adp"]

# === TABS: Board e Meu Time no mesmo nível ===

tab_board, tab_available, tab_team = st.tabs(["📊 Board + Rankings", "🔎 Busca Avançada", "👤 Meu Time"])

with tab_board:
    col_board, col_list = st.columns([4, 1])

    with col_board:
        if not picks:
            st.info("Nenhum pick realizado ainda.")
        else:
            board_html = render_board_html(
                picks, slot_to_roster, draft_type, num_rounds, num_teams,
                league.get("league_id"), conn, my_roster_id, adp_lookup
            )
            st.markdown(board_html, unsafe_allow_html=True)

    with col_list:
        list_pos_filter = st.selectbox("Posição", ["ALL", "QB", "RB", "WR", "TE"], key="list_pos", label_visibility="collapsed")

        if list_pos_filter != "ALL":
            list_df = all_available_df[all_available_df["pos"] == list_pos_filter].copy()
        else:
            list_df = all_available_df.copy()

        if my_next_pick and my_next_pick > next_pick:
            mc_cache_key = f"mc_{draft_id}_{len(picks)}_{my_next_pick}"
            if st.session_state.get("mc_cache_key") != mc_cache_key:
                mc_results = simulate_picks_monte_carlo(
                    next_pick, my_next_pick, draft_type, num_teams,
                    slot_to_roster, picks, all_available_df,
                    league.get("roster_positions", "[]"),
                    n_simulations=1000, top_n_candidates=30
                )
                st.session_state.mc_results = mc_results
                st.session_state.mc_cache_key = mc_cache_key
            else:
                mc_results = st.session_state.mc_results
            list_df["avail_pct"] = list_df["player_name"].map(lambda n: mc_results.get(n))
        elif my_next_pick and my_next_pick == next_pick:
            list_df["avail_pct"] = 100.0
        else:
            list_df["avail_pct"] = None

        use_pos_tier = list_pos_filter != "ALL"
        tier_field = "pos_tier" if use_pos_tier else "tier"
        current_tier = None
        targets_changed = False
        list_container = st.container(height=700)

        with list_container:
            for idx, (_, row) in enumerate(list_df.head(50).iterrows()):
                tier = row.get(tier_field)
                if pd.notna(tier) and tier != current_tier:
                    if current_tier is not None:
                        st.divider()
                    current_tier = tier

                pos = str(row.get("pos", ""))
                name = str(row.get("player_name", ""))
                team = str(row.get("team", ""))
                fp_pos_rank = str(row.get("position_rank", "")) if pd.notna(row.get("position_rank")) else ""
                lb_rank = row.get("lb_pos_rank")
                lb_str = str(lb_rank) if pd.notna(lb_rank) and lb_rank else ""
                wn_rank = row.get("wn_pos_rank")
                wn_str = str(wn_rank) if pd.notna(wn_rank) and wn_rank else ""
                adp = format_adp(row.get("avg_adp"), num_teams)
                tv_val = row.get("tv_value")
                tv_str = str(int(tv_val)) if pd.notna(tv_val) and tv_val else ""
                avail = row.get("avail_pct")
                avail_str = f"{avail:.0f}%" if pd.notna(avail) and avail is not None else ""

                POS_BG = {"QB": "#fce4e4", "RB": "#e0f5e0", "WR": "#ddeeff", "TE": "#fef0dd"}
                bg = POS_BG.get(pos, "#f0f0f0")

                is_target = name in target_names
                cb = st.checkbox(
                    name,
                    value=is_target,
                    key=f"fav_{idx}_{name}",
                    label_visibility="collapsed"
                )

                if cb != is_target:
                    pid = name_to_id.get(name)
                    if pid:
                        if cb:
                            st.session_state.targets.add(pid)
                        else:
                            st.session_state.targets.discard(pid)
                        targets_changed = True

                detail_parts = [fp_pos_rank]
                if lb_str:
                    detail_parts.append(f"/ {lb_str}")
                if wn_str:
                    detail_parts.append(f"/ {wn_str}")
                detail_parts.append(team)
                if adp:
                    detail_parts.append(adp)
                if tv_str:
                    detail_parts.append(tv_str)
                if avail_str:
                    detail_parts.append(avail_str)
                detail = " · ".join([p for p in detail_parts if p])

                star = "⭐ " if cb else ""
                info_html = f'''<div style="background:{bg};border-radius:4px;padding:5px 8px;margin-top:-35px;margin-bottom:4px;">
<div style="color:#1a1a1a;font-weight:bold;font-size:14px;">{star}{name}</div>
<div style="color:#333;font-size:12px;">{detail}</div>
</div>'''
                st.markdown(info_html, unsafe_allow_html=True)

        if targets_changed:
            save_targets(conn, draft_id, st.session_state.targets, st.session_state.avoids)

with tab_available:
    col_pos, col_search = st.columns([1, 3])
    with col_pos:
        positions = ["ALL", "QB", "RB", "WR", "TE"]
        if league.get("has_kicker"):
            positions.append("K")
        if league.get("has_dst"):
            positions.append("DST")
        pos_filter = st.selectbox("Posição", positions, key="avail_pos")
    with col_search:
        search = st.text_input("Buscar", placeholder="Nome do jogador", key="avail_search")

    available_df = all_available_df.copy()

    if pos_filter != "ALL":
        available_df = available_df[available_df["pos"] == pos_filter]

    if search:
        available_df = available_df[available_df["player_name"].str.contains(search, case=False, na=False)]

    if my_next_pick and my_next_pick > next_pick:
        available_df["Avail%"] = available_df["player_name"].map(lambda n: st.session_state.get("mc_results", {}).get(n))
    elif my_next_pick and my_next_pick == next_pick:
        available_df["Avail%"] = 100.0

    with st.expander(f"⭐ Targets ({len(st.session_state.targets)})"):
        current_target_names = sorted([id_to_name[pid] for pid in st.session_state.targets if pid in id_to_name and id_to_name[pid] in all_names])
        st.session_state.board_target_select = current_target_names
        board_targets = st.multiselect(
            "Adicionar/remover targets",
            all_names,
            key="board_target_select",
            label_visibility="collapsed"
        )
        new_target_ids = {name_to_id[n] for n in board_targets if n in name_to_id}
        if new_target_ids != st.session_state.targets:
            st.session_state.targets = new_target_ids
            save_targets(conn, draft_id, st.session_state.targets, st.session_state.avoids)

    with st.expander(f"❌ Avoids ({len(st.session_state.avoids)})"):
        current_avoid_names = sorted([id_to_name[pid] for pid in st.session_state.avoids if pid in id_to_name and id_to_name[pid] in all_names])
        st.session_state.avoid_select = current_avoid_names
        new_avoids = st.multiselect(
            "Adicionar/remover",
            all_names,
            key="avoid_select",
            label_visibility="collapsed"
        )
        new_avoid_ids = {name_to_id[n] for n in new_avoids if n in name_to_id}
        if new_avoid_ids != st.session_state.avoids:
            st.session_state.avoids = new_avoid_ids
            save_targets(conn, draft_id, st.session_state.targets, st.session_state.avoids)

    show_targets_only = st.checkbox("Mostrar apenas targets ⭐", key="avail_targets_only")
    if show_targets_only:
        available_df = available_df[available_df["player_id"].isin(st.session_state.targets)]

    def extract_rank_num(val):
        if pd.isna(val) or not val:
            return None
        import re
        m = re.search(r'(\d+)', str(val))
        return int(m.group(1)) if m else None

    available_df["position_rank"] = available_df["position_rank"].apply(extract_rank_num)
    available_df["lb_pos_rank"] = available_df["lb_pos_rank"].apply(extract_rank_num)
    available_df["wn_pos_rank"] = available_df["wn_pos_rank"].apply(extract_rank_num)
    available_df["Δ LB"] = available_df["position_rank"] - available_df["lb_pos_rank"]
    available_df["Δ WN"] = available_df["position_rank"] - available_df["wn_pos_rank"]

    display_cols = ["rank", "player_name", "pos", "team", "position_rank", "lb_pos_rank", "wn_pos_rank", "Δ LB", "Δ WN", "tier", "pos_tier", "lb_tier", "wn_tier", "adp_fmt", "bye_week"]
    col_rename = {
        "rank": "#", "player_name": "Jogador", "pos": "Pos", "team": "Time",
        "position_rank": "FP#", "lb_pos_rank": "LB#", "wn_pos_rank": "WN#",
        "tier": "Tier", "pos_tier": "Pos Tier",
        "lb_tier": "LB T", "wn_tier": "WN T",
        "adp_fmt": "ADP", "bye_week": "Bye"
    }

    if "Avail%" in available_df.columns:
        display_cols.append("Avail%")
    if "tv_value" in available_df.columns:
        display_cols.extend(["tv_value", "tv_trend"])
        col_rename["tv_value"] = "TV"
        col_rename["tv_trend"] = "Trend"

    display_df = available_df[display_cols].rename(columns=col_rename).reset_index(drop=True)

    tier_col = "Pos Tier" if pos_filter != "ALL" else "Tier"
    show_tiers = st.checkbox("Agrupar por tier", value=True, key="avail_tiers")

    st.text(f"{len(display_df)} disponíveis")

    if show_tiers and tier_col in display_df.columns:
        tiers = sorted(display_df[tier_col].dropna().unique())
        for tier in tiers:
            tier_df = display_df[display_df[tier_col] == tier].reset_index(drop=True)
            st.markdown(f"**Tier {int(tier)}** ({len(tier_df)})")
            st.dataframe(tier_df, use_container_width=True, hide_index=True)
    else:
        st.dataframe(display_df, use_container_width=True, hide_index=True)


with tab_team:
    if not my_picks:
        st.info("Você ainda não fez nenhum pick.")
    else:
        st.subheader("Picks realizados")
        team_rows = []
        for p in my_picks:
            meta = p.get("metadata", {})
            team_rows.append({
                "Pick": p.get("pick_no"),
                "Round": p.get("round"),
                "Jogador": f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip(),
                "Pos": meta.get("position", ""),
                "Time NFL": meta.get("team", ""),
            })
        st.table(team_rows)

    st.subheader("Necessidades Posicionais")
    roster_positions = json.loads(league.get("roster_positions", "[]"))
    starter_slots = [p for p in roster_positions if p != "BN"]

    slot_summary = []
    for slot in ["QB", "RB", "WR", "TE"]:
        required = starter_slots.count(slot)
        have = pos_counts.get(slot, 0)
        status = "✅" if have >= required else f"⚠️ Falta {required - have}"
        slot_summary.append({"Posição": slot, "Starter": required, "Draftado": have, "Status": status})

    flex_count = starter_slots.count("FLEX") + starter_slots.count("REC_FLEX") + starter_slots.count("WRRB_FLEX")
    sf_count = starter_slots.count("SUPER_FLEX")
    if flex_count:
        slot_summary.append({"Posição": "FLEX", "Starter": flex_count, "Draftado": "-", "Status": "RB/WR/TE"})
    if sf_count:
        slot_summary.append({"Posição": "SUPER_FLEX", "Starter": sf_count, "Draftado": "-", "Status": "QB/RB/WR/TE"})

    st.table(slot_summary)

    st.subheader("Prioridades")
    priority = []
    if needs.get("QB", 0) > 0:
        priority.append(f"QB (falta {needs['QB']})")
    if needs.get("RB", 0) > 0:
        priority.append(f"RB (falta {needs['RB']})")
    if needs.get("WR", 0) > 0:
        priority.append(f"WR (falta {needs['WR']})")
    if needs.get("TE", 0) > 0:
        priority.append(f"TE (falta {needs['TE']})")

    if not priority:
        st.success("Starters completos! Foco em BPA para bench.")
    else:
        st.warning(f"Prioridades: {', '.join(priority)}")

conn.close()
