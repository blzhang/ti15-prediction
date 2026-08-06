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


from model.l5_window_backtest import run_sliding
from model.l5_window import sliding_arms, patch_boundaries_in
from model.patches import patch_ts

_DAY = 86400
# 选一个开赛时间，让四段滑动窗口里至少一段跨版本边界、至少一段不跨：
# 7.39 发布 150 天后开赛时，slide0（开赛前 0-105 天）落在 7.39 之后、
# 早于 7.40，段内无边界；slide1（开赛前 105-210 天）跨过 7.39 发布日；
# slide2 跨过 7.38 发布日；slide3 又无边界。实测见下方各测试。
_SLIDE_EVENT_START = patch_ts("7.39") + 150 * _DAY


def _empty_train_and_pm():
    """占位 train/pm：各一行，列齐全，但 start_time=0（在任何滑动窗口
    之外）、match_date 的年份也不等于所用的 holdout 年份——这样窗口记账
    类的断言不会被真实评分逻辑的副作用干扰。"""
    train = pd.DataFrame(_train_rows(1, [0], 5.0))
    pm = pd.DataFrame([dict(_stat_row(2.0), match_date="2020-01-01", account_id=1)])
    return train, pm


def test_run_sliding_returns_one_entry_per_sliding_arms_window():
    """run_sliding 是台阶检验的骨架：必须跟 sliding_arms 产出的窗口一一
    对应——少一段就看不出台阶，多一段就是凭空多出来的数据点。"""
    train, pm = _empty_train_and_pm()
    holdout = {"year": "2099", "patch": "7.39"}
    out = run_sliding(train, pm, holdout, {1: 1}, _SLIDE_EVENT_START)
    expected_arms = sliding_arms(_SLIDE_EVENT_START)
    assert len(expected_arms) == 4
    assert [entry["arm"] for entry in out] == list(expected_arms.keys())


def test_run_sliding_since_until_match_sliding_arms_for_each_arm():
    """每段的时间边界必须直接来自 sliding_arms 本身的输出，而不是手抄的
    数字——这样两处永远不会悄悄 drift 开。"""
    train, pm = _empty_train_and_pm()
    holdout = {"year": "2099", "patch": "7.39"}
    out = run_sliding(train, pm, holdout, {1: 1}, _SLIDE_EVENT_START)
    expected_arms = sliding_arms(_SLIDE_EVENT_START)
    for entry in out:
        since, until = expected_arms[entry["arm"]]
        assert entry["since_ts"] == since
        assert entry["until_ts"] == until


def test_run_sliding_patch_boundaries_come_from_patch_boundaries_in_and_vary():
    """patch_boundaries 必须是该段自己窗口上 patch_boundaries_in 的结果，
    而且必须真的随窗口变化——如果这个字段跟窗口本身脱钩（比如恒为
    []），台阶检验就没法区分"平滑的近期性衰减"和"版本边界处掉档"。"""
    train, pm = _empty_train_and_pm()
    holdout = {"year": "2099", "patch": "7.39"}
    out = run_sliding(train, pm, holdout, {1: 1}, _SLIDE_EVENT_START)
    for entry in out:
        assert entry["patch_boundaries"] == patch_boundaries_in(
            entry["since_ts"], entry["until_ts"])
    assert any(entry["patch_boundaries"] == [] for entry in out)
    assert any(entry["patch_boundaries"] != [] for entry in out)


def test_run_sliding_window_with_no_training_rows_reports_none_not_zero():
    """窗口里没有训练数据时必须报 None，不能报 0.0——0.0 会被读成"测出来
    是零相关"，但实际上根本没测出任何东西。也不能抛异常：四段窗口里有
    几段没有训练数据是滑动窗口的常态，不是错误。"""
    train, pm = _empty_train_and_pm()
    holdout = {"year": "2099", "patch": "7.39"}
    out = run_sliding(train, pm, holdout, {1: 1}, _SLIDE_EVENT_START)
    assert len(out) == 4
    for entry in out:
        assert entry["mean_spearman"] is None
        assert entry["n_scored_units"] == 0


