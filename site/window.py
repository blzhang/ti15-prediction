"""生成「版本窗口」页：回答读者提的「只用 7.41 之后的数据是不是更靠谱」。

全部数字来自 reports/p5_window_backtest.json，一个都不手抄——这一页讲的就是
「先写死判据再跑数据」，要是页面上的数字能手改，那它自己就先破功了。

页面结构与 odds.py / changelog.py 同构：只返回 body，外壳由 pages.shell 套。
"""
import html as _h

# 臂名 -> 人话。键必须与 model/l5_window.py 的 ARM_LOOKBACK_DAYS 及
# window_arms() 产出的臂名一致；查不到的臂原样显示，不编。
ARM_LABEL = {
    "all": "全部历史",
    "L955d": "开赛前 955 天",
    "L365d": "开赛前 365 天",
    "L180d": "开赛前 180 天",
    "L105d": "开赛前 105 天",
    "patch": "当届版本发布日起",
    "prev_patch": "上一个版本发布日起",
}

VARIANT_LABEL = {
    "coarse_position": "只分「核心 / 辅助」两组",
    "min_games=3": "出场门槛放宽到 3 局",
    "min_games=8": "出场门槛收紧到 8 局",
}


def esc(s):
    return _h.escape(str(s), quote=True)


def _arm(name):
    return "%s（<code>%s</code>）" % (esc(ARM_LABEL.get(name, name)), esc(name))


def _pct(x):
    return "%.1f%%" % x


def _sec_conclusion(r):
    d = r["decision"]
    t = d["sign_test"]
    return """
<h1>一个读者的问题：只用 7.41 之后的数据，是不是更靠谱？</h1>
<p class="lede">有人在评论区问：梦幻挑战的选手数据，是不是只考虑 7.41 版本之后的比较靠谱。
这是个好问题，而且能验——所以我们拿过去四届 TI 当考卷，把「从哪天开始取数据」这件事
真跑了一遍。结论写在下面，好看不好看都照登。</p>
<p class="meta">判据在跑数据之前就写死了 · 产出物 <code>reports/p5_window_backtest.json</code> 可在「数据与检索」页下载</p>

<div class="note"><b>先给结论。</b>
<b>没有证据支持把取数起点改成「当届版本发布日」。</b>
配对符号检验 p=%.4f（判据要求 &lt;%.2f），中位差 %+.4f，
四届里只有 <b>%d</b> 届方向为正（判据要求至少 %d 届）。两条都没满足。<br>
但这句话不等于「版本不重要」，也不等于「两种取法一样好」——
下面那几节才是这次真正有意思的部分。</div>
""" % (t["p"], r["alpha"], t["median"], d["n_holdouts_positive"], r["min_holdouts_positive"])


def _baseline_days(r):
    """从 baseline 臂名里取回看天数，例如 "L955d" -> 955。取不到就返回 None。"""
    m = r["baseline_arm"]
    if m.startswith("L") and m.endswith("d") and m[1:-1].isdigit():
        return int(m[1:-1])
    return None


