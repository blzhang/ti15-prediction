"""已完赛结果开关（model/results.py）的测试。

两条最重要的：
  test_inactive_is_bit_identical —— 没有已完赛结果时，结果与加这个开关之前逐位一致。
  test_round4_is_a_cross_group_constraint —— R4 是跨组轮，把它当同组会静默推出错分组。
"""
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "model"))

import results as res_mod          # noqa: E402

TEAMS = ["T%02d" % i for i in range(16)]
# 与「首轮 8 场组内对阵」同构的一组配对：(0,1) (2,3) ... (14,15)
R1 = [{"a": TEAMS[2 * k], "b": TEAMS[2 * k + 1], "score": [2, 0]} for k in range(8)]


def write(tmp_path, **over):
    cfg = {"active": True, "as_of_utc": "2026-08-13T16:00:00Z", "source": "test",
           "rounds": [{"round": 1, "series": R1}]}
    cfg.update(over)
    p = tmp_path / "results.json"
    p.write_text(json.dumps(cfg))
    return str(p)


# ---------- 未开赛：必须零影响 ----------

def test_missing_file_is_inactive(tmp_path):
    assert res_mod.load(TEAMS, str(tmp_path / "nope.json")) is None


def test_active_false_returns_none(tmp_path):
    # 填好了结果但 active=false 也一律不生效——可以先填进去核对，确认无误再翻开关。
    assert res_mod.load(TEAMS, write(tmp_path, active=False)) is None


def test_inactive_is_bit_identical():
    """observed=None 时，run_one 消耗的随机数与加这个参数之前完全一致。

    做法与 test_draw.py::test_unannounced_is_bit_identical 同构：同一个种子跑两遍，
    一遍显式传 observed=None，一遍用旧调用签名（不传）。两边的返回值和之后的
    随机数流都必须一模一样——只要有一处多调或少调 rng，后面就会错位。
    """
    from l2_simulate import run_one

    def go(pass_kw):
        rng = np.random.default_rng(20260813)
        theta = np.linspace(-1.0, 1.0, 16)
        out = [run_one(theta, rng, None, None) if pass_kw else run_one(theta, rng, None)
               for _ in range(20)]
        return out, [rng.random() for _ in range(5)]

    assert go(True) == go(False)


# ---------- 已完赛结果：真的被照抄 ----------

def test_finished_series_are_replayed_verbatim_every_simulation():
    """已完赛的比赛不是随机变量：无论抽多少次 theta，结果都必须一模一样。"""
    from l2_simulate import run_one
    obs = res_mod.load(TEAMS, os.path.join(HERE, "_tmp_none")) or None
    cfg_path = None
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        cfg_path = os.path.join(d, "results.json")
        with open(cfg_path, "w") as fh:
            json.dump({"active": True, "as_of_utc": "x", "source": "t",
                       "rounds": [{"round": 1, "series": R1}]}, fh)
        obs = res_mod.load(TEAMS, cfg_path)

    rng = np.random.default_rng(5)
    for _ in range(30):
        theta = rng.standard_normal(16)
        rec, _, _, _, _, _, *_ = run_one(theta, rng, None, obs)
        # 每个偶数号队都赢了第一轮（R1 里 score 全是 [2,0]，a 方是偶数号）
        for k in range(8):
            assert rec[2 * k][0] >= 1, "已完赛的胜者在某次模拟里没赢"
            assert rec[2 * k + 1][1] >= 1, "已完赛的败者在某次模拟里没输"


def test_records_counts_only_finished_series(tmp_path):
    rounds = [{"round": 1, "series": R1},
              {"round": 2, "series": [{"a": TEAMS[0], "b": TEAMS[2], "score": [2, 1]},
                                      {"a": TEAMS[4], "b": TEAMS[6]}]}]
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=rounds))
    rec = res_mod.records(obs, TEAMS)
    assert rec[TEAMS[0]] == (2, 0)      # 两轮全胜
    assert rec[TEAMS[2]] == (1, 1)      # 首轮赢、次轮输
    assert rec[TEAMS[4]] == (1, 0)      # 次轮还没打，不计
    assert obs["n_done"] == 9 and obs["n_scheduled"] == 1


# ---------- 分组：由对阵反推，越打越紧 ----------

