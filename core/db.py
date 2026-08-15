import os
import sqlite3
from contextlib import contextmanager

from core.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS leagues (
    league_id TEXT PRIMARY KEY,
    name TEXT,
    season TEXT,
    league_type TEXT,
    scoring_type TEXT,
    is_superflex INTEGER DEFAULT 0,
    is_tep INTEGER DEFAULT 0,
    has_kicker INTEGER DEFAULT 0,
    has_dst INTEGER DEFAULT 0,
    roster_positions TEXT,
    scoring_settings TEXT,
    total_rosters INTEGER,
    draft_id TEXT,
    draft_rounds INTEGER,
    taxi_slots INTEGER DEFAULT 0,
    reserve_slots INTEGER DEFAULT 0,
    ranking_format TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT,
    league_id TEXT,
    display_name TEXT,
    team_name TEXT,
    avatar TEXT,
    roster_id INTEGER,
    PRIMARY KEY (user_id, league_id)
);

CREATE TABLE IF NOT EXISTS rosters (
    roster_id INTEGER,
    league_id TEXT,
    owner_id TEXT,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    ties INTEGER DEFAULT 0,
    fpts REAL DEFAULT 0,
    fpts_against REAL DEFAULT 0,
    waiver_position INTEGER,
    waiver_budget_used INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (roster_id, league_id)
);

CREATE TABLE IF NOT EXISTS roster_players (
    league_id TEXT,
    roster_id INTEGER,
    player_id TEXT,
    slot TEXT,
    PRIMARY KEY (league_id, roster_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_rp_player ON roster_players(player_id);
CREATE INDEX IF NOT EXISTS idx_rp_league ON roster_players(league_id);

CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    full_name TEXT,
    first_name TEXT,
    last_name TEXT,
    position TEXT,
    team TEXT,
    age INTEGER,
    status TEXT,
    injury_status TEXT,
    years_exp INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_players_name ON players(full_name);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team);

CREATE TABLE IF NOT EXISTS rankings (
    player_name TEXT,
    player_id TEXT,
    source TEXT DEFAULT 'fantasypros',
    ranking_type TEXT,
    format TEXT,
    week INTEGER,
    rank INTEGER,
    position TEXT,
    team TEXT,
    position_rank TEXT,
    tier INTEGER,
    pos_tier INTEGER,
    avg_adp REAL,
    best INTEGER,
    worst INTEGER,
    bye_week INTEGER,
    owned_pct REAL,
    ecr_delta REAL,
    fetched_at TIMESTAMP,
    PRIMARY KEY (player_name, ranking_type, format, week, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_rankings_player ON rankings(player_id);
CREATE INDEX IF NOT EXISTS idx_rankings_type ON rankings(ranking_type, format);

CREATE TABLE IF NOT EXISTS trade_values (
    player_id TEXT,
    player_name TEXT,
    source TEXT,
    format TEXT,
    value INTEGER,
    overall_rank INTEGER,
    position_rank INTEGER,
    position TEXT,
    team TEXT,
    age REAL,
    trend_30day INTEGER,
    fetched_at TIMESTAMP,
    PRIMARY KEY (player_id, source, format)
);
CREATE INDEX IF NOT EXISTS idx_tv_source ON trade_values(source, format);
CREATE INDEX IF NOT EXISTS idx_tv_player ON trade_values(player_id);

CREATE TABLE IF NOT EXISTS draft_picks (
    draft_id TEXT,
    pick_no INTEGER,
    round INTEGER,
    roster_id INTEGER,
    player_id TEXT,
    player_name TEXT,
    position TEXT,
    team TEXT,
    picked_by TEXT,
    PRIMARY KEY (draft_id, pick_no)
);

CREATE TABLE IF NOT EXISTS traded_picks (
    league_id TEXT,
    round INTEGER,
    season TEXT,
    roster_id INTEGER,
    original_owner_id TEXT,
    current_owner_id TEXT,
    PRIMARY KEY (league_id, round, season, roster_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    league_id TEXT,
    type TEXT,
    status TEXT,
    week INTEGER,
    roster_ids TEXT,
    adds TEXT,
    drops TEXT,
    draft_picks_traded TEXT,
    created_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tx_league ON transactions(league_id);
CREATE INDEX IF NOT EXISTS idx_tx_type ON transactions(type);

CREATE TABLE IF NOT EXISTS matchups (
    league_id TEXT,
    week INTEGER,
    matchup_id INTEGER,
    roster_id INTEGER,
    points REAL,
    starters TEXT,
    starters_points TEXT,
    PRIMARY KEY (league_id, week, roster_id)
);

CREATE TABLE IF NOT EXISTS draft_favorites (
    draft_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'target',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (draft_id, player_id)
);

CREATE TABLE IF NOT EXISTS longbuild_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT,
    position TEXT,
    pos_rank INTEGER,
    overall_rank INTEGER,
    full_name TEXT,
    team TEXT,
    age INTEGER,
    notes TEXT,
    tier INTEGER,
    tier_name TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS winnow_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT,
    position TEXT,
    pos_rank INTEGER,
    overall_rank INTEGER,
    full_name TEXT,
    team TEXT,
    age INTEGER,
    notes TEXT,
    tier INTEGER,
    tier_name TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def get_db(db_path=None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path=None):
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with get_db(path) as conn:
        conn.executescript(SCHEMA)
        _run_migrations(conn)
    return path


def _run_migrations(conn):
    conn.execute("UPDATE trade_values SET format = REPLACE(format, 'lqb', '1qb') WHERE format LIKE '%lqb%'")
    try:
        conn.execute("SELECT 1 FROM draft_targets LIMIT 1")
        conn.execute("""
            INSERT OR IGNORE INTO draft_favorites (draft_id, player_id, type)
            SELECT draft_id, player_name, type FROM draft_targets
            WHERE player_name GLOB '[0-9]*'
        """)
        conn.execute("DROP TABLE IF EXISTS draft_targets")
    except Exception:
        pass


def reset_db(db_path=None):
    path = db_path or DB_PATH
    if os.path.exists(path):
        os.remove(path)
    return init_db(path)


def upsert_many(conn, table, rows, conflict_keys):
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    cols_str = ", ".join(columns)
    update_cols = [c for c in columns if c not in conflict_keys]
    update_str = ", ".join([f"{c}=excluded.{c}" for c in update_cols])
    conflict_str = ", ".join(conflict_keys)

    sql = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})"
    if update_cols:
        sql += f" ON CONFLICT({conflict_str}) DO UPDATE SET {update_str}"
    else:
        sql += f" ON CONFLICT({conflict_str}) DO NOTHING"

    conn.executemany(sql, [tuple(r[c] for c in columns) for r in rows])


if __name__ == "__main__":
    path = init_db()
    print(f"Database initialized at {path}")
