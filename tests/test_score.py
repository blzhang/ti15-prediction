"""task-10-brief.md Step 1（brief 原文 5 条）+ 本任务在写测试时另外发现/补的缺口。

brief 只给了 brier / log_loss / calibration_bins 三个函数的参考实现和测试，
`score_report(csv_path)` 是 Interfaces 里点名要产出但 brief 没给代码的第 4 个
函数——按 task-10-report.md 的推理，它是把 reports/ti15_matches.csv 接到
brier/log_loss/calibration_bins 上的那一层，本文件后半段是它的测试。

写这些测试时验证过的一个真实发现（不是假设）：calibration_bins 用
`int(p * n_bins)` 做分桶索引，在某些 n_bins 下会因为浮点乘法不精确
把恰好落在桶边界上的 p 分进错误的前一个桶——用穷举脚本扫过 n_bins=2..59
的所有 k/n_bins 边界值，n_bins=10（本项目默认值、brief 五条测试全部使用的值）
下 k=1..9 全部精确，但 n_bins=22 (k=15)/23(k=13)/26(k=15)/39(k=31) 下确实复现：
比如 15/22=0.6818181818181818，乘以 22 得到 14.999999999999998，
`int()` 截断成 14 而不是 15。见 test_calibration_bins_handles_float_boundary_case。
"""
import csv
import math
import os

import pytest

from model.score import (
    brier, log_loss, calibration_bins, classify_brier, score_report,
    HEALTHY_BRIER_LO, HEALTHY_BRIER_HI, LEAKAGE_SUSPECT_BELOW, COINFLIP_BRIER,
)

FIELDNAMES = ["stage", "team_a", "team_b", "p_a_wins_series", "frozen_at", "result_a_wins"]


def _project_path(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, *parts)


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _row(stage, a, b, p, result):
    return {"stage": stage, "team_a": a, "team_b": b, "p_a_wins_series": p,
            "frozen_at": "2026-08-01T00:00:00Z", "result_a_wins": result}


# ---------- brief Step 1 原文 5 条（一字不改） ----------

def test_brier_is_zero_for_perfect_and_one_for_inverted():
    assert brier([1.0, 0.0], [1, 0]) == pytest.approx(0.0)
    assert brier([0.0, 1.0], [1, 0]) == pytest.approx(1.0)


def test_brier_of_coinflip_is_quarter():
    assert brier([0.5] * 4, [1, 0, 1, 0]) == pytest.approx(0.25)


def test_log_loss_clips_and_stays_finite():
    assert log_loss([0.0], [1]) < 40.0


def test_calibration_bins_group_and_report_counts():
    probs = [0.05] * 10 + [0.95] * 10
    out = [1] * 0 + [0] * 10 + [1] * 10
    bins = calibration_bins(probs, out, n_bins=10)
    filled = [b for b in bins if b["n"] > 0]
    assert len(filled) == 2
    assert filled[0]["observed"] == pytest.approx(0.0)
    assert filled[-1]["observed"] == pytest.approx(1.0)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        brier([0.5], [1, 0])


# ---------- 补的缺口：brier/log_loss 的空输入与更多校准桶场景 ----------

def test_brier_rejects_empty_input():
    """_check 除了长度匹配还应该拒绝空输入——brief 参考实现里这条分支存在
    但 brief 自己的 5 条测试从未触发过（构造非空但长度不等 vs 两者都空是
    两条不同的代码路径），这里单独锁一下。"""
    with pytest.raises(ValueError):
        brier([], [])
    with pytest.raises(ValueError):
        log_loss([], [])
    with pytest.raises(ValueError):
        calibration_bins([], [])


