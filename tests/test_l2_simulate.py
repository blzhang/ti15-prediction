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

from model.l2_simulate import run_one, n as N_TEAMS


def _theta(seed):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(N_TEAMS)


def test_run_one_returns_six_values_including_two_series_arrays():
    rng = np.random.default_rng(0)
    out = run_one(_theta(0), rng)
    assert len(out) == 6, "brief Step 5 要求 run_one 额外带上 group/playoff 两个系列赛数组"
    rec, swiss_rank, place, advanced, group_series, playoff_series = out
    assert len(group_series) == N_TEAMS
    assert len(playoff_series) == N_TEAMS


def test_group_series_is_five_for_direct_and_out_teams_six_for_playin_teams():
    """瑞士轮固定 5 轮（model/swiss.py 无提前淘汰），只有 4-13 名要多打
    1 场附加轮，所以 group_series 的取值只能是 5 或 6，不能是别的数。
    """
    rng = np.random.default_rng(1)
    for seed in range(15):
        _, swiss_rank, place, advanced, group_series, playoff_series = run_one(_theta(seed), rng)
        assert set(group_series) <= {5, 6}
        direct_and_out = [t for t in range(N_TEAMS) if place[t] == 14 or t in swiss_rank[:3]]
        for t in direct_and_out:
            assert group_series[t] == 5, "瑞士轮前 3（直接晋级）和 14-16 名（出局）都不打附加轮"
        playin_teams = [t for t in range(N_TEAMS) if t not in direct_and_out]
        assert len(playin_teams) == 10
        for t in playin_teams:
            assert group_series[t] == 6, "4-13 名进附加轮，多打 1 场"


def test_group_series_sums_to_ninety_every_single_simulation():
    """跟 tests/test_bracket.py 的 28 恒等式是同一类校验：16 队 ×5 瑞士轮
    + 10 队 ×1 附加轮 = 90，这是每一次模拟单独成立的恒等式，不是要多次
    模拟取平均才近似成立的东西——任何一次算错都能被单次调用直接抓到。
    """
    rng = np.random.default_rng(2)
    for seed in range(30):
        _, _, _, _, group_series, _ = run_one(_theta(seed), rng)
        assert sum(group_series) == 90


def test_playoff_series_is_zero_for_teams_that_never_reached_playoffs():
    rng = np.random.default_rng(3)
    for seed in range(15):
        _, _, place, advanced, _, playoff_series = run_one(_theta(seed), rng)
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
        _, _, _, _, _, playoff_series = run_one(_theta(seed), rng)
        assert sum(playoff_series) == 28


def test_playoff_series_matches_bracket_series_count_invariants():
    """跟 tests/test_bracket.py::test_series_count_is_recorded_per_team_when_requested
    锁的是同一组不变量，这里从 l2_simulate.run_one 的出口再验一遍——
    确保 run_one 真的把 run_playoffs 的 series_count 原样接上了，
    而不是漏接、接错索引，或者只接了部分队伍。"""
    rng = np.random.default_rng(5)
    for seed in range(20):
        _, _, place, advanced, _, playoff_series = run_one(_theta(seed), rng)
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
