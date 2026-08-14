from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates

from core.db import get_conn
from core.league_repo import get_my_leagues
from core.waiver_repo import get_waivers_data

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("/")
def waivers_page(
    request: Request,
    tab: str = "dynasty",
    ranking_mode: str = "season",
    week: int = 1,
    show_kdst: str = "",
    conn=Depends(get_conn),
):
    leagues = get_my_leagues(conn)
    dynasty_data, redraft_data = get_waivers_data(
        conn, leagues, tab, ranking_mode, week, show_kdst
    )

    return templates.TemplateResponse(request, "waivers.html", {
        "dynasty_data": dynasty_data,
        "redraft_data": redraft_data,
        "tab": tab,
        "ranking_mode": ranking_mode,
        "week": week,
        "show_kdst": show_kdst,
    })