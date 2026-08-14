import streamlit as st
import sqlite3
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from style import setup
setup("Rankings", "📊")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fantasy.db")

if not os.path.exists(DB_PATH):
    st.error("Banco não encontrado.")
    st.stop()

conn = sqlite3.connect(DB_PATH)

available = pd.read_sql_query(
    "SELECT DISTINCT ranking_type, format FROM rankings ORDER BY ranking_type, format", conn
)

if available.empty:
    st.warning("Nenhum ranking importado.")
    st.stop()

try:
    tv_formats = pd.read_sql_query(
        "SELECT DISTINCT format FROM trade_values ORDER BY format", conn
    )["format"].tolist()
except Exception:
    tv_formats = []

col1, col2, col3, col4 = st.columns(4)

with col1:
    ranking_types = available["ranking_type"].unique().tolist()
    selected_type = st.selectbox("Tipo", ranking_types)

with col2:
    formats = available[available["ranking_type"] == selected_type]["format"].unique().tolist()
    selected_format = st.selectbox("Formato", formats)

with col3:
    positions = ["ALL", "QB", "RB", "WR", "TE", "K", "DST"]
    selected_pos = st.selectbox("Posição", positions)

with col4:
    tv_options = ["Nenhum"] + tv_formats
    selected_tv = st.selectbox("Trade Value", tv_options)

query_parts = []
params = []

if selected_tv != "Nenhum":
    tv_join = "LEFT JOIN trade_values tv ON r.player_id = tv.player_id AND tv.source = 'fantasycalc' AND tv.format = ?"
    tv_cols = ", tv.value as \"TV\", tv.trend_30day as \"Trend 30d\""
    params.append(selected_tv)
else:
    tv_join = ""
    tv_cols = ""

params.extend([selected_type, selected_format])

pos_filter = ""
if selected_pos != "ALL":
    pos_filter = "AND r.position_rank LIKE ?"
    params.append(f"{selected_pos}%")

df = pd.read_sql_query(f"""
    SELECT
        r.rank as "#",
        r.player_name as "Jogador",
        COALESCE(p.team, '') as "Time",
        COALESCE(p.position, '') as "Pos",
        r.position_rank as "Pos Rank",
        r.tier as "Tier",
        r.pos_tier as "Pos Tier",
        r.avg_adp as "ADP",
        r.best as "Best",
        r.worst as "Worst",
        r.bye_week as "Bye",
        r.owned_pct as "Own%",
        r.ecr_delta as "ECR Δ"
        {tv_cols}
    FROM rankings r
    LEFT JOIN players p ON r.player_id = p.player_id
    {tv_join}
    WHERE r.ranking_type = ? AND r.format = ? AND r.week = 0
    {pos_filter}
    ORDER BY r.rank
""", conn, params=params)

conn.close()

if df.empty:
    st.warning("Sem dados para essa combinação.")
    st.stop()

search = st.text_input("Filtrar por nome", placeholder="Ex: Chase")
if search:
    df = df[df["Jogador"].str.contains(search, case=False, na=False)]

tier_col = "Pos Tier" if selected_pos != "ALL" else "Tier"
show_tiers = st.checkbox("Agrupar por tier", value=True)

st.text(f"{len(df)} jogadores | {selected_type} {selected_format}" + (f" | Trade Value: {selected_tv}" if selected_tv != "Nenhum" else ""))

if show_tiers and tier_col in df.columns:
    tiers = sorted(df[tier_col].dropna().unique())
    for tier in tiers:
        tier_df = df[df[tier_col] == tier].reset_index(drop=True)
        st.markdown(f"**Tier {int(tier)}** ({len(tier_df)})")
        st.dataframe(tier_df, use_container_width=True, hide_index=True)
else:
    st.dataframe(df, use_container_width=True, hide_index=True)
