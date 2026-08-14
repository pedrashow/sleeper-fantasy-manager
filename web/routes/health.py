import os
import sys
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fantasy.db"

SOURCES = {
    "fantasypros": {
        "label": "FantasyPros",
        "table": "rankings",
        "date_col": "fetched_at",
        "name_col": "player_name",
        "id_col": "player_id",
    },
    "longbuild": {
        "label": "Long Build",
        "table": "longbuild_rankings",
        "date_col": "updated_at",
        "name_col": "full_name",
        "id_col": "player_id",
    },
    "winnow": {
        "label": "Win-Now",
        "table": "winnow_rankings",
        "date_col": "updated_at",
        "name_col": "full_name",
        "id_col": "player_id",
    },
    "fantasycalc": {
        "label": "FantasyCalc",
        "table": "trade_values",
        "date_col": "fetched_at",
        "name_col": "player_name",
        "id_col": "player_id",
    },
}


def get_db():
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/")
def health(request: Request):
    health = []
    try:
        db = get_db()

        sleeper_row = db.execute(
            "SELECT COUNT(*) as total FROM players WHERE position IN ('QB','RB','WR','TE') AND team != 'FA'"
        ).fetchone()
        sleeper_total = sleeper_row["total"] if sleeper_row else 0

        sleeper_fa = db.execute(
            "SELECT COUNT(*) as total FROM players WHERE position IN ('QB','RB','WR','TE') AND team = 'FA'"
        ).fetchone()
        fa_count = sleeper_fa["total"] if sleeper_fa else 0

        health.append({
            "key": "sleeper",
            "name": "Sleeper",
            "total": sleeper_total,
            "fa_count": fa_count,
            "matched": 0,
            "unmatched": 0,
            "not_in_source": 0,
            "pct": 0,
            "last_update": None,
            "is_base": True,
        })

        for key, src in SOURCES.items():
            try:
                row = db.execute(
                    f"SELECT "
                    f"COUNT(DISTINCT {src['name_col']}) as total, "
                    f"COUNT(DISTINCT CASE WHEN player_id IS NOT NULL THEN {src['name_col']} END) as matched, "
                    f"COUNT(DISTINCT CASE WHEN player_id IS NULL THEN {src['name_col']} END) as unmatched "
                    f"FROM {src['table']}"
                ).fetchone()
                total = row["total"] or 0
                matched = row["matched"] or 0
                unmatched = row["unmatched"] or 0

                not_in_source = db.execute(
                    f"SELECT COUNT(*) as cnt FROM players "
                    f"WHERE position IN ('QB','RB','WR','TE') "
                    f"AND team != 'FA' "
                    f"AND player_id NOT IN "
                    f"(SELECT DISTINCT player_id FROM {src['table']} WHERE player_id IS NOT NULL)"
                ).fetchone()["cnt"]

                date_row = db.execute(
                    f"SELECT MAX({src['date_col']}) FROM {src['table']}"
                ).fetchone()
                last_update = date_row[0] if date_row else None

                health.append({
                    "key": key,
                    "name": src["label"],
                    "total": total,
                    "matched": matched,
                    "unmatched": unmatched,
                    "not_in_source": not_in_source,
                    "pct": round(matched / total * 100, 1) if total > 0 else 0,
                    "last_update": last_update,
                    "is_base": False,
                })
            except Exception:
                health.append({
                    "key": key,
                    "name": src["label"],
                    "total": 0,
                    "matched": 0,
                    "unmatched": 0,
                    "not_in_source": 0,
                    "pct": 0,
                    "last_update": None,
                    "is_base": False,
                    "error": True,
                })

        db.close()
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "health.html",
        {"health": health},
    )


@router.get("/detail/{source_key}")
def health_detail(source_key: str, request: Request):
    if source_key not in SOURCES:
        return HTMLResponse("<tr><td colspan='8'>Unknown source</td></tr>")

    src = SOURCES[source_key]
    db = get_db()

    in_source_not_sleeper = db.execute(
        f"SELECT DISTINCT {src['name_col']} as name, position, team "
        f"FROM {src['table']} WHERE player_id IS NULL "
        f"ORDER BY position, {src['name_col']}"
    ).fetchall()

    total_not_in = db.execute(
        f"SELECT COUNT(*) as cnt FROM players "
        f"WHERE position IN ('QB','RB','WR','TE') "
        f"AND team != 'FA' "
        f"AND player_id NOT IN "
        f"(SELECT DISTINCT player_id FROM {src['table']} WHERE player_id IS NOT NULL)"
    ).fetchone()["cnt"]

    in_sleeper_not_source = db.execute(
        f"SELECT full_name, position, team FROM players "
        f"WHERE position IN ('QB','RB','WR','TE') "
        f"AND team != 'FA' "
        f"AND player_id NOT IN "
        f"(SELECT DISTINCT player_id FROM {src['table']} WHERE player_id IS NOT NULL) "
        f"ORDER BY position, full_name LIMIT 300"
    ).fetchall()

    db.close()

    return templates.TemplateResponse(
        request,
        "health_detail.html",
        {
            "source_label": src["label"],
            "in_source": in_source_not_sleeper,
            "in_sleeper": in_sleeper_not_source,
            "total_not_in": total_not_in,
        },
    )


@router.post("/import/{source_key}")
def run_import(source_key: str, request: Request, week: int = None, sheet: str = None, filepath: str = "data/rsp.xlsx"):
    import io
    import sys
    from contextlib import redirect_stdout, redirect_stderr

    buf = io.StringIO()
    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            if source_key == "sleeper":
                from scrapers.sync_sleeper import run_sync
                run_sync("pedrashow")

            elif source_key == "fantasypros":
                from scrapers.fantasypros import run_all
                run_all()

            elif source_key == "fantasycalc":
                from scrapers.fantasycalc import run_all
                run_all()

            elif source_key == "weekly" and week:
                from scrapers.fantasypros import run
                for fmt in ["half", "ppr", "std"]:
                    run("weekly", fmt, week)

            elif source_key == "rsp" and sheet:
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
                from import_longbuild import import_sheet
                project_root = Path(__file__).resolve().parent.parent.parent
                xlsx_abs = str(project_root / filepath) if not os.path.isabs(filepath) else filepath
                db_abs = str(project_root / "data" / "fantasy.db")
                import_sheet(xlsx_abs, sheet, db_abs)

            else:
                return HTMLResponse(f'<span class="status-err">Unknown source: {source_key}</span>')

        output = buf.getvalue().strip()
        lines = output.split("\n")
        last_lines = "\n".join(lines[-5:]) if len(lines) > 5 else output
        return HTMLResponse(f'<span class="status-ok">✓ Done</span><pre style="font-size:11px;color:var(--text-dim);margin-top:4px;white-space:pre-wrap;">{last_lines}</pre>')

    except Exception as e:
        output = buf.getvalue().strip()
        err_msg = f"{str(e)[:200]}"
        if output:
            err_msg = f"{output[-200:]}\n{err_msg}"
        return HTMLResponse(f'<span class="status-err">✗ Failed</span><pre style="font-size:11px;color:var(--danger);margin-top:4px;white-space:pre-wrap;">{err_msg}</pre>')
