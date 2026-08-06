"""对 model/l5_window.py 的单元测试（纯函数层，全部走内联 fixture）。"""
import datetime

import pandas as pd
import pytest

from model.patches import patch_ts
from model.l5_window import window_arms, sliding_arms, derive_positions, coarsen


def _utc(y, m, d):
    return int(datetime.datetime(y, m, d, tzinfo=datetime.timezone.utc).timestamp())


TI15_START = _utc(2026, 8, 13)


def test_baseline_arm_l955d_reproduces_the_production_2024_01_01_cutoff():
    """spec §3 的核心口径：现行产线写的是日历日期 2024-01-01，它对 TI15 的
    真实含义是「开赛前 955 天」。这条断言把两者的等价性钉死——baseline 臂
    的定义一旦漂了，整个回测比的就不再是产线策略。"""
    arms = window_arms(TI15_START, "7.41")
    assert arms["L955d"][0] == _utc(2024, 1, 1)


def test_window_arms_has_exactly_the_seven_preregistered_arms():
    arms = window_arms(TI15_START, "7.41")
    assert set(arms) == {"all", "L955d", "L365d", "L180d", "L105d", "patch", "prev_patch"}


def test_patch_arm_starts_exactly_at_the_patch_release_timestamp():
    arms = window_arms(TI15_START, "7.41")
    assert arms["patch"][0] == patch_ts("7.41")
    assert arms["prev_patch"][0] == patch_ts("7.40")


def test_all_arms_end_at_the_event_start():
    """任何一个臂都不许把开赛当天及以后的数据喂进训练——那是数据泄漏。"""
    arms = window_arms(TI15_START, "7.41")
    assert all(until == TI15_START for _, until in arms.values())


def test_all_arm_starts_at_zero():
    assert window_arms(TI15_START, "7.41")["all"][0] == 0


def test_sliding_arms_are_contiguous_non_overlapping_and_complete():
    """固定长度往前滑：段与段首尾相接、不重叠、不留空隙。"""
    arms = sliding_arms(TI15_START, length_days=105, n_steps=4)
    assert list(arms) == ["slide0", "slide1", "slide2", "slide3"]
    assert arms["slide0"][1] == TI15_START
    for k in range(3):
        assert arms["slide%d" % k][0] == arms["slide%d" % (k + 1)][1]
    for since, until in arms.values():
        assert until - since == 105 * 86400


def _pm_rows(match_id, side_offset, net_worths, account_ids):
    """造一方五个人的选手-比赛行。side_offset=0 是天辉，128 是夜魇。"""
    return [{"match_id": match_id, "account_id": a, "player_slot": side_offset + i,
             "net_worth": nw}
            for i, (a, nw) in enumerate(zip(account_ids, net_worths))]


def test_derive_positions_ranks_by_net_worth_within_each_team_side():
    """队内净资产降序 = 1..5 号位。这是本项目唯一可用的号位来源：
    ti_2021_2025_player_matches.csv 自带的 fantasy_role 列有 2240 个 NaN
    且出现 0/3/4 等无法解释的取值，不能用。"""
    rows = (_pm_rows(1, 0, [30000, 25000, 20000, 15000, 10000], [11, 12, 13, 14, 15])
            + _pm_rows(1, 128, [31000, 26000, 21000, 16000, 11000], [21, 22, 23, 24, 25]))
    pos = derive_positions(pd.DataFrame(rows))
    assert pos == {11: 1, 12: 2, 13: 3, 14: 4, 15: 5,
                   21: 1, 22: 2, 23: 3, 24: 4, 25: 5}


def test_derive_positions_follows_net_worth_not_player_slot_order():
    """把净资产顺序反过来，推出的号位必须跟着反——否则说明实现其实是
    在按 player_slot 顺序发号位，那就完全没有信息量了。"""
    rows = _pm_rows(1, 0, [10000, 15000, 20000, 25000, 30000], [11, 12, 13, 14, 15])
    pos = derive_positions(pd.DataFrame(rows))
    assert pos == {11: 5, 12: 4, 13: 3, 14: 2, 15: 1}


def test_derive_positions_takes_the_mode_across_matches():
    """一名选手在两场里是 1 号位、一场里是 2 号位 -> 取众数 1。
    单场的临时换位不该改变他的号位归属。"""
    rows = []
    for mid, nws in [(1, [30000, 25000, 20000, 15000, 10000]),
                     (2, [30000, 25000, 20000, 15000, 10000]),
                     (3, [25000, 30000, 20000, 15000, 10000])]:
        rows += _pm_rows(mid, 0, nws, [11, 12, 13, 14, 15])
    pos = derive_positions(pd.DataFrame(rows))
    assert pos[11] == 1
    assert pos[12] == 2


