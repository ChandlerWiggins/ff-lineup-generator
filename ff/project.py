"""Turn sportsbook lines into expected fantasy points.

How a line becomes an expected stat:
  * Over/under yardage & receptions: the line is roughly the median. We remove the
    vig from the over/under prices, and if the over is juiced (e.g. 55% after vig
    removal) we shift the estimate up by sd * z(0.55). sd is a fraction of the line.
  * Count stats (pass TDs, INTs, field goals): solve for the Poisson mean whose
    P(X > line) matches the no-vig over probability.
  * Anytime TD: P(>=1 TD) -> expected TDs via Poisson: lambda = -ln(1 - p).
Each book is converted separately, then averaged (consensus across books).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist, median
from typing import Dict, List, Optional, Set, Tuple

from .players import match_name, norm_name

# (sd as fraction of line, minimum sd) for markets modeled as normal around the line.
NORMAL_MARKETS = {
    "player_pass_yds": (0.25, 25.0),
    "player_rush_yds": (0.45, 12.0),
    "player_reception_yds": (0.55, 12.0),
    "player_receptions": (0.40, 1.2),
    "player_kicking_points": (0.35, 2.5),
}
POISSON_MARKETS = {"player_pass_tds", "player_pass_interceptions", "player_field_goals"}
SINGLE_SIDE_VIG = 1.045  # when a book posts only the over
TD_VIG = 1.07            # anytime-TD "Yes" prices usually come without a "No" side

QB_MARKETS = ["player_pass_yds", "player_pass_tds", "player_pass_interceptions",
              "player_rush_yds", "player_anytime_td"]
RB_MARKETS = ["player_rush_yds", "player_receptions", "player_reception_yds", "player_anytime_td"]
REC_MARKETS = ["player_receptions", "player_reception_yds", "player_anytime_td"]
K_MARKETS = ["player_kicking_points", "player_field_goals"]
DST_MARKETS = ["player_pass_yds", "player_pass_interceptions", "player_rush_yds"]
MARKETS_BY_POS = {"QB": QB_MARKETS, "RB": RB_MARKETS, "WR": REC_MARKETS, "TE": REC_MARKETS,
                  "K": K_MARKETS, "D/ST": DST_MARKETS}

# D/ST events that books don't offer lines for: league-average-ish baselines per game.
DST_BASE_SACKS = 2.4
DST_BASE_FUMBLE_RECS = 0.6
DST_BASE_TDS = 0.15
DST_DEFAULT_INTS = 0.8
POINTS_ALLOWED_SD = 9.5
YARDS_ALLOWED_SD = 55.0
UNLISTED_RUSH_YDS = 15.0  # rushing by players with no prop line (WRs, backups)

# Kickers: share of made FGs by distance, and misses per make (~85% accuracy).
FG_DISTANCE_MIX = {"fg_0_39": 0.55, "fg_40_49": 0.30, "fg_50_plus": 0.15}
FG_MISSES_PER_MAKE = 0.18


def _clamp(p: float, lo: float = 0.03, hi: float = 0.97) -> float:
    return min(hi, max(lo, p))


def _poisson_sf(lam: float, k: int) -> float:
    """P(X > k) for X ~ Poisson(lam)."""
    term = cdf = math.exp(-lam)
    for i in range(1, k + 1):
        term *= lam / i
        cdf += term
    return 1 - cdf


def _poisson_lambda(line: float, p_over: float) -> float:
    k = math.floor(line)
    lo, hi = 1e-4, 30.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _poisson_sf(mid, k) < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


class GameLines:
    """All player-prop markets fetched for one game."""

    def __init__(self, markets: Dict[str, List[dict]]):
        self.markets = markets
        self._samples: Dict[str, Dict[str, list]] = {}
        self.display: Dict[str, str] = {}

    def _market_samples(self, market: str) -> Dict[str, list]:
        if market in self._samples:
            return self._samples[market]
        out: Dict[str, list] = {}
        for book in self.markets.get(market, []):
            sides: Dict[Tuple[str, Optional[float]], Dict[str, float]] = {}
            for o in book["outcomes"]:
                desc = o.get("description")
                if not desc:
                    continue
                key = norm_name(desc)
                self.display.setdefault(key, desc)
                sides.setdefault((key, o.get("point")), {})[o["name"].lower()] = o["price"]
            for (key, point), s in sides.items():
                yes = s.get("yes") or s.get("over")
                no = s.get("no") or s.get("under")
                if not yes:
                    continue
                if no:
                    p = (1 / yes) / (1 / yes + 1 / no)
                else:
                    p = (1 / yes) / (TD_VIG if market == "player_anytime_td" else SINGLE_SIDE_VIG)
                out.setdefault(key, []).append((point, _clamp(p)))
        self._samples[market] = out
        return out

    def names(self, market: Optional[str] = None) -> Set[str]:
        markets = [market] if market else list(self.markets)
        return {n for m in markets for n in self._market_samples(m)}

    def resolve(self, name: str) -> Optional[str]:
        return match_name(name, self.names())

    def mean(self, market: str, key: Optional[str]) -> Optional[float]:
        samples = self._market_samples(market).get(key) if key else None
        if not samples:
            return None
        if market == "player_anytime_td":
            return -math.log(1 - median(p for _, p in samples))
        ests = []
        for point, p in samples:
            if point is None:
                continue
            if market in POISSON_MARKETS:
                ests.append(_poisson_lambda(point, p))
            else:
                frac, floor = NORMAL_MARKETS.get(market, (0.4, 1.0))
                sd = max(frac * point, floor)
                ests.append(max(0.0, point + sd * NormalDist().inv_cdf(p)))
        return sum(ests) / len(ests) if ests else None


@dataclass
class Projection:
    points: Optional[float]
    detail: str = ""
    notes: List[str] = field(default_factory=list)


def _tier_expectation(mean: float, sd: float, tiers: List[List[float]]) -> float:
    nd = NormalDist(mean, sd)
    total, prev = 0.0, 0.0
    for upper, pts in tiers:
        c = nd.cdf(upper + 0.5)
        total += (c - prev) * pts
        prev = c
    return total


def project_skill(name: str, pos: str, lines: GameLines, s: dict) -> Projection:
    key = lines.resolve(name)
    if key is None:
        return Projection(None, notes=["no prop lines posted"])
    stats = [  # (market, label, points per unit, fmt)
        ("player_pass_yds", "pass yds", s["pass_yd"], "{:.0f}"),
        ("player_pass_tds", "pass TD", s["pass_td"], "{:.2f}"),
        ("player_pass_interceptions", "INT", s["int"], "{:.2f}"),
        ("player_rush_yds", "rush yds", s["rush_yd"], "{:.0f}"),
        ("player_receptions", "rec", s["reception"], "{:.1f}"),
        ("player_reception_yds", "rec yds", s["rec_yd"], "{:.0f}"),
        ("player_anytime_td", "TD", s["td"], "{:.2f}"),
    ]
    expected = set(MARKETS_BY_POS[pos])
    pts, parts, missing = 0.0, [], []
    for market, label, per, fmt in stats:
        v = lines.mean(market, key)
        if v is None:
            if market in expected:
                missing.append(label)
            continue
        pts += v * per
        parts.append(f"{fmt.format(v)} {label}")
    notes = [f"no line: {', '.join(missing)}"] if missing else []
    return Projection(pts, ", ".join(parts), notes)


def project_kicker(name: str, lines: GameLines, team_implied: Optional[float], s: dict) -> Projection:
    key = lines.resolve(name)
    kp = lines.mean("player_kicking_points", key)
    fg = lines.mean("player_field_goals", key)
    notes = []
    if kp is None:
        if team_implied is None:
            return Projection(None, notes=["no kicker lines or game total"])
        notes.append("estimated from team implied total")
        fg = fg if fg is not None else 0.075 * team_implied
        pats = 0.95 * 0.105 * team_implied
    else:
        if fg is None:
            fg = 0.075 * team_implied if team_implied else kp * 0.27
        pats = max(0.0, kp - 3 * fg)
    per_fg = sum(share * s[k] for k, share in FG_DISTANCE_MIX.items())
    pts = fg * per_fg + fg * FG_MISSES_PER_MAKE * s["fg_miss"] + pats * s["pat"]
    return Projection(pts, f"{fg:.2f} FG, {pats:.2f} PAT", notes)


def project_dst(opp: str, lines: GameLines, opp_implied: Optional[float],
                team_index: Dict[str, Set[str]], s: dict) -> Projection:
    notes = []
    on_opp = lambda key: opp in team_index.get(key, ())  # noqa: E731

    qbs = [(lines.mean("player_pass_yds", k), k) for k in lines.names("player_pass_yds") if on_opp(k)]
    qbs = [q for q in qbs if q[0] is not None]
    qb_yds, qb_key = max(qbs) if qbs else (None, None)

    ints = lines.mean("player_pass_interceptions", qb_key)
    if ints is None:
        ints = DST_DEFAULT_INTS
        notes.append("no opp QB INT line")

    if opp_implied is None:
        return Projection(None, notes=["no game total/spread posted"])

    rush = [lines.mean("player_rush_yds", k) for k in lines.names("player_rush_yds") if on_opp(k)]
    rush = [r for r in rush if r is not None]
    if qb_yds is not None and rush:
        yards = qb_yds + sum(rush) + UNLISTED_RUSH_YDS
    else:
        yards = 200 + 6.5 * opp_implied
        notes.append("yards allowed estimated from implied total")

    pa_pts = _tier_expectation(opp_implied, POINTS_ALLOWED_SD, s["dst_points_allowed"])
    ya_pts = _tier_expectation(yards, YARDS_ALLOWED_SD, s["dst_yards_allowed"])
    base = (DST_BASE_SACKS * s["dst_sack"] + DST_BASE_FUMBLE_RECS * s["dst_fumble_rec"]
            + DST_BASE_TDS * s["dst_td"])
    pts = pa_pts + ya_pts + ints * s["dst_int"] + base
    qb_name = lines.display.get(qb_key, "?") if qb_key else "?"
    detail = (f"opp {opp_implied:.1f} pts ({pa_pts:+.1f}), {yards:.0f} yds ({ya_pts:+.1f}), "
              f"{ints:.2f} INT from {qb_name}")
    return Projection(pts, detail, notes)


def implied_totals(game_lines: List[dict]) -> Dict[str, float]:
    """Full team name -> implied points, from consensus spread and total."""
    out: Dict[str, float] = {}
    for g in game_lines:
        totals, spreads = [], {}
        for book in g.get("bookmakers", []):
            for m in book["markets"]:
                for o in m["outcomes"]:
                    if m["key"] == "totals" and o["name"] == "Over":
                        totals.append(o["point"])
                    elif m["key"] == "spreads":
                        spreads.setdefault(o["name"], []).append(o["point"])
        if not totals or not spreads:
            continue
        total = median(totals)
        for team, pts in spreads.items():
            out[team] = (total - median(pts)) / 2
    return out
