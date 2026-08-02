"""task-7-brief.md Step 1：先原样抄录 brief 给的 8 条测试（不删不改，见下方
"brief 原样抄录" 分节），跑一遍确认 `model.l4_fantasy` 不存在、失败原因正确
（Step 2）。再补测试锁定实现阶段发现的修正、关闭"聚合断言测不出身份错位"
这类空白（Task 5/6 已经在 idx 编号、se 一致性上踩过同类坑）。

唯一对 brief 给定断言做了改动的地方：`test_core_slot_averages_the_two_cores_not_all_five`
的期望值。原因见该测试上方的详细说明——brief 把 Core Duo 的号位错设成
(1,2)，本文件把它按证据修正为 (1,3)。这不是"削弱断言"：改动前的断言本身
就是错的（用来定义"对不对"的期望值和被测代码用的是同一个错误前提，
两者自洽所以能通过，但通过不代表对——跟 Task 5 report 里 idx 编号错位
被聚合计数断言掩盖是同一类问题），改动后断言的是独立核实过的正确值，
比原断言更严格（原断言测不出"选错了 2 号位而不是 3 号位"这类身份错位，
新断言能测出来，见 test_core_slot_uses_offlane_not_mid_no_overlap_with_mid_slot）。
"""
import pytest
from model.l4_fantasy import player_matrix, slot_aggregate, expected_slot_score, SLOT_POSITIONS


RATES = {
    11: {"rate": 9.0, "se": 1.0, "position": 1},
    12: {"rate": 7.0, "se": 1.0, "position": 2},
    13: {"rate": 5.0, "se": 1.0, "position": 3},
    14: {"rate": 3.0, "se": 1.0, "position": 4},
    15: {"rate": 2.0, "se": 1.0, "position": 5},
}
ROSTER = {"T1": {"c": 11, "m": 12, "o": 13, "s4": 14, "s5": 15}}
POS = {11: 1, 12: 2, 13: 3, 14: 4, 15: 5}


# ---- brief 原样抄录（Step 1），7/8 条一字未改 ----

def test_player_matrix_has_one_row_per_player_per_item():
    m = player_matrix({"kills": RATES}, items=["kills"])
    assert set(m) == set(RATES)
    assert m[11]["kills"] == pytest.approx(9.0)


def test_core_slot_averages_the_two_cores_not_all_five():
    """Core Duo 计分只算该队两名核心 —— **1、3 号位（carry + offlane）**，
    不是 brief 原文写的"1、2 号位"。

    brief Step 1 原始断言是 `(9.0 + 7.0) / 2`（对应 1、2 号位），但这是错的，
    三条独立证据互相印证：

    1. **号位定义**：`model/rosters.py` 头注与 `01-ti15-facts.md:270` 都明确
       "1=carry 2=mid 3=offlane 4=soft support 5=hard support"——2 号位是
       Mid，不是 Core 的一部分。
    2. **历史 5 卡结构**：`06-fantasy-rules.md` §E.2 记录 Player Card 时代
       （TI6-TI13）阵容原文是"**2 Core + 1 Mid + 2 Support** 共 5 张卡"——
       5 个号位无重叠无遗漏地分给三类，Mid 已经单独占 1 张，Core 只能是
       剩下的两个核心向号位（1、3），Support 是 4、5。若 Core=(1,2)，则
       2 号位同时被 Core 和 Mid 计费（重复计分），3 号位（offlane）则完全
       没有任何槽位覆盖（一个理应覆盖全队 5 人的 fantasy 系统，凭空漏掉
       整整一个位置的产出，不合理）。
    3. **实测数据交叉验证**：`06-fantasy-rules.md` §G.4 TI14 真实数据表
       把 Team Falcons 的 Malr1ne（本队 2 号位/中单）标注为 **"Mid"**，
       不是 "Core"——OpenDota 的 `fantasy_role` 字段把 Core/Mid 当成两个
       互斥类别，进一步印证 Mid（2 号位）不计入 Core。

    brief 自己给的这条测试断言之所以能在错误实现下通过，是因为期望值
    `(9.0+7.0)/2` 和被测代码的 `SLOT_POSITIONS["core"]=(1,2)` 用的是同一个
    错误前提，两者自洽——这正是"聚合/自洽断言测不出身份错位"的典型案例
    （与 Task 5 report 记录的 idx 编号错位被聚合计数断言掩盖是同一类问题）。
    """
    m = player_matrix({"kills": RATES}, items=["kills"])
    agg = slot_aggregate(m, ROSTER, POS, slot="core")
    assert agg["T1"]["kills"] == pytest.approx((9.0 + 5.0) / 2), (
        "Core Duo 应为 1、3 号位（carry+offlane）取平均，不是 1、2 号位"
    )


