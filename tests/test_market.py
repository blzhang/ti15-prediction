import json
import math
import os
import pytest
from model.market import devig, blend_logodds


def _project_path(*parts):
    """定位仓库根目录下的文件，与 cwd 无关（tests/test_market.py 的上一级是仓库根）。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, *parts)


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
    # C 无盘口 → 融合后必须精确等于其原始模型概率，不能被市场信息污染
    # （核心不变量：之前这里只断言 > 0.0，任何把 C 改成任意正数的错误实现都能混过去）
    assert out["C"] == pytest.approx(model["C"])
    # A/B 有盘口且 w=1 → 二者比例应贴近去水后的市场比例
    assert out["A"] / out["B"] == pytest.approx((1 / 2.0) / (1 / 4.0), rel=0.05)


def test_blend_partial_raises_valueerror_when_priced_mass_is_zero():
    """有盘口的队在模型里的总概率质量为 0（mass==0）时，之前的实现会在
    `model_p[k] / mass` 裸抛 ZeroDivisionError。§52-53 对「一个队都没盘口」
    这个对称边界已有显式 guard，但「有盘口但份额全零」没有——这里补上，
    换成有领域语义的 ValueError，而不是让底层算术异常直接冒出来。"""
    model = {"A": 0.0, "B": 0.0, "C": 1.0}
    odds = {"A": 2.0, "B": 4.0, "C": None}
    with pytest.raises(ValueError):
        blend_partial(model, odds, w_market=0.5)


def test_market_odds_source_cites_traditional_bookmaker_section():
    """5 队赔率表实际在 01-ti15-facts.md §4.2「传统博彩交叉验证」；
    §5 是「来源冲突表」，跟赔率无关，之前 source 字段引用的章节号写错了。"""
    with open(_project_path("model", "market_odds.json")) as f:
        source = json.load(f)["source"]
    assert "§4.2" in source
    assert "§5" not in source


def test_blend_partial_real_16_team_scenario_preserves_unpriced_teams_exactly():
    """覆盖真实场景：16 队里只有 5 队有盘口（model/market_odds.json）。
    核心不变量——11 支无盘口队的融合结果必须逐一精确等于融合前的纯模型概率，
    不能被市场信息污染。这是本任务的核心不变量，用真实数据文件直接校验。"""
    with open(_project_path("model", "l2_predictions.json")) as f:
        model = json.load(f)["champion"]
    with open(_project_path("model", "market_odds.json")) as f:
        odds = json.load(f)["decimal_odds"]

    priced_teams = {k for k, v in odds.items() if v}
    unpriced_teams = set(model) - priced_teams
    assert len(priced_teams) == 5
    assert len(unpriced_teams) == 11

    out = blend_partial(model, odds, w_market=0.7)
    for team in unpriced_teams:
        assert out[team] == pytest.approx(model[team]), team


from model.market import round_probs


def test_round_probs_rounds_to_six_decimals_by_default():
    # 复现审查报告里指出的原始 17 位浮点噪声值
    probs = {"Iron Wing": 0.10461079383456102, "Team Falcons": 0.10320832299583454}
    out = round_probs(probs)
    assert out["Iron Wing"] == 0.104611
    assert out["Team Falcons"] == 0.103208


def test_round_probs_does_not_renormalise():
    """只四舍五入，不重新归一化——归一化会把小数位又变长，与四舍五入的目的相悖。
    调用方应自行校验 abs(sum(out.values()) - 1.0) < 容差（如 1e-5），
    而不是指望 round_probs 自己凑成精确的 1。"""
    probs = {"A": 1.0 / 3, "B": 1.0 / 3, "C": 1.0 / 3}
    out = round_probs(probs, ndigits=6)
    assert out == {"A": 0.333333, "B": 0.333333, "C": 0.333333}
    assert sum(out.values()) != 1.0
    assert sum(out.values()) == pytest.approx(1.0, abs=1e-5)


def test_l2_blended_json_probabilities_rounded_to_six_decimals():
    """Global Constraints：概率输出 JSON 一律 float，保 6 位小数。之前
    model/l2_blended.json 里是 17 位浮点噪声（如 "Iron Wing": 0.10461079383456102），
    完全没四舍五入——直接对实际产出文件做回归校验，防止再次漏掉 round()。"""
    with open(_project_path("model", "l2_blended.json")) as f:
        champ = json.load(f)["champion_blended"]
    for team, p in champ.items():
        assert p == round(p, 6), "%s 的概率未四舍五入到 6 位小数：%r" % (team, p)


def test_l2_blended_json_sum_within_documented_tolerance():
    """四舍五入到 6 位小数后，16 个概率的和不会精确等于 1（理论偏差上界约
    16*5e-7=8e-6）。不应该为了凑成 1 而在四舍五入后再归一化，只需校验偏差
    在 1e-5 容差内。"""
    with open(_project_path("model", "l2_blended.json")) as f:
        champ = json.load(f)["champion_blended"]
    deviation = abs(sum(champ.values()) - 1.0)
    assert deviation < 1e-5


from model.market import normalize, W_BOOK_DEFAULT


def test_w_book_default_is_half():
    """源间权重 0.5 的单一定义（设计文档 2026-08-05 §3：等权最不武断）。"""
    assert W_BOOK_DEFAULT == 0.5


def test_normalize_scales_to_unit_sum_preserving_ratios():
    out = normalize({"A": 0.6, "B": 0.6})
    assert abs(sum(out.values()) - 1.0) < 1e-12
    assert out["A"] == pytest.approx(0.5)
    # 已归一的输入 → 原样
    out2 = normalize({"A": 0.5, "B": 0.25, "C": 0.25})
    assert out2 == pytest.approx({"A": 0.5, "B": 0.25, "C": 0.25})


def test_normalize_rejects_empty_and_non_positive():
    with pytest.raises(ValueError):
        normalize({})
    with pytest.raises(ValueError):
        normalize({"A": 0.5, "B": 0.0})
    with pytest.raises(ValueError):
        normalize({"A": 0.5, "B": -0.1})


def test_consensus_equal_weight_is_symmetric_on_priced_subset():
    """等权对称性（设计文档 §6）：在庄家覆盖的子集上把两侧条件概率对换，
    共识价不变。blend_partial(主向量, 赔率, 0.5) 内部是 log-odds 等权，
    等权融合对两个输入对称——这条测试把「0.5 的含义就是两源地位对等」钉死。"""
    pm = {"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1}
    odds = {"A": 2.0, "B": 3.0, "C": None, "D": None}
    fwd = blend_partial(pm, odds, w_market=0.5)

    # 反向：主向量位置放庄家条件概率（乘回质量 0.7），赔率位置放 pm 条件概率的倒数
    book_p = devig({"A": 2.0, "B": 3.0})
    swapped_main = {"A": book_p["A"] * 0.7, "B": book_p["B"] * 0.7, "C": 0.2, "D": 0.1}
    swapped_odds = {"A": 1 / (0.4 / 0.7), "B": 1 / (0.3 / 0.7), "C": None, "D": None}
    rev = blend_partial(swapped_main, swapped_odds, w_market=0.5)

    for t in "ABCD":
        assert rev[t] == pytest.approx(fwd[t]), t


def test_consensus_w_book_extremes_reduce_to_single_source():
    """w_book=0 → 纯 Polymarket；w_book=1 → 庄家完全决定其 5 队内部排序，
    但质量分配仍由 Polymarket 决定（设计文档 §2）。"""
    pm = {"A": 0.4, "B": 0.3, "C": 0.3}
    odds = {"A": 3.0, "B": 2.0, "C": None}
    out0 = blend_partial(pm, odds, w_market=0.0)
    for t in pm:
        assert out0[t] == pytest.approx(pm[t]), t
    out1 = blend_partial(pm, odds, w_market=1.0)
    book_p = devig({"A": 3.0, "B": 2.0})
    assert out1["A"] / out1["B"] == pytest.approx(book_p["A"] / book_p["B"])
    assert out1["C"] == pytest.approx(pm["C"])


def test_consensus_preserves_mass_share_of_pm_only_teams():
    """庄家没开盘的队，其共识概率精确等于 Polymarket 概率（质量份额保持）。"""
    pm = {"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1}
    odds = {"A": 1.5, "B": 6.0, "C": None, "D": None}
    out = blend_partial(pm, odds, w_market=0.5)
    assert out["C"] == pytest.approx(0.2)
    assert out["D"] == pytest.approx(0.1)
    assert out["A"] + out["B"] == pytest.approx(0.7)
