# Daily News

一个轻量的每日科技新闻采集、聚类、日报生成和科技商业自媒体选题雷达项目。核心原则是先用公开、稳定、可解释的数据源和规则完成闭环，再按需要接入 OpenClaw 做少量网页补采。

## 第一性原理流程

本项目把每日新闻处理拆成几个清晰步骤：

1. 采集：从 RSS、公开 API、GitHub Trending、Hacker News 和 Google News RSS 获取候选新闻。
2. 标准化：统一标题、链接、来源、发布时间、语言、公司、主题和事件类型。
3. 去重：先按 URL 去重，再按标题相似度合并完全重复或近似重复新闻。
4. 过滤：只保留最近窗口内的新闻，默认最近 3 天。
5. 事件聚合：把相似标题或多源报道合并成一个 topic cluster。
6. 日报排序：按来源质量、关键词、时效、多源数量和社区指标计算 `heat_score`。
7. 生成日报：输出 `reports/daily-tech-news-YYYY-MM-DD.md`。
8. 生成选题雷达：优先从日报候选池中选出 Top 5 科技商业选题，输出完整 JSON 和 Telegram Markdown。
9. 推送：选题雷达生成后再尝试发送 Telegram；推送失败不影响本地文件。

## 数据源

- 国内科技媒体 RSS：IT之家、钛媒体、少数派、36氪、cnBeta、新浪科技、量子位、雷峰网
- 待稳定后启用的国内源：中国新闻网科技、机器之心
- 国际科技媒体 RSS：TechCrunch、The Verge
- 官方博客 RSS：OpenAI、Google AI、Microsoft Azure、AWS、GitHub
- Hacker News：Algolia HN Search API
- GitHub Trending：公开页面解析
- Google News RSS：按关键词生成 RSS 搜索源

新闻源、关键词、推荐权重和采集设置都在 `sources.yml` 中维护。每个 source 配置都包含 `enabled`、`quality_score`、`category`、`region`，国内源 `region=china`。

## 目录结构

```text
.
├── sources.yml
├── requirements.txt
├── scripts/
│   ├── run_daily.py
│   ├── collect_rss.py
│   ├── collect_hn.py
│   ├── collect_github_trending.py
│   ├── normalize.py
│   ├── dedupe.py
│   ├── rank.py
│   ├── generate_report.py
│   ├── generate_recommendations.py
│   ├── send_telegram.py
│   └── generate_topics.py
├── prompts/
│   └── openclaw/
├── data/
│   ├── raw/
│   ├── normalized/
│   ├── events/
│   ├── recommendations/
│   └── processed/
├── reports/
└── outputs/
```

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

复制 Telegram 配置模板：

```bash
cp .env.dailynews.example .env.dailynews
```

然后编辑 `.env.dailynews`，填入真实 bot token、chat_id 和代理地址。不要把 `.env.dailynews` 提交到仓库。

## 运行

```bash
python scripts/run_daily.py
```

指定日期：

```bash
python scripts/run_daily.py --date 2026-05-24
```

只收录最近 N 天内发布或采集的新闻：

```bash
python scripts/run_daily.py --window-days 3 --force
```

日报会输出到：

```text
reports/daily-tech-news-YYYY-MM-DD.md
reports/topic-radar-YYYY-MM-DD.md
```

原始数据保存到 `data/raw/YYYY-MM-DD/`。标准化新闻、事件聚合和完整推荐结果分别保存到：

```text
data/normalized/YYYY-MM-DD.json
data/events/YYYY-MM-DD.json
data/recommendations/YYYY-MM-DD.json
```

兼容旧流程的中间 JSON 仍保存到 `data/processed/`。

## 科技商业选题雷达

日报生成成功后，`scripts/run_daily.py` 会调用 `scripts/generate_recommendations.py`，生成“今日科技商业选题”。系统不直接生成完整文章，只回答“今天什么最值得做”。

完整推荐结果输出到：

```text
data/recommendations/YYYY-MM-DD.json
```

Telegram 推送文件输出到：

```text
reports/topic-radar-YYYY-MM-DD.md
```

每条推荐包含：

- 事件标题、事件摘要、来源和原始链接
- AI / 大模型、芯片 / 半导体、消费电子、互联网公司、机器人、新能源汽车、云计算、软件 / SaaS、科技政策、资本市场等分类
- 重要性、商业价值、讨论价值、争议性、延展性、时效性 6 个维度评分
- 每个评分的一句简短理由
- 选题标题、核心问题、推荐切入角度和 3～5 个研究方向
- 信息边界提示，避免把市场消息或推测写成事实

推送 Top 5 默认从 `daily-tech-news` 的日报候选池前 20 个事件中选择，再按 `selection_score` 排序。`selection_score` 默认由 65% 六维综合评分和 35% 日报热度组成，权重在 `sources.yml` 的 `recommendation` 中调整。

手动根据已有事件文件重新生成选题雷达：

```bash
PYTHONPATH=scripts .venv/bin/python -c 'from pathlib import Path; from utils import load_sources, read_json; from generate_recommendations import generate_recommendations; print(generate_recommendations(read_json(Path("data/processed/2026-09-10-topic-clusters.json")), load_sources(), "2026-09-10"))'
```

`scripts/generate_topics.py` 仍保留作为旧版日报选题辅助工具，会输出到：

```text
outputs/topics/topics-YYYY-MM-DD.md
```

后续写完整文章时，可以先选择 `topic-radar` 中最值得写的 1 个选题，再根据研究方向补充事实核查、数据和案例。

## Telegram 推送