def test_support_slot_averages_positions_four_and_five():
    m = player_matrix({"kills": RATES}, items=["kills"])
    agg = slot_aggregate(m, ROSTER, POS, slot="support")
    assert agg["T1"]["kills"] == pytest.approx((3.0 + 2.0) / 2)


def test_mid_slot_is_a_single_player_not_averaged():
    m = player_matrix({"kills": RATES}, items=["kills"])
    agg = slot_aggregate(m, ROSTER, POS, slot="mid")
    assert agg["T1"]["kills"] == pytest.approx(7.0)


def test_branch_b_penalises_early_exit_far_more_than_branch_a():
    """§4.3：分支 B 缺席阶段记 0，深度压倒能力；分支 A 只取最好系列赛。"""
    m = {"T1": {"kills": 6.0}}
    deep = {"T1": {"group": 5, "playoff": 4}}
    early = {"T1": {"group": 5, "playoff": 0}}
    a_deep = expected_slot_score(m, deep, branch="A")["T1"]
    a_early = expected_slot_score(m, early, branch="A")["T1"]
    b_deep = expected_slot_score(m, deep, branch="B")["T1"]
    b_early = expected_slot_score(m, early, branch="B")["T1"]
    assert (b_deep - b_early) > (a_deep - a_early) * 2


def test_max_order_statistic_grows_slowly_not_logarithmically_in_scale():
    """护栏：取最大值随系列赛数增长**极慢**。不许放松。

    早期 plan 用 `per_game * (1 + ln(n))` 近似，实测相对误差 43%→130%
    且随 n 放大（真实 2→9 场只涨约 17%，该近似涨 89%），会系统性
    高估深跑收益，直接污染 A/B 分支对比。必须用真实模拟。
    """
    m = {"T1": {"k": 14.67}}
    s2 = expected_slot_score(m, {"T1": {"g": 2}}, branch="A", per_game_sd=4.72)["T1"]
    s9 = expected_slot_score(m, {"T1": {"g": 9}}, branch="A", per_game_sd=4.72)["T1"]
    assert s9 > s2, "系列赛越多，取到的最好成绩应更高"
    assert (s9 - s2) / s2 < 0.35, "增幅必须远小于 log 近似的 89%"


def test_calibrates_to_ti14_measured_distribution():
    """用 TI14 实测口径（场均 14.67、单局 sd 4.72）校准，
    5 个系列赛的取最大值期望应落在 19 分附近（06-fantasy-rules.md）。
    不许放松。"""
    m = {"T1": {"k": 14.67}}
    got = expected_slot_score(m, {"T1": {"g": 5}}, branch="A", per_game_sd=4.72)["T1"]
    assert 18.0 < got < 21.0


def test_unknown_branch_raises():
    with pytest.raises(ValueError):
        expected_slot_score({"T1": {"kills": 1.0}}, {"T1": {"group": 1}}, branch="C")


# ---- 补充测试：锁定实现阶段发现的修正、补齐身份级校验 ----

def test_core_slot_uses_offlane_not_mid_no_overlap_with_mid_slot():
    """直接钉住 SLOT_POSITIONS 常量本身，防止以后有人"优化"时改回 (1,2)。

    同时验证 Core 与 Mid 两个槽在号位层面完全不相交——这是 5 人无重叠
    分给 3 槽（2+1+2）的结构性要求，不是巧合。
    """
    assert SLOT_POSITIONS["core"] == (1, 3)
    assert SLOT_POSITIONS["mid"] == (2,)
    assert SLOT_POSITIONS["support"] == (4, 5)
    core, mid, support = (set(SLOT_POSITIONS[s]) for s in ("core", "mid", "support"))
    assert not (core & mid), "Core 与 Mid 号位不应重叠"
    assert not (core & support) and not (mid & support)
    assert core | mid | support == {1, 2, 3, 4, 5}, "三槽合起来应覆盖全部 5 个号位，不多不少"


