#!/bin/bash
# 小红书半自动发布助手
# 用法: ./publish_xiaohongshu.sh [日期] [类型]
# 示例: ./publish_xiaohongshu.sh 2026-06-04 xiaobai

set -e

DATE="${1:-$(date +%Y-%m-%d)}"
TYPE="${2:-xiaobai}"

PROJECT_DIR="/Users/heyuxian/Desktop/ai_news_translation"
IMG_DIR="${PROJECT_DIR}/xiaohongshu/${DATE}/${TYPE}"
CAPTION_FILE="${IMG_DIR}/xiaobai_caption.txt"
CREATOR_URL="https://creator.xiaohongshu.com/publish/publish"

echo "📕 小红书发布助手"
echo "  日期: ${DATE}"
echo "  类型: ${TYPE}"
echo ""

# 1. 复制文案到剪贴板
if [ -f "$CAPTION_FILE" ]; then
    cat "$CAPTION_FILE" | pbcopy
    echo "✅ 文案已复制到剪贴板"
else
    echo "⚠️  文案文件不存在: $CAPTION_FILE"
fi

# 2. 打开所有图片
PNG_COUNT=$(ls "${IMG_DIR}"/*.png 2>/dev/null | wc -l)
if [ "$PNG_COUNT" -gt 0 ]; then
    open "${IMG_DIR}"/*.png
    echo "✅ 已打开 ${PNG_COUNT} 张图片"
else
    echo "⚠️  未找到图片"
fi

# 3. 打开发布页
open "$CREATOR_URL"
echo "✅ 已打开小红书创作中心"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━"
echo "接下来手动操作:"
echo "  1. 在发布页粘贴文案 (Cmd+V)"
echo "  2. 拖入图片（按 01-04 顺序）"
echo "  3. 检查预览 → 发布"
echo "━━━━━━━━━━━━━━━━━━━━━"
