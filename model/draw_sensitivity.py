"""分组敏感度：知道抽签结果，到底能让预测「准多少」？

抄作业页上写着「等公布之后我会重算一版，那版会准不少」。这个脚本量化
那句话——如果重算后建议填法根本不变，那句承诺就得改口径，不能让读者
以为会有大变化。

做法：随机抽若干种可能的分组，各跑一遍模拟，看两件事——
  1. 各队分档概率摆动多大
  2. **建议填法有没有变**（这才是抄作业页真正交付的东西）

用法：
    python3 -m model.draw_sensitivity            # 默认 8 种分组 × 5 万次
    python3 -m model.draw_sensitivity 12 30000   # 自定义
"""
import collections
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "site"))

from l2_simulate import TEAMS, TH, SE, n, run_one     # noqa: E402
import homework                                        # noqa: E402

STRENGTH = json.load(open(os.path.join(HERE, "l1_rating.json")))["rating"]


def simulate(group_vec, n_sim, seed):
    """按给定分组跑 n_sim 次，返回 record_dist / 附加轮生还率，形状与 l2_predictions 一致。"""
    rng = np.random.default_rng(seed)
    drawn = {"group_vec": group_vec, "r1_pairs": None} if group_vec else None
    rec_dist = [collections.Counter() for _ in range(n)]
    surv = np.zeros(n); out = np.zeros(n)
    series = np.zeros(n); pseries = np.zeros(n)
    for _ in range(n_sim):
        theta = TH + SE * rng.standard_normal(n)
        rec, _sr, _pl, _adv, g_s, p_s, ew, el = run_one(theta, rng, drawn)
        for t in range(n):
            rec_dist[t]["%d-%d" % rec[t]] += 1
        for t in ew: surv[t] += 1
        for t in el: out[t] += 1
        series += g_s; pseries += p_s
    return {
        "record_dist": {TEAMS[t]: {k: v / n_sim for k, v in rec_dist[t].items()} for t in range(n)},
        "elim_round_survive": {TEAMS[t]: surv[t] / n_sim for t in range(n)},
        "elim_round_out": {TEAMS[t]: out[t] / n_sim for t in range(n)},
        "series_dist": {TEAMS[t]: {"group": series[t] / n_sim, "playoff": pseries[t] / n_sim}
                        for t in range(n)},
    }


def answer_key(pred):
    """把建议填法压成一个可比较的字符串。"""
    a = homework.compute(pred, STRENGTH)["answer"]
    parts = []
    for slot in sorted(a):
        v = a[slot]
        names = [v] if isinstance(v, str) else [x[0] if isinstance(x, (list, tuple)) else x for x in v]
        parts.append(slot + "=" + ",".join(sorted(names)))
    return " | ".join(parts), homework.compute(pred, STRENGTH)["expected_correct"]


