#!/usr/bin/env bash
# 构建并部署到 https://shadowjacob.shop/dota2
# 用法: bash site/deploy.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${TI15_SITE_HOST:-vultr}"
DST="/var/www/shadowjacob.shop/dota2"

python3 "$ROOT/site/build_site.py"

TGZ="$(mktemp -t dota2site).tgz"
# COPYFILE_DISABLE=1 防止 macOS 打出 ._ AppleDouble 伪文件
COPYFILE_DISABLE=1 tar czf "$TGZ" -C "$ROOT/site/dist" .
scp -q "$TGZ" "$HOST:/tmp/dota2-site.tgz"
rm -f "$TGZ"

# ⚠️ 不做 rm -rf：这个目录里可能有本仓库构建产物之外的页面
# （例如另一个 session 部署的 homework.html）。初版直接 rm -rf 会把它们
# 静默删掉——差点真的删了。现在改为覆盖式部署，并把"存在但不属于本次
# 构建"的文件列出来供人工判断，绝不自动删。
ssh "$HOST" "set -e
TS=\$(date -u +%Y%m%dT%H%M%SZ)
[ -d '$DST' ] && cp -a '$DST' '${DST}.bak-'\$TS
mkdir -p '$DST'
BEFORE=\$(cd '$DST' && find . -type f | sort)
tar xzf /tmp/dota2-site.tgz -C '$DST'
NEW=\$(tar tzf /tmp/dota2-site.tgz | grep -v '/\$' | sed 's|^\./||' | sort)
find '$DST' \\( -name '._*' -o -name '.DS_Store' \\) -delete
chown -R root:root '$DST'
find '$DST' -type d -exec chmod 755 {} \;
find '$DST' -type f -exec chmod 644 {} \;
rm -f /tmp/dota2-site.tgz
ORPHAN=\$(comm -23 <(echo \"\$BEFORE\" | sed 's|^\./||') <(echo \"\$NEW\") | grep -v '^\$' || true)
echo \"部署完成，\$(find '$DST' -type f | wc -l) 个文件\"
if [ -n \"\$ORPHAN\" ]; then
  echo '⚠️  以下文件不属于本次构建，已保留未删除：'
  echo \"\$ORPHAN\" | sed 's|^|     |'
fi"

echo "验证："
for p in "" predictions.html methodology.html data.html data/search_index.json; do
  printf "  /dota2/%-26s %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code}' "https://shadowjacob.shop/dota2/$p")"
done