def _sec_method(r):
    d = r["decision"]
    t = d["sign_test"]
    holds = "、".join("TI%s（%s）" % (esc(m["holdout"]), esc(m["patch"]))
                      for m in r["holdout_meta"])
    # 「几届 × 几项 × 几个号位」全部反推自数据，不写死——换一份产出物页面也要自洽
    n_hold = len(r["holdout_meta"])
    n_item = int(str(r["items_covered"]).split("/")[0])
    n_pos = d["n_units_compared"] // max(n_hold * n_item, 1)
    parts = [m["n_participants"] for m in r["holdout_meta"]]
    who = ("%d" % parts[0]) if min(parts) == max(parts) else ("%d~%d" % (min(parts), max(parts)))
    days = _baseline_days(r)
    days_txt = ("正好是 <b>%d 天</b>，所以现行策略就是「开赛前 %d 天」" % (days, days)
                if days else "对应本次的 baseline 臂 <code>%s</code>" % esc(r["baseline_arm"]))
    # 只靠「届内一致性」这一条能达到的最好 p 值：n 届全部同向的双侧精确二项。
    # 写死成某个数会随届数漂掉，而且单侧/双侧差一倍——这里按实际用的双侧算。
    best_p = 2.0 * 0.5 ** n_hold
    return """
<h2>怎么验的</h2>
<p>选手数据模型现在的取数起点是 <b>2024-01-01</b>，这个日期当初是拍出来的经验值，
从来没人验过。要验它，得先把「取数起点」翻译成一个跟具体日期无关的<b>策略</b>：
2024-01-01 到 TI15 开赛%s。这样才能拿去年、前年的 TI 一起考。</p>
<p>%d 届考卷：%s。每一届都假装自己站在那届开赛前一天，用<b>%d 种不同的取数起点</b>
各算一遍 %s 名参赛选手的场均数据，再跟他们在那届 TI <b>实际</b>打出来的场均数据比。</p>
<div class="note"><b>比什么？比同号位内的排序。</b>
梦幻挑战是在同一个槽位里挑人，所以「1 号位里谁补刀最多」排对了才有用，
绝对值差一点不影响选人。跨号位混着比是没有意义的——那只会说明「核心补刀比辅助多」。<br>
一共 %d 届 × %d 个计分项 × %d 个号位 = <b>%d</b> 个比较单元，
本次全部算出，没有一个因样本不足被跳过。</div>
<div class="note"><b>判据在跑之前就写死并提交了。</b>
%s要赢过%s，必须同时满足两条：
配对符号检验 p&lt;%.2f 且中位差为正；%d 届里至少 %d 届方向为正。<br>
为什么要两条：同一届的 %d 个计分项用的是同一批选手，单元之间并不独立，
只看符号检验会高估显著性；而只看届间一致性的话，%d 届全部同向也只能给到
p=%.3f，永远够不到 %.2f。两条合起来才是这个样本量下能给出的最诚实的判据。<br>
跑完再挑对自己有利的指标看，是这个项目最反对的事——所以规则先写、再跑。</div>
<h2>主结果</h2>
<p>%s对%s，%d 届各自的中位差（正数=版本窗口更好）：</p>
<div class="tbl-wrap"><table>
<thead><tr><th>届</th><th>当届版本</th><th>中位差</th><th>方向</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">合计 %d 个单元里，版本窗口赢 %d 个、输 %d 个、平 %d 个。
%d 届里有 %d 届方向为正，判据要求至少 %d 届。</p>
""" % (days_txt, n_hold, holds, len(r["exploratory"]["arm_vs_baseline"]) + 1, who,
       n_hold, n_item, n_pos, d["n_units_compared"],
       _arm(r["treatment_arm"]), _arm(r["baseline_arm"]),
       r["alpha"], n_hold, r["min_holdouts_positive"],
       n_item, n_hold, best_p, r["alpha"],
       _arm(r["treatment_arm"]), _arm(r["baseline_arm"]), n_hold,
       "".join(
           "<tr><td>TI%s</td><td>%s</td><td class=num>%+.4f</td><td>%s</td></tr>"
           % (esc(m["holdout"]), esc(m["patch"]),
              d["median_diff_by_holdout"][m["holdout"]],
              "更好" if d["median_diff_by_holdout"][m["holdout"]] > 0 else "更差")
           for m in r["holdout_meta"]),
       d["n_units_compared"], t["n_pos"], t["n_neg"], t["n_zero"],
       n_hold, d["n_holdouts_positive"], r["min_holdouts_positive"])


