"""照着游戏内「赛事预测 → 国际邀请赛」那张对阵表画一张同构的图，方便照着填。

为什么要照抄游戏里的版式：这一页的用途是**一边看图一边在客户端里点**。
版式对不上就得来回找「我现在填的是哪一格」，而 14 格里有 6 格叫「败者组第 N 轮」，
极容易串行。所以列的位置、格子的编号（A–G）、日期、队伍简称，全部与客户端一致，
读者可以逐格平移。

一处刻意的不同：客户端里后面几轮显示「?」，这里**填的是模型的建议**——
那正是这张图存在的理由。被推荐的一方画成实心圆点（对应客户端里点亮的那个单选钮）。

主题：`theme="page"` 用 CSS 变量（跟随站点明暗），`theme="card"` 用写死的深色
（长图/卡片是 PNG，没有 CSS 变量可用）。
"""

# 客户端里用的队伍简称。照抄截图，方便逐格对照着点。
SHORT = {
    "Iron Wing": "IW", "Team Spirit": "TSpirit", "TEAM VISION": "VSN",
    "BoomBoys": "BB", "Team Liquid": "Liquid", "Team Yandex": "TY",
    "Nigma Galaxy": "NGX", "Team Falcons": "FLCN",
}

# 版式：四列 + 两条泳道，与客户端一致
COL = [24, 290, 556, 822, 1046]
BOXW = 230
SLOTH = 30
HEADH = 20

PALETTE = {
    "page": {
        "bg": "none", "box": "var(--surface-1)", "line": "var(--grid)",
        "ink": "var(--ink)", "dim": "var(--ink-muted)", "sec": "var(--ink-2)",
        "pick": "var(--s1)", "gf": "var(--s2)",
    },
    "card": {
        "bg": "#0d0d0d", "box": "#1a1a19", "line": "#2c2c2a",
        "ink": "#ffffff", "dim": "#898781", "sec": "#c3c2b7",
        "pick": "#3987e5", "gf": "#eb6834",
    },
}


