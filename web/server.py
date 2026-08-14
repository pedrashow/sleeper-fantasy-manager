import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.routes import home, health, draft, player, waivers

app = FastAPI(title="Sleeper Fantasy Manager")

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

app.include_router(home.router)
app.include_router(health.router, prefix="/health")
app.include_router(draft.router, prefix="/draft")
app.include_router(player.router, prefix="/player")
app.include_router(waivers.router, prefix="/waivers")
