from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser

from utils import LOGS_DIR, PROCESSED_DIR, write_json


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _log(message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with (LOGS_DIR / "daily.log").open("a", encoding="utf-8") as fh:
        fh.write(message + "\n")


def _parse_news_time(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = parser.parse(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SHANGHAI_TZ)
    return dt.astimezone(SHANGHAI_TZ)


def filter_recent_items(
    items: list[dict[str, Any]],
    date_str: str,
    window_days: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    now = datetime.now(SHANGHAI_TZ)
    cutoff = now - timedelta(days=window_days)
    kept: list[dict[str, Any]] = []
    filtered_old = 0
    filtered_invalid = 0
    filtered_missing_time = 0

    for item in items:
        title = item.get("title", "untitled")
        published_at = item.get("published_at")
        collected_at = item.get("collected_at")
        time_value = published_at or collected_at

        if not time_value:
            filtered_missing_time += 1
            _log(f"Skip old item: {title} | published_at={published_at} | collected_at={collected_at}")
            continue

        try:
            news_time = _parse_news_time(time_value)
        except (ValueError, TypeError, OverflowError) as exc:
            filtered_invalid += 1
            _log(
                "Warning: skip item with invalid time: "
                f"{title} | published_at={published_at} | collected_at={collected_at} | error={exc}"
            )
            continue

        if news_time is None or news_time < cutoff:
            filtered_old += 1
            _log(f"Skip old item: {title} | published_at={published_at} | collected_at={collected_at}")
            continue

        item["news_time"] = news_time.isoformat()
        kept.append(item)

    audit = {
        "time_window_days": window_days,
        "window_started_at": cutoff.isoformat(),
        "window_ended_at": now.isoformat(),
        "input_items": len(items),
        "kept_items": len(kept),
        "filtered_old_items": filtered_old,
        "filtered_invalid_time_items": filtered_invalid,
        "filtered_missing_time_items": filtered_missing_time,
        "filtered_total": filtered_old + filtered_invalid + filtered_missing_time,
    }
    write_json(PROCESSED_DIR / f"{date_str}-recent-filter-audit.json", audit)
    write_json(PROCESSED_DIR / f"{date_str}-recent.json", kept)
    return kept, audit
