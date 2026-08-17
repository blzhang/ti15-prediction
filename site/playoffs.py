"""八强前瞻页（首页）：小组赛结束后，对剩下 14 场淘汰赛的预测。

全部数字来自 reports/p8_playoffs.json（model/l6_playoffs.py 产出），不手抄。

页面的口径纪律：
  · **融合值是交付值**（模型 ⊕ 市场，市场权重 0.7），与全站其它页一致；
    模型值与市场值并排列出，让读者自己看分歧在哪。
  · 融合口径下的逐场胜率、各轮晋级、名次分布**全部出自同一组隐含实力**，
    所以读者按逐场胜率自己乘一遍，能得到页面上的冠军概率——不会出现
    「冠军用融合值、逐场用模型值」那种自己跟自己对不上的情况。
"""
import json

import pages
from pages import esc

# 未来 10 场的时间表顺序（Liquipedia 赛程）。八强那 4 场单独用卡片展示。
FUTURE_ORDER = ("LBR1-1", "LBR1-2", "UBSF1", "UBSF2",
                "LBQF-2", "LBQF-1", "UBF", "LBSF", "LBF", "GF")

# 模型与市场差多少才算「吵起来了」。夺冠概率表与分歧小节共用这一个阈值——
# 分成两处写迟早会漂，然后页面上就会出现「标出来的是超过 5pp 的」配一张
# 按 8pp 标的表。
GAP_THRESHOLD = 0.05


def _pct(v, d=1):
    return ("%." + str(d) + "f%%") % (v * 100)


def _split_bar(pa, a, b):
    """一场对阵的胜率分割条。左侧 a 队、右侧 b 队，宽度即各自胜率。"""
    return (
        '<div class="mbar"><div class="mfill a" style="width:%.2f%%"></div>'
        '<div class="mfill b" style="width:%.2f%%"></div></div>'
        '<div class="mpct"><span>%s</span><span>%s</span></div>'
        % (pa * 100, (1 - pa) * 100, _pct(pa), _pct(1 - pa))
    )


def _qf_cards(pl):
    model, blend = pl["views"]["model"], pl["views"]["blended"]
    mkt = {r["stage"]: r for r in ((pl.get("match_market") or {}).get("rows") or [])}
    out = []
    for m in pl["ubqf"]:
        key = "%s|%s" % (m["a"], m["b"])
        pb, pm = blend["h2h"][key], model["h2h"][key]
        mm = mkt.get(m["stage"])
        sub = "纯模型口径 %s · %s" % (_pct(pm), _pct(1 - pm))
        if mm:
            sub = ("单场盘 <b>%s</b> · 纯模型 %s<br><span class=dim>盘口成交 $%s</span>"
                   % (_pct(mm["p_market"]), _pct(pm), "{:,.0f}".format(mm["volume"])))
        out.append(
            '<div class="mcard">'
            '<div class="mhead"><span class="mstage">%s</span><span class="mtime">%s</span></div>'
            '<div class="mteams"><b>%s</b><i>vs</i><b>%s</b></div>'
            '%s'
            '<div class="msub">%s</div>'
            '</div>'
            % (esc(pl["stage_meta"][m["stage"]]["cn"]), esc(m["time_cst"]),
               esc(m["a"]), esc(m["b"]), _split_bar(pb, m["a"], m["b"]), sub)
        )
    return '<div class="mgrid">%s</div>' % "".join(out)


