from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Tuple


def get_json(url: str, params: Dict[str, str] | None = None, timeout: int = 30) -> Tuple[Any, Dict[str, str]]:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ff-lineup-generator"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        # Never echo the URL: it contains the API key.
        raise RuntimeError(f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}: {body}") from None