def test_run_sliding_mean_spearman_is_the_mean_over_scored_item_position_units():
    """mean_spearman 必须是所有 (item, position) 打分单元的算术平均——不是
    只取某一个计分项、也不是加权平均。构造 12 个计分项里 11 个正相关、
    1 个（kills）反相关的 fixture：账号 1/2/3 除 kills 外的所有项都按
    base=1/5/9 递增，kills 单独反过来按 9/5/1；实际值（actual）按
    2/6/10 递增。这样 11 项 rho=+1.0、kills 项 rho=-1.0，期望的均值是
    可以手算的 (11*1 + 1*(-1)) / 12 = 5/6，不是随便挑一项的结果。"""
    since, until = sliding_arms(_SLIDE_EVENT_START)["slide0"]
    mid = (since + until) // 2
    times = [mid, mid + 1000, mid + 2000, mid + 3000]

    train_rows = []
    for account_id, base, kills_override in [(1, 1.0, 9.0), (2, 5.0, 5.0), (3, 9.0, 1.0)]:
        for i, t in enumerate(times):
            train_rows.append(dict(_stat_row(base, kills=kills_override),
                                   match_id=1000 + i, account_id=account_id,
                                   player_slot=0, net_worth=20000, start_time=t))
    train = pd.DataFrame(train_rows)

    pm_rows = []
    for account_id, base in [(1, 2.0), (2, 6.0), (3, 10.0)]:
        for _ in range(4):
            pm_rows.append(dict(_stat_row(base), match_date="2025-09-05",
                                account_id=account_id))
    pm = pd.DataFrame(pm_rows)

    positions = {1: "X", 2: "X", 3: "X"}
    holdout = {"year": "2025", "patch": "7.39"}
    out = run_sliding(train, pm, holdout, positions, _SLIDE_EVENT_START)

    slide0 = next(entry for entry in out if entry["arm"] == "slide0")
    assert slide0["n_scored_units"] == len(ITEMS)
    assert slide0["mean_spearman"] == pytest.approx(5.0 / 6.0)

    # 训练行全部落在 slide0 窗口内，其余三段窗口没有任何训练数据，
    # 必须是 None，不能被悄悄记成 0 而拉低/污染整体印象。
    for entry in out:
        if entry["arm"] != "slide0":
            assert entry["mean_spearman"] is None


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


from model.l5_window_backtest import render_markdown


def _minimal_report(supported=False):
    return {
        "generated_by": "model/l5_window_backtest.py",
        "spec": "docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md",
        "baseline_arm": "L955d", "treatment_arm": "patch",
        "alpha": 0.05, "min_holdouts_positive": 3,
        "items_covered": "12/15",
        "excluded_items": ["smokes", "tormentor", "courier"],
        "holdouts": ["2022", "2023", "2024", "2025"],
        "holdout_meta": [{"holdout": y, "patch": p} for y, p in
                         [("2022", "7.32"), ("2023", "7.34"),
                          ("2024", "7.37"), ("2025", "7.39")]],
        "decision": {"sign_test": {"n_pos": 100, "n_neg": 110, "n_zero": 0,
                                   "median": -0.01, "p": 0.55},
                     "median_diff_by_holdout": {"2022": -0.02, "2023": 0.01,
                                                "2024": -0.03, "2025": 0.00},
                     "n_holdouts_positive": 1, "n_units_compared": 210,
                     "supported": supported},
        "coverage": [{"holdout": "2022", "item": "kills", "n_union": 20,
                      "n_intersection": 14, "n_dropped_by_intersection": 6}],
        "skipped": [{"holdout": "2022", "item": "roshan", "arm": "patch",
                     "position": 5, "reason": "预测值全同"}],
        "sliding": [{"holdout": "2025", "arm": "slide0", "mean_spearman": 0.21,
                     "patch_boundaries": []}],
    }


def test_render_markdown_states_the_conclusion_without_overclaiming():
    """判不出显著时，报告必须说"没有证据支持"，不能说成"证明了两者一样"
    ——那是本次样本量给不出的结论（spec §8）。"""
    md = render_markdown(_minimal_report(supported=False))
    assert "没有证据支持" in md
    assert "证明两者一样" not in md


def test_render_markdown_always_reports_dropped_and_skipped_counts():
    """静默截断是这个项目最容易再被读者抓的地方——交集丢掉的人数和
    跳过的单元数必须出现在报告正文里。"""
    md = render_markdown(_minimal_report())
    # 光断言 "6" in md 是没用的：一个裸数字在任何一版渲染里几乎都能撞上。
    assert "共丢弃 **6** 人次" in md
    assert "跳过的单元 **1** 个" in md
    assert "预测值全同：1" in md


def test_render_markdown_states_item_coverage_is_12_of_15():
    md = render_markdown(_minimal_report())
    assert "12/15" in md
    assert "smokes" in md


from model.l5_window_backtest import (ROBUSTNESS_MIN_GAMES, run_robustness,
                                      aggregate_robustness)


def test_robustness_min_games_are_the_preregistered_three_and_eight():
    assert ROBUSTNESS_MIN_GAMES == (3, 8)


def _tiny_holdout_frames():
    """三名选手、训练侧各 30 局、TI 侧各 8 局，12 个计分项列齐。"""
    train_rows = []
    for a, base in [(1, 1.0), (2, 5.0), (3, 9.0)]:
        train_rows += _train_rows(a, list(range(100, 130)), base)
    pm_rows = []
    for a, base in [(1, 2.0), (2, 6.0), (3, 10.0)]:
        for _ in range(8):
            pm_rows.append(dict(_stat_row(base), match_date="2025-09-05",
                                account_id=a))
    return pd.DataFrame(train_rows), pd.DataFrame(pm_rows)


def test_run_robustness_produces_exactly_three_variants():
    train, pm = _tiny_holdout_frames()
    arms = {"L955d": (0, 200), "patch": (110, 200), "all": (0, 200)}
    out = run_robustness(train, pm, {"year": "2025", "patch": "7.39"},
                         {1: 1, 2: 1, 3: 1}, arms)
    assert [r["variant"] for r in out] == ["coarse_position", "min_games=3",
                                           "min_games=8"]


