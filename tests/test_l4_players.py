"""task-8-brief.md Step 1：先原样抄录 brief 给的 4 条测试（不删不改，见下方
"brief 原样抄录" 分节），跑一遍确认 `model.l4_players` 不存在、失败原因正确
（Step 2）。再补测试锁定实现阶段发现的修正、关闭"toy 数据凑巧不触发"这类
空白（Task 5/6/7 已经在 idx 编号、se 一致性、号位常量上踩过同类坑：
brief 自带的测试断言与参考实现共享同一个错误前提，两者自洽所以能通过——
但通过不代表对）。

唯一对 brief Step 3 参考实现做了改动的地方：`_interval()` 补一个下界地板
（`max(0.0, lo)`）。原因见下方"补充测试"分节最前面的详细说明——这不是
"削弱断言"：brief 给的 4 条断言全部保持原样、逐字未改，新增测试只是补上
brief 的 toy fixture（rate 全部是 4.0/8.0/9.0，从不触碰 0 附近）结构性
测不出的一个真实数据场景（例如 HULIGANI 这种小样本队伍在低频计分项上，
后验均值本身接近 0 时，对称正态区间的下界会算出负数——"选手场均 Roshan
击杀 [-0.3, 0.5]"这种物理上不可能存在的下界）。
"""
import pytest
from model.l4_players import rank_players, predict_player_stats, _interval, Z95


# ---- brief 给定的 4 条测试（Step 1，原样使用，不可削弱） ----

RATES = {
    1: {"rate": 9.0, "se": 0.5, "position": 1, "n_games": 100},
    2: {"rate": 8.0, "se": 2.5, "position": 1, "n_games": 6},
    3: {"rate": 4.0, "se": 0.4, "position": 5, "n_games": 90},
}
META = {1: ("Yatoro", "Team Spirit"), 2: ("Rookie", "HULIGANI"), 3: ("rue", "Team Spirit")}


def test_ranking_is_within_position_when_requested():
    out = rank_players(RATES, META, by_position=True)
    pos1 = [r for r in out if r["position"] == 1]
    assert [r["account_id"] for r in pos1] == [1, 2]
    assert pos1[0]["rank"] == 1 and pos1[1]["rank"] == 2
    assert [r["rank"] for r in out if r["position"] == 5] == [1]


def test_interval_is_wider_for_small_sample_players():
    out = {r["account_id"]: r for r in rank_players(RATES, META, by_position=True)}
    assert (out[2]["hi"] - out[2]["lo"]) > (out[1]["hi"] - out[1]["lo"])


def test_predict_stats_returns_mean_and_bounds_in_order():
    got = predict_player_stats({"kills": RATES}, ["kills"])
    mean, lo, hi = got[1]["kills"]
    assert lo < mean < hi


def test_missing_meta_falls_back_without_crashing():
    out = rank_players(RATES, {}, by_position=False)
    assert all(r["name"] for r in out)


# ---- 补充测试：锁定实现阶段发现的修正、补齐 toy 数据测不出的空白 ----
#
# 修正：`_interval(rate, se) = rate ± Z95*se` 对称正态区间在 rate 本身接近 0
# 且 se 相对偏大时（典型小样本场景——本任务点名的 HULIGANI 只有 109 场）
# 会算出负的下界。15 个可得计分项（kills/deaths/creep_score/gpm/
# tower_kills/roshan/teamfight/wards/camps_stacked/runes/first_blood/
# stuns/smokes/tormentor/courier）全部是计数或计数类比例，物理上不可能为
# 负——报一个"场均 Roshan 击杀 [-0.3, 0.5]"的下界会直接误导 Step 5 的
# 人工抽查。brief 给的 4 条测试的 toy RATES 三个 rate 分别是 9.0/8.0/4.0、
# se 最大 2.5，7 条 lo 全部远离 0（8-1.96*2.5=3.1 左右），结构上不可能
# 暴露这个问题——跟 Task 6 report 记录的"toy 数据凑巧躲开了错误分支"是
# 同一类空白。只对下界加地板，不处理上界：teamfight_participation /
# first_blood 概念上有 <=1 的上界，但 `_interval`/`rank_players`/
# `predict_player_stats` 都不掌握"这是哪个 item"的信息，不能不分青红皂白
# 地给全部 15 项加上界=1 的截断（例如 kills/gpm 根本没有这个上界），
# 这一点在 model/l4_players.py 的 docstring 和 task-8-report.md 里都会
# 明确记成已知限制，不是漏改。

