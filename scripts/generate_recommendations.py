from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from dateutil import parser

from generate_report import select_report_items
from utils import RECOMMENDATIONS_DIR, REPORTS_DIR, stable_id, write_json


DISPLAY_CATEGORIES = {
    "AI": "AI / 大模型",
    "芯片": "芯片 / 半导体",
    "消费电子": "消费电子",
    "互联网公司": "互联网公司",
    "机器人": "机器人",
    "新能源汽车": "新能源汽车",
    "云计算": "云计算",
    "软件 / SaaS": "软件 / SaaS",
    "科技政策": "科技政策",
    "资本市场": "资本市场",
}

CATEGORY_RULES = {
    "AI / 大模型": ["AI", "大模型", "智能体", "Agent", "LLM", "AIGC", "GPT", "Claude", "Gemini", "DeepSeek"],
    "芯片 / 半导体": ["芯片", "半导体", "算力", "GPU", "NPU", "晶圆", "封测", "DRAM"],
    "消费电子": ["手机", "iPhone", "折叠屏", "电脑", "耳机", "平板", "硬件"],
    "互联网公司": ["电商", "平台", "阿里", "腾讯", "字节", "百度", "美团", "京东"],
    "机器人": ["机器人", "具身", "自动驾驶", "无人车"],
    "新能源汽车": ["新能源", "智能车", "自动驾驶", "比亚迪", "蔚来", "小鹏", "理想"],
    "云计算": ["云计算", "云服务", "数据中心", "Azure", "AWS"],
    "软件 / SaaS": ["软件", "SaaS", "开源", "开发者", "应用", "Coding"],
    "科技政策": ["政策", "监管", "工信部", "商务部", "规划", "禁令"],
    "资本市场": ["融资", "IPO", "上市", "财报", "并购", "投资"],
}

EVENT_RULES = {
    "新品发布": ["发布", "推出", "上线", "亮相", "发布会"],
    "融资": ["融资", "投资", "募资"],
    "财报": ["财报", "营收", "利润", "亏损"],
    "并购": ["并购", "收购", "合并"],
    "监管": ["监管", "处罚", "调查", "禁令", "诉讼"],
    "供应链": ["供应链", "供应商", "代工", "产能"],
    "价格调整": ["降价", "涨价", "价格", "订阅费"],
    "技术突破": ["突破", "论文", "模型", "芯片", "算法"],
    "合作": ["合作", "联手", "签约", "联盟"],
    "裁员": ["裁员", "离职", "重组"],
    "市场竞争": ["竞争", "份额", "对手", "挑战"],
}

BUSINESS_TERMS = ["收入", "成本", "市场", "份额", "供应链", "融资", "IPO", "财报", "价格", "战略", "竞争", "商业"]
DISCUSSION_TERMS = ["为什么", "争议", "回应", "首次", "突然", "背后", "影响", "挑战", "能否"]
CONTROVERSY_TERMS = ["争议", "监管", "诉讼", "调查", "回应", "禁令", "分歧", "离职", "裁员", "价格战", "竞争"]
UNCERTAIN_TERMS = ["传", "网传", "消息称", "据称", "可能", "或", "爆料", "尚未", "未确认", "知情人士"]
ROUNDUP_TERMS = ["早报", "晨报", "晚报", "汇总", "要闻提示", "一文看懂", "一文读懂"]