def test_slot_aggregate_rejects_unknown_slot():
    """跟 expected_slot_score 的 test_unknown_branch_raises 对称：
    slot_aggregate 对未知槽位也该快速失败，不能静默返回空结果。"""
    m = player_matrix({"kills": RATES}, items=["kills"])
    with pytest.raises(ValueError):
        slot_aggregate(m, ROSTER, POS, slot="jungle")


def test_slot_aggregate_skips_team_with_no_matched_member_in_matrix():
    """某队在该槽位对应号位的选手完全没有出现在 matrix 里（比如样本量为 0
    被上游过滤掉）时，该队应从结果里跳过，而不是产出一个除以 0 的假平均。"""
    m = player_matrix({"kills": {11: RATES[11]}}, items=["kills"])  # 只有 1 号位选手
    agg = slot_aggregate(m, ROSTER, POS, slot="support")   # support 要 14/15 号位，matrix 里没有
    assert "T1" not in agg


def test_slot_aggregate_excludes_missing_item_from_denominator_not_zero_fills():
    """【Important】当槽位命中的 2 名成员中一人在 matrix 里缺某个 item 时，
    该 item 的分母必须只算实际持有该 item 的成员数——不能把缺失方按 0.0
    计入总和后仍除以全部成员数（那样会把该队该项的分数静默腰斩）。

    Core 槽（1、3 号位）：11 号位两项都有（kills/gpm），13 号位只有 kills、
    没有 gpm（比如该项样本量为 0 被上游 fit_rate_model 过滤掉，但另一项
    样本量足够）。修复前：gpm = (500.0 + 0.0) / 2 == 250.0（错误地把 13
    号位的缺失当成 0 分计入）。修复后：gpm 应该只由持有该项的 11 号位
    单独决定，即 500.0。"""
    matrix = {
        11: {"kills": 9.0, "gpm": 500.0},   # 1 号位：kills 和 gpm 都有
        13: {"kills": 5.0},                  # 3 号位：只有 kills，没有 gpm
    }
    agg = slot_aggregate(matrix, ROSTER, POS, slot="core")
    assert agg["T1"]["kills"] == pytest.approx((9.0 + 5.0) / 2), "两人都有的 item 应正常取平均"
    assert agg["T1"]["gpm"] == pytest.approx(500.0), (
        "只有 11 号位有 gpm，分母应该是 1（只算持有该 item 的成员），"
        "不能把没有 gpm 的 13 号位当成 0.0 计入分母，导致该项分数被静默腰斩一半"
    )


def test_expected_slot_score_branch_a_uses_total_series_across_both_stages():
    """分支 A"全程只取最好的一个系列赛"：应该是把 group+playoff 的系列赛数
    合并后一起抽最大值，而不是只看其中一段。用一个几乎必赢的场景验证：
    只算 group 的 5 场，跟 group+playoff 共 5+4=9 场相比，后者取到的最大值
    期望必须更高（多打 9 场比只打 5 场更可能刷出高分）。"""
    m = {"T1": {"k": 14.67}}
    group_only = expected_slot_score(m, {"T1": {"group": 5, "playoff": 0}},
                                      branch="A", per_game_sd=4.72)["T1"]
    group_and_playoff = expected_slot_score(m, {"T1": {"group": 5, "playoff": 4}},
                                             branch="A", per_game_sd=4.72)["T1"]
    assert group_and_playoff > group_only


def test_expected_slot_score_is_deterministic_given_fixed_seed():
    """项目全局约束：蒙特卡洛固定 seed，多次调用同一输入必须逐位重复。"""
    m = {"T1": {"k": 14.67}, "T2": {"k": 10.0}}
    dist = {"T1": {"group": 5, "playoff": 3}, "T2": {"group": 5, "playoff": 1}}
    r1 = expected_slot_score(m, dist, branch="A")
    r2 = expected_slot_score(m, dist, branch="A")
    assert r1 == r2


def test_expected_slot_score_handles_missing_team_in_series_dist_as_zero():
    """matrix 里有、series_dist 里没有的 key：不应该报错，应视为 0 场
    （没有系列赛数据 = 预测不出这个团队打了多少场，期望分退化为 0）。"""
    out = expected_slot_score({"T1": {"k": 10.0}}, {}, branch="A")
    assert out["T1"] == pytest.approx(0.0)
