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

# 验证清单从构建产物现取，不写死——写死的清单会随新页面悄悄过期。
#
# ⚠️ 只看 HTTP 200 是验不出东西的：这台服务器对 /dota2/ 下任何不存在的路径
# 都返回站点落地页并给 200（实测 /dota2/zzz-not-exist.html → 200）。
# 也就是说，一个页面根本没传上去，旧版的「全部 200」照样打勾——
# 新增 window.html 那次就是这么差点蒙混过去的。
# 改为拿线上内容与本地构建产物**逐字节比对**：漏页、旧版、截断一次全抓。
echo "验证：逐页与本地构建产物逐字节比对"
FAIL=0
check() {  # check <URL 路径> <本地文件>
  if curl -fsS --max-time 30 "https://shadowjacob.shop/dota2/$1" | cmp -s - "$2"; then
    printf "  /dota2/%-26s 一致\n" "$1"
  else
    printf "  /dota2/%-26s ❌ 与本地构建不一致（漏传 / 旧版 / 截断）\n" "$1"
    FAIL=1
  fi
}
for p in $(cd "$ROOT/site/dist" && ls *.html) data/site.json data/search_index.json; do
  check "$p" "$ROOT/site/dist/$p"
done
check "" "$ROOT/site/dist/index.html"   # 目录根须落到 index.html
[ "$FAIL" = "0" ] || { echo "❌ 部署未通过验证"; exit 1; }
echo "✅ 全部与本地构建逐字节一致"
