from __future__ import annotations

import re
from datetime import timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from dateutil import parser

from utils import NORMALIZED_DIR, PROCESSED_DIR, stable_id, write_json


TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}

COMPANY_ALIASES = {
    "Apple": ["Apple", "苹果", "iPhone", "Mac"],
    "OpenAI": ["OpenAI", "ChatGPT", "GPT"],
    "NVIDIA": ["NVIDIA", "英伟达"],
    "Google": ["Google", "谷歌", "Gemini"],
    "Anthropic": ["Anthropic", "Claude"],
    "Meta": ["Meta", "Facebook"],
    "Microsoft": ["Microsoft", "微软"],
    "Amazon": ["Amazon", "AWS", "亚马逊"],
    "Huawei": ["Huawei", "华为", "鸿蒙"],
    "Alibaba": ["Alibaba", "阿里", "阿里巴巴", "通义", "夸克"],
    "Tencent": ["Tencent", "腾讯", "混元"],
    "ByteDance": ["ByteDance", "字节跳动", "豆包"],
    "Baidu": ["Baidu", "百度", "文心"],
    "Xiaomi": ["Xiaomi", "小米"],
    "JD.com": ["JD", "京东"],
    "Meituan": ["Meituan", "美团"],
    "BYD": ["BYD", "比亚迪"],
    "NIO": ["NIO", "蔚来"],
    "XPeng": ["XPeng", "小鹏"],
    "Li Auto": ["Li Auto", "理想汽车", "理想"],
    "DeepSeek": ["DeepSeek"],
}

TOPIC_KEYWORDS = {
    "AI": ["AI", "大模型", "智能体", "Agent", "LLM", "AIGC", "ChatGPT", "GPT", "Claude", "Gemini", "DeepSeek"],
    "芯片": ["芯片", "半导体", "算力", "GPU", "NPU", "晶圆", "封测"],
    "消费电子": ["手机", "iPhone", "折叠屏", "电脑", "耳机", "平板", "硬件"],
    "互联网公司": ["电商", "平台", "阿里", "腾讯", "字节", "百度", "美团", "京东"],
    "机器人": ["机器人", "具身", "自动驾驶", "无人车"],
    "新能源汽车": ["新能源", "智能车", "自动驾驶", "比亚迪", "蔚来", "小鹏", "理想"],
    "云计算": ["云计算", "云服务", "数据中心", "Azure", "AWS"],
    "软件 / SaaS": ["软件", "SaaS", "开源", "开发者", "应用"],
    "科技政策": ["政策", "监管", "工信部", "商务部", "规划"],
    "资本市场": ["融资", "IPO", "上市", "财报", "并购", "投资"],
}

EVENT_TYPE_KEYWORDS = {
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


def _language(text: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en"


def _companies(text: str) -> list[str]:
    lower = text.lower()
    return [company for company, aliases in COMPANY_ALIASES.items() if any(alias.lower() in lower for alias in aliases)]


def _topics(text: str) -> list[str]:
    lower = text.lower()
    return [topic for topic, words in TOPIC_KEYWORDS.items() if any(word.lower() in lower for word in words)]


def _event_type(text: str) -> str:
    lower = text.lower()
    for event_type, words in EVENT_TYPE_KEYWORDS.items():
        if any(word.lower() in lower for word in words):
            return event_type
    return "其他"


def normalize_items(items: list[dict[str, Any]], date_str: str) -> list[dict[str, Any]]:
    normalized = []
    for item in items:
        title = _clean_text(item.get("title"))
        url = _canonical_url(item.get("url", ""))
        if not title or not url:
            continue
        summary = _clean_text(item.get("summary"))
        text = f"{title} {summary}"
        published_at = _parse_datetime(item.get("published_at"))
        normalized.append(
            {
                "id": stable_id(url, title),
                "title": title,
                "url": url,
                "summary": summary,
                "content": _clean_text(item.get("content")),
                "publish_time": published_at,
                "published_at": published_at,
                "collected_at": _parse_datetime(item.get("collected_at")),
                "language": _language(text),
                "companies": _companies(text),
                "topics": _topics(text),
                "event_type": _event_type(text),
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
    write_json(NORMALIZED_DIR / f"{date_str}.json", normalized)
    write_json(PROCESSED_DIR / f"{date_str}-normalized.json", normalized)
    return normalized
