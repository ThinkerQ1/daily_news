from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

from dateutil import parser

from rank import _keyword_score, _metrics_score
from utils import LOGS_DIR, PROCESSED_DIR, stable_id, write_json


KEY_TERMS = [
    "AI",
    "大模型",
    "智能体",
    "Agent",
    "LLM",
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
    "低空经济",
    "卫星互联网",
    "数据中心",
    "出海",
    "监管",
    "投融资",
    "OpenAI",
    "Google",
    "Anthropic",
    "Meta",
    "Microsoft",
    "NVIDIA",
    "GitHub",
    "Apple",
    "DeepSeek",
    "Claude",
    "Gemini",
    "GPT",
]

STOP_TOKENS = {
    "一个",
    "发布",
    "正式",
    "宣布",
    "消息",
    "今日",
    "今年",
    "进行",
    "推出",
    "上线",
    "更新",
    "获得",
    "公司",
    "科技",
    "中国",
    "国际",
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "that",
    "this",
}

GENERIC_CLUSTER_TERMS = {"ai", "agent", "llm", "google", "microsoft", "github", "apple"}


def _log(message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with (LOGS_DIR / "daily.log").open("a", encoding="utf-8") as fh:
        fh.write(message + "\n")


def _domain(url: str) -> str:
    netloc = urlparse(url or "").netloc.lower()
    return netloc.removeprefix("www.")


def _source_key(source: str) -> str:
    if source.startswith("GitHub Trending"):
        return "GitHub Trending"
    if source.startswith("Google News"):
        return "Google News"
    return source or "unknown"


def _news_time(item: dict[str, Any]) -> datetime:
    value = item.get("news_time") or item.get("published_at") or item.get("collected_at")
    return parser.parse(value)


def _clean_title(title: str) -> str:
    title = re.sub(r"https?://\S+", " ", title or "")
    title = re.sub(r"[｜|_-].{0,20}$", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def _ngrams(text: str, size: int) -> set[str]:
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    joined = "".join(chars)
    return {joined[index : index + size] for index in range(max(0, len(joined) - size + 1))}


def _tokens(item: dict[str, Any]) -> set[str]:
    text = item.get("title", "")
    lower = text.lower()
    tokens = {term.lower() for term in KEY_TERMS if term.lower() in lower}
    tokens.update(word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9+\-.]{1,}", text))
    tokens.update(re.findall(r"\d+(?:\.\d+)?", text))
    tokens.update(_ngrams(item.get("title", ""), 2))
    tokens.update(_ngrams(item.get("title", ""), 3))
    return {token for token in tokens if token and token not in STOP_TOKENS and len(token) > 1}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _cluster_similarity(item: dict[str, Any], cluster: dict[str, Any]) -> float:
    item_title = _clean_title(item.get("title", "")).lower()
    cluster_title = _clean_title(cluster["_match_title"]).lower()
    title_score = SequenceMatcher(None, item_title, cluster_title).ratio()
    token_score = _jaccard(item["_topic_tokens"], cluster["_match_tokens"])
    shared_key_terms = item["_key_terms"] & cluster["_match_key_terms"]
    strong_shared_terms = shared_key_terms - GENERIC_CLUSTER_TERMS
    item_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", item_title))
    cluster_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", cluster_title))
    key_bonus = min(0.16, len(shared_key_terms) * 0.04)
    if item_has_cjk != cluster_has_cjk and title_score < 0.62 and (token_score < 0.45 or not strong_shared_terms):
        return 0.0
    if title_score < 0.62 and (token_score < 0.38 or len(shared_key_terms) < 2):
        return 0.0
    return max(title_score, token_score + key_bonus)


def _quality_score(item: dict[str, Any], config: dict[str, Any]) -> float:
    quality = float(item.get("source_quality", 0.0) or 0.0)
    if quality:
        return quality
    quality_config = config.get("source_quality_scores", {})
    source_scores = quality_config.get("sources", {})
    category_scores = quality_config.get("categories", {})
    source = item.get("source", "")
    for source_name, score in source_scores.items():
        if source == source_name or source.startswith(f"{source_name} "):
            return float(score)
    return float(category_scores.get(item.get("source_category"), quality_config.get("default", 0.75)))


def _item_value(item: dict[str, Any], config: dict[str, Any]) -> float:
    quality = _quality_score(item, config)
    summary_len = min(1.0, len(item.get("summary", "")) / 260)
    official_bonus = 0.4 if item.get("source_category") == "official_blog" else 0.0
    recency_bonus = 0.2
    metrics_bonus = min(1.0, _metrics_score(item) / 8)
    return quality * 3 + summary_len + official_bonus + recency_bonus + metrics_bonus


def _pick_main_item(items: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    return max(items, key=lambda item: (_item_value(item, config), _news_time(item)))


def _region(cluster: dict[str, Any]) -> str:
    regions = Counter(item.get("source_region", "international") for item in cluster["items"])
    return "china" if regions.get("china", 0) >= regions.get("international", 0) else "international"


def _topic_title(cluster: dict[str, Any], config: dict[str, Any]) -> str:
    main = _pick_main_item(cluster["items"], config)
    title = _clean_title(main.get("title", ""))
    terms = [term for term in KEY_TERMS if term.lower() in " ".join(cluster["_topic_tokens"]).lower()]
    if cluster["source_count"] >= 2 and terms:
        prefix = "、".join(terms[:3])
        if prefix and prefix not in title:
            return f"{prefix}：{title}"
    return title


def _cluster_summary(cluster: dict[str, Any]) -> str:
    snippets = []
    seen = set()
    for item in cluster["items"]:
        text = item.get("summary") or item.get("title", "")
        text = re.sub(r"\s+", " ", text).strip()
        if not text or text in seen:
            continue
        snippets.append(text[:120])
        seen.add(text)
        if len(snippets) >= 3:
            break
    return " ".join(snippets)[:360]


def _importance_reason(cluster: dict[str, Any]) -> str:
    reasons = []
    if cluster["source_count"] >= 4:
        reasons.append("达到核心热点覆盖")
    elif cluster["source_count"] >= 2:
        reasons.append("获得多源交叉验证")
    if cluster.get("matched_keywords"):
        reasons.append("命中重点方向：" + "、".join(cluster["matched_keywords"][:5]))
    if cluster["region"] == "china":
        reasons.append("与中国科技产业主线相关")
    if len(cluster.get("source_categories", [])) >= 2:
        reasons.append("覆盖不同类型来源")
    return "；".join(reasons) or "来源质量、时效和主题相关性综合较高"


def _heat_score(cluster: dict[str, Any], config: dict[str, Any]) -> tuple[float, list[str]]:
    keywords = config.get("keywords", {})
    text = " ".join([cluster["topic_title"]] + [item.get("summary", "") for item in cluster["items"][:4]])
    keyword_score, matched = _keyword_score(text, keywords, cluster["region"])
    keyword_score = min(keyword_score, 18.0 if cluster["source_count"] >= 2 else 12.0)
    latest = max(_news_time(item) for item in cluster["items"])
    age_hours = max(0.0, (datetime.now(latest.tzinfo) - latest).total_seconds() / 3600)
    half_life = float(config.get("settings", {}).get("freshness_half_life_hours", 36))
    recency_score = math.exp(-age_hours / half_life) * 4
    source_count = cluster["source_count"]
    source_quality_total = sum(cluster["_domain_quality"].values())
    category_diversity = len(cluster["source_categories"])
    multi_source_bonus = 0.0
    if source_count >= 2:
        multi_source_bonus += 8.0 + source_count * 2.0
    if source_count >= int(config.get("settings", {}).get("core_topic_source_threshold", 4)):
        multi_source_bonus += 6.0
    region_bonus = 1.5 if cluster["region"] == "china" else 0.4
    focus_bonus = 2.0 if matched else 0.0
    metrics_score = min(4.0, sum(_metrics_score(item) for item in cluster["items"]) / 4)
    score = (
        source_quality_total * 3
        + keyword_score
        + recency_score
        + multi_source_bonus
        + category_diversity * 0.7
        + region_bonus
        + focus_bonus
        + metrics_score
    )
    return round(score, 3), matched


def _finalize_cluster(cluster: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    threshold = float(config.get("settings", {}).get("min_cluster_similarity", 0.45))
    main_item = _pick_main_item(cluster["items"], config)
    match_cluster = {
        "_match_title": main_item.get("title", ""),
        "_match_tokens": set(main_item.get("_topic_tokens", set())),
        "_match_key_terms": set(main_item.get("_key_terms", set())),
    }
    valid_items = []
    for item in cluster["items"]:
        if item["id"] == main_item["id"] or _cluster_similarity(item, match_cluster) >= threshold:
            valid_items.append(item)
        else:
            _log(f"Skip duplicate from same domain: {item.get('title')} | domain={item.get('_domain', '')}")
    cluster["items"] = valid_items
    cluster["_domains"] = {item["_domain"] for item in valid_items}
    cluster["_source_keys"] = {item["_source_key"] for item in valid_items}
    cluster["_source_names"] = {item["_source_key"]: item.get("source", "unknown") for item in valid_items}
    cluster["_domain_quality"] = {item["_domain"]: item["source_quality"] for item in valid_items}
    cluster["_topic_tokens"] = set().union(*(item["_topic_tokens"] for item in valid_items)) if valid_items else set()
    cluster["_key_terms"] = set().union(*(item["_key_terms"] for item in valid_items)) if valid_items else set()
    cluster["source_count"] = len(cluster["_source_keys"])
    cluster["sources"] = sorted(cluster["_source_names"].values())
    cluster["source_categories"] = sorted({item.get("source_category", "unknown") for item in cluster["items"]})
    cluster["region"] = _region(cluster)
    cluster["main_item"] = _pick_main_item(cluster["items"], config)
    cluster["topic_title"] = _topic_title(cluster, config)
    cluster["items"] = [_public_item(item) for item in cluster["items"]]
    cluster["main_item"] = _public_item(cluster["main_item"])
    cluster["related_items"] = [item for item in cluster["items"] if item["id"] != cluster["main_item"]["id"]]
    cluster["first_seen_at"] = min(_news_time(item) for item in cluster["items"]).isoformat()
    cluster["latest_seen_at"] = max(_news_time(item) for item in cluster["items"]).isoformat()
    cluster["summary"] = _cluster_summary(cluster)
    cluster["heat_score"], cluster["matched_keywords"] = _heat_score(cluster, config)
    cluster["why_important"] = _importance_reason(cluster)
    cluster["id"] = stable_id(cluster["topic_title"], ",".join(cluster["sources"]))
    return {key: value for key, value in cluster.items() if not key.startswith("_")}


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if not key.startswith("_")}


def cluster_topics(
    items: list[dict[str, Any]],
    config: dict[str, Any],
    date_str: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    settings = config.get("settings", {})
    threshold = float(settings.get("min_cluster_similarity", 0.45))
    hot_threshold = int(settings.get("hot_topic_source_threshold", 2))
    clusters: list[dict[str, Any]] = []

    prepared = []
    for item in items:
        item = dict(item)
        item["_domain"] = _domain(item.get("url", ""))
        item["_source_key"] = _source_key(item.get("source", "unknown"))
        item["_topic_tokens"] = _tokens(item)
        item["_key_terms"] = {term.lower() for term in KEY_TERMS if term.lower() in item.get("title", "").lower()}
        item["source_quality"] = _quality_score(item, config)
        prepared.append(item)

    prepared.sort(key=lambda item: (_news_time(item), _item_value(item, config)), reverse=True)

    same_domain_duplicates = 0
    for item in prepared:
        best_cluster = None
        best_score = 0.0
        for cluster in clusters:
            score = _cluster_similarity(item, cluster)
            if score > best_score:
                best_score = score
            best_cluster = cluster

        if best_cluster and best_score >= threshold:
            domain = item["_domain"]
            source_key = item["_source_key"]
            if domain in best_cluster["_domains"] or source_key in best_cluster["_source_keys"]:
                same_domain_duplicates += 1
                _log(f"Skip duplicate from same domain: {item.get('title')} | domain={domain}")
                continue
            best_cluster["items"].append(item)
            best_cluster["_domains"].add(domain)
            best_cluster["_source_keys"].add(source_key)
            best_cluster["_domain_sources"][domain] = item.get("source", "unknown")
            best_cluster["_source_names"][source_key] = item.get("source", "unknown")
            best_cluster["_domain_quality"][domain] = max(best_cluster["_domain_quality"].get(domain, 0.0), item["source_quality"])
            best_cluster["_topic_tokens"].update(item["_topic_tokens"])
            best_cluster["_key_terms"].update(item["_key_terms"])
            continue

        domain = item["_domain"]
        source_key = item["_source_key"]
        clusters.append(
            {
                "topic_title": _clean_title(item.get("title", "")),
                "items": [item],
                "_domains": {domain},
                "_source_keys": {source_key},
                "_domain_sources": {domain: item.get("source", "unknown")},
                "_source_names": {source_key: item.get("source", "unknown")},
                "_domain_quality": {domain: item["source_quality"]},
                "_topic_tokens": set(item["_topic_tokens"]),
                "_key_terms": set(item["_key_terms"]),
                "_match_title": item.get("title", ""),
                "_match_tokens": set(item["_topic_tokens"]),
                "_match_key_terms": set(item["_key_terms"]),
            }
        )

    finalized = [_finalize_cluster(cluster, config) for cluster in clusters]
    finalized.sort(key=lambda cluster: cluster["heat_score"], reverse=True)

    for cluster in finalized:
        if cluster["source_count"] >= hot_threshold:
            _log(
                "Cluster created: "
                f"{cluster['topic_title']} | source_count={cluster['source_count']} | sources={','.join(cluster['sources'])}"
            )
            _log(
                "Promote hot topic: "
                f"{cluster['topic_title']} | source_count={cluster['source_count']} | heat_score={cluster['heat_score']}"
            )

    audit = {
        "input_items": len(items),
        "topic_clusters": len(finalized),
        "multi_source_hot_topics": sum(1 for cluster in finalized if cluster["source_count"] >= hot_threshold),
        "highest_source_count": max((cluster["source_count"] for cluster in finalized), default=0),
        "same_domain_duplicates": same_domain_duplicates,
        "min_cluster_similarity": threshold,
        "hot_topic_source_threshold": hot_threshold,
        "core_topic_source_threshold": int(settings.get("core_topic_source_threshold", 4)),
    }
    write_json(PROCESSED_DIR / f"{date_str}-topic-clusters.json", finalized)
    write_json(PROCESSED_DIR / f"{date_str}-cluster-audit.json", audit)
    return finalized, audit
