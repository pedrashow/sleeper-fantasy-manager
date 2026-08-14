import streamlit as st
import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from style import setup
setup("Player Lookup", "🔍")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fantasy.db")

if not os.path.exists(DB_PATH):
    st.error("Banco não encontrado.")
    st.stop()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

search = st.text_input("Buscar jogador", placeholder="Ex: Ja'Marr Chase")

if search and len(search) >= 2:
    players = conn.execute(
        "SELECT player_id, full_name, position, team, age, years_exp FROM players WHERE full_name LIKE ? ORDER BY full_name LIMIT 20",
        (f"%{search}%",),
    ).fetchall()

    if not players:
        st.warning("Nenhum jogador encontrado.")
        st.stop()

    player_options = {f"{p['full_name']} ({p['position']} - {p['team']})": p["player_id"] for p in players}

    if len(players) == 1:
        selected_id = players[0]["player_id"]
    else:
        selected = st.selectbox("Selecione", list(player_options.keys()))
        selected_id = player_options[selected]

    player = conn.execute(
        "SELECT player_id, full_name, position, team, age, years_exp, injury_status FROM players WHERE player_id = ?",
        (selected_id,),
    ).fetchone()

    st.subheader(f"{player['full_name']}")
    st.text(f"{player['position']} | {player['team']} | Idade: {player['age'] or '?'} | Exp: {player['years_exp'] or '?'} anos | Injury: {player['injury_status'] or '-'}")

    POS_COLORS = {"QB": "#e74c6f", "RB": "#4caf8a", "WR": "#4a9bd9", "TE": "#e8a838"}
    pos = player["position"]

    fp_row = conn.execute("""
        SELECT rank, position_rank, tier, pos_tier, avg_adp, bye_week
        FROM rankings WHERE player_id = ? AND week = 0
        ORDER BY ranking_type DESC
        LIMIT 1
    """, (selected_id,)).fetchone()

    lb_row = None
    try:
        lb_row = conn.execute(
            "SELECT pos_rank, overall_rank, tier, tier_name FROM longbuild_rankings WHERE player_id = ? LIMIT 1",
            (selected_id,)
        ).fetchone()
    except Exception:
        pass

    wn_row = None
    try:
        wn_row = conn.execute(
            "SELECT pos_rank, overall_rank, tier, tier_name FROM winnow_rankings WHERE player_id = ? LIMIT 1",
            (selected_id,)
        ).fetchone()
    except Exception:
        pass

    tv_row = None
    try:
        tv_row = conn.execute("""
            SELECT value, overall_rank, position_rank, trend_30day
            FROM trade_values WHERE player_id = ? AND source = 'fantasycalc'
            ORDER BY format LIMIT 1
        """, (selected_id,)).fetchone()
    except Exception:
        pass

    has_any = fp_row or lb_row or wn_row or tv_row
    if has_any:
        summary_html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin:8px 0 16px;">'

        if fp_row:
            summary_html += f'''<div style="background:#1a1a2e;border:1px solid #333;border-radius:8px;padding:10px 16px;text-align:center;min-width:100px;">
<div style="color:#aaa;font-size:11px;margin-bottom:4px;">FantasyPros</div>
<div style="color:#eee;font-size:20px;font-weight:bold;">{fp_row["position_rank"] or "—"}</div>
<div style="color:#888;font-size:11px;">Overall #{fp_row["rank"] or "?"} · Tier {int(fp_row["pos_tier"] or 0)}</div>
<div style="color:#888;font-size:11px;">ADP {fp_row["avg_adp"] or "—"}</div>
</div>'''

        if lb_row:
            summary_html += f'''<div style="background:#2a2a1a;border:1px solid #554;border-radius:8px;padding:10px 16px;text-align:center;min-width:100px;">
<div style="color:#c9a227;font-size:11px;margin-bottom:4px;">Long Build</div>
<div style="color:#eee;font-size:20px;font-weight:bold;">{pos}{lb_row["pos_rank"]}</div>
<div style="color:#888;font-size:11px;">Overall #{lb_row["overall_rank"] or "?"} · Tier {lb_row["tier"] or "?"}</div>
<div style="color:#998;font-size:10px;">{lb_row["tier_name"] or ""}</div>
</div>'''

        if wn_row:
            summary_html += f'''<div style="background:#1a2a1a;border:1px solid #353;border-radius:8px;padding:10px 16px;text-align:center;min-width:100px;">
<div style="color:#6ab04c;font-size:11px;margin-bottom:4px;">Win-Now</div>
<div style="color:#eee;font-size:20px;font-weight:bold;">{pos}{wn_row["pos_rank"]}</div>
<div style="color:#888;font-size:11px;">Overall #{wn_row["overall_rank"] or "?"} · Tier {wn_row["tier"] or "?"}</div>
<div style="color:#898;font-size:10px;">{wn_row["tier_name"] or ""}</div>
</div>'''

        if tv_row:
            trend = tv_row["trend_30day"] or 0
            trend_color = "#4caf8a" if trend >= 0 else "#e74c6f"
            trend_str = f"↑{trend}" if trend > 0 else f"↓{abs(trend)}" if trend < 0 else "—"
            summary_html += f'''<div style="background:#1a1a2e;border:1px solid #333;border-radius:8px;padding:10px 16px;text-align:center;min-width:100px;">
<div style="color:#aaa;font-size:11px;margin-bottom:4px;">Trade Value</div>
<div style="color:#eee;font-size:20px;font-weight:bold;">{tv_row["value"]}</div>
<div style="color:#888;font-size:11px;">Rank #{tv_row["overall_rank"] or "?"} · {tv_row["position_rank"] or "?"}</div>
<div style="color:{trend_color};font-size:11px;">30d: {trend_str}</div>
</div>'''

        summary_html += '</div>'
        st.markdown(summary_html, unsafe_allow_html=True)

    st.markdown("---")

    rostered = conn.execute("""
        SELECT l.name as liga, l.league_type, l.scoring_type, l.is_superflex,
               u.display_name as owner, rp.slot, rp.roster_id
        FROM roster_players rp
        JOIN leagues l ON rp.league_id = l.league_id
        JOIN rosters r ON rp.roster_id = r.roster_id AND rp.league_id = r.league_id
        LEFT JOIN users u ON r.owner_id = u.user_id AND r.league_id = u.league_id
        WHERE rp.player_id = ?
        ORDER BY l.name
    """, (selected_id,)).fetchall()

    all_leagues = conn.execute("SELECT league_id, name FROM leagues ORDER BY name").fetchall()
    rostered_league_names = set()

    if rostered:
        st.subheader(f"Rostereado em {len(rostered)} liga(s)")
        rows = []
        for r in rostered:
            rostered_league_names.add(r["liga"])
            sf = "SF" if r["is_superflex"] else "1QB"
            rows.append({
                "Liga": r["liga"],
                "Tipo": r["league_type"],
                "Scoring": f"{r['scoring_type']} {sf}",
                "Owner": r["owner"] or "?",
                "Slot": r["slot"],
            })
        st.table(rows)
    else:
        st.info("Não está em nenhum roster.")

    available_leagues = [lg for lg in all_leagues if lg["name"] not in rostered_league_names]
    if available_leagues:
        st.subheader(f"Disponível em {len(available_leagues)} liga(s)")
        rows = [{"Liga": lg["name"]} for lg in available_leagues]
        st.table(rows)

    st.markdown("---")

    rankings = conn.execute("""
        SELECT ranking_type, format, rank, position_rank, tier, pos_tier, avg_adp, bye_week, owned_pct, ecr_delta
        FROM rankings
        WHERE player_id = ?
        ORDER BY ranking_type, format
    """, (selected_id,)).fetchall()

    if rankings:
        with st.expander("Rankings detalhados (FantasyPros)", expanded=False):
            rows = []
            for r in rankings:
                rows.append({
                    "Tipo": r["ranking_type"],
                    "Formato": r["format"],
                    "Rank": r["rank"],
                    "Pos Rank": r["position_rank"],
                    "Tier": r["tier"],
                    "Pos Tier": r["pos_tier"],
                    "ADP": r["avg_adp"],
                    "Bye": r["bye_week"],
                    "Own%": r["owned_pct"],
                    "ECR Δ": r["ecr_delta"],
                })
            st.table(rows)

    try:
        trade_vals = conn.execute("""
            SELECT source, format, value, overall_rank, position_rank, trend_30day
            FROM trade_values
            WHERE player_id = ?
            ORDER BY source, format
        """, (selected_id,)).fetchall()

        if trade_vals:
            with st.expander("Trade Values detalhados", expanded=False):
                rows = []
                for r in trade_vals:
                    rows.append({
                        "Fonte": r["source"],
                        "Formato": r["format"],
                        "Valor": r["value"],
                        "Rank": r["overall_rank"],
                        "Pos Rank": r["position_rank"],
                        "Trend 30d": r["trend_30day"],
                    })
                st.table(rows)
    except Exception:
        pass

conn.close()
