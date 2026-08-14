import argparse
import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def run_cmd(args):
    subprocess.run([sys.executable] + args, check=True)


def cmd_install(_):
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)


def cmd_init(_):
    run_cmd(["-m", "core.db"])


def cmd_sync(args):
    cmd = ["scrapers/sync_sleeper.py", args.user, "--season", args.season]
    if args.skip_players:
        cmd.append("--skip-players")
    run_cmd(cmd)


def cmd_rankings(args):
    if args.all:
        run_cmd(["scrapers/fantasypros.py", "--all"])
    else:
        cmd = ["scrapers/fantasypros.py", "--type", args.type, "--format", args.format]
        if args.week:
            cmd.extend(["--week", str(args.week)])
        run_cmd(cmd)


def cmd_update(args):
    cmd_sync(args)
    print("\n--- Updating all rankings ---\n")
    run_cmd(["scrapers/fantasypros.py", "--all"])
    print("\n--- Updating all trade values ---\n")
    run_cmd(["scrapers/fantasycalc.py", "--all"])


def cmd_trade_values(args):
    if args.all:
        run_cmd(["scrapers/fantasycalc.py", "--all", "--teams", str(args.teams)])
    else:
        run_cmd(["scrapers/fantasycalc.py", "--format", args.format, "--teams", str(args.teams)])


def cmd_app(_):
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app/Home.py"], check=True)


def cmd_clean(_):
    db_path = os.path.join("data", "fantasy.db")
    for folder in ["data/rankings", "data/trade_values"]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.endswith(".json"):
                    os.remove(os.path.join(folder, f))
                    print(f"Removed {folder}/{f}")
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed {db_path}")
    print("Clean complete. Run 'python manage.py sync <user>' to rebuild.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sleeper Fantasy Manager CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("install", help="Install dependencies")
    sub.add_parser("init", help="Initialize database")

    p_sync = sub.add_parser("sync", help="Sync Sleeper data")
    p_sync.add_argument("user", help="Sleeper username")
    p_sync.add_argument("--season", default="2026")
    p_sync.add_argument("--skip-players", action="store_true")

    p_rank = sub.add_parser("rankings", help="Fetch FantasyPros rankings")
    p_rank.add_argument("--type", choices=["redraft", "dynasty", "rookie", "weekly", "ros"])
    p_rank.add_argument("--format", choices=["half", "ppr", "std", "sf_half", "sf_ppr", "sf_std", "sf", "1qb"])
    p_rank.add_argument("--week", type=int)
    p_rank.add_argument("--all", action="store_true", help="Fetch all ranking formats")

    p_update = sub.add_parser("update", help="Sync Sleeper + fetch all rankings + trade values")
    p_update.add_argument("user", help="Sleeper username")
    p_update.add_argument("--season", default="2026")
    p_update.add_argument("--skip-players", action="store_true")

    p_tv = sub.add_parser("trade-values", help="Fetch FantasyCalc trade values")
    p_tv.add_argument("--format", choices=[
        "dynasty_sf_half", "dynasty_sf_ppr", "dynasty_1qb_half", "dynasty_1qb_ppr",
        "redraft_sf_half", "redraft_sf_ppr", "redraft_1qb_half", "redraft_1qb_ppr",
    ])
    p_tv.add_argument("--teams", type=int, default=12, choices=[10, 12, 14])
    p_tv.add_argument("--all", action="store_true", help="Fetch all formats")

    sub.add_parser("app", help="Start Streamlit app")
    sub.add_parser("clean", help="Remove database and cached rankings")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "install": cmd_install,
        "init": cmd_init,
        "sync": cmd_sync,
        "rankings": cmd_rankings,
        "trade-values": cmd_trade_values,
        "update": cmd_update,
        "app": cmd_app,
        "clean": cmd_clean,
    }
    commands[args.command](args)
