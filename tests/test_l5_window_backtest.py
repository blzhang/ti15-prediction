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
    assert "6" in md          # n_dropped_by_intersection
    assert "跳过" in md
    assert "预测值全同" in md


def test_render_markdown_states_item_coverage_is_12_of_15():
    md = render_markdown(_minimal_report())
    assert "12/15" in md
    assert "smokes" in md
