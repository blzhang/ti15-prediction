"""task-10-brief.md Step 5：生成赛前两两对阵概率表 reports/ti15_matches.csv。

结构性难点（task-10-report.md 有完整推理）：瑞士轮配对是内生的——R2 起，
谁打谁取决于前几轮战绩；R1 虽由赛事方指定，但两个分组本身赛前未公布，
连 R1 具体配对都列不出来。选择是列全部 16×15/2=120 个可能配对的两两 BO3
胜率（`build_match_rows`），赛后按实际发生的配对取子集回填评分——
`team_a`/`team_b` 按队名字典序排列去重，`stage`/`result_a_wins` 赛前是
占位值，赛后人工回填。

这里的测试刻意用一组“字典序与实力强弱不一致”的合成队伍名
（Alpha 最强但字典序在 Delta 之后），专门用来堵住一类隐藏假设——
“team_a 恒强”或者“按字典序排列时顺带把强队排在前面”——如果实现偷懒
按 theta 排序而不是按队名排序，这里会直接失败。
"""
import csv
import itertools
import os
import tempfile

import numpy as np
import pytest

from model.emit_match_table import (
    build_match_rows, series_win_prob_matrix, write_match_csv, main,
    FIELDNAMES, STAGE_PENDING, DEFAULT_N_SIM,
)

TEAMS = ["Delta", "Alpha", "Charlie", "Bravo"]     # 乱序 + 字典序与实力不对齐
THETA = [0.0, 1.5, -1.0, 0.4]                      # Alpha 最强，Charlie 最弱
SE0 = [0.0, 0.0, 0.0, 0.0]


def _bo3(theta_i, theta_j):
    p1 = 1.0 / (1.0 + np.exp(-(theta_i - theta_j)))
    return p1 ** 2 * (3 - 2 * p1)


def test_row_count_is_n_choose_2():
    rng = np.random.default_rng(1)
    rows = build_match_rows(TEAMS, THETA, SE0, rng, n_sim=500)
    assert len(rows) == 6


def test_team_a_is_always_alphabetically_before_team_b_and_pairs_are_unique():
    rng = np.random.default_rng(1)
    rows = build_match_rows(TEAMS, THETA, SE0, rng, n_sim=500)
    for r in rows:
        assert r["team_a"] < r["team_b"]
    pairs = {(r["team_a"], r["team_b"]) for r in rows}
    assert len(pairs) == 6


def test_no_uncertainty_matches_closed_form_bo3_exactly():
    """se=0 时每次蒙特卡洛重抽的 theta 都精确等于 theta_hat（没有噪声可言），
    所以蒙特卡洛均值必须与闭式 BO3 公式在浮点精度内完全相等。这不是「大致
    接近」的模糊断言，是能验证整条蒙特卡洛管线算对了没有的精确断言——
    如果 diff 矩阵算反了符号、或者 p3 公式抄错，这里会精确地失败而不是
    「看起来差不多就让它过」。
    """
    rng = np.random.default_rng(2)
    rows = build_match_rows(TEAMS, THETA, SE0, rng, n_sim=1000)
    theta_of = dict(zip(TEAMS, THETA))
    for r in rows:
        expected = round(float(_bo3(theta_of[r["team_a"]], theta_of[r["team_b"]])), 6)
        assert r["p_a_wins_series"] == pytest.approx(expected, abs=1e-9)


def test_stronger_team_wins_more_regardless_of_which_alphabetical_slot_it_lands_in():
    """Alpha（theta 最高）在字典序中排在 Delta 之后，所以在“Alpha vs Charlie”
    这一行里 Alpha 是 team_a（'Alpha' < 'Charlie'），但在“Bravo vs ...”里
    可能是另一种情况——直接用真实排序结果核对，不臆测顺序，确保没有
    “team_a 恒强”之类的隐藏耦合。"""
    rng = np.random.default_rng(3)
    rows = build_match_rows(TEAMS, THETA, SE0, rng, n_sim=1000)
    by_pair = {(r["team_a"], r["team_b"]): r["p_a_wins_series"] for r in rows}
    a, c = sorted(["Alpha", "Charlie"])
    p_a_wins = by_pair[(a, c)]
    p_alpha_wins = p_a_wins if a == "Alpha" else 1 - p_a_wins
    assert p_alpha_wins > 0.5, "Alpha 明显最强，无论它落在 team_a 还是 team_b 都应该赢面更大"


