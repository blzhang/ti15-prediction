"""L2 融合脚本：市场赔率去水 + log-odds 融合，产出 model/l2_blended.json。

设计文档 §8 验收标准 1「可复现：从原始 CSV 到最终概率，一条命令跑通，
无手工步骤」在这份产出物上原本不成立——`model/l2_blended.json` 最初
（Task 2）是靠一段贴在报告里的内联 `python -c` 手打出来的，`model/` 下
没有对应脚本；后来 Task 3（瑞士轮分轮配对修正）、Task 4（双败结构+动态
让分）又都重新生成过 `model/l2_predictions.json`，`l2_blended.json` 却
一直没跟着重新融合，两者从 Task 2 起就已经不同步（task-23-report.md 有
完整的重新产出记录与新旧对照）。本脚本把这条链路固化成一条命令：

    python3 model/l2_blend.py

只做编排（读输入 → 调用 → 落盘 → 打印），融合数学全部复用
`model/market.py` 的 `blend_partial`（内部已调用 `devig`/`blend_logodds`）
与 `round_probs`，本文件不重新实现任何一步。

融合权重 `w_market` 默认取 `market.W_MARKET_DEFAULT`（0.7，设计文档 §4.2
建议区间 0.6-0.8 的中点这一份共享定义，不在本文件里重复写常量），也可以
用 `--w-market` 覆盖。

`tests/test_l2_blend.py::test_build_blend_reproduces_committed_l2_blended_json`
把"重跑这个脚本得到的结果 == 磁盘上的 model/l2_blended.json"钉成硬约束——
以后谁改了 model/l2_predictions.json 或 model/market_odds.json 却忘了重新
跑这个脚本，这条测试会直接变红。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)   # 与 l2_simulate.py/l3_player.py/emit_match_table.py 一致的裸导入 shim
from market import blend_partial, round_probs, W_MARKET_DEFAULT

DEFAULT_L2 = os.path.join(HERE, "l2_predictions.json")
DEFAULT_ODDS = os.path.join(HERE, "market_odds.json")
DEFAULT_OUT = os.path.join(HERE, "l2_blended.json")


def build_blend(l2_path=DEFAULT_L2, odds_path=DEFAULT_ODDS, w_market=W_MARKET_DEFAULT):
    """读 l2_path 的 `champion` 与 odds_path 的 `decimal_odds` → 条件去水
    融合（`blend_partial`）→ 四舍五入到 6 位小数（`round_probs`）。

    纯函数，不做任何文件写入——写盘是 `main()` 的职责，这样测试可以直接
    调用这个函数跟磁盘上已有的 `l2_blended.json` 比对，不必每次都真的
    重新落盘。返回结构与现有 `model/l2_blended.json` 的顶层字段一致：
    `{"champion_blended": {...}, "w_market": w_market}`。
    """
    model = json.load(open(l2_path))["champion"]
    odds = json.load(open(odds_path))["decimal_odds"]
    blended = blend_partial(model, odds, w_market=w_market)
    rounded = round_probs(blended, 6)

    # 设计文档口径：四舍五入后 16 个概率的和不会精确等于 1（偏差量级
    # 1e-16~1e-5），不应该为了凑整再归一化（那会把小数位又变长）——
    # 只校验偏差在文档化容差内。
    deviation = abs(sum(rounded.values()) - 1.0)
    assert deviation < 1e-5, (
        "四舍五入后概率和偏离 1 超出文档化容差：deviation=%r" % deviation
    )
    return {"champion_blended": rounded, "w_market": w_market}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--l2", default=DEFAULT_L2, help="model/l2_predictions.json 路径")
    ap.add_argument("--odds", default=DEFAULT_ODDS, help="model/market_odds.json 路径")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出路径")
    ap.add_argument("--w-market", type=float, default=W_MARKET_DEFAULT, help="市场权重，默认 0.7")
    args = ap.parse_args(argv)

    result = build_blend(l2_path=args.l2, odds_path=args.odds, w_market=args.w_market)
    champ = result["champion_blended"]

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)

    print("融合权重 w_market=%s（%s + %s）" % (args.w_market, args.l2, args.odds))
    print("%-17s%10s" % ("队", "融合后夺冠概率"))
    for team in sorted(champ, key=lambda t: -champ[t]):
        print("%-17s%9.1f%%" % (team, champ[team] * 100))
    total = sum(champ.values())
    print("\n合计：%.10f（偏差 |sum-1|=%.2e，应 < 1e-5）" % (total, abs(total - 1.0)))
    print("\n→ 写入 %s" % args.out)
    return result


if __name__ == "__main__":
    main()
