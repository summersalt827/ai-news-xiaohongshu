# News Pipeline — AI 新闻抓取与精选

## 概述

从邮箱拉取 AI 新闻邮件 → 翻译 → 全网多源抓取 → Claude 精选内容 → 输出到 xhs_publish。

两种发布场景：
- **周报（默认）**：精选 6-8 条 AI 新闻 + 3 条 GitHub 项目 → AI News 周报格式，覆盖近7天
- **AI Skills 深度**：单主题深度内容 → 长图文格式（手动触发）

**每次精选前必读** `.claude/preferences.md` — 用户的内容偏好和过滤规则。偏好文件改语料，不改代码。

**看到好的小红书样式时说「参考这个样式」** → 触发 `.claude/skills/style-reference.md` 自动提取设计 token + 生成 HTML。

## 文件夹结构

```
ai-news-xiaohongshu/
├── news_pipeline/     ← 📥 本目录：抓取与精选
├── xhs_publish/       ← 📕 小红书生成与发布
├── legacy/            ← 🗄️ 旧文件参考
├── daily/             ← Markdown + 双语 HTML
├── xiaohongshu/       ← 小红书输出（按日期）
└── logs/              ← 运行日志
```

## 文件

| 文件 | 职责 |
|------|------|
| `fetch_ai_news.py` | 主编排入口，协调全流程 |
| `web_scraper.py` | 全网抓取：Bing + HN + Reddit + Twitter/X + ArXiv |
| `github_trending.py` | GitHub Search API 抓 24h star 增速最快仓库 |
| `item_matcher.py` | Claude 从全源中精选内容 |
| `claude_utils.py` | 共享 Claude API 调用 + JSON 宽松解析 |

## 运行方式

```bash
cd ai-news-xiaohongshu
python3 news_pipeline/fetch_ai_news.py
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `EMAIL_163_USER` | 163 邮箱地址 |
| `EMAIL_163_PASS` | 163 IMAP 授权码 |
| `ANTHROPIC_API_KEY` | Claude API key |
| `ANTHROPIC_BASE_URL` | 默认 `https://api.deepseek.com/anthropic` |
| `ANTHROPIC_MODEL` | 默认 `deepseek-v4-pro[1m]` |
| `FEISHU_WEBHOOK` | 飞书推送 Webhook（可选） |
| `VERCEL_URL` | Vercel 部署地址 |
| `GITHUB_TOKEN` | GitHub API token（可选，提高频率限制） |

## 流程

```
Weekday (AI News 周报 — 默认):
  1. IMAP 连接 163 → 搜索近7天标题含 [AINews] 的邮件
  2. Claude 翻译（中英对照格式）
  3. 全网抓取（web_scraper）— 独立于邮件
  4. Claude 精选 6-8 条 AI 新闻（item_matcher），按分类组织
  5. GitHub Trending 3 条（github_trending，7天范围）
  6. 终端交互确认
  7. 输出 → xhs_publish/（卡片 + 封面 + 视频）

AI Skills 深度 (手动触发):
  1. 全网抓取 + 邮件内容
  2. Claude 选一个深度话题
  3. 生成 xhs-skill 格式长图文（cover + p1~p4）
  4. 文案用 xhs-skill-caption.md 格式
```

## 信息源

| 源 | 接入方式 | 状态 |
|----|---------|------|
| Bing | HTML 解析 b_algo 块 | ✅ |
| Hacker News | Algolia API | ✅ |
| Reddit | JSON API | ❌ 国内超时 |
| Twitter/X | Nitter 镜像 → Bing fallback | ✅ |
| ArXiv | Atom XML API | ✅ |
| 媒体博客 | Bing site: 搜索 | ✅ |
| GitHub Trending | Search API | ✅ |
