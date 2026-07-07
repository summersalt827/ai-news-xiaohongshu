# AI 内容工厂 — 说一句命令，让 AI 为你工作

两个 Claude Code Skill 的开源版，帮你在 90 秒内完成从信息采集到多平台发布的全流程。

## 两个 Skill

| Skill | 一句话 | 适合谁 |
|-------|--------|--------|
| **AI News 发布引擎** | 说一句命令，邮件→卡片→发布全自动 | 想自动化内容生产链的人 |
| **YouTube 内容蒸馏器** | 一个链接 → 4 张卡片 | 想快速把视频转成图文的人 |

---

## 环境要求

| 工具 | 两个 Skill 都需要？ | 安装方式 |
|------|---------------------|----------|
| Python 3.10+ | ✅ 都需要 | `brew install python` 或系统自带 |
| Google Chrome | ✅ 都需要 | 系统自带或 `brew install google-chrome` |
| yt-dlp | ⚠️ 仅 YouTube | `brew install yt-dlp` |
| FFmpeg | ⚠️ 仅 YouTube / 视频 | `brew install ffmpeg` |
| openai-whisper | ⚠️ 仅 YouTube（无字幕时） | `pipx install openai-whisper` |
| 邮箱 + IMAP | ⚠️ 仅 AI News | 163 / Gmail / QQ 均可，需开启 IMAP 生成授权码 |

---

## 快速开始

### 1. 克隆 + 装依赖

```bash
git clone <repo-url> ai-news-pipeline
cd ai-news-pipeline

# Python 依赖（核心）
pip install -r requirements.txt

# 装 Playwright 浏览器
playwright install chromium
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填 ANTHROPIC_API_KEY
```

| 变量 | 必填 | 说明 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key，推荐 `deepseek-v4-pro[1m]` |
| `EMAIL_163_USER` | 仅 AI News | 邮箱地址（163 / Gmail / QQ 均可） |
| `EMAIL_163_PASS` | 仅 AI News | 邮箱 IMAP **授权码**（不是登录密码） |
| `GITHUB_TOKEN` | 可选 | 提高 GitHub API 频率限制 |

> **注意**：默认 API 后端是 `https://api.deepseek.com/anthropic`，模型是 `deepseek-v4-pro[1m]`。想用 Anthropic 官方，设置 `ANTHROPIC_BASE_URL=https://api.anthropic.com` 和 `ANTHROPIC_MODEL=claude-sonnet-4-6`。

---

## Skill 1: AI News 发布引擎

「说一句 AI news，你的内容工厂开始运转」

### 能做什么

```
📧 拉取 → 🌐 翻译 → 🔍 搜索 → ⭐ 精选 → 🎨 卡片 → 🎬 视频 → 📕 发布
  3s       15s       10s       20s       5s       30s        8s
```

### 前置准备

