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


# ---------- 仓库里那份真实配置必须始终可读 ----------

def test_shipped_config_loads():
    """model/draw.json 现在应该是"未公布"状态；等填了分组，这条会校验它合法。"""
    import json as _j
    with open(draw_mod.PATH) as fh:
        cfg = _j.load(fh)
    real = _j.load(open(os.path.join(HERE, "..", "model", "l1_rating.json")))
    got = draw_mod.load(list(real["rating"]))          # 不合法会在这里抛
    assert (got is None) == (not cfg.get("announced"))
