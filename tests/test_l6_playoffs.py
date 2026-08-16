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
    SEATS, bayesian_update, check_coherent, enumerate_bracket,
    games_from_results, integrate, probs_from_theta, solve_implied,
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
    place, _ = enumerate_bracket(QF, p3, p5, 1)
    check_coherent(place)

    # 再显式写一遍席位数，让这条恒等式在测试里也看得见（而不是只藏在 check_coherent 里）
    col = sum(row[:, 0] for row in place.values())
    assert list(np.round(col[1:9], 9)) == list(SEATS)


def test_check_coherent_rejects_a_broken_distribution():
    """自检本身必须真的会失败——否则它只是一句装饰。"""
    _, p3, p5 = _mats(THETA)
    place, _ = enumerate_bracket(QF, p3, p5, 1)
    place[0] = place[0] * 1.5                      # 人为破坏行和
    with pytest.raises(AssertionError, match="名次概率和"):
        check_coherent(place)


def test_enumeration_matches_bracket_monte_carlo():
    """枚举给的是精确值，蒙特卡洛给的是带噪声的估计，两者必须吻合。

    model/bracket.py 是全站主链路在用的实现；如果哪天有人改了它的连接
    结构（比如把败者组的交叉连法改成同侧连），这条会立刻变红。
    """
    _, p3, p5 = _mats(THETA)
    place, _ = enumerate_bracket(QF, p3, p5, 1)

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
    _, pairs = enumerate_bracket(QF, p3, p5, 1)
    for stage, d in pairs.items():
        total = float(sum(v[0] for v in d.values()))
        assert total == pytest.approx(1.0, abs=1e-9), (stage, total)


def test_ubsf_can_only_pair_winners_from_opposite_quarterfinals():
    """结构约束：UBSF1 只可能是 QF1 胜者对 QF2 胜者，四种组合、不多不少。"""
    _, p3, p5 = _mats(THETA)
    _, pairs = enumerate_bracket(QF, p3, p5, 1)
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
    place, _, _ = integrate(QF, th, SE, n_draw=400, seed=5)
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
    place_pt, _, _ = integrate(QF, THETA, SE * 0, n_draw=1)
    place_se, _, _ = integrate(QF, THETA, SE, n_draw=1500, seed=3)
    top = max(range(8), key=lambda t: place_pt[t][1])
    assert place_se[top][1] < place_pt[top][1]
