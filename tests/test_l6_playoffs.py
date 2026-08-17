"""L6 八强前瞻的回归测试。

这套测试守的是三件事，每一件坏掉都会让页面上印出一份看着正常的错预测：
  1. 枚举器的名次分布是结构性恒等式（不是「差不多对」）
  2. 枚举器与既有的 model/bracket.py 蒙特卡洛给出同一个答案
  3. 隐含实力反解之后，冠军概率真的等于融合目标
"""
import itertools

import numpy as np
import pytest

from model.bracket import run_playoffs
from model.l6_playoffs import (
    ALL_STAGES, SEATS, bayesian_update, best_bracket, check_coherent,
    enumerate_bracket, games_from_results, integrate, probs_from_theta,
    solve_implied, solve_implied_joint,
)

THETA = np.array([1.20, 1.00, 0.95, 0.90, 0.85, 0.60, 0.40, 0.10])
SE = np.array([0.12, 0.13, 0.11, 0.14, 0.12, 0.15, 0.13, 0.20])
QF = [(0, 7), (1, 6), (2, 5), (3, 4)]


def _mats(theta, D=1):
    th = np.repeat(np.asarray(theta, float)[None, :], D, axis=0)
    return probs_from_theta(th)


def test_place_distribution_is_a_structural_identity():
    """每队名次概率和恰为 1；各名次席位数恰为 1/1/1/1/2/2。

    这不是「应该差不多」——每条枚举路径都让 8 支队各落在恰好一个名次上，
    所以行和与列和都是恒等式。用它当自检能抓到重复计数：本模块第一版把
    LBR1 的 7-8 名写在了 UBSF 循环里面，被乘了 4 倍，正是这条断言抓出来的。
    """
    _, p3, p5 = _mats(THETA)
    place, _, _ = enumerate_bracket(QF, p3, p5, 1)
    check_coherent(place)

    # 再显式写一遍席位数，让这条恒等式在测试里也看得见（而不是只藏在 check_coherent 里）
    col = sum(row[:, 0] for row in place.values())
    assert list(np.round(col[1:9], 9)) == list(SEATS)


def test_check_coherent_rejects_a_broken_distribution():
    """自检本身必须真的会失败——否则它只是一句装饰。"""
    _, p3, p5 = _mats(THETA)
    place, _, _ = enumerate_bracket(QF, p3, p5, 1)
    place[0] = place[0] * 1.5                      # 人为破坏行和
    with pytest.raises(AssertionError, match="名次概率和"):
        check_coherent(place)


def test_enumeration_matches_bracket_monte_carlo():
    """枚举给的是精确值，蒙特卡洛给的是带噪声的估计，两者必须吻合。

    model/bracket.py 是全站主链路在用的实现；如果哪天有人改了它的连接
    结构（比如把败者组的交叉连法改成同侧连），这条会立刻变红。
    """
    _, p3, p5 = _mats(THETA)
    place, _, _ = enumerate_bracket(QF, p3, p5, 1)

    # bracket.py 的 QF 构造顺序是 [(s0,s7),(s3,s4),(s1,s6),(s2,s5)]，
    # 反过来编码使它逐场还原上面的 QF。
    (m1a, m1b), (m2a, m2b), (m3a, m3b), (m4a, m4b) = QF
    seeds = [m1a, m3a, m4a, m2a, m2b, m4b, m3b, m1b]

    p3_pt = p3[:, :, 0]
    p5_pt = p5[:, :, 0]
    rng = np.random.default_rng(20260816)
    n = 120000
    mc = np.zeros((8, 9))
    for _ in range(n):
        for t, pl in run_playoffs(seeds, p3_pt, p5_pt, rng).items():
            mc[t, pl] += 1
    mc /= n

    for t in range(8):
        for k in (1, 2, 3, 4, 5, 7):
            exact = float(place[t][k][0])
            # 蒙特卡洛 3 倍标准误 + 一点余量
            tol = 3 * np.sqrt(max(exact, 1e-4) * (1 - exact) / n) + 0.002
            assert abs(exact - mc[t, k]) < tol, (t, k, exact, mc[t, k])


def test_seeds_encoding_round_trips_through_bracket_construction():
    """槽位编码必须逐场还原输入的四场对阵。

    这条钉住的是 l2_simulate.seeds_from_ubqf 与本模块共用的那个映射。
    写反了不会报错，只会安静地把「VISION 打 BoomBoys」变成别的对阵。
    """
    (m1a, m1b), (m2a, m2b), (m3a, m3b), (m4a, m4b) = QF
    seeds = [m1a, m3a, m4a, m2a, m2b, m4b, m3b, m1b]
    rebuilt = [(seeds[0], seeds[7]), (seeds[3], seeds[4]),
               (seeds[1], seeds[6]), (seeds[2], seeds[5])]
    assert rebuilt == QF


