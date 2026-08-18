"""对阵表 SVG 的渲染测试：交互版有热区、卡片版一个像素都不许变。"""
import os
import re
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site"))
import bracket_svg  # noqa: E402

STAGES = ("UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2",
          "LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "UBF", "LBF", "GF")
TEAMS = ["Iron Wing", "Team Spirit", "TEAM VISION", "BoomBoys",
         "Team Liquid", "Team Yandex", "Nigma Galaxy", "Team Falcons"]


def _pl():
    """最小 pl 切片：八强对阵 + 一份把每场都填成 UBQF 胜者的填法。"""
    qf = [("Iron Wing", "Team Spirit"), ("TEAM VISION", "BoomBoys"),
          ("Team Liquid", "Team Yandex"), ("Nigma Galaxy", "Team Falcons")]
    pick = {"UBQF1": "Iron Wing", "UBQF2": "TEAM VISION",
            "UBQF3": "Team Liquid", "UBQF4": "Nigma Galaxy",
            "UBSF1": "Iron Wing", "UBSF2": "Team Liquid", "UBF": "Iron Wing",
            "LBR1-1": "Team Spirit", "LBR1-2": "Team Yandex",
            "LBQF-1": "Team Spirit", "LBQF-2": "Team Yandex",
            "LBSF": "Team Spirit", "LBF": "Team Spirit", "GF": "Iron Wing"}
    return {
        "ubqf": [{"stage": "UBQF%d" % (k + 1), "a": a, "b": b} for k, (a, b) in enumerate(qf)],
        "bracket_homework": {
            "pick": pick,
            "rows": [{"stage": st, "p_pick": 0.5} for st in STAGES],
        },
    }


def test_交互版每格两行都有热区():
    svg = bracket_svg.render(_pl(), "page", interactive=True)
    assert svg.count('class="bkhit"') == 28, "14 格 × 2 行 = 28 个热区"
    for st in STAGES:
        assert 'data-stage="%s" data-side="0"' % st in svg
        assert 'data-stage="%s" data-side="1"' % st in svg


def test_交互版每行的队名圆点百分比都有稳定_id():
    """JS 只改这些节点的文本与属性，不重建 SVG——id 缺一个那一行就永远不刷新。"""
    svg = bracket_svg.render(_pl(), "page", interactive=True)
    for st in STAGES:
        for side in (0, 1):
            for kind in ("dot", "nm", "p"):
                assert 'id="bk-%s-%d-%s"' % (st, side, kind) in svg


def test_未选中那一行的百分比元素照样存在只是内容为空():
    """换选之后 JS 要把百分比挪到另一行。元素若不存在，JS 就得插节点——
    那等于把「只改属性」的约定破掉，也就没法保证不重排版式。"""
    svg = bracket_svg.render(_pl(), "page", interactive=True)
    # UBQF1 选的是 side 0（Iron Wing），所以 side 0 有数字、side 1 是空的
    on = re.search(r'<text id="bk-UBQF1-0-p"[^>]*>([^<]*)</text>', svg)
    off = re.search(r'<text id="bk-UBQF1-1-p"[^>]*>([^<]*)</text>', svg)
    assert on and on.group(1).endswith("%"), "选中那行该有百分比"
    assert off and off.group(1) == "", "未选中那行该是空的，但元素必须在"


def test_交互版每行只输出一个百分比元素不会重复():
    """靠 render() 里 if interactive / elif show_prob and won 这一组 if/elif
    保证每行只出一个 class="pb" 元素。哪天 elif 被错改成独立的 if，
    选中那行就会重复输出两个——id 撞车，前端 JS 按 id 更新时也分不清改哪个，
    视觉上还会叠成两行数字。"""
    svg = bracket_svg.render(_pl(), "page", interactive=True)
    assert svg.count('class="pb"') == 28, "14 格 × 2 行 = 28 个百分比元素，一个都不能多"


def test_卡片版没有任何交互痕迹():
    """长图是 PNG，热区与 id 对它毫无用处，只会让产物变大、diff 变脏。"""
    svg = bracket_svg.render(_pl(), "card")
    assert "bkhit" not in svg
    assert "id=\"bk-" not in svg


def test_不开交互时输出与开交互前完全一致():
    """默认参数不改变任何既有行为——卡片与无 JS 回退都依赖这一条。"""
    a = bracket_svg.render(_pl(), "page")
    b = bracket_svg.render(_pl(), "page", interactive=False)
    assert a == b
    assert "bkhit" not in a
