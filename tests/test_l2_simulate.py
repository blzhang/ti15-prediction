"""task-7-brief.md Step 5：`l2_simulate.run_one` 额外导出每队分阶段系列赛数。

这个测试文件是 Task 7 新增（brief 本身没有要求，00-PLAN.md 里 Task 7 的
Files 清单只列了 model/l4_fantasy.py + tests/test_l4_fantasy.py）。补它的
理由：l2_simulate.py 在这次改动前完全没有单元测试覆盖（L2 是初始
"chore: 项目落地"那次大提交里做的，早于本项目后续引入的逐任务 TDD 流程），
但 Step 5 要求往 run_one 里加一段全新的计数逻辑（瑞士轮+附加轮系列赛数、
主赛事系列赛数），这段逻辑如果写错、且只靠"跑一遍脚本人工看总数对不对"
去验证，正是本项目过去两次踩过的坑（Task 5 的 idx 编号错位、Task 6 的
se 内部不一致）——聚合层面的自洽校验能过，不代表每队算对了。这里用
纯函数 `run_one` 直接单测，配合 tests/test_bracket.py 新增的
`test_series_count_is_recorded_per_team_when_requested`，把"名次自洽"
和"系列赛数逐队正确"分开锁定。

`model/l2_simulate.py` 顶层过去直接摆着一个跑 20 万次模拟 + 打印 + 落盘的
循环（无 `if __name__ == "__main__":` guard），意味着单是
`from model.l2_simulate import run_one` 就会触发一次完整的 20 万次蒙特卡洛
（实测约 100 秒）。这次顺带补了这个 guard（纯粹搬代码位置，一行计算逻辑
没改，用重跑前后 l2_predictions.json 字节级 diff 验证过等价，见
task-7-report.md），使这里的单测能秒级跑完。
"""
import numpy as np
import pytest

from model.l2_simulate import run_one, place_dist_from_counts, n as N_TEAMS


def _theta(seed):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(N_TEAMS)


def test_run_one_return_contract_is_positionally_stable():
    """锁住 run_one 的返回契约：**前 6 个字段的位置不许变**，新字段只许追加在末尾。

    这条契约不是形式主义——本函数的返回值已经被追加过两次
    （Task 7 加 group/playoff_series，后来加附加轮生还/出局集合），
    头一次是插在中间的，直接撞坏了本文件里 8 处位置解包。
    所以这里既钉死前 6 位的语义，也允许末尾继续追加。
    """
    rng = np.random.default_rng(0)
    out = run_one(_theta(0), rng)
    assert len(out) >= 6, "前 6 个字段是既有契约，不许减少"
    rec, swiss_rank, place, advanced, group_series, playoff_series = out[:6]
    assert len(rec) == N_TEAMS and len(swiss_rank) == N_TEAMS
    assert len(place) == N_TEAMS and isinstance(advanced, set)
    assert len(group_series) == N_TEAMS
    assert len(playoff_series) == N_TEAMS

    # 末尾新增的附加轮两个集合：5 队晋级 / 5 队出局，且互不相交
    elim_win, elim_lose = out[6], out[7]
    assert len(elim_win) == 5 and len(elim_lose) == 5
    assert not (elim_win & elim_lose), "同一支队不可能既晋级又出局"
    assert elim_win <= advanced, "附加轮晋级的队必然在 advanced 里"


def test_group_series_matches_the_stop_at_four_format():
    """小组赛场次由「4 胜或 4 负即停」的赛制唯一决定：

        4-0 → 打 4 场（第 4 轮clinch，停赛），不进附加轮        = 4
        4-1 → 打 5 场，直通淘汰赛，不进附加轮                  = 5
        3-2 / 2-3 → 打 5 场 + 附加轮 1 场                      = 6
        1-4 → 打 5 场，已淘汰                                  = 5
        0-4 → 打 4 场（第 4 轮被淘汰，停赛）                    = 4

    旧版断言的是「一律 5 或 6」，那是「固定 5 轮人人打满」的产物——
    该赛制会产出现实中不存在的 5-0 / 0-5（官方预测面板的档位是 4-0/0-4）。
    """
    rng = np.random.default_rng(1)
    for seed in range(30):
        rec, _, _, _, group_series, _, *_ = run_one(_theta(seed), rng)
        for t in range(N_TEAMS):
            w, l = rec[t]
            played = w + l
            expect = played + (1 if (w, l) in ((3, 2), (2, 3)) else 0)
            assert group_series[t] == expect, (
                "%s 队战绩 %d-%d 应打 %d 场，实为 %d" % (t, w, l, expect, group_series[t]))
            assert played in (4, 5), "任何队小组赛只可能打 4 或 5 场"


