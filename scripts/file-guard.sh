#!/bin/bash
# file-guard.sh - 文件保护机制（精简版）
# 功能：1)脚本缺失时自动恢复 2)执行前自动备份

GUARD_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$GUARD_DIR")"
SCRIPT="$GUARD_DIR/news_briefing.py"
BACKUP_DIR="$GUARD_DIR/backup"
LOG="$PROJECT_DIR/logs/file-guard.log"

mkdir -p "$BACKUP_DIR"

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $1" | tee -a "$LOG"; }

# === 1. 脚本缺失？自动恢复最新备份 ===
if [ ! -f "$SCRIPT" ]; then
    LATEST=$(ls -t "$BACKUP_DIR"/news_briefing.py.bak.* 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        cp "$LATEST" "$SCRIPT"
        chmod +x "$SCRIPT"
        log "⚠️ 脚本缺失，已从备份恢复: $(basename $LATEST)"
    else
        log "❌ 脚本缺失且无备份！需要手动恢复"
        exit 1
    fi
fi

# === 2. 执行前自动备份（保留最近3个版本） ===
if [ -f "$SCRIPT" ]; then
    TS=$(date +%Y%m%d_%H%M%S)
    cp "$SCRIPT" "$BACKUP_DIR/news_briefing.py.bak.$TS"
    # 清理旧备份，只保留最近3个
    ls -t "$BACKUP_DIR"/news_briefing.py.bak.* 2>/dev/null | tail -n +4 | xargs rm -f 2>/dev/null
fi

exit 0
