# AI News 小红书发布工作流

从 163 邮箱抓取 AI 新闻邮件 → 中英翻译 → 生成小红书图文 → 一键发布。

## 项目结构

```
ai_news_translation/
├── fetch_ai_news.py          # 主脚本：抓邮件 + 翻译 + 生成
├── render_html.py            # HTML 展示页生成
├── render_xiaohongshu.py     # 小红书图文生成（PIL 版）
├── publish_xiaohongshu.sh    # 小红书一键发布助手
├── .env.example              # 环境变量模板
├── daily/                    # 每日翻译输出（gitignore）
├── xiaohongshu/              # 小红书图片输出（gitignore）
└── logs/                     # 日志（gitignore）
```

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的邮箱、API Key 等
```

### 2. 安装依赖

```bash
pip install pillow anthropic
```

### 3. 运行翻译

```bash
python3 fetch_ai_news.py
```

输出：
- `daily/YYYY-MM-DD.md` — 中英对照 Markdown
- `daily/YYYY-MM-DD.html` — 线上展示页
- `xiaohongshu/YYYY-MM-DD/` — 小红书图文

### 4. 生成小红书图片（AI 小白版）

从当日翻译中精选 4 条 AI 小白友好新闻，扩写为独立图文：

```
帮我生成小红书图片
```

Claude Code 会自动执行：
1. **选材** — 从当日 8 条新闻中挑 4 条易懂的
2. **扩写** — 补充背景知识 + 数据对比 + 三点总结
3. **生成 HTML** — 套用暖白配色设计系统（1080×1440）
4. **截图** — Chrome headless @2x 输出高清图
5. **写文案** — 带标题 + 摘要 + 话题标签的发布文案

### 5. 一键发布

```bash
./publish_xiaohongshu.sh 2026-06-04
```

自动完成：复制文案到剪贴板 → 打开图片 → 打开小红书创作中心。

## 设计系统

小红书图片采用统一设计规范：

| 属性 | 值 |
|------|-----|
| 尺寸 | 1080 × 1440 (3:4) |
| 背景 | `#faf9f5` 暖白 |
| 强调色 | `#d97757` 橙色 |
| 字体 | Inter + PingFang SC |
| 卡片 | 白底 + `#e8e6dc` 边框 + 18-20px 圆角 |
| 深色块 | `#1a1918` 背景 + 橙色高亮关键词 |

## 定时运行

macOS launchd 定时任务（工作日早上）：

```bash
# 编辑 plist 中的路径后
cp com.ai-news.fetch.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ai-news.fetch.plist
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `EMAIL_163_USER` | 是 | 163 邮箱地址 |
| `EMAIL_163_PASS` | 是 | 163 IMAP 授权码 |
| `ANTHROPIC_API_KEY` | 是 | Claude/DeepSeek API Key |
| `ANTHROPIC_BASE_URL` | 否 | API 代理地址 |
| `ANTHROPIC_MODEL` | 否 | 模型名，默认 deepseek-v4-pro |
| `FEISHU_WEBHOOK` | 否 | 飞书机器人 Webhook |
| `VERCEL_URL` | 否 | Vercel 部署域名 |

## 163 邮箱文件夹映射

| IMAP 名称 | 中文 |
|-----------|------|
| INBOX | 收件箱 |
| `&Xn9USpCuTvY-` | 广告邮件 |
| `&i6KWBZCuTvY-` | 订阅邮件 |
| `&V4NXPpCuTvY-` | 垃圾邮件 |

脚本默认搜索以上 4 个文件夹中标题含 `[AINews]` 的邮件。

## License

MIT
