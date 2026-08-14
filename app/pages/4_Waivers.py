import streamlit as st
import sqlite3
import os
import sys
import re
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from style import setup
setup("Waivers", "📎")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fantasy.db")

POS_COLORS = {
    "QB": "#e74c6f",
    "RB": "#4caf8a",
    "WR": "#4a9bd9",
    "TE": "#e8a838",
}

INJURY_EMOJI = {
    "Out": "🔴",
    "IR": "🔴",
    "Doubtful": "🟠",
    "Questionable": "🟡",
    "Probable": "🟢",
    "Suspension": "⛔",
    "PUP": "🔴",
    "NFI": "🔴",
    "COV": "🔴",
}

if not os.path.exists(DB_PATH):
    st.error("Banco não encontrado.")
    st.stop()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

username = st.sidebar.text_input("Username Sleeper", value="pedrashow")
top_n = st.sidebar.slider("Free agents por posição", 3, 10, 5)
worst_n = st.sidebar.slider("Meus piores por posição", 1, 5, 2)

tv_formats = []
try:
    tv_formats = [r[0] for r in conn.execute("SELECT DISTINCT format FROM trade_values ORDER BY format").fetchall()]
except Exception:
    pass

show_tv = st.sidebar.checkbox("Mostrar Trade Values", value=True)

leagues = conn.execute(
    "SELECT league_id, name, league_type, scoring_type, is_superflex, ranking_format, total_rosters FROM leagues ORDER BY name"
).fetchall()

if not leagues:
    st.warning("Nenhuma liga encontrada.")
    st.stop()

user_row = conn.execute("SELECT DISTINCT user_id FROM users WHERE display_name = ? LIMIT 1", (username,)).fetchone()
if not user_row:
    st.error(f"Usuário '{username}' não encontrado. Faça o Sync primeiro.")
    st.stop()
my_user_id = user_row["user_id"]


def tv_format_for_league(lg):
    lt = "dynasty" if lg["league_type"] == "dynasty" else "redraft"
    sf = "sf" if lg["is_superflex"] else "1qb"
    sc = {"ppr": "ppr", "half_ppr": "half", "standard": "half"}.get(lg["scoring_type"], "half")
    return f"{lt}_{sf}_{sc}"


def ranking_type_for_league(lg):
    return "dynasty" if lg["league_type"] == "dynasty" else "redraft"


def ranking_format_for_league(lg):
    if lg["league_type"] == "dynasty":
        return "sf" if lg["is_superflex"] else "1qb"
    return lg["ranking_format"] or "sf_half"


def get_my_roster_id(conn, league_id, user_id):
    row = conn.execute(
        "SELECT roster_id FROM users WHERE user_id = ? AND league_id = ?",
        (user_id, league_id)
    ).fetchone()
    return row["roster_id"] if row else None


def get_injured_players(conn, league_id, roster_id):
    rows = conn.execute("""
        SELECT p.full_name, p.position, p.team, p.injury_status, rp.slot
        FROM roster_players rp
        JOIN players p ON rp.player_id = p.player_id
        WHERE rp.league_id = ? AND rp.roster_id = ?
        AND p.injury_status IS NOT NULL AND p.injury_status != ''
        ORDER BY p.position, p.full_name
    """, (league_id, roster_id)).fetchall()
    return [dict(r) for r in rows]