def test_calibration_bins_handles_float_boundary_case():
    """真实复现的浮点边界 bug：15/22 这个概率乘以 22 应该精确落在桶 15
    的下边界，但 IEEE754 双精度算出 14.999999999999998，naive
    `int(p*n_bins)` 截断成 14——把本该在桶 15（[15/22,16/22)）的样本
    错分进桶 14（[14/22,15/22)）。用 `int(p*n_bins + 1e-9)` 修好后，
    这个样本必须出现在桶 15，桶 14 必须仍然是空的（n=0）。
    """
    n_bins = 22
    p = 15 / 22
    assert p * n_bins == 14.999999999999998, "环境浮点行为与本地复现不一致，需要重新核实这条 bug 的前提"
    bins = calibration_bins([p], [1], n_bins=n_bins)
    assert bins[14]["n"] == 0, "桶 14 不应该收到本该属于桶 15 的样本"
    assert bins[15]["n"] == 1
    assert bins[15]["lo"] == pytest.approx(15 / 22)


def test_calibration_bins_default_decile_boundaries_are_all_exact():
    """穷举核实：n_bins=10（本项目实际使用的默认值）下，k=1..9 十个边界值
    全部精确落入桶 k，不受上一条测试发现的浮点问题影响——这是「default
    配置在真实使用场景下没有这个问题」的正面证据，不能因为发现了 n_bins=22
    的边界 bug 就想当然地认为默认配置也受影响，必须实测。"""
    for k in range(1, 10):
        p = k / 10
        bins = calibration_bins([p], [1], n_bins=10)
        assert bins[k]["n"] == 1, "p=%r 应落入桶 %d" % (p, k)


def test_calibration_bins_predicted_and_observed_averages():
    probs = [0.1, 0.2, 0.25]
    outs = [0, 1, 1]
    bins = calibration_bins(probs, outs, n_bins=10)
    assert bins[1]["n"] == 1
    assert bins[1]["predicted"] == pytest.approx(0.1)
    assert bins[1]["observed"] == pytest.approx(0.0)
    assert bins[2]["n"] == 2
    assert bins[2]["predicted"] == pytest.approx((0.2 + 0.25) / 2)
    assert bins[2]["observed"] == pytest.approx(1.0)


# ---------- classify_brier：设计文档 §5 健全性护栏的四分类 ----------

def test_classify_brier_healthy_range_inclusive_both_ends():
    assert classify_brier(HEALTHY_BRIER_LO) == "healthy"
    assert classify_brier(HEALTHY_BRIER_HI) == "healthy"
    assert classify_brier(0.225) == "healthy"


def test_classify_brier_suspect_leakage_strictly_below_020():
    assert classify_brier(0.1999999) == "suspect_leakage"
    assert classify_brier(0.0) == "suspect_leakage"


def test_classify_brier_worse_than_coinflip_strictly_above_025():
    assert classify_brier(0.2500001) == "worse_than_coinflip"
    assert classify_brier(1.0) == "worse_than_coinflip"


def test_classify_brier_boundary_values_are_not_suspect_or_worse():
    """0.20 本身不算「低于 0.20」，0.25 本身就是抛硬币、不算「高于 0.25」——
    两个边界值单独按字面意思都应该落进 borderline，不是它们各自相邻的极端分类。"""
    assert classify_brier(LEAKAGE_SUSPECT_BELOW) == "borderline"
    assert classify_brier(COINFLIP_BRIER) == "borderline"


def test_classify_brier_borderline_gray_zones():
    assert classify_brier(0.205) == "borderline"   # [0.20, 0.21) 灰区
    assert classify_brier(0.245) == "borderline"   # (0.24, 0.25] 灰区


# ---------- score_report：CSV -> 打分，brief 没给参考实现的第 4 个接口 ----------

def test_score_report_on_fully_unscored_csv_returns_no_data_yet(tmp_path):
    """赛前刚生成的表：全部 result_a_wins 留空。这不是错误，是「赛事还没打」
    的正常状态，score_report 必须优雅返回而不是抛异常或算出诡异的数字。"""
    p = tmp_path / "matches.csv"
    _write_csv(str(p), [_row("pending", "A", "B", "0.6", "")])
    out = score_report(str(p))
    assert out["n_total"] == 1
    assert out["n_scored"] == 0
    assert out["brier"] is None
    assert out["log_loss"] is None
    assert out["calibration_bins"] == []
    assert out["verdict"] == "no_data_yet"


