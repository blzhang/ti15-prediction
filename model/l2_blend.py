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

2026-08-05 起改为两级融合（docs/superpowers/specs/2026-08-05-polymarket-
integration-design.md）：第一级 blend_partial(Polymarket 16 队概率,
庄家 5 队赔率, w_book=0.5) 得市场共识价——庄家只影响它开过盘的 5 队内部
排序，5 队与其余 11 队的质量分配由全覆盖的 Polymarket 决定；第二级
blend_logodds(模型, 共识, w_market=0.7)。融合数学仍全部来自 market.py。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)   # 与 l2_simulate.py/l3_player.py/emit_match_table.py 一致的裸导入 shim
from market import (
    blend_logodds, blend_partial, normalize, round_probs,
    W_BOOK_DEFAULT, W_MARKET_DEFAULT,
)

DEFAULT_L2 = os.path.join(HERE, "l2_predictions.json")
DEFAULT_ODDS = os.path.join(HERE, "market_odds.json")
DEFAULT_PM = os.path.join(HERE, "polymarket_odds.json")
DEFAULT_OUT = os.path.join(HERE, "l2_blended.json")


def build_blend(l2_path=DEFAULT_L2, odds_path=DEFAULT_ODDS, pm_path=DEFAULT_PM,
                w_book=W_BOOK_DEFAULT, w_market=W_MARKET_DEFAULT):
    """两级融合，纯函数不写盘（写盘是 main() 的职责）。

    第一级：市场共识 = blend_partial(Polymarket 概率, 庄家赔率, w_book)
    第二级：最终概率 = blend_logodds(模型概率, 共识, w_market)

    返回 {"champion_blended", "w_market", "market_consensus", "sources"}；
    前两个字段与旧版结构一致（站点在读），后两个是本次新增的出处块。
    """
    model = json.load(open(l2_path))["champion"]
    book = json.load(open(odds_path))
    pm = json.load(open(pm_path))

    pm_probs = normalize({t: rec["mid"] for t, rec in pm["prices"].items()})
    if set(pm_probs) != set(model):
        raise ValueError(
            "Polymarket 与模型的队伍集合不一致，只在一侧出现：%s"
            % sorted(set(pm_probs) ^ set(model)))

    consensus = blend_partial(pm_probs, book["decimal_odds"], w_market=w_book)
    blended = blend_logodds(model, consensus, w_market)
    rounded = round_probs(blended, 6)

    # 口径不变：四舍五入后不重新归一化，只校验偏差在文档化容差内
    deviation = abs(sum(rounded.values()) - 1.0)
    assert deviation < 1e-5, (
        "四舍五入后概率和偏离 1 超出文档化容差：deviation=%r" % deviation)
    return {
        "champion_blended": rounded,
        "w_market": w_market,
        "market_consensus": round_probs(consensus, 6),
        "sources": {
            "book": {
                "file": os.path.basename(str(odds_path)),
                "captured_utc": book.get("captured_utc"),
                "teams_priced": sum(1 for v in book["decimal_odds"].values() if v),
            },
            "polymarket": {
                "file": os.path.basename(str(pm_path)),
                "captured_utc": pm.get("captured_utc"),
                "event_slug": pm.get("event_slug"),
                "teams_priced": len(pm_probs),
            },
            "w_book": w_book,
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--l2", default=DEFAULT_L2, help="model/l2_predictions.json 路径")
    ap.add_argument("--odds", default=DEFAULT_ODDS, help="model/market_odds.json 路径")
    ap.add_argument("--pm", default=DEFAULT_PM, help="model/polymarket_odds.json 路径")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出路径")
    ap.add_argument("--w-book", type=float, default=W_BOOK_DEFAULT,
                    help="共识价里庄家一侧的权重，默认 0.5（0=纯 Polymarket）")
    ap.add_argument("--w-market", type=float, default=W_MARKET_DEFAULT,
                    help="市场共识对模型的权重，默认 0.7")
    args = ap.parse_args(argv)

    result = build_blend(l2_path=args.l2, odds_path=args.odds, pm_path=args.pm,
                         w_book=args.w_book, w_market=args.w_market)
    champ = result["champion_blended"]

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)

    print("两级融合：w_book=%s，w_market=%s" % (args.w_book, args.w_market))
    print("输入：%s + %s + %s" % (args.l2, args.odds, args.pm))
    print("%-17s%12s%14s" % ("队", "市场共识", "融合后夺冠概率"))
    cons = result["market_consensus"]
    for team in sorted(champ, key=lambda t: -champ[t]):
        print("%-17s%11.1f%%%13.1f%%" % (team, cons[team] * 100, champ[team] * 100))
    total = sum(champ.values())
    print("\n合计：%.10f（偏差 |sum-1|=%.2e，应 < 1e-5）" % (total, abs(total - 1.0)))
    print("\n→ 写入 %s" % args.out)
    return result


if __name__ == "__main__":
    main()
