from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from utils import REPORTS_DIR


def _main_item(topic: dict[str, Any]) -> dict[str, Any]:
    return topic.get("main_item", topic)


def _is_china(topic: dict[str, Any]) -> bool:
    item = _main_item(topic)
    category = item.get("source_category", "")
    return topic.get("region") == "china" or item.get("source_region") == "china" or category.endswith("_china") or category.startswith("china_")


def _published_text(topic: dict[str, Any]) -> str:
    item = _main_item(topic)
    value = topic.get("latest_seen_at") or item.get("published_at") or item.get("collected_at") or ""
    return value.replace("T", " ")[:16] if value else "unknown"


def _reason(topic: dict[str, Any]) -> str:
    reasons = []
    if topic.get("why_important"):
        return topic["why_important"]
    if topic.get("matched_keywords"):
        reasons.append("命中关键词：" + "、".join(topic["matched_keywords"][:5]))
    if topic.get("source_count", 1) > 1:
        reasons.append("多源交叉验证")
    if _is_china(topic):
        reasons.append("国内科技主线相关")
    if _main_item(topic).get("source_category") == "developer":
        reasons.append("开发者/开源趋势")
    return "；".join(reasons) or "来源质量、时效和热度综合靠前"


def _line_for_item(index: int, topic: dict[str, Any], config: dict[str, Any]) -> str:
    item = _main_item(topic)
    sources = ", ".join(topic.get("sources", item.get("duplicate_sources", [item.get("source", "unknown")])))
    related = topic.get("related_items", [])
    keywords = ", ".join(topic.get("matched_keywords", [])[:6])
    summary = topic.get("summary") or item.get("summary") or ""
    if len(summary) > 220:
        summary = summary[:217].rstrip() + "..."
    title = topic.get("topic_title", item.get("title", "untitled"))
    main_url = item.get("url", "")
    max_related = int(config.get("settings", {}).get("max_related_links_per_topic", 4))
    related_links = []
    seen_urls = {main_url}
    for related_item in related:
        if related_item.get("url") in seen_urls:
            continue
        related_links.append(related_item)
        seen_urls.add(related_item.get("url"))
        if len(related_links) >= max_related:
            break
    meta = (
        f"热度：{topic.get('source_count', 1)} 个来源报道 | 来源：{sources} | "
        f"分类：{', '.join(topic.get('source_categories', [item.get('source_category', 'unknown')]))} | "
        f"时间：{_published_text(topic)} | heat_score {topic.get('heat_score')}"
    )
    if keywords:
        meta += f" | keywords: {keywords}"
    lines = [f"{index}. {title}", f"   - {meta}"]
    lines.append(f"   - 主要来源：{item.get('source', 'unknown')} | [主链接]({main_url})")
    if related_links:
        link_text = "；".join(f"{row.get('source', 'unknown')}：[链接]({row.get('url')})" for row in related_links)
        lines.append(f"   - 相关链接：{link_text}")
    else:
        lines.append("   - 相关链接：暂无多源链接")
    lines.append(f"   - 摘要：{summary or '暂无摘要'}")
    lines.append(f"   - 为什么重要：{_reason(topic)}")
    return "\n".join(lines)


