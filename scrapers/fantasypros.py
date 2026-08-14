import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.db import get_db, init_db, upsert_many

RANKINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "rankings")

OVERALL_URLS = {
    ("redraft", "half"): "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php",
    ("redraft", "ppr"): "https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php",
    ("redraft", "std"): "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php",
    ("redraft", "sf_half"): "https://www.fantasypros.com/nfl/rankings/half-point-ppr-superflex-cheatsheets.php",
    ("redraft", "sf_ppr"): "https://www.fantasypros.com/nfl/rankings/ppr-superflex-cheatsheets.php",
    ("redraft", "sf_std"): "https://www.fantasypros.com/nfl/rankings/superflex-cheatsheets.php",
    ("dynasty", "sf"): "https://www.fantasypros.com/nfl/rankings/dynasty-superflex.php",
    ("dynasty", "1qb"): "https://www.fantasypros.com/nfl/rankings/dynasty-overall.php",
    ("rookie", "sf"): "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-superflex.php",
    ("rookie", "1qb"): "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-overall.php",
    ("weekly", "half"): "https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php",
    ("weekly", "ppr"): "https://www.fantasypros.com/nfl/rankings/ppr-cheatsheets.php",
    ("weekly", "std"): "https://www.fantasypros.com/nfl/rankings/consensus-cheatsheets.php",
    ("ros", "half"): "https://www.fantasypros.com/nfl/rankings/ros-overall.php",
    ("ros", "ppr"): "https://www.fantasypros.com/nfl/rankings/ros-ppr-overall.php",
    ("ros", "std"): "https://www.fantasypros.com/nfl/rankings/ros-overall.php",
}

