import math
import pytest
from model.market import devig, blend_logodds


def test_devig_removes_overround_and_normalises():
    # 三路盘，隐含概率和 = 1/2 + 1/3 + 1/4 = 1.0833（8.3% 抽水）
    p = devig({"A": 2.0, "B": 3.0, "C": 4.0})
    assert abs(sum(p.values()) - 1.0) < 1e-12
    # 去水后应保持原始顺序与相对比例
    assert p["A"] > p["B"] > p["C"]
    assert abs(p["A"] / p["B"] - (1 / 2) / (1 / 3)) < 1e-12


def test_devig_rejects_non_positive_odds():
    with pytest.raises(ValueError):
        devig({"A": 0.0, "B": 3.0})


def test_blend_is_identity_at_extremes():
    m = {"A": 0.7, "B": 0.3}
    k = {"A": 0.4, "B": 0.6}
    assert blend_logodds(m, k, 0.0)["A"] == pytest.approx(0.7)
    assert blend_logodds(m, k, 1.0)["A"] == pytest.approx(0.4)


def test_blend_geometric_midpoint_and_normalised():
    m = {"A": 0.8, "B": 0.2}
    k = {"A": 0.2, "B": 0.8}
    out = blend_logodds(m, k, 0.5)
    assert abs(sum(out.values()) - 1.0) < 1e-12
    # 对称输入，50/50 权重 → 各 0.5
    assert out["A"] == pytest.approx(0.5)


def test_blend_requires_same_keys():
    with pytest.raises(ValueError):
        blend_logodds({"A": 1.0}, {"B": 1.0}, 0.5)


from model.market import blend_partial


def test_blend_partial_leaves_unpriced_teams_on_model_only():
    model = {"A": 0.5, "B": 0.3, "C": 0.2}
    odds = {"A": 2.0, "B": 4.0, "C": None}
    out = blend_partial(model, odds, w_market=1.0)
    assert abs(sum(out.values()) - 1.0) < 1e-12
    # C 无盘口 → 其相对于总量的份额不应被市场信息改变方向
    assert out["C"] > 0.0
    # A/B 有盘口且 w=1 → 二者比例应贴近去水后的市场比例
    assert out["A"] / out["B"] == pytest.approx((1 / 2.0) / (1 / 4.0), rel=0.05)
