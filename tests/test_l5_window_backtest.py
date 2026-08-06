"""对 model/l5_window_backtest.py 编排层的单元测试（全部走内联 fixture，
不读真实 CSV、不打网）。"""
import pandas as pd
import pytest

from model.l5_window_backtest import (HOLDOUTS, ITEMS, BASELINE_ARM, TREATMENT_ARM,
                                      ALPHA, MIN_HOLDOUTS_POSITIVE,
                                      holdout_participants, holdout_actuals,
                                      intersect_players)


def test_preregistered_decision_constants_are_what_the_spec_says():
    """判定规则是预注册的（spec §2）：跑完再改这几个常量就等于事后挑指标。
    这条测试的作用是让任何改动都必须显式地改到测试，而不是悄悄改掉。"""
    assert ALPHA == 0.05
    assert MIN_HOLDOUTS_POSITIVE == 3
    assert BASELINE_ARM == "L955d"
    assert TREATMENT_ARM == "patch"


def test_holdouts_are_the_four_preregistered_ti_events():
    assert [(h["year"], h["patch"]) for h in HOLDOUTS] == [
        ("2022", "7.32"), ("2023", "7.34"), ("2024", "7.37"), ("2025", "7.39")]


def test_items_are_the_twelve_csv_direct_scoring_items():
    """blob 三项 smokes/tormentor/courier 历史届取不到（pro_blob_stats.csv
    只覆盖 TI15 的 80 名选手、2024-01-01 起），必须排除。"""
    assert ITEMS == ["kills", "deaths", "creep_score", "gpm", "tower_kills",
                     "roshan", "teamfight", "wards", "camps_stacked", "runes",
                     "first_blood", "stuns"]
    assert "smokes" not in ITEMS and "tormentor" not in ITEMS and "courier" not in ITEMS


def _pm(rows):
    return pd.DataFrame(rows)


def test_holdout_participants_requires_min_games_in_that_event():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 5}] * 4
            + [{"match_date": "2025-09-05", "account_id": 2, "kills": 5}] * 2
            + [{"match_date": "2024-09-05", "account_id": 3, "kills": 5}] * 9)
    out = holdout_participants(_pm(rows), "2025", min_games=4)
    assert out == {1}


def test_holdout_actuals_averages_per_game_for_the_requested_year_only():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 10}] * 2
            + [{"match_date": "2025-09-06", "account_id": 1, "kills": 20}] * 2
            + [{"match_date": "2024-09-05", "account_id": 1, "kills": 999}] * 5)
    out = holdout_actuals(_pm(rows), "2025", "kills", min_games=4)
    assert out == {1: pytest.approx(15.0)}


def test_holdout_actuals_resolves_creep_score_as_last_hits_plus_denies():
    """预测侧和实际侧必须走同一套列合成（l3_player._resolve_item_values）。
    两边用不同的合成方式是这类回测最容易出、也最难发现的错。"""
    rows = [{"match_date": "2025-09-05", "account_id": 1,
             "last_hits": 300, "denies": 20}] * 4
    out = holdout_actuals(_pm(rows), "2025", "creep_score", min_games=4)
    assert out == {1: pytest.approx(320.0)}


def test_holdout_actuals_drops_players_below_min_games():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 5}] * 4
            + [{"match_date": "2025-09-05", "account_id": 2, "kills": 5}] * 3)
    out = holdout_actuals(_pm(rows), "2025", "kills", min_games=4)
    assert set(out) == {1}


def test_holdout_actuals_counts_only_non_null_rows_toward_min_games():
    """teamfight_participation / stuns 在真实数据里有 NaN。口径必须与
    fit_rate_model 一致：n 按非空计，NaN 行不算出场。"""
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "stuns": 3.0}] * 3
            + [{"match_date": "2025-09-05", "account_id": 1, "stuns": None}] * 5)
    out = holdout_actuals(_pm(rows), "2025", "stuns", min_games=4)
    assert out == {}


