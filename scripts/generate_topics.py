from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from utils import PROCESSED_DIR, PROJECT_ROOT, REPORTS_DIR, stable_id


TOPICS_DIR = PROJECT_ROOT / "outputs" / "topics"
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

THEMES: list[dict[str, Any]] = [
    {
        "id": "ai_agent",
        "name": "AI 与智能体",
        "terms": ["AI", "大模型", "智能体", "Agent", "LLM", "开源", "多模态", "Coding", "Siri", "Claude", "Gemini", "GPT"],
        "title": "AI 竞争正在从模型发布转向智能体落地",
        "topic_type": "趋势判断",
        "platforms": "公众号 / 知乎 / 视频脚本",
        "core": "单点模型能力已经不够构成壁垒，产品化、生态入口和真实工作流落地正在成为新一轮竞争焦点。",
        "reader": "关注 AI 工具、产品经理、开发者和科技内容读者",
        "spread": "把复杂的模型新闻转成普通读者能理解的产品趋势，并能延展到工作效率、创业机会和平台竞争。",
        "risk": "模型参数、开源协议、融资金额和产品发布时间需要核实；避免把单个产品发布夸大成行业定论。",
        "words": "1800-2500 字",
        "titles": [
            "大模型不只拼参数了，真正的战场转向智能体",
            "为什么 AI 公司都开始强调 Agent 和生态？",
            "从模型发布到工作流落地：AI 竞争进入下半场",
        ],
        "outline": [
            "用今日新闻串起模型、Agent、AI 应用入口的共同变化",
            "分析竞争焦点为何从单次发布转向生态、数据和工作流",
            "判断普通用户、开发者和企业客户接下来会受到什么影响",
        ],
    },
    {
        "id": "chip_compute",
        "name": "芯片与算力",
        "terms": ["芯片", "半导体", "算力", "GPU", "HBM", "英伟达", "NVIDIA", "昇腾", "鲲鹏", "龙芯", "数据中心", "光模块", "CPO"],
        "title": "AI 算力竞争正在重塑芯片、数据中心和供应链",
        "topic_type": "深度分析",
        "platforms": "公众号 / 知乎 / 头条",
        "core": "AI 热点背后的核心变量不是单一芯片，而是从芯片、网络、数据中心到软件生态的整条算力供应链。",
        "reader": "科技产业读者、投资者、半导体和云计算从业者",
        "spread": "算力是 AI 产业最容易被大众理解的硬约束，适合用供应链视角解释行业变化。",
        "risk": "制程、性能、采购规模和项目投资额容易被误读，需要优先引用原始公告或权威媒体。",
        "words": "2200-3000 字",
        "titles": [
            "AI 的下一场硬仗，不在模型而在算力供应链",
            "芯片、数据中心、光模块：谁在吃到 AI 算力红利？",
            "国产算力为什么越来越强调生态和易用性？",
        ],
        "outline": [
            "梳理今日算力、芯片和数据中心相关新闻",
            "拆解 AI 需求如何传导到硬件、云服务和产业链公司",
            "讨论国产算力与全球供应链各自的机会和约束",
        ],
    },
    {
        "id": "robot_car",
        "name": "智能车与机器人",
        "terms": ["智能车", "自动驾驶", "辅助驾驶", "机器人", "具身", "VLA", "世界模型", "比亚迪", "小鹏", "理想", "蔚来", "小米汽车", "特斯拉", "华为乾崑"],
        "title": "智能车和机器人正在从技术秀走向规模化落地",
        "topic_type": "商业分析",
        "platforms": "公众号 / 头条 / 视频脚本",
        "core": "智能车与机器人不再只是发布会概念，真实交付、成本控制、场景适配和安全责任正在决定商业化速度。",
        "reader": "汽车科技读者、机器人从业者、消费电子和产业投资关注者",
        "spread": "车和机器人有具象场景，容易用案例讲清楚技术商业化的难点。",
        "risk": "自动驾驶能力、事故责任、量产时间和融资信息都需要二次核实，避免营销口径当事实。",
        "words": "1800-2600 字",
        "titles": [
            "智能车和机器人，终于进入拼交付的阶段",
            "具身智能热潮背后，谁能真正走进工厂和家庭？",
            "从智驾到机器人：AI 硬件商业化为什么越来越难？",
        ],
        "outline": [
            "从今日智能车、机器人新闻提炼共同趋势",
            "分析技术路线、供应链、场景落地和安全责任的变化",
            "给出哪些公司和赛道更值得持续跟踪",
        ],
    },
    {
        "id": "bigtech_business",
        "name": "互联网大厂与商业竞争",
        "terms": ["阿里", "腾讯", "字节", "百度", "京东", "美团", "拼多多", "小米", "华为", "电商", "广告", "云", "搜索", "出行", "支付"],
        "title": "互联网大厂正在把 AI 变成新一轮业务入口竞争",
        "topic_type": "商业分析",
        "platforms": "公众号 / 头条 / 知乎",
        "core": "大厂的 AI 动作不只是技术展示，背后是搜索、办公、电商、出行、内容和云服务入口的重新分配。",
        "reader": "互联网从业者、产品运营、商业观察类读者",
        "spread": "大厂竞争天然有关注度，适合解释“为什么这些公司同时做同一件事”。",
        "risk": "商业合作、用户规模和财务数据要核实；不要把短期动作直接推断为战略胜负。",
        "words": "1800-2400 字",
        "titles": [
            "大厂密集加码 AI，争的其实是下一代入口",
            "AI 正在改写互联网公司的业务边界",
            "从搜索到出行，大厂为什么都要把 AI 塞进核心业务？",
        ],
        "outline": [
            "列出今日大厂相关热点及它们对应的业务入口",
            "分析 AI 如何改变原有产品的获客、留存和变现逻辑",
            "判断哪些业务会先被 AI 重做，哪些只是营销包装",
        ],
    },
    {
        "id": "finance_ipo",
        "name": "投融资与上市",
        "terms": ["投融资", "融资", "A轮", "天使轮", "IPO", "上市", "估值", "港交所", "科创板", "收购", "入股"],
        "title": "科技投融资正在向 AI 基础设施和硬科技集中",
        "topic_type": "趋势判断",
        "platforms": "公众号 / 知乎 / 头条",
        "core": "资本更愿意押注有真实客户、硬件壁垒或基础设施属性的项目，泛 AI 概念正在让位于可验证的商业化。",
        "reader": "创业者、投资人、科技产业观察者",
        "spread": "融资和上市新闻适合从资本流向切入，解释哪些赛道正在升温或降温。",
        "risk": "融资金额、估值、投资方和上市进度必须核实；避免使用未确认传闻做确定性判断。",
        "words": "1600-2200 字",
        "titles": [
            "AI 热潮没有退，钱正流向更硬的地方",
            "从融资到 IPO：科技资本在押注哪些新方向？",
            "为什么有真实交付能力的 AI 公司更容易拿钱？",
        ],
        "outline": [
            "汇总今日融资、入股、IPO 和估值相关信息",
            "分析资本偏好的赛道、阶段和商业化信号",
            "给出创业者和普通读者应关注的风险与机会",
        ],
    },
    {
        "id": "policy_regulation",
        "name": "监管与政策",
        "terms": ["监管", "政策", "规定", "新规", "规划", "审批", "安全", "合规", "数据", "隐私", "牌照", "限制"],
        "title": "科技产业进入政策、合规和安全共同塑形的新阶段",
        "topic_type": "快评",
        "platforms": "公众号 / 头条 / 知乎",
        "core": "当技术进入大规模应用，监管不只是约束，也会影响产业节奏、商业模式和用户信任。",
        "reader": "科技新闻读者、企业管理者、政策观察者",
        "spread": "政策话题容易和个人生活、企业经营相连，适合做解释型快评。",
        "risk": "法规原文、实施时间和适用范围必须核实；不要把地方政策扩展成全国结论。",
        "words": "1200-1800 字",
        "titles": [
            "科技公司不能只拼速度了，合规正在成为新门槛",
            "新规背后：技术落地为什么越来越离不开监管？",
            "从创新到合规，科技产业的节奏正在变化",
        ],
        "outline": [
            "指出今日政策、监管或安全相关热点",
            "解释政策对企业、用户和行业竞争的影响",
            "提醒仍需核实的适用范围和执行细节",
        ],
    },
]