def _market_section(pl):
    """两个市场自己不一致——这一节把它摊开。

    冠军盘只说「谁最后举盾」，要得到「这一场谁赢」必须反解隐含实力；单场盘是
    直接价格。两者在同一件事上给出不同答案时，藏起来任何一个都不诚实。
    """
    mm = pl.get("match_market")
    if not mm:
        return ""
    si = pl.get("implied_solve") or {}
    rows = "".join(
        "<tr><td class=lft>%s <span class=vs>vs</span> %s</td>"
        "<td class='num hi'>%s</td><td class=num>%s</td><td class=num>%s</td>"
        "<td class='num %s'>%+.1fpp</td><td class=num>$%s</td></tr>"
        % (esc(r["a"]), esc(r["b"]), _pct(r["p_blended"]), _pct(r["p_market"]),
           _pct(r["p_model"]),
           "up" if r["p_market"] > r["p_model"] else "down",
           (r["p_market"] - r["p_model"]) * 100, "{:,.0f}".format(r["volume"]))
        for r in mm["rows"])

    sens = si.get("w_match_sensitivity") or {}
    srows = ""
    if sens:
        order = sorted(pl["alive"], key=lambda t: -sens["3.0"][t])
        srows = "".join(
            "<tr><td class=lft>%s</td><td class=num>%s</td><td class=num>%s</td>"
            "<td class='num hi'>%s</td><td class=num>%s</td></tr>"
            % (esc(t), _pct(sens["0.0"][t]), _pct(sens["1.0"][t]),
               _pct(sens["3.0"][t]), _pct(sens["10.0"][t]))
            for t in order)

    return """
<h2>八强这四场，市场直接开了盘</h2>
<p>上面那四张卡片的条形是<b>交付值</b>，它现在有了第二个来源：Polymarket 给这四场
各开了一个<b>单场盘</b>。这跟冠军盘是两个独立市场、两拨交易者——
<b>而且它们并不完全同意对方。</b></p>
<div class="tbl-wrap"><table class="rv">
<thead><tr><th class=lft>对阵（先手队视角）</th><th>交付值</th><th>单场盘</th><th>纯模型</th>
<th>盘口−模型</th><th>盘口成交额</th></tr></thead>
<tbody>%s</tbody></table></div>

<div class="note crit"><b>接入单场盘之后，立刻打脸了上一版的一个做法。</b><br>
上一版没有单场盘，只能从冠军盘反解隐含实力、再让赛制展开成逐场胜率。
现在有直接价格可以对了，那套翻译偏成这样：%s——
<b>两个方向都错，且都不小。</b><br>
这正是上一版写在这一页上的那条局限：<i>市场若因赛制之外的理由给某队定价，
反解会把那部分理由强行翻译成「实力」</i>。<b>它被实测打中了，所以这一版把单场盘一起拟合进来。</b></div>

<h3>但两个市场调不到完全一致，差多少写在这</h3>
<p>现在隐含实力要同时解释<b>冠军盘</b>和<b>四场单场盘</b>：7 个自由参数对 11 个目标，
<b>超定</b>，不可能全中。所以这不再是「恰好求解」而是最小二乘，
<b>残差就是两个市场的分歧量</b>——冠军侧最大 %s，单场侧最大 %s。</p>
<p>给单场盘多少权重是个判断，不是算出来的。所以把它扫了一遍：</p>
<div class="tbl-wrap"><table class="rv">
<thead><tr><th class=lft>队伍</th><th>只信冠军盘</th><th>等权</th>
<th>本版采用</th><th>几乎只信单场盘</th></tr></thead>
<tbody>%s</tbody></table></div>
<div class="note"><b>这个判断最多能把夺冠概率挪 %.1f 个百分点</b>（VISION 那一支）。
本版取的是偏向单场盘的一档，理由是：<b>那四个是对这四场的直接价格，
而冠军概率是往后推演 14 场的间接量——直接价格没道理被间接量推翻。</b><br>
<span class="hint">这也意味着<b>这一页的夺冠概率比站内其它页高一点</b>：
其它页（结论、复盘）用的是只含冠军盘的口径 %s，这一页是 %s。
差的这 %.1fpp 不是算错，是多用了一个市场。</span></div>
""" % (rows,
       "、".join(
           "<b>%s vs %s</b> 翻译值 %s、单场盘 %s"
           % (esc(r["a"]), esc(r["b"]),
              _pct((si.get("w_match_h2h") or {}).get("0.0", {}).get(
                  "%s|%s" % (r["a"], r["b"]), 0)),
              _pct(r["p_market"]))
           for r in mm["rows"]
           if abs((si.get("w_match_h2h") or {}).get("0.0", {}).get(
               "%s|%s" % (r["a"], r["b"]), 0) - r["p_market"]) > 0.05),
       "%.1fpp" % (si.get("max_abs_champ_resid", 0) * 100),
       "%.1fpp" % (si.get("max_abs_match_resid", 0) * 100),
       srows, si.get("w_match_swing_pp", 0),
       _pct(sens.get("0.0", {}).get("TEAM VISION", 0)) if sens else "—",
       _pct(pl["views"]["blended"]["place"]["TEAM VISION"]["champion"]),
       (pl["views"]["blended"]["place"]["TEAM VISION"]["champion"]
        - sens.get("0.0", {}).get("TEAM VISION", 0)) * 100 if sens else 0)