def _sec_why(r):
    """版本臂到底亏在「版本边界」还是「窗口太短」。"""
    e = r["exploratory"]
    ctrl = e["control_arm"]
    rows = "".join(
        "<tr><td>TI%s</td><td>%s</td><td class=num>%d 天</td>"
        "<td class=num>%d/%d</td><td class=num>%.0f</td><td class=num>%s</td>"
        "<td class='num hi'>%+.4f</td></tr>"
        % (esc(m["holdout"]), esc(m["patch"]), m["patch_window"]["window_days"],
           m["patch_window"]["n_players_in_window"], m["patch_window"]["n_players_total"],
           m["patch_window"]["median_games_in_window"],
           _pct(m["patch_window"]["pct_below_min_n"]),
           e["median_diff_vs_control_by_holdout"][m["holdout"]])
        for m in r["holdout_meta"])
    last = r["holdout_meta"][-1]
    thr = last["patch_window"]["min_n_for_own_game_var"]
    ident = e["treatment_vs_control_by_holdout"][last["holdout"]]
    return """
<h2>但它输在哪儿：是「版本」还是「窗口太短」？</h2>
<p>这是这次最值得看的一节。往年 TI 都是开赛前一两个月才换版本，
所以「只用当届版本」在历史上意味着一个<b>非常短</b>的窗口——短到样本量塌掉。
问题是：版本臂输，是输在「跨版本的数据没用」，还是单纯输在「数据太少」？</p>
<p>把它跟一个<b>等长的日历窗口</b>比就能分开。下表最后一列，比的是
「从版本发布日切」相对「%s」的届内中位差：</p>
<div class="tbl-wrap"><table>
<thead><tr><th>届</th><th>版本</th><th>版本窗口</th><th>窗内有数据的选手</th>
<th>每人局数中位</th><th>低于 %d 局门槛</th><th>中位差 vs 等长窗口</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">「%d 局门槛」是选手模型里的一个内部开关：一名选手在窗口内不足 %d 局时，
模型不敢信他自己的波动幅度，只能退回同号位的平均水平——个人特征就被抹掉了。</p>
<div class="note good"><b>答案很清楚：窗口长度一对齐，版本边界就不花钱了。</b><br>
TI%s 的版本窗口有 %d 天，跟等长日历窗口基本同长，这一届的中位差是 <b>%+.4f</b>——
%d 个比较单元里有 %d 个两种取法算出来<b>完全一样</b>。<br>
另外三届的版本窗口只有 %d~%d 天，同一个对照下中位差是 %s，全是负的。
差距出现在窗口短的那几届，不出现在长度对齐的那一届。<br>
换句话说：<b>版本边界只是通过「它圈进来多少数据」起作用，边界本身不额外携带信息。</b></div>
<p class="hint">一个必须说明的限制：这个等长对照窗口本来就是为了跟 TI%s 的版本窗口几乎重合
而设计的，所以那个「差不多为零」有一部分是构造出来的。它能证明的是
「边界本身不携带额外信息」，<b>不是</b>「版本边界在任何窗口长度下都无害」。</p>
""" % (_arm(ctrl), thr, rows, thr, thr,
       esc(last["holdout"]), last["patch_window"]["window_days"],
       e["median_diff_vs_control_by_holdout"][last["holdout"]],
       ident["n_units"], ident["n_identical"],
       e["historical_patch_window_days"]["min"],
       sorted(m["patch_window"]["window_days"] for m in r["holdout_meta"])[-2],
       "、".join("%+.4f" % e["median_diff_vs_control_by_holdout"][m["holdout"]]
                 for m in r["holdout_meta"][:-1]),
       esc(last["holdout"]))


