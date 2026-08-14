import streamlit as st
import sqlite3
import os
import sys
import json
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from style import setup
setup("Roster Viewer", "👥")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fantasy.db")

POS_COLORS = {
    "QB": "#e74c6f",
    "RB": "#4caf8a",
    "WR": "#4a9bd9",
    "TE": "#e8a838",
    "K": "#9b7fc4",
    "DEF": "#7f8c8d",
}

SLOT_ORDER = {"starter": 0, "bench": 1, "taxi": 2, "reserve": 3}
SLOT_LABEL = {"starter": "START", "bench": "BN", "taxi": "TX", "reserve": "IR"}

if not os.path.exists(DB_PATH):
    st.error("Banco não encontrado.")
    st.stop()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

username = st.sidebar.text_input("Username Sleeper", value="pedrashow")
show_tv = st.sidebar.checkbox("Mostrar Trade Values", value=True)
show_all_teams = st.sidebar.checkbox("Mostrar todos os times da liga", value=False)

leagues = conn.execute(
    "SELECT league_id, name, league_type, scoring_type, is_superflex, is_tep, total_rosters, ranking_format FROM leagues ORDER BY name"
).fetchall()

if not leagues:
    st.warning("Nenhuma liga encontrada.")
    st.stop()

user_row = conn.execute("SELECT DISTINCT user_id FROM users WHERE display_name = ? LIMIT 1", (username,)).fetchone()
if not user_row:
    st.error(f"Usuário '{username}' não encontrado.")
    st.stop()
my_user_id = user_row["user_id"]

league_options = {f"{lg['name']} ({lg['league_type']} {lg['scoring_type']})": dict(lg) for lg in leagues}
selected_label = st.sidebar.selectbox("Liga", list(league_options.keys()))
league = league_options[selected_label]
league_id = league["league_id"]


def tv_format_for_league(lg):
    lt = "dynasty" if lg.get("league_type") == "dynasty" else "redraft"
    sf = "sf" if lg.get("is_superflex") else "1qb"
    sc = {"ppr": "ppr", "half_ppr": "half", "standard": "half"}.get(lg.get("scoring_type", ""), "half")
    return f"{lt}_{sf}_{sc}"


def ranking_type_for_league(lg):
    return "dynasty" if lg.get("league_type") == "dynasty" else "redraft"


def ranking_format_for_league(lg):
    if lg.get("league_type") == "dynasty":
        return "sf" if lg.get("is_superflex") else "1qb"
    return lg.get("ranking_format") or "sf_half"


def get_roster_data(conn, league_id, roster_id, tv_format, r_type, r_format):
    tv_join = ""
    tv_cols = ""
    tv_params = []
    if tv_format:
        tv_join = "LEFT JOIN trade_values tv ON rp.player_id = tv.player_id AND tv.source = 'fantasycalc' AND tv.format = ?"
        tv_cols = ", tv.value as tv_value, tv.trend_30day as tv_trend"
        tv_params = [tv_format]

    r_params = [r_type, r_format]

    params = tv_params + r_params + [league_id, roster_id]

    rows = conn.execute(f"""
        SELECT p.full_name, p.position, p.team, p.age, p.injury_status,
            rp.slot, rp.player_id,
            r.rank, r.tier, r.pos_tier, r.position_rank
            {tv_cols}
        FROM roster_players rp
        JOIN players p ON rp.player_id = p.player_id
        LEFT JOIN rankings r ON r.player_id = rp.player_id AND r.ranking_type = ? AND r.format = ? AND r.week = 0
        {tv_join}
        WHERE rp.league_id = ? AND rp.roster_id = ?
        ORDER BY p.position, COALESCE(r.rank, 9999), p.full_name
    """, params).fetchall()

    return [dict(r) for r in rows]


def render_position_group(players, position, show_tv):
    color = POS_COLORS.get(position, "#888")

    html = f'<div style="margin-bottom:16px;">'
    html += f'<div style="margin-bottom:6px;display:flex;align-items:center;gap:8px;">'
    html += f'<span style="background:{color};color:#fff;padding:4px 10px;border-radius:4px;font-weight:bold;font-size:14px;">{position}</span>'

    if show_tv:
        total_tv = sum(p.get("tv_value", 0) or 0 for p in players)
        html += f'<span style="color:#aaa;font-size:12px;">Valor total: {total_tv}</span>'

    html += f'<span style="color:#666;font-size:12px;">{len(players)} jogadores</span>'
    html += '</div>'

    for p in players:
        name = p["full_name"]
        team = p.get("team", "")
        age = p.get("age")
        age_str = str(age) if age else ""
        slot = SLOT_LABEL.get(p.get("slot", ""), "")
        rank = p.get("rank")
        rank_str = f"#{rank}" if rank and rank < 9999 else ""
        pos_rank = p.get("position_rank", "")
        injury = p.get("injury_status", "")

        slot_color = "#4caf8a" if slot == "START" else "#888"
        if slot == "IR":
            slot_color = "#e74c6f"
        if slot == "TX":
            slot_color = "#e8a838"

        injury_str = ""
        if injury:
            injury_str = f'<span style="color:#e74c6f;font-size:11px;margin-left:4px;">({injury})</span>'

        tv_str = ""
        if show_tv and p.get("tv_value"):
            trend = p.get("tv_trend", 0) or 0
            trend_color = "#4caf8a" if trend >= 0 else "#e74c6f"
            trend_arrow = f"↑{trend}" if trend > 0 else f"↓{abs(trend)}" if trend < 0 else ""
            tv_str = f'<span style="color:#ccc;font-size:12px;width:50px;text-align:right;">{p["tv_value"]}</span>'
            if trend_arrow:
                tv_str += f'<span style="color:{trend_color};font-size:10px;margin-left:2px;">{trend_arrow}</span>'

        html += f'''<div style="padding:3px 4px;font-size:13px;display:flex;align-items:center;gap:6px;">
<span style="color:{slot_color};font-weight:bold;font-size:10px;width:35px;">{slot}</span>
<span style="color:#eee;font-weight:bold;flex:1;">{name}{injury_str}</span>
<span style="color:#999;font-size:11px;width:30px;">{team}</span>
<span style="color:#999;font-size:11px;width:25px;text-align:right;">{age_str}</span>
<span style="color:#888;font-size:11px;width:40px;text-align:right;">{pos_rank}</span>
{tv_str}
</div>'''

    html += '</div>'
    return html


