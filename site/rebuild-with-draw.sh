#!/usr/bin/env bash
# 分组公布后的一键重算：校验分组 → 重跑模拟 → 融合市场 → 重出报告 → 冻结存证 → 建站 → 部署
#
# 用法：
#   1. 编辑 model/draw.json：announced 改 true，填 group_a / group_b（各 8 队），
#      官方若同时公布首轮对阵就填 round1，没公布留空数组
#   2. bash site/rebuild-with-draw.sh          # 全流程，最后会问一次要不要部署
#      bash site/rebuild-with-draw.sh --dry    # 只算不部署，先看结果
#
# 为什么要有这个脚本：分组大概率在 8/12 晚到 8/13 早才公布，而预测面板
# 8/13 10:00 就锁。那个窗口里不该有人现改代码——所有决定都提前做完，
# 到时候只填两个数组、跑一条命令。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DRY=0
[ "${1:-}" = "--dry" ] && DRY=1

step() { printf "\n\033[1m▸ %s\033[0m\n" "$1"; }

step "1/7 校验分组配置"
# 先单独校验一次再动全流程：填错就在这里停，不会白跑两分钟模拟。
python3 - <<'PY'
import json, os, sys
sys.path.insert(0, "model")
import draw as d
teams = list(json.load(open("model/l1_rating.json"))["rating"])
got = d.load(teams)                      # 不合法会抛 DrawError
print(d.describe(got, teams))
if not got:
    print("\n⚠️  draw.json 还是「未公布」状态。")
    print("    现在跑下去只会重算出与线上一模一样的结果，没有意义。")
    print("    请先编辑 model/draw.json：announced 改成 true，并填好两个组。")
    sys.exit(2)
PY

step "2/7 蒙特卡洛模拟（20 万届，约 2 分钟）"
python3 -m model.l2_simulate

step "3/7 与市场共识融合"
python3 -m model.l2_blend

step "4/7 重出下游报告（梦幻挑战 / 极值题依赖瑞士轮场次分布）"
python3 -m model.l4_fantasy_report
python3 -m model.l4_extremes_report

step "5/7 冻结存证"
# 关键：这是**新增**一版，不是覆盖赛前那版。
# 整个项目的立身之本是「赛前冻结 + 哈希存证」，把原始版本改掉等于自毁信用。
# 两版都留着，赛后可以分别打分——原始版是「什么都不知道时的预测」，
# 这一版是「知道分组后的预测」，对比本身就是有价值的结果。
python3 - <<'PY'
import sys
sys.path.insert(0, "model")
from freeze import freeze_predictions
for src, label in (("model/l2_predictions.json", "v7-postdraw-predictions"),
                   ("model/l2_blended.json",     "v7-postdraw-blended")):
    rec = freeze_predictions(src, "frozen", label)
    print("  冻结 %s" % label)
PY

step "6/7 重建站点"
python3 site/build_site.py

step "7/7 部署"
if [ "$DRY" = "1" ]; then
  echo "  --dry：跳过部署。产物在 site/dist/，可先本地看过再手动跑 bash site/deploy.sh"
  exit 0
fi
read -r -p "  以上结果确认无误，部署到 shadowjacob.shop/dota2？[y/N] " ok
case "$ok" in
  [yY]*) bash site/deploy.sh ;;
  *) echo "  已取消。产物留在 site/dist/，随时可跑 bash site/deploy.sh" ;;
esac