def main(n_draws=6, n_sim=50000):
    """必须带噪声对照组，否则结论是错的。

    第一版没有对照组，直接拿「不同分组下建议填法变了几次」下结论，结果是
    「7/8 变了 → 分组很重要」。但跑了对照才发现：**条件完全相同、只换随机
    种子，建议填法照样会变**——因为淘汰赛胜者那 5 格在前八队之间只差
    1.9pp，本来就是近似平局，谁进谁出高度依赖抽样噪声。
    所以判据不能是「填法变没变」，必须是「分组带来的差异有没有超过噪声」。
    """
    rng = np.random.default_rng(2026)
    print("分组敏感度：噪声对照 %d 次 + 随机分组 %d 种，每次 %s 模拟\n"
          % (n_draws, n_draws, format(n_sim, ",")))

    # —— 对照组：都不给分组，只换种子。测的是纯蒙特卡洛噪声 ——
    print("【对照组】条件相同，只换随机种子（此处的波动全部是噪声）")
    ctl_ans, ctl_exp = collections.Counter(), []
    for i in range(n_draws):
        a, e = answer_key(simulate(None, n_sim, 900 + i))
        ctl_ans[a] += 1; ctl_exp.append(e)
        print("  第 %d 次  期望答对 %.3f 格" % (i + 1, e))
    ctl_spread = max(ctl_exp) - min(ctl_exp)
    print("  → 噪声下期望答对区间 %.3f–%.3f（幅度 %.3f 格），"
          "出现 %d 种不同填法\n" % (min(ctl_exp), max(ctl_exp), ctl_spread, len(ctl_ans)))

    # —— 实验组：每次换一种真实可能的分组 ——
    print("【实验组】每次换一种分组")
    p40 = collections.defaultdict(list)
    exp_ans, exps = collections.Counter(), []
    for i in range(n_draws):
        gv = list(rng.permutation([0] * 8 + [1] * 8))
        r = simulate(gv, n_sim, 1000 + i)
        a, e = answer_key(r)
        exp_ans[a] += 1; exps.append(e)
        for t in TEAMS:
            p40[t].append(r["record_dist"][t].get("4-0", 0) * 100)
        print("  分组 %d  期望答对 %.3f 格" % (i + 1, e))
    exp_spread = max(exps) - min(exps)
    print("  → 换分组下期望答对区间 %.3f–%.3f（幅度 %.3f 格），"
          "出现 %d 种不同填法\n" % (min(exps), max(exps), exp_spread, len(exp_ans)))

    print("【4-0 概率在不同分组下的摆动】")
    print("  %-17s %7s %7s %7s" % ("队", "最低", "最高", "极差"))
    for t in sorted(TEAMS, key=lambda t: -(max(p40[t]) - min(p40[t]))):
        print("  %-17s %6.1f%% %6.1f%% %6.1fpp"
              % (t, min(p40[t]), max(p40[t]), max(p40[t]) - min(p40[t])))

    print("\n【结论】")
    print("  噪声本身造成的期望答对幅度：%.3f 格" % ctl_spread)
    print("  换分组造成的期望答对幅度：  %.3f 格" % exp_spread)
    ratio = exp_spread / ctl_spread if ctl_spread else float("inf")
    print("  比值 %.2f 倍" % ratio)

    # 写成产物：更新日志页要引用这些数字，而那一页的规矩是「数字取自 payload，
    # 不手抄」——手抄的话，页面上的数就没法追溯到任何一次真实运行。
    out = os.path.join(HERE, "..", "reports", "p6_draw_sensitivity.json")
    json.dump({
        "n_draws": n_draws, "n_sim": n_sim,
        "noise_exp_min": min(ctl_exp), "noise_exp_max": max(ctl_exp),
        "noise_spread": ctl_spread, "noise_distinct_answers": len(ctl_ans),
        "draw_exp_min": min(exps), "draw_exp_max": max(exps),
        "draw_spread": exp_spread, "draw_distinct_answers": len(exp_ans),
        "ratio": ratio,
        "max_p40_swing_pp": max(max(p40[t]) - min(p40[t]) for t in TEAMS),
        "max_p40_swing_team": max(TEAMS, key=lambda t: max(p40[t]) - min(p40[t])),
        "p40_range": {t: [min(p40[t]), max(p40[t])] for t in TEAMS},
    }, open(out, "w"), indent=1, ensure_ascii=False)
    print("  → 已写入 reports/p6_draw_sensitivity.json")
    if ratio < 2:
        print("\n  → 分组带来的差异没有明显超过噪声。知道分组**不会让预测变准**，")
        print("     「重算一版会准不少」站不住，应改口径。")
        print("     注：建议填法确实会变，但那是因为中间几格本就是近似平局，")
        print("     换个随机种子也会变——变化不等于变准。")
    else:
        print("\n  → 分组带来的差异明显超过噪声，重算确有价值。")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 8, int(a[1]) if len(a) > 1 else 50000)
