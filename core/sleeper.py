import requests
import time

BASE_URL = "https://api.sleeper.app/v1"
PLAYERS_CACHE = None
PLAYERS_CACHE_TIME = 0
PLAYERS_CACHE_TTL = 3600


def _get(path):
    resp = requests.get(f"{BASE_URL}{path}", timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_user(username):
    return _get(f"/user/{username}")


def get_user_leagues(user_id, season="2026", sport="nfl"):
    return _get(f"/user/{user_id}/leagues/{sport}/{season}")


def get_league(league_id):
    return _get(f"/league/{league_id}")


def get_rosters(league_id):
    return _get(f"/league/{league_id}/rosters")


def get_users(league_id):
    return _get(f"/league/{league_id}/users")


def get_matchups(league_id, week):
    return _get(f"/league/{league_id}/matchups/{week}")


def get_transactions(league_id, week):
    return _get(f"/league/{league_id}/transactions/{week}")


def get_traded_picks(league_id):
    return _get(f"/league/{league_id}/traded_picks")


def get_draft(draft_id):
    return _get(f"/draft/{draft_id}")


def get_draft_picks(draft_id):
    return _get(f"/draft/{draft_id}/picks")


def get_all_players():
    global PLAYERS_CACHE, PLAYERS_CACHE_TIME
    now = time.time()
    if PLAYERS_CACHE and (now - PLAYERS_CACHE_TIME) < PLAYERS_CACHE_TTL:
        return PLAYERS_CACHE
    PLAYERS_CACHE = _get("/players/nfl")
    PLAYERS_CACHE_TIME = now
    return PLAYERS_CACHE


def classify_league(league_data):
    settings = league_data.get("settings", {})
    scoring = league_data.get("scoring_settings", {})
    positions = league_data.get("roster_positions", [])

    type_map = {0: "redraft", 1: "keeper", 2: "dynasty"}
    league_type = type_map.get(settings.get("type", 0), "redraft")

    rec_scoring = scoring.get("rec", 0)
    scoring_map = {1.0: "ppr", 0.5: "half_ppr", 0.0: "standard"}
    scoring_type = scoring_map.get(rec_scoring, "custom")

    is_sf = 1 if "SUPER_FLEX" in positions else 0
    is_tep = 1 if scoring.get("bonus_rec_te", 0) > 0 else 0
    has_k = 1 if "K" in positions else 0
    has_dst = 1 if "DEF" in positions else 0

    sf_label = "sf" if is_sf else "1qb"
    sc_label = {1.0: "ppr", 0.5: "half", 0.0: "std"}.get(rec_scoring, "half")
    ranking_format = f"{sf_label}_{sc_label}"

    return {
        "league_type": league_type,
        "scoring_type": scoring_type,
        "is_superflex": is_sf,
        "is_tep": is_tep,
        "has_kicker": has_k,
        "has_dst": has_dst,
        "ranking_format": ranking_format,
    }