def test_group_series_sums_to_eighty_eight_every_single_simulation():
    """跟 test_bracket.py 的 28 恒等式同类：本届小组赛场次和是结构性常数。

        瑞士轮：1×4 + 2×5 + 5×5 + 5×5 + 2×5 + 1×4 = 78 → 39 场比赛
        附加轮：10 队各 1 场                        = 10 → 5 场比赛
        合计 group_series = 88（对应 44 场比赛）

    注意瑞士轮是 **39 场不是 40 场**——第 5 轮只有 7 场，因为 4-0 与 0-4
    两支已经停赛（Liquipedia 的 TI2025 分组标签可直接核对：R5 只有
    3-1 / 2-2 / 1-3 三组共 2+3+2 场）。
    """
    rng = np.random.default_rng(2)
    for seed in range(30):
        _, _, _, _, group_series, _, *_ = run_one(_theta(seed), rng)
        assert sum(group_series) == 88


def test_playoff_series_is_zero_for_teams_that_never_reached_playoffs():
    rng = np.random.default_rng(3)
    for seed in range(15):
        _, _, place, advanced, _, playoff_series, *_ = run_one(_theta(seed), rng)
        for t in range(N_TEAMS):
            if t not in advanced:
                assert playoff_series[t] == 0, "没打进主赛事的队伍不应该有主赛事系列赛数"
            else:
                assert playoff_series[t] > 0


def test_playoff_series_sums_to_twenty_eight_every_single_simulation():
    """主赛事固定 14 场系列赛（UB 7 + LB 6 + 决赛 1），每场系列赛让两支
    队伍各 +1，14×2=28，与谁夺冠、种子如何都无关——每次模拟都必须精确
    成立（不是平均意义上的近似）。"""
    rng = np.random.default_rng(4)
    for seed in range(30):
        _, _, _, _, _, playoff_series, *_ = run_one(_theta(seed), rng)
        assert sum(playoff_series) == 28


def test_playoff_series_matches_bracket_series_count_invariants():
    """跟 tests/test_bracket.py::test_series_count_is_recorded_per_team_when_requested
    锁的是同一组不变量，这里从 l2_simulate.run_one 的出口再验一遍——
    确保 run_one 真的把 run_playoffs 的 series_count 原样接上了，
    而不是漏接、接错索引，或者只接了部分队伍。"""
    rng = np.random.default_rng(5)
    for seed in range(20):
        _, _, place, advanced, _, playoff_series, *_ = run_one(_theta(seed), rng)
        for t in advanced:
            p = place[t]
            if p == 7:
                assert playoff_series[t] == 2
            elif p == 5:
                assert playoff_series[t] == 3
            elif p == 4:
                assert playoff_series[t] == 4
            else:
                assert 4 <= playoff_series[t] <= 6


# ---- 补充测试：修复【4】T2「最终名次分布」矩阵从未落盘 ----
#
# model/l2_simulate.py 的 __main__ 已经在算 place_c（16×17 累计计数矩阵），
# 但只写出了 top4（1-4 名求和）——00-DESIGN.md §2.1 把「T2 最终名次分布/
# 16×名次档 概率矩阵」列为交付物，§8 验收标准第 3 条要求"名次分布行列和
# 自洽"，矩阵本身不存在，这条无从核对（见 fix-final-report.md【4】）。
# 新增 place_dist_from_counts()：把 place_c 归一化成
# {队名: {"1": 概率, ..., "16": 概率}}，main 块写进 l2_predictions.json
# 的新字段 place_dist。

