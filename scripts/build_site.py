from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from utils import LOGS_DIR, PROJECT_ROOT, REPORTS_DIR


SITE_DIR = PROJECT_ROOT / "site"
SITE_REPORTS_DIR = SITE_DIR / "reports"
REPORT_PATTERN = "daily-tech-news-*.md"


@dataclass
class Story:
    title: str
    link: str = ""
    source: str = ""
    category: str = ""
    summary: str = ""
    meta: str = ""


@dataclass
class ReportDoc:
    path: Path
    date: str
    title: str
    generated_at: str = ""
    snapshot: list[str] = field(default_factory=list)
    sections: dict[str, list[Story]] = field(default_factory=dict)


def _escape(value: str) -> str:
    return html.escape(value or "", quote=True)


def _strip_md_links(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)


def _md_inline(text: str) -> str:
    escaped = _escape(text)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: f'<a href="{_escape(match.group(2))}" target="_blank" rel="noopener noreferrer">{_escape(match.group(1))}</a>',
        escaped,
    )
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def _extract_link(text: str) -> tuple[str, str]:
    match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text.strip(), ""


def _parse_story(block: list[str]) -> Story | None:
    if not block:
        return None
    first = re.sub(r"^\d+\.\s*", "", block[0]).strip()
    title, link = _extract_link(first)
    story = Story(title=_strip_md_links(title), link=link)

    for raw in block[1:]:
        line = raw.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if line.startswith("热度：") or line.startswith("score ") or line.startswith("来源："):
            story.meta = _strip_md_links(line)
            source_match = re.search(r"来源：([^|]+)", line)
            if source_match:
                story.source = source_match.group(1).strip()
            category_match = re.search(r"分类：([^|]+)", line)
            if category_match:
                story.category = category_match.group(1).strip()
        elif line.startswith("主要来源："):
            source_match = re.search(r"主要来源：([^|]+)", line)
            if source_match and not story.source:
                story.source = source_match.group(1).strip()
            _, main_link = _extract_link(line)
            if main_link and not story.link:
                story.link = main_link
        elif line.startswith("摘要："):
            story.summary = _strip_md_links(line.removeprefix("摘要：").strip())
        elif line and not story.summary and len(line) > 16:
            story.summary = _strip_md_links(line)
    return story


def parse_report(path: Path) -> ReportDoc:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    doc = ReportDoc(path=path, date=date_match.group(1) if date_match else path.stem, title=path.stem)

    current_section: str | None = None
    story_block: list[str] = []

    def flush_story() -> None:
        nonlocal story_block
        if current_section and story_block:
            story = _parse_story(story_block)
            if story:
                doc.sections.setdefault(current_section, []).append(story)
        story_block = []

    for line in lines:
        if line.startswith("# "):
            doc.title = line[2:].strip()
            continue
        if line.startswith("Generated at:"):
            doc.generated_at = line.split(":", 1)[1].strip()
            continue
        if line.startswith("## "):
            flush_story()
            current_section = line[3:].strip()
            doc.sections.setdefault(current_section, [])
            continue
        if current_section == "Snapshot" and line.startswith("- "):
            doc.snapshot.append(line[2:].strip())
            continue
        if current_section and re.match(r"^\d+\.\s+", line):
            flush_story()
            story_block = [line]
            continue
        if story_block and (line.startswith("   - ") or line.startswith("- ") or line.strip()):
            story_block.append(line)
    flush_story()
    return doc


def _render_story_card(story: Story) -> str:
    href = story.link or "#"
    source = story.source or "未知来源"
    category = story.category or "未分类"
    title_html = f'<a href="{_escape(href)}" target="_blank" rel="noopener noreferrer">{_escape(story.title)}</a>' if story.link else _escape(story.title)
    return f"""
      <article class="story-card">
        <div class="story-meta"><span>{_escape(source)}</span><span>{_escape(category)}</span></div>
        <h3>{title_html}</h3>
        <p>{_escape(story.summary or "暂无摘要")}</p>
      </article>
    """