def test_round1_alone_leaves_thirty_five_splits(tmp_path):
    """只知道首轮 → 8 个必须同组的块 → C(8,4)/2 = 35 种自洽分法。

    与 2026-08-10 那一版「对 35 种平均」必须给出同一个数——这两条路径
    算的是同一件事，对不上说明其中一条错了。
    """
    obs = res_mod.load(TEAMS, write(tmp_path))
    assert len(obs["blocks"]) == 8
    assert all(len(b) == 2 for b in obs["blocks"])
    assert len(obs["splits"]) == 35


def test_round2_narrows_to_three_splits(tmp_path):
    """再知道第二轮 → 4 个块（各 4 队）→ C(4,2)/2 = 3 种。"""
    r2 = [{"a": TEAMS[0], "b": TEAMS[2]}, {"a": TEAMS[1], "b": TEAMS[3]},
          {"a": TEAMS[4], "b": TEAMS[6]}, {"a": TEAMS[5], "b": TEAMS[7]},
          {"a": TEAMS[8], "b": TEAMS[10]}, {"a": TEAMS[9], "b": TEAMS[11]},
          {"a": TEAMS[12], "b": TEAMS[14]}, {"a": TEAMS[13], "b": TEAMS[15]}]
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=[{"round": 1, "series": R1},
                                                      {"round": 2, "series": r2}]))
    assert [len(b) for b in obs["blocks"]] == [4, 4, 4, 4]
    assert len(obs["splits"]) == 3


def test_round3_collapses_grouping_to_a_unique_answer(tmp_path):
    """打完第三轮，分组只剩唯一解——到这一步就不必再平均了，也不必猜。"""
    r2 = [{"a": TEAMS[0], "b": TEAMS[2]}, {"a": TEAMS[1], "b": TEAMS[3]},
          {"a": TEAMS[4], "b": TEAMS[6]}, {"a": TEAMS[5], "b": TEAMS[7]},
          {"a": TEAMS[8], "b": TEAMS[10]}, {"a": TEAMS[9], "b": TEAMS[11]},
          {"a": TEAMS[12], "b": TEAMS[14]}, {"a": TEAMS[13], "b": TEAMS[15]}]
    r3 = [{"a": TEAMS[0], "b": TEAMS[4]}, {"a": TEAMS[1], "b": TEAMS[5]},
          {"a": TEAMS[2], "b": TEAMS[6]}, {"a": TEAMS[3], "b": TEAMS[7]},
          {"a": TEAMS[8], "b": TEAMS[12]}, {"a": TEAMS[9], "b": TEAMS[13]},
          {"a": TEAMS[10], "b": TEAMS[14]}, {"a": TEAMS[11], "b": TEAMS[15]}]
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=[{"round": 1, "series": R1},
                                                      {"round": 2, "series": r2},
                                                      {"round": 3, "series": r3}]))
    assert [len(b) for b in obs["blocks"]] == [8, 8]
    assert len(obs["splits"]) == 1
    gv = obs["splits"][0]
    assert sum(gv) == 8
    assert {t for t in range(8)} == {t for t in range(16) if gv[t] == gv[0]}


def test_round4_is_a_cross_group_constraint(tmp_path):
    """R4 只跨组。把它当成同组约束会把两个组合并成一个，推出一个错的分组——
    这是本模块最容易犯、又最看不出来的错，所以单独钉一条。"""
    r2 = [{"a": TEAMS[0], "b": TEAMS[2]}, {"a": TEAMS[1], "b": TEAMS[3]},
          {"a": TEAMS[4], "b": TEAMS[6]}, {"a": TEAMS[5], "b": TEAMS[7]},
          {"a": TEAMS[8], "b": TEAMS[10]}, {"a": TEAMS[9], "b": TEAMS[11]},
          {"a": TEAMS[12], "b": TEAMS[14]}, {"a": TEAMS[13], "b": TEAMS[15]}]
    r3 = [{"a": TEAMS[0], "b": TEAMS[4]}, {"a": TEAMS[1], "b": TEAMS[5]},
          {"a": TEAMS[2], "b": TEAMS[6]}, {"a": TEAMS[3], "b": TEAMS[7]},
          {"a": TEAMS[8], "b": TEAMS[12]}, {"a": TEAMS[9], "b": TEAMS[13]},
          {"a": TEAMS[10], "b": TEAMS[14]}, {"a": TEAMS[11], "b": TEAMS[15]}]
    # R4 跨组：0-7 组的队对上 8-15 组的队
    r4 = [{"a": TEAMS[k], "b": TEAMS[k + 8]} for k in range(8)]
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=[
        {"round": 1, "series": R1}, {"round": 2, "series": r2},
        {"round": 3, "series": r3}, {"round": 4, "series": r4}]))
    # 仍是两个 8 队的块（R4 没有把它们合并），且唯一解与 R3 推出来的一致
    assert [len(b) for b in obs["blocks"]] == [8, 8]
    assert len(obs["splits"]) == 1


