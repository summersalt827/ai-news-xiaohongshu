# Style Reference Skill

当用户在小红书或其他平台看到好的卡片/封面样式，截图发给你并说「参考这个样式」时，执行以下流程。

## 触发词

- "参考这个样式"
- "学习这个风格"
- "用这个风格套到 X 内容上"
- "提取这个设计"

## 工作流

### Step 1: 提取设计 Token

用户提供截图（或 URL），从截图中提取以下信息：

```css
:root {
  --bg: #xxx;           /* 页面底色 */
  --card: #xxx;         /* 卡片底色 */
  --ink: #xxx;          /* 主文字色 */
  --soft: #xxx;         /* 辅助文字色 */
  --accent: #xxx;       /* 强调色 */
  --line: #xxx;         /* 分割线色 */
}
```

同时提取：
- **字号阶梯**: eyebrow / label / body / cn-title / en-title / big-number
- **间距阶梯**: section-gap / card-padding / element-gap
- **圆角**: card / box / tag
- **字体**: 如果有特殊字体，注明 fallback

### Step 2: 识别组件

从截图中识别每个 UI 组件，命名并描述：

| 组件 | 样式特征 | 适用场景 |
|------|---------|----------|
| eyebrow-row | 顶部标签横条 | 分类/编号标识 |
| title-block | 英文大标题+下划线 | 每页主标题 |
| cn-block | 中文副标题+关键词色 | 标题补充 |
| compare-box | 2列对比浅色/实色 | Before/After |
| steps-list | 圆形编号+文字 | 步骤/流程 |
| insight-box | 分割线+金句 | 核心洞察 |

### Step 3: 生成设计参考 HTML

在 `xiaohongshu/design-refs/` 目录创建 HTML 文件：

```
文件名: <style-name>.html
尺寸: 390px 宽度 (还原参考图的手机比例，方便对比原图)
内容: 用 placeholder 文字还原每个组件，不填真实内容
```

生成后用 Chrome headless 截图对比确认。

### Step 4: 套用到实际内容

用户说「用这个套到 X 内容上」时：
1. 从 Step 3 提取的 token + 组件库出发
2. Canvas 从 390px 切换到 **1080×1440px**（铁律）
3. 字号按比例放大（约 2.5-2.8x），实际以内容舒适为准
4. 用已有内容数据（JSON 格式的卡片数据）填充组件
5. 渲染 @2x PNG

## 设计参考目录

```
xiaohongshu/design-refs/
├── claude-fable-style.html     ← 参考样式 HTML (390px)
├── claude-fable-style.png      ← 参考样式截图
├── ...
```

## 示例对话

```
用户: [截图] 参考这个样式
Claude: 提取设计 token → 识别 6 个组件 → 生成 design-refs/minimal-tech.html

用户: 用这个套到今天的 AI News
Claude: 读 token + 组件 → 1080×1440 → 套卡片数据 → 渲染 PNG
```
