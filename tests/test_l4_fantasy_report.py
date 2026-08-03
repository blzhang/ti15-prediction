"""对 model/l4_fantasy_report.py 的单元测试。

目前只覆盖 `_pool_coverage_from_scoring_items`——build_report() 本身要读
真实 CSV/JSON 数据文件，端到端跑一遍的成本和价值都更适合手工核对
（Step 5，见 task-7-report.md），不在这里重复。

【Minor 缺陷修复】`coverage.pool_coverage` 原来是手写常量字符串
（`{"red": "5(+1 代理 madstone)/6", "blue": "4/6", "green": "6/6"}`），跟
`model/fantasy_stats.py::SCORING_ITEMS` 完全没有挂钩——SCORING_ITEMS 以后
增删项，这几个数字不会跟着自动更新。改成从 SCORING_ITEMS 动态算
「可得/总数」，用一份自定义的最小 fixture 验证计算逻辑本身是数据驱动的，
不是又换了个地方硬编码。
"""
import pytest

from model.l4_fantasy_report import _pool_coverage_from_scoring_items, load_blob_joined_df
from model.fantasy_stats import SCORING_ITEMS


def test_pool_coverage_is_computed_from_a_custom_scoring_items_not_hardcoded():
    """用一份跟真实 SCORING_ITEMS 数字对不上的自定义 fixture 验证：输出
    确实随输入变化——如果实现偷偷用了硬编码常量而不是真的读参数，这里
    会得到跟 fixture 对不上的旧数字（例如真实数据的 "5/6"），从而被抓到。"""
    custom_items = [
        {"key": "a", "pool": "red", "available": True},
        {"key": "b", "pool": "red", "available": False},
        {"key": "c", "pool": "blue", "available": True},
    ]
    out = _pool_coverage_from_scoring_items(custom_items)
    assert out == {"red": "1/2", "blue": "1/1"}


def test_pool_coverage_on_real_scoring_items_matches_known_gaps():
    """跟 tests/test_fantasy_stats.py 里已经独立核实过的红/蓝/绿池覆盖数
    对齐：红池 5/6（唯一缺口 madstone）、蓝池 4/6（缺 watchers/lotuses）、
    绿池 6/6 全部可得。默认参数不传时应该读真实的 SCORING_ITEMS。"""
    out = _pool_coverage_from_scoring_items()
    assert out == {"red": "5/6", "blue": "4/6", "green": "6/6"}
    # 交叉核对：用真实 SCORING_ITEMS 独立算一遍，两边必须一致
    expected = {}
    for pool in sorted({i["pool"] for i in SCORING_ITEMS}):
        items = [i for i in SCORING_ITEMS if i["pool"] == pool]
        n_avail = sum(1 for i in items if i["available"])
        expected[pool] = "%d/%d" % (n_avail, len(items))
    assert out == expected


# ---- 补充测试：修复【3】blob csv 缺失时静默降级 ----
#
# `load_blob_joined_df` 原来在 blob_path 不存在时只打一句 stderr 警告，
# 然后把 smokes/tormentor/courier 三项全部填 0 继续跑完——产出物看起来
# 完全正常，没人会发现这三项计分项其实是假的（见
# .superpowers/sdd/fix-final-report.md【3】）。改成显式抛
# FileNotFoundError，不允许静默退化。

_MATCHES_CSV_HEADER = "match_id,account_id,start_time,kills\n"


def test_load_blob_joined_df_raises_when_blob_csv_missing(tmp_path):
    """blob_path 缺失时必须显式报错，不能像原实现那样打个警告就把
    smokes/tormentor/courier 三项悄悄填 0 继续跑完。"""
    csv_path = tmp_path / "matches.csv"
    csv_path.write_text(_MATCHES_CSV_HEADER + "1,100,1700000000,5\n")
    missing_blob = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        load_blob_joined_df(str(csv_path), str(missing_blob), account_ids=[100], since_ts=0)


def test_load_blob_joined_df_error_message_points_to_the_missing_path(tmp_path):
    """报错信息应该点名具体缺了哪个路径、并指向 06-fantasy-rules.md §F.5
    的重新生成方法，而不是一句笼统的"文件不存在"。"""
    csv_path = tmp_path / "matches.csv"
    csv_path.write_text(_MATCHES_CSV_HEADER + "1,100,1700000000,5\n")
    missing_blob = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError) as exc_info:
        load_blob_joined_df(str(csv_path), str(missing_blob), account_ids=[100], since_ts=0)

    msg = str(exc_info.value)
    assert str(missing_blob) in msg
    assert "06-fantasy-rules.md" in msg


def test_load_blob_joined_df_joins_when_blob_csv_present(tmp_path):
    """blob_path 存在时应按 match_id+account_id 左连接，缺失值按 0 处理
    （回归保护：不能因为把「缺失」改成抛异常，就连带改坏「存在时」的
    正常合并逻辑）。"""
    csv_path = tmp_path / "matches.csv"
    csv_path.write_text(
        _MATCHES_CSV_HEADER + "1,100,1700000000,5\n" + "2,100,1700000000,7\n"
    )
    blob_path = tmp_path / "blob.csv"
    blob_path.write_text(
        "match_id,account_id,smokes,tormentor,courier\n"
        "1,100,2,0,1\n"
    )
    df = load_blob_joined_df(str(csv_path), str(blob_path), account_ids=[100], since_ts=0)

    row1 = df[df["match_id"] == 1].iloc[0]
    assert row1["smokes"] == 2 and row1["tormentor"] == 0 and row1["courier"] == 1

    row2 = df[df["match_id"] == 2].iloc[0]
    assert row2["smokes"] == 0 and row2["tormentor"] == 0 and row2["courier"] == 0, (
        "blob 表里没有 match_id=2 的记录，左连接缺失值应按 0 处理，不是报错或留 NaN"
    )