def test_intersect_players_keeps_only_players_predicted_by_every_arm():
    """臂之间人群不同就不是配对比较：短窗口会漏掉赛前歇了几个月的人，
    不取交集等于拿"全历史臂上的 18 人"跟"patch 臂上的 12 人"比。"""
    rates_by_arm = {"all": {1: 0.1, 2: 0.2, 3: 0.3},
                    "patch": {1: 0.1, 3: 0.3},
                    "L955d": {1: 0.1, 2: 0.2, 3: 0.3}}
    assert intersect_players(rates_by_arm) == {1, 3}


def test_intersect_players_on_empty_input_is_empty():
    assert intersect_players({}) == set()


from model.l5_window_backtest import fit_arm, run_holdout, decide

# fit_rate_model / holdout_actuals 会解析全部 12 个计分项，所以 fixture 必须
# 把这些原始列都带上，缺一列就是 KeyError。
_STAT_COLS = ["kills", "deaths", "last_hits", "denies", "gold_per_min",
              "towers_killed", "roshans_killed", "teamfight_participation",
              "obs_placed", "camps_stacked", "rune_pickups",
              "firstblood_claimed", "stuns"]


def _stat_row(base, **over):
    """一行选手-比赛数据：12 个计分项全部填成 base 的倍数，便于造出可预期的排序。"""
    row = {c: float(base) for c in _STAT_COLS}
    row.update(over)
    return row


def _train_rows(account_id, start_times, kills):
    """训练侧的选手-比赛行。fit_rate_model 需要 account_id + 计分列；
    derive_positions 不在这里跑，所以 net_worth/player_slot 只是占位。"""
    return [dict(_stat_row(kills), match_id=1000 + i, account_id=account_id,
                 player_slot=0, net_worth=20000, start_time=t)
            for i, t in enumerate(start_times)]


def test_fit_arm_only_uses_rows_inside_the_half_open_window():
    """区间语义 [since, until)：开赛当天那一行必须被排除，否则是数据泄漏。

    三名选手窗口内的 kills 分别是 1 / 5 / 9，窗口外那一行是 99。
    正确排除时 3 号位选手的收缩后速率约 8.5；如果 99 那行漏进来，
    他的速率会跳到 38 上下——所以阈值取 10，能真正把泄漏抓出来
    （写成 50 就抓不到了）。"""
    rows = (_train_rows(1, [100, 200, 300], 1)
            + _train_rows(2, [100, 200, 300], 5)
            + _train_rows(3, [100, 200, 300], 9))
    # 把每人第三行（start_time=300，等于 until）改成异常值
    train = pd.DataFrame(rows)
    train.loc[train["start_time"] == 300, "kills"] = 99.0
    positions = {1: 1, 2: 1, 3: 1}
    rates = fit_arm(train, since=0, until=300, item="kills", positions=positions)
    assert rates[1] < rates[2] < rates[3]
    assert rates[3] < 10


def test_fit_arm_returns_empty_when_the_window_has_no_rows():
    train = pd.DataFrame(_train_rows(1, [100], 5))
    assert fit_arm(train, since=1000, until=2000, item="kills",
                   positions={1: 1}) == {}


def test_run_holdout_uses_the_positions_it_was_given_for_every_arm():
    """号位必须跨臂固定（spec §4）：每臂各推一次会让各臂连分组都不同，
    那就不是配对比较了。这里传入一组正常推导绝不会产生的标签 "X"，
    断言输出单元的 position 正是 "X" —— 若实现内部偷偷重推号位，
    会得到 1..5，测试立刻变红。"""
    train_rows = []
    for a, base in [(1, 1.0), (2, 5.0), (3, 9.0)]:
        train_rows += _train_rows(a, list(range(100, 130)), base)
    train = pd.DataFrame(train_rows)
    pm_rows = []
    for a, base in [(1, 2.0), (2, 6.0), (3, 10.0)]:
        for _ in range(4):
            pm_rows.append(dict(_stat_row(base), match_date="2025-09-05",
                                account_id=a))
    pm = pd.DataFrame(pm_rows)

    positions = {1: "X", 2: "X", 3: "X"}
    arms = {"L955d": (0, 200), "patch": (110, 200)}
    res = run_holdout(train, pm, {"year": "2025", "patch": "7.39"}, positions, arms)

    assert res["units"], "至少要产出一个单元"
    assert {u["position"] for u in res["units"]} == {"X"}


