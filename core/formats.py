import math

from core.config import SCORING_MAP


def detect_ranking_type(league, live_rounds=None):
    lt = league.get("league_type", "redraft")
    dr = live_rounds or league.get("draft_rounds") or 0
    if lt == "dynasty":
        return "rookie" if dr <= 6 else "startup"
    return "redraft"


def map_ranking_format(league, ranking_type=None):
    if ranking_type is None:
        ranking_type = detect_ranking_type(league)
    if ranking_type in ("rookie", "startup", "dynasty"):
        return "sf" if league.get("is_superflex") else "1qb"
    scoring = league.get("scoring_type", "half_ppr")
    sc = SCORING_MAP.get(scoring, "half")
    if league.get("is_superflex"):
        return f"sf_{sc}"
    return sc


def tv_format_for_league(lg):
    lt = "dynasty" if lg.get("league_type") == "dynasty" else "redraft"
    sf = "sf" if lg.get("is_superflex") else "1qb"
    sc = {"ppr": "ppr", "half_ppr": "half", "standard": "half"}.get(
        lg.get("scoring_type", ""), "half"
    )
    return f"{lt}_{sf}_{sc}"


def ranking_type_for_db(ranking_type):
    return "dynasty" if ranking_type == "startup" else ranking_type


def ranking_type_label(ranking_type):
    return {"rookie": "Rookie", "startup": "Startup", "redraft": "Redraft"}.get(
        ranking_type, ranking_type
    )


def format_adp(adp, num_teams):
    if adp is None or num_teams <= 0:
        return ""
    try:
        adp = float(adp)
    except (TypeError, ValueError):
        return ""
    if adp <= 0:
        return ""
    rd = int(math.ceil(adp / num_teams))
    pick = int(((adp - 1) % num_teams) + 1)
    return f"{rd}.{pick:02d}"