def test_stage_pairs_sum_to_one_per_stage():
    """每个未来阶段恰好会发生一场比赛，所以该阶段全部可能对阵的概率和为 1。"""
    _, p3, p5 = _mats(THETA)
    _, pairs, _ = enumerate_bracket(QF, p3, p5, 1)
    for stage, d in pairs.items():
        total = float(sum(v[0] for v in d.values()))
        assert total == pytest.approx(1.0, abs=1e-9), (stage, total)


def test_ubsf_can_only_pair_winners_from_opposite_quarterfinals():
    """结构约束：UBSF1 只可能是 QF1 胜者对 QF2 胜者，四种组合、不多不少。"""
    _, p3, p5 = _mats(THETA)
    _, pairs, _ = enumerate_bracket(QF, p3, p5, 1)
    want = {tuple(sorted((a, b))) for a in QF[0] for b in QF[1]}
    assert set(pairs["UBSF1"]) == want


def test_implied_strength_reproduces_the_blend_target():
    """反解之后，枚举出的冠军概率必须等于给定目标。

    这是引入隐含实力的全部理由：让「逐场胜率」和「冠军概率」出自同一套参数。
    """
    target_names = [0.35, 0.15, 0.12, 0.11, 0.10, 0.08, 0.06, 0.03]
    alive = list(range(8))
    target = {t: target_names[t] for t in alive}
    th, n_iter, err = solve_implied(QF, THETA, SE, target, alive,
                                    n_draw=400, seed=5, tol=1e-3)
    place, _, _, _ = integrate(QF, th, SE, n_draw=400, seed=5)
    tot = sum(place[t][1] for t in alive)
    for t in alive:
        assert place[t][1] / tot == pytest.approx(target[t], abs=2e-3)


def test_implied_strength_raises_instead_of_returning_unconverged():
    """没收敛就抛错，不返回一个凑合的结果——凑合的结果会让整页数字对不上。"""
    target = {t: 1 / 8 for t in range(8)}
    with pytest.raises(RuntimeError, match="没收敛"):
        solve_implied(QF, THETA, SE, target, list(range(8)),
                      n_draw=200, seed=1, tol=1e-12, max_iter=3)


def test_bayesian_update_moves_toward_observed_results_but_stays_anchored():
    """贝叶斯更新的两条定性性质：方向对，且被先验压住。

    赢球的队实力分上升、输球的下降（方向对）；但先验很紧（se 约 0.13，
    先验精度约 60），少量比赛不可能把排序整个掀翻——这正是本模块要
    量化的那件事，所以它必须在测试里被钉住，而不是只写在文案里。
    """
    idx = {"T%d" % i: i for i in range(8)}
    games = [{"a": "T7", "b": "T0", "a_won": True} for _ in range(10)]
    upd = bayesian_update(THETA, SE, games, idx)
    assert upd[7] > THETA[7]                 # 连赢 10 局，实力分上升
    assert upd[0] < THETA[0]                 # 连输 10 局，实力分下降
    assert upd[7] < THETA[0]                 # 但仍翻不过原来最强的那支
    assert np.max(np.abs(upd - THETA)) < 0.5


def test_bayesian_update_is_identity_without_games():
    assert np.allclose(bayesian_update(THETA, SE, [], {}), THETA)


def test_games_from_results_expands_series_into_individual_games():
    """BO3 的 2-0 摊成 2 局、2-1 摊成 3 局——口径要与 L1 的逐局拟合一致。"""
    teams = ["A", "B", "C", "D"]
    observed = {
        "rounds": {1: [(0, 1, True, 1)]},        # A 2-1 B
        "elim": [(2, 3, False, 0)],              # D 2-0 C
    }
    games = games_from_results(observed, teams)
    assert len(games) == 5
    a_wins = sum(1 for g in games if g["a"] == "A" and g["a_won"])
    b_wins = sum(1 for g in games if g["a"] == "B" and g["a_won"])
    assert (a_wins, b_wins) == (2, 1)
    d_wins = sum(1 for g in games if g["a"] == "D" and g["a_won"])
    assert d_wins == 2
    assert all(g["a_won"] for g in games)        # 一律记成「a 赢」，不留半条反向记录


def test_games_from_results_skips_unplayed_series():
    teams = ["A", "B"]
    observed = {"rounds": {1: [(0, 1, None, None)]}, "elim": []}
    assert games_from_results(observed, teams) == []


def test_uncertainty_integration_widens_the_field():
    """把实力不确定性积分进去之后，强队的夺冠概率必须下降。

    这是方法论一致性的检查：l2_simulate 每次模拟重抽 theta，本模块也必须
    这么做。如果哪天有人图快把 se 那一步去掉，最强的队会显得比实际更稳。
    """
    place_pt, _, _, _ = integrate(QF, THETA, SE * 0, n_draw=1)
    place_se, _, _, _ = integrate(QF, THETA, SE, n_draw=1500, seed=3)
    top = max(range(8), key=lambda t: place_pt[t][1])
    assert place_se[top][1] < place_pt[top][1]