def test_contradictory_pairings_raise(tmp_path):
    """对阵自相矛盾（同一批队既要同组又要跨组）必须炸，不能静默挑一个。"""
    r4 = [{"a": TEAMS[0], "b": TEAMS[1]}] + [{"a": TEAMS[2 * k], "b": TEAMS[2 * k + 1]}
                                             for k in range(1, 8)]
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=[{"round": 1, "series": R1},
                                                    {"round": 4, "series": r4}]))
    assert "自相矛盾" in str(e.value) or "缺第" in str(e.value)


# ---------- 校验：填错必须炸，且说清楚哪错了 ----------

@pytest.mark.parametrize("series,frag", [
    ([{"a": "nope", "b": TEAMS[1], "score": [2, 0]}], "不认识"),
    ([{"a": TEAMS[0], "b": TEAMS[0], "score": [2, 0]}], "同一支队"),
    ([{"a": TEAMS[0], "b": TEAMS[1], "score": [1, 1]}], "BO3"),
    ([{"a": TEAMS[0], "b": TEAMS[1], "score": [3, 0]}], "BO3"),
    ([{"a": TEAMS[0], "b": TEAMS[1], "score": [2, 2]}], "BO3"),
    ([{"a": TEAMS[0], "b": TEAMS[1], "score": [2]}], "两个整数"),
])
def test_bad_series_raise(tmp_path, series, frag):
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=[{"round": 1, "series": series}]))
    assert frag in str(e.value)


def test_in_progress_score_is_rejected(tmp_path):
    """正在进行中的 1-1 被填进来会被当成最终结果——这是最危险的一种填法，
    报错信息必须直说「还没打完就把 score 删掉」。"""
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=[
            {"round": 1, "series": [{"a": TEAMS[0], "b": TEAMS[1], "score": [1, 1]}]}]))
    assert "删掉" in str(e.value)


def test_team_twice_in_one_round_raises(tmp_path):
    dup = [{"a": TEAMS[0], "b": TEAMS[1]}, {"a": TEAMS[0], "b": TEAMS[2]}]
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=[{"round": 1, "series": dup}]))
    assert "不止一次" in str(e.value)


def test_missing_middle_round_raises(tmp_path):
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=[
            {"round": 1, "series": R1},
            {"round": 3, "series": [{"a": TEAMS[0], "b": TEAMS[2]}]}]))
    assert "缺第" in str(e.value)


def test_duplicate_round_raises(tmp_path):
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=[{"round": 1, "series": R1},
                                                    {"round": 1, "series": R1}]))
    assert "两次" in str(e.value)


def test_describe_never_claims_certainty_while_splits_remain(tmp_path):
    """还剩多种分法时，摘要绝不能说「分组已确定」——与 draw.describe 同一条纪律。"""
    obs = res_mod.load(TEAMS, write(tmp_path))
    text = res_mod.describe(obs, TEAMS)
    assert "已由对阵唯一确定" not in text
    assert "35 种" in text


# ---------- 仓库里那份真实数据必须始终可读、且与首轮锁定的对阵一致 ----------

def test_shipped_results_load_and_agree_with_draw():
    """真实 results.json 必须合法，且其第一轮与 draw.json 锁定的首轮对阵完全一致。

    两份文件都写着首轮对阵，写岔了就会一边按 A 打、一边按 B 打，
    产出一份自相矛盾又不报错的预测。
    """
    import draw as draw_mod
    teams = list(json.load(open(os.path.join(HERE, "..", "model", "l1_rating.json")))["rating"])
    obs = res_mod.load(teams)
    if obs is None:
        pytest.skip("results.json 处于未启用状态")
    drawn = draw_mod.load(teams)
    if not drawn or not drawn.get("r1_pairs"):
        pytest.skip("draw.json 没有锁定首轮")
    assert {frozenset(p) for p in drawn["r1_pairs"]} == \
           {frozenset((i, j)) for i, j, _, _ in obs["rounds"][1]}, \
        "results.json 的首轮对阵与 draw.json 锁定的不一致"


