import numpy as np
import pytest
from model.bracket import run_playoffs, loser_games_prob


def _matrix(theta):
    t = np.asarray(theta, dtype=float)
    p1 = 1.0 / (1.0 + np.exp(-(t[:, None] - t[None, :])))
    p3 = p1 ** 2 * (3 - 2 * p1)
    q = 1 - p1
    p5 = p1 ** 3 * (1 + 3 * q + 6 * q ** 2)
    return p3, p5


def test_placements_are_structurally_valid():
    p3, p5 = _matrix([2, 1.5, 1, .5, 0, -.5, -1, -1.5])
    rng = np.random.default_rng(0)
    place = run_playoffs(list(range(8)), p3, p5, rng)
    assert sorted(place.keys()) == list(range(8))
    assert sorted(place.values()) == [1, 2, 3, 4, 5, 5, 7, 7]


def test_strongest_seed_wins_most_often():
    p3, p5 = _matrix([4, 0, 0, 0, 0, 0, 0, 0])
    rng = np.random.default_rng(1)
    champs = [min(run_playoffs(list(range(8)), p3, p5, rng).items(),
                  key=lambda kv: kv[1])[0] for _ in range(400)]
    assert champs.count(0) / 400 > 0.7


def test_loser_games_prob_is_higher_for_even_matchups():
    assert loser_games_prob(0.50) > loser_games_prob(0.85)
    assert 0.0 < loser_games_prob(0.99) < 1.0


def test_loser_games_prob_matches_bo3_conditional_algebra():
    # BO3 中赢方 2-1 的概率 = 2p^2(1-p)；赢方获胜概率 = p^2(3-2p)
    p = 0.6
    expected = 2 * p ** 2 * (1 - p) / (p ** 2 * (3 - 2 * p))
    assert loser_games_prob(p) == pytest.approx(expected)


def test_seeding_matters_for_champion_odds():
    """种子规则未公布(假设 A3)：验证它到底影响多大，供文档记录。"""
    p3, p5 = _matrix([2, 1.6, 1.2, .8, .4, 0, -.4, -.8])
    rng = np.random.default_rng(7)
    def champ_rate(seeds, n=600):
        return sum(1 for _ in range(n)
                   if min(run_playoffs(seeds, p3, p5, rng).items(),
                          key=lambda kv: kv[1])[0] == 0) / n
    by_rank = champ_rate(list(range(8)))
    reversed_ = champ_rate(list(range(8))[::-1])
    assert abs(by_rank - reversed_) < 0.25, "种子规则影响应小于 25pp，否则必须查实真实规则"
