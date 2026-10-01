from __future__ import annotations

from typing import Dict, List, Optional, Set

ELIGIBLE: Dict[str, Set[str]] = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"}, "D/ST": {"D/ST"},
    "RB/WR": {"RB", "WR"}, "WR/TE": {"WR", "TE"},
    "FLEX": {"RB", "WR", "TE"}, "RB/WR/TE": {"RB", "WR", "TE"},
    "OP": {"QB", "RB", "WR", "TE"},
}


def best_lineup(slots: List[str], players: List[dict]) -> List[Optional[dict]]:
    """Fill slots greedily, most restrictive slot first.

    players: dicts with "pos", "points" (None = unknown, ranked last), "locked_slot"
    (slot the player must stay in because their game already kicked off), "available".
    Greedy is optimal here because the flex slots' eligibility sets nest.
    """
    lineup: List[Optional[dict]] = [None] * len(slots)
    used = set()

    for i, slot in enumerate(slots):
        for p in players:
            if id(p) not in used and p.get("locked_slot") == slot:
                lineup[i] = p
                used.add(id(p))
                break

    order = sorted((i for i in range(len(slots)) if lineup[i] is None),
                   key=lambda i: len(ELIGIBLE[slots[i]]))
    for i in order:
        pool = [p for p in players
                if id(p) not in used and p["available"] and p["pos"] in ELIGIBLE[slots[i]]]
        if pool:
            pick = max(pool, key=lambda p: -1 if p["points"] is None else p["points"])
            lineup[i] = pick
            used.add(id(pick))
    return lineup
