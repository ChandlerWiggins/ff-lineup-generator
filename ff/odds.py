"""The Odds API client with an on-disk cache so re-runs don't spend credits.

Credit cost: event odds = (# markets returned) x (# regions); listing events is free.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Iterable, List

from .http import get_json

BASE = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl"
REGION = "us"


class OddsClient:
    def __init__(self, api_key: str, cache_dir: Path, ttl_hours: float, refresh: bool):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.ttl = ttl_hours * 3600
        self.refresh = refresh
        self.credits_used = 0
        self.credits_remaining = None

    def _get(self, path: str, **params):
        data, headers = get_json(f"{BASE}{path}", {"apiKey": self.api_key, **params})
        self.credits_used += int(headers.get("x-requests-last", 0) or 0)
        if "x-requests-remaining" in headers:
            self.credits_remaining = headers["x-requests-remaining"]
        return data

    def _cache_read(self, path: Path):
        if self.refresh or not path.exists():
            return None
        blob = json.loads(path.read_text())
        if time.time() - blob["fetched_at"] > self.ttl:
            return None
        return blob["data"]

    def _cache_write(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched_at": time.time(), "data": data}))

    def events(self) -> List[dict]:
        """Upcoming (not yet started) games. Free."""
        return self._get("/events")

    def game_lines(self) -> List[dict]:
        """Spreads and totals for every game: 2 credits for the whole slate."""
        path = self.cache_dir / "game_lines.json"
        data = self._cache_read(path)
        if data is None:
            data = self._get("/odds", regions=REGION, markets="spreads,totals", oddsFormat="decimal")
            self._cache_write(path, data)
        return data

    def event_markets(self, event_id: str, markets: Iterable[str]) -> Dict[str, List[dict]]:
        """Return {market_key: [{"book": key, "outcomes": [...]}, ...]} for one game.

        Each market is cached separately so only missing markets are requested.
        Markets with no lines posted yet are not cached (they cost nothing to re-ask).
        """
        out: Dict[str, List[dict]] = {}
        missing = []
        for m in sorted(set(markets)):
            cached = self._cache_read(self.cache_dir / event_id / f"{m}.json")
            if cached is None:
                missing.append(m)
            else:
                out[m] = cached
        if missing:
            data = self._get(f"/events/{event_id}/odds", regions=REGION,
                             markets=",".join(missing), oddsFormat="decimal")
            fetched: Dict[str, List[dict]] = {}
            for book in data.get("bookmakers", []):
                for mk in book.get("markets", []):
                    fetched.setdefault(mk["key"], []).append(
                        {"book": book["key"], "outcomes": mk["outcomes"]})
            for m, books in fetched.items():
                self._cache_write(self.cache_dir / event_id / f"{m}.json", books)
            out.update(fetched)
        return out