def test_score_report_scores_only_the_backfilled_subset(tmp_path):
    """核心行为：120 个候选配对里只有真正发生过的那些被回填了结果，
    score_report 必须只对这个子集打分，未发生的配对（result_a_wins 留空）
    必须被排除在外，不能被当成"预测错误"或"预测正确"计入。"""
    rows = [
        _row("swiss_r1", "A", "B", "0.7", "1"),
        _row("swiss_r1", "C", "D", "0.5", "0"),
        _row("pending", "A", "C", "0.55", ""),   # 还没发生，必须被跳过
    ]
    p = tmp_path / "matches.csv"
    _write_csv(str(p), rows)
    out = score_report(str(p))
    assert out["n_total"] == 3
    assert out["n_scored"] == 2
    assert out["brier"] == pytest.approx(brier([0.7, 0.5], [1, 0]))
    assert out["log_loss"] == pytest.approx(log_loss([0.7, 0.5], [1, 0]))
    assert len(out["calibration_bins"]) == 10


def test_score_report_rejects_non_binary_result_value(tmp_path):
    """人工回填是本流程的一部分（赛后有人把 CSV 里的 result_a_wins 从空
    改成 1/0），手滑打成别的字符串（"yes"/"1.0"/多余空格之外的东西）
    应该报出清晰的 ValueError，而不是让后面的算术裸抛 TypeError。"""
    p = tmp_path / "matches.csv"
    _write_csv(str(p), [_row("swiss_r1", "A", "B", "0.6", "yes")])
    with pytest.raises(ValueError):
        score_report(str(p))


def test_score_report_rejects_malformed_probability_on_scored_row(tmp_path):
    p = tmp_path / "matches.csv"
    _write_csv(str(p), [_row("swiss_r1", "A", "B", "not-a-number", "1")])
    with pytest.raises(ValueError):
        score_report(str(p))


def test_score_report_tolerates_whitespace_in_result_column(tmp_path):
    """人工编辑 CSV 常见的小意外：多打/漏打空格。应该被 strip 掉，不该
    被当成"不合法值"报错，也不该被当成"留空未发生"而跳过。"""
    p = tmp_path / "matches.csv"
    _write_csv(str(p), [_row("swiss_r1", "A", "B", "0.6", " 1 ")])
    out = score_report(str(p))
    assert out["n_scored"] == 1


def test_score_report_includes_documented_healthy_range(tmp_path):
    """§5 健全性护栏的区间必须作为可程序访问的字段出现在返回值里，
    而不是只存在于代码注释——下游（比如赛后复盘脚本）需要读它来判定。

    之前这条测试只检查了模块常量等于它自己的字面量（`HEALTHY_BRIER_LO ==
    0.21`），从未调用 `score_report()`，也从未看过 `out["healthy_range"]`——
    对 `score_report` 返回字典里删掉 `"healthy_range"` 整行做变异测试，
    旧断言照样通过，零保护力。现在真正调用 `score_report()` 并断言返回值
    本身携带这个字段、取值与文档常量一致。"""
    assert HEALTHY_BRIER_LO == 0.21
    assert HEALTHY_BRIER_HI == 0.24
    p = tmp_path / "matches.csv"
    _write_csv(str(p), [_row("pending", "A", "B", "0.6", "")])
    out = score_report(str(p))
    assert "healthy_range" in out, "score_report 的返回值必须包含 healthy_range 字段"
    assert out["healthy_range"] == [HEALTHY_BRIER_LO, HEALTHY_BRIER_HI]


def test_score_report_verdict_matches_classify_brier(tmp_path):
    rows = [_row("s", "A", "B", "0.9", "1")] * 9 + [_row("s", "A", "B", "0.9", "0")]
    p = tmp_path / "matches.csv"
    _write_csv(str(p), rows)
    out = score_report(str(p))
    assert out["verdict"] == classify_brier(out["brier"])