def _sec_proposal(r):
    e = r["exploratory"]
    pr = e["proposal"]
    lo = e["historical_patch_window_days"]["min"]
    hi = e["historical_patch_window_days"]["max"]
    return """
<h2>那这对 7.41 到底意味着什么</h2>
<div class="note"><b>最关键的一点：读者提的那个窗口，这次其实没测到。</b><br>
%s 发布到 TI15 开赛有 <b>%d 天</b>，而四届考卷里的版本窗口只有 <b>%d~%d 天</b>。
今年这个窗口<b>比历史上任何一届都长</b>，落在日历窗口的量级里，
而不是落在被测的那些短版本窗口的量级里。<br>
所以对「只用 7.41 起的数据」这个提议，这次回测<b>既没有证伪，也没有证实</b>。</div>
<p>把上面几节连起来，给这位读者的回话大概是这样：</p>
<p><b>你对「越新越好」的直觉，数据是站在你这边的</b>——下一节会看到，
比现行窗口更短的几种取法确实更准。<b>但「按版本切」不是实现它的正确切法</b>：
版本边界本身没有信息，起作用的一直是「离开赛多近」。
而 7.41 这个 %d 天的窗口，恰好落在看起来比现行取法更好的那个长度区间里——
这一点值得单独再验一次。</p>
""" % (esc(pr["patch"]), pr["window_days"], lo, hi, pr["window_days"])


def _sec_exploratory(r):
    e = r["exploratory"]
    avb = e["arm_vs_baseline"]
    base = r["baseline_arm"]
    order = sorted(avb, key=lambda a: -avb[a]["sign_test"]["median"])
    rows = "".join(
        "<tr><td>%s%s</td><td class=num>%d/%d/%d</td><td class='num hi'>%+.4f</td>"
        "<td class=num>%.5f</td><td class=num>%d/4</td><td>%s</td></tr>"
        % (_arm(a), "（本次的 treatment）" if a == r["treatment_arm"] else "",
           avb[a]["sign_test"]["n_pos"], avb[a]["sign_test"]["n_neg"],
           avb[a]["sign_test"]["n_zero"], avb[a]["sign_test"]["median"],
           avb[a]["sign_test"]["p"], avb[a]["n_holdouts_positive"],
           "是" if avb[a]["supported"] else "否")
        for a in order)
    win = [a for a in order if avb[a]["supported"]]
    return """
<h2>探索性：其余几种取法各自什么成绩</h2>
<div class="note crit"><b>本节全部是探索性的，不属于预注册分析。</b>
上面那条结论只对应一组预注册的对照（当届版本起 vs 开赛前 955 天）。
本节把七种取法逐个摆开，是在<b>看过主结果之后</b>才做的：多重比较没有做任何校正，
分析单元之间也不独立。<br>
<b>本节任何一行都不构成现在就改模型取数起点的依据。</b>
真要动，必须另立一次预注册检验：先写死候选与判据、再跑数据。</div>
<p>下表对每一种取法套用与主判定<b>完全相同</b>的那把尺子，对照组都是
%s。「同一规则下成立？」那一列只是尺子的读数，不是推荐。</p>
<div class="tbl-wrap"><table>
<thead><tr><th>取数起点</th><th>赢/输/平</th><th>中位差</th><th>p</th>
<th>四届中为正</th><th>同一规则下成立？</th></tr></thead>
<tbody>%s</tbody></table></div>
<div class="note"><b>现行的「开赛前 955 天」可能开得太长了。</b>
同一把尺子下有 <b>%d</b> 种取法同时满足两条判定，全部是比现行更短的窗口。
这是本次最意外的产出——它说明「窗口长度」这个维度还没有被认真查过，
而不是说明现在就该改。</div>
""" % (_arm(base), rows, len(win))


