from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from utils import RAW_DIR, stable_id, utc_now_iso, write_json


BASE_URL = "https://github.com/trending"


def _parse_count(text: str) -> int:
    text = (text or "").strip().replace(",", "")
    if not text:
        return 0
    if text.lower().endswith("k"):
        return int(float(text[:-1]) * 1000)
    try:
        return int(text)
    except ValueError:
        return 0


def _collect_language(language: str, since: str, weight: float, category: str, region: str, priority: float, quality: float) -> dict[str, Any]:
    url = f"{BASE_URL}/{language}" if language else BASE_URL
    response = requests.get(url, params={"since": since}, timeout=20, headers={"User-Agent": "daily-tech-news/0.1"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    for article in soup.select("article.Box-row"):
        link = article.select_one("h2 a")
        if not link:
            continue
        repo_path = " ".join(link.get_text(" ", strip=True).split()).replace(" / ", "/")
        repo_url = "https://github.com" + link.get("href", "").strip()
        description_el = article.select_one("p")
        desc = description_el.get_text(" ", strip=True) if description_el else ""
        meta_links = article.select("a.Link--muted")
        stars = _parse_count(meta_links[0].get_text(strip=True)) if meta_links else 0
        forks = _parse_count(meta_links[1].get_text(strip=True)) if len(meta_links) > 1 else 0
        stars_today_el = article.find(string=lambda text: text and "stars today" in text)
        stars_today = _parse_count(str(stars_today_el).replace("stars today", "")) if stars_today_el else 0
        items.append(
            {
                "id": stable_id("GitHub Trending", repo_url, since),
                "title": repo_path,
                "url": repo_url,
                "summary": desc,
                "published_at": None,
                "collected_at": utc_now_iso(),
                "source": f"GitHub Trending {language or 'all'}",
                "source_type": "github_trending",
                "source_category": category,
                "source_region": region,
                "source_weight": weight,
                "source_priority": priority,
                "source_quality": quality,
                "metrics": {
                    "stars": stars,
                    "forks": forks,
                    "stars_today": stars_today,
                    "language": language or "all",
                },
                "raw": {},
            }
        )
    return {
        "source": f"GitHub Trending {language or 'all'}",
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "count": len(items),
        "items": items,
    }


def collect_github_trending(config: dict[str, Any], date_str: str) -> list[dict[str, Any]]:
    gh_config = config.get("github_trending", {})
    if not gh_config.get("enabled", True):
        return []

    since = gh_config.get("since", "daily")
    weight = float(gh_config.get("weight", 0.85))
    category = gh_config.get("category", "developer")
    region = gh_config.get("region", "international")
    priority = float(gh_config.get("priority", weight))
    quality = float(gh_config.get("quality_score", 0.0))
    results = []
    all_items = []
    for language in gh_config.get("languages", [""]):
        try:
            result = _collect_language(language, since, weight, category, region, priority, quality)
        except Exception as exc:
            result = {
                "source": f"GitHub Trending {language or 'all'}",
                "url": f"{BASE_URL}/{language}" if language else BASE_URL,
                "fetched_at": utc_now_iso(),
                "status": "error",
                "error": str(exc),
                "items": [],
            }
        results.append(result)
        all_items.extend(result["items"])
    write_json(RAW_DIR / date_str / "github-trending.json", results)
    return all_items
