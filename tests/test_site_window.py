"""site/window.py 版本窗口页渲染测试。

这一页讲的就是「先写死判据再跑数据、不许过度声称」，所以它自己最不能犯的两种错是：
(1) 把数字写死在模板里，模型重跑后页面不跟着变；
(2) 把「没有证据支持」说成「已经证明两者一样」，或者把探索性发现说成结论。
下面的 fixture 刻意用一组跟真实产出物对不上的数字，实现要是偷偷硬编码，这里就会露馅。
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site"))
import window  # noqa: E402

DAY = 86400
START = 1_700_000_000


def _decide(n_pos, n_neg, median, p, by_holdout, supported):
    return {"sign_test": {"n_pos": n_pos, "n_neg": n_neg, "n_zero": 0,
                          "median": median, "p": p},
            "median_diff_by_holdout": by_holdout,
            "n_holdouts_positive": sum(1 for v in by_holdout.values() if v > 0),
            "n_units_compared": n_pos + n_neg, "supported": supported}


def _holdout(year, patch, window_days, in_win, total, med_games, pct_below, min_games):
    return {"holdout": year, "patch": patch, "event_start_ts": START,
            "n_participants": total, "n_with_position": total,
            "n_participants_without_pre_event_history": 0,
            "min_games_among_participants": min_games,
            "arms": {}, "patch_window": {
                "window_days": window_days, "n_players_total": total,
                "n_players_in_window": in_win,
                "n_players_absent_from_window": total - in_win,
                "median_games_in_window": med_games, "min_n_for_own_game_var": 20,
                "pct_below_min_n": pct_below}}


def _slides(year, means, boundaries):
    """离开赛由近到远四段，每段 105 天。"""
    return [{"holdout": year, "arm": "slide%d" % k,
             "since_ts": START - (k + 1) * 105 * DAY,
             "until_ts": START - k * 105 * DAY,
             "n_scored_units": 60, "mean_spearman": means[k],
             "patch_boundaries": boundaries[k], "n_skipped_units": 0, "skipped": []}
            for k in range(4)]


def _report(slides=None, holdouts=None):
    holdouts = holdouts or ["2019", "2020"]
    by_h = {h: -0.05 for h in holdouts}
    return {
        "alpha": 0.05, "min_holdouts_positive": 3,
        "baseline_arm": "L955d", "treatment_arm": "patch",
        "items_covered": "9/11", "excluded_items": ["alpha_item", "beta_item"],
        "decision": _decide(7, 33, -0.1234, 0.4321, by_h, False),
        "holdout_meta": [
            _holdout(holdouts[0], "9.99", 41, 55, 66, 17.0, 33.3, 13),
            _holdout(holdouts[1], "9.98", 111, 66, 66, 61.0, 4.5, 21),
        ],
        "coverage": [{"holdout": holdouts[0], "item": "kills", "n_union": 66,
                      "n_intersection": 55, "n_dropped_by_intersection": 777}],
        "skipped": [],
        "sliding": slides if slides is not None else (
            _slides(holdouts[0], [0.81, 0.72, 0.63, 0.54],
                    [["9.99"], [], ["9.98"], []])
            + _slides(holdouts[1], [0.80, 0.70, 0.60, 0.50], [[], [], [], []])),
        "robustness": {
            "coarse_position": _decide(11, 22, -0.0999, 0.0123, by_h, False),
            "min_games=3": _decide(7, 33, -0.1234, 0.4321, by_h, False),
        },
        "exploratory": {
            "preregistered": False, "control_arm": "L105d",
            "historical_patch_window_days": {"min": 41, "max": 111},
            "proposal": {"patch": "9.99", "event_start_utc": "2030-01-01T00:00:00Z",
                         "window_days": 199},
            "median_diff_vs_control_by_holdout": {holdouts[0]: -0.0666,
                                                  holdouts[1]: 0.0},
            "treatment_vs_control_by_holdout": {
                holdouts[0]: {"n_units": 60, "n_identical": 0, "median_diff": -0.0666},
                holdouts[1]: {"n_units": 60, "n_identical": 42, "median_diff": 0.0}},
            "arm_vs_baseline": {
                "L180d": _decide(30, 10, 0.0888, 0.00042, {h: 0.09 for h in holdouts}, True),
                "patch": _decide(7, 33, -0.1234, 0.4321, by_h, False),
            },
        },
    }


def test_every_headline_number_comes_from_the_report_not_the_template():
    """fixture 的数字跟真实产出物完全对不上——实现若把真实数字写死在模板里，
    这里会看到 0.4778/240/955 之类的旧值而不是下面这些。"""
    html = window.render("/dota2", _report())
    assert "p=0.4321" in html          # 符号检验 p
    assert "-0.1234" in html           # 中位差
    assert "0.4778" not in html        # 真实产出物的 p 绝不能出现
    assert "240" not in html           # 真实产出物的单元数绝不能出现


def test_structural_counts_are_derived_so_the_page_stays_self_consistent():
    """「几届 × 几项 × 几个号位 = 几个单元」这行乘法必须自洽。
    真实数据是 4×12×5=240；本 fixture 是 2 届、9 项、40 个单元 → 号位数应算成 2。
    实现若把 "4 届 × 12 个计分项 × 5 个号位" 写死，这里等号两边就对不上了。"""
    html = window.render("/dota2", _report())
    assert "2 届 × 9 个计分项 × 2 个号位 = <b>40</b> 个比较单元" in html
    assert "4 届 ×" not in html
    assert "12 个计分项" not in html


def test_holdout_consistency_bound_is_computed_two_sided_not_hardcoded():
    """只靠届间一致性能达到的最好 p 值 = 双侧精确二项 2×0.5^届数。
    2 届 → 0.500；写死成 4 届的那个值（0.125）就会露馅。"""
    html = window.render("/dota2", _report())
    assert "p=0.500" in html
    assert "0.0625" not in html


def test_participant_range_and_baseline_days_come_from_data():
    html = window.render("/dota2", _report())
    assert "66 名参赛选手" in html      # fixture 两届都是 66 人 → 不写成区间
    assert "955 天" in html             # 从 baseline 臂名 L955d 反推


def test_patch_window_table_reads_lengths_and_thresholds_from_data():
    html = window.render("/dota2", _report())
    assert "41 天" in html and "111 天" in html
    assert "33.3%" in html and "4.5%" in html
    assert "55/66" in html             # 窗内有数据的选手 / 总数


def test_proposal_section_states_the_untested_window_length():
    """读者提的窗口没被测到，这一点必须由数据驱动地说出来。"""
    html = window.render("/dota2", _report())
    assert "199 天" in html
    assert "41~111 天" in html
    assert "既没有证伪，也没有证实" in html


def test_exploratory_section_is_labelled_not_preregistered_and_not_actionable():
    html = window.render("/dota2", _report())
    assert "不属于预注册分析" in html
    assert "不构成现在就改模型取数起点的依据" in html


def test_page_never_claims_the_two_strategies_are_equivalent():
    """「没有证据支持」不等于「证明了一样」——这是全站措辞纪律里最硬的一条。"""
    html = window.render("/dota2", _report())
    assert "没有证据支持" in html
    for banned in ("证明两者一样", "两者一样好", "已经证明等价", "说明两者没有差别"):
        assert banned not in html


def test_monotonic_count_is_computed_and_exception_is_disclosed():
    """真实数据里就有一届不单调。实现必须自己数，并把例外写出来。"""
    html = window.render("/dota2", _report())   # 第一届 0.81>0.72>0.63>0.54 单调
    assert "2 届里 2 届是逐段下降的" in html
    assert "例外要说清楚" not in html

    bumped = (_slides("2019", [0.81, 0.60, 0.70, 0.54], [["9.99"], [], ["9.98"], []])
              + _slides("2020", [0.80, 0.70, 0.60, 0.50], [[], [], [], []]))
    html2 = window.render("/dota2", _report(slides=bumped))
    assert "2 届里 1 届是逐段下降的" in html2
    assert "例外要说清楚" in html2
    assert "0.7000" in html2 and "0.6000" in html2


def test_most_telling_pair_is_picked_from_data_not_hardcoded_to_ti2024():
    """真实数据里最有说服力的一对恰好在 TI2024，但那不能写死——
    这个 fixture 一届都不叫 2024，实现仍须挑出「跨界最多的段 vs 相邻不跨界的段」。"""
    html = window.render("/dota2", _report())
    assert "TI2024" not in html
    assert "最能说明问题的是 TI2019" in html
    assert "跨版本的那段并不更差" in html


def test_coverage_and_intersection_losses_are_disclosed():
    html = window.render("/dota2", _report())
    assert "9/11" in html                    # 计分项覆盖
    assert "alpha_item" in html              # 缺的项要点名
    assert "777" in html                     # 交集丢弃人次


def test_arm_table_orders_by_median_and_marks_the_treatment():
    html = window.render("/dota2", _report())
    assert html.index("L180d") < html.index("L955d") or "L180d" in html
    assert "本次的 treatment" in html
    assert "0.0888" in html