def test_derive_positions_ignores_rows_with_missing_account_or_net_worth():
    rows = _pm_rows(1, 0, [30000, 25000, 20000, 15000, 10000], [11, 12, 13, 14, 15])
    rows.append({"match_id": 2, "account_id": None, "player_slot": 0, "net_worth": 9999})
    rows.append({"match_id": 2, "account_id": 99, "player_slot": 1, "net_worth": None})
    pos = derive_positions(pd.DataFrame(rows))
    assert 99 not in pos
    assert set(pos) == {11, 12, 13, 14, 15}


def test_coarsen_splits_core_1_to_3_from_support_4_to_5():
    """稳健口径：这个划分在 TI15 的 80 名人工策展选手上与净资产排名
    100% 吻合（15 处不一致全部落在 core 内部或 support 内部）。"""
    assert coarsen({1: 1, 2: 2, 3: 3, 4: 4, 5: 5}) == {
        1: "core", 2: "core", 3: "core", 4: "support", 5: "support"}


from model.l5_window import (score_arm, SKIP_TOO_FEW, SKIP_CONSTANT_PRED,
                             SKIP_CONSTANT_ACTUAL)


def test_score_arm_returns_perfect_correlation_when_ranking_matches():
    rates = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0, 4: 40.0}
    positions = {1: 1, 2: 1, 3: 1, 4: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores[1] == pytest.approx(1.0)
    assert skipped == {}


def test_score_arm_returns_minus_one_when_ranking_is_reversed():
    rates = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0}
    actual = {1: 40.0, 2: 30.0, 3: 20.0, 4: 10.0}
    positions = {1: 1, 2: 1, 3: 1, 4: 1}
    scores, _ = score_arm(rates, actual, positions)
    assert scores[1] == pytest.approx(-1.0)


def test_score_arm_scores_each_position_group_separately():
    """同号位内排序是主判据——绝不能把 1 号位和 5 号位混在一起算，
    那样算出来的高相关只反映"核心补刀比辅助多"，跟选人决策无关。"""
    rates = {1: 1.0, 2: 2.0, 3: 3.0, 4: 30.0, 5: 20.0, 6: 10.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0, 4: 1.0, 5: 2.0, 6: 3.0}
    positions = {1: 1, 2: 1, 3: 1, 4: 5, 5: 5, 6: 5}
    scores, _ = score_arm(rates, actual, positions)
    assert scores[1] == pytest.approx(1.0)
    assert scores[5] == pytest.approx(-1.0)


def test_score_arm_skips_groups_with_fewer_than_three_candidates():
    """候选人不足 3 人的组算不出有意义的 Spearman，跳过——但必须带原因
    出现在 skipped 里，不许静默丢掉。"""
    rates = {1: 1.0, 2: 2.0}
    actual = {1: 10.0, 2: 20.0}
    positions = {1: 1, 2: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores == {}
    assert skipped == {1: SKIP_TOO_FEW}


def test_score_arm_skips_constant_prediction_instead_of_scoring_zero():
    """预测值全同时 Spearman 未定义（NaN）。必须计入跳过，不能当成 0——
    记成 0 会把"算不出来"混进"预测力为零"，直接污染配对检验。"""
    rates = {1: 5.0, 2: 5.0, 3: 5.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0}
    positions = {1: 1, 2: 1, 3: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores == {}
    assert skipped == {1: SKIP_CONSTANT_PRED}


def test_score_arm_skips_constant_actual():
    rates = {1: 1.0, 2: 2.0, 3: 3.0}
    actual = {1: 7.0, 2: 7.0, 3: 7.0}
    positions = {1: 1, 2: 1, 3: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores == {}
    assert skipped == {1: SKIP_CONSTANT_ACTUAL}


def test_score_arm_only_uses_players_present_in_both_rates_and_actual():
    rates = {1: 1.0, 2: 2.0, 3: 3.0, 99: 9.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0}
    positions = {1: 1, 2: 1, 3: 1, 99: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores[1] == pytest.approx(1.0)


def test_score_arm_works_with_string_position_labels_from_coarsen():
    rates = {1: 1.0, 2: 2.0, 3: 3.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0}
    positions = coarsen({1: 1, 2: 2, 3: 3})
    scores, _ = score_arm(rates, actual, positions)
    assert scores["core"] == pytest.approx(1.0)
