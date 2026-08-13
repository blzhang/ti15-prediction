#!/usr/bin/env bash
# 赛程推进后的一键重算：把新打完的比赛填进 model/results.json，然后跑这个。
#
# 用法：
#   1. 编辑 model/results.json：把新打完的系列赛加上 score（[A 局数, B 局数]），
#      新排定但还没打的对阵只写 a/b、不写 score，并更新 as_of_utc
#   2. bash site/rebuild-with-results.sh          # 全流程，最后会问一次要不要部署
#      bash site/rebuild-with-results.sh --dry    # 只算不部署，先看结果
#
# ⚠️ 正在进行中的系列赛不要填当前比分——填了会被当成最终结果。model/results.py
#    会拦下 1-1 这种非终局比分并报错，但 2-0 的「其实还没打完」它拦不住。
#
# 与 rebuild-with-draw.sh 的关系：那个是「分组公布后」用的，这个是「打完几轮后」用的。
# 现在分组这件事已经由 results.json 接管（每多打一轮，候选分组自动收紧），
# 所以常规重算走这个脚本。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DRY=0
[ "${1:-}" = "--dry" ] && DRY=1

step() { printf "\n\033[1m▸ %s\033[0m\n" "$1"; }

step "1/8 校验已完赛数据与分组约束"
# 先单独校验一次再动全流程：填错就在这里停，不会白跑两分钟模拟。
python3 - <<'PY'
import json, sys
sys.path.insert(0, "model")
import draw as d, results as r
teams = list(json.load(open("model/l1_rating.json"))["rating"])
print(d.describe(d.load(teams), teams))
print()
got = r.load(teams)                      # 不合法会抛 ResultsError
print(r.describe(got, teams))
if not got:
    print("\n⚠️  results.json 还是「未启用」状态（active=false 或文件缺失）。")
    print("    现在跑下去只会重算出与赛前一模一样的结果。")
    sys.exit(2)
PY

step "2/8 抓最新市场价（Polymarket 实时）"
# 抓不到不算致命：市场价可以沿用上一份快照，但必须让人看见它没更新。
python3 fetch_polymarket.py || echo "  ⚠️  抓取失败，沿用磁盘上已有的 polymarket_odds.json（时间戳不会变，注意核对）"

step "3/8 蒙特卡洛模拟（20 万届，约 2 分钟）"
python3 -m model.l2_simulate

step "4/8 与市场共识融合"
python3 -m model.l2_blend

step "5/8 回填赛前对账表并打分"
python3 -m model.backfill_results

step "6/8 重出下游报告（梦幻挑战 / 极值题依赖瑞士轮场次分布）"
python3 -m model.l4_fantasy_report
python3 -m model.l4_extremes_report

step "7/8 冻结存证"
# 关键：**新增**一版，不覆盖任何旧版。赛前那版是「什么都没打时的预测」，
# 每一版在途预测是「打了 N 场之后的预测」，赛后要分开打分——
# 拿在途预测冒充赛前预测，是这个项目最不能犯的错。
python3 - <<'PY'
import json, sys
sys.path.insert(0, "model")
from freeze import freeze_predictions
n = json.load(open("model/l2_predictions.json"))["results"]["n_series_done"]
tag = "v-inplay-%02d" % n          # 用「已完赛场次」做版本号，天然递增且自解释
for src in ("model/l2_predictions.json", "model/l2_blended.json",
            "model/results.json", "reports/ti15_matches.csv"):
    label = "%s-%s" % (tag, src.split("/")[-1].split(".")[0])
    try:
        freeze_predictions(src, "frozen", label)
        print("  冻结 %s" % label)
    except FileExistsError:
        print("  已存在，跳过：%s（同一场次数重复跑不会覆盖旧证据）" % label)
PY

step "8/8 重建站点与长图"
python3 site/build_site.py
python3 site/make_cards.py

if [ "$DRY" = "1" ]; then
  echo "  --dry：跳过部署。产物在 site/dist/ 与 site/cards/，可先本地看过再手动跑 bash site/deploy.sh"
  exit 0
fi
read -r -p "  以上结果确认无误，部署到 shadowjacob.shop/dota2？[y/N] " ok
case "$ok" in
  [yY]*) bash site/deploy.sh ;;
  *) echo "  已取消。产物留在 site/dist/，随时可跑 bash site/deploy.sh" ;;
esac