def render_roster_summary(players, show_tv):
    positions = ["QB", "RB", "WR", "TE"]
    summary = []

    for pos in positions:
        pos_players = [p for p in players if p.get("position") == pos]
        starters = [p for p in pos_players if p.get("slot") == "starter"]
        count = len(pos_players)
        starter_count = len(starters)

        if show_tv:
            total_val = sum(p.get("tv_value", 0) or 0 for p in pos_players)
            starter_val = sum(p.get("tv_value", 0) or 0 for p in starters)
        else:
            total_val = 0
            starter_val = 0

        ages = [p.get("age") for p in pos_players if p.get("age")]
        avg_age = round(sum(ages) / len(ages), 1) if ages else 0

        summary.append({
            "pos": pos,
            "count": count,
            "starters": starter_count,
            "total_val": total_val,
            "starter_val": starter_val,
            "avg_age": avg_age,
        })

    return summary


my_roster_row = conn.execute(
    "SELECT roster_id FROM users WHERE user_id = ? AND league_id = ?",
    (my_user_id, league_id)
).fetchone()

if not my_roster_row:
    st.warning("Seu roster não encontrado nessa liga.")
    st.stop()

my_roster_id = my_roster_row["roster_id"]

sf = "SF" if league.get("is_superflex") else "1QB"
tep = " TEP" if league.get("is_tep") else ""
st.markdown(f"### [{league['name']}](https://sleeper.com/leagues/{league_id})")
st.caption(f"{league['league_type']} · {league['scoring_type']} · {sf}{tep} · {league['total_rosters']} times")

tv_format = tv_format_for_league(league) if show_tv else None
r_type = ranking_type_for_league(league)
r_format = ranking_format_for_league(league)

if show_all_teams:
    all_rosters = conn.execute(
        "SELECT DISTINCT r.roster_id, u.display_name FROM rosters r LEFT JOIN users u ON r.owner_id = u.user_id AND r.league_id = u.league_id WHERE r.league_id = ? ORDER BY u.display_name",
        (league_id,)
    ).fetchall()
    roster_options = {f"{r['display_name'] or 'Roster ' + str(r['roster_id'])}": r["roster_id"] for r in all_rosters}
    selected_team = st.selectbox("Time", list(roster_options.keys()), index=list(roster_options.values()).index(my_roster_id) if my_roster_id in roster_options.values() else 0)
    view_roster_id = roster_options[selected_team]
else:
    view_roster_id = my_roster_id

roster_data = get_roster_data(conn, league_id, view_roster_id, tv_format, r_type, r_format)

if not roster_data:
    st.warning("Roster vazio.")
    st.stop()

summary = render_roster_summary(roster_data, show_tv)

st.subheader("Resumo")
cols = st.columns(4)
for i, s in enumerate(summary):
    color = POS_COLORS.get(s["pos"], "#888")
    with cols[i]:
        val_line = f"Valor: {s['total_val']}" if show_tv else ""
        st.markdown(f"""
<div style="border:1px solid #333;border-radius:8px;padding:12px;text-align:center;">
<div style="background:{color};color:#fff;padding:4px 8px;border-radius:4px;font-weight:bold;font-size:16px;display:inline-block;margin-bottom:6px;">{s['pos']}</div>
<div style="color:#eee;font-size:20px;font-weight:bold;">{s['count']}</div>
<div style="color:#999;font-size:11px;">{s['starters']} starters · Idade média: {s['avg_age']}</div>
<div style="color:#aaa;font-size:12px;">{val_line}</div>
</div>
""", unsafe_allow_html=True)

if show_tv:
    total_value = sum(p.get("tv_value", 0) or 0 for p in roster_data)
    st.markdown(f"**Valor total do roster: {total_value}**")

st.markdown("---")

st.subheader("Roster Completo")

for pos in ["QB", "RB", "WR", "TE", "K", "DEF"]:
    pos_players = [p for p in roster_data if p.get("position") == pos]
    if not pos_players:
        continue

    pos_players.sort(key=lambda p: (SLOT_ORDER.get(p.get("slot", ""), 9), p.get("rank") or 9999))
    html = render_position_group(pos_players, pos, show_tv)
    st.markdown(html, unsafe_allow_html=True)

conn.close()
