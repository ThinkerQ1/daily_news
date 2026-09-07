from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import requests

from utils import RAW_DIR, google_news_rss_url, slugify, stable_id, utc_now_iso, write_json


REQUEST_TIMEOUT_SECONDS = 15


def _entry_datetime(entry: Any) -> str | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            continue
    return None


def _summary(entry: Any) -> str:
    for key in ("summary", "description"):
        value = entry.get(key)
        if value:
            return value
    return ""


def _collect_feed(source: dict[str, Any], url: str, date_str: str, source_type: str, limit: int) -> dict[str, Any]:
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": "daily-tech-news/0.1"})
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    entries = []
    for entry in feed.entries[:limit]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        entries.append(
            {
                "id": stable_id(source["name"], link, title),
                "title": title,
                "url": link,
                "summary": _summary(entry),
                "published_at": _entry_datetime(entry),
                "collected_at": utc_now_iso(),
                "source": source["name"],
                "source_type": source_type,
                "source_category": source.get("category", source_type),
                "source_region": source.get("region", "international"),
                "source_weight": float(source.get("weight", 1.0)),
                "source_priority": float(source.get("priority", source.get("weight", 1.0))),
                "source_quality": float(source.get("quality_score", 0.0)),
                "raw": {
                    "feed_title": getattr(feed.feed, "title", ""),
                    "authors": entry.get("authors", []),
                    "tags": entry.get("tags", []),
                },
            }
        )
    return {
        "source": source["name"],
        "url": url,
        "source_type": source_type,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "count": len(entries),
        "items": entries,
        "bozo": bool(getattr(feed, "bozo", False)),
    }


def _skipped_feed(source: dict[str, Any], url: str | None, source_type: str) -> dict[str, Any]:
    return {
        "source": source.get("name", "unknown"),
        "url": url,
        "source_type": source_type,
        "source_category": source.get("category", source_type),
        "source_region": source.get("region", "international"),
        "fetched_at": utc_now_iso(),
        "status": "skipped",
        "reason": source.get("disabled_reason", "disabled"),
        "count": 0,
        "items": [],
    }


def collect_rss(config: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    results = []
    limit = int(config.get("settings", {}).get("max_items_per_source", 30))
    for source in config.get("rss_sources", []):
        source_type = source.get("source_type", "rss")
        if not source.get("enabled", True):
            result = _skipped_feed(source, source.get("url"), source_type)
            write_json(RAW_DIR / date_str / f"rss-{slugify(result['source'])}.json", result)
            continue
        try:
            result = _collect_feed(source, source["url"], date_str, source_type, limit)
        except Exception as exc:
            result = {
                "source": source.get("name", "unknown"),
                "url": source.get("url"),
                "source_type": source_type,
                "source_category": source.get("category", source_type),
                "source_region": source.get("region", "international"),
                "fetched_at": utc_now_iso(),
                "status": "error",
                "error": str(exc),
                "items": [],
            }
        write_json(RAW_DIR / date_str / f"rss-{slugify(result['source'])}.json", result)
        results.extend(result["items"])

    for source in config.get("google_news_rss", []):
        url = google_news_rss_url(source["query"])
        google_source = {
            "name": source["name"],
            "category": source.get("category", "google_news"),
            "region": source.get("region", "international"),
            "priority": source.get("priority", source.get("weight", 0.8)),
            "quality_score": source.get("quality_score", 0.0),
            "weight": source.get("weight", 0.8),
        }
        source_type = source.get("source_type", "google_news_rss")
        if not source.get("enabled", True):
            result = _skipped_feed(google_source, url, source_type)
            write_json(RAW_DIR / date_str / f"google-news-{slugify(result['source'])}.json", result)
            continue
        try:
            result = _collect_feed(google_source, url, date_str, source_type, limit)
        except Exception as exc:
            result = {
                "source": google_source["name"],
                "url": url,
                "source_type": source_type,
                "source_category": google_source["category"],
                "source_region": google_source["region"],
                "fetched_at": utc_now_iso(),
                "status": "error",
                "error": str(exc),
                "items": [],
            }
        write_json(RAW_DIR / date_str / f"google-news-{slugify(result['source'])}.json", result)
        results.extend(result["items"])
    return results
