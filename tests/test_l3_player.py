import numpy as np
import pandas as pd
import pytest
from model.l3_player import shrink, fit_rate_model


# ---- brief 给定的 5 条测试（Step 1，原样使用，不可削弱） ----

def test_shrink_pulls_small_samples_toward_prior():
    prior, pv = 5.0, 1.0
    low_n, _ = shrink(raw_rate=12.0, n=2, prior_mean=prior, prior_var=pv)
    high_n, _ = shrink(raw_rate=12.0, n=200, prior_mean=prior, prior_var=pv)
    assert prior < low_n < high_n < 12.0, "样本越少越该被拉回先验"


def test_shrink_se_decreases_with_sample_size():
    _, se_small = shrink(8.0, 3, 5.0, 1.0)
    _, se_big = shrink(8.0, 300, 5.0, 1.0)
    assert se_small > se_big


def test_tail_heavy_prior_shrinks_outliers_less():
    """03-academic-methods.md 的 Clemente Problem：
    重尾先验应避免把真·离群选手过度收缩回均值。"""
    normal, _ = shrink(20.0, 30, 5.0, 1.0, tail_heavy=False)
    heavy, _ = shrink(20.0, 30, 5.0, 1.0, tail_heavy=True)
    assert heavy > normal


def test_tail_heavy_must_not_defeat_shrinkage_on_tiny_samples():
    """护栏：重尾修正只能削弱收缩，不能取消收缩。

    只打 2 局的离群观测（12.0 对先验 5.0）必须仍被显著拉回，
    否则「Clemente 修正」就把收缩机制本身废掉了。
    """
    tiny, _ = shrink(12.0, n=2, prior_mean=5.0, prior_var=1.0, tail_heavy=True)
    assert tiny < 9.0, "2 局样本的离群值必须被显著收缩"


def test_tail_heavy_weight_still_monotone_in_sample_size():
    """无论是否重尾，样本越多越该信观测。"""
    vals = [shrink(12.0, n, 5.0, 1.0, tail_heavy=True)[0] for n in (2, 5, 20, 100)]
    assert vals == sorted(vals), "后验应随样本量单调上升"
    assert vals[-1] - vals[0] > 2.0, "样本量必须实质性地改变结论"


def test_fit_rate_model_stratifies_by_position():
    rng = np.random.default_rng(0)
    rows = []
    for acct, pos, lam in [(1, 1, 9.0), (2, 5, 3.0)]:
        for g in range(40):
            rows.append({"account_id": acct, "match_id": g, "position": pos,
                         "kills": rng.poisson(lam), "duration_min": 38.0})
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "kills", positions={1: 1, 2: 5})
    assert out[1]["rate"] > out[2]["rate"], "1 号位击杀率应显著高于 5 号位"
    assert out[1]["position"] == 1 and out[2]["position"] == 5
    assert out[1]["n_games"] == 40


def test_fit_rate_model_rejects_unknown_item():
    df = pd.DataFrame({"account_id": [1], "match_id": [1],
                       "position": [1], "duration_min": [30.0]})
    with pytest.raises(KeyError):
        fit_rate_model(df, "no_such_column", positions={1: 1})