POSITION_URLS = {
    ("redraft", "half"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/qb-cheatsheets.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-rb-cheatsheets.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-wr-cheatsheets.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-te-cheatsheets.php",
        "K": "https://www.fantasypros.com/nfl/rankings/k-cheatsheets.php",
        "DST": "https://www.fantasypros.com/nfl/rankings/dst-cheatsheets.php",
    },
    ("redraft", "ppr"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/qb-cheatsheets.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/ppr-rb-cheatsheets.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/ppr-wr-cheatsheets.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/ppr-te-cheatsheets.php",
        "K": "https://www.fantasypros.com/nfl/rankings/k-cheatsheets.php",
        "DST": "https://www.fantasypros.com/nfl/rankings/dst-cheatsheets.php",
    },
    ("redraft", "std"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/qb-cheatsheets.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/rb-cheatsheets.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/wr-cheatsheets.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/te-cheatsheets.php",
        "K": "https://www.fantasypros.com/nfl/rankings/k-cheatsheets.php",
        "DST": "https://www.fantasypros.com/nfl/rankings/dst-cheatsheets.php",
    },
    ("redraft", "sf_half"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/qb-cheatsheets.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-rb-cheatsheets.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-wr-cheatsheets.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/half-point-ppr-te-cheatsheets.php",
        "K": "https://www.fantasypros.com/nfl/rankings/k-cheatsheets.php",
        "DST": "https://www.fantasypros.com/nfl/rankings/dst-cheatsheets.php",
    },
    ("redraft", "sf_ppr"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/qb-cheatsheets.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/ppr-rb-cheatsheets.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/ppr-wr-cheatsheets.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/ppr-te-cheatsheets.php",
        "K": "https://www.fantasypros.com/nfl/rankings/k-cheatsheets.php",
        "DST": "https://www.fantasypros.com/nfl/rankings/dst-cheatsheets.php",
    },
    ("redraft", "sf_std"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/qb-cheatsheets.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/rb-cheatsheets.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/wr-cheatsheets.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/te-cheatsheets.php",
        "K": "https://www.fantasypros.com/nfl/rankings/k-cheatsheets.php",
        "DST": "https://www.fantasypros.com/nfl/rankings/dst-cheatsheets.php",
    },
    ("dynasty", "sf"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/dynasty-qb.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/dynasty-rb.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/dynasty-wr.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/dynasty-te.php",
    },
    ("dynasty", "1qb"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/dynasty-qb.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/dynasty-rb.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/dynasty-wr.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/dynasty-te.php",
    },
    ("rookie", "sf"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-qb.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-rb.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-wr.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-te.php",
    },
    ("rookie", "1qb"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-qb.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-rb.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-wr.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/dynasty-rookies-te.php",
    },
    ("ros", "half"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/ros-qb.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/ros-rb.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/ros-wr.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/ros-te.php",
    },
    ("ros", "ppr"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/ros-qb.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/ros-ppr-rb.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/ros-ppr-wr.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/ros-ppr-te.php",
    },
    ("ros", "std"): {
        "QB": "https://www.fantasypros.com/nfl/rankings/ros-qb.php",
        "RB": "https://www.fantasypros.com/nfl/rankings/ros-rb.php",
        "WR": "https://www.fantasypros.com/nfl/rankings/ros-wr.php",
        "TE": "https://www.fantasypros.com/nfl/rankings/ros-te.php",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

DST_MAP = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}

ALIASES = {
    "Hollywood Brown": "Marquise Brown",
    "Bam Knight": "Isiah Pacheco",
    "Tommy Myers": "Thomas Myers",
}

REQUEST_DELAY = 2


def fetch_page(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_ecr_data(html):
    match = re.search(r"var\s+ecrData\s*=\s*({.*?});", html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def parse_html_table(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "ranking-table"})
    if not table:
        table = soup.find("table", class_="player-table")
    if not table:
        tables = soup.find_all("table")
        table = tables[0] if tables else None
    if not table:
        return []

    rows = []
    tbody = table.find("tbody")
    if not tbody:
        return []

    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 4:
            continue

        rank_text = cells[0].get_text(strip=True)
        if not rank_text.isdigit():
            continue

        player_cell = cells[1]
        name_el = player_cell.find("a", class_="player-name") or player_cell.find("a")
        player_name = name_el.get_text(strip=True) if name_el else player_cell.get_text(strip=True)

        team_el = player_cell.find("small") or player_cell.find("span", class_="player-team")
        team_text = team_el.get_text(strip=True).upper() if team_el else ""

        pos_text = ""
        for cell in cells[2:5]:
            txt = cell.get_text(strip=True)
            if re.match(r"^(QB|RB|WR|TE|K|DST|DEF)\d*$", txt):
                pos_text = txt
                break

        pos = re.match(r"(QB|RB|WR|TE|K|DST|DEF)", pos_text).group(1) if re.match(r"(QB|RB|WR|TE|K|DST|DEF)", pos_text) else ""
        pos_rank = pos_text

        rows.append({
            "rank": int(rank_text),
            "name": player_name,
            "team": team_text.replace("(", "").replace(")", "").strip(),
            "pos": pos,
            "position_rank": pos_rank,
            "tier": None,
            "best": None,
            "worst": None,
            "avg": None,
            "std_dev": None,
            "bye_week": None,
            "owned_pct": None,
            "ecr_delta": None,
        })

    return rows


def extract_players_from_ecr(ecr_data):
    players = ecr_data.get("players", [])
    rows = []
    for p in players:
        rows.append({
            "rank": p.get("rank_ecr", 0),
            "name": p.get("player_name", ""),
            "team": p.get("player_team_id", ""),
            "pos": p.get("player_position_id", ""),
            "position_rank": p.get("pos_rank", ""),
            "tier": p.get("tier"),
            "best": p.get("rank_min"),
            "worst": p.get("rank_max"),
            "avg": p.get("rank_ave"),
            "std_dev": p.get("rank_std"),
            "bye_week": p.get("player_bye_week"),
            "owned_pct": p.get("player_owned_avg"),
            "ecr_delta": p.get("player_ecr_delta"),
        })
    return rows


def fetch_and_parse(url):
    print(f"  Fetching: {url}")
    html = fetch_page(url)
    ecr_data = parse_ecr_data(html)
    if ecr_data:
        return extract_players_from_ecr(ecr_data)
    return parse_html_table(html)


def scrape_rankings(ranking_type, format_key, week=None):
    url_key = (ranking_type, format_key)
    overall_url = OVERALL_URLS.get(url_key)
    if not overall_url:
        print(f"No URL mapping for type={ranking_type}, format={format_key}")
        print(f"Available: {list(OVERALL_URLS.keys())}")
        return []

    if week and ranking_type == "weekly":
        overall_url = overall_url.replace(".php", f".php?week={week}")

    print(f"\n[{ranking_type.upper()} {format_key.upper()}] Fetching overall rankings...")
    players = fetch_and_parse(overall_url)

    if not players:
        print("  WARNING: No players found in overall page!")
        return []

    print(f"  Overall: {len(players)} players")

    pos_urls = POSITION_URLS.get(url_key, {})
    if pos_urls:
        pos_tier_map = {}

        for pos, pos_url in pos_urls.items():
            time.sleep(REQUEST_DELAY)

            if week and ranking_type == "weekly":
                pos_url = pos_url.replace(".php", f".php?week={week}")

            try:
                pos_players = fetch_and_parse(pos_url)
                for pp in pos_players:
                    if pp.get("tier") is not None:
                        pos_tier_map[pp["name"]] = pp["tier"]
                print(f"  {pos}: {len(pos_players)} players, {sum(1 for pp in pos_players if pp.get('tier'))} with tiers")
            except Exception as e:
                print(f"  {pos}: FAILED ({e})")

        for p in players:
            p["pos_tier"] = pos_tier_map.get(p["name"])
    else:
        for p in players:
            p["pos_tier"] = None

    print(f"\n  Total: {len(players)} players parsed")
    return players


def save_json(players, ranking_type, format_key, week=None):
    os.makedirs(RANKINGS_DIR, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    week_suffix = f"_w{week}" if week else ""
    filename = f"{ranking_type}_{format_key}{week_suffix}.json"
    filepath = os.path.join(RANKINGS_DIR, filename)

    data = {
        "source": "fantasypros",
        "type": ranking_type,
        "format": format_key,
        "week": week,
        "fetched_at": now,
        "players": players,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"  Saved to {filepath}")
    return filepath


def save_to_db(players, ranking_type, format_key, week=None):
    init_db()
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for p in players:
        rows.append({
            "player_name": p["name"],
            "player_id": None,
            "source": "fantasypros",
            "ranking_type": ranking_type,
            "format": format_key,
            "week": week or 0,
            "rank": p["rank"],
            "position": p.get("pos", ""),
            "team": p.get("team", ""),
            "position_rank": p.get("position_rank", ""),
            "tier": p.get("tier"),
            "pos_tier": p.get("pos_tier"),
            "avg_adp": p.get("avg"),
            "best": p.get("best"),
            "worst": p.get("worst"),
            "bye_week": p.get("bye_week"),
            "owned_pct": p.get("owned_pct"),
            "ecr_delta": p.get("ecr_delta"),
            "fetched_at": now,
        })

    with get_db() as conn:
        conn.execute(
            "DELETE FROM rankings WHERE ranking_type = ? AND format = ? AND week = ?",
            (ranking_type, format_key, week or 0),
        )
        upsert_many(conn, "rankings", rows, ["player_name", "ranking_type", "format", "week", "fetched_at"])

    print(f"  Inserted {len(rows)} rows into rankings table")


def _normalize_name(name):
    n = name.strip()
    n = re.sub(r"\s+(Jr\.?|Sr\.?|II|III|IV|V)$", "", n)
    n = n.replace(".", "")
    n = n.replace("'", "")
    n = n.replace("-", " ")
    return n.lower().strip()


def match_player_ids():
    with get_db() as conn:
        unmatched = conn.execute(
            "SELECT DISTINCT player_name, position_rank FROM rankings WHERE player_id IS NULL"
        ).fetchall()

        all_players = conn.execute(
            "SELECT player_id, full_name, position, team FROM players"
        ).fetchall()

        player_lookup = {}
        for p in all_players:
            normalized = _normalize_name(p["full_name"])
            exact = p["full_name"].lower()
            for key in [normalized, exact]:
                if key not in player_lookup:
                    player_lookup[key] = []
                player_lookup[key].append({
                    "player_id": p["player_id"],
                    "position": p["position"],
                    "team": p["team"],
                })
            if p["position"] == "DEF":
                pid_key = p["player_id"].lower()
                player_lookup[pid_key] = [{"player_id": p["player_id"], "position": "DEF", "team": p["player_id"]}]

        def pick_best(candidates, pos_hint):
            if len(candidates) == 1:
                return candidates[0]["player_id"]
            if pos_hint:
                pos_matches = [c for c in candidates if c["position"] == pos_hint]
                if pos_matches:
                    active = [c for c in pos_matches if c["team"] != "FA"]
                    return active[0]["player_id"] if active else pos_matches[0]["player_id"]
            active = [c for c in candidates if c["team"] != "FA"]
            return active[0]["player_id"] if active else candidates[0]["player_id"]

        matched = 0
        still_unmatched = []
        for row in unmatched:
            name = row["player_name"]
            pos_rank = row["position_rank"] or ""
            pos_hint = re.match(r"(QB|RB|WR|TE|K|DST|DEF)", pos_rank)
            pos_hint = pos_hint.group(1) if pos_hint else None

            pid = None

            if name in DST_MAP:
                abbr = DST_MAP[name].lower()
                candidates = player_lookup.get(abbr, [])
                if candidates:
                    pid = candidates[0]["player_id"]
            elif name in ALIASES:
                alias = ALIASES[name]
                candidates = player_lookup.get(alias.lower(), []) or player_lookup.get(_normalize_name(alias), [])
                if candidates:
                    pid = pick_best(candidates, pos_hint)
            else:
                normalized = _normalize_name(name)
                candidates = player_lookup.get(name.lower(), []) or player_lookup.get(normalized, [])
                if candidates:
                    pid = pick_best(candidates, pos_hint)

            if pid:
                conn.execute(
                    "UPDATE rankings SET player_id = ? WHERE player_name = ? AND player_id IS NULL",
                    (pid, name),
                )
                matched += 1
            else:
                still_unmatched.append(name)

        if unmatched:
            print(f"  Matched {matched}/{len(unmatched)} player names to IDs")
        if still_unmatched:
            print(f"  Still unmatched: {len(still_unmatched)}")
            for n in still_unmatched:
                print(f"    - {n}")


def run(ranking_type, format_key, week=None):
    players = scrape_rankings(ranking_type, format_key, week)
    if not players:
        return

    save_json(players, ranking_type, format_key, week)
    save_to_db(players, ranking_type, format_key, week)
    match_player_ids()
    print("  Done!\n")


def run_all():
    formats = [
        ("redraft", "half"),
        ("redraft", "ppr"),
        ("redraft", "std"),
        ("redraft", "sf_half"),
        ("ros", "half"),
        ("ros", "ppr"),
        ("ros", "std"),
        ("dynasty", "sf"),
        ("dynasty", "1qb"),
        ("rookie", "sf"),
        ("rookie", "1qb"),
    ]

    print("=" * 60)
    print("UPDATING ALL RANKINGS")
    print("=" * 60)

    for ranking_type, format_key in formats:
        run(ranking_type, format_key)
        time.sleep(REQUEST_DELAY)

    print("=" * 60)
    print("ALL RANKINGS UPDATED")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape FantasyPros rankings")
    parser.add_argument(
        "--type",
        choices=["redraft", "dynasty", "rookie", "weekly", "ros"],
        help="Type of ranking",
    )
    parser.add_argument(
        "--format",
        choices=["half", "ppr", "std", "sf_half", "sf_ppr", "sf_std", "sf", "1qb"],
        help="Scoring format",
    )
    parser.add_argument("--week", type=int, help="Week number (for weekly rankings)")
    parser.add_argument("--all", action="store_true", help="Fetch all ranking formats")
    args = parser.parse_args()

    if args.all:
        run_all()
    elif args.type and args.format:
        run(args.type, args.format, args.week)
    else:
        parser.print_help()