def get_my_worst(conn, league_id, roster_id, r_type, r_format, position, worst_n, tv_format=None):
    tv_join = ""
    tv_cols = ""
    tv_params = []
    if tv_format:
        tv_join = "LEFT JOIN trade_values tv ON r.player_id = tv.player_id AND tv.source = 'fantasycalc' AND tv.format = ?"
        tv_cols = ", tv.value as tv_value"
        tv_params = [tv_format]

    params = [r_type, r_format] + tv_params + [league_id, roster_id, position, worst_n]

    rows = conn.execute(f"""
        SELECT r.rank, r.player_name, p.team, r.position_rank, r.tier, r.pos_tier,
            rp.slot, 'mine' as source
            {tv_cols}
        FROM roster_players rp
        JOIN players p ON rp.player_id = p.player_id
        LEFT JOIN rankings r ON r.player_id = rp.player_id AND r.ranking_type = ? AND r.format = ? AND r.week = 0
        {tv_join}
        WHERE rp.league_id = ? AND rp.roster_id = ?
        AND p.position = ?
        ORDER BY COALESCE(r.rank, 9999) DESC
        LIMIT ?
    """, params).fetchall()
    return [dict(r) for r in rows]


def get_top_available(conn, league_id, r_type, r_format, position, top_n, tv_format=None):
    tv_join = ""
    tv_cols = ""
    params = []
    if tv_format:
        tv_join = "LEFT JOIN trade_values tv ON r.player_id = tv.player_id AND tv.source = 'fantasycalc' AND tv.format = ?"
        tv_cols = ", tv.value as tv_value"
        params.append(tv_format)
    params.extend([r_type, r_format, position, league_id, top_n])

    rows = conn.execute(f"""
        SELECT r.rank, r.player_name, p.team, r.position_rank, r.tier, r.pos_tier,
            NULL as slot, 'free' as source
            {tv_cols}
        FROM rankings r
        JOIN players p ON r.player_id = p.player_id
        {tv_join}
        WHERE r.ranking_type = ? AND r.format = ? AND r.week = 0
        AND p.position = ?
        AND r.player_id NOT IN (SELECT player_id FROM roster_players WHERE league_id = ?)
        ORDER BY r.rank
        LIMIT ?
    """, params).fetchall()
    return [dict(r) for r in rows]


def get_my_worst_dynasty(conn, league_id, roster_id, r_type, r_format, position, worst_n, tv_format=None):
    tv_join = ""
    tv_cols = ""
    tv_params = []
    if tv_format:
        tv_join = "LEFT JOIN trade_values tv ON rp.player_id = tv.player_id AND tv.source = 'fantasycalc' AND tv.format = ?"
        tv_cols = ", tv.value as tv_value"
        tv_params = [tv_format]

    params = [r_type, r_format] + tv_params + [league_id, roster_id, position, worst_n]

    rows = conn.execute(f"""
        SELECT r.rank, r.player_name, p.team, r.position_rank as fp_pos_rank, r.pos_tier as fp_tier,
            rp.slot, 'mine' as source,
            lb.pos_rank as lb_rank, lb.tier as lb_tier,
            wn.pos_rank as wn_rank, wn.tier as wn_tier
            {tv_cols}
        FROM roster_players rp
        JOIN players p ON rp.player_id = p.player_id
        LEFT JOIN rankings r ON r.player_id = rp.player_id AND r.ranking_type = ? AND r.format = ? AND r.week = 0
        LEFT JOIN longbuild_rankings lb ON rp.player_id = lb.player_id
        LEFT JOIN winnow_rankings wn ON rp.player_id = wn.player_id
        {tv_join}
        WHERE rp.league_id = ? AND rp.roster_id = ?
        AND p.position = ?
        ORDER BY COALESCE(r.rank, 9999) DESC
        LIMIT ?
    """, params).fetchall()
    return [dict(r) for r in rows]


