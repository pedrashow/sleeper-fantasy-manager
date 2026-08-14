import streamlit as st
import sqlite3
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from style import setup
setup("Sleeper Fantasy Manager")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "fantasy.db")
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


def run_script(args):
    result = subprocess.run(
        [sys.executable] + args,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    return result.stdout, result.stderr, result.returncode


def get_db():
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


st.subheader("Sleeper Sync")

col_user, col_season = st.columns([3, 1])
with col_user:
    username = st.text_input("Username Sleeper", value="pedrashow", label_visibility="collapsed", placeholder="Username Sleeper")
with col_season:
    season = st.text_input("Season", value="2026", label_visibility="collapsed")

skip_players = st.checkbox("Skip players", value=True, help="Pula a base de jogadores (~10k). Desmarque na primeira vez.")

if st.button("Sync Sleeper"):
    with st.spinner("Sincronizando com Sleeper..."):
        args = ["scrapers/sync_sleeper.py", username, "--season", season]
        if skip_players:
            args.append("--skip-players")
        stdout, stderr, code = run_script(args)
    if code == 0:
        st.success("Sync concluído")
        st.code(stdout)
    else:
        st.error("Erro no sync")
        st.code(stderr)

st.markdown("---")

st.subheader("Rankings FantasyPros")

ranking_options = {
    "Redraft Half-PPR": ("redraft", "half"),
    "Redraft PPR": ("redraft", "ppr"),
    "Redraft SF Half-PPR": ("redraft", "sf_half"),
    "Redraft SF PPR": ("redraft", "sf_ppr"),
    "Dynasty SF": ("dynasty", "sf"),
    "Dynasty 1QB": ("dynasty", "1qb"),
    "Rookie SF": ("rookie", "sf"),
    "Rookie 1QB": ("rookie", "1qb"),
}

selected_rankings = st.multiselect(
    "Selecione os rankings para importar",
    list(ranking_options.keys()),
    default=["Redraft Half-PPR", "Redraft PPR"],
)

if st.button("Importar Rankings"):
    if not selected_rankings:
        st.warning("Selecione pelo menos um ranking.")
    else:
        for label in selected_rankings:
            rtype, rformat = ranking_options[label]
            with st.spinner(f"Importando {label}..."):
                args = ["scrapers/fantasypros.py", "--type", rtype, "--format", rformat]
                stdout, stderr, code = run_script(args)
            if code == 0:
                st.success(f"{label} importado")
                st.code(stdout)
            else:
                st.error(f"Erro em {label}")
                st.code(stderr)

st.markdown("---")

st.subheader("Trade Values (FantasyCalc)")

tv_options = {
    "Dynasty SF Half-PPR": "dynasty_sf_half",
    "Dynasty SF PPR": "dynasty_sf_ppr",
    "Dynasty 1QB Half-PPR": "dynasty_1qb_half",
    "Dynasty 1QB PPR": "dynasty_1qb_ppr",
    "Redraft SF Half-PPR": "redraft_sf_half",
    "Redraft SF PPR": "redraft_sf_ppr",
    "Redraft 1QB Half-PPR": "redraft_1qb_half",
    "Redraft 1QB PPR": "redraft_1qb_ppr",
}

selected_tv = st.multiselect(
    "Selecione os formatos para importar",
    list(tv_options.keys()),
    default=["Dynasty SF Half-PPR", "Redraft 1QB Half-PPR"],
)

num_teams = st.selectbox("Número de times", [10, 12, 14], index=1)

if st.button("Importar Trade Values"):
    if not selected_tv:
        st.warning("Selecione pelo menos um formato.")
    else:
        for label in selected_tv:
            fmt = tv_options[label]
            with st.spinner(f"Importando {label}..."):
                args = ["scrapers/fantasycalc.py", "--format", fmt, "--teams", str(num_teams)]
                stdout, stderr, code = run_script(args)
            if code == 0:
                st.success(f"{label} importado")
                st.code(stdout)
            else:
                st.error(f"Erro em {label}")
                st.code(stderr)

st.markdown("---")

st.subheader("Status do Banco")

conn = get_db()
if conn:
    players_count = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    rankings_count = conn.execute("SELECT COUNT(*) FROM rankings").fetchone()[0]
    roster_players_count = conn.execute("SELECT COUNT(*) FROM roster_players").fetchone()[0]

    try:
        tv_count = conn.execute("SELECT COUNT(*) FROM trade_values").fetchone()[0]
    except Exception:
        tv_count = 0

    st.text(f"Jogadores: {players_count}  |  Rankings: {rankings_count}  |  Trade Values: {tv_count}  |  Roster slots: {roster_players_count}")

    rankings_detail = conn.execute(
        "SELECT ranking_type, format, COUNT(*) as total, MAX(fetched_at) as ultimo FROM rankings GROUP BY ranking_type, format ORDER BY ranking_type, format"
    ).fetchall()

    if rankings_detail:
        st.markdown("**Rankings importados**")
        rows = []
        for r in rankings_detail:
            rows.append({
                "Tipo": r["ranking_type"],
                "Formato": r["format"],
                "Jogadores": r["total"],
                "Última atualização": r["ultimo"][:16] if r["ultimo"] else "-",
            })
        st.table(rows)

    try:
        tv_detail = conn.execute(
            "SELECT source, format, COUNT(*) as total, MAX(fetched_at) as ultimo FROM trade_values GROUP BY source, format ORDER BY source, format"
        ).fetchall()
        if tv_detail:
            st.markdown("**Trade Values importados**")
            rows = []
            for r in tv_detail:
                rows.append({
                    "Fonte": r["source"],
                    "Formato": r["format"],
                    "Jogadores": r["total"],
                    "Última atualização": r["ultimo"][:16] if r["ultimo"] else "-",
                })
            st.table(rows)
    except Exception:
        pass

    st.markdown("**Ligas**")
    leagues = conn.execute("SELECT name, league_type, scoring_type, is_superflex, is_tep, total_rosters, ranking_format FROM leagues ORDER BY name").fetchall()
    if leagues:
        rows = []
        for lg in leagues:
            sf = "SF" if lg["is_superflex"] else "1QB"
            tep = " TEP" if lg["is_tep"] else ""
            rows.append({
                "Liga": lg["name"],
                "Tipo": lg["league_type"],
                "Scoring": f"{lg['scoring_type']} {sf}{tep}",
                "Times": lg["total_rosters"],
                "Format": lg["ranking_format"],
            })
        st.table(rows)

    conn.close()
else:
    st.warning("Banco não encontrado. Faça o Sync primeiro.")