订阅一份 AI 新闻邮件（如 [AINews](https://buttondown.email/ainews)、[TLDR AI](https://tldr.tech/ai)、[The Batch](https://www.deeplearning.ai/the-batch/) 等），然后配置邮箱 IMAP：

1. 登录邮箱网页版（163 / Gmail / QQ 均可）
2. 设置 → 开启 IMAP 服务 → 生成**授权码**
3. 把邮箱地址和授权码填入 `.env` 的 `EMAIL_163_USER` / `EMAIL_163_PASS`

> **注意**：脚本默认搜索标题含 `[AINews]` 的邮件。如果你订阅的是其他 Newsletter，修改 `news_pipeline/fetch_ai_news.py` 顶部的 `SEARCH_SUBJECT` 变量即可。

### 第一次运行

```bash
python3 news_pipeline/fetch_ai_news.py
```

### 定时运行（macOS）

```bash
# 编辑定时任务
crontab -e

# 工作日每天早上 8:00 自动跑
0 8 * * 1-5 cd /path/to/ai-news-pipeline && python3 news_pipeline/fetch_ai_news.py >> logs/cron.log 2>&1
```

### 输出

- `daily/` — 双语日报 MD + HTML（可部署到 Vercel）
- `xiaohongshu/<日期>/` — 小红书素材包（卡片 PNG + 封面 + 文案 + 视频）

### 当天没有邮件怎么办

自动回退到最近一封未处理的邮件，不会空跑。

---

## Skill 2: YouTube 内容蒸馏器

「一个 YouTube 链接 → 4 张高质量卡片」

### 不需要邮箱、不需要定时任务

这是**最轻**的管道，你只需要 `ANTHROPIC_API_KEY` 和 `yt-dlp`。

### 用法

```bash
# 最简单：给一个链接
python3 distill.py https://www.youtube.com/watch?v=xxxxx

# 指定输出目录
python3 distill.py https://www.youtube.com/watch?v=xxxxx --output ~/Desktop/my-cards

# 强制用 Whisper 转写（视频没字幕时）
python3 distill.py https://www.youtube.com/watch?v=xxxxx --force-whisper

# 已有音频文件，直接蒸馏
python3 distill.py --audio ~/Downloads/talk.m4a --skip-download
```

### 工作流程

```
🎬 输入URL → 📥 下载字幕(5s) → 🧠 Claude蒸馏(20s) → 🎨 卡片渲染(5s)
                          ↓ 无字幕时
                    📥 下载音频 → 🎙️ Whisper转写(60s) → 继续蒸馏
```

### 输出

在 `xiaohongshu/<日期>/` 下生成：
- `card_01.png` ~ `card_04.png` — 4 张卡片（1080×1440 @2x）
- `<日期>_cover.png` — 封面图
- `caption.md` — 写好的小红书文案
- 每张卡片含 emoji + 标题 + 3 要点 + Insight

---

## 项目结构

```
ai-news-xiaohongshu/
├── news_pipeline/           ← 📥 信息采集 + AI 处理
│   ├── fetch_ai_news.py     ← AI News 引擎主入口
│   ├── youtube_to_xhs.py    ← YouTube 蒸馏核心
│   ├── claude_utils.py      ← Claude API 封装
│   ├── web_scraper.py       ← Bing/HN/ArXiv 抓取
│   ├── github_trending.py   ← GitHub Trending
│   └── item_matcher.py      ← 去重精选
├── xhs_publish/             ← 📕 卡片渲染 + 发布
│   ├── render_combined.py   ← 卡片 HTML → PNG
│   ├── render_video.py      ← 视频合成
│   ├── azure_tts.py         ← TTS 旁白
│   └── publish_xiaohongshu_auto.py ← 自动发布
├── distill.py               ← YouTube 蒸馏快捷入口
├── requirements.txt
├── .env.example
├── daily/                   ← 双语日报存档 (gitignore)
├── xiaohongshu/             ← 小红书素材 (gitignore)
└── logs/                    ← 运行日志 (gitignore)
```

---

## 管道架构

```
                    ┌──────────────────┐
                    │   Claude API      │
                    │   (神经中枢)       │
                    └──────┬───────────┘
            ┌──────────────┼──────────────┐
            │              │              │
       ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
       │ 采集层   │   │ 处理层   │   │ 生成层   │
       │ 163 IMAP │   │ 翻译    │   │ HTML卡片 │
       │ Bing搜索 │   │ 精选    │   │ 封面合成 │
       │ HN/ArXiv │   │ 蒸馏    │   │ 视频合成 │
       │ yt-dlp   │   │ JSON输出│   │ TTS旁白  │
       └─────────┘   └─────────┘   └─────────┘
                                        │
                                   ┌────▼────┐
                                   │ 分发层   │
                                   │ 小红书   │
                                   │ B站视频  │
                                   │ Vercel   │
                                   │ 飞书     │
                                   └─────────┘

管道独立，中枢统一。加新平台 = 只加一个 render 脚本。
```

---

## FAQ

**Q: 一定要用 163 邮箱吗？**
A: 不用，任何支持 IMAP 的邮箱都行（Gmail、QQ、163 等）。脚本用 Python 标准库 `imaplib`，配置 IMAP 服务器地址和端口即可。YouTube 蒸馏器不需要邮箱。

**Q: 能用其他 AI 模型吗？**
A: 能。设置 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_MODEL` 即可，兼容 deepseek、OpenRouter 等所有 Anthropic-兼容 API。

**Q: 小红书自动发布失败？**
A: 大概率是 cookie 过期。运行 `python3 xhs_publish/publish_xiaohongshu_auto.py --login-only` 手动登录一次，cookie 存到 `.playwright-data/`。

**Q: Windows 能用吗？**
A: 核心 Python 代码跨平台。`crontab` 换成 Task Scheduler，yt-dlp 和 FFmpeg 有 Windows 版。

**Q: 为什么不用 anthropic SDK？**
A: `urllib.request` 直接调 HTTP API，零额外依赖，方便兼容任何后端。

---

## 从 0 到 1 的进化

最初只有两个步骤：拉取 + 翻译。后来每次遇到做了 3 遍以上的重复劳动，就加一层：

1. 拉取 + 翻译 → 能看了，但不够
2. + 外部搜索 → 邮件没到也能有内容
3. + 去重精选 → 信息源太多需要筛选
4. + HTML 卡片 → 分享需要视觉
5. + 视频生成 → 多平台需要不同格式
6. + 自动发布 → 手动传图太慢
7. + 定时调度 → 每天手动跑太累

每个管道独立可替换。你不需要从 7 条开始，从 1 条开始就够了。

---

## License

MIT