def test_run_robustness_only_uses_the_treatment_and_baseline_arms():
    """变体只为交叉验证主结论，不需要另外五个臂——跑全套是三倍的成本
    换不来信息。"""
    train, pm = _tiny_holdout_frames()
    arms = {"L955d": (0, 200), "patch": (110, 200), "all": (0, 200)}
    out = run_robustness(train, pm, {"year": "2025", "patch": "7.39"},
                         {1: 1, 2: 1, 3: 1}, arms)
    arms_seen = {a for r in out for u in r["units"] for a in u["spearman"]}
    assert arms_seen == {BASELINE_ARM, TREATMENT_ARM}


def test_run_robustness_coarse_variant_groups_by_core_and_support():
    train, pm = _tiny_holdout_frames()
    arms = {"L955d": (0, 200), "patch": (110, 200)}
    out = run_robustness(train, pm, {"year": "2025", "patch": "7.39"},
                         {1: 1, 2: 2, 3: 3}, arms)
    coarse = next(r for r in out if r["variant"] == "coarse_position")
    assert {u["position"] for u in coarse["units"]} == {"core"}


def test_aggregate_robustness_merges_units_by_variant_and_decides_each():
    runs = [
        {"variant": "coarse_position",
         "units": [{"holdout": "2022", "item": "kills", "position": "core",
                    "diff": 0.4}]},
        {"variant": "coarse_position",
         "units": [{"holdout": "2023", "item": "kills", "position": "core",
                    "diff": 0.2}]},
        {"variant": "min_games=3",
         "units": [{"holdout": "2022", "item": "kills", "position": 1,
                    "diff": -0.1}]},
    ]
    out = aggregate_robustness(runs)
    assert set(out) == {"coarse_position", "min_games=3"}
    assert out["coarse_position"]["n_units_compared"] == 2
    assert out["min_games=3"]["sign_test"]["n_neg"] == 1


def test_render_markdown_includes_a_robustness_section_when_present():
    report = _minimal_report()
    report["robustness"] = {
        "coarse_position": {"sign_test": {"p": 0.42, "median": -0.01,
                                          "n_pos": 30, "n_neg": 34, "n_zero": 0},
                            "median_diff_by_holdout": {}, "n_holdouts_positive": 1,
                            "n_units_compared": 64, "supported": False}}
    md = render_markdown(report)
    assert "稳健性" in md
    assert "coarse_position" in md


# ---- 稳健性变体的 skipped 必须带原因进报告（不许悄悄丢数据）----------------


def _skip_prone_frames():
    """4 名选手、位置刻意拆成两两一组，两个变体口径下每个号位组都不足
    MIN_CANDIDATES(3) 人——这个 fixture 是专门用来稳定触发跳过的，不是用来
    测打分本身。"""
    train_rows = []
    for a, base in [(1, 1.0), (2, 5.0), (3, 9.0), (4, 3.0)]:
        train_rows += _train_rows(a, list(range(100, 130)), base)
    pm_rows = []
    for a, base in [(1, 2.0), (2, 6.0), (3, 10.0), (4, 4.0)]:
        for _ in range(8):
            pm_rows.append(dict(_stat_row(base), match_date="2025-09-05",
                                account_id=a))
    return pd.DataFrame(train_rows), pd.DataFrame(pm_rows)


def test_run_robustness_attributes_skipped_units_to_their_variant():
    """三个变体各自跑 run_holdout，各自的 skipped 不能被扔掉——必须带上
    是哪个变体产生的，原因字段原样保留（不能被摘要成一个数字）。"""
    train, pm = _skip_prone_frames()
    # coarsen 下 1/2 -> core、4/5 -> support，各 2 人；原始分组下
    # 1 有 2 人、4 和 5 各 1 人——两种口径都必然低于 MIN_CANDIDATES(3)。
    positions = {1: 1, 2: 1, 3: 4, 4: 5}
    arms = {"L955d": (0, 200), "patch": (110, 200), "all": (0, 200)}
    out = run_robustness(train, pm, {"year": "2025", "patch": "7.39"},
                         positions, arms)

    coarse = next(r for r in out if r["variant"] == "coarse_position")
    assert coarse["skipped"], "core/support 都只有 2 人，必然全部跳过"
    assert all(s["variant"] == "coarse_position" for s in coarse["skipped"])
    assert all(s["position"] in ("core", "support") for s in coarse["skipped"])
    assert all(s["reason"] == "候选人不足3" for s in coarse["skipped"])
    assert all(s["arm"] in (BASELINE_ARM, TREATMENT_ARM) for s in coarse["skipped"])
    assert all(s["holdout"] == "2025" for s in coarse["skipped"])

    mg3 = next(r for r in out if r["variant"] == "min_games=3")
    assert mg3["skipped"]
    assert all(s["variant"] == "min_games=3" for s in mg3["skipped"])
    assert all(s["position"] in (1, 4, 5) for s in mg3["skipped"])

    mg8 = next(r for r in out if r["variant"] == "min_games=8")
    assert mg8["skipped"]
    assert all(s["variant"] == "min_games=8" for s in mg8["skipped"])


