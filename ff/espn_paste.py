"""Parse a roster copy-pasted from ESPN's "My Team" page.

Each player block looks like:
    <slot>                 e.g. QB, FLEX, Bench
    <Name><Name>           name printed twice back to back
    <Name>
    [<status>]             optional: Q, D, O, IR, ...
    <team>
    <position>
An empty slot is the slot label followed by "Empty".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .teams import TEAMS, canon

SLOT_LABELS = {
    "QB", "RB", "WR", "TE", "FLEX", "D/ST", "K", "OP",
    "RB/WR", "WR/TE", "RB/WR/TE", "Bench", "IR",
}
STATUSES = {"Q", "D", "O", "IR", "SSPD", "NA", "P", "DTD", "OUT"}
POSITIONS = {"QB", "RB", "WR", "TE", "K", "D/ST"}


@dataclass
class RosterPlayer:
    name: str
    team: str
    pos: str
    status: Optional[str]
    espn_slot: str  # slot ESPN currently has them in

    @property
    def unavailable(self) -> bool:
        return self.status in {"O", "IR", "SSPD", "OUT"}


def _is_doubled(line: str) -> bool:
    n = len(line)
    return n >= 2 and n % 2 == 0 and line[: n // 2] == line[n // 2:]


def parse_espn_roster(text: str) -> Tuple[List[str], List[RosterPlayer]]:
    """Return (starting slots in order, all rostered players)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    slots: List[str] = []
    players: List[RosterPlayer] = []
    i = 0
    while i < len(lines) - 1:
        label, nxt = lines[i], lines[i + 1]
        if label in SLOT_LABELS and (nxt == "Empty" or _is_doubled(nxt)):
            if label not in ("Bench", "IR"):
                slots.append(label)
            if nxt == "Empty":
                i += 2
                continue
            name = lines[i + 2]
            j = i + 3
            status = None
            if lines[j] in STATUSES:
                status = lines[j]
                j += 1
            team, pos = canon(lines[j]), lines[j + 1]
            if team not in TEAMS or pos not in POSITIONS:
                raise ValueError(f"Could not parse player block near {name!r}: team={team!r} pos={pos!r}")
            players.append(RosterPlayer(name, team, pos, status, label))
            i = j + 2
            continue
        i += 1
    if not slots or not players:
        raise ValueError("No roster found; paste the table from ESPN's My Team page.")
    return slots, players
