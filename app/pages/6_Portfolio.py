import streamlit as st
import sqlite3
import os
import sys
import pandas as pd
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from style import setup
setup("Portfolio View", "💼")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fantasy.db")

POS_COLORS = {
    "QB": "#e74c6f",
    "RB": "#4caf8a",
    "WR": "#4a9bd9",
    "TE": "#e8a838",
    "K": "#9b7fc4",
    "DEF": "#7f8c8d",
}

if not os.path.exists(DB_PATH):
    st.error("Banco não encontrado.")
    st.stop()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

username = st.sidebar.text_input("Username Sleeper", value="pedrashow")

user_row = conn.execute("SELECT DISTINCT user_id FROM users WHERE display_name = ? LIMIT 1", (username,)).fetchone()
if not user_row:
    st.error(f"Usuário '{username}' não encontrado.")
    st.stop()
my_user_id = user_row["user_id"]

leagues = conn.execute(
    "SELECT league_id, name, league_type, scoring_type, is_superflex, total_rosters FROM leagues ORDER BY name"
).fetchall()

if not leagues:
    st.warning("Nenhuma liga encontrada.")
    st.stop()

league_map = {}
for lg in leagues:
    league_map[lg["league_id"]] = dict(lg)


def tv_format_for_league(lg):
    lt = "dynasty" if lg.get("league_type") == "dynasty" else "redraft"
    sf = "sf" if lg.get("is_superflex") else "1qb"
    sc = {"ppr": "ppr", "half_ppr": "half", "standard": "half"}.get(lg.get("scoring_type", ""), "half")
    return f"{lt}_{sf}_{sc}"


my_roster_ids = {}
for lg in leagues:
    row = conn.execute(
        "SELECT roster_id FROM users WHERE user_id = ? AND league_id = ?",
        (my_user_id, lg["league_id"])
    ).fetchone()
    if row and row["roster_id"] is not None:
        my_roster_ids[lg["league_id"]] = row["roster_id"]

all_my_players = conn.execute("""
    SELECT rp.league_id, rp.player_id, rp.slot,
        p.full_name, p.position, p.team, p.age, p.injury_status
    FROM roster_players rp
    JOIN players p ON rp.player_id = p.player_id
    WHERE rp.league_id IN ({}) AND ({})
""".format(
    ",".join(f"'{lid}'" for lid in my_roster_ids),
    " OR ".join(f"(rp.league_id = '{lid}' AND rp.roster_id = {rid})" for lid, rid in my_roster_ids.items())
)).fetchall() if my_roster_ids else []

player_data = defaultdict(lambda: {
    "name": "", "position": "", "team": "", "age": None, "injury": "",
    "leagues": [], "league_count": 0,
})

for row in all_my_players:
    pid = row["player_id"]
    lid = row["league_id"]
    lg_info = league_map.get(lid, {})
    tv_fmt = tv_format_for_league(lg_info)

    tv_row = conn.execute(
        "SELECT value FROM trade_values WHERE player_id = ? AND source = 'fantasycalc' AND format = ?",
        (pid, tv_fmt)
    ).fetchone()
    tv_val = tv_row["value"] if tv_row else None

    pd_entry = player_data[pid]
    pd_entry["name"] = row["full_name"]
    pd_entry["position"] = row["position"]
    pd_entry["team"] = row["team"]
    pd_entry["age"] = row["age"]
    pd_entry["injury"] = row["injury_status"] or ""
    pd_entry["leagues"].append({
        "league_id": lid,
        "league_name": lg_info.get("name", ""),
        "league_type": lg_info.get("league_type", ""),
        "slot": row["slot"],
        "tv_value": tv_val,
        "tv_format": tv_fmt,
    })
    pd_entry["league_count"] = len(pd_entry["leagues"])

total_leagues = len(my_roster_ids)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Ligas:** {total_leagues}")
st.sidebar.markdown(f"**Jogadores únicos:** {len(player_data)}")

min_exposure = st.sidebar.slider("Exposição mínima", 1, total_leagues, 1)
pos_filter = st.sidebar.selectbox("Posição", ["ALL", "QB", "RB", "WR", "TE"], key="port_pos")

tab_exposure, tab_nfl, tab_bye, tab_strength = st.tabs([
    "👤 Exposição por Jogador", "🏟️ Exposição NFL", "📅 Bye Week", "💪 Força por Liga"
])