def test_aggregate_robustness_merges_skipped_by_variant_across_holdouts():
    """同一变体跨多届的 skipped 要合并，不同变体之间不能串。"""
    runs = [
        {"variant": "coarse_position", "units": [],
         "skipped": [{"holdout": "2022", "item": "kills", "arm": "patch",
                      "position": "support", "reason": "候选人不足3",
                      "variant": "coarse_position"}]},
        {"variant": "coarse_position", "units": [],
         "skipped": [{"holdout": "2023", "item": "deaths", "arm": "L955d",
                      "position": "core", "reason": "预测值全同",
                      "variant": "coarse_position"}]},
        {"variant": "min_games=3", "units": [],
         "skipped": [{"holdout": "2022", "item": "kills", "arm": "patch",
                      "position": 4, "reason": "候选人不足3",
                      "variant": "min_games=3"}]},
    ]
    out = aggregate_robustness(runs)
    assert len(out["coarse_position"]["skipped"]) == 2
    assert {s["holdout"] for s in out["coarse_position"]["skipped"]} == {"2022", "2023"}
    assert len(out["min_games=3"]["skipped"]) == 1
    assert out["min_games=3"]["skipped"][0]["position"] == 4
    # 不能因为加了 skipped 就破坏既有的返回形状。
    assert out["coarse_position"]["n_units_compared"] == 0
    assert out["coarse_position"]["supported"] is False


def test_render_markdown_shows_per_variant_skip_counts_and_reasons():
    """每个变体的跳过数与原因分布要能在报告正文里看到，风格跟主路径的
    跳过小节一致；某个变体零跳过时不能崩，也要能看出是 0。"""
    report = _minimal_report()
    report["robustness"] = {
        "coarse_position": {
            "sign_test": {"p": 0.42, "median": -0.01,
                         "n_pos": 30, "n_neg": 34, "n_zero": 0},
            "median_diff_by_holdout": {}, "n_holdouts_positive": 1,
            "n_units_compared": 64, "supported": False,
            "skipped": ([{"holdout": "2022", "item": "kills", "arm": "patch",
                         "position": "support", "reason": "候选人不足3",
                         "variant": "coarse_position"}] * 3
                       + [{"holdout": "2022", "item": "deaths", "arm": "L955d",
                          "position": "core", "reason": "预测值全同",
                          "variant": "coarse_position"}]),
        },
        "min_games=8": {
            "sign_test": {"p": 0.10, "median": 0.02,
                         "n_pos": 40, "n_neg": 20, "n_zero": 0},
            "median_diff_by_holdout": {}, "n_holdouts_positive": 3,
            "n_units_compared": 60, "supported": True,
            "skipped": [],
        },
    }
    md = render_markdown(report)
    assert "跳过 4 个" in md
    assert "候选人不足3：3" in md
    assert "预测值全同：1" in md
    assert "min_games=8" in md
    assert "跳过 0 个" in md


# ---- 复审整改：报告必须把七个臂的对照与窗口长度分解带给读者 -----------------

from model.l5_window_backtest import (CONTROL_ARM, PROPOSAL_PATCH,
                                      arm_diff_units, compare_arms_to_baseline,
                                      median_diff_by_holdout,
                                      identical_units_by_holdout,
                                      window_sample_profile, baseline_overlap,
                                      proposal_window_days, build_exploratory,
                                      participant_game_counts)


def _spearman_units(rows):
    """rows = [(holdout, item, position, {arm: rho})] -> units 形状。"""
    return [{"holdout": h, "item": it, "position": p, "spearman": dict(s),
             "diff": (None if (s.get(TREATMENT_ARM) is None or s.get(BASELINE_ARM) is None)
                      else float(s[TREATMENT_ARM] - s[BASELINE_ARM]))}
            for h, it, p, s in rows]


def test_arm_diff_units_pairs_each_arm_against_the_baseline():
    units = _spearman_units([
        ("2022", "kills", 1, {"L955d": 0.10, "patch": 0.30, "L180d": 0.50}),
    ])
    assert [u["diff"] for u in arm_diff_units(units, "L180d")] == [pytest.approx(0.40)]
    assert [u["diff"] for u in arm_diff_units(units, "patch")] == [pytest.approx(0.20)]


def test_arm_diff_units_leaves_diff_none_when_either_side_is_missing():
    """某臂在该单元被跳过时不能记成 0——那会把"算不出来"混进"没有差异"。"""
    units = _spearman_units([("2022", "kills", 1, {"L955d": 0.1, "patch": None,
                                                   "L180d": 0.5})])
    units[0]["spearman"]["L180d"] = None
    assert arm_diff_units(units, "L180d")[0]["diff"] is None
    units[0]["spearman"]["L180d"] = 0.5
    units[0]["spearman"]["L955d"] = None
    assert arm_diff_units(units, "L180d")[0]["diff"] is None


