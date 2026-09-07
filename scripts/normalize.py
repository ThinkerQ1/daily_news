from __future__ import annotations

import re
from datetime import timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from dateutil import parser

from utils import PROCESSED_DIR, stable_id, write_json


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


def _canonical_url(url: str) -> str:
    parsed = urlparse(url or "")
    if parsed.netloc == "news.google.com" and parsed.path.startswith("/rss/articles/"):
        # Google News redirect URLs are still useful, but keep them stable.
        return url.split("?")[0]
    query = parse_qs(parsed.query, keep_blank_values=True)
    clean_query = [(k, v) for k, values in query.items() for v in values if k not in TRACKING_PARAMS]
    query_text = "&".join(f"{k}={v}" for k, v in sorted(clean_query))
    return parsed._replace(query=query_text, fragment="").geturl()


def _parse_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def _clean_text(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unquote(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_items(items: list[dict[str, Any]], date_str: str) -> list[dict[str, Any]]:
    normalized = []
    for item in items:
        title = _clean_text(item.get("title"))
        url = _canonical_url(item.get("url", ""))
        if not title or not url:
            continue
        normalized.append(
            {
                "id": stable_id(url, title),
                "title": title,
                "url": url,
                "summary": _clean_text(item.get("summary")),
                "published_at": _parse_datetime(item.get("published_at")),
                "collected_at": _parse_datetime(item.get("collected_at")),
                "source": item.get("source", "unknown"),
                "source_type": item.get("source_type", "unknown"),
                "source_category": item.get("source_category", "unknown"),
                "source_region": item.get("source_region", "international"),
                "source_weight": float(item.get("source_weight", 1.0)),
                "source_priority": float(item.get("source_priority", item.get("source_weight", 1.0))),
                "source_quality": float(item.get("source_quality", 0.0)),
                "metrics": item.get("metrics", {}),
                "duplicate_sources": [item.get("source", "unknown")],
                "score": 0.0,
            }
        )
    write_json(PROCESSED_DIR / f"{date_str}-normalized.json", normalized)
    return normalized