def test_interval_lower_bound_is_floored_at_zero_for_near_zero_rate():
    """rate 很小、se 相对偏大时，朴素对称区间的下界会算出负数——
    计数类指标的场均速率不可能为负，下界必须被截断在 0。"""
    naive_lo = 0.05 - Z95 * 1.0
    assert naive_lo < 0, "先确认这个输入确实会触发朴素公式算出负下界，否则本测试测不出任何东西"
    lo, hi = _interval(rate=0.05, se=1.0)
    assert lo == 0.0, "计数类指标不可能为负，下界必须截断在 0，不能原样报出负数"
    assert hi == pytest.approx(0.05 + Z95 * 1.0), "上界不做地板处理，不能被这次修正连带改变"


def test_interval_upper_bound_is_not_floored_or_capped():
    """只处理下界，不处理上界——回归防线：以后有人"顺手"把上界也夹到
    某个值（比如误夹到 1）时，这条测试应该失败。"""
    lo, hi = _interval(rate=5.0, se=3.0)
    assert hi == pytest.approx(5.0 + Z95 * 3.0)


def test_interval_unaffected_when_naturally_non_negative():
    """rate 远离 0 时（brief toy 数据的常态），补的地板不应该动到任何数值——
    这是纯粹的边界修正，不是新公式。"""
    lo, hi = _interval(rate=9.0, se=0.5)
    assert lo == pytest.approx(9.0 - Z95 * 0.5)
    assert hi == pytest.approx(9.0 + Z95 * 0.5)


def test_rank_players_and_predict_player_stats_both_floor_via_shared_interval():
    """`rank_players` 和 `predict_player_stats` 都要吃到同一处下界修正——
    不能只改一个入口、留另一个入口继续报负数。"""
    tiny = {9: {"rate": 0.02, "se": 5.0, "position": 3, "n_games": 3}}
    out = rank_players(tiny, {}, by_position=False)
    assert out[0]["lo"] == 0.0

    got = predict_player_stats({"roshan": tiny}, ["roshan"])
    mean, lo, hi = got[9]["roshan"]
    assert lo == 0.0


# ---- 补充测试：brief 自带测试从未真正检验的行为 ----
#
# `test_missing_meta_falls_back_without_crashing` 只断言 `r["name"]` 非空
# （truthy），从未检查 `by_position=False` 时排名数值本身是否正确——
# 一个把全局排名算错（比如漏排、重复排、不跨位置比较）的实现依然能让
# "name 非空"这条断言通过。补一条直接钉住数值的测试，跟 Task 8 brief
# 自己说的"由使用者用 by_position=False 出跨位置总榜"这个用法对齐。

def test_global_ranking_ignores_position_when_by_position_false():
    out = {r["account_id"]: r for r in rank_players(RATES, META, by_position=False)}
    assert out[1]["rank"] == 1  # rate 9.0，全场最高
    assert out[2]["rank"] == 2  # rate 8.0，次高（即使和账号1同为1号位）
    assert out[3]["rank"] == 3  # rate 4.0，全场最低（虽然是本位置里唯一的选手）


def test_predict_stats_merges_multiple_items_per_account_without_overwriting():
    """`out.setdefault(acct, {})[item] = ...` 必须是累加合并，不能是覆盖——
    brief 给的测试只传了一个 item("kills")，结构上测不出"第二个 item
    是否会把第一个 item 的结果覆盖掉"这类 bug。"""
    kills = {1: {"rate": 9.0, "se": 0.5, "position": 1, "n_games": 100}}
    deaths = {1: {"rate": 2.0, "se": 0.2, "position": 1, "n_games": 100}}
    got = predict_player_stats({"kills": kills, "deaths": deaths}, ["kills", "deaths"])
    assert set(got[1]) == {"kills", "deaths"}
    assert got[1]["kills"][0] == pytest.approx(9.0)
    assert got[1]["deaths"][0] == pytest.approx(2.0)
