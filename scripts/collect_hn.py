from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from utils import RAW_DIR, stable_id, utc_now_iso, write_json


HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"


def collect_hn(config: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    hn_config = config.get("hacker_news", {})
    if not hn_config.get("enabled", True):
        return []

    params = {
        "tags": ",".join(hn_config.get("tags", ["story"])),
        "hitsPerPage": 100,
        "numericFilters": f"points>={int(hn_config.get('min_points', 50))}",
    }
    result: dict[str, Any]
    try:
        response = requests.get(HN_SEARCH_URL, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        items = []
        for hit in payload.get("hits", []):
            title = hit.get("title") or hit.get("story_title") or ""
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            if not title or not url:
                continue
            items.append(
                {
                    "id": stable_id("Hacker News", str(hit.get("objectID")), title),
                    "title": title.strip(),
                    "url": url,
                    "summary": "",
                    "published_at": hit.get("created_at"),
                    "collected_at": utc_now_iso(),
                    "source": "Hacker News",
                    "source_type": "hacker_news",
                    "source_category": hn_config.get("category", "developer"),
                    "source_region": hn_config.get("region", "international"),
                    "source_weight": float(hn_config.get("weight", 0.9)),
                    "source_priority": float(hn_config.get("priority", hn_config.get("weight", 0.9))),
                    "source_quality": float(hn_config.get("quality_score", 0.0)),
                    "metrics": {
                        "points": hit.get("points") or 0,
                        "comments": hit.get("num_comments") or 0,
                        "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    },
                    "raw": hit,
                }
            )
        result = {
            "source": "Hacker News",
            "url": HN_SEARCH_URL,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
            "count": len(items),
            "items": items,
        }
    except Exception as exc:
        result = {
            "source": "Hacker News",
            "url": HN_SEARCH_URL,
            "fetched_at": utc_now_iso(),
            "status": "error",
            "error": str(exc),
            "items": [],
        }
    write_json(RAW_DIR / date_str / "hacker-news.json", result)
    return result["items"]