def _render_section(title: str, stories: list[Story], limit: int = 8) -> str:
    if not stories:
        return f"""
    <section class="section-block">
      <div class="section-title"><h2>{_escape(title)}</h2></div>
      <p class="muted">暂无条目。</p>
    </section>
        """
    cards = "\n".join(_render_story_card(story) for story in stories[:limit])
    return f"""
    <section class="section-block">
      <div class="section-title"><h2>{_escape(title)}</h2><span>{len(stories)} 条</span></div>
      <div class="story-grid">{cards}</div>
    </section>
    """


def _render_markdown_page(doc: ReportDoc, body_html: str, markdown_name: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(doc.title)}</title>
  <link rel="stylesheet" href="../styles.css">
</head>
<body>
  <main class="page">
    <nav class="top-nav"><a href="../index.html">返回看板</a><a href="{_escape(markdown_name)}">Markdown 原文</a></nav>
    <article class="report-article">{body_html}</article>
  </main>
</body>
</html>
"""


def _markdown_to_html(markdown: str) -> str:
    parts: list[str] = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            parts.append(f"<h1>{_md_inline(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h2>{_md_inline(line[3:].strip())}</h2>")
        elif re.match(r"^\d+\.\s+", line):
            if in_list:
                parts.append("</ul>")
                in_list = False
            heading = re.sub(r"^\d+\.\s+", "", line).strip()
            parts.append(f"<h3>{_md_inline(heading)}</h3>")
        elif line.strip().startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_md_inline(line.strip()[2:].strip())}</li>")
        else:
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<p>{_md_inline(line.strip())}</p>")
    if in_list:
        parts.append("</ul>")
    return "\n".join(parts)


def _telegram_status() -> str:
    log_path = LOGS_DIR / "daily.log"
    if not log_path.exists():
        return "见 logs/daily.log"
    tail = log_path.read_text(encoding="utf-8", errors="ignore")[-6000:]
    success = re.findall(r"Telegram report sent: ([^\n]+)", tail)
    failed = re.findall(r"Telegram send failed: ([^\n]+)", tail)
    if success and (not failed or tail.rfind("Telegram report sent:") > tail.rfind("Telegram send failed:")):
        return f"最近一次成功：{success[-1]}"
    if failed:
        return "最近一次失败，见 logs/daily.log"
    return "见 logs/daily.log"


def _write_styles() -> None:
    css = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #1f2933;
  --muted: #697586;
  --line: #d9dee7;
  --accent: #0f766e;
  --accent-soft: #e4f4f1;
  --shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: var(--text);
  background: var(--bg);
  line-height: 1.6;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.page { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 48px; }
.hero {
  display: grid;
  gap: 18px;
  padding: 28px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.hero h1 { margin: 0; font-size: clamp(28px, 5vw, 44px); line-height: 1.15; }
.hero p { margin: 0; color: var(--muted); max-width: 760px; }
.hero-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.button {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: var(--accent);
  color: white;
  font-weight: 700;
}
.button.secondary { background: white; color: var(--accent); }
.dashboard-grid { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 18px; margin-top: 18px; }
.panel, .section-block {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
  padding: 20px;
}
.panel h2, .section-block h2 { margin: 0; font-size: 20px; }
.snapshot-list, .report-list { margin: 14px 0 0; padding: 0; list-style: none; display: grid; gap: 10px; }
.snapshot-list li, .report-list li { padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: #fbfcfd; }
.section-block { margin-top: 18px; }
.section-title { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 14px; }
.section-title span, .muted { color: var(--muted); }
.story-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.story-card {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  background: #fbfcfd;
}
.story-card h3 { margin: 8px 0; font-size: 17px; line-height: 1.35; }
.story-card p { margin: 0; color: var(--muted); font-size: 14px; }
.story-meta { display: flex; flex-wrap: wrap; gap: 8px; }
.story-meta span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}
.top-nav { display: flex; gap: 14px; margin-bottom: 18px; }
.report-article {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 24px;
  box-shadow: var(--shadow);
}
.report-article h1 { margin-top: 0; }
.report-article h2 { margin-top: 30px; padding-top: 14px; border-top: 1px solid var(--line); }
.report-article h3 { margin-top: 22px; }
.report-article li { margin: 6px 0; }
footer { margin-top: 24px; color: var(--muted); font-size: 14px; }
@media (max-width: 820px) {
  .page { width: min(100% - 20px, 1180px); padding-top: 14px; }
  .hero, .panel, .section-block, .report-article { padding: 16px; }
  .dashboard-grid, .story-grid { grid-template-columns: 1fr; }
}
"""
    (SITE_DIR / "styles.css").write_text(css.strip() + "\n", encoding="utf-8")