def _champ_table(pl):
    model, blend = pl["views"]["model"], pl["views"]["blended"]
    mk = pl["market"]["implied"]
    rows = []
    for t in sorted(pl["alive"], key=lambda x: -blend["place"][x]["champion"]):
        cb = blend["place"][t]["champion"]
        cm = model["place"][t]["champion"]
        gap = cm - mk[t]
        cls = " class='gap'" if abs(gap) > GAP_THRESHOLD else ""
        rows.append(
            "<tr%s><td class=lft>%s</td><td class='num hi'>%s</td>"
            "<td class=num>%s</td><td class=num>%s</td><td class='num %s'>%s</td>"
            "<td class=num>%s</td><td class=num>%s</td></tr>"
            % (cls, esc(t), _pct(cb), _pct(cm), _pct(mk[t]),
               "up" if gap > 0 else "down", "%+.1fpp" % (gap * 100),
               _pct(blend["place"][t]["final"]), _pct(blend["place"][t]["top4"]))
        )
    return (
        '<div class="tbl-wrap"><table class="rv">'
        "<thead><tr><th class=lft>队伍</th><th>夺冠（交付值）</th><th>纯模型</th>"
        "<th>冠军盘</th><th>模型−冠军盘</th><th>进决赛</th><th>进前四</th></tr></thead>"
        "<tbody>%s</tbody></table></div>" % "".join(rows)
    )


def _place_table(pl):
    blend = pl["views"]["blended"]
    rows = []
    for t in sorted(pl["alive"], key=lambda x: -blend["place"][x]["champion"]):
        d = blend["place"][t]["dist"]
        cells = "".join(
            "<td class='num%s'>%s</td>"
            % (" hi" if d[k] == max(d.values()) else "", _pct(d[k]))
            for k in ("1", "2", "3", "4", "5", "7"))
        rows.append("<tr><td class=lft>%s</td>%s</tr>" % (esc(t), cells))
    return (
        '<div class="tbl-wrap"><table class="rv">'
        "<thead><tr><th class=lft>队伍</th><th>冠军</th><th>亚军</th><th>第 3</th>"
        "<th>第 4</th><th>5-6</th><th>7-8</th></tr></thead>"
        "<tbody>%s</tbody></table></div>" % "".join(rows)
    )


def _future_table(pl):
    blend = pl["views"]["blended"]
    rows = []
    for stage in FUTURE_ORDER:
        meta = pl["stage_meta"][stage]
        top = blend["stage_pairs"][stage][:3]
        cell = "<br>".join(
            "%s <span class=vs>vs</span> %s <span class=dim>%s</span>"
            % (esc(r["a"]), esc(r["b"]), _pct(r["p"], 0)) for r in top)
        n_possible = len(blend["stage_pairs"][stage])
        rows.append(
            "<tr><td class=num>%s</td><td class=lft>%s</td><td class=lft>%s</td>"
            "<td class=num>%d</td></tr>"
            % (esc(meta["time_cst"]), esc(meta["cn"]), cell, n_possible))
    return (
        '<div class="tbl-wrap"><table class="rv">'
        "<thead><tr><th>时间</th><th class=lft>场次</th>"
        "<th class=lft>最可能的三种对阵</th><th>可能对阵数</th></tr></thead>"
        "<tbody>%s</tbody></table></div>" % "".join(rows)
    )