def test_place_assigns_exact_multiset_of_placements_every_single_simulation():
    """place_dist 行列和自洽的真正原因：名次赋值不是"随机凑出来的"，而是
    结构上保证的——8 支打进主赛事的队伍名次由 model/bracket.py::run_playoffs
    互不重叠地覆盖 1/2/3/4/5/5/7/7（tests/test_bracket.py::
    test_placements_are_structurally_valid 已锁定这 8 队的子集），另外 5 支
    附加轮出局队恒为 9、3 支瑞士轮垫底队恒为 14。16 队的名次多重集合因此
    每一次模拟都精确等于同一个固定集合——不是多次模拟取平均才近似成立
    的东西，任何一次算错都能被单次调用直接抓到（跟 group_series 恒为 90、
    playoff_series 恒为 28 是同一类"每次模拟单独成立"的恒等式）。"""
    rng = np.random.default_rng(6)
    expected = sorted([1, 2, 3, 4, 5, 5, 7, 7, 9, 9, 9, 9, 9, 14, 14, 14])
    assert len(expected) == N_TEAMS
    for seed in range(20):
        _, _, place, _, _, _, *_ = run_one(_theta(seed), rng)
        assert sorted(place) == expected


def test_place_dist_from_counts_normalises_and_rounds_to_six_decimals():
    """纯变换函数：给定累计计数矩阵和总模拟次数，归一化成概率并保 6 位
    小数，覆盖第 1-16 名全部名次档（未出现的档位显式记 0，不是缺键）。
    用一个手算好的 2 队合成矩阵验证，不需要真的跑模拟。"""
    place_c = np.zeros((2, 17))
    place_c[0, 1] = 3   # 队 A：10 次模拟里 3 次拿第 1 名
    place_c[0, 3] = 7   #        7 次拿第 3 名
    place_c[1, 1] = 1   # 队 B：1 次拿第 1 名
    place_c[1, 3] = 9   #        9 次拿第 3 名
    n_sim = 10

    dist = place_dist_from_counts(place_c, n_sim, teams=["A", "B"])

    assert set(dist) == {"A", "B"}
    assert set(dist["A"]) == {str(p) for p in range(1, 17)}, (
        "应覆盖第 1-16 名全部名次档，未出现的档位显式记 0 而不是缺键"
    )
    assert dist["A"]["1"] == pytest.approx(0.3)
    assert dist["A"]["3"] == pytest.approx(0.7)
    assert dist["A"]["2"] == 0.0
    assert dist["B"]["1"] == pytest.approx(0.1)
    assert dist["B"]["3"] == pytest.approx(0.9)
    # 6 位小数：1/3 除不尽，验证确实做了 round(..., 6) 而不是原样吐浮点噪声
    place_c2 = np.zeros((1, 17))
    place_c2[0, 1] = 1
    rounded = place_dist_from_counts(place_c2, 3, teams=["C"])
    assert rounded["C"]["1"] == round(1.0 / 3.0, 6)


def test_place_dist_pipeline_row_sums_to_one_and_grand_total_equals_team_count():
    """结构性恒等式（00-DESIGN.md §8 验收标准第 3 条「名次分布行列和
    自洽」）：接上真实 run_one（不是手造的合成矩阵）跑一段小规模模拟
    （不需要跑满 20 万次），验证每队的名次概率恰好和为 1（行和），
    全部队伍、全部名次概率加总恰好等于队伍数（列和之和）。"""
    rng = np.random.default_rng(20260802)
    n_sim = 300
    place_c = np.zeros((N_TEAMS, 17))
    for _ in range(n_sim):
        theta = rng.standard_normal(N_TEAMS)
        _, _, place, _, _, _, *_ = run_one(theta, rng)
        for t in range(N_TEAMS):
            place_c[t, place[t]] += 1

    teams = [str(t) for t in range(N_TEAMS)]
    dist = place_dist_from_counts(place_c, n_sim, teams=teams)

    # 容差取法跟 tests/test_market.py::test_l2_blended_json_sum_within_documented_tolerance
    # 同一个道理：每个概率都先各自 round() 到 6 位小数再相加，16 个数各带最多
    # 5e-7 的四舍五入误差，理论偏差上界 16*5e-7=8e-6——不应该为了凑成精确的
    # 1 而在四舍五入后再归一化，只校验偏差在 1e-5 容差内。
    for team in teams:
        assert sum(dist[team].values()) == pytest.approx(1.0, abs=1e-5), (
            "每队的名次概率必须（在 6 位小数四舍五入的容差内）和为 1——"
            "每次模拟每队必然落在恰好一个名次"
        )
    # 16 队 × 16 个名次档 = 256 个四舍五入后的数相加，理论偏差上界 256*5e-7=1.28e-4。
    grand_total = sum(sum(d.values()) for d in dist.values())
    assert grand_total == pytest.approx(N_TEAMS, abs=2e-4), (
        "全部队伍全部名次概率加总应（在四舍五入容差内）恰好等于队伍数"
    )
