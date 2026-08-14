from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates

from core.db import get_conn
from core.player_repo import search_players, get_player_detail

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("/")
def player_page(request: Request, q: str = "", conn=Depends(get_conn)):
    if not q:
        return templates.TemplateResponse(request, "player.html", {"q": "", "results": [], "player": None})

    results = search_players(conn, q)

    player = None
    if results:
        player = get_player_detail(conn, results[0]["player_id"])

    return templates.TemplateResponse(request, "player.html", {
        "q": q,
        "results": [dict(r) for r in results],
        "player": player,
    })


@router.get("/detail/{player_id}")
def player_detail(request: Request, player_id: str, conn=Depends(get_conn)):
    player = get_player_detail(conn, player_id)
    return templates.TemplateResponse(request, "player_detail.html", {"player": player})