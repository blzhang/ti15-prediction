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
from model.l4_fantasy_report import _pool_coverage_from_scoring_items
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
