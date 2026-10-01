"""Player-name helpers, plus a name -> NFL team index from Sleeper's free API.

Odds API outcomes only carry a player name, so the team index is how we find
the *opposing* QB and rushers when projecting a D/ST.
"""
from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

from .http import get_json
from .teams import canon

SLEEPER_PLAYERS = "https://api.sleeper.app/v1/players/nfl"
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_name(name: str) -> str:
    name = re.sub(r"[^a-z ]", "", name.lower().replace("-", " "))
    return " ".join(w for w in name.split() if w not in SUFFIXES)


def match_name(name: str, candidates: Iterable[str]) -> Optional[str]:
    """Find `name` among normalized candidate names (exact, then fuzzy)."""
    target = norm_name(name)
    cands = list(candidates)
    if target in cands:
        return target
    close = difflib.get_close_matches(target, cands, n=1, cutoff=0.85)
    return close[0] if close else None


def load_team_index(cache_dir: Path, max_age_days: float = 3) -> Dict[str, Set[str]]:
    """normalized name -> set of team abbrs. Sleeper asks for <=1 fetch/day; we cache."""
    path = cache_dir / "sleeper_team_index.json"
    if path.exists() and time.time() - path.stat().st_mtime < max_age_days * 86400:
        return {k: set(v) for k, v in json.loads(path.read_text()).items()}
    players, _ = get_json(SLEEPER_PLAYERS, timeout=60)
    index: Dict[str, Set[str]] = {}
    for p in players.values():
        if p.get("team") and p.get("full_name"):
            index.setdefault(norm_name(p["full_name"]), set()).add(canon(p["team"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: sorted(v) for k, v in index.items()}))
    return index
