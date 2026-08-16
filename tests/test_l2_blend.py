"""对 model/l2_blend.py 的测试（两级融合版）。

第一级：市场共识 = blend_partial(Polymarket 16 队概率, 庄家 5 队赔率, w_book)
第二级：最终概率 = blend_logodds(模型, 共识, w_market)

复现性钉子测试的立场不变：以后任何人改了三个输入文件
（l2_predictions / market_odds / polymarket_odds）却忘了重跑
model/l2_blend.py，这条测试直接变红，不让产出物静默漂移。
"""
import json

import pytest

from model.l2_blend import build_blend, main, DEFAULT_ODDS, DEFAULT_OUT
from model.market import (
    blend_logodds, blend_partial, normalize, round_probs,
    W_BOOK_DEFAULT, W_MARKET_DEFAULT,
)


def test_build_blend_reproduces_committed_l2_blended_json():
    """核心不变量：用磁盘上的三个真实输入文件（默认参数）重新融合，
    结果必须与已冻结的 model/l2_blended.json 完全相等（含 market_consensus
    与 sources 元信息块）。"""
    result = build_blend()
    with open(DEFAULT_OUT) as f:
        on_disk = json.load(f)
    assert result == on_disk


def test_build_blend_defaults_come_from_markets_shared_constants():
    """0.7 与 0.5 都必须来自 market.py 的单一定义，本脚本不得另写字面量。"""
    assert W_MARKET_DEFAULT == 0.7
    assert W_BOOK_DEFAULT == 0.5
    result = build_blend()
    assert result["w_market"] == W_MARKET_DEFAULT
    assert result["sources"]["w_book"] == W_BOOK_DEFAULT


def test_build_blend_toy_example_is_a_thin_wrapper_not_a_reimplementation(tmp_path):
    """最小合成输入验证 build_blend 只是 market.py 公开函数的两级薄封装：
    期望值手动调 normalize → blend_partial → blend_logodds → round_probs 算出，
    不是硬编码数字。"""
    l2_path = tmp_path / "toy_l2.json"
    odds_path = tmp_path / "toy_odds.json"
    pm_path = tmp_path / "toy_pm.json"
    model = {"A": 0.5, "B": 0.3, "C": 0.2}
    odds = {"A": 2.0, "B": None, "C": 5.0}
    pm_mids = {"A": 0.5, "B": 0.4, "C": 0.3}
    l2_path.write_text(json.dumps({"champion": model}))
    odds_path.write_text(json.dumps(
        {"decimal_odds": odds, "captured_utc": "2026-08-01"}))
    pm_path.write_text(json.dumps(
        {"prices": {t: {"mid": v, "bid": None, "ask": None, "last": None}
                    for t, v in pm_mids.items()},
         "captured_utc": "2026-08-05T00:00:00Z", "event_slug": "toy"}))

    result = build_blend(l2_path=str(l2_path), odds_path=str(odds_path),
                         pm_path=str(pm_path), w_book=0.5, w_market=0.5)

    consensus = blend_partial(normalize(pm_mids), odds, w_market=0.5)
    expected = round_probs(blend_logodds(model, consensus, 0.5), 6)
    assert result["champion_blended"] == expected
    assert result["market_consensus"] == round_probs(consensus, 6)
    # B 庄家无盘口 → 共识里 B 精确等于归一化后的 Polymarket 概率（质量份额保持）
    assert result["market_consensus"]["B"] == round(normalize(pm_mids)["B"], 6)


def test_build_blend_rejects_pm_team_set_mismatch(tmp_path):
    """Polymarket 与模型的队伍集合不一致必须报错，不能静默丢队。"""
    l2_path = tmp_path / "toy_l2.json"
    odds_path = tmp_path / "toy_odds.json"
    pm_path = tmp_path / "toy_pm.json"
    l2_path.write_text(json.dumps({"champion": {"A": 0.6, "B": 0.4}}))
    odds_path.write_text(json.dumps({"decimal_odds": {"A": 2.0, "B": None}}))
    pm_path.write_text(json.dumps(
        {"prices": {"A": {"mid": 0.5, "bid": None, "ask": None, "last": None}}}))
    with pytest.raises(ValueError, match="B"):
        build_blend(l2_path=str(l2_path), odds_path=str(odds_path),
                    pm_path=str(pm_path))


def test_main_cli_writes_file_matching_build_blend_return_value(tmp_path):
    """CLI 真实入口（真实数据，--out 指向临时文件）：写盘内容与 build_blend()
    返回值一致，16 队、和在容差内、元信息块齐全。"""
    out = str(tmp_path / "l2_blended.json")
    result = main(["--out", out])

    with open(out) as f:
        on_disk = json.load(f)
    assert on_disk == result
    assert on_disk["w_market"] == 0.7
    assert len(on_disk["champion_blended"]) == 16
    assert len(on_disk["market_consensus"]) == 16
    # 进入融合的队数 = 16 减去按 0 直通的出局队数（开赛前后都成立）
    assert on_disk["sources"]["polymarket"]["teams_priced"] == \
        16 - len(on_disk["sources"]["teams_settled_zero"])
    # 庄家侧 2026-08-13 起停用（赛前盘口，赛中已过时，见 model/market_odds.json
    # 的 note）：teams_priced 归零，共识价退化成纯 Polymarket。这个 0 是有意的，
    # 不是抓取失败——两者的区别由 status 字段区分，所以一并断言。
    assert on_disk["sources"]["book"]["teams_priced"] == 0
    with open(DEFAULT_ODDS) as f:
        assert json.load(f)["status"] == "retired_in_tournament"
    assert abs(sum(on_disk["champion_blended"].values()) - 1.0) < 1e-5


def test_build_blend_passes_structurally_settled_teams_through_at_zero(tmp_path):
    """已出局的队（模型概率精确为 0）不进 log-odds 融合，直接带 0——
    靠 1e-9 裁剪会把「不可能」悄悄变成「万分之几」。市场侧的尘埃挂单同样按 0。
    活着的队之间的融合结果必须与「只拿活队单独融合」逐字节一致。"""
    l2_path = tmp_path / "l2.json"
    odds_path = tmp_path / "odds.json"
    pm_path = tmp_path / "pm.json"
    model = {"A": 0.6, "B": 0.4, "OUT1": 0.0, "OUT2": 0.0}
    mids = {"A": 0.55, "B": 0.5, "OUT1": 0.0, "OUT2": 0.004}   # OUT2 是尘埃挂单
    l2_path.write_text(json.dumps({"champion": model}))
    odds_path.write_text(json.dumps({"decimal_odds": {t: None for t in model},
                                     "captured_utc": "x"}))
    pm_path.write_text(json.dumps({
        "prices": {t: {"mid": v} for t, v in mids.items()},
        "captured_utc": "x", "event_slug": "toy"}))
    result = build_blend(l2_path=str(l2_path), odds_path=str(odds_path),
                         pm_path=str(pm_path))
    champ = result["champion_blended"]
    assert champ["OUT1"] == 0.0 and champ["OUT2"] == 0.0
    assert result["market_consensus"]["OUT1"] == 0.0
    assert result["sources"]["teams_settled_zero"] == ["OUT1", "OUT2"]
    assert abs(sum(champ.values()) - 1.0) < 1e-5
    # 活队部分 == 只拿活队融合的结果
    alive = {"A": model["A"], "B": model["B"]}
    pm_alive = normalize({"A": mids["A"], "B": mids["B"]})
    expect = round_probs(blend_logodds(alive, pm_alive, W_MARKET_DEFAULT), 6)
    assert {t: champ[t] for t in alive} == expect