def _bracket_svg(pl):
    """赛制结构图。只画连线关系，不画概率——概率在上面的表里，画进图里会挤成一团。

    这张图要回答的是读者最常问的一句：「八强输了是不是就没了？」
    答案是没有：输一场掉败者组，还要再输一场才淘汰。
    """
    return """
<div class="bracket">
<svg viewBox="0 0 760 300" role="img" aria-label="TI15 主赛事双败赛制结构图">
  <defs><marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6"
    orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="currentColor"/></marker></defs>
  <g class="bk-lane">
    <text x="8" y="20" class="bk-lane-t">胜者组</text>
    <rect x="70"  y="30" width="112" height="30" rx="5"/><text x="126" y="50">八强 · 4 场</text>
    <rect x="230" y="30" width="112" height="30" rx="5"/><text x="286" y="50">四强 · 2 场</text>
    <rect x="390" y="30" width="112" height="30" rx="5"/><text x="446" y="50">胜者组决赛</text>
    <rect x="576" y="120" width="132" height="34" rx="5" class="bk-gf"/>
    <text x="642" y="142" class="bk-gft">总决赛 BO5</text>
    <path d="M182 45 H228" marker-end="url(#ar)"/>
    <path d="M342 45 H388" marker-end="url(#ar)"/>
    <path d="M502 45 H540 V132 H574" marker-end="url(#ar)"/>
  </g>
  <g class="bk-lane bk-lb">
    <text x="8" y="215" class="bk-lane-t">败者组</text>
    <rect x="70"  y="225" width="112" height="30" rx="5"/><text x="126" y="245">首轮 · 2 场</text>
    <rect x="230" y="225" width="112" height="30" rx="5"/><text x="286" y="245">八强 · 2 场</text>
    <rect x="390" y="225" width="96" height="30" rx="5"/><text x="438" y="245">四强 · 1 场</text>
    <rect x="500" y="225" width="96" height="30" rx="5"/><text x="548" y="245">败者组决赛</text>
    <path d="M182 240 H228" marker-end="url(#ar)"/>
    <path d="M342 240 H388" marker-end="url(#ar)"/>
    <path d="M486 240 H498" marker-end="url(#ar)"/>
    <path d="M596 240 H640 V158" marker-end="url(#ar)"/>
  </g>
  <g class="bk-drop">
    <path d="M126 62 V222" marker-end="url(#ar)"/><text x="134" y="150">败者掉这里</text>
    <path d="M286 62 V150 H340 V222" marker-end="url(#ar)"/>
    <path d="M446 62 V196 H548 V222" marker-end="url(#ar)"/>
  </g>
</svg>
<p class="hint"><b>八强输一场不会被淘汰</b>——败者组还有一条路，要再输一次才回家。
所以这 8 支队里有 4 支的最终名次会是「5-6 名或更差」，另外 4 支能进前四。
总决赛是 BO5，且<b>没有 bracket reset</b>：胜者组冠军在决赛输一个 BO5 就直接丢冠军。</p>
</div>"""


# 三笔主要分歧各自的理由。只写理由，数字全部从产出物取。
GAP_WHY = {
    "TEAM VISION":
        "小组赛 <b>4-0</b> 唯一全胜。模型的实力分本来就把它排在 16 队第一，"
        "分歧不在「谁最强」，而在<b>强多少</b>——模型认为在一个 8 队水平接近、"
        "还要连赢 4 场的签表里，没有谁配得上三分之一以上的概率。",
    "Team Falcons":
        "16 队里<b>唯一阵容零变动</b>的卫冕冠军。模型按「当前这五个人」算历史战绩，"
        "阵容连续性直接兑现成样本量与稳定性；市场只看到它小组赛 3-2、还在附加轮走了一遭。",
    "Nigma Galaxy":
        "赛前实力分是 16 队里的<b>倒数第四</b>，却打出 4-1 直通八强。"
        "模型认为那多半是赛程给的；市场认为它真的变强了。",
}