def test_compare_arms_to_baseline_covers_every_arm_except_the_baseline_itself():
    """报告里五个臂一个数字都没有，是这次复审的头号问题：读者只看得到
    treatment 输了，看不到别的臂赢了多少。"""
    units = _spearman_units([
        ("2022", "kills", 1, {"L955d": 0.1, "patch": 0.2, "L180d": 0.3, "all": 0.0}),
    ])
    out = compare_arms_to_baseline(units)
    assert set(out) == {"patch", "L180d", "all"}
    assert BASELINE_ARM not in out


def test_compare_arms_to_baseline_reuses_the_headline_decide_rule_exactly():
    """探索性对照必须跟主判定跑同一套 decide()，否则"同一把尺子"这句话
    就是假的。treatment 那一格必须与主判定逐位相同。"""
    rows = []
    for h in ("2022", "2023", "2024", "2025"):
        for i in range(6):
            rows.append((h, "kills", i, {"L955d": 0.1, "patch": 0.1 + 0.01 * (i - 2),
                                         "L180d": 0.4}))
    units = _spearman_units(rows)
    out = compare_arms_to_baseline(units)
    assert out[TREATMENT_ARM] == decide(units)


def test_median_diff_by_holdout_compares_two_arbitrary_arms_per_holdout():
    units = _spearman_units([
        ("2022", "kills", 1, {"L955d": 0.0, "patch": 0.1, "L105d": 0.5}),
        ("2022", "kills", 2, {"L955d": 0.0, "patch": 0.3, "L105d": 0.5}),
        ("2025", "kills", 1, {"L955d": 0.0, "patch": 0.5, "L105d": 0.5}),
    ])
    out = median_diff_by_holdout(units, "patch", "L105d")
    assert out["2022"] == pytest.approx(-0.3)
    assert out["2025"] == pytest.approx(0.0)


def test_identical_units_by_holdout_counts_exact_ties_between_two_arms():
    """all 与 baseline 在最早那届几乎重合（spec §3 的已知弱点）——"几乎重合"
    必须能用数字讲出来，不能只靠一句话。"""
    units = _spearman_units([
        ("2022", "kills", 1, {"L955d": 0.4, "all": 0.4, "patch": 0.1}),
        ("2022", "kills", 2, {"L955d": 0.4, "all": 0.2, "patch": 0.1}),
        ("2025", "kills", 1, {"L955d": 0.4, "all": 0.1, "patch": 0.1}),
    ])
    out = identical_units_by_holdout(units, "all", BASELINE_ARM)
    assert out["2022"]["n_units"] == 2 and out["2022"]["n_identical"] == 1
    assert out["2025"]["n_identical"] == 0


def test_window_sample_profile_counts_only_players_present_in_the_window():
    """窗内一局都没有的选手根本进不了该臂的预测，也就进不了配对交集。
    把他们按 0 局混进中位数，会把"样本稀薄"和"人直接消失"两件事搅在一起
    ——两个数都要分开报。"""
    rows = _train_rows(1, [100, 110, 120], 1.0) + _train_rows(2, [10], 5.0)
    train = pd.DataFrame(rows)
    prof = window_sample_profile(train, (50, 50 + 4 * 86400), n_players_total=3)
    assert prof["window_days"] == 4
    assert prof["n_players_total"] == 3
    assert prof["n_players_in_window"] == 1          # 只有 1 号在窗内
    assert prof["n_players_absent_from_window"] == 2
    assert prof["median_games_in_window"] == pytest.approx(3.0)


def test_window_sample_profile_reports_share_below_l3_players_own_variance_floor():
    """低于 l3_player.MIN_N_FOR_OWN_GAME_VAR 的选手拿不到自身局内方差估计，
    只能退回号位先验——这是版本臂真正的代价，必须量化。"""
    from model.l3_player import MIN_N_FOR_OWN_GAME_VAR
    rows = _train_rows(1, list(range(100, 100 + MIN_N_FOR_OWN_GAME_VAR + 5)), 1.0)
    rows += _train_rows(2, [100, 110], 5.0)
    train = pd.DataFrame(rows)
    prof = window_sample_profile(train, (0, 10 ** 6), n_players_total=2)
    assert prof["min_n_for_own_game_var"] == MIN_N_FOR_OWN_GAME_VAR
    assert prof["pct_below_min_n"] == pytest.approx(50.0)


def test_window_sample_profile_on_an_empty_window_is_none_not_zero():
    train = pd.DataFrame(_train_rows(1, [100], 1.0))
    prof = window_sample_profile(train, (10 ** 6, 2 * 10 ** 6), n_players_total=1)
    assert prof["n_players_in_window"] == 0
    assert prof["median_games_in_window"] is None
    assert prof["pct_below_min_n"] is None


def test_baseline_overlap_measures_how_much_of_all_the_baseline_already_covers():
    train = pd.DataFrame(_train_rows(1, [10, 20, 30, 40], 1.0))
    arms = {"all": (0, 100), BASELINE_ARM: (25, 100)}
    out = baseline_overlap(train, arms)
    assert out["n_rows_all"] == 4
    assert out["n_rows_baseline"] == 2
    assert out["baseline_share_of_all"] == pytest.approx(0.5)


