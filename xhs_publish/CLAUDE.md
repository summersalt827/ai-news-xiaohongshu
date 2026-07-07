# XHS Publish — 小红书格式生成与发布

## 两种发布格式

本模块支持两版小红书发布格式，按日期自动选择：

| 格式 | 触发条件 | 输出 | 模板参考 |
|------|---------|------|---------|
| **AI News 日报** | 周一至周五 | 4 张卡片 + 1 张封面 | `render_combined.py` |
| **AI Skills 深度** | 周六/周日 | 单主题长图文（多张） | `xiaohongshu/2026-06-14/xhs-skill-*` |

---

## 格式一：AI News 日报（weekday）

### 卡片结构（每张 1080×1440 @2x = 2160×2880 PNG）

```
┌─ 4px 橙色顶条 ────────────────────────┐
│  Badge: ⭐ GitHub 最新趋势 / AI 小白速览 │
│  emoji + 主标题（38px, 800 字重）       │
├───────────────────────────────────────┤
│  info-card 📰 "发生了什么？"           │
│  └─ 2-3句大白话解释                     │
├───────────────────────────────────────┤
│  info-card 🔍 "深入了解一下"            │
│  └─ 3-4句详细背景 + 数据               │
├───────────────────────────────────────┤
│  info-card 💡 "为什么值得关注"          │
│  └─ 对普通人的影响                      │
├───────────────────────────────────────┤
│  🧠 小白记住这三点                      │
│  ① ...  ② ...  ③ ...                   │
├───────────────────────────────────────┤
│  Insight Box (深色 #1a1918)            │
│  └─ KEY INSIGHT + 橙色高亮关键词        │
├───────────────────────────────────────┤
│  Footer: 来源 + NN/05 页码              │
└───────────────────────────────────────┘
```

### 封面结构（2×2 网格）

```
┌─ Hero: "今日 AI 速览" + 日期 ──────────┐
├─ 2×2 卡片网格 ─────────────────────────┤
│  Card 1 (橙 L1)  │  Card 2 (绿 L2)     │
│  Card 3 (蓝 L3)  │  Card 4 (紫 L4)     │
├───────────────────────────────────────┤
│  Insight Box                           │
├───────────────────────────────────────┤
│  Footer: tags + 日期                    │
└───────────────────────────────────────┘
```

### 输出路径

```
xiaohongshu/<YYYY-MM-DD>/
├── <date>_card_01.html / .png    ← 单张卡片
├── <date>_card_02.html / .png
├── <date>_card_03.html / .png
├── <date>_card_04.html / .png
├── <date>_cover.html / .png      ← 封面
├── <date>_caption.txt            ← 发布文案
└── <date>.jpg                    ← PIL 旧格式（兼容）
```

---

## 格式二：AI Skills 深度（weekend）

### 结构特征

- 单主题深度展开，类似教程/白皮书
- 封面 (cover.png) + 内容页 (p1/p2/p3/p4.png)
- 文案使用 markdown 格式 (`xhs-skill-caption.md`)
- 风格：步骤式引导 + 案例举证 + 金句收尾

### 文案模板（来自 xhs-skill-caption.md）

```markdown
# 小红书文案
如何从0到1搭建一个 [主题] 🤖

说一个你可能不知道的事 — [hook/悬念]

[内容分节，每节用 ─── 分隔]

🧩 第一节：概念解释

🖐️ 第二节：步骤拆解

📋 第三节：关键要素

💡 实战经验 / 金句

───────────────

总结句

右上角关注，更多 AI 实战干货在路上 🔥

#标签1 #标签2 ...
```

### 输出路径

```
xiaohongshu/<YYYY-MM-DD>/
├── xhs-skill-cover.png           ← 封面
├── xhs-skill-p1.png ~ p4.png    ← 内容页
├── xhs-skill-caption.md         ← 发布文案 (markdown)
└── xhs-skill-caption.txt        ← 发布文案 (纯文本)
```

---

## 设计规范（两版共用）

**⚠️ 尺寸铁律：所有小红书卡片永远固定 1080×1440px，截图 @2x = 2160×2880 PNG。不接受任何其他尺寸，即使参考 HTML 用了别的尺寸也忽略。**

严格遵循 `小红书发布.md` 风格指南：

| 属性 | 值 |
|------|-----|
| 宽度 | 1080px |
| 背景 | `#faf9f5`（暖白） |
| 强调色 | `#d97757`（橙色） |
| 字体 | Inter + PingFang SC |
| 卡片 | 白底、20px 圆角、`#e8e6dc` 边框 |
| Insight Box | 深色背景 `#1a1918`、橙色高亮 |
| 编号徽章 | L1 橙 / L2 绿 / L3 蓝 / L4 紫 |
| 截图 | 1080×1440 @2x = 2160×2880 PNG |

## 文件