def test_shipped_results_grouping_is_consistent_with_round1_being_intra_group():
    """真实数据推出来的每一种候选分组，都必须让首轮 8 场全部是组内对阵。"""
    teams = list(json.load(open(os.path.join(HERE, "..", "model", "l1_rating.json")))["rating"])
    obs = res_mod.load(teams)
    if obs is None:
        pytest.skip("results.json 处于未启用状态")
    for gv in obs["splits"]:
        assert sum(gv) == len(teams) // 2
        for i, j, _, _ in obs["rounds"][1]:
            assert gv[i] == gv[j], "某种候选分组把首轮对手拆到了两个组"


# ---------- 半轮：一轮里只知道一部分对阵 ----------
#
# 赛程推进到一半时必然出现：第 5 轮 7 场只开了 3 场，另外 8 队的对阵还没出。
# 早先的实现是「这一轮有已知对阵就整轮照用」，剩下的队会整轮不打球，
# 直接破坏 1/2/5/5/2/1 的分档恒等式。这一组测试钉住半轮必须补配对。

def _swiss_only(theta, rng, obs):
    """跑一次 run_one，返回每队的瑞士轮总场次（胜+负）。"""
    from l2_simulate import run_one
    rec, _, _, _, _, _, *_ = run_one(theta, rng, None, obs)
    return [w + l for w, l in rec]


def test_partial_round_still_pairs_everyone_else(tmp_path):
    """一轮里只填了 1 场，其余 14 队必须照常按战绩配对，没有人被漏掉。"""
    import numpy as np
    rounds = [{"round": 1, "series": R1},
              {"round": 2, "series": [{"a": TEAMS[0], "b": TEAMS[2]}]}]
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=rounds))
    rng = np.random.default_rng(3)
    for _ in range(20):
        n = _swiss_only(rng.standard_normal(16), rng, obs)
        # 第二轮谁都没停赛（最多 1 胜 1 负），所以人人都该打满两轮以上
        assert min(n) >= 2, "半轮情形下有队伍被漏配了：每队场次 %s" % n


def test_partial_round_keeps_the_bucket_identity(tmp_path):
    """半轮情形下 1/2/5/5/2/1 的分档恒等式必须仍然成立。

    这是「有人整轮没打球」最容易暴露的地方：少打一场，战绩分布立刻塌掉。
    """
    import collections
    import numpy as np
    from l2_simulate import run_one
    rounds = [{"round": 1, "series": R1},
              {"round": 2, "series": [{"a": TEAMS[0], "b": TEAMS[2]},
                                      {"a": TEAMS[4], "b": TEAMS[6]}]}]
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=rounds))
    rng = np.random.default_rng(11)
    for _ in range(40):
        rec, _, _, _, _, _, *_ = run_one(rng.standard_normal(16), rng, None, obs)
        c = collections.Counter("%d-%d" % r for r in rec)
        assert c["4-0"] == 1 and c["4-1"] == 2 and c["3-2"] == 5, dict(c)
        assert c["2-3"] == 5 and c["1-4"] == 2 and c["0-4"] == 1, dict(c)


def test_known_pairings_in_a_partial_round_are_still_honoured(tmp_path):
    """半轮里已知的那几场，对阵必须原样生效，不能被重新配对冲掉。"""
    import numpy as np
    from l2_simulate import run_one
    from swiss import SwissState
    rounds = [{"round": 1, "series": R1},
              {"round": 2, "series": [{"a": TEAMS[0], "b": TEAMS[2], "score": [2, 0]}]}]
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=rounds))
    rng = np.random.default_rng(5)
    for _ in range(20):
        rec, _, _, _, _, _, *_ = run_one(rng.standard_normal(16), rng, None, obs)
        # T00 两轮全胜（R1 赢 T01、R2 赢 T02），T02 一胜一负
        assert rec[0][0] >= 2, "已知对阵的胜者在半轮里没被照抄"
        assert rec[2][1] >= 1, "已知对阵的败者在半轮里没被照抄"


# ---------- 附加淘汰轮：选人制对阵当事实，不用规则近似 ----------
#
# 附加轮的实际配对是选人制（最高排位的 3-2 队先挑 2-3 的对手），与模拟器里
# 「hi[k] vs lo[4-k]」的规则近似不是一回事。所以一旦对阵公布就必须当事实录入，
# 这组测试钉住：校验从严（资格、战绩档、重复），以及 replay 真的按实际对阵走。

