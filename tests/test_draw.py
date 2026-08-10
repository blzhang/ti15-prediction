"""分组开关（model/draw.py）的测试。

最重要的一条是 test_unannounced_is_bit_identical：证明"没填分组时，
结果与加这个开关之前逐位一致"。加开关的全部意义就是**现在零风险**，
这条测试没了，这个前提就无从保证。
"""
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "model"))

import draw as draw_mod          # noqa: E402
from swiss import SwissState, pair_round, active_teams   # noqa: E402

TEAMS = ["T%02d" % i for i in range(16)]
A, B = TEAMS[:8], TEAMS[8:]


def write(tmp_path, **over):
    cfg = {"announced": True, "group_a": A, "group_b": B, "round1": [], "source": "test"}
    cfg.update(over)
    p = tmp_path / "draw.json"
    p.write_text(json.dumps(cfg))
    return str(p)


# ---------- 未公布：必须零影响 ----------

def test_missing_file_is_unannounced(tmp_path):
    assert draw_mod.load(TEAMS, str(tmp_path / "nope.json")) is None


def test_announced_false_returns_none(tmp_path):
    # 即使把分组填好了，只要 announced 是 false 就一律不生效——
    # 这样可以先把分组填进去核对，确认无误再翻开关。
    assert draw_mod.load(TEAMS, write(tmp_path, announced=False)) is None


def test_unannounced_is_bit_identical():
    """未公布时，pair_round 消耗的随机数与加 fixed_r1 参数之前完全一致。

    做法：同一个种子跑两遍，一遍显式传 fixed_r1=None，一遍完全不传这个参数
    （即旧调用签名）。两边的配对结果和之后的随机数流都必须一模一样——
    只要有一处多调或少调 rng，后面的随机数就会错位，结果必然不同。
    """
    def go(pass_kw):
        rng = np.random.default_rng(12345)
        s = SwissState(16)
        s.group = list(rng.permutation([0] * 8 + [1] * 8))
        out = []
        for rnd in range(5):
            act = active_teams(s)
            if len(act) < 2:
                break
            pairs = (pair_round(s, rnd, rng, active=act, fixed_r1=None) if pass_kw
                     else pair_round(s, rnd, rng, active=act))
            out.append(sorted(pairs))
            for a, b in pairs:
                s.record(a, b, rng.random() < 0.5, 0)
        # 把配对之后的随机数流也带上：错位一次这里就对不上
        return out, [rng.random() for _ in range(5)]

    assert go(True) == go(False)


# ---------- 已公布：真的生效 ----------

def test_group_vec_matches_config(tmp_path):
    d = draw_mod.load(TEAMS, write(tmp_path))
    assert d["group_vec"] == [0] * 8 + [1] * 8
    assert d["r1_pairs"] is None          # round1 留空 = 首轮仍随机
    assert d["source"] == "test"


def test_group_vec_follows_actual_membership(tmp_path):
    # 交错分组，确认不是靠"前 8 个"的巧合过的
    a2, b2 = TEAMS[0::2], TEAMS[1::2]
    d = draw_mod.load(TEAMS, write(tmp_path, group_a=a2, group_b=b2))
    assert d["group_vec"] == [0, 1] * 8


def test_fixed_r1_is_used_verbatim():
    pairs = [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13), (14, 15)]
    s = SwissState(16)
    got = pair_round(s, 0, np.random.default_rng(1), active=range(16), fixed_r1=pairs)
    assert got == pairs


def test_fixed_r1_does_not_leak_into_later_rounds():
    """fixed_r1 只管第一轮。后面几轮必须照常按战绩配对，不能重复第一轮对阵。"""
    pairs = [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13), (14, 15)]
    rng = np.random.default_rng(7)
    s = SwissState(16)
    s.group = [0] * 8 + [1] * 8
    for a, b in pair_round(s, 0, rng, active=active_teams(s), fixed_r1=pairs):
        s.record(a, b, True, 0)
    r2 = pair_round(s, 1, rng, active=active_teams(s), fixed_r1=pairs)
    assert sorted(r2) != sorted(pairs)
    for a, b in r2:                       # 瑞士轮不能重复交手
        assert b not in s.played[a]


# ---------- 校验：填错必须炸，且说清楚哪错了 ----------

@pytest.mark.parametrize("over,frag", [
    ({"group_a": A[:7]}, "8 支队"),
    ({"group_b": B + ["T99"]}, "8 支队"),
    ({"group_a": ["nope"] + A[1:]}, "找不到"),
    ({"group_a": A, "group_b": A}, "多次"),
])
def test_bad_groups_raise(tmp_path, over, frag):
    with pytest.raises(draw_mod.DrawError) as e:
        draw_mod.load(TEAMS, write(tmp_path, **over))
    assert frag in str(e.value)


