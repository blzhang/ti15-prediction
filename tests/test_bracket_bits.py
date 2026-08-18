"""对阵表 bit 编码的回归测试。

守的是一件事：「一份自洽填法 ↔ 一个 14 位整数」这个对应关系。
Python 与前端 site/assets_src/bracket.js 各有一份实现，两份必须逐位一致——
漂移的表现不是崩溃，是抄作业页静静印出一个跟模型对不上的期望答对数。

位定义表在 docs/superpowers/specs/2026-08-18-bracket-editor-design.md 决定一。
"""
import itertools
import json
import os

import numpy as np
import pytest

from model.l6_playoffs import (
    ALL_STAGES, BIT_STAGE, N_BITS, best_bracket, enumerate_bracket, expand,
    probs_from_theta,
)

THETA = [1.20, 1.00, 0.95, 0.90, 0.85, 0.60, 0.40, 0.10]
QF = [(0, 7), (1, 6), (2, 5), (3, 4)]


def _winners(theta=THETA):
    th = np.repeat(np.asarray(theta, float)[None, :], 1, axis=0)
    _, p3, p5 = probs_from_theta(th)
    _, _, winners = enumerate_bracket(QF, p3, p5, 1)
    return {s: {t: float(v[0]) for t, v in d.items()} for s, d in winners.items()}


def _assert_coherent(pick, qf):
    """填进后面几轮的队，必须是自己在前面几轮推上去的。

    与 tests/test_l6_playoffs.py:test_最优填法本身是自洽的 是同一套检查——
    那边只查最优那一份，这里查全部 16384 份。
    """
    w = [pick["UBQF%d" % (k + 1)] for k in range(4)]
    l = [qf[k][0] if w[k] == qf[k][1] else qf[k][1] for k in range(4)]
    for k in range(4):
        assert w[k] in qf[k]
    assert pick["UBSF1"] in (w[0], w[1])
    assert pick["UBSF2"] in (w[2], w[3])
    sf1_l = w[0] if pick["UBSF1"] == w[1] else w[1]
    sf2_l = w[2] if pick["UBSF2"] == w[3] else w[3]
    assert pick["LBR1-1"] in (l[0], l[1])
    assert pick["LBR1-2"] in (l[2], l[3])
    # 败者组交叉：败2上 = 败1上胜者 vs F 的败者；败2下 = 败1下胜者 vs E 的败者
    assert pick["LBQF-1"] in (pick["LBR1-1"], sf2_l)
    assert pick["LBQF-2"] in (pick["LBR1-2"], sf1_l)
    assert pick["LBSF"] in (pick["LBQF-1"], pick["LBQF-2"])
    assert pick["UBF"] in (pick["UBSF1"], pick["UBSF2"])
    ubf_l = pick["UBSF1"] if pick["UBF"] == pick["UBSF2"] else pick["UBSF2"]
    assert pick["LBF"] in (pick["LBSF"], ubf_l)
    assert pick["GF"] in (pick["UBF"], pick["LBF"])


def test_全部_16384_种_bits_展开后都是自洽填法():
    """这是 bit 编码的立身之本：任何一个 14 位整数都对应一份能真的填进面板的填法。"""
    assert N_BITS == 14 and len(BIT_STAGE) == 14
    assert set(BIT_STAGE) == set(ALL_STAGES)
    for bits in range(1 << N_BITS):
        _assert_coherent(expand(QF, bits), QF)


def test_bits_与自洽填法一一对应():
    """双射。少一种说明有填法漏了，重复说明有填法被算了两次。

    重构前这条由「10 层嵌套循环恰好转 16384 圈」的计数断言守着；
    换成位展开后计数变成同义反复，所以改由这条实打实的双射检查接手。
    """
    seen = {}
    for bits in range(1 << N_BITS):
        key = tuple(expand(QF, bits)[st] for st in BIT_STAGE)
        assert key not in seen, "bits %d 与 %d 展开出同一份填法" % (bits, seen[key])
        seen[key] = bits
    assert len(seen) == 16384


