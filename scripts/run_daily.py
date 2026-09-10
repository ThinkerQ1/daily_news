from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from build_site import build_site
from collect_github_trending import collect_github_trending
from collect_hn import collect_hn
from collect_rss import collect_rss
from cluster_topics import cluster_topics
from dedupe import dedupe_items
from filter_recent import filter_recent_items
from generate_recommendations import generate_recommendations
from generate_report import generate_report
from generate_topics import generate_topics
from normalize import normalize_items
from send_telegram import send_report
from utils import LOGS_DIR, PROJECT_ROOT, ensure_dirs, load_sources, stable_id, today_string, utc_now_iso, write_json


def _append_runtime_log(message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with (LOGS_DIR / "daily.log").open("a", encoding="utf-8") as fh:
        fh.write(message + "\n")


def _sspai_source_config(config: dict) -> dict:
    for source in config.get("rss_sources", []):
        if source.get("name") == "少数派":
            return source
    return {}


def load_openclaw_items(date_str: str) -> list[dict]:
    path = PROJECT_ROOT / "data" / "openclaw" / f"sspai_{date_str}.json"
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        items = payload.get("items", [])
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    except (OSError, json.JSONDecodeError, AttributeError):
        return []


def _openclaw_sspai_item(raw_item: dict, source_config: dict) -> dict:
    title = raw_item.get("title", "")
    url = raw_item.get("url", "")
    return {
        "id": stable_id("少数派", url, title),
        "title": title,
        "url": url,
        "summary": raw_item.get("summary", ""),
        "published_at": raw_item.get("published_at") or "",
        "collected_at": utc_now_iso(),
        "source": "少数派",
        "source_name": "少数派",
        "source_type": "openclaw",
        "source_category": source_config.get("category", "china_media"),
        "source_region": source_config.get("region", "china"),
        "source_weight": float(source_config.get("weight", 1.0)),
        "source_priority": float(source_config.get("priority", source_config.get("weight", 1.0))),
        "source_quality": float(source_config.get("quality_score", 0.0)),
        "tags": raw_item.get("tags", []),
        "metrics": {
            "confidence": raw_item.get("confidence", 0.0),
        },
        "raw": {
            "collector": "openclaw",
            "item": raw_item,
        },
    }


def collect_sspai_items(config: dict, date_str: str) -> list[dict]:
    source_config = _sspai_source_config(config)
    return [_openclaw_sspai_item(item, source_config) for item in load_openclaw_items(date_str)]


def run(date_str: str | None = None, force: bool = False, window_days: int | None = None) -> tuple[str, str]:
    ensure_dirs()
    config = load_sources()
    date_str = date_str or today_string()
    effective_window_days = int(window_days or config.get("settings", {}).get("news_window_days", 3))

    all_items = []
    rss_items = collect_rss(config, date_str)
    all_items.extend(rss_items)
    all_items.extend(collect_sspai_items(config, date_str))
    all_items.extend(collect_hn(config, date_str))
    all_items.extend(collect_github_trending(config, date_str))

    write_json(Path("data/processed") / f"{date_str}-collected.json", all_items)
    normalized = normalize_items(all_items, date_str)
    deduped = dedupe_items(normalized, date_str)
    recent_items, time_audit = filter_recent_items(deduped, date_str, effective_window_days)
    clusters, cluster_audit = cluster_topics(recent_items, config, date_str)
    write_json(Path("data/processed") / f"{date_str}-ranked.json", clusters)
    report_path = generate_report(clusters, config, date_str, time_audit, cluster_audit)
    recommendation_path = generate_recommendations(clusters, config, date_str)
    return report_path, recommendation_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and rank daily China-first tech news.")
    parser.add_argument("--date", help="Report date, defaults to today in local timezone.")
    parser.add_argument("--force", action="store_true", help="Regenerate today's report even if output files already exist.")
    parser.add_argument("--window-days", type=int, help="Only keep news published or collected within this many days.")
    args = parser.parse_args()
    report_path, recommendation_path = run(args.date, force=args.force, window_days=args.window_days)
    print(f"Generated report: {report_path}")
    print(f"Generated topic radar: {recommendation_path}")
    try:
        topics_path = generate_topics(args.date, Path(report_path))
    except Exception as exc:
        print(f"Topics generation failed: {exc}", file=sys.stderr)
        _append_runtime_log(f"Topics generation failed: {exc}")
    else:
        message = f"Topics generated: {topics_path}"
        print(message)
        _append_runtime_log(message)
    try:
        site_index = build_site()
    except Exception as exc:
        print(f"Site generation failed: {exc}", file=sys.stderr)
    else:
        print(f"Site generated: {site_index}")
    try:
        sent_path = send_report(Path(report_path))
    except Exception as exc:
        print(f"Telegram send failed: {exc}", file=sys.stderr)
        _append_runtime_log(f"Telegram send failed: {exc}")
    else:
        print(f"Telegram report sent: {sent_path.name}")
        _append_runtime_log(f"Telegram report sent: {sent_path.name}")
    try:
        sent_path = send_report(Path(recommendation_path))
    except Exception as exc:
        print(f"Telegram send failed: {exc}", file=sys.stderr)
        _append_runtime_log(f"Telegram send failed: {exc}")
    else:
        print(f"Telegram report sent: {sent_path.name}")
        _append_runtime_log(f"Telegram report sent: {sent_path.name}")
    try:
        site_index = build_site()
    except Exception as exc:
        print(f"Site refresh after Telegram failed: {exc}", file=sys.stderr)
    else:
        print(f"Site refreshed: {site_index}")


if __name__ == "__main__":
    main()