def test_proposal_window_days_is_derived_from_the_patch_table_not_typed_in():
    """读者提的是 7.41（142 天），比本次回测里任何一届的版本窗口都长——
    这个天数必须从 patches.py 推出来，改了版本表就跟着变。"""
    assert proposal_window_days() == 142
    assert PROPOSAL_PATCH == "7.41"


def test_participant_game_counts_returns_games_per_participant():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 5}] * 6
            + [{"match_date": "2025-09-05", "account_id": 2, "kills": 5}] * 2)
    assert participant_game_counts(_pm(rows), "2025", min_games=4) == {1: 6}


def _exploratory_holdout_meta():
    return [
        {"holdout": "2022", "patch": "7.32", "min_games_among_participants": 18,
         "patch_window": {"window_days": 52, "n_players_total": 100,
                          "n_players_in_window": 69,
                          "n_players_absent_from_window": 31,
                          "median_games_in_window": 20.0,
                          "min_n_for_own_game_var": 20, "pct_below_min_n": 43.5},
         "baseline_overlap": {"n_rows_all": 50620, "n_rows_baseline": 48295,
                              "baseline_share_of_all": 0.954}},
        {"holdout": "2025", "patch": "7.39", "min_games_among_participants": 10,
         "patch_window": {"window_days": 104, "n_players_total": 80,
                          "n_players_in_window": 80,
                          "n_players_absent_from_window": 0,
                          "median_games_in_window": 55.0,
                          "min_n_for_own_game_var": 20, "pct_below_min_n": 6.2},
         "baseline_overlap": {"n_rows_all": 80162, "n_rows_baseline": 44709,
                              "baseline_share_of_all": 0.558}},
    ]


def test_build_exploratory_bundles_every_arm_and_the_control_comparison():
    units = _spearman_units([
        ("2022", "kills", 1, {"L955d": 0.1, "patch": 0.0, "L180d": 0.4, "L105d": 0.3}),
        ("2025", "kills", 1, {"L955d": 0.1, "patch": 0.3, "L180d": 0.4, "L105d": 0.3}),
    ])
    ex = build_exploratory(units, _exploratory_holdout_meta())
    assert ex["control_arm"] == CONTROL_ARM
    assert set(ex["arm_vs_baseline"]) == {"patch", "L180d", "L105d"}
    assert ex["median_diff_vs_control_by_holdout"]["2022"] == pytest.approx(-0.3)
    assert ex["median_diff_vs_control_by_holdout"]["2025"] == pytest.approx(0.0)
    assert ex["proposal"]["window_days"] == proposal_window_days()
    assert ex["historical_patch_window_days"] == {"min": 52, "max": 104}


def _report_with_exploratory(supported=False):
    report = _minimal_report(supported=supported)
    report["holdout_meta"] = _exploratory_holdout_meta()
    units = _spearman_units([
        ("2022", "kills", 1, {"L955d": 0.10, "patch": 0.00, "L180d": 0.40,
                              "L105d": 0.30, "all": 0.10}),
        ("2025", "kills", 1, {"L955d": 0.10, "patch": 0.30, "L180d": 0.40,
                              "L105d": 0.30, "all": 0.20}),
    ])
    report["exploratory"] = build_exploratory(units, report["holdout_meta"])
    return report


def test_render_markdown_puts_every_arm_in_the_report_body():
    """复审的头号问题：七个臂里只有 treatment 的数字到得了读者眼前。"""
    md = render_markdown(_report_with_exploratory())
    for arm in ("L180d", "L105d", "all", "patch"):
        assert arm in md


def test_render_markdown_renders_the_arm_table_from_the_data_not_from_a_constant():
    """表格必须由产出物算出来。把某个臂的中位差改掉，渲染必须跟着变——
    手抄一张表能骗过"臂名出现在正文里"这种断言，骗不过这一条。"""
    report = _report_with_exploratory()
    report["exploratory"]["arm_vs_baseline"]["L180d"]["sign_test"]["median"] = 0.1234
    md = render_markdown(report)
    assert "+0.1234" in md
    report["exploratory"]["arm_vs_baseline"]["L180d"]["sign_test"]["median"] = -0.4321
    assert "-0.4321" in render_markdown(report)
    assert "+0.1234" not in render_markdown(report)


def test_render_markdown_labels_the_exploratory_section_as_not_preregistered():
    """探索性结论最容易被读成"报告推荐改成 L180d"。三句话必须都在：
    非预注册、单元不独立、不构成改 since_ts 的依据。"""
    md = render_markdown(_report_with_exploratory())
    assert "探索性" in md and "非预注册" in md
    assert "不独立" in md
    assert "since_ts" in md
    assert "预注册" in md.split("## 探索性分析")[1]