# ---- 补充测试：锁定对 brief Step 3 参考实现的三处修正 ----
#
# 1) 参考实现里后验标准误（se）直接用未放大的 prior_var 结算，跟用来算
#    后验均值的 eff_prior_var（重尾放大后的有效先验方差）不是同一个数。
#    对几乎所有真实选手（raw_rate 只要偏离 prior_mean 一点，z2>0，
#    eff_prior_var 就会被放大）这会让 se 系统性偏小——模型一边说
#    "这可能是真实水平，不收缩"，一边却报一个跟没做重尾修正时一样小的
#    标准误，精度被凭空夸大，会直接污染 Task 8 用 se 撑开的置信区间。
#
# 2) 参考实现的 fit_rate_model 只认与 df 列名完全相同的 item_key。但
#    model/fantasy_stats.py 的 docstring 明确写了"跨列合成留给下游
#    （L3 速率模型）"处理：SCORING_ITEMS 18 项里，除 kills/deaths/
#    camps_stacked/stuns 外，其余可用项的 key 与实际列名全部不同
#    （例如 gpm→gold_per_min、tower_kills→towers_killed），Creep Score
#    更是要 last_hits+denies 逐局求和。不解析的话，Task 7 若直接用
#    SCORING_ITEMS 的 key 调用，15 个可得项里有 9 个会直接 KeyError。
#
# 3) 真实数据里 teamfight_participation / stuns 在目标选手+时间窗下
#    各有 54 行是 NaN（fantasy_stats.load_player_games 的 fillna 列表
#    没覆盖这两列——已用 data/pro_player_matches_2020_2026.csv 实测
#    验证：49762 行里 gold_per_min/kills 0 个 NaN，teamfight_participation
#    /stuns 各 54 个 NaN）。参考实现用 len(g)（原始行数）当 n 喂给
#    shrink，会把这些 NaN 行也算进样本量，n_games 偏大、se 被人为拉低。

def test_tail_heavy_se_reflects_inflated_uncertainty_not_just_mean():
    """重尾修正放大的是「有效先验方差」，喂给后验均值的 eff_prior_var
    必须同样喂给后验方差——否则对真·离群值，模型一边几乎不收缩均值，
    一边却报一个和没做重尾修正时一样小的标准误。"""
    _, se_normal = shrink(20.0, 30, 5.0, 1.0, tail_heavy=False)
    _, se_heavy = shrink(20.0, 30, 5.0, 1.0, tail_heavy=True)
    assert se_heavy > se_normal, "重尾修正减少收缩的同时必须相应放大标准误，否则精度被凭空夸大"


def test_fit_rate_model_resolves_creep_score_by_summing_last_hits_and_denies():
    """item_key 用 SCORING_ITEMS 的 key "creep_score"（不是原始列名），
    模型必须自己按 SCORING_ITEMS 声明的 ("last_hits","denies") 逐局求和。"""
    rows = [{"account_id": 1, "match_id": g, "position": 1,
             "last_hits": 300 + g, "denies": 10}
            for g in range(10)]
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "creep_score", positions={1: 1})
    expected_raw = float((df["last_hits"] + df["denies"]).mean())
    assert out[1]["raw_rate"] == pytest.approx(expected_raw)


def test_fit_rate_model_resolves_key_to_mismatched_column_name():
    """SCORING_ITEMS 多数 key 与实际列名不同（gpm→gold_per_min）。
    item_key 传 key 时必须能解析到正确的列，而不是报 KeyError。"""
    rows = [{"account_id": 1, "match_id": g, "position": 1,
             "gold_per_min": 600 + g}
            for g in range(10)]
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "gpm", positions={1: 1})
    assert out[1]["raw_rate"] == pytest.approx(float(df["gold_per_min"].mean()))


def test_fit_rate_model_still_rejects_item_with_no_resolvable_column():
    """madstone 在 SCORING_ITEMS 里 available=False、column=None，
    既不是 df 里的列，也解析不出原始列，必须继续 KeyError，
    不能被 SCORING_ITEMS 兜底成"假装存在"。"""
    df = pd.DataFrame({"account_id": [1], "match_id": [1], "position": [1]})
    with pytest.raises(KeyError):
        fit_rate_model(df, "madstone", positions={1: 1})


def test_fit_rate_model_does_not_inflate_n_games_with_nan_observations():
    """item_key 存在 NaN（例如真实数据里 teamfight_participation /
    stuns 各有 54 行 NaN）时，n_games 必须是有效观测数，不能把 NaN 行
    也计入样本量（否则 obs_var 被低估、se 被人为拉低）。"""
    rows = [{"account_id": 1, "match_id": g, "position": 1, "stuns": 2.0}
            for g in range(8)]
    rows += [{"account_id": 1, "match_id": 100 + g, "position": 1, "stuns": np.nan}
             for g in range(2)]
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "stuns", positions={1: 1})
    assert out[1]["n_games"] == 8, "2 行 NaN 不能被算进样本量"
    assert out[1]["raw_rate"] == pytest.approx(2.0)