# ---------- 对真实交付物 reports/ti15_matches.csv 的回归测试 ----------
# 这张表是本任务真正的交付物（Step 5/6），下面这条测试保证它已经生成、
# 表头与 120 行两两组合精确匹配约定的 schema——类比 tests/test_market.py
# 里对 model/l2_blended.json 的真实产出文件回归校验，防止脚本以后被改坏
# 而没有测试兜底。

def test_real_ti15_matches_csv_is_well_formed():
    path = _project_path("reports", "ti15_matches.csv")
    assert os.path.exists(path), (
        "reports/ti15_matches.csv 尚未生成——先跑 "
        "python3 model/emit_match_table.py --out reports/ti15_matches.csv"
    )
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == FIELDNAMES
        rows = list(reader)
    assert len(rows) == 16 * 15 // 2

    pairs = set()
    for r in rows:
        a, b = r["team_a"], r["team_b"]
        assert a < b, "team_a 必须字典序小于 team_b（去重规范）"
        pairs.add((a, b))
        p = float(r["p_a_wins_series"])
        assert 0.0 <= p <= 1.0
        assert round(p, 6) == p
        # 结果列：赛前留空，赛后由 model/backfill_results.py 回填 0/1。
        # 两种状态都合法，但 stage 必须跟着走——回填了结果却还标 pending，
        # 或者标了真实阶段却没结果，都是回填脚本出了问题。
        res = r["result_a_wins"]
        assert res in ("", "0", "1"), "结果列只能是空、0 或 1，现在是 %r" % res
        assert (res == "") == (r["stage"] == "pending"), (
            "%s vs %s 的 stage=%r 与 result_a_wins=%r 对不上"
            % (a, b, r["stage"], res))
    assert len(pairs) == len(rows), "不能有重复配对"

    out = score_report(path)
    assert out["n_total"] == 120
    # 赛前 n_scored=0；开赛后等于已回填的场次数。两种都合法，但打分必须自洽。
    if out["n_scored"] == 0:
        assert out["verdict"] == "no_data_yet"
    else:
        assert out["brier"] is not None and 0.0 <= out["brier"] <= 1.0
        assert out["verdict"] != "no_data_yet"


def test_backfill_never_touches_the_frozen_pre_match_probabilities():
    """回填只许写 stage 与 result_a_wins 两列。

    `p_a_wins_series` 是赛前对每一对队伍的唯一承诺，一旦被回填脚本碰过，
    整张对账表就失去了意义——而且改完看起来一切正常，赛后打分照样出数，
    只是那个数不再对应任何赛前承诺。所以拿开赛前的冻结件逐行比对。
    """
    live = _project_path("reports", "ti15_matches.csv")
    frozen = _project_path("frozen", "frozen_v3-matchtable.json")
    if not os.path.exists(frozen):
        pytest.skip("缺少 v3 冻结件")
    # 名字是 .json，内容其实是 CSV 原文——freeze.py 对任何源文件都原样复制，
    # 只是统一按 frozen_<label>.json 命名。这里按它的真实格式读。
    with open(frozen, newline="", encoding="utf-8") as f:
        frozen_rows = list(csv.DictReader(f))
    with open(live, newline="", encoding="utf-8") as f:
        live_rows = list(csv.DictReader(f))
    assert len(frozen_rows) == len(live_rows)
    for fr, lr in zip(frozen_rows, live_rows):
        assert (fr["team_a"], fr["team_b"]) == (lr["team_a"], lr["team_b"])
        assert fr["p_a_wins_series"] == lr["p_a_wins_series"], (
            "%s vs %s 的赛前概率被改过了：冻结件 %s，现在 %s"
            % (fr["team_a"], fr["team_b"], fr["p_a_wins_series"], lr["p_a_wins_series"]))
        assert fr["frozen_at"] == lr["frozen_at"]