def _main_item(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("main_item", event)


def _event_text(event: dict[str, Any]) -> str:
    parts = [event.get("topic_title", ""), event.get("summary", "")]
    parts.extend(item.get("title", "") for item in event.get("items", []))
    parts.extend(item.get("summary", "") for item in event.get("items", [])[:3])
    return " ".join(parts)


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    dt = parser.parse(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _age_hours(event: dict[str, Any]) -> float:
    item = _main_item(event)
    value = event.get("latest_seen_at") or item.get("news_time") or item.get("published_at") or item.get("collected_at")
    try:
        return max(0.0, (datetime.now(timezone.utc) - _parse_time(value)).total_seconds() / 3600)
    except (ValueError, TypeError, OverflowError):
        return 72.0


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 1)


def _hits(text: str, words: list[str]) -> list[str]:
    lower = text.lower()
    return [word for word in words if word.lower() in lower]


def _companies(event: dict[str, Any]) -> list[str]:
    companies = []
    for item in event.get("items", []):
        companies.extend(item.get("companies", []))
    return sorted(set(companies))


def _categories(event: dict[str, Any]) -> list[str]:
    text = _event_text(event)
    categories = []
    for item in event.get("items", []):
        for topic in item.get("topics", []):
            category = DISPLAY_CATEGORIES.get(topic)
            if category and category not in categories:
                categories.append(category)
    for category, words in CATEGORY_RULES.items():
        if category not in categories and _hits(text, words):
            categories.append(category)
    return categories or ["其他"]


def _event_type(event: dict[str, Any]) -> str:
    if _is_roundup(event):
        return "综合简讯"
    from_items = [item.get("event_type") for item in event.get("items", []) if item.get("event_type") and item.get("event_type") != "其他"]
    if from_items:
        return Counter(from_items).most_common(1)[0][0]
    text = _event_text(event)
    for event_type, words in EVENT_RULES.items():
        if _hits(text, words):
            return event_type
    return "其他"


def _is_roundup(event: dict[str, Any]) -> bool:
    item = _main_item(event)
    text = " ".join([event.get("topic_title", ""), event.get("summary", ""), item.get("title", ""), item.get("url", "")])
    return "/zaobao/" in item.get("url", "") or bool(_hits(text, ROUNDUP_TERMS))


def _reason(label: str, evidence: list[str], fallback: str) -> str:
    if evidence:
        return f"{label}：" + "、".join(evidence[:4])
    return fallback


def _score_event(event: dict[str, Any], categories: list[str], event_type: str) -> dict[str, dict[str, Any]]:
    text = _event_text(event)
    source_count = int(event.get("source_count", 1))
    companies = _companies(event)
    business_hits = _hits(text, BUSINESS_TERMS)
    discussion_hits = _hits(text, DISCUSSION_TERMS)
    controversy_hits = _hits(text, CONTROVERSY_TERMS)
    category_bonus = sum(1 for category in categories if category != "其他")

    importance = 3.0 + min(3.0, source_count * 0.8) + min(2.0, category_bonus * 0.6)
    if {"AI / 大模型", "芯片 / 半导体", "科技政策", "资本市场"} & set(categories):
        importance += 1.2
    if companies:
        importance += 0.8

    business = 2.5 + min(3.0, len(business_hits) * 0.9) + min(1.8, len(companies) * 0.45)
    if event_type in {"融资", "财报", "并购", "供应链", "价格调整", "市场竞争"}:
        business += 1.6
    if "资本市场" in categories:
        business += 0.8

    discussion = 3.0 + min(2.4, len(discussion_hits) * 0.8) + min(1.6, category_bonus * 0.4)
    if event_type in {"新品发布", "监管", "裁员", "价格调整", "市场竞争"}:
        discussion += 1.2
    if companies:
        discussion += 0.8

    controversy = 2.0 + min(4.0, len(controversy_hits) * 1.0)
    if event_type in {"监管", "裁员", "价格调整", "市场竞争"}:
        controversy += 2.0

    depth = 3.0 + min(2.4, category_bonus * 0.6) + min(1.6, len(companies) * 0.4) + min(2.0, len(business_hits) * 0.5)
    if event_type in {"供应链", "监管", "并购", "技术突破", "市场竞争"}:
        depth += 1.2

    freshness = 10.0 * math.exp(-_age_hours(event) / 96.0)

    return {
        "importance_score": {
            "score": _clamp_score(importance),
            "reason": _reason("影响因素", categories + companies, "来源质量、行业相关性和事件规模中等"),
        },
        "business_score": {
            "score": _clamp_score(business),
            "reason": _reason("商业线索", business_hits + [event_type], "商业模式或产业链线索不强"),
        },
        "discussion_score": {
            "score": _clamp_score(discussion),
            "reason": _reason("讨论入口", discussion_hits + categories, "可以解释事件背景，但公众讨论入口有限"),
        },
        "controversy_score": {
            "score": _clamp_score(controversy),
            "reason": _reason("分歧信号", controversy_hits, "暂未看到明显利益冲突或政策争议"),
        },
        "depth_score": {
            "score": _clamp_score(depth),
            "reason": _reason("延展方向", categories + business_hits + companies, "可延展到行业背景，但深挖空间一般"),
        },
        "freshness_score": {
            "score": _clamp_score(freshness),
            "reason": f"最近更新时间约 {_age_hours(event):.0f} 小时内",
        },
    }


def _total_score(scores: dict[str, dict[str, Any]], config: dict[str, Any]) -> float:
    weights = config.get("recommendation", {}).get("score_weights", {})
    default_weights = {
        "importance_score": 0.25,
        "business_score": 0.25,
        "discussion_score": 0.20,
        "depth_score": 0.20,
        "controversy_score": 0.05,
        "freshness_score": 0.05,
    }
    total = 0.0
    for name, default in default_weights.items():
        total += float(scores[name]["score"]) * float(weights.get(name, default))
    return round(total, 1)


def _level(score: float, config: dict[str, Any]) -> str:
    levels = config.get("recommendation", {}).get("levels", {})
    if score >= float(levels.get("strong", 8.0)):
        return "强烈推荐"
    if score >= float(levels.get("watch", 7.0)):
        return "值得关注"
    if score >= float(levels.get("backup", 6.0)):
        return "备选"
    return "不推送"


def _short_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    return title if len(title) <= 42 else title[:40].rstrip() + "..."


def _uncertainty_note(event: dict[str, Any]) -> str:
    text = _event_text(event)
    if _hits(text, UNCERTAIN_TERMS):
        return "含市场消息或未确认表述，制作内容前需要核实原始信源。"
    return "当前按已采集报道表述处理，观点延伸仍需与事实分开。"


def _research_directions(categories: list[str], companies: list[str], event_type: str) -> list[str]:
    directions = []
    if companies:
        directions.append("相关公司的收入结构、战略优先级和历史动作")
    if "芯片 / 半导体" in categories:
        directions.append("上游供应链、产能、技术路线和主要竞争者")
    if "AI / 大模型" in categories:
        directions.append("模型能力、成本结构、生态合作和商业化路径")
    if "资本市场" in categories or event_type in {"融资", "财报", "IPO"}:
        directions.append("估值、融资节奏、盈利能力和资本市场预期")
    if "科技政策" in categories or event_type == "监管":
        directions.append("政策文件、监管口径和对上下游企业的约束")
    directions.append("同类事件的历史案例和市场反应")
    directions.append("需要核实的原始公告、财报、监管文件或权威报道")
    return directions[:5]


def _angle(categories: list[str], event_type: str) -> str:
    if event_type == "供应链":
        return "从供应链议价、产能弹性和替代供应商关系切入。"
    if event_type in {"融资", "财报", "并购"}:
        return "从资本预期与真实商业化能力是否匹配切入。"
    if event_type == "监管" or "科技政策" in categories:
        return "从监管约束如何改变公司策略和行业竞争边界切入。"
    if "AI / 大模型" in categories:
        return "从能力展示背后的成本、场景和商业闭环切入。"
    if "芯片 / 半导体" in categories:
        return "从技术路线、供应链位置和国产替代的真实约束切入。"
    return "从它改变了谁的成本、收入、效率或竞争位置切入。"


def _topic_for_event(event: dict[str, Any], categories: list[str], event_type: str, scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    title = _short_title(event.get("topic_title") or _main_item(event).get("title", "未命名事件"))
    companies = _companies(event)
    company_text = companies[0] if companies else "这件事"
    return {
        "topic_title": f"{title}，真正值得研究的商业问题是什么？",
        "core_question": f"{company_text} 的这次动作究竟会改变收入、成本、供应链还是竞争格局？",
        "why_it_matters": scores["importance_score"]["reason"],
        "recommended_angle": _angle(categories, event_type),
        "research_directions": _research_directions(categories, companies, event_type),
        "scores": scores,
    }


def _links(event: dict[str, Any]) -> list[dict[str, str]]:
    links = []
    seen = set()
    for item in [_main_item(event)] + event.get("related_items", []) + event.get("items", []):
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        links.append({"source": item.get("source", "unknown"), "title": item.get("title", ""), "url": url})
    return links


def _recommendation_record(event: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    categories = _categories(event)
    event_type = _event_type(event)
    scores = _score_event(event, categories, event_type)
    total = _total_score(scores, config)
    if _is_roundup(event):
        total = min(total, 5.9)
    return {
        "id": stable_id(event.get("id", ""), event.get("topic_title", "")),
        "event_title": event.get("topic_title") or _main_item(event).get("title", ""),
        "event_summary": event.get("summary") or _main_item(event).get("summary", ""),
        "event_type": event_type,
        "categories": categories,
        "companies": _companies(event),
        "main_source": _main_item(event).get("source", "unknown"),
        "sources": event.get("sources", [_main_item(event).get("source", "unknown")]),
        "source_count": event.get("source_count", 1),
        "fact_boundary": _uncertainty_note(event),
        "scores": scores,
        "total_score": total,
        "news_heat_score": float(event.get("heat_score", 0.0) or 0.0),
        "selection_score": total,
        "recommendation_level": _level(total, config),
        "topic": _topic_for_event(event, categories, event_type, scores),
        "related_news": event.get("items", []),
        "links": _links(event),
        "classification_method": "rules_fallback",
    }


def _selection_score(record: dict[str, Any], max_heat_score: float, config: dict[str, Any]) -> float:
    weights = config.get("recommendation", {}).get("selection_weights", {})
    total_weight = float(weights.get("total_score", 0.65))
    heat_weight = float(weights.get("heat_score", 0.35))
    heat_score = 10.0 * float(record.get("news_heat_score", 0.0)) / max_heat_score if max_heat_score else 0.0
    return round(float(record["total_score"]) * total_weight + heat_score * heat_weight, 2)


def _rank_for_push(records: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    top_n = int(config.get("recommendation", {}).get("top_n", 5))
    min_score = float(config.get("recommendation", {}).get("min_push_score", 6.0))
    candidate_pool_size = int(config.get("recommendation", {}).get("candidate_pool_size", 20))
    candidates = [record for record in records if record["total_score"] >= min_score][:candidate_pool_size]
    max_heat_score = max((record.get("news_heat_score", 0.0) for record in candidates), default=0.0)
    for record in candidates:
        record["selection_score"] = _selection_score(record, max_heat_score, config)
    candidates.sort(key=lambda row: (row["selection_score"], row["news_heat_score"], row["total_score"]), reverse=True)
    return candidates[:top_n]


def _daily_focus_titles(date_str: str) -> list[str]:
    path = REPORTS_DIR / f"daily-tech-news-{date_str}.md"
    if not path.exists():
        return []

    titles = []
    in_focus = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if in_focus:
                break
            in_focus = line.strip() == "## 今日重点"
            continue
        if not in_focus:
            continue
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if match:
            titles.append(match.group(1).strip())
    return titles


def _title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().lower()


def _focus_records_from_report(records: list[dict[str, Any]], date_str: str) -> list[dict[str, Any]]:
    focus_records = []
    unused = list(records)
    for title in _daily_focus_titles(date_str):
        title_key = _title_key(title)
        match = next((record for record in unused if _title_key(record["event_title"]) == title_key), None)
        if not match:
            match = next((record for record in unused if title_key in _title_key(record["event_title"]) or _title_key(record["event_title"]) in title_key), None)
        if match:
            focus_records.append(match)
            unused.remove(match)
    return focus_records


def _render_focus_topics(focus_records: list[dict[str, Any]]) -> list[str]:
    lines = ["", "## 日报今日重点衍生选题", ""]
    if not focus_records:
        lines.append("今日日报没有可用于衍生选题的重点事件。")
        return lines

    for index, record in enumerate(focus_records, 1):
        topic = record["topic"]
        summary = record["event_summary"] or record["event_title"]
        links = record["links"][:2]
        lines.extend(
            [
                f"{index}. {topic['topic_title']}",
                f"   - 来自日报重点：{record['event_title']}",
                f"   - 核心事件：{summary}",
                f"   - 推荐切入：{topic['recommended_angle']}",
            ]
        )
        if links:
            lines.append("   - 原始链接：" + "；".join(f"{link['source']}：{link['url']}" for link in links))
    return lines


def _render_markdown(records: list[dict[str, Any]], selected: list[dict[str, Any]], focus_records: list[dict[str, Any]], date_str: str, config: dict[str, Any]) -> Path:
    lines = [
        "# dailyNews · 今日科技商业选题",
        "",
        f"日期：{date_str}",
        f"生成时间：{datetime.now().astimezone().isoformat()}",
        f"候选事件：{len(records)}，推送选题：{len(selected)}",
        f"候选来源：daily-tech-news 热度排序前 {config.get('recommendation', {}).get('candidate_pool_size', 20)} 个事件",
        "",
    ]
    if not selected:
        lines.append("今日没有达到推送阈值的科技商业选题。")

    for index, record in enumerate(selected, 1):
        topic = record["topic"]
        scores = record["scores"]
        lines.extend(
            [
                "━━━━━━━━━━",
                "",
                f"TOP {index} · {record['recommendation_level']}",
                "",
                topic["topic_title"],
                "",
                f"综合评分：{record['total_score']} / 10",
                f"选题排序分：{record['selection_score']} / 10（含日报热度）",
                f"日报热度：{record['news_heat_score']}",
                "",
                f"重要性：{scores['importance_score']['score']} - {scores['importance_score']['reason']}",
                f"商业价值：{scores['business_score']['score']} - {scores['business_score']['reason']}",
                f"讨论价值：{scores['discussion_score']['score']} - {scores['discussion_score']['reason']}",
                f"延展性：{scores['depth_score']['score']} - {scores['depth_score']['reason']}",
                f"争议性：{scores['controversy_score']['score']} - {scores['controversy_score']['reason']}",
                f"时效性：{scores['freshness_score']['score']} - {scores['freshness_score']['reason']}",
                "",
                "核心事件：",
                record["event_summary"] or record["event_title"],
                "",
                "为什么值得做：",
                topic["why_it_matters"],
                "",
                "推荐切入：",
                topic["recommended_angle"],
                "",
                "信息边界：",
                record["fact_boundary"],
                "",
                "建议研究：",
            ]
        )
        lines.extend(f"{number}. {direction}" for number, direction in enumerate(topic["research_directions"], 1))
        lines.extend(["", "来源：", "、".join(record["sources"]) or record["main_source"], "", "原始链接："])
        lines.extend(f"- {link['source']}：{link['url']}" for link in record["links"][:5])
        lines.append("")

    lines.extend(_render_focus_topics(focus_records))

    path = REPORTS_DIR / f"topic-radar-{date_str}.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def generate_recommendations(events: list[dict[str, Any]], config: dict[str, Any], date_str: str) -> str:
    report_events = select_report_items(events, config)
    focus_event_ids = {event["id"] for event in report_events[:6]}
    report_event_ids = {event["id"] for event in report_events}
    ordered_events = report_events + [event for event in events if event["id"] not in report_event_ids]
    records = [_recommendation_record(event, config) for event in ordered_events]
    focus_records = _focus_records_from_report(records, date_str)
    if not focus_records:
        focus_records = [record for event, record in zip(ordered_events, records) if event["id"] in focus_event_ids]
    selected = _rank_for_push(records, config)
    selected_ids = {record["id"] for record in selected}
    records = selected + [record for record in records if record["id"] not in selected_ids]
    output = {
        "date": date_str,
        "generated_at": datetime.now().astimezone().isoformat(),
        "scoring_weights": config.get("recommendation", {}).get("score_weights", {}),
        "selection_weights": config.get("recommendation", {}).get("selection_weights", {}),
        "candidate_pool_size": config.get("recommendation", {}).get("candidate_pool_size", 20),
        "daily_focus_topics": focus_records,
        "recommendations": records,
    }
    write_json(RECOMMENDATIONS_DIR / f"{date_str}.json", output)
    return str(_render_markdown(records, selected, focus_records, date_str, config))
