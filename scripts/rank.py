from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from dateutil import parser

from utils import PROCESSED_DIR, write_json


def _age_hours(value: str | None) -> float:
    if not value:
        return 48.0
    try:
        dt = parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600)
    except (ValueError, TypeError, OverflowError):
        return 48.0


def _keyword_score(text: str, keywords: dict[str, list[str]], region: str) -> tuple[float, list[str]]:
    lower = text.lower()
    matched = []
    score = 0.0
    high_keys = list(keywords.get("high", []))
    medium_keys = list(keywords.get("medium", []))
    if region == "china":
        high_keys.extend(keywords.get("china_high", []))
        medium_keys.extend(keywords.get("china_medium", []))
        medium_keys.extend(keywords.get("international_high", []))
    else:
        high_keys.extend(keywords.get("international_high", []))
        medium_keys.extend(keywords.get("international_medium", []))
        medium_keys.extend(keywords.get("china_high", []))
    for word in high_keys:
        if word.lower() in lower:
            score += 2.2
            matched.append(word)
    for word in medium_keys:
        if word.lower() in lower:
            score += 1.0
            matched.append(word)
    for word in keywords.get("exclude", []):
        if word.lower() in lower:
            score -= 3.0
            matched.append(f"exclude:{word}")
    return score, matched


def _metrics_score(item: dict[str, Any]) -> float:
    metrics = item.get("metrics", {})
    points = float(metrics.get("points", 0) or 0)
    comments = float(metrics.get("comments", 0) or 0)
    stars_today = float(metrics.get("stars_today", 0) or 0)
    stars = float(metrics.get("stars", 0) or 0)
    return math.log1p(points) * 0.8 + math.log1p(comments) * 0.4 + math.log1p(stars_today) * 1.0 + math.log1p(stars) * 0.25


def rank_items(items: list[dict[str, Any]], config: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    keywords = config.get("keywords", {})
    half_life = float(config.get("settings", {}).get("freshness_half_life_hours", 36))
    ranked = []
    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        region = item.get("source_region", "international")
        keyword_score, matched_keywords = _keyword_score(text, keywords, region)
        freshness = math.exp(-_age_hours(item.get("published_at") or item.get("collected_at")) / half_life)
        multi_source_bonus = min(3.0, max(0, len(item.get("duplicate_sources", [])) - 1) * 1.25)
        priority = float(item.get("source_priority", item.get("source_weight", 1.0)))
        region_bonus = 1.2 if region == "china" else 0.0
        score = (
            item.get("source_weight", 1.0) * 4.0
            + priority * 1.5
            + region_bonus
            + keyword_score
            + freshness * 3.0
            + multi_source_bonus
            + _metrics_score(item)
        )
        item["matched_keywords"] = matched_keywords
        item["score"] = round(score, 3)
        item["score_parts"] = {
            "source_weight": item.get("source_weight", 1.0),
            "source_priority": priority,
            "region_bonus": region_bonus,
            "keyword_score": round(keyword_score, 3),
            "freshness": round(freshness, 3),
            "multi_source_bonus": round(multi_source_bonus, 3),
            "metrics_score": round(_metrics_score(item), 3),
        }
        ranked.append(item)
    ranked.sort(key=lambda row: row["score"], reverse=True)
    write_json(PROCESSED_DIR / f"{date_str}-ranked.json", ranked)
    return ranked