def _sec_sliding(r):
    """滑动窗口。段标签与「是否单调」都从数据算，不写死——
    本次真实数据里就有一届不单调，写死成「四届都单调」会是假话。"""
    start = {m["holdout"]: m["event_start_ts"] for m in r["holdout_meta"]}
    by_hold = {}
    for s in r["sliding"]:
        by_hold.setdefault(s["holdout"], []).append(s)

    def span(s):
        e = start[s["holdout"]]
        return (round((e - s["until_ts"]) / 86400), round((e - s["since_ts"]) / 86400))

    length = span(r["sliding"][0])[1] - span(r["sliding"][0])[0]
    rows = "".join(
        "<tr><td>TI%s</td><td>开赛前 %d–%d 天</td><td class='num hi'>%.4f</td><td>%s</td></tr>"
        % (esc(s["holdout"]), span(s)[0], span(s)[1], s["mean_spearman"],
           "、".join(esc(b) for b in s["patch_boundaries"]) or "无")
        for s in r["sliding"])

    # 单调下降的届数：按离开赛由近到远排序后逐段比较
    mono, exceptions = [], []
    for h, segs in by_hold.items():
        segs = sorted(segs, key=lambda s: span(s)[0])
        vals = [s["mean_spearman"] for s in segs]
        if all(a > b for a, b in zip(vals, vals[1:])):
            mono.append(h)
        else:
            bad = next(i for i in range(len(vals) - 1) if vals[i] <= vals[i + 1])
            exceptions.append((h, segs[bad], segs[bad + 1], vals[bad], vals[bad + 1]))

    ex = ""
    for h, s_near, s_far, v_near, v_far in exceptions:
        ex += ("<br><b>例外要说清楚：</b>TI%s 的「开赛前 %d–%d 天」那段（%.4f）"
               "反而比更靠近开赛的「%d–%d 天」那段（%.4f）高。"
               "而它跨的恰恰是 %s 的版本边界——"
               "如果跨版本真的有害，这一段本该更低才对。"
               % (esc(h), span(s_far)[0], span(s_far)[1], v_far,
                  span(s_near)[0], span(s_near)[1], v_near,
                  "、".join(esc(b) for b in s_far["patch_boundaries"]) or "无"))

    # 「最能说明问题的一对」也从数据里挑：跨边界最多的那一段，
    # 与它相邻的、一个边界都没跨的那一段。不写死是哪一届。
    pair = ""
    cand = sorted(r["sliding"], key=lambda s: -len(s["patch_boundaries"]))
    for s in cand:
        if not s["patch_boundaries"]:
            break
        segs = sorted(by_hold[s["holdout"]], key=lambda x: span(x)[0])
        i = segs.index(s)
        for j in (i + 1, i - 1):
            if 0 <= j < len(segs) and not segs[j]["patch_boundaries"]:
                pair = ("最能说明问题的是 TI%s：「开赛前 %d–%d 天」那段"
                        "<b>跨了 %s %s个版本边界</b>，平均相关 %.4f；"
                        "相邻的「开赛前 %d–%d 天」<b>一个边界都没跨</b>，平均相关 %.4f"
                        "——跨版本的那段并不更差。"
                        % (esc(s["holdout"]), span(s)[0], span(s)[1],
                           "、".join(esc(b) for b in s["patch_boundaries"]),
                           "两" if len(s["patch_boundaries"]) > 1 else "",
                           s["mean_spearman"], span(segs[j])[0], span(segs[j])[1],
                           segs[j]["mean_spearman"]))
                break
        if pair:
            break
    return """
<h2>另一个角度：把窗口固定成等长，往前滑</h2>
<p>还有一个更直接的查法：<b>窗口长度固定 %d 天不变</b>，只把起点一段一段往前挪，
看预测力怎么变。如果是平滑下降，说明起作用的纯粹是「离开赛多近」；
如果在跨版本的那一段突然掉档，那才是版本效应。</p>
<div class="tbl-wrap"><table>
<thead><tr><th>届</th><th>窗口位置</th><th>平均排序相关</th><th>段内跨越的版本</th></tr></thead>
<tbody>%s</tbody></table></div>
<div class="note good"><b>%d 届里 %d 届是逐段下降的，而且没有一处台阶落在版本边界上。</b>
%s%s</div>
""" % (length, rows, len(by_hold), len(mono), pair, ex)


