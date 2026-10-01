#!/usr/bin/env python3
"""Pick fantasy starters from Vegas player-prop lines.

Usage:
  python3 lineup.py                 # all leagues in config.json
  python3 lineup.py netties         # one league
  python3 lineup.py -v              # show the stat line behind each projection
  python3 lineup.py --dry-run       # show credit cost without spending any
  python3 lineup.py --refresh       # ignore cached odds (spends credits)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from ff.espn_paste import parse_espn_roster
from ff.odds import OddsClient
from ff.optimize import best_lineup
from ff.players import load_team_index
from ff.project import (MARKETS_BY_POS, GameLines, implied_totals, project_dst,
                        project_kicker, project_skill)
from ff.teams import NAME_TO_ABBR, TEAMS

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def team_schedule(events: List[dict]) -> Dict[str, dict]:
    """Team abbr -> its next game: {id, opp, home, kickoff}."""
    now = datetime.now(timezone.utc)
    sched: Dict[str, dict] = {}
    for e in sorted(events, key=lambda e: e["commence_time"]):
        kickoff = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
        home, away = NAME_TO_ABBR[e["home_team"]], NAME_TO_ABBR[e["away_team"]]
        for team, opp, is_home in ((home, away, True), (away, home, False)):
            if team not in sched:
                sched[team] = {"id": e["id"], "opp": opp, "home": is_home,
                               "kickoff": kickoff, "started": kickoff <= now}
    return sched


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("leagues", nargs="*", help="league names from config.json (default: all)")
    ap.add_argument("-v", "--verbose", action="store_true", help="show stat lines behind projections")
    ap.add_argument("--dry-run", action="store_true", help="print credit cost, fetch nothing paid")
    ap.add_argument("--refresh", action="store_true", help="ignore cached odds")
    ap.add_argument("--cache-hours", type=float, default=6, help="reuse cached odds this long (default 6)")
    args = ap.parse_args()

    load_env()
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        sys.exit("ODDS_API_KEY missing: add `ODDS_API_KEY=yourkey` to .env")

    config = json.loads((ROOT / "config.json").read_text())
    names = args.leagues or list(config["leagues"])
    leagues = {}
    for name in names:
        if name not in config["leagues"]:
            sys.exit(f"Unknown league {name!r}; choices: {', '.join(config['leagues'])}")
        lc = config["leagues"][name]
        slots, roster = parse_espn_roster((ROOT / lc["roster_file"]).read_text())
        scoring = {**config["scoring"], **lc.get("scoring", {})}
        leagues[name] = (slots, roster, scoring)

    client = OddsClient(api_key, CACHE, args.cache_hours, args.refresh)
    sched = team_schedule(client.events())

    # Which markets each game needs, across every league (shared fetch).
    needed: Dict[str, set] = {}
    for slots, roster, _ in leagues.values():
        for p in roster:
            game = sched.get(p.team)
            if game and not game["started"] and not p.unavailable:
                needed.setdefault(game["id"], set()).update(MARKETS_BY_POS[p.pos])

    if args.dry_run:
        uncached = sum(1 for gid, ms in needed.items() for m in ms
                       if args.refresh or not (CACHE / gid / f"{m}.json").exists())
        print(f"{len(needed)} games, up to {uncached} credits for props "
              f"+ 2 for game lines (markets with no lines yet are free).")
        return 0

    implied = {NAME_TO_ABBR[t]: v for t, v in implied_totals(client.game_lines()).items()}
    game_lines = {gid: GameLines(client.event_markets(gid, ms)) for gid, ms in needed.items()}
    any_dst = any(p.pos == "D/ST" for _, roster, _ in leagues.values() for p in roster)
    team_index = load_team_index(CACHE) if any_dst else {}

    for name, (slots, roster, s) in leagues.items():
        rows = []
        for p in roster:
            game = sched.get(p.team)
            row = {"player": p, "pos": p.pos, "points": None, "detail": "", "notes": [],
                   "available": not p.unavailable, "locked_slot": None, "game": game}
            if p.unavailable:
                row["notes"].append(f"status {p.status}")
            elif game is None:
                row["notes"].append("no upcoming game (bye?)")
            elif game["started"]:
                row["notes"].append("game started: locked")
                if p.espn_slot not in ("Bench", "IR"):
                    row["locked_slot"] = p.espn_slot
                row["available"] = False
            else:
                lines = game_lines[game["id"]]
                if p.pos == "K":
                    proj = project_kicker(p.name, lines, implied.get(p.team), s)
                elif p.pos == "D/ST":
                    proj = project_dst(game["opp"], lines, implied.get(game["opp"]), team_index, s)
                else:
                    proj = project_skill(p.name, p.pos, lines, s)
                row.update(points=proj.points, detail=proj.detail)
                row["notes"] += proj.notes
                if p.status:
                    row["notes"].append(f"status {p.status}")
            rows.append(row)
        print_league(name, slots, rows, s, args.verbose)

    print(f"Odds API credits used this run: {client.credits_used}"
          + (f" | remaining this month: {client.credits_remaining}" if client.credits_remaining else ""))
    return 0


def fmt_row(slot: str, r: dict, verbose: bool) -> str:
    p, g = r["player"], r["game"]
    opp = (("vs " if g["home"] else "@ ") + g["opp"]) if g else "BYE"
    pts = "  --" if r["points"] is None else f"{r['points']:5.1f}"
    line = f"  {slot:<6} {p.name:<24} {p.team:<4} {opp:<7} {pts}"
    extra = list(r["notes"])
    if verbose and r["detail"]:
        extra.insert(0, r["detail"])
    return line + (f"   [{'; '.join(extra)}]" if extra else "")


def print_league(name: str, slots: List[str], rows: List[dict], s: dict, verbose: bool) -> None:
    ppr = {1: "PPR", 0.5: "half PPR", 0: "standard"}.get(s["reception"], f"{s['reception']} PPR")
    print(f"\n=== {name.upper()} ({ppr}) ===")
    lineup = best_lineup(slots, rows)
    starters = {id(r) for r in lineup if r}
    total = 0.0
    for slot, r in zip(slots, lineup):
        if r is None:
            print(f"  {slot:<6} (nobody eligible)")
            continue
        total += r["points"] or 0
        print(fmt_row(slot, r, verbose))
    print(f"  {'':<6} {'PROJECTED TOTAL':<37} {total:5.1f}")
    print("  Bench:")
    bench = sorted((r for r in rows if id(r) not in starters),
                   key=lambda r: -(r["points"] if r["points"] is not None else -1))
    for r in bench:
        print(fmt_row("", r, verbose))

    to_start = [r["player"].name for r in lineup if r and r["player"].espn_slot in ("Bench", "IR")]
    to_sit = [r["player"].name for r in rows
              if id(r) not in starters and r["player"].espn_slot not in ("Bench", "IR")]
    if to_start or to_sit:
        print(f"  Changes vs ESPN: START {', '.join(to_start) or '-'} | SIT {', '.join(to_sit) or '-'}")
    else:
        print("  Changes vs ESPN: none, your current lineup matches.")
    no_lines = [r["player"].name for r in rows if r["available"] and r["points"] is None]
    if no_lines:
        print(f"  Heads up: no lines yet for {', '.join(no_lines)}. Re-run closer to kickoff.")


if __name__ == "__main__":
    sys.exit(main())