def get_top_available_dynasty(conn, league_id, r_type, r_format, position, top_n, tv_format=None):
    tv_join = ""
    tv_cols = ""
    params = []
    if tv_format:
        tv_join = "LEFT JOIN trade_values tv ON r.player_id = tv.player_id AND tv.source = 'fantasycalc' AND tv.format = ?"
        tv_cols = ", tv.value as tv_value"
        params.append(tv_format)
    params.extend([r_type, r_format, position, league_id, top_n])

    rows = conn.execute(f"""
        SELECT r.rank, r.player_name, p.team, r.position_rank as fp_pos_rank, r.pos_tier as fp_tier,
            NULL as slot, 'free' as source,
            lb.pos_rank as lb_rank, lb.tier as lb_tier,
            wn.pos_rank as wn_rank, wn.tier as wn_tier
            {tv_cols}
        FROM rankings r
        JOIN players p ON r.player_id = p.player_id
        LEFT JOIN longbuild_rankings lb ON r.player_id = lb.player_id
        LEFT JOIN winnow_rankings wn ON r.player_id = wn.player_id
        {tv_join}
        WHERE r.ranking_type = ? AND r.format = ? AND r.week = 0
        AND p.position = ?
        AND r.player_id NOT IN (SELECT player_id FROM roster_players WHERE league_id = ?)
        ORDER BY r.rank
        LIMIT ?
    """, params).fetchall()
    return [dict(r) for r in rows]


def extract_pos_num(val):
    if not val:
        return ""
    import re
    m = re.search(r'(\d+)', str(val))
    return m.group(1) if m else str(val)


def render_position_dynasty(mine, available, position, tv_format=None, sort_by="fp"):
    color = POS_COLORS.get(position, "#888")

    sort_keys = {
        "fp": lambda p: int(extract_pos_num(p.get("fp_pos_rank", "")) or 9999),
        "lb": lambda p: p.get("lb_rank") or 9999,
        "wn": lambda p: p.get("wn_rank") or 9999,
        "tv": lambda p: -(p.get("tv_value") or 0),
    }
    sort_fn = sort_keys.get(sort_by, sort_keys["fp"])

    merged = []
    for p in mine:
        p["_rank"] = sort_fn(p)
        merged.append(p)
    for p in available:
        p["_rank"] = sort_fn(p)
        merged.append(p)

    merged.sort(key=lambda x: x["_rank"])

    html = f'<div style="margin-bottom:6px;"><span style="background:{color};color:#fff;padding:3px 8px;border-radius:4px;font-weight:bold;font-size:13px;">{position}</span></div>'

    if not merged:
        html += '<div style="color:#666;font-size:12px;">Sem dados</div>'
        return html

    fp_style = "color:#fff;font-weight:bold;" if sort_by == "fp" else ""
    lb_style = "color:#fff;font-weight:bold;" if sort_by == "lb" else ""
    wn_style = "color:#fff;font-weight:bold;" if sort_by == "wn" else ""

    html += '<div style="display:flex;gap:4px;padding:2px 0;font-size:10px;color:#888;border-bottom:1px solid #333;">'
    html += f'<span style="width:30px;text-align:right;{fp_style}">FP</span>'
    html += '<span style="width:24px;"></span>'
    html += '<span style="flex:1;">Nome</span>'
    html += f'<span style="width:24px;text-align:center;{lb_style}">LB</span>'
    html += f'<span style="width:24px;text-align:center;{wn_style}">WN</span>'
    if tv_format:
        html += '<span style="width:32px;text-align:right;">TV</span>'
    html += '</div>'

    for p in merged:
        name = p.get("player_name", "?")
        team = p.get("team", "")
        fp = extract_pos_num(p.get("fp_pos_rank", ""))
        lb = str(p.get("lb_rank", "")) if p.get("lb_rank") else ""
        wn = str(p.get("wn_rank", "")) if p.get("wn_rank") else ""
        is_mine = p.get("source") == "mine"
        slot = format_slot(p.get("slot")) if is_mine else ""

        tv_str = ""
        if tv_format and p.get("tv_value"):
            tv_str = f'<span style="color:#aaa;font-size:11px;width:32px;text-align:right;">{p["tv_value"]}</span>'

        if is_mine:
            bg = "background:#2a1a1a;" if (p.get("rank") or 0) > 9000 else "background:#1a2a1a;"
            label = f'<span style="color:#e74c6f;font-size:10px;font-weight:bold;width:24px;">{slot}</span>'
        else:
            bg = ""
            label = '<span style="color:#4caf8a;font-size:10px;font-weight:bold;width:24px;">FA</span>'

        lb_color = "#c9a227" if lb else "#555"
        wn_color = "#6ab04c" if wn else "#555"

        html += f'''<div style="padding:3px 2px;font-size:13px;display:flex;align-items:center;gap:4px;{bg}">
<span style="color:#888;width:30px;text-align:right;font-size:12px;">{fp}</span>
{label}
<span style="color:#eee;font-weight:bold;flex:1;font-size:12px;" title="{team}">{name}</span>
<span style="color:{lb_color};width:24px;text-align:center;font-size:12px;font-weight:bold;">{lb}</span>
<span style="color:{wn_color};width:24px;text-align:center;font-size:12px;font-weight:bold;">{wn}</span>
{tv_str}
</div>'''

    return html


