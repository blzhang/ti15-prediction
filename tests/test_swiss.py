import numpy as np
import pytest
from model.swiss import SwissState, pair_round, rank_teams


def fresh(n=16):
    s = SwissState(n)
    s.group = [0] * 8 + [1] * 8
    return s


def test_round1_pairs_across_the_two_groups():
    rng = np.random.default_rng(1)
    s = fresh()
    pairs = pair_round(s, 0, rng)
    assert len(pairs) == 8
    for a, b in pairs:
        assert s.group[a] != s.group[b], "R1 必须跨组配对"
    assert sorted([t for p in pairs for t in p]) == list(range(16))


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
