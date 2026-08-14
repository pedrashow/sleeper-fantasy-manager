from pathlib import Path

SLEEPER_USERNAME = "pedrashow"
SLEEPER_API_URL = "https://api.sleeper.app/v1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(PROJECT_ROOT / "data" / "fantasy.db")

POS_COLORS = {
    "QB": "#e74c6f", "RB": "#4caf8a", "WR": "#4a9bd9",
    "TE": "#e8a838", "K": "#9b7fc4", "DEF": "#7f8c8d",
}

POS_PASTEL = {
    "QB": "#fce4e4", "RB": "#e0f5e0", "WR": "#ddeeff",
    "TE": "#fef0dd", "K": "#ede0f5", "DEF": "#e5e8ea",
}

SCORING_MAP = {"ppr": "ppr", "half_ppr": "half", "standard": "std"}