with tab_exposure:
    players_list = []
    for pid, data in player_data.items():
        if data["league_count"] < min_exposure:
            continue
        if pos_filter != "ALL" and data["position"] != pos_filter:
            continue

        tv_values = [lg["tv_value"] for lg in data["leagues"] if lg["tv_value"]]
        avg_tv = int(sum(tv_values) / len(tv_values)) if tv_values else 0
        league_names = [lg["league_name"] for lg in data["leagues"]]

        players_list.append({
            "name": data["name"],
            "position": data["position"],
            "team": data["team"],
            "age": data["age"],
            "injury": data["injury"],
            "count": data["league_count"],
            "pct": round(data["league_count"] / total_leagues * 100),
            "avg_tv": avg_tv,
            "leagues": league_names,
        })

    players_list.sort(key=lambda x: (-x["count"], -x["avg_tv"]))

    if not players_list:
        st.info("Nenhum jogador com essa exposição mínima.")
    else:
        html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        html += '<tr style="border-bottom:1px solid #444;color:#888;"><td style="padding:6px;">Jogador</td><td>Pos</td><td>Time</td><td>Idade</td><td>Ligas</td><td>%</td><td>TV médio</td><td>Onde</td></tr>'

        for p in players_list:
            color = POS_COLORS.get(p["position"], "#888")
            injury_str = f' <span style="color:#e74c6f;">({p["injury"]})</span>' if p["injury"] else ""

            pct_color = "#e74c6f" if p["pct"] >= 75 else "#e8a838" if p["pct"] >= 50 else "#4caf8a"
            bar_width = p["pct"]

            leagues_str = ", ".join(p["leagues"][:4])
            if len(p["leagues"]) > 4:
                leagues_str += f" +{len(p['leagues'])-4}"

            html += f'''<tr style="border-bottom:1px solid #222;">
<td style="padding:5px;color:#eee;font-weight:bold;">{p["name"]}{injury_str}</td>
<td><span style="background:{color};color:#fff;padding:1px 5px;border-radius:3px;font-size:10px;font-weight:bold;">{p["position"]}</span></td>
<td style="color:#999;">{p["team"]}</td>
<td style="color:#999;">{p["age"] or ""}</td>
<td style="color:#eee;font-weight:bold;text-align:center;">{p["count"]}/{total_leagues}</td>
<td style="color:{pct_color};font-weight:bold;">{p["pct"]}%</td>
<td style="color:#ccc;">{p["avg_tv"]}</td>
<td style="color:#888;font-size:11px;">{leagues_str}</td>
</tr>'''

        html += '</table>'
        st.markdown(html, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Jogadores em 1 liga só (candidatos a trade)")
    singles = [p for p in players_list if p["count"] == 1 and min_exposure <= 1]
    singles.sort(key=lambda x: -x["avg_tv"])
    if singles:
        html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        html += '<tr style="border-bottom:1px solid #444;color:#888;"><td style="padding:6px;">Jogador</td><td>Pos</td><td>Time</td><td>TV</td><td>Liga</td></tr>'
        for p in singles[:20]:
            color = POS_COLORS.get(p["position"], "#888")
            html += f'''<tr style="border-bottom:1px solid #222;">
<td style="padding:4px;color:#eee;font-weight:bold;">{p["name"]}</td>
<td><span style="background:{color};color:#fff;padding:1px 4px;border-radius:3px;font-size:10px;font-weight:bold;">{p["position"]}</span></td>
<td style="color:#999;">{p["team"]}</td>
<td style="color:#ccc;">{p["avg_tv"]}</td>
<td style="color:#888;font-size:11px;">{p["leagues"][0]}</td>
</tr>'''
        html += '</table>'
        st.markdown(html, unsafe_allow_html=True)


with tab_nfl:
    team_exposure = defaultdict(lambda: {"count": 0, "players": [], "leagues": set()})

    for pid, data in player_data.items():
        if data["position"] in ("K", "DEF"):
            continue
        nfl_team = data["team"]
        if not nfl_team or nfl_team == "FA":
            continue
        te = team_exposure[nfl_team]
        te["count"] += data["league_count"]
        te["players"].append(data["name"])
        for lg in data["leagues"]:
            te["leagues"].add(lg["league_name"])

    teams_sorted = sorted(team_exposure.items(), key=lambda x: -x[1]["count"])

    html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
    html += '<tr style="border-bottom:1px solid #444;color:#888;"><td style="padding:6px;">Time NFL</td><td>Slots totais</td><td>Jogadores</td><td>Ligas afetadas</td></tr>'

    for team, data in teams_sorted[:20]:
        players_str = ", ".join(sorted(set(data["players"]))[:5])
        if len(set(data["players"])) > 5:
            players_str += f" +{len(set(data['players']))-5}"
        leagues_affected = len(data["leagues"])

        risk_color = "#e74c6f" if data["count"] >= 10 else "#e8a838" if data["count"] >= 5 else "#4caf8a"

        html += f'''<tr style="border-bottom:1px solid #222;">
<td style="padding:5px;color:#eee;font-weight:bold;">{team}</td>
<td style="color:{risk_color};font-weight:bold;text-align:center;">{data["count"]}</td>
<td style="color:#999;font-size:11px;">{players_str}</td>
<td style="color:#888;text-align:center;">{leagues_affected}/{total_leagues}</td>
</tr>'''

    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)


