from pathlib import Path

from fastapi.templating import Jinja2Templates

from core.db import get_conn

TEMPLATES = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