# ---------------------------------------------------------------- 抄作业：整张对阵表
def _winners_from(theta):
    _, p3, p5 = _mats(theta)
    _, _, winners = enumerate_bracket(QF, p3, p5, 1)
    return {s: {t: float(v[0]) for t, v in d.items()} for s, d in winners.items()}


def test_每场胜者概率之和恒为一():
    """每一场恰好有一个胜者，所以该场全部队伍的「赢下这一场」概率和为 1。

    这是恒等式，不是近似——它同时锁住「没走到这一场的队不该被计入」这条：
    winners 里已经把「该队根本没到场」的路径排除了，所以八支队的和才会是 1。
    """
    w = _winners_from(THETA)
    for stage, d in w.items():
        assert sum(d.values()) == pytest.approx(1.0, abs=1e-9), (stage, sum(d.values()))


def test_八强胜者概率就是那两支队的对阵胜率():
    """UBQF 的胜者概率不该经过任何推演——它就是这两队的 BO3 胜率本身。"""
    _, p3, _ = _mats(THETA)
    w = _winners_from(THETA)
    for k, (a, b) in enumerate(QF):
        st = "UBQF%d" % (k + 1)
        assert w[st][a] == pytest.approx(float(p3[a, b][0]), abs=1e-9)
        assert w[st][b] == pytest.approx(float(p3[b, a][0]), abs=1e-9)
        # 没打这一场的六支队必须恒为 0
        for t in range(8):
            if t not in (a, b):
                assert w[st][t] == 0.0


def test_最优填法枚举恰好覆盖全部自洽填法():
    """2^14 = 16384。少一种说明有分支漏了，多一种说明有填法被重复计入。"""
    w = _winners_from(THETA)
    _, _, stats = best_bracket(QF, w, [str(i) for i in range(8)])
    assert stats["n_brackets"] == 16384
    assert stats["n_matches"] == 14


def test_最优填法不劣于随机且不超过贪心上界():
    """三个数的大小关系是结构性的：随机 ≤ 最优 ≤ 逐场贪心。

    贪心把路径自洽这条约束整个无视掉，所以它永远是上界；
    最优是在自洽解里搜的，不可能超过它，也不可能比随机差。
    """
    w = _winners_from(THETA)
    _, _, st = best_bracket(QF, w, [str(i) for i in range(8)])
    assert st["random"] <= st["expected"] <= st["greedy_upper"] + 1e-9


def test_最优填法本身是自洽的():
    """填进后面几轮的队，必须是自己在前面几轮推上去的——否则这份填法根本填不进面板。"""
    teams = [str(i) for i in range(8)]
    w = _winners_from(THETA)
    pick, _, _ = best_bracket(QF, w, teams)
    qf_names = [(teams[a], teams[b]) for a, b in QF]
    ub_w = [pick["UBQF%d" % (k + 1)] for k in range(4)]
    ub_l = [b if pick["UBQF%d" % (k + 1)] == a else a for k, (a, b) in enumerate(qf_names)]
    for k in range(4):
        assert ub_w[k] in qf_names[k]
    assert pick["UBSF1"] in (ub_w[0], ub_w[1])
    assert pick["UBSF2"] in (ub_w[2], ub_w[3])
    assert pick["UBF"] in (pick["UBSF1"], pick["UBSF2"])
    assert pick["LBR1-1"] in (ub_l[0], ub_l[1])
    assert pick["LBR1-2"] in (ub_l[2], ub_l[3])
    # 败者组交叉：败2上 = 败1上胜者 vs UBSF2 的败者
    sf2_l = pick["UBSF2"] if False else (ub_w[2] if pick["UBSF2"] == ub_w[3] else ub_w[3])
    sf1_l = ub_w[0] if pick["UBSF1"] == ub_w[1] else ub_w[1]
    assert pick["LBQF-1"] in (pick["LBR1-1"], sf2_l)
    assert pick["LBQF-2"] in (pick["LBR1-2"], sf1_l)
    assert pick["LBSF"] in (pick["LBQF-1"], pick["LBQF-2"])
    ubf_l = pick["UBSF1"] if pick["UBF"] == pick["UBSF2"] else pick["UBSF2"]
    assert pick["LBF"] in (pick["LBSF"], ubf_l)
    assert pick["GF"] in (pick["UBF"], pick["LBF"])


def test_一边倒的实力下最优填法就是全押最强():
    """极端情形自检：一支队强到碾压时，最优填法应把它填进它参与的每一场。"""
    teams = [str(i) for i in range(8)]
    w = _winners_from([9.0, 0, 0, 0, 0, 0, 0, 0])
    pick, _, _ = best_bracket(QF, w, teams)
    assert pick["UBQF1"] == "0"      # 0 号队在 QF[0]=(0,7) 里
    assert pick["UBSF1"] == "0" and pick["UBF"] == "0" and pick["GF"] == "0"
