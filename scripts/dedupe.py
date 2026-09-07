from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from utils import PROCESSED_DIR, normalize_title, write_json


EVENT_TERMS = {
    "AI",
    "大模型",
    "智能体",
    "Agent",
    "芯片",
    "半导体",
    "算力",
    "华为",
    "阿里",
    "腾讯",
    "字节跳动",
    "百度",
    "小米",
    "京东",
    "美团",
    "拼多多",
    "比亚迪",
    "蔚来",
    "小鹏",
    "理想",
    "自动驾驶",
    "机器人",
    "鸿蒙",
    "OpenAI",
    "Google",
    "Anthropic",
    "NVIDIA",
}


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    shorter = min(len(a), len(b))
    if shorter < 18:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.9


def _event_overlap(a: str, b: str) -> bool:
    a_terms = {term.lower() for term in EVENT_TERMS if term.lower() in a}
    b_terms = {term.lower() for term in EVENT_TERMS if term.lower() in b}
    if not a_terms or not b_terms:
        return False
    return len(a_terms & b_terms) >= 2


def _better_item(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_quality = (
        float(left.get("source_priority", left.get("source_weight", 1.0))),
        bool(left.get("summary")),
        len(left.get("summary", "")),
    )
    right_quality = (
        float(right.get("source_priority", right.get("source_weight", 1.0))),
        bool(right.get("summary")),
        len(right.get("summary", "")),
    )
    return left if left_quality >= right_quality else right


def _merge_items(existing: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    winner = _better_item(existing, item)
    loser = item if winner is existing else existing
    winner["duplicate_sources"] = sorted(set(existing["duplicate_sources"] + item["duplicate_sources"]))
    winner["source_weight"] = max(existing["source_weight"], item["source_weight"])
    winner["source_priority"] = max(
        float(existing.get("source_priority", existing["source_weight"])),
        float(item.get("source_priority", item["source_weight"])),
    )
    if not winner.get("summary") and loser.get("summary"):
        winner["summary"] = loser["summary"]
    return winner


def dedupe_items(items: list[dict[str, Any]], date_str: str) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for item in items:
        existing = by_url.get(item["url"])
        if existing:
            by_url[item["url"]] = _merge_items(existing, item)
            continue
        by_url[item["url"]] = item

    deduped: list[dict[str, Any]] = []
    title_index: list[tuple[str, dict[str, Any]]] = []
    for item in by_url.values():
        title_key = normalize_title(item["title"])
        match = None
        match_index = None
        for index, (existing_key, existing) in enumerate(title_index):
            title_ratio = SequenceMatcher(None, title_key, existing_key).ratio()
            keyword_duplicate = title_ratio >= 0.72 and _event_overlap(title_key, existing_key)
            if _similar(title_key, existing_key) or keyword_duplicate:
                match = existing
                match_index = index
                break
        if match:
            merged = _merge_items(match, item)
            if match_index is not None:
                title_index[match_index] = (normalize_title(merged["title"]), merged)
            if merged is not match:
                deduped[deduped.index(match)] = merged
        else:
            title_index.append((title_key, item))
            deduped.append(item)

    write_json(PROCESSED_DIR / f"{date_str}-deduped.json", deduped)
    return deduped