def test_cross_group_round1_raises(tmp_path):
    """首轮跨组是最容易犯又最难看出的错——分组和对阵填反了就会这样。

    它不会让程序崩，只会让分档结构失效、产出一份看着正常的错预测，
    所以必须在入口挡掉。
    """
    bad = [[A[0], B[0]]] + [[A[i], A[i + 1]] for i in (1, 3, 5)] \
        + [[B[i], B[i + 1]] for i in (1, 3, 5)] + [[A[7], B[7]]]
    with pytest.raises(draw_mod.DrawError) as e:
        draw_mod.load(TEAMS, write(tmp_path, round1=bad))
    assert "跨组" in str(e.value)


def test_round1_must_cover_all_sixteen(tmp_path):
    dup = [[A[0], A[1]]] * 4 + [[B[0], B[1]]] * 4
    with pytest.raises(draw_mod.DrawError) as e:
        draw_mod.load(TEAMS, write(tmp_path, round1=dup))
    assert "不止一次" in str(e.value)


def test_round1_wrong_count_raises(tmp_path):
    with pytest.raises(draw_mod.DrawError) as e:
        draw_mod.load(TEAMS, write(tmp_path, round1=[[A[0], A[1]]]))
    assert "8 组" in str(e.value)


# ---------- 只锁首轮、分组留空 ----------
#
# 2026-08-10 的真实处境：首轮 8 场对阵有两个独立来源，可以当事实；A/B 分组
# 官方从没公布过。此前一版从转播分流"推"了一个分组填进去——那是把 35 种
# 同样自洽的切法里挑了一种当事实，等于凭空多了一个自由度。
# 这个模式是正确的做法：首轮照填，分组留空，由模拟器对 35 种切法平均。

def test_round1_without_groups_is_allowed(tmp_path):
    """两组留空 + grouping=unknown + 填了 round1 = 「只锁首轮，分组未知」。"""
    got = draw_mod.load(TEAMS, write(tmp_path, group_a=[], group_b=[], grouping="unknown",
                                     round1=[[TEAMS[2 * k], TEAMS[2 * k + 1]] for k in range(8)]))
    assert got is not None
    assert got["group_vec"] is None          # 没有分组可用
    assert len(got["r1_pairs"]) == 8         # 但首轮是确定的
    assert got["grouping"] == "unknown"


def test_empty_groups_without_explicit_unknown_is_rejected(tmp_path):
    """两组留空但没声明 grouping=unknown —— 拒绝。

    留空必须是**明说**的选择，不能是漏填。漏填却被静默当成「分组未知」，
    等于换了一个模型还没人知道。grouping 缺省是 official，正好在这里撞上报错。
    """
    with pytest.raises(draw_mod.DrawError) as e:
        draw_mod.load(TEAMS, write(tmp_path, group_a=[], group_b=[],
                                   round1=[[TEAMS[2 * k], TEAMS[2 * k + 1]] for k in range(8)]))
    assert "grouping" in str(e.value)


def test_round1_without_groups_forces_grouping_unknown(tmp_path):
    """分组留空却声称 official/inferred 是自相矛盾的配置，必须拦下。"""
    r1 = [[TEAMS[2 * k], TEAMS[2 * k + 1]] for k in range(8)]
    for claim in ("official", "inferred"):
        with pytest.raises(draw_mod.DrawError) as e:
            draw_mod.load(TEAMS, write(tmp_path, group_a=[], group_b=[],
                                       round1=r1, grouping=claim))
        assert "grouping" in str(e.value)


def test_both_groups_and_round1_empty_is_rejected(tmp_path):
    """两组留空、round1 也留空 —— 这份配置什么都没说，却把 announced 打开了。
    静默当成「已公布」会产出一版与未公布完全相同、却标着 announced 的预测。"""
    with pytest.raises(draw_mod.DrawError):
        draw_mod.load(TEAMS, write(tmp_path, group_a=[], group_b=[], round1=[],
                                   grouping="unknown"))


