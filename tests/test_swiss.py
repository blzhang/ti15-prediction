import numpy as np
import pytest
from model.swiss import SwissState, pair_round, rank_teams


def fresh(n=16):
    s = SwissState(n)
    s.group = [0] * 8 + [1] * 8
    return s


def test_round1_pairs_within_each_group_not_across():
    """R1 是**组内**配对，不是跨组。

    这条测试原本断言的是「R1 必须跨组」——那是错的，来自对赛制的误解。
    证伪它的是官方预测面板：面板给的战绩档是 4-0 / 4-1 / 1-4 / 0-4，
    而只有 R1-R3 组内、R4 跨组，才能推出每届恒定的 1/2/5/5/2/1 分档
    （见 test_record_buckets_are_structurally_fixed_every_single_tournament）。
    若 R1 跨组，两组的胜者数会不确定（可能 5:3），R2 的组内配对就会
    撞上奇数战绩组、触发下浮，分档结构随之瓦解。
    """
    rng = np.random.default_rng(1)
    s = fresh()
    pairs = pair_round(s, 0, rng)
    assert len(pairs) == 8
    for a, b in pairs:
        assert s.group[a] == s.group[b], "R1 必须组内配对"
    assert sorted([t for p in pairs for t in p]) == list(range(16))
    # 每组各打 4 场
    from collections import Counter
    per_group = Counter(s.group[a] for a, _ in pairs)
    assert per_group[0] == 4 and per_group[1] == 4


def test_round2_pairs_only_within_group():
    rng = np.random.default_rng(2)
    s = fresh()
    for a, b in pair_round(s, 0, rng):
        s.record(a, b, a_wins=True, loser_games=1)
    for a, b in pair_round(s, 1, rng):
        assert s.group[a] == s.group[b], "R2 只在组内配对"


def test_round4_prefers_cross_group_but_score_group_wins():
    """R4 规则是「只与另一组配对」，但它是**次级**约束——
    同战绩配对优先。当某个战绩组内两队恰好同属一组时，跨组不可能满足。
    因此断言的是「绝大多数跨组」，而非「全部跨组」。
    """
    rng = np.random.default_rng(3)
    cross = same = 0
    for _ in range(50):
        s = fresh()
        for rnd in range(3):
            for a, b in pair_round(s, rnd, rng):
                s.record(a, b, a_wins=bool(rng.random() < 0.5), loser_games=0)
        for a, b in pair_round(s, 3, rng):
            if s.group[a] != s.group[b]:
                cross += 1
            else:
                same += 1
    assert cross / (cross + same) > 0.75, "R4 应以跨组为主"


def test_no_rematch_within_five_rounds():
    rng = np.random.default_rng(4)
    s = fresh()
    for rnd in range(5):
        for a, b in pair_round(s, rnd, rng):
            assert b not in s.played[a], "不得重赛"
            s.record(a, b, a_wins=bool(rng.random() < 0.5), loser_games=1)


def test_at_most_one_team_can_go_5_0():
    """瑞士轮结构性事实：同分配对强制不败队互碰，5 轮后至多 1 支 5-0。"""
    rng = np.random.default_rng(5)
    for _ in range(200):
        s = fresh()
        for rnd in range(5):
            for a, b in pair_round(s, rnd, rng):
                s.record(a, b, a_wins=bool(rng.random() < 0.5), loser_games=0)
        assert sum(1 for t in range(16) if s.wins[t] == 5) <= 1


def test_rank_uses_buchholz_before_coinflip():
    s = fresh()
    # 两队同为 1 胜 0 负、小局同为 2-0，但 0 号的对手更强（更多胜场）
    s.wins[0] = s.wins[1] = 1
    s.game_wins[0] = s.game_wins[1] = 2
    s.opponents[0] = [2]; s.wins[2] = 4
    s.opponents[1] = [3]; s.wins[3] = 0
    order = rank_teams(s, np.random.default_rng(6))
    assert order.index(0) < order.index(1), "Buchholz 高的应排前面"


def test_record_buckets_are_structurally_fixed_every_single_tournament():
    """★ 最强的结构性护栏：每一届瑞士轮的分档**恒为** 1/2/5/5/2/1。

    这不是概率，是「4 胜或 4 负即停 + R1-R3 组内 / R4 跨组」推出的恒等式：
      R1 组内 → 每组恰好 4 胜 4 负
      R3 后每组 3-0:1 / 2-1:3 / 1-2:3 / 0-3:1
      R4 跨组 → 3-0 那两队互打 → 恰好 1 支 4-0；0-3 同理 → 恰好 1 支 0-4
      R5 → 3-1 组 4 队出 2 支 4-1；1-3 组 4 队出 2 支 1-4；余 3-2 五支、2-3 五支

    这条正是官方预测面板槽位数固定（1/2/5/5/2/1 = 16）的原因。
    若实现退回「固定 5 轮人人打满」，会产出现实中不存在的 5-0 / 0-5，本条立刻变红。
    """
    from model.swiss import active_teams
    rng = np.random.default_rng(20260802)
    want = {"4-0": 1, "4-1": 2, "3-2": 5, "2-3": 5, "1-4": 2, "0-4": 1}
    for seed in range(120):
        s = fresh()
        s.group = list(np.random.default_rng(seed).permutation([0] * 8 + [1] * 8))
        for rnd in range(5):
            act = active_teams(s)
            if len(act) < 2:
                break
            for a, b in pair_round(s, rnd, rng, active=act):
                s.record(a, b, a_wins=bool(rng.random() < 0.5), loser_games=0)
        got = {}
        for t in range(16):
            k = "%d-%d" % (s.wins[t], s.losses[t])
            got[k] = got.get(k, 0) + 1
        assert got == want, "seed=%d 分档应恒为 1/2/5/5/2/1，实为 %s" % (seed, got)


def test_no_team_ever_plays_after_clinching_or_being_eliminated():
    """4 胜或 4 负之后不得再上场——固定 5 轮制会违反这条。"""
    from model.swiss import active_teams
    rng = np.random.default_rng(3)
    for seed in range(40):
        s = fresh()
        s.group = list(np.random.default_rng(seed).permutation([0] * 8 + [1] * 8))
        for rnd in range(5):
            act = active_teams(s)
            if len(act) < 2:
                break
            for a, b in pair_round(s, rnd, rng, active=act):
                for t in (a, b):
                    assert s.wins[t] < 4 and s.losses[t] < 4, "已停赛的队不该再配对"
                s.record(a, b, a_wins=bool(rng.random() < 0.5), loser_games=0)
        for t in range(16):
            assert s.wins[t] + s.losses[t] <= 5, "任何队最多打 5 场"
