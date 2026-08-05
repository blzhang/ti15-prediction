"""site/odds.py 市场页渲染测试：两来源对照、留空规则、按融合概率排序。"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site"))
import odds  # noqa: E402


def _render(blended, decimal_odds, pm_mids):
    market = {"decimal_odds": decimal_odds, "captured_utc": "2026-08-01"}
    pm = {"prices": {t: {"mid": v, "bid": None, "ask": None, "last": None}
                     for t, v in pm_mids.items()},
          "captured_utc": "2026-08-05T09:00:00Z",
          "event_liquidity": 890000.0}
    return odds.render("/dota2", {}, blended, market, pm)


def test_render_shows_both_sources_and_dashes_for_unpriced_bookmaker():
    html = _render({"A": 0.5, "B": 0.3, "C": 0.2},
                   {"A": 2.0, "B": None, "C": None},
                   {"A": 0.6, "B": 0.3, "C": 0.3})
    assert "Polymarket" in html
    assert "2.00" in html                    # A 的庄家小数赔率
    assert "—" in html                       # B/C 的庄家两列留空
    assert "25.0%" in html                   # B 的 Polymarket 胜率 = 0.3/1.2
    assert "2026-08-01" in html              # 庄家抓取时间
    assert "2026-08-05T09:00:00Z" in html    # Polymarket 抓取时间
    assert "不提供任何投注建议" in html
    # 部分覆盖盘上不成立的旧「抽水」解释不得回归
    assert "公平市场应该正好等于" not in html
    # 覆盖数字必须来自数据，不是手抄：3 队 fixture、1 队有盘 → 1 与 2
    assert "只开了 1 支队的盘" in html
    assert "缺了 2 支队" in html
    assert "不过 3 份合约" in html
    assert "完整 3 队的夺冠盘" in html
    # 注：模板里「内部」两字被 <b> 包住（"这 %d 支队<b>内部</b>按比例去掉抽水"，
    # 该 <b> 标签是第二轮修复时按 Controller 原文写入的），字面串 "这 1 支队内部"
    # 不会连续出现，故按实际标签结构断言，验证同一处的数字仍是算出来的 1。
    assert "这 1 支队<b>内部</b>" in html
    assert "只影响这 1 队内部的排序" in html


def test_render_orders_rows_by_blended_probability_desc():
    html = _render({"A": 0.2, "B": 0.5, "C": 0.3},
                   {"A": None, "B": None, "C": None},
                   {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})
    assert html.index(">B<") < html.index(">C<") < html.index(">A<")