def test_group_split_randomization_respects_fixed_pairs():
    """核心正确性：随机出来的分组必须让每个固定对子同组。

    切法有 C(8,4)/2 = 35 种，全部满足「对子不跨组」。抽 300 次，
    每次都必须满足；同时必须真的在变（不是永远同一种切法）。
    """
    from l2_simulate import group_vec_from_pairs
    pairs = [(2 * k, 2 * k + 1) for k in range(8)]
    rng = np.random.default_rng(7)
    seen = set()
    for _ in range(300):
        gv = group_vec_from_pairs(pairs, rng)
        assert sum(gv) == 8, "两组必须各 8 队"
        for i, j in pairs:
            assert gv[i] == gv[j], "固定对子被拆到了两个组"
        seen.add(tuple(gv))
    assert len(seen) > 1, "分组没有在随机化，退化成了固定一种"


def test_group_split_covers_all_thirty_five_splits():
    """35 种切法应当都能被抽到——少抽一种就是在偷偷加先验。"""
    from l2_simulate import group_vec_from_pairs
    pairs = [(2 * k, 2 * k + 1) for k in range(8)]
    rng = np.random.default_rng(11)
    # 用「0 组包含哪几个对子」的规范形式计数，两组互换算同一种
    seen = set()
    for _ in range(4000):
        gv = group_vec_from_pairs(pairs, rng)
        side = frozenset(k for k, (i, _) in enumerate(pairs) if gv[i] == gv[pairs[0][0]])
        seen.add(side)
    assert len(seen) == 35, "抽到的切法只有 %d 种，应为 35" % len(seen)


# ---------- 分组的出处：官方公布 vs 我们推的 ----------
#
# 2026-08-10 起这条区分是硬要求。当时的实际情况是：首轮 8 场对阵有两个
# 独立来源，可以当事实用；A/B 分组官方**从没公布过**，是从转播分流推的，
# 而同样自洽的切法还有 34 种。两者混在一个 announced=true 里发出去，读者
# 只会读成「分组公布了」——那是我们没有的东西。所以出处必须是结构化字段，
# 一路带到产物和站点上，而不是写在 _说明 里等人去读。

def test_grouping_defaults_to_official_when_absent(tmp_path):
    """旧配置没有这个字段：默认按官方公布处理，保持向后兼容。"""
    got = draw_mod.load(TEAMS, write(tmp_path))
    assert got["grouping"] == "official"


def test_grouping_inferred_is_carried_through(tmp_path):
    got = draw_mod.load(TEAMS, write(tmp_path, grouping="inferred"))
    assert got["grouping"] == "inferred"


def test_unknown_grouping_value_raises(tmp_path):
    """只认这两个值。写错一个字（比如 "infered"）不能静默当成 official——
    那正好把「推测」降级成「事实」，是这个字段最该防住的失败。"""
    with pytest.raises(draw_mod.DrawError) as e:
        draw_mod.load(TEAMS, write(tmp_path, grouping="infered"))
    assert "grouping" in str(e.value)


def test_describe_never_says_announced_when_grouping_is_inferred(tmp_path):
    """describe() 的第一行会被打进重算日志、也会被人抄进文案。
    分组是推的时候，这一行绝不能出现「分组已公布」。"""
    got = draw_mod.load(TEAMS, write(tmp_path, grouping="inferred"))
    text = draw_mod.describe(got, TEAMS)
    assert "分组已公布" not in text
    assert "推测" in text


def test_describe_says_announced_when_official(tmp_path):
    got = draw_mod.load(TEAMS, write(tmp_path, grouping="official"))
    assert "分组已公布" in draw_mod.describe(got, TEAMS)


# ---------- 仓库里那份真实配置必须始终可读 ----------

def test_shipped_config_loads():
    """model/draw.json 现在应该是"未公布"状态；等填了分组，这条会校验它合法。"""
    import json as _j
    with open(draw_mod.PATH) as fh:
        cfg = _j.load(fh)
    real = _j.load(open(os.path.join(HERE, "..", "model", "l1_rating.json")))
    got = draw_mod.load(list(real["rating"]))          # 不合法会在这里抛
    assert (got is None) == (not cfg.get("announced"))


def test_shipped_config_locks_round1_and_leaves_grouping_unknown():
    """当前这一版：首轮已证实并锁定，分组明确未知（不猜）。

    哪天官方真公布了分组、改 draw.json 时这条会红——提醒一并把站点与文案里
    「分组未公布、已平均掉」的措辞改掉。
    """
    real = json.load(open(os.path.join(HERE, "..", "model", "l1_rating.json")))
    got = draw_mod.load(list(real["rating"]))
    if got is None:
        pytest.skip("draw.json 处于未公布状态")
    assert got["grouping"] == "unknown"
    assert got["group_vec"] is None
    assert got["r1_pairs"] and len(got["r1_pairs"]) == 8