def test_render_markdown_keeps_the_preregistered_verdict_ahead_of_the_exploratory_part():
    """预注册结论是头条，必须在探索性内容之前——顺序一反，读者读到的就是
    "其实短窗口更好"，而不是"没有证据支持切版本窗口"。"""
    md = render_markdown(_report_with_exploratory())
    assert md.index("没有证据支持") < md.index("## 探索性分析")
    assert md.index("## 结论") < md.index("## 探索性分析")


def test_render_markdown_reports_patch_window_length_and_small_sample_share():
    """版本臂的亏损按窗口长度分解：窗口越短、低于自身方差门槛的人越多。"""
    md = render_markdown(_report_with_exploratory())
    assert "52" in md and "104" in md          # 版本窗口长度
    assert "43.5" in md and "6.2" in md        # 低于门槛的比例
    assert "20" in md                          # MIN_N_FOR_OWN_GAME_VAR


def test_render_markdown_names_the_matched_length_control_holdout():
    """(a) 版本边界在窗口长度对齐后不花钱——靠的是版本窗口最长那一届
    与等长日历窗口的对照，这一届必须被点名。"""
    md = render_markdown(_report_with_exploratory())
    tail = md.split("## 探索性分析")[1]
    assert CONTROL_ARM in tail
    assert "TI2025" in tail


def test_render_markdown_says_the_proposal_is_longer_than_anything_backtested():
    """(c) 读者提的 7.41 窗口是 142 天，比四届历史版本窗口都长——本次回测
    根本没测到提议本身，报告必须自己说破。"""
    md = render_markdown(_report_with_exploratory())
    assert str(proposal_window_days()) in md
    assert PROPOSAL_PATCH in md


def test_render_markdown_restores_the_spec_known_weakness_about_all_vs_baseline():
    """spec §3 写了、计划里掉了的已知弱点：训练数据下限 2020-01，最早那届的
    baseline 几乎盖满了 all，这一届对「all vs baseline」没有信息量。"""
    md = render_markdown(_report_with_exploratory())
    tail = md.split("## 探索性分析")[1]
    assert "95.4" in tail          # baseline 覆盖 all 的比例
    assert "55.8" in tail
    assert "2020" in tail


# ---- 反过度声称的告诫必须真的被钉住（原断言那句话仓库里根本不存在）--------


def test_render_markdown_keeps_the_anti_overclaim_caveat_when_not_supported():
    """原来的断言写的是「"证明两者一样" not in md」，而这句话仓库里压根
    没有——把整段告诫删掉，那条测试照样绿。这里钉的是告诫本身。"""
    md = render_markdown(_minimal_report(supported=False))
    assert "「没有证据支持」不等于「两者已被证明等价」" in md
    assert "检验力" in md


def test_render_markdown_never_claims_the_two_windows_are_proven_equivalent():
    """「两者已被证明等价」只允许出现在那句否定里；任何形式的等价声称都不行。"""
    md = render_markdown(_minimal_report(supported=False))
    assert md.count("两者已被证明等价") == md.count("不等于「两者已被证明等价」")
    for phrase in ("证明两者一样", "证明了两者一样", "两者一样", "已证明等价"):
        assert phrase not in md


# ---- 稳健性：方向列、门槛空检验、units 随变体入库 --------------------------


def _robustness_report(variants):
    report = _minimal_report()
    report["robustness"] = variants
    return report


def _variant(median, p, n_pos=30, n_neg=34, n_holdouts_positive=1, supported=False,
             n_units=64):
    return {"sign_test": {"p": p, "median": median, "n_pos": n_pos, "n_neg": n_neg,
                          "n_zero": 0},
            "median_diff_by_holdout": {}, "n_holdouts_positive": n_holdouts_positive,
            "n_units_compared": n_units, "supported": supported}


def test_render_markdown_direction_column_compares_median_sign_not_the_supported_flag():
    """原实现比的是两个 supported 布尔值，而"不支持"有好几种理由，两边都
    False 就渲染成「是」。构造一个中位差**强烈为正**、只是届数不够所以
    supported=False 的变体：主结果中位差为负，方向明明相反，必须是「否」。"""
    md = render_markdown(_robustness_report({"flipped": _variant(+0.25, 0.001,
                                                                 n_pos=60, n_neg=4)}))
    row = next(ln for ln in md.splitlines() if ln.startswith("| flipped "))
    assert row.rstrip().endswith("否 |"), row


def test_render_markdown_direction_column_says_yes_when_the_median_agrees_in_sign():
    md = render_markdown(_robustness_report({"agree": _variant(-0.03, 0.30)}))
    row = next(ln for ln in md.splitlines() if ln.startswith("| agree "))
    assert row.rstrip().endswith("是 |"), row


def test_render_markdown_flags_a_variant_that_is_significantly_against_the_treatment():
    """coarse_position 在 α 下显著、且中位差为负——粗分组下 treatment 显著
    **更差**。这是全场最扎眼的一个数字，不能一句话都不说。"""
    md = render_markdown(_robustness_report({"coarse_position": _variant(-0.0257, 0.0184)}))
    tail = md.split("## 稳健性变体")[1]
    assert "coarse_position" in tail
    assert "更差" in tail
    assert "0.0184" in tail