| 文件 | 职责 |
|------|------|
| `render_combined.py` | AI News 卡片 HTML + PNG 生成 |
| `render_html.py` | 双语展示 HTML（Vercel 部署） |
| `render_xiaohongshu.py` | PIL 生成 1080×1440 单图（旧格式） |
| `publish_xiaohongshu_auto.py` | Playwright 自动上传图片+文案到创作者中心 |
| `publish_xiaohongshu.sh` | Shell 快捷发布脚本 |

## 参考风格提取流程

当拿到一张参考图片或 HTML 文件，需要把它的视觉风格迁移到小红书卡片时，严格按以下流程操作。

### Step 1：把参考图片写成 HTML 设计参考文件

这是最关键的一步——不要直接跳去改卡片。先在 `xiaohongshu/design-refs/` 下创建一个独立的 HTML 文件，**只还原参考图的视觉样式，不填真实内容**。

```
目标：产出一个可运行的 HTML，打开后能看到参考风格 1:1 还原。

做法：
1. 在浏览器打开参考图/HTML，逐一读取 CSS 属性
2. 写一个干净的 HTML，包含：
   - :root 变量（颜色、字号、间距）
   - 每个组件一个 demo 区块（title-block / compare-box / insight-box 等）
   - 用 placeholder 文字占位，不写真实内容
3. ⚠️ Canvas 尺寸用 390px 宽度还原参考图的手机比例即可
   （方便对比原图，实际卡片生成时再放大到 1080px）
4. Chrome 截图，和参考图放在一起对比确认一致性

文件路径示例：
  xiaohongshu/design-refs/claude-fable-style.html
  xiaohongshu/design-refs/claude-fable-style.png
```

### Step 2：提取设计 Token

从 Step 1 的 HTML 中提取固定变量，输出 CSS token 表：

```css
:root{
  --bg: #f4f2ee;          /* 页面底色 */
  --card: #ffffff;        /* 卡片底色 */
  --ink: #1a1a1a;         /* 主文字 */
  --soft: #6b6b6b;        /* 辅助文字 */
  --accent: #2f4bf0;      /* 强调色 */
  --line: #e7e4de;        /* 分割线 */
}
```

同时记录字号阶梯和间距阶梯：
```
字号: eyebrow 10px / label 9px / body 13px / cn-title 21px / en-title 32-46px
间距: section-gap 14-20px / card-padding 28px / element-gap 8-10px
圆角: card 2px / box 6px / tag 3px
```

### Step 3：提取组件库

从 Step 1 的 HTML 中识别并命名每个可复用组件：

| 组件 | CSS class | 样式特征 | 适用场景 |
|------|-----------|----------|----------|
| eyebrow-row | `.eyebrow-row` | 左右标签横条，10px, #9a9a9a | 页面顶部分类标识 |
| title-block | `.title-block` | 英文大标题 + 黑色下划线 | 每页主标题 |
| cn-block | `.cn-block` | 中文副标题，关键词蓝色高亮 | 标题补充说明 |
| compare-row | `.compare-row` | 2 列并排 box (cream 浅色 / accent 实色) | 对比/选择场景 |
| steps-list | `.step-item` | 圆形蓝色编号 + 文字 | 步骤流程 |
| layers | `.layer` | 编号圆 + 标题 + 灰色描述 | 层级架构 |
| sources | `.src` | emoji + 名称 + 描述行 | 输入源列表 |
| insight-blue | `.insight-blue` | accent 实色底 + 白色文字 | 核心洞察（深色模式用 insight-dark） |
| bars-row | `.bars-row` | 底部标签 + 柱状条（accent 色标识重点） | 技术栈/属性可视化 |
| pipe-tags | `.pipe-tag` | 浅色背景圆角标签 | 关键词标签组 |

### Step 4：套用生成实际卡片

现在才用提取的 token + 组件生成小红书的真实卡片：

1. **尺寸切换** — Token 不变，但 Canvas 从 390px 切换到 **1080×1440px**（固定铁律）
2. **字号等比例放大** — 参考尺寸 390px → 目标 1080px，约 2.5-2.8x。实际按视觉微调，以内容舒适为准
3. **组件拼装** — 每张卡片 = eyebrow-row + title-block + cn-block + (选择 2-4 个内容组件) + 底部收尾
4. **截图验证** — Chrome `--window-size=1080,1440 --force-device-scale-factor=2`，确认内容撑满不溢出

### 完整流程回顾

```
参考图/HTML
    │
    ▼
Step 1: 写成 HTML 设计参考文件 (390px, design-refs/ 目录)
    │
    ▼
Step 2: 提取 Token (CSS 变量 + 字号阶梯 + 间距阶梯)
    │
    ▼
Step 3: 提取组件库 (命名 + CSS class + 适用场景)
    │
    ▼
Step 4: 套用生成实际卡片 (1080×1440, 组件拼装 + 截图验证)
```

---

## 发布命令

```bash
cd ai-news-xiaohongshu

# 首次登录
python3 xhs_publish/publish_xiaohongshu_auto.py <日期> --login-only

# 日常发布
python3 xhs_publish/publish_xiaohongshu_auto.py <日期>
```

## 全流程入口

```bash
cd ai-news-xiaohongshu
python3 news_pipeline/fetch_ai_news.py
```
