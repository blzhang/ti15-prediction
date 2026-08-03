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

ssh "$HOST" "set -e
TS=\$(date -u +%Y%m%dT%H%M%SZ)
[ -d '$DST' ] && cp -a '$DST' '${DST}.bak-'\$TS
mkdir -p '$DST' && rm -rf '$DST'/*
tar xzf /tmp/dota2-site.tgz -C '$DST'
find '$DST' \\( -name '._*' -o -name '.DS_Store' \\) -delete
chown -R root:root '$DST'
find '$DST' -type d -exec chmod 755 {} \;
find '$DST' -type f -exec chmod 644 {} \;
rm -f /tmp/dota2-site.tgz
echo \"部署完成，\$(find '$DST' -type f | wc -l) 个文件\""

echo "验证："
for p in "" predictions.html methodology.html data.html data/search_index.json; do
  printf "  /dota2/%-26s %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code}' "https://shadowjacob.shop/dota2/$p")"
done