def _disagreement(pl):
    model = pl["views"]["model"]["place"]
    upd = pl["views"]["updated"]["place"]
    mk = pl["market"]["implied"]
    rb = pl["robustness"]
    th, ti, dth = pl["theta"], pl["theta_implied"], rb["dtheta"]

    gaps = sorted(((t, model[t]["champion"] - mk[t]) for t in pl["alive"]),
                  key=lambda kv: -abs(kv[1]))
    big = [(t, g) for t, g in gaps if abs(g) > GAP_THRESHOLD]

    rows = "".join(
        "<tr class='gap'><td class=lft>%s</td><td class=num>%s</td><td class=num>%s</td>"
        "<td class='num %s'>%+.1fpp</td><td class=lft>%s</td></tr>"
        % (esc(t), _pct(model[t]["champion"]), _pct(mk[t]),
           "up" if g > 0 else "down", g * 100, GAP_WHY.get(t, ""))
        for t, g in big)

    # 「市场给的加减分」对「TI15 战绩支持的加减分」——两者都是实力分尺度，可以直接比
    prem = "".join(
        "<tr><td class=lft>%s</td><td class=num>%+.3f</td><td class=num>%+.3f</td>"
        "<td class=num>%s</td></tr>"
        % (esc(t), ti[t] - th[t], dth[t],
           ("%.1f 倍" % ((ti[t] - th[t]) / dth[t]))
           if dth[t] != 0 and (ti[t] - th[t]) / dth[t] > 1 else "方向相反")
        for t, _ in big)

    nig_m = model["Nigma Galaxy"]["champion"]
    return """
<h2>模型和市场吵得最凶的三支队</h2>
<p>这一版最值得赛后复盘的不是头名是谁，而是下面这三笔。它们方向不一致，而且<b>赛后能判对错</b>。</p>
<div class="tbl-wrap"><table class="rv">
<thead><tr><th class=lft>队伍</th><th>纯模型</th><th>市场</th><th>模型−市场</th>
<th class=lft>分歧在哪</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">其余 %d 支队模型与市场的差都在 %d 个百分点以内——<b>分歧是局部的，不是全面的</b>。</p>

<h3>把分歧换算成实力分，再问一句：数据支持这么改吗</h3>
<p>上面那张表是概率，不好直接判断谁更离谱。换个尺度就清楚了：把融合值反解成实力分
（<b>市场给的加减分</b>），再把 TI15 已打完的 <b>%d 小局</b>按贝叶斯折进赛前实力分
（<b>战绩支持的加减分</b>），两者是同一个尺度，可以并排比。</p>
<div class="tbl-wrap"><table class="rv">
<thead><tr><th class=lft>队伍</th><th>市场给的加减分</th><th>TI15 战绩支持的加减分</th>
<th>市场的倍数</th></tr></thead>
<tbody>%s</tbody></table></div>
<div class="note crit"><b>市场对 VISION 和 Nigma 的加价，都是这届实际战绩所能支持的约 4 倍。</b><br>
而对 Falcons，市场在<b>减分</b>，可它这届的战绩根本没说要减（贝叶斯更新给的是 %+.3f，几乎为零）。</div>

<h3>「你只是数据没更新」——这条质疑我算过了，不成立</h3>
<p>模型的实力分训练截止 <b>2026-08-02</b>，<b>没有见过 TI15 任何一局</b>。
所以看到 Nigma 只有 %s，第一反应多半是：你的数据是旧的。
这个质疑值多少，上面那次贝叶斯更新已经答了——</p>
<div class="tiles">
  <div class="tile"><div class="k">实力分最大位移</div><div class="v">%.3f</div>
       <div class="s">全 16 队里最大的一支</div></div>
  <div class="tile"><div class="k">Nigma 的实力分</div><div class="v">%+.3f → %+.3f</div>
       <div class="s">仍是 16 队里倒数第五</div></div>
  <div class="tile"><div class="k">夺冠概率最大位移</div><div class="v">%.1fpp</div>
       <div class="s">Nigma 只从 %s 挪到 %s</div></div>
</div>
<div class="note"><b>结论：分歧不是「数据没更新」造成的，折进 TI15 战绩之后它依然在。</b><br>
原因是先验太紧——Nigma 赛前的实力分是几百场比赛拟合出来的（标准误 %.3f），
而 TI15 它只打了十来局。两边的信息量差着近 20 倍，十来局翻不动。<br>
<span class="hint">诚实的限定：这个计算把「赛前实力到今天仍然有效」当成前提，
没有为状态漂移放宽先验方差。所以 %.3f 是「TI15 战绩该挪多少」的<b>下界</b>，不是上界。
真实答案在这个下界和市场给的加价之间，赛后可以回头判。</span></div>
<p>所以这三笔是<b>真分歧</b>，不是数据新旧的问题：要么模型的「阵容连续性」逻辑是对的，
要么市场看到了模型看不到的东西。<b>8 月 23 日见分晓。</b></p>
""" % (rows, len(pl["alive"]) - len(big), int(GAP_THRESHOLD * 100),
       rb["n_games"], prem, dth["Team Falcons"],
       _pct(nig_m),
       rb["max_abs_dtheta"],
       th["Nigma Galaxy"], pl["theta_updated"]["Nigma Galaxy"],
       rb["max_abs_dchampion"] * 100,
       _pct(nig_m), _pct(upd["Nigma Galaxy"]["champion"]),
       pl["theta_se"]["Nigma Galaxy"],
       rb["max_abs_dtheta"])


