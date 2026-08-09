"""对 model/patch_weight.py 的单元测试。

这一层的风险不在算错，在**算反**：把「离现在几个版本」算成「从最早版本
数过来第几个」，权重方向就整个颠倒，而 BT 拟合照样收敛、报告照样出数，
没有任何一处会报错。所以下面每一条都在钉方向和边界，而不是钉某个浮点值。

另一条必须钉死的是 gamma=1 的**逐位还原**：新加的这一层默认要能被验证期
选掉。如果 gamma=1 时权重不是精确的 1.0（哪怕差 1e-16），改动前后的
l1_rating.json 就会有肉眼看不见的漂移，「没启用就零影响」这句话也就成了
空话。
"""
import numpy as np
import pytest

from model.patch_weight import (
    patch_index, patch_distance, patch_weights, GAMMA_OFF,
)
from model.patches import patch_ts


TS_741 = patch_ts("7.41")          # 2026-03-24
TS_740 = patch_ts("7.40")          # 2025-12-16
TS_731 = patch_ts("7.31")          # 2022-02-23，表里最早的版本
TS_TI15 = 1786060800               # 2026-08-13T00:00:00Z，TI15 开赛


def test_patch_index_counts_patches_released_at_or_before_ts():
    """索引 = 到该时刻为止已发布的版本数。7.41 发布当秒即算进 7.41。"""
    assert patch_index(TS_741) == patch_index(TS_741 + 86400)
    assert patch_index(TS_741) == patch_index(TS_740) + 1


def test_patch_index_is_zero_before_the_earliest_known_patch():
    """比表里最早的版本还早 -> 0。这是「更老一档」的地板，不是错误：
    L1 的训练数据从 2022-01-01 起，比 7.31（2022-02-23）早的那一小段
    没有版本可归，统一按比 7.31 再老一档处理。"""
    assert patch_index(TS_731 - 1) == 0
    assert patch_index(TS_731) == 1


def test_patch_distance_is_zero_for_matches_on_the_reference_patch():
    """参照时点当前版本内的比赛不打折。"""
    assert patch_distance(TS_741 + 1000, TS_TI15) == 0
    assert patch_distance(TS_TI15 - 1, TS_TI15) == 0


def test_patch_distance_counts_backwards_not_forwards():
    """方向：越老的比赛距离越**大**。这条抓的就是把索引方向写反的错。"""
    d_new = patch_distance(TS_740 + 86400, TS_TI15)   # 7.40 的比赛
    d_old = patch_distance(TS_731 + 86400, TS_TI15)   # 7.31 的比赛
    assert d_new == 1
    assert d_old > d_new
    assert d_old == 10                                 # 7.31 -> 7.41 共 10 步


def test_patch_distance_never_goes_negative_for_future_matches():
    """比参照时点还新的比赛（切分口径下不该出现，但别静默出负数：
    gamma**负数 会放大权重，比报错更难发现）。"""
    assert patch_distance(TS_741 + 86400, TS_740 + 86400) == 0


def test_patch_weights_gamma_one_is_bit_identical_to_all_ones():
    """gamma=1 必须逐位还原：不是「约等于 1」，是 == 1.0。"""
    ts = np.array([TS_731, TS_740, TS_741, TS_TI15 - 1], dtype=float)
    w = patch_weights(ts, TS_TI15, GAMMA_OFF)
    assert w.dtype == np.float64
    assert np.array_equal(w, np.ones(len(ts)))


def test_patch_weights_are_monotone_decreasing_in_age():
    """同一个 gamma<1 下，越老的比赛权重越小，且严格单调。"""
    ts = np.array([TS_731, TS_740, TS_741], dtype=float)
    w = patch_weights(ts, TS_TI15, 0.8)
    assert w[0] < w[1] < w[2]
    assert w[2] == pytest.approx(1.0)
    assert w[1] == pytest.approx(0.8)


def test_patch_weights_reject_gamma_outside_zero_one():
    """gamma>1 会让老比赛权重**变大**——这是一个能跑通但含义相反的配置，
    必须拦在入口，不能等到看排名不对才发现。"""
    ts = np.array([TS_740], dtype=float)
    for bad in (1.0001, 1.5, 0.0, -0.5):
        with pytest.raises(ValueError):
            patch_weights(ts, TS_TI15, bad)


def test_patch_weights_shape_matches_input():
    ts = np.array([TS_731, TS_740], dtype=float)
    assert patch_weights(ts, TS_TI15, 0.9).shape == (2,)