选题雷达生成成功后，`scripts/run_daily.py` 会调用 Telegram Bot API，把 `reports/topic-radar-YYYY-MM-DD.md` 作为附件发送。完整日报 `reports/daily-tech-news-YYYY-MM-DD.md` 仍会保留在本地。

Telegram 配置建议写在项目根目录的 `.env.dailynews`，并使用 `DAILYNEWS_TELEGRAM_*` 命名空间，避免和 OpenClaw/Codex 的 Telegram 对话 bot 共享通用 `TELEGRAM_*` 环境变量：

```text
DAILYNEWS_TELEGRAM_BOT_TOKEN=your_dailynews_bot_token
DAILYNEWS_TELEGRAM_CHAT_ID=your_chat_id
DAILYNEWS_TELEGRAM_PROXY=socks5h://127.0.0.1:7897
```

读取优先级为：系统环境变量中的 `DAILYNEWS_TELEGRAM_*` > `.env.dailynews` > `.env` > 旧版 `.env.example` 兜底。默认不读取通用系统环境变量 `TELEGRAM_*`，除非显式设置 `DAILYNEWS_ALLOW_GENERIC_TELEGRAM_ENV=1`。`DAILYNEWS_TELEGRAM_PROXY` 未设置时默认使用 `socks5h://127.0.0.1:7897`。

项目提供了无密钥模板 `.env.dailynews.example`。不要把真实 token 提交到仓库。

单独发送最新日报：

```bash
.venv/bin/python scripts/send_telegram.py
```

## OpenClaw 接入

OpenClaw 用于补充少量需要网页阅读的内容，例如 `scripts/openclaw_collect.py` 会根据 `prompts/openclaw/sspai_collect_prompt.md` 采集少数派近 3 天内的科技内容。

先安装并初始化 OpenClaw CLI，确保本机能执行：

```bash
openclaw --version
openclaw onboard
openclaw status
```

如果还没有安装 OpenClaw，请先按官方文档安装：<https://docs.openclaw.ai/cli>

本项目的 OpenClaw 补采命令：

```bash
.venv/bin/python scripts/openclaw_collect.py
```

也可以执行完整流程：

```bash
bash scripts/run_all.sh
```

`scripts/run_all.sh` 会先尝试 OpenClaw 补采，再运行 `scripts/run_daily.py`。OpenClaw 补采失败会写入 fallback JSON，不阻断主日报流程。

如果希望 OpenClaw 自己通过 Telegram 收发消息，使用 OpenClaw 的 channel 配置，而不是本项目的 `.env.dailynews`：

```bash
openclaw channels add
openclaw channels status
openclaw message send --channel telegram --target @your_chat --message "dailyNews test"
```

如果 OpenClaw 或 Telegram 需要代理，建议只在本机环境里配置，例如：

```bash
DAILYNEWS_TELEGRAM_PROXY=socks5h://127.0.0.1:7897
```

不要把 SSR 订阅、代理密码或真实 token 写进仓库。

## 网页看板部署

每次 `scripts/run_daily.py` 生成日报和选题雷达后，会自动调用 `scripts/build_site.py`，把 Markdown 报告构建成静态网页：

```text
site/
├── index.html
├── styles.css
└── reports/
    ├── daily-tech-news-YYYY-MM-DD.html
    └── daily-tech-news-YYYY-MM-DD.md
```

也可以单独构建：

```bash
.venv/bin/python scripts/build_site.py
```

本地预览：

```bash
cd site
python3 -m http.server 8080
```

浏览器访问：

```text
http://127.0.0.1:8080
```

部署建议：

- GitHub Pages：运行 `scripts/build_site.py` 后，把生成的 `site/` 作为 Pages artifact 发布。
- Cloudflare Pages / Vercel：项目根目录作为仓库根目录，构建命令留空或使用 `.venv/bin/python scripts/build_site.py`，发布目录设置为 `site`。
- 默认不提交 `reports/`、`outputs/`、`site/`、`logs/` 和 `data/` 运行产物；这些都可以由定时任务重新生成。
- 不要提交 `.env`、`.env.dailynews`、`.venv/`、`logs/`、`data/raw/`、`data/normalized/`、`data/events/`、`data/recommendations/`、`data/processed/`、`reports/`、`outputs/`、`site/`。这些已在 `.gitignore` 中排除。

推荐的 crontab 写法：

```cron
0 10 * * * cd /path/to/dailyNews && echo "===== $(date) start daily news =====" >> logs/daily.log && /path/to/dailyNews/.venv/bin/python scripts/run_daily.py >> logs/daily.log 2>&1
```

## 排序逻辑

日报热度排序会综合以下因素打分：

- 来源权重：官方博客和高质量媒体可获得更高基础分
- 关键词：`sources.yml` 中 high/medium 关键词加分，exclude 关键词扣分
- 新鲜度：越新的内容分数越高
- 多源重复：同一 URL 或高度相似标题被多个来源捕获时加分
- 社区/开发者指标：HN points/comments、GitHub stars/stars today 等

## 去重逻辑

`scripts/dedupe.py` 会先按规范化 URL 去重，再按标题相似度做轻量合并，并保留重复来源列表。

## 推荐逻辑

`scripts/generate_recommendations.py` 会为每个事件生成 0～10 分评分：

- 重要性 `importance_score`
- 商业价值 `business_score`
- 讨论价值 `discussion_score`
- 延展性 `depth_score`
- 争议性 `controversy_score`
- 时效性 `freshness_score`

综合评分默认权重为：重要性 25%、商业价值 25%、讨论价值 20%、延展性 20%、争议性 5%、时效性 5%。Top 5 推送会优先参考 `daily-tech-news` 候选池，再结合日报热度，避免单源但讨论空间较大的稿件脱离当天重点。
