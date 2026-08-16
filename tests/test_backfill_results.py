"""回填脚本（model/backfill_results.py）的测试。

重点钉「二次相遇」：瑞士轮打过、附加轮又碰上（8/16 真实发生：Aurora vs
BoomBoys）。按 emit_match_table.py 的说明，第二场要**追加一行**，赛前概率
照抄第一行——赛前概率是对这对队伍的唯一承诺，不为第二次相遇重新估计。
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "model"))

from backfill_results import backfill, BackfillError          # noqa: E402

TEAMS = ["T%02d" % i for i in range(16)]


def _obs(rounds=None, elim=None):
    """直接构造 results.load 返回值的形状（索引元组），绕开完整 5 轮的铺垫。"""
    return {"rounds": rounds or {}, "elim": elim or []}


def _row(a, b, p="0.600000", stage="pending", result=""):
    return {"stage": stage, "team_a": a, "team_b": b, "p_a_wins_series": p,
            "frozen_at": "2026-08-02T00:00:00Z", "result_a_wins": result}


def test_swiss_backfill_fills_the_pending_row():
    rows = [_row(TEAMS[0], TEAMS[1])]
    changed, detail = backfill(rows, _obs({1: [(0, 1, True, 0)]}), TEAMS)
    assert changed == 1
    assert rows[0]["stage"] == "swiss_r1" and rows[0]["result_a_wins"] == "1"


def test_rematch_appends_a_row_and_copies_the_frozen_probability():
    """瑞士轮 R4 打过、附加轮又碰上：追加一行，p 与 frozen_at 照抄，互不覆盖。"""
    rows = [_row(TEAMS[0], TEAMS[1])]
    obs = _obs({4: [(0, 1, True, 0)]}, elim=[(0, 1, False, 1)])
    changed, detail = backfill(rows, obs, TEAMS)
    assert changed == 2 and len(rows) == 2
    first, second = rows
    assert first["stage"] == "swiss_r4" and first["result_a_wins"] == "1"
    assert second["stage"] == "advance" and second["result_a_wins"] == "0"
    assert second["p_a_wins_series"] == first["p_a_wins_series"]
    assert second["frozen_at"] == first["frozen_at"]


def test_rematch_backfill_is_idempotent():
    """重复回填不追加第三行、不改任何已有行。"""
    rows = [_row(TEAMS[0], TEAMS[1])]
    obs = _obs({4: [(0, 1, True, 0)]}, elim=[(0, 1, False, 1)])
    backfill(rows, obs, TEAMS)
    snapshot = [dict(r) for r in rows]
    changed, _ = backfill(rows, obs, TEAMS)
    assert changed == 0
    assert rows == snapshot


def test_contradicting_result_still_raises():
    rows = [_row(TEAMS[0], TEAMS[1], stage="swiss_r1", result="0")]
    with pytest.raises(BackfillError) as e:
        backfill(rows, _obs({1: [(0, 1, True, 0)]}), TEAMS)
    assert "对不上" in str(e.value)


def test_missing_pair_still_raises():
    with pytest.raises(BackfillError) as e:
        backfill([], _obs({1: [(0, 1, True, 0)]}), TEAMS)
    assert "找不到" in str(e.value)