def build_site() -> Path:
    report_paths = sorted(REPORTS_DIR.glob(REPORT_PATTERN), key=lambda path: path.name, reverse=True)
    if not report_paths:
        raise FileNotFoundError(f"No reports found in {REPORTS_DIR}")

    SITE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    docs = [parse_report(path) for path in report_paths]
    latest = docs[0]

    for doc in docs:
        markdown_name = doc.path.name
        html_name = doc.path.with_suffix(".html").name
        shutil.copy2(doc.path, SITE_REPORTS_DIR / markdown_name)
        body_html = _markdown_to_html(doc.path.read_text(encoding="utf-8"))
        (SITE_REPORTS_DIR / html_name).write_text(
            _render_markdown_page(doc, body_html, markdown_name),
            encoding="utf-8",
        )

    _write_styles()

    recent_links = "\n".join(
        f'<li><a href="reports/{_escape(doc.path.with_suffix(".html").name)}">{_escape(doc.date)}</a> '
        f'<a class="muted" href="reports/{_escape(doc.path.name)}">Markdown</a></li>'
        for doc in docs[:7]
    )
    snapshot = "\n".join(f"<li>{_md_inline(item)}</li>" for item in latest.snapshot) or "<li>暂无 Snapshot</li>"

    section_aliases = [
        ("Top Stories / 今日重点", ["今日重点", "Top Stories"]),
        ("中国科技热点", ["中国科技热点"]),
        ("国际科技观察", ["国际科技观察"]),
        ("开发者与开源趋势", ["开发者与开源趋势"]),
    ]
    sections_html = []
    for title, aliases in section_aliases:
        stories: list[Story] = []
        for alias in aliases:
            stories = latest.sections.get(alias, [])
            if stories:
                break
        sections_html.append(_render_section(title, stories))

    latest_summary = latest.sections.get("今日重点") or latest.sections.get("Top Stories") or []
    summary_cards = "\n".join(_render_story_card(story) for story in latest_summary[:3])
    latest_html_name = latest.path.with_suffix(".html").name

    index_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>每日科技新闻看板</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="page">
    <section class="hero">
      <div>
        <h1>每日科技新闻看板</h1>
        <p>以内地主流科技新闻为主，兼顾国际科技观察、开发者社区和开源趋势。</p>
      </div>
      <div class="hero-actions">
        <a class="button" href="reports/{_escape(latest_html_name)}">查看最新日报</a>
        <a class="button secondary" href="reports/{_escape(latest.path.name)}">下载 Markdown</a>
      </div>
    </section>

    <section class="dashboard-grid">
      <div class="panel">
        <h2>最新日报摘要</h2>
        <p class="muted">最新日报日期：{_escape(latest.date)}</p>
        <div class="story-grid">{summary_cards or '<p class="muted">暂无摘要。</p>'}</div>
      </div>
      <div class="panel">
        <h2>最近 7 天日报</h2>
        <ul class="report-list">{recent_links}</ul>
      </div>
    </section>

    <section class="panel" style="margin-top: 18px;">
      <h2>Snapshot</h2>
      <ul class="snapshot-list">{snapshot}</ul>
    </section>

    {''.join(sections_html)}

    <footer>
      <p>数据更新时间：{_escape(datetime.now().astimezone().isoformat())}</p>
      <p>Telegram 推送状态：{_escape(_telegram_status())}</p>
    </footer>
  </main>
</body>
</html>
"""
    index_path = SITE_DIR / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    return index_path


def main() -> None:
    index_path = build_site()
    print(f"Site generated: {index_path}")


if __name__ == "__main__":
    main()