def format_slot(slot):
    slot_map = {"starter": "START", "bench": "BN", "taxi": "TX", "reserve": "IR"}
    return slot_map.get(slot, slot or "")


def render_injury_html(injured):
    if not injured:
        return None

    html = '<table style="width:100%;font-size:13px;border-collapse:collapse;">'
    html += '<tr style="color:#888;border-bottom:1px solid #333;"><td style="padding:4px;">Jogador</td><td>Pos</td><td>Time</td><td>Status</td><td>Slot</td></tr>'

    for p in injured:
        status = p["injury_status"]
        emoji = INJURY_EMOJI.get(status, "❓")
        slot = format_slot(p["slot"])
        slot_color = "#e74c6f" if slot in ("START", "BN") and status in ("Out", "IR", "Doubtful") else "#999"

        html += f'''<tr style="border-bottom:1px solid #222;">
<td style="padding:4px;color:#eee;font-weight:bold;">{p["full_name"]}</td>
<td style="color:#aaa;">{p["position"]}</td>
<td style="color:#aaa;">{p["team"]}</td>
<td>{emoji} {status}</td>
<td style="color:{slot_color};font-weight:bold;">{slot}</td>
</tr>'''

    html += '</table>'
    return html


def render_position_comparison(mine, available, position, tv_format=None):
    color = POS_COLORS.get(position, "#888")

    merged = []
    for p in mine:
        p["_rank"] = p.get("rank") or 9999
        merged.append(p)
    for p in available:
        p["_rank"] = p.get("rank") or 9999
        merged.append(p)

    merged.sort(key=lambda x: x["_rank"])

    html = f'<div style="margin-bottom:6px;"><span style="background:{color};color:#fff;padding:3px 8px;border-radius:4px;font-weight:bold;font-size:13px;">{position}</span></div>'

    if not merged:
        html += '<div style="color:#666;font-size:12px;">Sem dados</div>'
        return html

    for p in merged:
        name = p.get("player_name", "?")
        team = p.get("team", "")
        rank = p.get("rank")
        rank_str = str(rank) if rank and rank < 9999 else "—"
        pos_rank = p.get("position_rank", "")
        is_mine = p.get("source") == "mine"
        slot = format_slot(p.get("slot")) if is_mine else ""

        tv_str = ""
        if tv_format and p.get("tv_value"):
            tv_str = f'<span style="color:#aaa;font-size:11px;">{p["tv_value"]}</span>'

        if is_mine:
            bg = "background:#2a1a1a;" if rank and rank > 9000 else "background:#1a2a1a;"
            label = f'<span style="color:#e74c6f;font-size:10px;font-weight:bold;">{slot}</span>'
        else:
            bg = ""
            label = '<span style="color:#4caf8a;font-size:10px;font-weight:bold;">FA</span>'

        html += f'''<div style="padding:3px 2px;font-size:13px;display:flex;align-items:center;gap:5px;{bg}">
<span style="color:#888;width:30px;text-align:right;">{rank_str}</span>
{label}
<span style="color:#eee;font-weight:bold;flex:1;">{name}</span>
<span style="color:#999;font-size:11px;">{team}</span>
{tv_str}
</div>'''

    return html


