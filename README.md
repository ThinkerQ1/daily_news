# Daily News

一个轻量的每日科技新闻采集、聚类、日报生成和自媒体选题提炼项目。核心原则是先用公开、稳定、可解释的数据源和规则完成闭环，再按需要接入 OpenClaw 做少量网页补采。

## 第一性原理流程

本项目把每日新闻处理拆成几个清晰步骤：

1. 采集：从 RSS、公开 API、GitHub Trending、Hacker News 和 Google News RSS 获取候选新闻。
2. 归一化：统一标题、链接、来源、发布时间、分类和区域。
3. 过滤：只保留最近窗口内的新闻，默认最近 3 天。
4. 聚类：把相似标题或多源报道合并成一个 topic cluster。
5. 排序：按来源质量、关键词、时效、多源数量和社区指标计算热度。
6. 生成日报：输出 `reports/daily-tech-news-YYYY-MM-DD.md`。
7. 生成选题：从日报和聚类结果提炼 3～5 个自媒体专题角度。
8. 推送：日报成功后再尝试发送 Telegram；推送失败不影响日报文件。

## 数据源

- 科技媒体 RSS：TechCrunch、The Verge、Ars Technica、Wired、MIT Technology Review、IEEE Spectrum
- 官方博客 RSS：OpenAI、Google AI、Microsoft Azure、AWS、GitHub
- Hacker News：Algolia HN Search API
- GitHub Trending：公开页面解析
- Google News RSS：按关键词生成 RSS 搜索源

新闻源、关键词、权重和采集设置都在 `sources.yml` 中维护。

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
│   ├── send_telegram.py
│   └── generate_topics.py
├── prompts/
│   └── openclaw/
├── data/
│   ├── raw/
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
```

原始数据保存到 `data/raw/YYYY-MM-DD/`，处理后的 JSON 保存到 `data/processed/`。

## 自媒体选题提炼

日报生成成功后，`scripts/run_daily.py` 会额外调用 `scripts/generate_topics.py`，基于当天日报提炼 3～5 个“今日推荐选题”。第一版使用规则和模板生成，不直接生成完整文章。

选题文件输出到：

```text
outputs/topics/topics-YYYY-MM-DD.md
```

手动生成当天选题：

```bash
.venv/bin/python scripts/generate_topics.py
```

指定日期：

```bash
.venv/bin/python scripts/generate_topics.py --date 2026-05-28
```

指定某一份日报文件：

```bash
.venv/bin/python scripts/generate_topics.py --input reports/daily-tech-news-2026-05-28.md
```

选题文件只包含专题角度、推荐标题、大纲、相关来源、可引用链接、目标读者、传播点和风险点。后续写完整文章时，可以先选择“最值得写的 1 个选题”，再根据“文章大纲”和“风险点”补充事实核查、数据和案例。

## Telegram 推送

日报生成成功后，`scripts/run_daily.py` 会调用 Telegram Bot API，把最新 Markdown 日报作为附件发送。

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

每次 `scripts/run_daily.py` 生成日报后，会自动调用 `scripts/build_site.py`，把 Markdown 日报构建成静态网页：

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
- 不要提交 `.env`、`.env.dailynews`、`.env.example`、`.venv/`、`logs/`、`data/raw/`、`data/processed/`、`reports/`、`outputs/`、`site/`。这些已在 `.gitignore` 中排除。

推荐的 crontab 写法：

```cron
0 10 * * * cd /path/to/dailyNews && echo "===== $(date) start daily news =====" >> logs/daily.log && /path/to/dailyNews/.venv/bin/python scripts/run_daily.py >> logs/daily.log 2>&1
```

## 排序逻辑

`scripts/rank.py` 会综合以下因素打分：

- 来源权重：官方博客和高质量媒体可获得更高基础分
- 关键词：`sources.yml` 中 high/medium 关键词加分，exclude 关键词扣分
- 新鲜度：越新的内容分数越高
- 多源重复：同一 URL 或高度相似标题被多个来源捕获时加分
- 社区/开发者指标：HN points/comments、GitHub stars/stars today 等

## 去重逻辑

`scripts/dedupe.py` 会先按规范化 URL 去重，再按标题相似度做轻量合并，并保留重复来源列表。