def _sec_robust(r):
    rb = r["robustness"]
    d = r["decision"]
    main_sign = d["sign_test"]["median"] > 0
    rows = "".join(
        "<tr><td>%s</td><td class=num>%d</td><td class=num>%d/%d</td>"
        "<td class='num hi'>%+.4f</td><td class=num>%.4f</td><td>%s</td></tr>"
        % (esc(VARIANT_LABEL.get(k, k)), rb[k]["n_units_compared"],
           rb[k]["sign_test"]["n_pos"], rb[k]["sign_test"]["n_neg"],
           rb[k]["sign_test"]["median"], rb[k]["sign_test"]["p"],
           "是" if (rb[k]["sign_test"]["median"] > 0) == main_sign else "否")
        for k in rb)
    co = rb.get("coarse_position")
    mins = "、".join(str(m["min_games_among_participants"]) for m in r["holdout_meta"])
    return """
<h2>换个口径还成立吗</h2>
<p>怕结论是靠某一个口径撑起来的，所以换三种口径各跑一遍。这三个都<b>不参与</b>主判定。</p>
<div class="tbl-wrap"><table>
<thead><tr><th>换的口径</th><th>比较单元</th><th>赢/输</th><th>中位差</th><th>p</th>
<th>方向与主结果一致？</th></tr></thead>
<tbody>%s</tbody></table></div>
<div class="note"><b>只分核心/辅助两组时，结论反而更强。</b>
这个口径下 p=%.4f，已经<b>显著</b>，而中位差是 %+.4f——
也就是说在这个分组下，「只用当届版本」不只是「没证据更好」，而是<b>显著更差</b>。
方向与主结果一致，它加强而不是削弱上面的结论。</div>
<div class="note"><b>出场门槛那两个变体是空检验，如实说明。</b>
把门槛从 4 局放宽到 3 局或收紧到 8 局，结果与主判定<b>逐位相同</b>。
原因是四届参赛者的最少出场局数分别是 %s 局——收紧到 8 局一个人也筛不掉；
而放宽到 3 局在程序结构上根本不可能再多收进选手。
所以三个变体里真正有信息量的只有第一个。</div>
""" % (rows, co["sign_test"]["p"], co["sign_test"]["median"], mins)


def _sec_check(r):
    return """
<h2>怎么自己核对</h2>
<p>这一页的每个数字都是从 <code>reports/p5_window_backtest.json</code> 现算的，
没有一个是手写在页面里的。那份文件在<b>「数据与检索」页可以直接下载</b>，
里面有全部 %d 个比较单元的逐条明细——包括每个单元在七种取法下各自的相关系数，
你可以拿它把上面任何一张表重算一遍。</p>
<div class="note"><b>顺带交代覆盖范围。</b>
计分项覆盖 <b>%s</b>，缺的三项是 %s——它们要另外解析 OpenDota 的 JSON 字段，
历史届取不到。<br>
七种取法下各自有数据的选手不完全相同（窗口越短，赛前歇过几个月的人越容易缺席），
所以比较前先取了<b>七种取法的选手交集</b>，共丢弃 <b>%d</b> 人次；
不取交集的话就不是同一批人在比，那样的对比没有意义。</div>
<p class="hint">这次没有改任何线上数字。模型的取数起点仍然是 2024-01-01，
预测结果、冻结存证都没有动——本页只是把「这个选择到底对不对」查了一遍并如实公布。</p>
""" % (r["decision"]["n_units_compared"], esc(r["items_covered"]),
       "、".join(esc(x) for x in r["excluded_items"]),
       sum(c["n_dropped_by_intersection"] for c in r["coverage"]))


def render(base, report):
    """report = reports/p5_window_backtest.json 解出来的 dict。"""
    return (_sec_conclusion(report) + _sec_method(report) + _sec_why(report)
            + _sec_proposal(report) + _sec_exploratory(report)
            + _sec_sliding(report) + _sec_robust(report) + _sec_check(report))