def _layout(pl):
    """把 bracket_homework.pick 展开成 14 个格子的「两位候选 + 谁被推荐」。

    后面几轮的候选**由前面的推荐决定**——这正是这道题的路径约束：填进第 2 轮的队
    必须是自己在第 1 轮推上去的。所以这里必须顺着推，不能各格独立取最大。
    """
    pick = pl["bracket_homework"]["pick"]
    qf = [(m["a"], m["b"]) for m in pl["ubqf"]]
    p = {r["stage"]: r["p_pick"] for r in pl["bracket_homework"]["rows"]}

    def other(pair, who):
        a, b = pair
        return b if who == a else a

    w = [pick["UBQF%d" % (k + 1)] for k in range(4)]
    l = [other(qf[k], w[k]) for k in range(4)]
    e_pair, f_pair = (w[0], w[1]), (w[2], w[3])
    g_pair = (pick["UBSF1"], pick["UBSF2"])
    lb1 = ((l[0], l[1]), (l[2], l[3]))
    # 败者组交叉：败2上 = 败1上胜者 vs F（胜者组第2轮下）的败者
    lb2 = ((pick["LBR1-1"], other(f_pair, pick["UBSF2"])),
           (pick["LBR1-2"], other(e_pair, pick["UBSF1"])))
    lb3 = (pick["LBQF-1"], pick["LBQF-2"])
    lbf = (pick["LBSF"], other(g_pair, pick["UBF"]))
    gf = (pick["UBF"], pick["LBF"])

    def cell(stage, label, date, pair, col, y, src=""):
        return {"stage": stage, "label": label, "date": date, "pair": pair,
                "win": pick[stage], "p": p[stage], "x": COL[col], "y": y, "src": src}

    return [
        cell("UBQF1", "A", "8月20日", qf[0], 0, 55),
        cell("UBQF2", "B", "8月20日", qf[1], 0, 160),
        cell("UBQF3", "C", "8月20日", qf[2], 0, 265),
        cell("UBQF4", "D", "8月20日", qf[3], 0, 370),
        cell("UBSF1", "E", "8月21日", e_pair, 1, 107),
        cell("UBSF2", "F", "8月21日", f_pair, 1, 317),
        cell("UBF", "G", "8月22日", g_pair, 2, 212),
        cell("GF", "总决赛", "8月23日", gf, 4, 245),
        cell("LBR1-1", "败1上", "8月21日", lb1[0], 0, 520, "A 的败者 / B 的败者"),
        cell("LBR1-2", "败1下", "8月21日", lb1[1], 0, 625, "C 的败者 / D 的败者"),
        cell("LBQF-1", "败2上", "8月22日", lb2[0], 1, 520, "败1上胜者 / F 的败者"),
        cell("LBQF-2", "败2下", "8月22日", lb2[1], 1, 625, "败1下胜者 / E 的败者"),
        cell("LBSF", "败3", "8月22日", lb3, 2, 572, "败2上胜者 / 败2下胜者"),
        cell("LBF", "败决", "8月23日", lbf, 3, 572, "败3胜者 / G 的败者"),
    ]


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render(pl, theme="page", show_prob=True):
    c = PALETTE[theme]
    cells = _layout(pl)
    by = {x["stage"]: x for x in cells}
    out = []

    def box(x):
        y, X, is_gf = x["y"], x["x"], x["stage"] == "GF"
        edge = c["gf"] if is_gf else c["line"]
        g = ['<g>']
        g.append('<text x="%d" y="%d" class="bl"><tspan class="lb">%s</tspan> · %s%s</text>'
                 % (X, y + 13, _esc(x["label"]), _esc(x["date"]),
                    ('　<tspan class="src">%s</tspan>' % _esc(x["src"])) if x["src"] else ""))
        g.append('<rect x="%d" y="%d" width="%d" height="%d" rx="6" fill="%s" '
                 'stroke="%s" stroke-width="%s"/>'
                 % (X, y + HEADH, BOXW, SLOTH * 2, c["box"], edge,
                    "1.8" if is_gf else "1"))
        g.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1"/>'
                 % (X, y + HEADH + SLOTH, X + BOXW, y + HEADH + SLOTH, c["line"]))
        for i, team in enumerate(x["pair"]):
            ty = y + HEADH + SLOTH * i + SLOTH / 2
            won = team == x["win"]
            # 单选钮：被推荐的一方点亮，对应客户端里你要点的那个圆点
            g.append('<circle cx="%d" cy="%.1f" r="6.5" fill="%s" stroke="%s" '
                     'stroke-width="1.4"/>'
                     % (X + 18, ty, c["pick"] if won else "none",
                        c["pick"] if won else c["dim"]))
            g.append('<text x="%d" y="%.1f" class="%s">%s</text>'
                     % (X + 33, ty + 4.5, "tm on" if won else "tm",
                        _esc(SHORT.get(team, team))))
            if show_prob and won:
                g.append('<text x="%d" y="%.1f" class="pb">%.0f%%</text>'
                         % (X + BOXW - 10, ty + 4.5, x["p"] * 100))
        g.append('</g>')
        return "".join(g)

    def link(a, b, side="right"):
        """从 a 格右缘牵到 b 格左缘，走直角折线。"""
        A, B = by[a], by[b]
        x1 = A["x"] + BOXW
        y1 = A["y"] + HEADH + SLOTH
        x2 = B["x"]
        y2 = B["y"] + HEADH + SLOTH
        mx = (x1 + x2) / 2
        return ('<path d="M%d %d H%.0f V%d H%d" fill="none" stroke="%s" '
                'stroke-width="1.2"/>' % (x1, y1, mx, y2, x2, c["line"]))

    for a, b in (("UBQF1", "UBSF1"), ("UBQF2", "UBSF1"),
                 ("UBQF3", "UBSF2"), ("UBQF4", "UBSF2"),
                 ("UBSF1", "UBF"), ("UBSF2", "UBF"), ("UBF", "GF"),
                 ("LBR1-1", "LBQF-1"), ("LBR1-2", "LBQF-2"),
                 ("LBQF-1", "LBSF"), ("LBQF-2", "LBSF"),
                 ("LBSF", "LBF"), ("LBF", "GF")):
        out.append(link(a, b))

    # 原来这里画过三条「败者掉下去」的虚线，已删。它们从胜者组的格子垂直下坠，
    # 会**从下面几个格子中间穿过去**，看起来像连错了线。赛制本身在首页那张结构图里
    # 讲得更清楚；这张图的职责是「照着填」，格子上的来源小字（A 的败者 / F 的败者）
    # 已经把关系说明白了，不需要再画线。

    for x in cells:
        out.append(box(x))

    heads = "".join(
        '<text x="%d" y="%d" class="col">%s</text>' % (COL[c], yy, t)
        for c, yy, t in ((0, 36, "胜者组第1轮"), (1, 36, "胜者组第2轮"),
                         (2, 36, "胜者组决赛"), (4, 36, "总决赛"),
                         (0, 501, "败者组第1轮"), (1, 501, "败者组第2轮"),
                         (2, 501, "败者组第3轮"), (3, 501, "败者组决赛")))
    lanes = heads

    return """<svg viewBox="0 0 1300 720" xmlns="http://www.w3.org/2000/svg"
 role="img" aria-label="TI15 主赛事预测面板建议填法">
<style>
  .bl{fill:%(dim)s;font-size:12.5px;font-family:inherit}
  .bl .lb{font-weight:700;fill:%(sec)s}
  .bl .src{font-size:11.5px;opacity:.8}
  .col{fill:%(dim)s;font-size:14px;font-weight:700;font-family:inherit}
  .tm{fill:%(sec)s;font-size:16px;font-family:inherit}
  .tm.on{fill:%(ink)s;font-weight:700}
  .pb{fill:%(dim)s;font-size:13px;text-anchor:end;font-family:inherit;
      font-variant-numeric:tabular-nums}
</style>
%(lanes)s
%(body)s
</svg>""" % {"dim": c["dim"], "sec": c["sec"], "ink": c["ink"],
             "lanes": lanes, "body": "\n".join(out)}
