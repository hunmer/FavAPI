#!/usr/bin/env bash
# 构建便携包：PyInstaller onedir + platforms 资源 + Playwright chromium 内核
# 产物：dist/FavAPI/（整目录拷走即可运行，无需 Python 环境）
# 依赖：web 前端已构建（web/dist 存在）；chromium 已下载（.venv/bin/python -m playwright install chromium）
set -euo pipefail
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
[ -x "$PY" ] || PY=".venv/Scripts/python.exe"  # Windows 兼容

if [ ! -f "web/dist/index.html" ]; then
  echo "错误：web/dist 不存在，先执行 cd web && npm install && npm run build" >&2
  exit 1
fi

"$PY" -m PyInstaller --version >/dev/null 2>&1 || "$PY" -m pip install pyinstaller

echo "==> PyInstaller 打包"
"$PY" -m PyInstaller FavAPI.spec --noconfirm

OUT="dist/FavAPI"

echo "==> 复制声明式平台资源"
rm -rf "$OUT/platforms"
cp -R platforms "$OUT/platforms"

echo "==> 复制 Playwright chromium 内核（便携包内自带，不依赖用户缓存）"
BROWSERS_JSON=$("$PY" - <<'EOF'
import json, os, playwright
p = os.path.join(os.path.dirname(playwright.__file__), "driver", "package", "browsers.json")
revs = {b["name"]: b["revision"] for b in json.load(open(p, encoding="utf-8"))["browsers"]}
print(revs["chromium"], revs.get("ffmpeg", ""))
EOF
)
CHROMIUM_REV=$(echo "$BROWSERS_JSON" | cut -d' ' -f1)
FFMPEG_REV=$(echo "$BROWSERS_JSON" | cut -d' ' -f2)
CACHE="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"
[ -d "$CACHE" ] || CACHE="$HOME/.cache/ms-playwright"

rm -rf "$OUT/pw-browsers"
mkdir -p "$OUT/pw-browsers"
if [ -d "$CACHE/chromium-$CHROMIUM_REV" ]; then
  cp -R "$CACHE/chromium-$CHROMIUM_REV" "$OUT/pw-browsers/"
else
  echo "警告：缓存缺 chromium-$CHROMIUM_REV，先执行 $PY -m playwright install chromium" >&2
fi
[ -z "$FFMPEG_REV" ] || [ ! -d "$CACHE/ffmpeg-$FFMPEG_REV" ] || cp -R "$CACHE/ffmpeg-$FFMPEG_REV" "$OUT/pw-browsers/"

if [ "$(uname)" = "Darwin" ]; then
  echo "==> ad-hoc 签名（避免本机以外机器被 Gatekeeper 拦截）"
  codesign --force --deep --sign - "$OUT/FavAPI" >/dev/null 2>&1 || true
fi

echo "==> 完成：$OUT"
du -sh "$OUT"