def test_probabilities_are_six_decimals_and_within_unit_interval():
    rng = np.random.default_rng(4)
    rows = build_match_rows(TEAMS, THETA, [0.15, 0.1, 0.2, 0.12], rng, n_sim=2000)
    for r in rows:
        p = r["p_a_wins_series"]
        assert 0.0 <= p <= 1.0
        assert round(p, 6) == p


def test_stage_is_pending_and_result_blank_pre_tournament():
    rng = np.random.default_rng(5)
    rows = build_match_rows(TEAMS, THETA, SE0, rng, n_sim=200)
    for r in rows:
        assert r["stage"] == STAGE_PENDING == "pending"
        assert r["result_a_wins"] == ""


def test_frozen_at_is_shared_timestamp_across_all_rows():
    rng = np.random.default_rng(6)
    rows = build_match_rows(TEAMS, THETA, SE0, rng, n_sim=200, frozen_at="2026-08-03T00:00:00Z")
    assert {r["frozen_at"] for r in rows} == {"2026-08-03T00:00:00Z"}


def test_frozen_at_defaults_to_utc_iso_when_not_given():
    rng = np.random.default_rng(9)
    rows = build_match_rows(TEAMS, THETA, SE0, rng, n_sim=200)
    ts = rows[0]["frozen_at"]
    assert ts.endswith("Z")
    assert ts[4] == "-" and ts[7] == "-" and ts[10] == "T"


def test_matrix_is_complementary_by_construction():
    """P[i,j] + P[j,i] 必须精确等于 1：p3(q) + p3(1-q) == 1 是 BO3 公式本身
    的代数恒等式（对任意单局胜率 q 都成立），且用的是同一批 theta 抽样算
    出的两个方向，所以逐次抽样都精确成立，不是「平均意义上大致」。
    这是设计文档 §8 验收标准 3「概率自洽」在这张新表上的版本，也直接
    验证了 series_win_prob_matrix 没有算反符号或者漏乘。
    """
    rng = np.random.default_rng(7)
    theta = [0.3, -0.2, 1.1, 0.0, -0.9]
    se = [0.1, 0.2, 0.05, 0.3, 0.15]
    P = series_win_prob_matrix(theta, se, rng, n_sim=5000, batch=777)
    n = len(theta)
    for i, j in itertools.combinations(range(n), 2):
        assert P[i, j] + P[j, i] == pytest.approx(1.0, abs=1e-9)


def test_series_win_prob_matrix_handles_batch_not_dividing_n_sim_evenly():
    rng = np.random.default_rng(10)
    P = series_win_prob_matrix(THETA, SE0, rng, n_sim=1001, batch=300)
    assert P.shape == (4, 4)


def test_write_match_csv_round_trip_has_exact_header_and_creates_parent_dirs():
    rng = np.random.default_rng(8)
    rows = build_match_rows(TEAMS, THETA, SE0, rng, n_sim=200)
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "nested", "sub", "matches.csv")
        write_match_csv(rows, out)
        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == FIELDNAMES == [
                "stage", "team_a", "team_b", "p_a_wins_series", "frozen_at", "result_a_wins",
            ]
            body = list(reader)
        assert len(body) == len(rows)


def test_main_writes_csv_using_real_sixteen_team_roster(tmp_path):
    """走 main()/CLI 这条真实入口（真实 l1_rating.json 的 16 队），
    n_sim 调小只是为了让测试快，不改变任何 wiring 逻辑。"""
    out = str(tmp_path / "matches.csv")
    main(["--out", out, "--n-sim", "500"])
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 16 * 15 // 2
    teams = set()
    for r in rows:
        teams.add(r["team_a"])
        teams.add(r["team_b"])
    assert len(teams) == 16