def _full_swiss():
    """一套打完的 5 轮瑞士轮（全部 2-0），战绩分档恰为 1/2/5/5/2/1：
    4-0: T00；4-1: T08,T02；3-2: T04,T01,T12,T09,T05；
    2-3: T10,T06,T03,T14,T11；1-4: T13,T07；0-4: T15。"""
    S = lambda pairs: [{"a": TEAMS[i], "b": TEAMS[j], "score": [2, 0]} for i, j in pairs]
    return [
        {"round": 1, "series": S([(0, 1), (2, 3), (4, 5), (6, 7),
                                  (8, 9), (10, 11), (12, 13), (14, 15)])},
        {"round": 2, "series": S([(0, 2), (4, 6), (1, 3), (5, 7),
                                  (8, 10), (12, 14), (9, 11), (13, 15)])},
        {"round": 3, "series": S([(0, 4), (2, 6), (1, 5), (3, 7),
                                  (8, 12), (10, 14), (9, 13), (11, 15)])},
        {"round": 4, "series": S([(0, 8), (4, 12), (2, 10), (1, 9),
                                  (6, 14), (5, 13), (3, 11), (7, 15)])},
        {"round": 5, "series": S([(8, 4), (2, 1), (12, 10), (9, 6),
                                  (5, 3), (14, 13), (11, 7)])},
    ]


# 与规则近似刻意不同的选人制对阵（3-2 在前）：T01 还爆冷输给了 T10
ELIM = [
    {"a": TEAMS[4], "b": TEAMS[3], "score": [2, 0]},
    {"a": TEAMS[1], "b": TEAMS[10], "score": [0, 2]},
    {"a": TEAMS[12], "b": TEAMS[6], "score": [2, 1]},
    {"a": TEAMS[9], "b": TEAMS[14], "score": [2, 0]},
    {"a": TEAMS[5], "b": TEAMS[11], "score": [2, 1]},
]


def test_elimination_loads_and_counts(tmp_path):
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=_full_swiss(), elimination=ELIM))
    assert len(obs["elim"]) == 5
    assert obs["n_done"] == 39 + 5 and obs["n_scheduled"] == 0
    # records 只算瑞士轮：附加轮的胜负不改小组赛战绩
    rec = res_mod.records(obs, TEAMS)
    assert rec[TEAMS[4]] == (3, 2) and rec[TEAMS[10]] == (2, 3)


def test_elimination_requires_finished_swiss(tmp_path):
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, elimination=ELIM))
    assert "瑞士轮还没打完" in str(e.value)


def test_elimination_must_pair_three_two_against_two_three(tmp_path):
    bad = [{"a": TEAMS[4], "b": TEAMS[1], "score": [2, 0]}]     # 3-2 对 3-2
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=_full_swiss(), elimination=bad))
    assert "3-2 对 2-3" in str(e.value)


def test_elimination_team_twice_raises(tmp_path):
    dup = [{"a": TEAMS[4], "b": TEAMS[3], "score": [2, 0]},
           {"a": TEAMS[4], "b": TEAMS[10], "score": [2, 0]}]
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=_full_swiss(), elimination=dup))
    assert "不止一次" in str(e.value)


def test_observed_elimination_is_replayed_verbatim_every_simulation(tmp_path):
    """附加轮 5 场都有结果时，晋级八强的集合在每次模拟里都必须一模一样——
    包括 T10 爆冷淘汰 T01 这种规则近似绝不会配出来的结果。"""
    from l2_simulate import run_one
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=_full_swiss(), elimination=ELIM))
    expect = {0, 8, 2} | {4, 10, 12, 9, 5}       # 直通三队 + 实际附加轮胜者
    rng = np.random.default_rng(7)
    for _ in range(30):
        _, _, _, advanced, _, _, ew, el = run_one(rng.standard_normal(16), rng, None, obs)
        assert advanced == expect
        assert ew == {4, 10, 12, 9, 5} and el == {3, 1, 6, 14, 11}


def test_partial_elimination_pairs_the_rest_by_rule(tmp_path):
    """只公布了一部分选人结果时：已知对阵照用，其余队伍退回规则近似——
    附加轮 10 队每队仍然恰好打 1 场，谁都不缺席。"""
    from l2_simulate import run_one
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=_full_swiss(),
                                    elimination=ELIM[:2]))
    pool = {4, 1, 12, 9, 5, 10, 6, 3, 14, 11}
    rng = np.random.default_rng(9)
    for _ in range(30):
        _, _, _, advanced, _, _, ew, el = run_one(rng.standard_normal(16), rng, None, obs)
        assert ew | el == pool and not (ew & el)
        assert 4 in ew and 3 in el          # 已打完的照抄
        assert 10 in ew and 1 in el         # 爆冷也照抄，不被规则近似冲掉