dynasty_leagues = [lg for lg in leagues if lg["league_type"] == "dynasty"]
redraft_leagues = [lg for lg in leagues if lg["league_type"] != "dynasty"]

has_winnow = False
try:
    has_winnow = conn.execute("SELECT COUNT(*) FROM winnow_rankings").fetchone()[0] > 0
except Exception:
    pass

tab_dynasty, tab_redraft = st.tabs([f"🏆 Dynasty ({len(dynasty_leagues)})", f"🔄 Redraft ({len(redraft_leagues)})"])


def render_league_waivers(lg, conn, my_user_id, show_tv, top_n, worst_n, show_winnow=False, sort_by="fp"):
    league_id = lg["league_id"]
    r_type = ranking_type_for_league(lg)
    r_format = ranking_format_for_league(lg)
    roster_id = get_my_roster_id(conn, league_id, my_user_id)
    tv_format = tv_format_for_league(lg) if show_tv else None

    sf = "SF" if lg["is_superflex"] else "1QB"

    has_rankings = conn.execute(
        "SELECT COUNT(*) FROM rankings WHERE ranking_type = ? AND format = ?",
        (r_type, r_format)
    ).fetchone()[0]

    tv_summary = ""
    all_rosters_data = None
    if show_tv and tv_format and roster_id:
        all_rosters_data = conn.execute("""
            SELECT r.roster_id, u.display_name,
                SUM(COALESCE(tv.value, 0)) as total_tv,
                SUM(CASE WHEN p.position = 'QB' THEN COALESCE(tv.value, 0) ELSE 0 END) as qb_tv,
                SUM(CASE WHEN p.position = 'RB' THEN COALESCE(tv.value, 0) ELSE 0 END) as rb_tv,
                SUM(CASE WHEN p.position = 'WR' THEN COALESCE(tv.value, 0) ELSE 0 END) as wr_tv,
                SUM(CASE WHEN p.position = 'TE' THEN COALESCE(tv.value, 0) ELSE 0 END) as te_tv
            FROM rosters r
            LEFT JOIN users u ON r.owner_id = u.user_id AND r.league_id = u.league_id
            LEFT JOIN roster_players rp ON r.roster_id = rp.roster_id AND r.league_id = rp.league_id
            LEFT JOIN players p ON rp.player_id = p.player_id
            LEFT JOIN trade_values tv ON rp.player_id = tv.player_id AND tv.source = 'fantasycalc' AND tv.format = ?
            WHERE r.league_id = ?
            GROUP BY r.roster_id
            ORDER BY total_tv DESC
        """, (tv_format, league_id)).fetchall()

        if all_rosters_data:
            my_rank = next((i + 1 for i, r in enumerate(all_rosters_data) if r["roster_id"] == roster_id), "?")
            my_tv = next((r["total_tv"] for r in all_rosters_data if r["roster_id"] == roster_id), 0)
            tv_summary = f" · 💰 {my_tv:,} (#{my_rank}/{len(all_rosters_data)})"

    st.markdown(f"### [{lg['name']}](https://sleeper.com/leagues/{league_id})")
    st.caption(f"{lg['league_type']} · {lg['scoring_type']} · {sf} · {lg['total_rosters']} times{tv_summary}")

    if not roster_id:
        st.warning("Seu roster não encontrado nessa liga.")
        st.markdown("---")
        return

    if not has_rankings:
        st.warning(f"Sem rankings para {r_type}/{r_format}. Importe na Home.")
        st.markdown("---")
        return

    injured = get_injured_players(conn, league_id, roster_id)
    if injured:
        with st.expander(f"🏥 Jogadores machucados ({len(injured)})", expanded=True):
            injury_html = render_injury_html(injured)
            st.markdown(injury_html, unsafe_allow_html=True)

    col_qb, col_rb, col_wr, col_te = st.columns(4)

    if show_winnow:
        for col, pos in [(col_qb, "QB"), (col_rb, "RB"), (col_wr, "WR"), (col_te, "TE")]:
            with col:
                my_worst = get_my_worst_dynasty(conn, league_id, roster_id, r_type, r_format, pos, worst_n, tv_format)
                fa_top = get_top_available_dynasty(conn, league_id, r_type, r_format, pos, top_n, tv_format)
                html = render_position_dynasty(my_worst, fa_top, pos, tv_format, sort_by=sort_by)
                st.markdown(html, unsafe_allow_html=True)
    else:
        for col, pos in [(col_qb, "QB"), (col_rb, "RB"), (col_wr, "WR"), (col_te, "TE")]:
            with col:
                my_worst = get_my_worst(conn, league_id, roster_id, r_type, r_format, pos, worst_n, tv_format)
                fa_top = get_top_available(conn, league_id, r_type, r_format, pos, top_n, tv_format)
                html = render_position_comparison(my_worst, fa_top, pos, tv_format)
                st.markdown(html, unsafe_allow_html=True)

    if show_tv and tv_format and all_rosters_data:
        max_tv = max(r["total_tv"] for r in all_rosters_data) or 1
        my_rank = next((i + 1 for i, r in enumerate(all_rosters_data) if r["roster_id"] == roster_id), "?")

        with st.expander(f"📊 Comparação Trade Value na liga", expanded=False):
            tv_html = ''
            for r in all_rosters_data:
                name = r["display_name"] or f"Roster {r['roster_id']}"
                total = r["total_tv"]
                bar_pct = int(total / max_tv * 100) if max_tv else 0
                is_me = r["roster_id"] == roster_id
                name_style = "color:#e8c84a;font-weight:bold;" if is_me else "color:#eee;"
                bar_color = "#e8c84a" if is_me else "#4a9bd9"
                marker = " ◄" if is_me else ""

                tv_html += f'''<div style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:13px;">
<span style="{name_style}width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{name}{marker}</span>
<div style="flex:1;background:#222;border-radius:3px;height:16px;overflow:hidden;">
<div style="width:{bar_pct}%;background:{bar_color};height:100%;border-radius:3px;"></div>
</div>
<span style="color:#ccc;width:55px;text-align:right;font-size:12px;">{total:,}</span>
<span style="color:#e74c6f;font-size:10px;width:30px;">{r["qb_tv"]}</span>
<span style="color:#4caf8a;font-size:10px;width:30px;">{r["rb_tv"]}</span>
<span style="color:#4a9bd9;font-size:10px;width:30px;">{r["wr_tv"]}</span>
<span style="color:#e8a838;font-size:10px;width:30px;">{r["te_tv"]}</span>
</div>'''

            st.markdown(tv_html, unsafe_allow_html=True)

    st.markdown("---")


with tab_dynasty:
    if not dynasty_leagues:
        st.info("Nenhuma liga dynasty encontrada.")
    else:
        sort_options = {"FantasyPros": "fp", "Long Build": "lb", "Win-Now": "wn", "Trade Value": "tv"}
        sort_label = st.radio("Ordenar por", list(sort_options.keys()), horizontal=True, key="dynasty_sort")
        dynasty_sort = sort_options[sort_label]
        for lg in dynasty_leagues:
            render_league_waivers(lg, conn, my_user_id, show_tv, top_n, worst_n, show_winnow=True, sort_by=dynasty_sort)

with tab_redraft:
    if not redraft_leagues:
        st.info("Nenhuma liga redraft encontrada.")
    else:
        for lg in redraft_leagues:
            render_league_waivers(lg, conn, my_user_id, show_tv, top_n, worst_n, show_winnow=False)

conn.close()
