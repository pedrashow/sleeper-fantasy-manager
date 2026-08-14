import time

import requests

from core.config import SLEEPER_API_URL

_cache = {}


def _get(path):
    resp = requests.get(f"{SLEEPER_API_URL}{path}", timeout=15)
    resp.raise_for_status()
    return resp.json()


def cached_get(path, ttl=15):
    now = time.time()
    if path in _cache and now - _cache[path][1] < ttl:
        return _cache[path][0]
    data = _get(path)
    _cache[path] = (data, now)
    return data


def clear_cache():
    _cache.clear()


def get_user(username):
    return cached_get(f"/user/{username}", ttl=3600)


def get_user_leagues(user_id, season="2026", sport="nfl"):
    return cached_get(f"/user/{user_id}/leagues/{sport}/{season}", ttl=300)


def get_league(league_id):
    return cached_get(f"/league/{league_id}", ttl=300)


def get_rosters(league_id):
    return cached_get(f"/league/{league_id}/rosters", ttl=60)


def get_users(league_id):
    return cached_get(f"/league/{league_id}/users", ttl=300)


def get_matchups(league_id, week):
    return cached_get(f"/league/{league_id}/matchups/{week}", ttl=30)


def get_transactions(league_id, week):
    return cached_get(f"/league/{league_id}/transactions/{week}", ttl=60)


def get_traded_picks(league_id):
    return cached_get(f"/league/{league_id}/traded_picks", ttl=300)


def get_draft(draft_id):
    return cached_get(f"/draft/{draft_id}", ttl=15)


def get_draft_picks(draft_id):
    return cached_get(f"/draft/{draft_id}/picks", ttl=15)


def get_all_players():
    return cached_get("/players/nfl", ttl=3600)


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
