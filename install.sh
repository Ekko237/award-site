#!/usr/bin/env bash
# 把 award-site 装到本机的 Codex / Claude Code。
# 用法：bash install.sh            （自动检测装到哪个）
#       bash install.sh codex      （只装 Codex）
#       bash install.sh claude     （只装 Claude Code）
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGETS=()

case "${1:-auto}" in
  codex)  TARGETS=("$HOME/.codex/skills/award-site") ;;
  claude) TARGETS=("$HOME/.claude/skills/award-site") ;;
  auto)
    [ -d "$HOME/.codex" ]  && TARGETS+=("$HOME/.codex/skills/award-site")
    [ -d "$HOME/.claude" ] && TARGETS+=("$HOME/.claude/skills/award-site")
    ;;
  *) echo "用法: bash install.sh [codex|claude]"; exit 1 ;;
esac

if [ ${#TARGETS[@]} -eq 0 ]; then
  echo "没找到 ~/.codex 或 ~/.claude —— 先装 Codex 或 Claude Code 再跑这个脚本。"
  exit 1
fi

for DST in "${TARGETS[@]}"; do
  # 目标已存在且不是本仓库装出来的 → 先整目录备份，绝不覆盖别人的东西。
  # （典型情况：你本来就有一个同名的私人版 skill。）
  if [ -d "$DST" ] && [ ! -f "$DST/.award-site-installed" ]; then
    BAK="$DST.bak-$(date +%Y%m%d-%H%M%S)"
    cp -R "$DST" "$BAK"
    echo "⚠️  $DST 已存在且不是本仓库装的，已整份备份到："
    echo "    $BAK"
  fi

  mkdir -p "$DST"
  # 不用 --delete：目标里多出来的文件（你自己的档案、笔记）一律保留
  rsync -a \
    --exclude '.git' --exclude 'install.sh' --exclude '.DS_Store' \
    "$SRC"/ "$DST"/
  touch "$DST/.award-site-installed"
  echo "✅ 已安装到 $DST"
done

echo
echo "打开 Codex 或 Claude Code，说一句「把这个网站打磨到获奖水平」，或者用 /award-site 就会触发。"