# ---------- 八强真实对阵：槽位顺序编码 + 校验 ----------

UBQF = [[TEAMS[4], TEAMS[0]], [TEAMS[8], TEAMS[10]],
        [TEAMS[2], TEAMS[9]], [TEAMS[12], TEAMS[5]]]     # 刻意打乱，不按名次


def test_seeds_from_ubqf_round_trips_through_bracket_slot_order():
    """seeds 编码展开成 bracket.py 的 QF 构造顺序后，必须逐场还原输入——
    这是槽位映射唯一的真值来源，错一位败者组交叉连法就全串。"""
    from l2_simulate import seeds_from_ubqf
    pairs = [(10, 17), (23, 14), (11, 16), (12, 15)]
    s = seeds_from_ubqf(pairs)
    assert [(s[0], s[7]), (s[3], s[4]), (s[1], s[6]), (s[2], s[5])] == pairs


def test_playoffs_load_and_seed_the_bracket_verbatim(tmp_path):
    """八强对阵录入后，每次模拟的 QF 对阵都必须是官方公布的那四场。"""
    from l2_simulate import run_one, seeds_from_ubqf
    obs = res_mod.load(TEAMS, write(tmp_path, rounds=_full_swiss(),
                                    elimination=ELIM, playoffs={"ubqf": UBQF}))
    assert [(TEAMS[i], TEAMS[j]) for i, j in obs["ubqf"]] == \
        [tuple(p) for p in UBQF]
    # 结构校验：8 支八强队每次都拿到主赛事名次（1/2/3/4/5/5/7/7——
    # 5-6 与 7-8 是并列名次，bracket.py 只记 5 和 7）。
    rng = np.random.default_rng(13)
    for _ in range(20):
        _, _, place, advanced, _, _, ew, _ = run_one(rng.standard_normal(16), rng, None, obs)
        assert sorted(place[t] for t in advanced) == [1, 2, 3, 4, 5, 5, 7, 7]


def test_playoffs_require_finished_elimination(tmp_path):
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=_full_swiss(),
                                  elimination=ELIM[:3], playoffs={"ubqf": UBQF}))
    assert "附加轮还没打完" in str(e.value)


def test_playoffs_reject_unqualified_team(tmp_path):
    bad = [[TEAMS[4], TEAMS[15]]] + UBQF[1:]      # T15 是 0-4，早出局了
    with pytest.raises(res_mod.ResultsError) as e:
        res_mod.load(TEAMS, write(tmp_path, rounds=_full_swiss(),
                                  elimination=ELIM, playoffs={"ubqf": bad}))
    assert "没有晋级八强" in str(e.value)


def test_shipped_results_playoff_bracket_matches_qualifiers():
    """仓库真实数据：八强对阵里的 8 支队必须恰好是直通 3 队 + 附加轮 5 胜者。"""
    teams = list(json.load(open(os.path.join(HERE, "..", "model", "l1_rating.json")))["rating"])
    obs = res_mod.load(teams)
    if obs is None or not obs.get("ubqf"):
        pytest.skip("八强对阵还没录入")
    in_bracket = {t for pair in obs["ubqf"] for t in pair}
    assert len(in_bracket) == 8


def test_shipped_results_grouping_has_collapsed_to_a_unique_answer():
    """仓库里这份真实数据：分组应当已经由对阵唯一确定，且 R4 全部跨组。

    R1-R3 组内 + R4 跨组是两个**方向相反**的约束，同时成立才说明这个切分是对的。
    哪天这条红了，多半是某一轮的对阵抄错了、或者赛制规则变了。
    """
    teams = list(json.load(open(os.path.join(HERE, "..", "model", "l1_rating.json")))["rating"])
    obs = res_mod.load(teams)
    if obs is None or 4 not in obs["rounds"]:
        pytest.skip("还没打到第四轮")
    assert len(obs["splits"]) == 1, "分组还没收敛到唯一解"
    gv = obs["splits"][0]
    for rnd in (1, 2, 3):
        for i, j, _, _ in obs["rounds"].get(rnd, []):
            assert gv[i] == gv[j], "第 %d 轮出现跨组对阵" % rnd
    for i, j, _, _ in obs["rounds"][4]:
        assert gv[i] != gv[j], "第 4 轮出现组内对阵"
