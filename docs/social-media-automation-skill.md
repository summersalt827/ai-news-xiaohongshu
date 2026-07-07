# 🤖 AI 社媒自动化全流程 Skill

## 总览

一个 Python 脚本驱动 7 条自动化管道，从邮件拉取到多平台发布全链路 AI 化。

---

## 架构全景

```
                              ┌──────────────────────────────────────┐
                              │          🤖 Claude API 中枢           │
                              │   deepseek-v4-pro[1m] · 翻译·精选·蒸馏  │
                              └──────────┬───────────────────────────┘
                                         │
        ┌────────────┬──────────┬────────┼──────────┬──────────┬────────────┐
        ▼            ▼          ▼        ▼          ▼          ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌──────┐ ┌──────┐ ┌─────────┐ ┌──────┐ ┌──────────┐
   │📥 邮件   │ │🌐 全网  │ │📊 GitHub│ │🎬   │ │📝 内容  │ │📸 截图│ │🚀 发布   │
   │  拉取   │ │  抓取   │ │Trending│ │YouTube│ │  生成   │ │  渲染 │ │  部署    │
   └────┬────┘ └────┬────┘ └──┬───┘ └──┬───┘ └────┬────┘ └──┬───┘ └────┬─────┘
        │          │         │        │          │         │          │
        ▼          ▼         ▼        ▼          ▼         ▼          ▼
     163 IMAP   Bing       GitHub   yt-dlp    HTML卡片  Playwright  小红书API
    4个文件夹   HN        Search   Whisper   暖白设计  Chrome       B站API
    [AINews]   Twitter/X   API     字幕      1080×1440  @2x         Vercel
    过滤        ArXiv      24h⭐                @2x       PNG        飞书推送
               媒体博客
```

---

## 7 条自动化管道

### 📬 Pipeline 1 — AI News 日报（周一至周五）

```
163 邮箱 ──→ IMAP 搜索 [AINews] ──→ Claude 翻译 ──→ 全网抓取(Bing+HN+X+ArXiv)
                                                         │
   ┌─────────────────────────────────────────────────────┘
   ▼
Claude 精选 4 条 AI 新闻 + 1 条 GitHub Trending
   │
   ▼
生成 HTML 卡片 (1080×1440 @2x) ──→ Playwright 截图 PNG
   │
   ▼
自动上传 小红书创作者中心 + 飞书推送 + Vercel 部署
```

| 步骤 | 工具 | 耗时 |
|------|------|------|
| 拉取 | Python imaplib | ~3s |
| 翻译 | Claude API (deepseek-v4-pro) | ~15s |
| 抓取 | `web_scraper.py` (Bing/HN/X/ArXiv) | ~10s |
| 精选 | `item_matcher.py` (Claude) | ~20s |
| 生成 | `render_combined.py` (HTML) | ~5s |
| 截图 | Playwright headless Chrome | ~8s |
| 发布 | `publish_xiaohongshu_auto.py` | ~30s |
| **总计** | | **~90s** |

---

### 📝 Pipeline 2 — AI Skills 深度（周六/周日）

```
全网抓取 + 邮件内容 ──→ Claude 选深度话题 ──→ 生成多页长图文
                                                   │
                          ┌────────────────────────┘
                          ▼
                    cover.png + p1~p4.png + caption.md
                          │
                          ▼
                    自动发布 小红书
```

**格式**：概念解释 → 步骤拆解 → 关键要素 → 实战金句

---

### 🎬 Pipeline 3 — YouTube → 小红书

```
YouTube URL ──→ yt-dlp 自动字幕 ──→ Claude 蒸馏 4 张卡片 JSON ──→ HTML → 截图 → 发布
                    │
                    └── (fallback) Audio → Whisper 转写 → 文本 → Claude 蒸馏
```

| 模式 | 速度 | 精度 |
|------|------|------|
| 字幕模式 | ~5s | 高（原文） |
| Whisper 模式 | ~60s | 中（转写有损） |

---

### 🎥 Pipeline 4 — 视频生成（小红书 + B站）

```
卡片 PNG ──→ FFmpeg 合成视频 ──→ Azure/Zhipu TTS 旁白 ──→ 混入 BGM ──→ 双平台发布
                                              │
                            ┌─────────────────┘
                            ▼
                    render_video.py → .mp4
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
         render_h1_video.py     render_h1_bilibili.py
         小红书 3:4 竖版           B站 16:9 横版
```

---

### 🔄 Pipeline 5 — 飞书 + Vercel 同步

```
每日输出 ──→ Markdown 存档 (daily/) ──→ 双语 HTML ──→ Vercel 部署
                │                                        │
                └── 飞书 Webhook ──→ 推送摘要+链接        └── claude-test.vercel.app
```

---

### 🗂️ Pipeline 6 — 外部聚合增强

```
Bing → "AI news today" → 抓取前10条 → 提取正文
HN  → Algolia API → 前30条 → 过滤 tech/AI 相关
X   → Nitter 镜像 → Bing fallback → 热门 AI 讨论
ArXiv → Atom XML → cs.AI / cs.CL → 最新论文标题摘要
GitHub → Search API → 24h stars → 增速最快仓库
```

---

### 📅 Pipeline 7 — 定时调度

```
macOS launchd ──→ 工作日 08:00 自动触发
                      │
                      ▼
              fetch_ai_news.py
                      │
                      ▼
              ┌──── 全流程一键跑完 ────┐
              │  拉取→翻译→抓取→精选    │
              │  →生成→截图→发布→推送   │
              └──────────────────────┘
```

---

## 技术栈

| 层 | 技术 |
|------|------|
| AI 引擎 | Claude API (deepseek-v4-pro[1m]) |
| 邮件 | Python imaplib → 163.com |
| 抓取 | Bing/HTML解析, HN/Algolia API, ArXiv/Atom, GitHub/Search API |
| 翻译 | Claude 中英互译，保留 Markdown 格式 |
| 精选 | Claude 从 30+ 信息源中挑 4 条 + 1 GitHub 项目 |
| 渲染 | HTML/CSS (暖白设计系统) → Playwright @2x 截图 |
| 视频 | FFmpeg + Azure TTS + Mixkit BGM |
| 语音 | Azure TTS (主) / 智谱 TTS (备) / Whisper (转写) |
| 发布 | Playwright 模拟点击上传小红书 |
| 部署 | Vercel 自动部署静态 HTML |
| 推送 | 飞书 Webhook |
| 调度 | macOS launchd 工作日定时 |

---

## 一句话总结

> 说"AI news" → 1分半后小红书自动更新。全程无人值守，AI 从收邮件跑到发布。