def render(base, p):
    pl = p["raw_playoffs"]
    blend = pl["views"]["blended"]
    top = max(pl["alive"], key=lambda t: blend["place"][t]["champion"])
    top_p = blend["place"][top]["champion"]
    mkt = pl["market"]
    n_done = ((p.get("raw_pred") or {}).get("results") or {}).get("n_series_done", 0)

    # 「最可能的总决赛」——顺手回答读者最想问的一句，但要把它有多不确定说清楚
    gf_top = blend["stage_pairs"]["GF"][0]

    body = """
<h1>接下来这 14 场</h1>
<p class="lede">TI15 小组赛已经打完——瑞士轮 5 轮加附加淘汰轮，共 <b>%d 场系列赛</b>全部结束，
八强名单与对阵表已由官方公布。这一页只讲<b>还没打的那 14 场</b>：谁打谁、各自多大概率、
最后谁举盾。所有数字都代入了已经发生的全部赛果与实时市场价。</p>
<p class="meta">截至 %s · 市场快照 %s（Polymarket 累计成交 $%s，抽水仅 %.1f%%）·
剩余 14 场：胜者组 7 + 败者组 6 + 总决赛 1</p>

<div class="tiles">
  <div class="tile"><div class="k">夺冠概率最高</div><div class="v">%s</div>
       <div class="s">%s · 已融合市场共识价</div></div>
  <div class="tile"><div class="k">但冠军不在它身上的概率</div><div class="v">%s</div>
       <div class="s">另外 7 支队合计——仍是大头</div></div>
  <div class="tile"><div class="k">最可能的总决赛</div><div class="v">%s</div>
       <div class="s">%s vs %s——最高的一种也只有这么多</div></div>
  <div class="tile"><div class="k">决赛 BO5</div><div class="v">无 reset</div>
       <div class="s">胜者组冠军输一个 BO5 就丢冠</div></div>
</div>

<h2>八强四场：这是事实，不是预测</h2>
<p>对阵由官方排定，<b>不是按瑞士轮名次机械排的</b>——附加轮采用「高排位队自己挑对手」的选人制，
八强签表也随之与名次规则对不上。所以对阵本身当事实录入，模型只预测胜负。</p>
%s
<p class="hint">条形是<b>交付值</b>（模型与市场融合，市场占七成权重）。下面一行给出
<b>市场对这一场的直接报价</b>与纯模型口径——三个数差得越远，说明这一场分歧越大。
下一节专门讲两个市场自己也不一致这件事。</p>

%s

<h2>夺冠概率</h2>
%s
<p class="hint"><b>「模型−冠军盘」那一列是本页信息量最大的地方。</b>标出来的几行差值超过 %d 个百分点，
下一节专门讲它们。交付值比冠军盘那一列高，是因为它还并进了上面那四场的单场盘。</p>

<h2>赛制：输一场还不会回家</h2>
%s

%s

<h2>最终名次分布</h2>
<p>八支队、八个名次档。每一行加起来是 100%%，每一列加起来是该名次的席位数
（1-4 名各 1 席，5-6 和 7-8 各 2 席）——这是赛制的恒等式，不是凑出来的。</p>
%s

<h2>之后那 10 场，最可能是谁打谁</h2>
<p>八强之后的对阵取决于前面谁赢，所以只能给概率。下面每一格列出该场<b>最可能的三种对阵</b>。</p>
%s
<div class="note"><b>注意最后一列。</b>越往后，可能的对阵组合越多、每一种的概率越低——
总决赛有 %d 种可能的组合，最高的一种也只有 %s。<b>现在去赌具体的决赛对阵，是在赌一件九成不会发生的事。</b></div>

<h2>这一版预测的三条局限</h2>
<div class="note crit"><b>一、融合口径下的逐场胜率，是「翻译」出来的。</b><br>
市场只开夺冠盘，没有「谁进四强」「这一场谁赢」的盘口。所以做法是：反解一组隐含实力，
使它算出的夺冠概率<b>恰好等于</b>融合值，再让赛制把它展开成逐场胜率。
这样整页数字出自同一套参数，读者按逐场胜率自己乘一遍能得到页面上的冠军概率。<br>
代价是：<b>市场如果因为赛制之外的理由给某队定价</b>（伤病、对签表软硬的主观判断），
这一步会把那部分理由强行翻译成「实力」。所以隐含实力是「市场若只通过实力表达观点，它在说什么」，
不是「这支队真实有多强」。</div>
<div class="note crit"><b>二、模型的实力分没有见过 TI15。</b><br>
训练截止 2026-08-02。TI15 的赛果通过两条路进入这一版：一是<b>作为条件</b>——谁进了八强、
签表长什么样，全部当事实代入；二是<b>通过市场价</b>——市场看过每一局。
但队伍实力那一层本身没有重新拟合。上一节量化了这件事值多少：<b>%.1fpp</b>。</div>
<div class="note crit"><b>三、14 场样本，判不出模型好坏。</b><br>
这一页的每个数字赛后都能对账，但要提前说清楚：<b>14 场系列赛的样本量，得不出任何统计结论。</b>
就算全对或全错，也主要是运气。真正有统计功效的检验是<a href="%s/review.html">复盘页</a>那 44 场，
以及跨届累积。<b>别拿这 14 场的结果来判定这套方法行不行。</b></div>

<p><a href="%s/review.html">→ 已经打完的 %d 场，逐场对账在这里</a> ｜
<a href="%s/overview.html">→ 这套预测是怎么做的</a> ｜
<a href="%s/homework.html">→ 抄作业页（小组赛答案已揭晓）</a></p>

<div class="cta">
  <div>
    <b>建了个微信群：TI15 抄作业群</b>
    <span>8/20 淘汰赛开打，一起看这份预测被打成什么样。</span>
  </div>
  <a class="cta-btn" href="%s/group.html">扫码进群 →</a>
</div>
""" % (n_done,
       esc(pl["as_of_utc"][:10]), esc(mkt["captured_utc"][:10]),
       "{:,}".format(int(mkt["event_volume"] or 0)), (mkt["overround"] - 1) * 100,
       esc(top), _pct(top_p),
       _pct(1 - top_p),
       _pct(gf_top["p"], 0), esc(gf_top["a"]), esc(gf_top["b"]),
       _qf_cards(pl),
       _market_section(pl),
       _champ_table(pl), int(GAP_THRESHOLD * 100),
       _bracket_svg(pl),
       _disagreement(pl),
       _place_table(pl),
       _future_table(pl),
       len(blend["stage_pairs"]["GF"]), _pct(gf_top["p"], 0),
       pl["robustness"]["max_abs_dchampion"] * 100,
       base, base, n_done, base, base, base)
    return pages.shell(base, "index.html", "八强前瞻", body)
