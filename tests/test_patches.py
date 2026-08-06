"""对 model/patches.py 的单元测试。

版本发布时间是整个回测的地基：patch 臂的起点就是这张表里的时间戳。
表错了，回测的 treatment 臂就是错的，而且不会有任何地方报错——所以
这里既钉死具体数值，也钉死"查不到必须抛错"这条不许静默回退的约定。
"""
import pytest

from model.patches import PATCH_RELEASE_UTC, patch_ts, previous_patch


def test_patch_ts_7_41_matches_opendota_constants():
    """7.41 = 2026-03-24T00:50:59Z，取自 OpenDota constants/patch。
    这是 TI15 的版本，也是这次回测要验证的那个切点，数值必须钉死。"""
    assert patch_ts("7.41") == 1774313459


def test_patch_ts_is_strictly_increasing_over_the_table():
    """表里的版本按名字升序排列时，发布时间必须也严格递增。
    抄错一个日期最容易表现为顺序颠倒，这条能直接抓到。"""
    names = sorted(PATCH_RELEASE_UTC)
    stamps = [patch_ts(n) for n in names]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_patch_ts_raises_on_unknown_patch_instead_of_falling_back():
    """查不到必须 KeyError。静默回退（例如返回 0）会让该届的 patch 臂
    悄悄退化成全历史臂，而报告里完全看不出来。"""
    with pytest.raises(KeyError):
        patch_ts("7.99")


def test_previous_patch_walks_back_by_release_time():
    assert previous_patch("7.41") == "7.40"
    assert previous_patch("7.39") == "7.38"


def test_previous_patch_raises_on_earliest_entry():
    """表里最早的版本没有上一个——不能悄悄返回它自己。"""
    earliest = sorted(PATCH_RELEASE_UTC, key=patch_ts)[0]
    with pytest.raises(KeyError):
        previous_patch(earliest)


def test_previous_patch_raises_on_unknown_patch():
    with pytest.raises(KeyError):
        previous_patch("7.99")