with tab_bye:
    bye_data = {}
    for pid, data in player_data.items():
        if data["position"] in ("K", "DEF"):
            continue

        bye_row = conn.execute(
            "SELECT bye_week FROM rankings WHERE player_id = ? AND bye_week IS NOT NULL LIMIT 1",
            (pid,)
        ).fetchone()
        if not bye_row:
            continue

        bye = int(bye_row["bye_week"])
        for lg in data["leagues"]:
            key = (lg["league_name"], bye)
            if key not in bye_data:
                bye_data[key] = {"league": lg["league_name"], "bye": bye, "players": [], "starters": 0}
            bye_data[key]["players"].append(data["name"])
            if lg["slot"] == "starter":
                bye_data[key]["starters"] += 1

    danger_weeks = []
    for key, bd in bye_data.items():
        if len(bd["players"]) >= 3:
            danger_weeks.append(bd)

    danger_weeks.sort(key=lambda x: (-len(x["players"]), x["bye"]))

    if danger_weeks:
        st.subheader(f"⚠️ {len(danger_weeks)} situações de bye hell")
        html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        html += '<tr style="border-bottom:1px solid #444;color:#888;"><td style="padding:6px;">Liga</td><td>Semana</td><td>Jogadores</td><td>Starters</td></tr>'

        for bw in danger_weeks:
            players_str = ", ".join(bw["players"][:5])
            if len(bw["players"]) > 5:
                players_str += f" +{len(bw['players'])-5}"
            risk_color = "#e74c6f" if bw["starters"] >= 3 else "#e8a838" if bw["starters"] >= 2 else "#999"

            html += f'''<tr style="border-bottom:1px solid #222;">
<td style="padding:4px;color:#eee;">{bw["league"]}</td>
<td style="color:#eee;font-weight:bold;text-align:center;">Wk {bw["bye"]}</td>
<td style="color:#999;font-size:11px;">{players_str}</td>
<td style="color:{risk_color};font-weight:bold;text-align:center;">{bw["starters"]}</td>
</tr>'''

        html += '</table>'
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.success("Sem bye hell detectado (3+ jogadores no mesmo bye em uma liga).")


with tab_strength:
    league_values = []

    for lg in leagues:
        lid = lg["league_id"]
        if lid not in my_roster_ids:
            continue

        rid = my_roster_ids[lid]
        lg_dict = league_map[lid]
        tv_fmt = tv_format_for_league(lg_dict)

        rows = conn.execute("""
            SELECT p.position, tv.value as tv_value
            FROM roster_players rp
            JOIN players p ON rp.player_id = p.player_id
            LEFT JOIN trade_values tv ON rp.player_id = tv.player_id AND tv.source = 'fantasycalc' AND tv.format = ?
            WHERE rp.league_id = ? AND rp.roster_id = ?
        """, (tv_fmt, lid, rid)).fetchall()

        total = 0
        by_pos = defaultdict(int)
        for r in rows:
            val = r["tv_value"] or 0
            total += val
            by_pos[r["position"]] += val

        sf = "SF" if lg["is_superflex"] else "1QB"
        league_values.append({
            "name": lg["name"],
            "type": lg["league_type"],
            "scoring": f"{lg['scoring_type']} {sf}",
            "total": total,
            "qb": by_pos.get("QB", 0),
            "rb": by_pos.get("RB", 0),
            "wr": by_pos.get("WR", 0),
            "te": by_pos.get("TE", 0),
        })

    league_values.sort(key=lambda x: -x["total"])

    html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
    html += '<tr style="border-bottom:1px solid #444;color:#888;"><td style="padding:6px;">Liga</td><td>Tipo</td><td>Total</td>'
    html += '<td style="color:#e74c6f;">QB</td><td style="color:#4caf8a;">RB</td><td style="color:#4a9bd9;">WR</td><td style="color:#e8a838;">TE</td></tr>'

    max_total = league_values[0]["total"] if league_values else 1

    for lv in league_values:
        bar_pct = int(lv["total"] / max_total * 100) if max_total else 0

        html += f'''<tr style="border-bottom:1px solid #222;">
<td style="padding:5px;color:#eee;font-weight:bold;">{lv["name"]}</td>
<td style="color:#888;font-size:11px;">{lv["scoring"]}</td>
<td style="color:#eee;font-weight:bold;">{lv["total"]}</td>
<td style="color:#e74c6f;">{lv["qb"]}</td>
<td style="color:#4caf8a;">{lv["rb"]}</td>
<td style="color:#4a9bd9;">{lv["wr"]}</td>
<td style="color:#e8a838;">{lv["te"]}</td>
</tr>'''

    html += '</table>'
    st.markdown(html, unsafe_allow_html=True)

conn.close()