def select_report_items(items: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    top_n = int(config.get("settings", {}).get("report_top_n", 60))
    china_ratio = float(config.get("settings", {}).get("china_report_ratio", 0.75))
    china_target = round(top_n * china_ratio)
    china_items = [item for item in items if _is_china(item)]
    international_items = [item for item in items if not _is_china(item)]

    selected = china_items[:china_target]
    selected.extend(international_items[: max(0, top_n - len(selected))])
    if len(selected) < top_n:
        selected.extend(item for item in china_items[china_target:] if item not in selected)
    return selected[:top_n]


def _matches_any(item: dict[str, Any], terms: list[str]) -> bool:
    main = _main_item(item)
    text = f"{item.get('topic_title', main.get('title', ''))} {item.get('summary', '')} {main.get('summary', '')}".lower()
    return any(term.lower() in text for term in terms)


def _section_items(selected: list[dict[str, Any]], used: set[str], predicate: Any, limit: int) -> list[dict[str, Any]]:
    picked = []
    for item in selected:
        if item["id"] in used or not predicate(item):
            continue
        picked.append(item)
        used.add(item["id"])
        if len(picked) >= limit:
            break
    return picked


def _append_section(lines: list[str], title: str, items: list[dict[str, Any]]) -> None:
    lines.extend(["", f"## {title}", ""])
    if items:
        lines.extend(_line_for_item(index, item, _append_section.config) for index, item in enumerate(items, 1))
    else:
        lines.append("今日没有足够高质量条目。")


def generate_report(
    items: list[dict[str, Any]],
    config: dict[str, Any],
    date_str: str,
    time_audit: dict[str, Any] | None = None,
    cluster_audit: dict[str, Any] | None = None,
) -> str:
    _append_section.config = config
    selected = select_report_items(items, config)
    source_counts = Counter(_main_item(item).get("source_type", "unknown") for item in selected)
    category_counts = Counter(category for item in selected for category in item.get("source_categories", [_main_item(item).get("source_category", "unknown")]))
    region_counts = Counter("china" if _is_china(item) else "international" for item in selected)
    china_count = region_counts.get("china", 0)
    international_count = region_counts.get("international", 0)
    china_ratio = china_count / len(selected) if selected else 0

    lines = [
        f"# 中国科技新闻日报 - {date_str}",
        "",
        f"Generated at: {datetime.now().astimezone().isoformat()}",
        f"定位：以内地主流科技新闻为主，国际科技新闻与开发者趋势为辅。",
        f"Total topic clusters: {len(items)}. Report topics: {len(selected)}.",
        "",
        "## Snapshot",
        "",
        f"- Time window: last {time_audit.get('time_window_days', 3) if time_audit else config.get('settings', {}).get('news_window_days', 3)} days",
        f"- Filtered old items: {time_audit.get('filtered_old_items', 0) if time_audit else 0}",
        f"- Discarded invalid/missing time items: {(time_audit.get('filtered_invalid_time_items', 0) + time_audit.get('filtered_missing_time_items', 0)) if time_audit else 0}",
        f"- Final selected items: {len(selected)}",
        f"- Topic clusters: {cluster_audit.get('topic_clusters', len(items)) if cluster_audit else len(items)}",
        f"- Multi-source hot topics: {cluster_audit.get('multi_source_hot_topics', 0) if cluster_audit else 0}",
        f"- Highest source_count: {cluster_audit.get('highest_source_count', 0) if cluster_audit else 0}",
        f"- China / International ratio: 国内 {china_count} 条（{china_ratio:.1%}），国际 {international_count} 条",
        "- By source type: " + (", ".join(f"{k}: {v}" for k, v in source_counts.most_common()) or "none"),
        "- By category: " + (", ".join(f"{k}: {v}" for k, v in category_counts.most_common()) or "none"),
    ]
    if selected:
        used: set[str] = set()
        focus = selected[:6]
        used.update(item["id"] for item in focus)
        _append_section(lines, "今日重点", focus)
        _append_section(lines, "中国科技热点", _section_items(selected, used, _is_china, 12))
        _append_section(
            lines,
            "AI 与大模型",
            _section_items(selected, used, lambda item: _matches_any(item, ["AI", "大模型", "智能体", "Agent", "OpenAI", "Anthropic", "机器学习"]), 10),
        )
        _append_section(
            lines,
            "智能车 / 芯片 / 硬件",
            _section_items(selected, used, lambda item: _matches_any(item, ["智能车", "自动驾驶", "芯片", "半导体", "硬件", "手机", "机器人", "算力"]), 10),
        )
        _append_section(
            lines,
            "公司与投融资",
            _section_items(selected, used, lambda item: _matches_any(item, ["融资", "投融资", "创业", "公司", "IPO", "阿里", "腾讯", "字节", "百度", "小米"]), 8),
        )
        _append_section(lines, "国际科技观察", _section_items(selected, used, lambda item: not _is_china(item) and _main_item(item).get("source_category") != "developer", 10))
        _append_section(lines, "开发者与开源趋势", _section_items(selected, used, lambda item: _main_item(item).get("source_category") == "developer", 8))
        _append_section(lines, "值得继续跟踪", _section_items(selected, used, lambda item: True, 6))
    else:
        lines.extend(["", "## 今日重点", ""])
        lines.append("No stories collected. Check raw collector logs under `data/raw`.")

    path = REPORTS_DIR / f"daily-tech-news-{date_str}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)