def test_render_markdown_does_not_flag_a_non_significant_variant_as_against():
    md = render_markdown(_robustness_report({"coarse_position": _variant(-0.0257, 0.42)}))
    assert "更差" not in md.split("## 稳健性变体")[1]


def test_render_markdown_calls_the_min_games_variants_vacuous_when_identical():
    """build_report 把 positions/train 冻结在 MIN_HOLDOUT_GAMES 上之后，
    放宽到 3 在构造上不可能再收进任何选手；实测两个变体与主结果逐位相同。
    报告不能把空检验摆成"通过了的稳健性检查"。"""
    d = _minimal_report()["decision"]
    same = _variant(d["sign_test"]["median"], d["sign_test"]["p"],
                    n_pos=d["sign_test"]["n_pos"], n_neg=d["sign_test"]["n_neg"],
                    n_units=d["n_units_compared"])
    md = render_markdown(_robustness_report({"min_games=3": same,
                                             "min_games=8": dict(same)}))
    tail = md.split("## 稳健性变体")[1]
    assert "空检验" in tail
    assert "min_games=3" in tail and "min_games=8" in tail


def test_render_markdown_does_not_call_a_min_games_variant_vacuous_when_it_differs():
    md = render_markdown(_robustness_report({"min_games=8": _variant(+0.02, 0.10)}))
    assert "空检验" not in md.split("## 稳健性变体")[1]


def test_render_markdown_reports_the_minimum_games_per_participant_per_holdout():
    """门槛敏感性为什么是空的，要有数：四届参赛者的最少出场局数本身就在
    ROBUSTNESS_MIN_GAMES 之上。"""
    report = _report_with_exploratory()
    report["robustness"] = {"min_games=3": _variant(-0.01, 0.55)}
    md = render_markdown(report)
    assert "18" in md and "10" in md


def test_aggregate_robustness_carries_units_into_each_variant():
    """只有 decide() 的汇总能进 JSON 的话，coarse_position 的 p=0.0184 就没法
    像主结论那样被独立复核。不许悄悄丢数据。"""
    runs = [
        {"variant": "coarse_position", "units": [
            {"holdout": "2022", "item": "kills", "position": "core", "diff": 0.4}]},
        {"variant": "coarse_position", "units": [
            {"holdout": "2023", "item": "kills", "position": "core", "diff": 0.2}]},
        {"variant": "min_games=3", "units": [
            {"holdout": "2022", "item": "kills", "position": 1, "diff": -0.1}]},
    ]
    out = aggregate_robustness(runs)
    assert [u["diff"] for u in out["coarse_position"]["units"]] == [0.4, 0.2]
    assert [u["holdout"] for u in out["coarse_position"]["units"]] == ["2022", "2023"]
    assert len(out["min_games=3"]["units"]) == 1
    # 带上 units 之后原有形状不能变
    assert out["coarse_position"]["n_units_compared"] == 2


# ---- 零跳过时不要留一个吊在半空的冒号 --------------------------------------


def test_render_markdown_omits_the_reason_list_when_nothing_was_skipped():
    report = _minimal_report()
    report["skipped"] = []
    md = render_markdown(report)
    assert "跳过的单元 **0** 个。" in md
    assert "跳过的单元 **0** 个，按原因：" not in md


def test_render_markdown_keeps_the_reason_list_when_something_was_skipped():
    md = render_markdown(_minimal_report())
    assert "跳过的单元 **1** 个，按原因：" in md
    assert "预测值全同：1" in md


# ---- run_sliding 也要留住跳过原因（run_holdout / run_robustness 早已如此）----


def test_run_sliding_records_skip_reasons_instead_of_discarding_them():
    """run_holdout 和 run_robustness 都把 score_arm 的跳过原因记了下来，
    run_sliding 却写成 `scores, _ = ...` 直接丢掉。同一个缺陷在
    run_robustness 上已经被判定为缺陷并修过，这里必须一致。"""
    train, pm = _empty_train_and_pm()
    holdout = {"year": "2099", "patch": "7.39"}
    out = run_sliding(train, pm, holdout, {1: 1}, _SLIDE_EVENT_START)
    for entry in out:
        assert entry["n_scored_units"] == 0
        assert entry["n_skipped_units"] == len(ITEMS)
        assert len(entry["skipped"]) == len(ITEMS)
        assert {s["reason"] for s in entry["skipped"]} == {"候选人不足3"}
        assert {s["position"] for s in entry["skipped"]} == {1}
        assert {s["item"] for s in entry["skipped"]} == set(ITEMS)


def test_render_markdown_shows_the_sliding_skip_counts():
    report = _minimal_report()
    report["sliding"] = [{"holdout": "2025", "arm": "slide0", "mean_spearman": 0.21,
                          "patch_boundaries": [], "n_skipped_units": 7,
                          "skipped": []}]
    md = render_markdown(report)
    row = next(ln for ln in md.splitlines() if ln.startswith("| TI2025 | slide0 "))
    assert "| 7 |" in row