def test_run_holdout_records_intersection_coverage_for_every_item():
    """交集丢掉多少人必须逐项记账——静默截断是这个项目最容易被抓的地方。"""
    train_rows = []
    for a, base in [(1, 1.0), (2, 5.0), (3, 9.0)]:
        train_rows += _train_rows(a, list(range(100, 130)), base)
    # 4 号选手只在早期有数据，短窗口臂里会消失 -> 交集必然收缩
    train_rows += _train_rows(4, list(range(100, 108)), 3.0)
    train = pd.DataFrame(train_rows)
    pm_rows = []
    for a, base in [(1, 2.0), (2, 6.0), (3, 10.0), (4, 4.0)]:
        for _ in range(4):
            pm_rows.append(dict(_stat_row(base), match_date="2025-09-05",
                                account_id=a))
    pm = pd.DataFrame(pm_rows)

    positions = {1: 1, 2: 1, 3: 1, 4: 1}
    arms = {"L955d": (0, 200), "patch": (110, 200)}
    res = run_holdout(train, pm, {"year": "2025", "patch": "7.39"}, positions, arms)

    assert len(res["coverage"]) == len(ITEMS)
    kills_cov = next(c for c in res["coverage"] if c["item"] == "kills")
    assert kills_cov["n_union"] == 4
    assert kills_cov["n_intersection"] == 3
    assert kills_cov["n_dropped_by_intersection"] == 1


def _units(holdout, n_pos, n_neg):
    """造一届的配对单元：n_pos 个 +0.3、n_neg 个 -0.1。"""
    return ([{"holdout": holdout, "item": "kills", "position": i, "diff": 0.3}
             for i in range(n_pos)]
            + [{"holdout": holdout, "item": "deaths", "position": i, "diff": -0.1}
               for i in range(n_neg)])


def test_decide_refuses_to_support_when_only_two_holdouts_agree():
    """预注册的两条判定必须同时满足（spec §2）。这组输入的符号检验
    p = 0.0293（< 0.05）、中位差 +0.3 > 0——第 1 条过了——但只有 2 届
    届内中位差为正，所以结论仍然是"不支持"。这正是加第 2 条的目的：
    挡住"某一两届的特殊情况撑起了全局显著"。"""
    units = _units("2022", 11, 1) + _units("2023", 11, 1) \
        + _units("2024", 5, 7) + _units("2025", 5, 7)
    out = decide(units)
    assert out["sign_test"]["n_pos"] == 32 and out["sign_test"]["n_neg"] == 16
    assert out["sign_test"]["p"] == pytest.approx(0.0293049, abs=1e-6)
    assert out["sign_test"]["median"] > 0
    assert out["n_holdouts_positive"] == 2
    assert out["supported"] is False


def test_decide_supports_when_significant_and_three_of_four_holdouts_positive():
    units = (_units("2022", 12, 0) + _units("2023", 12, 0)
             + _units("2024", 12, 0) + _units("2025", 0, 12))
    out = decide(units)
    assert out["sign_test"]["p"] < ALPHA
    assert out["n_holdouts_positive"] == 3
    assert out["supported"] is True


def test_decide_reports_median_diff_per_holdout():
    units = [{"holdout": "2022", "item": "kills", "position": 1, "diff": 0.1},
             {"holdout": "2022", "item": "kills", "position": 2, "diff": 0.3},
             {"holdout": "2023", "item": "kills", "position": 1, "diff": -0.2}]
    out = decide(units)
    assert out["median_diff_by_holdout"]["2022"] == pytest.approx(0.2)
    assert out["median_diff_by_holdout"]["2023"] == pytest.approx(-0.2)


def test_decide_ignores_units_whose_diff_is_none():
    """某臂在该单元被跳过时 diff 是 None，不能当成 0 参与检验。"""
    units = [{"holdout": "2022", "item": "kills", "position": 1, "diff": 0.1},
             {"holdout": "2022", "item": "roshan", "position": 5, "diff": None}]
    out = decide(units)
    assert out["n_units_compared"] == 1


def test_decide_on_empty_units_is_not_supported():
    out = decide([])
    assert out["supported"] is False
