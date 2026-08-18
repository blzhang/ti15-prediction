"""抄作业页前端编辑器的数据契约测试。

守的是「页面拿到的东西够不够它自己算完一遍」——前端不再回头找服务端，
所以缺一项都会变成页面上一个静悄悄的 0 或空白。
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site"))
import homework  # noqa: E402

STAGES = ("UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2",
          "LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "UBF", "LBF", "GF")
TEAMS = ["Iron Wing", "Team Spirit", "TEAM VISION", "BoomBoys",
         "Team Liquid", "Team Yandex", "Nigma Galaxy", "Team Falcons"]


def _pl():
    """最小可用的 p8_playoffs.json 切片。"""
    qf = [("Iron Wing", "Team Spirit"), ("TEAM VISION", "BoomBoys"),
          ("Team Liquid", "Team Yandex"), ("Nigma Galaxy", "Team Falcons")]
    win_p = {st: {t: 1.0 / 8 for t in TEAMS} for st in STAGES}
    return {
        "ubqf": [{"stage": "UBQF%d" % (k + 1), "a": a, "b": b,
                  "time_cst": "8/20 %02d:00" % (10 + k * 3)}
                 for k, (a, b) in enumerate(qf)],
        "bracket_homework": {
            "pick": {st: TEAMS[0] for st in STAGES},
            "pick_bits": 5753,
            "win_p": win_p,
            "rows": [{"stage": st, "cn": "第%s场" % st, "panel": st,
                      "time_cst": "8/2x", "pick": TEAMS[0], "p_pick": 0.125,
                      "top": []} for st in STAGES],
            "stats": {"expected": 4.2, "random": 1.75, "greedy_upper": 5.0,
                      "n_matches": 14, "n_brackets": 16384},
        },
    }


def test_qf_顺序与元素顺序就是_bit_的_0_1():
    """qf[k][0] 必须是 UBQF{k+1} 的 a——bit 取 0 时选中的正是它。"""
    d = homework.bracket_data(_pl())
    assert d["qf"] == [["Iron Wing", "Team Spirit"], ["TEAM VISION", "BoomBoys"],
                       ["Team Liquid", "Team Yandex"], ["Nigma Galaxy", "Team Falcons"]]


def test_win_p_是全表且每格八支队():
    d = homework.bracket_data(_pl())
    assert set(d["win_p"]) == set(STAGES)
    for st in STAGES:
        assert len(d["win_p"][st]) == 8, st


def test_每格都有面板编号与时间():
    """图上和卡片上都要印它们；缺了就会渲染出「undefined · undefined」。

    只断真值抓不住 panel 与 cn 被接反的情况——fixture 里两个字段都是非空
    字符串，接反了照样非空。改成断言具体值，两个字段本身就取不同的串
    （panel=st，cn="第{st}场"），接反了会立刻不相等。"""
    d = homework.bracket_data(_pl())
    assert set(d["meta"]) == set(STAGES)
    for st in STAGES:
        assert d["meta"][st]["panel"] == st
        assert d["meta"][st]["cn"] == "第%s场" % st
        assert d["meta"][st]["time"] == "8/2x"


def test_简称表覆盖全部八支队():
    """图上印的是客户端里的简称（IW / TSpirit / FLCN…），缺一支就会印出全名撑破格子。"""
    d = homework.bracket_data(_pl())
    for t in TEAMS:
        assert t in d["short"], t


def test_统计只带前端真的会用的两项():
    """greedy_upper 与填法无关，只出现在服务端渲染的静态文案里，不进前端。"""
    d = homework.bracket_data(_pl())
    assert d["stats"] == {"expected": 4.2, "random": 1.75}


def test_bits_原样带出():
    """fixture 里 pick_bits 若是 0，这条测试连「转发 bh['pick_bits']」与
    「硬编码 'bits': 0」都区分不开——换成一个非零值（真实产物里是 5753）
    才能确认这里是真的原样带出，不是巧合。"""
    assert homework.bracket_data(_pl())["bits"] == 5753