def _today_shanghai() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _date_from_path(path: Path) -> str | None:
    match = DATE_RE.search(path.name)
    return match.group(1) if match else None


def _main_item(topic: dict[str, Any]) -> dict[str, Any]:
    return topic.get("main_item") or topic


def _story_id(topic: dict[str, Any]) -> str:
    main = _main_item(topic)
    return topic.get("id") or main.get("id") or stable_id(topic.get("topic_title", ""), main.get("url", ""))


def _story_text(topic: dict[str, Any]) -> str:
    main = _main_item(topic)
    parts = [
        topic.get("topic_title", ""),
        topic.get("summary", ""),
        topic.get("why_important", ""),
        main.get("title", ""),
        main.get("summary", ""),
        " ".join(topic.get("matched_keywords", [])),
    ]
    return " ".join(str(part) for part in parts if part)


def _source_count(topic: dict[str, Any]) -> int:
    value = topic.get("source_count") or len(topic.get("sources", [])) or len(_main_item(topic).get("duplicate_sources", [])) or 1
    return int(value)


def _published_date(topic: dict[str, Any]) -> date | None:
    main = _main_item(topic)
    value = topic.get("latest_seen_at") or main.get("news_time") or main.get("published_at") or main.get("collected_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        match = DATE_RE.search(str(value))
        if match:
            return date.fromisoformat(match.group(1))
    return None


def _story_score(topic: dict[str, Any], report_date: date) -> float:
    heat = float(topic.get("heat_score") or _main_item(topic).get("score") or 0)
    keywords = len(topic.get("matched_keywords", []))
    source_count = _source_count(topic)
    region_bonus = 5 if topic.get("region") == "china" or _main_item(topic).get("source_region") == "china" else 0
    categories = topic.get("source_categories") or [_main_item(topic).get("source_category", "")]
    category_bonus = 3 if any("china" in str(category) for category in categories) else 0
    published = _published_date(topic)
    recency_bonus = 0
    if published:
        age_days = max(0, (report_date - published).days)
        if age_days <= 3:
            recency_bonus = 4 - age_days
    return heat + source_count * 4 + min(8, keywords) + region_bonus + category_bonus + recency_bonus


def _sources(topic: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    main = _main_item(topic)
    for item in [main] + list(topic.get("related_items", [])):
        url = item.get("url", "")
        if not url:
            continue
        rows.append(
            {
                "source": item.get("source", "unknown"),
                "url": url,
                "title": item.get("title", topic.get("topic_title", "")),
            }
        )
    seen: set[str] = set()
    unique = []
    for row in rows:
        key = row["url"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _load_ranked(date_str: str, report_path: Path) -> list[dict[str, Any]]:
    default_report = REPORTS_DIR / f"daily-tech-news-{date_str}.md"
    if report_path.resolve() != default_report.resolve():
        return []
    ranked_path = PROCESSED_DIR / f"{date_str}-ranked.json"
    if not ranked_path.exists():
        return []
    with ranked_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else []


def _parse_markdown(report_path: Path) -> list[dict[str, Any]]:
    stories: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in report_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if match:
            if current:
                stories.append(current)
            current = {
                "topic_title": match.group(1).strip(),
                "sources": [],
                "source_categories": [],
                "matched_keywords": [],
                "main_item": {"title": match.group(1).strip(), "source": "unknown", "url": ""},
                "related_items": [],
            }
            continue
        if not current:
            continue
        if "热度：" in line:
            count_match = re.search(r"热度：(\d+)\s*个来源", line)
            if count_match:
                current["source_count"] = int(count_match.group(1))
            source_match = re.search(r"来源：([^|]+)", line)
            if source_match:
                current["sources"] = [item.strip() for item in source_match.group(1).split(",") if item.strip()]
            category_match = re.search(r"分类：([^|]+)", line)
            if category_match:
                current["source_categories"] = [item.strip() for item in category_match.group(1).split(",") if item.strip()]
            time_match = re.search(r"时间：([^|]+)", line)
            if time_match:
                current["latest_seen_at"] = time_match.group(1).strip()
            heat_match = re.search(r"heat_score\s+([0-9.]+)", line)
            if heat_match:
                current["heat_score"] = float(heat_match.group(1))
            keyword_match = re.search(r"keywords:\s*(.+)$", line)
            if keyword_match:
                current["matched_keywords"] = [item.strip() for item in keyword_match.group(1).split(",") if item.strip()]
        elif "主要来源：" in line:
            source_match = re.search(r"主要来源：(.+?)\s*\|\s*\[主链接\]\((.*?)\)", line)
            if source_match:
                current["main_item"]["source"] = source_match.group(1).strip()
                current["main_item"]["url"] = source_match.group(2).strip()
        elif "相关链接：" in line:
            for source, url in re.findall(r"([^：；]+)：\[链接\]\((.*?)\)", line):
                current["related_items"].append({"source": source.strip(), "url": url.strip(), "title": current["topic_title"]})
        elif "摘要：" in line:
            summary = line.split("摘要：", 1)[1].strip()
            current["summary"] = summary
            current["main_item"]["summary"] = summary
        elif "为什么重要：" in line:
            current["why_important"] = line.split("为什么重要：", 1)[1].strip()
    if current:
        stories.append(current)
    for story in stories:
        story["id"] = _story_id(story)
    return stories


def _parse_focus_markdown(report_path: Path) -> list[dict[str, Any]]:
    stories: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_focus = False
    for line in report_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if in_focus:
                break
            in_focus = line.strip() == "## 今日重点"
            continue
        if not in_focus:
            continue
        match = re.match(r"^\d+\.\s+(.+)$", line)
        if match:
            if current:
                stories.append(current)
            current = {
                "topic_title": match.group(1).strip(),
                "sources": [],
                "source_categories": [],
                "matched_keywords": [],
                "main_item": {"title": match.group(1).strip(), "source": "unknown", "url": ""},
                "related_items": [],
            }
            continue
        if not current:
            continue
        if "主要来源：" in line:
            source_match = re.search(r"主要来源：(.+?)\s*\|\s*\[主链接\]\((.*?)\)", line)
            if source_match:
                current["main_item"]["source"] = source_match.group(1).strip()
                current["main_item"]["url"] = source_match.group(2).strip()
        elif "相关链接：" in line:
            for source, url in re.findall(r"([^：；]+)：\[链接\]\((.*?)\)", line):
                current["related_items"].append({"source": source.strip(), "url": url.strip(), "title": current["topic_title"]})
        elif "摘要：" in line:
            summary = line.split("摘要：", 1)[1].strip()
            current["summary"] = summary
            current["main_item"]["summary"] = summary
        elif "为什么重要：" in line:
            current["why_important"] = line.split("为什么重要：", 1)[1].strip()
    if current:
        stories.append(current)
    for story in stories:
        story["id"] = _story_id(story)
    return stories


def _matches_theme(story: dict[str, Any], theme: dict[str, Any]) -> bool:
    return _theme_match_score(story, theme) > 0


def _theme_match_score(story: dict[str, Any], theme: dict[str, Any]) -> int:
    main = _main_item(story)
    headline_text = " ".join(
        [
            story.get("topic_title", ""),
            main.get("title", ""),
            " ".join(story.get("matched_keywords", [])),
        ]
    ).lower()
    full_text = _story_text(story).lower()
    score = 0
    for term in theme["terms"]:
        term = str(term).lower()
        if term in headline_text:
            score += 3
        elif term in full_text:
            score += 1
    return score


def _rank_theme_groups(stories: list[dict[str, Any]], report_date: date) -> list[dict[str, Any]]:
    groups = []
    for theme in THEMES:
        matched = [story for story in stories if _matches_theme(story, theme)]
        if not matched:
            continue
        matched.sort(key=lambda story: (_theme_match_score(story, theme) * 10 + _story_score(story, report_date)), reverse=True)
        evidence = matched[:5]
        score = sum(_story_score(story, report_date) + _theme_match_score(story, theme) * 4 for story in evidence) / len(evidence)
        score += min(10, len(matched)) + sum(max(0, _source_count(story) - 1) * 3 for story in evidence)
        groups.append({"theme": theme, "stories": evidence, "score": score})
    groups.sort(key=lambda group: group["score"], reverse=True)
    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for group in groups:
        ids = {_story_id(story) for story in group["stories"][:3]}
        if selected and len(ids & used_ids) >= 2:
            continue
        selected.append(group)
        used_ids.update(ids)
        if len(selected) >= 5:
            break
    if len(selected) < 3:
        for group in groups:
            if group in selected:
                continue
            selected.append(group)
            if len(selected) >= min(3, len(groups)):
                break
    return selected[:5]


def _recommendation_index(group: dict[str, Any]) -> int:
    best_source_count = max((_source_count(story) for story in group["stories"]), default=1)
    score = group["score"]
    if best_source_count >= 2 or score >= 45:
        return 5
    if score >= 35:
        return 4
    return 3


def _reason(group: dict[str, Any]) -> str:
    stories = group["stories"]
    sources = sorted({row["source"] for story in stories for row in _sources(story)})
    theme_terms = {str(term).lower() for term in group["theme"]["terms"]}
    keywords = sorted(
        {
            keyword
            for story in stories
            for keyword in story.get("matched_keywords", [])
            if str(keyword).lower() in theme_terms
        }
    )[:6]
    bits = []
    if any(_source_count(story) >= 2 for story in stories):
        bits.append("存在多源报道热点")
    bits.append(f"相关报道集中在 {group['theme']['name']}")
    if keywords:
        bits.append("命中关键词：" + "、".join(keywords))
    if sources:
        bits.append("可引用来源：" + "、".join(sources[:4]))
    return "；".join(bits)


def _render_sources(stories: list[dict[str, Any]]) -> list[str]:
    lines = []
    seen: set[str] = set()
    for story in stories:
        for source in _sources(story):
            if source["url"] in seen:
                continue
            seen.add(source["url"])
            title = source["title"]
            if len(title) > 36:
                title = title[:35].rstrip() + "..."
            lines.append(f"     - {source['source']}（{title}）：{source['url']}")
            if len(lines) >= 5:
                return lines
    return lines or ["     - 暂无可引用链接"]


def _render_focus_markdown(stories: list[dict[str, Any]]) -> list[str]:
    lines = ["", "## 日报今日重点专题角度", ""]
    if not stories:
        lines.append("今日日报没有可用于衍生选题的重点事件。")
        return lines

    for index, story in enumerate(stories, 1):
        title = story["topic_title"]
        lines.extend(
            [
                f"### {index}. {title}",
                f"- 选题角度：不要复述新闻本身，重点追问这件事会改变哪些用户选择、公司策略或产业节奏。",
                f"- 核心依据：{story.get('summary') or story.get('why_important') or title}",
                "- 相关来源：",
            ]
        )
        lines.extend(_render_sources([story]))
    return lines


def _render_markdown(date_str: str, groups: list[dict[str, Any]], focus_stories: list[dict[str, Any]] | None = None) -> str:
    directions = "、".join(group["theme"]["name"] for group in groups)
    lines = [
        f"# 今日自媒体选题推荐 - {date_str}",
        "",
        "## 选题总览",
        f"- 今日推荐选题数量：{len(groups)}",
        f"- 主要方向：{directions}",
        f"- 最值得写的 1 个选题：{groups[0]['theme']['title'] if groups else '暂无'}",
        "",
    ]
    for index, group in enumerate(groups, 1):
        theme = group["theme"]
        lines.extend(
            [
                f"## {index}. {theme['title']}",
                f"- 选题类型：{theme['topic_type']}",
                f"- 适合平台：{theme['platforms']}",
                f"- 推荐指数：{_recommendation_index(group)}",
                f"- 推荐理由：{_reason(group)}",
                f"- 核心观点：{theme['core']}",
                "- 推荐标题：",
            ]
        )
        lines.extend(f"  {title_index}. {title}" for title_index, title in enumerate(theme["titles"], 1))
        lines.append("- 文章大纲：")
        lines.extend(f"  {outline_index}. {outline}" for outline_index, outline in enumerate(theme["outline"], 1))
        lines.append("- 相关来源：")
        lines.extend(_render_sources(group["stories"]))
        lines.extend(
            [
                f"- 目标读者：{theme['reader']}",
                f"- 传播点：{theme['spread']}",
                f"- 风险点：{theme['risk']}",
                f"- 建议字数：{theme['words']}",
                "",
            ]
        )
    lines.extend(_render_focus_markdown(focus_stories or []))
    return "\n".join(lines).rstrip() + "\n"


def _resolve_date(date_str: str | None, input_path: Path | None) -> str:
    if date_str:
        return date_str
    if input_path:
        path_date = _date_from_path(input_path)
        if path_date:
            return path_date
    return _today_shanghai()


def generate_topics(date_str: str | None = None, input_path: str | Path | None = None) -> str:
    report_path = Path(input_path) if input_path else None
    date_str = _resolve_date(date_str, report_path)
    report_path = report_path or REPORTS_DIR / f"daily-tech-news-{date_str}.md"
    report_path = report_path.expanduser()
    if not report_path.is_absolute():
        report_path = PROJECT_ROOT / report_path
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    stories = _load_ranked(date_str, report_path) or _parse_markdown(report_path)
    if not stories:
        raise ValueError(f"No news items parsed from report: {report_path}")

    groups = _rank_theme_groups(stories, date.fromisoformat(date_str))
    if not groups:
        raise ValueError(f"No suitable self-media topics found in report: {report_path}")

    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TOPICS_DIR / f"topics-{date_str}.md"
    output_path.write_text(_render_markdown(date_str, groups, _parse_focus_markdown(report_path)), encoding="utf-8")
    return str(output_path.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate self-media topic ideas from a daily tech news report.")
    parser.add_argument("--date", help="Report date, defaults to today in Asia/Shanghai or the date in --input.")
    parser.add_argument("--input", help="Path to a specific daily report Markdown file.")
    args = parser.parse_args()
    output_path = generate_topics(args.date, args.input)
    print(f"Topics generated: {output_path}")


if __name__ == "__main__":
    main()
