from pathlib import Path
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.db import get_conn
from core.formats import format_adp
from core.league_repo import get_all_leagues
from core.draft_repo import get_draft_context, save_favorite, remove_favorite

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("/")
def draft_page(request: Request, league_id: str = "", conn=Depends(get_conn)):
    leagues = get_all_leagues(conn)

    if not leagues:
        return templates.TemplateResponse(request, "draft.html", {
            "leagues": [], "ctx": None, "league_id": "",
        })

    if not league_id:
        league_id = leagues[0]["league_id"]

    league = None
    for lg in leagues:
        if lg["league_id"] == league_id:
            league = dict(lg)
            break
    if not league:
        league = dict(leagues[0])
        league_id = league["league_id"]

    ctx = None
    error = None
    try:
        ctx = get_draft_context(conn, league)
    except Exception as e:
        error = str(e)

    return templates.TemplateResponse(request, "draft.html", {
        "leagues": [dict(lg) for lg in leagues],
        "league_id": league_id,
        "league": league,
        "ctx": ctx,
        "error": error,
        "format_adp": format_adp,
    })


@router.post("/favorite")
def toggle_favorite(
    request: Request,
    draft_id: str = Form(...),
    player_id: str = Form(...),
    action: str = Form(...),
    conn=Depends(get_conn),
):
    if action == "remove":
        remove_favorite(conn, draft_id, player_id)
    else:
        save_favorite(conn, draft_id, player_id, action)
    return HTMLResponse('<span class="status-ok">✓</span>')