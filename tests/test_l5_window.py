"""对 model/l5_window.py 的单元测试（纯函数层，全部走内联 fixture）。"""
import datetime

import pandas as pd
import pytest

from model.patches import patch_ts
from model.l5_window import window_arms, sliding_arms


def _utc(y, m, d):
    return int(datetime.datetime(y, m, d, tzinfo=datetime.timezone.utc).timestamp())


TI15_START = _utc(2026, 8, 13)


def test_baseline_arm_l955d_reproduces_the_production_2024_01_01_cutoff():
    """spec §3 的核心口径：现行产线写的是日历日期 2024-01-01，它对 TI15 的
    真实含义是「开赛前 955 天」。这条断言把两者的等价性钉死——baseline 臂
    的定义一旦漂了，整个回测比的就不再是产线策略。"""
    arms = window_arms(TI15_START, "7.41")
    assert arms["L955d"][0] == _utc(2024, 1, 1)


def test_window_arms_has_exactly_the_seven_preregistered_arms():
    arms = window_arms(TI15_START, "7.41")
    assert set(arms) == {"all", "L955d", "L365d", "L180d", "L105d", "patch", "prev_patch"}


def test_patch_arm_starts_exactly_at_the_patch_release_timestamp():
    arms = window_arms(TI15_START, "7.41")
    assert arms["patch"][0] == patch_ts("7.41")
    assert arms["prev_patch"][0] == patch_ts("7.40")


def test_all_arms_end_at_the_event_start():
    """任何一个臂都不许把开赛当天及以后的数据喂进训练——那是数据泄漏。"""
    arms = window_arms(TI15_START, "7.41")
    assert all(until == TI15_START for _, until in arms.values())


def test_all_arm_starts_at_zero():
    assert window_arms(TI15_START, "7.41")["all"][0] == 0


def test_sliding_arms_are_contiguous_non_overlapping_and_complete():
    """固定长度往前滑：段与段首尾相接、不重叠、不留空隙。"""
    arms = sliding_arms(TI15_START, length_days=105, n_steps=4)
    assert list(arms) == ["slide0", "slide1", "slide2", "slide3"]
    assert arms["slide0"][1] == TI15_START
    for k in range(3):
        assert arms["slide%d" % k][0] == arms["slide%d" % (k + 1)][1]
    for since, until in arms.values():
        assert until - since == 105 * 86400