def _reference_best_bracket(qf, winners):
    """重构前那 10 层嵌套循环的逐字搬运，只当参照用。

    留着它的理由：这次重构把「枚举全部自洽填法」从显式分支结构换成了位展开，
    两者等价是整个改动的赌注。参照实现让这个赌注变成一条会变红的断言，
    而不是一句「我检查过了」。
    """
    a1, b1 = qf[0]; a2, b2 = qf[1]; a3, b3 = qf[2]; a4, b4 = qf[3]
    best, best_sc, total, n = None, -1.0, 0.0, 0
    for m in itertools.product((0, 1), repeat=4):
        w = [a1 if m[0] == 0 else b1, a2 if m[1] == 0 else b2,
             a3 if m[2] == 0 else b3, a4 if m[3] == 0 else b4]
        l = [b1 if m[0] == 0 else a1, b2 if m[1] == 0 else a2,
             b3 if m[2] == 0 else a3, b4 if m[3] == 0 else a4]
        for e, f in itertools.product((0, 1), repeat=2):
            sf_w = [w[0] if e == 0 else w[1], w[2] if f == 0 else w[3]]
            sf_l = [w[1] if e == 0 else w[0], w[3] if f == 0 else w[2]]
            for r1, r2 in itertools.product((0, 1), repeat=2):
                lb1 = [l[0] if r1 == 0 else l[1], l[2] if r2 == 0 else l[3]]
                q1_opts = (lb1[0], sf_l[1])
                q2_opts = (lb1[1], sf_l[0])
                for c1, c2 in itertools.product((0, 1), repeat=2):
                    lb2 = [q1_opts[c1], q2_opts[c2]]
                    for v in (0, 1):
                        lb3 = lb2[v]
                        for g in (0, 1):
                            ubf_w, ubf_l = ((sf_w[0], sf_w[1]) if g == 0
                                            else (sf_w[1], sf_w[0]))
                            for lf in (0, 1):
                                lbf = lb3 if lf == 0 else ubf_l
                                for gf in (0, 1):
                                    champ = ubf_w if gf == 0 else lbf
                                    pick = {
                                        "UBQF1": w[0], "UBQF2": w[1],
                                        "UBQF3": w[2], "UBQF4": w[3],
                                        "UBSF1": sf_w[0], "UBSF2": sf_w[1],
                                        "LBR1-1": lb1[0], "LBR1-2": lb1[1],
                                        "LBQF-1": lb2[0], "LBQF-2": lb2[1],
                                        "LBSF": lb3, "UBF": ubf_w,
                                        "LBF": lbf, "GF": champ,
                                    }
                                    sc = sum(winners[st][pick[st]] for st in ALL_STAGES)
                                    total += sc
                                    n += 1
                                    if sc > best_sc:
                                        best_sc, best = sc, pick
    assert n == 16384
    return best, best_sc, total / n


def test_位展开枚举与重构前的嵌套循环给出同一个答案():
    """最优填法、期望答对数、随机基线三项都必须一致。"""
    teams = [str(i) for i in range(8)]
    w = _winners()
    ref_pick, ref_sc, ref_rand = _reference_best_bracket(QF, w)
    pick, _, stats = best_bracket(QF, w, teams)

    assert pick == {st: teams[t] for st, t in ref_pick.items()}
    assert stats["expected"] == ref_sc
    assert abs(stats["random"] - ref_rand) < 1e-12


def test_位展开在另一组实力下也与嵌套循环一致():
    """换一组实力再比一次——单点相等可能是巧合，两个不同的最优解不会都是巧合。"""
    teams = [str(i) for i in range(8)]
    w = _winners([0.10, 0.40, 0.60, 0.85, 0.90, 0.95, 1.00, 1.20])
    ref_pick, ref_sc, _ = _reference_best_bracket(QF, w)
    pick, _, stats = best_bracket(QF, w, teams)
    assert pick == {st: teams[t] for st, t in ref_pick.items()}
    assert stats["expected"] == ref_sc


def test_stats_里的_pick_bits_展开回同一份最优填法():
    """前端拿 pick_bits 当初始状态，它必须真的等于 pick。"""
    teams = [str(i) for i in range(8)]
    w = _winners()
    pick, _, stats = best_bracket(QF, w, teams)
    assert expand(QF, stats["pick_bits"]) == {st: teams.index(t) for st, t in pick.items()}


REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "p8_playoffs.json")


def _report():
    """读真实产物。测的就是**导出环节**——内存里的 winners 一直是全表，
    在序列化那一步被截断才是真正会发生的事故。"""
    if not os.path.exists(REPORT):
        pytest.skip("需要先跑 python3 model/l6_playoffs.py 生成产物")
    with open(REPORT) as fh:
        return json.load(fh)


def test_导出的_win_p_是全表而不是被截断的_top4():
    """前端算分靠查这张表，缺一支队就会把它算成 0 分。

    rows[].top 那份为了显示做了截断（top4 且 p>0.005），交互版必须用没截断的。
    """
    d = _report()["bracket_homework"]
    assert set(d["win_p"]) == set(ALL_STAGES)
    for st in ALL_STAGES:
        assert len(d["win_p"][st]) == 8, "%s 少了队：%s" % (st, sorted(d["win_p"][st]))
        assert abs(sum(d["win_p"][st].values()) - 1.0) < 1e-9, "%s 概率和不为 1" % st


def test_导出的_pick_bits_展开回同一份_pick():
    """前端拿它当初始状态。展不回去就意味着读者一进页面看到的填法与模型的不是同一份。"""
    r = _report()
    qf = [(m["a"], m["b"]) for m in r["ubqf"]]
    d = r["bracket_homework"]
    assert expand(qf, d["pick_bits"]) == d["pick"]
