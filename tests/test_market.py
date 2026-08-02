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
