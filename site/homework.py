"""生成「作业」页：官方游戏内预测面板的建议填法。

题型来自客户端本地化文件 DOTA_Predictions26_*（一手），并经用户客户端截图核对。
分档 1/2/5/5/2/1 是赛制的结构性恒等式，不是概率。
最优分配用匈牙利算法（题目是把 16 队分到 6 档，各档不能重复用队）。
"""
import json
import os

import numpy as np
from scipy.optimize import linear_sum_assignment

import bracket_svg
import pages
from pages import esc

BUCKETS = [
    ("4-0", 1, "一支全胜的队伍", "record_dist", "4-0"),
    ("4-1", 2, "两支四胜一负的队伍", "record_dist", "4-1"),
    ("淘汰赛胜者", 5, "五支在淘汰赛胜出的队伍", "elim_round_survive", None),
    ("淘汰赛败者", 5, "五支在淘汰赛失败的队伍", "elim_round_out", None),
    ("1-4", 2, "两支一胜四负的队伍", "record_dist", "1-4"),
    ("0-4", 1, "一支全败的队伍", "record_dist", "0-4"),
]


def _prob(pred, src, key, team):
    if src == "record_dist":
        return pred["record_dist"][team].get(key, 0.0)
    return pred[src][team]


def solve(pred, force=None):
    """返回 (期望答对数, {档位: [(队, 命中概率)]})。force 可钉死某队到某档。"""
    teams = list(pred["record_dist"])
    slots = [(nm, src, key) for nm, cap, _, src, key in BUCKETS for _ in range(cap)]
    W = np.array([[_prob(pred, src, key, t) for _, src, key in slots] for t in teams])
    M = W.copy()
    for team, bucket in (force or {}).items():
        i = teams.index(team)
        for j, (nm, _, _) in enumerate(slots):
            if nm != bucket:
                M[i, j] = -9.0
    r, c = linear_sum_assignment(-M)
    out = {}
    for i, j in zip(r, c):
        out.setdefault(slots[j][0], []).append((teams[i], float(W[i, j])))
    for k in out:
        out[k].sort(key=lambda x: -x[1])
    return float(W[r, c].sum()), out


SLOT_CN = [("core", "核心", "这支队的两个核心一起计分"),
           ("mid", "中单", "只算这支队的中单"),
           ("support", "辅助", "这支队的两个辅助一起计分")]


def fantasy(fan, pred):
    """梦幻挑战三个槽位的推荐。

    一名选手的总产出 ≈ 每局表现 × 打了多少局，而后者由队伍走多深决定。
    所以这里把「每局分」乘上「期望系列赛数」排序。
    """
    sd = pred["series_dist"]
    out = {}
    for key, cn, desc in SLOT_CN:
        by = fan["proxy_score_by_slot"][key]
        rows = [(t, by[t], sd[t]["group"] + sd[t]["playoff"]) for t in by]
        rows.sort(key=lambda r: -(r[1] * r[2]))
        top = rows[0][1] * rows[0][2]
        out[key] = {
            "cn": cn, "desc": desc,
            "rows": [{"team": t, "per_game": v, "series": g, "total": v * g,
                      "gap": (v * g) / top - 1.0} for t, v, g in rows],
        }
    return out


def picker_data(pred, hw, fan_rec):
    """喂给前端选择器的数据：每格每队的命中概率 + 模型推荐的预设。"""
    teams = list(pred["record_dist"])
    buckets = {}
    for nm, cap, desc, src, key in BUCKETS:
        buckets[nm] = {
            "cap": cap, "desc": desc,
            "p": {t: round(_prob(pred, src, key, t), 4) for t in teams},
            "preset": [t for t, _ in hw["answer"].get(nm, [])],
        }
    return {
        "teams": teams,
        "order": [nm for nm, _, _, _, _ in BUCKETS],
        "buckets": buckets,
        "random": sum(cap * cap / 16.0 for _, cap, _, _, _ in BUCKETS),
        "fantasy": {k: {"cn": v["cn"], "desc": v["desc"],
                        "rows": [{"team": r["team"], "total": round(r["total"], 2),
                                  "gap": round(r["gap"], 4)} for r in v["rows"]]}
                    for k, v in fan_rec.items()},
    }


def elim_pitfalls(pred, strength):
    """「淘汰赛胜者 / 败者」两格的真实落差。

    两格的概率都 = P(打得上附加轮) × P(打上了赢 / 输)。前一项随实力先升后降
    （太强直接晋级、太弱直接出局，两头都碰不到这一轮），后一项随实力单调。
    乘出来是两个形状不同的曲线：胜者格在实力前八几乎持平，败者格被最强的压到最低。

    早先的文案两格都挑了落差小的那一头讲。所以这里把形状钉成断言——
    重算后若形状变了，构建直接失败，而不是继续印一句错话。

    ⚠️ 这条断言只在**赛前**成立，2026-08-15 被真实赛况打掉过一次：瑞士轮打到
    4 胜或 4 负即停，一旦有队伍锁定 4-0（直通淘汰赛）或 0-4（出局），它们
    **根本碰不到附加轮**，两格概率同时归零，「胜者格最低的是垫底队」就不再成立了。
    那不是 bug，是赛况本身变了。所以开赛后不再断言，改为把形状是否还成立
    （shape_holds）交出去，由页面自己选措辞——断言的职责是「别印错话」，
    而不是「不许赛况变化」。
    """
    # 必须按实力参数排序。用模拟出来的夺冠概率当代理会在末尾翻转——
    # 垫底两队的夺冠概率都是 0.1%~0.2% 量级，差异纯粹是蒙特卡洛噪声。
    order = sorted(strength, key=lambda t: -strength[t])
    sv = [pred["elim_round_survive"][t] for t in order]
    ou = [pred["elim_round_out"][t] for t in order]
    shape_holds = sv.index(min(sv)) >= 11 and ou.index(min(ou)) == 0
    in_play = bool((pred.get("results") or {}).get("active"))
    if not in_play:
        assert sv.index(min(sv)) >= 11, "胜者格最低的不再是垫底队，文案需重写"
        assert ou.index(min(ou)) == 0, "败者格最低的不再是最强队，文案需重写"
    # 已经碰不到附加轮的队：要么已锁定直通（4 胜），要么已出局（4 负）。
    # 这两类队在两格里都是 0%，赛前那套「填谁都一样 / 别填垫底队」的说法对它们无效。
    unreachable = [t for t in order
                   if pred["elim_round_survive"][t] == 0 and pred["elim_round_out"][t] == 0]
    return {"shape_holds": shape_holds, "in_play": in_play,
            "unreachable": unreachable,
            "sv_lo8": min(sv[:8]) * 100, "sv_hi8": max(sv[:8]) * 100,
            "sv_min": min(sv) * 100, "sv_gap": (max(sv) - min(sv)) * 100,
            "ou_min": min(ou) * 100, "ou_gap": (max(ou) - min(ou)) * 100,
            # 「避开最强的那支」在两格里各值多少——更新日志要用这两个数
            # 来说明早先的建议为什么等于没说。
            "sv_cost_top": (max(sv) - sv[0]) * 100,
            "ou_cost_bot": (max(ou) - ou[-1]) * 100}


def compute(pred, strength):
    """产出推荐答案（直觉版）与纯最优版的对照。"""
    best, _ = solve(pred)
    teams = list(pred["record_dist"])
    top_40 = max(teams, key=lambda t: pred["record_dist"][t].get("4-0", 0))
    bot_04 = max(teams, key=lambda t: pred["record_dist"][t].get("0-4", 0))
    intuit, asg = solve(pred, force={top_40: "4-0", bot_04: "0-4"})
    random_baseline = sum(cap * cap / 16.0 for _, cap, _, _, _ in BUCKETS)
    return {
        "answer": asg,
        "fantasy": None,
        "expected_correct": intuit,
        "expected_correct_optimal": best,
        "random_baseline": random_baseline,
        "cost_of_intuition": best - intuit,
        "elim": elim_pitfalls(pred, strength),
    }


def resolved(pred):
    """小组赛那 16 格是否已经全部揭晓。

    判据是概率退化成 0/1：瑞士轮与附加轮全部打完之后，每支队落在哪一档
    已经是事实，record_dist 与 elim_round_* 里不再有中间值。
    用「期望答对数 == 16」当判据也等价，但那要多跑一次匈牙利算法；
    这里直接看分布本身，更便宜也更直白。
    """
    for _, _, _, src, key in BUCKETS:
        for team in pred["record_dist"]:
            p = _prob(pred, src, key, team)
            if 1e-9 < p < 1 - 1e-9:
                return False
    return True


def score_against(pre_pred, pred, strength):
    """拿赛前那一版的建议填法，对着已揭晓的答案打分。

    pre_pred 必须是**冻结件**（8/13 锁定前挂在站上的那一版），不能是当前产物——
    当前产物已经知道答案了，拿它算「赛前建议」等于开卷考试。这条纪律与
    site/build_site.py 的 REVIEWS 表是同一条：历史条目只能指向冻结件。

    返回 {"buckets": [...], "hits": n, "expected": 赛前自称期望, "random": 乱填基线}。
    """
    truth = {b: [t for t, _ in v] for b, v in compute(pred, strength)["answer"].items()}
    pre = compute(pre_pred, strength)
    rows, hits = [], 0
    for nm, cap, desc, src, key in BUCKETS:
        picks = [t for t, _ in pre["answer"].get(nm, [])]
        got = truth.get(nm, [])
        hit = [t for t in picks if t in got]
        hits += len(hit)
        rows.append({
            "bucket": nm, "cap": cap, "desc": desc,
            "picks": picks, "truth": got, "hit": hit,
            # 赛前给每个人选的命中概率。押中一个 17.6% 的格子说明不了什么，
            # 所以打分时必须把「当时有多不确定」一并摆出来，而不是只报命中数。
            "pre_p": {t: _prob(pre_pred, src, key, t) for t in picks},
        })
    return {"buckets": rows, "hits": hits, "total": sum(c for _, c, _, _, _ in BUCKETS),
            "expected": pre["expected_correct"], "random": pre["random_baseline"]}


def elim_note(ep, base):
    """「淘汰赛胜者 / 败者」两格的说明。赛前与赛中是两套说法，不能混用。

    赛前：两格形状相反，坑分别是「填垫底队」和「填最强队」。
    赛中：一旦有队伍锁定 4 胜（直通）或 4 负（出局），它们**根本碰不到附加轮**，
          两格概率同时归零——赛前那句「坑是填垫底队」就不成立了
          （最低的变成了那支 4-0 直通的队）。硬套赛前措辞会印出一句错话，
          所以这里按 shape_holds 分叉，由 elim_pitfalls 判定形状是否还成立。
    """
    if ep["shape_holds"]:
        return """<div class="note"><b>这两格最贵，而且方向相反。</b><br>
两格的概率都等于「打得上那一轮」乘「打上了赢还是输」。前一项随实力先升后降——太强的直接晋级，
太弱的直接出局，两头都碰不到这一轮；后一项则随实力一路走高。两项乘出来是两个完全不同的形状。<br>
<b>「淘汰赛胜者」：实力前八全挤在 %.1f%%–%.1f%%，填哪支都一样，别在这纠结。</b>
真正的坑是填垫底队——最低只有 %.1f%%，比最优的一格差 %.1f 个百分点。<br>
<b>「淘汰赛败者」：反过来，最该躲开的是最强的那支。</b>它只有 %.1f%%，比最优低 %.1f 个百分点——
强队根本打不到附加轮就直通了，填在这格几乎是白给。</div>""" % (
            ep["sv_lo8"], ep["sv_hi8"], ep["sv_min"], ep["sv_gap"],
            ep["ou_min"], ep["ou_gap"])

    unreachable = ep["unreachable"]
    return """<div class="note crit"><b>赛程推进之后，这两格的形状变了——赛前那句建议现在不成立了。</b><br>
赛前的说法是「胜者格填谁都一样，坑是填垫底队」。那条依赖一个前提：每支队都还有可能打到附加轮。
现在这个前提破了：瑞士轮打到 <b>4 胜或 4 负即停</b>，
<b>%s</b> 已经锁定直通或已经出局，<b>根本碰不到附加轮</b>，两格概率同时归零。
所以现在两格里最低的不再是垫底队，而是那支已经打完的队。<br>
<span class="hint">这不是模型改了，是赛况变了。构建脚本里那条守着这句文案的断言在 8/15 被真实赛况打掉，
本段就是替换上来的新说法——旧说法留在<a href="%s/review.html">复盘页</a>的第一次复盘里，没有删改。</span></div>""" % (
        "、".join(pages.esc(t) for t in unreachable) or "部分队伍", base)


def bracket_section(base, pl):
    """游戏内主赛事预测面板（「国际邀请赛」页签）的建议填法。

    面板是一整张对阵表、14 场逐场点胜者——与小组赛那 16 格的分档填空完全不是
    一道题。所以这里不能复用 solve()（匈牙利分配），要的是
    model.l6_playoffs.best_bracket 在 16384 种自洽填法里搜出来的那一种。
    """
    bh = pl["bracket_homework"]
    st = bh["stats"]
    si = pl.get("implied_solve") or {}
    rows = bh["rows"]

    def block(title, keys):
        out = []
        for r in rows:
            if r["stage"] not in keys:
                continue
            alts = "".join(
                '<div class="pick"><span class="t">%s</span><span class="p">%.0f%%</span></div>'
                % (esc(c["team"]), c["p"] * 100)
                for c in r["top"][1:4] if c["team"] != r["pick"])
            out.append(
                '<div class="hwcard"><div class="hwhead"><b>%s</b>'
                '<span>%s · %s</span></div>'
                '<div class="pickbig">%s</div>'
                '<div class="picksub">这一场它赢的概率 %.1f%%　｜　其它可能</div>%s</div>'
                % (esc(r["panel"]), esc(r["cn"]), esc(r["time_cst"]),
                   esc(r["pick"]), r["p_pick"] * 100, alts or
                   '<div class="pick"><span class="t">—</span><span class="p"></span></div>'))
        return '<div class="hwgrid">%s</div>' % "".join(out)

    unstable = si.get("pick_unstable_stages") or []
    lbl = {r["stage"]: r["panel"] for r in rows}
    pk = {r["stage"]: r["p_pick"] for r in rows}
    stab = ("<b>%d 格里只有 %s 会随这个判断翻面</b>（%s），而它们本来就在五五开附近；"
            "<b>另外 %d 格在整个权重范围内一模一样</b>——也就是说这个判断怎么选，"
            "对结论几乎没有影响。"
            % (len(rows), "、".join(lbl.get(s, s) for s in unstable),
               "、".join("%s %.0f%%" % (lbl.get(s, s), pk.get(s, 0) * 100) for s in unstable),
               si.get("pick_stable_count", 0))
            if unstable else
            "<b>整个权重范围内 %d 格填法完全一致</b>——这个判断怎么选都不影响结论。" % len(rows))

    return """
<h2>一、照着这张图填（14 场，%s 锁定）</h2>
<p>版式与客户端里那张表一致——列的位置、格子编号 A–G、日期、队伍简称都照抄，
可以逐格平移着点。<b>实心圆点就是建议点亮的那一边</b>，右边的百分比是它赢下这一场的概率。</p>
%s
<p class="hint">客户端里后面几轮显示「?」，这里填的是模型的推荐——那正是这张图的用处。
<b>注意后面几轮的候选是被前面的选择锁死的</b>：你如果在 A 格改填 Iron Wing，
E 格的候选也会跟着变，不能照抄下面这份了。</p>

<div class="pkbar">
  <div class="pkstats">
    <div><span class="pklab">这份填法期望答对</span><span class="pkbig">%.2f</span><span class="pkunit">/ 14 场</span></div>
    <div><span class="pklab">闭眼乱填</span><span class="pkbig">%.2f</span><span class="pkunit">场</span></div>
    <div><span class="pklab">理论上界</span><span class="pkbig">%.2f</span><span class="pkunit">场</span></div>
  </div>
  <div class="pkmeter"><div style="width:%.1f%%"></div></div>
  <div class="pkbtns"><span class="pkstat ok">在 %s 种自洽填法里穷举出来的最优解</span></div>
</div>

<div class="note crit"><b>先说清楚这道题为什么不能「每场都挑赢面大的」。</b><br>
对阵表是有路径的：你填进「胜者组第 2 轮」的队，<b>必须是你自己在第 1 轮推上去的那两支之一</b>。
所以后面每一轮的可选项都被前面的选择锁死，「每场都挑最可能赢的那支」通常<b>根本填不出来</b>。<br>
那个填法的分数是 <b>%.2f 场</b>——它是个够不着的上界，不是可选项。真正能填出来的最优是
<b>%.2f 场</b>，中间这 <b>%.2f 场</b>就是「路径必须自洽」这条约束的代价。<br>
<span class="hint">16384 = 2^14，14 场各二选一。这个规模可以直接穷举，不需要任何启发式，
所以下面这份填法是<b>确定的最优解</b>，不是搜出来的近似。</span></div>

<h3>胜者组（4 + 2 + 1 场）</h3>
%s
<h3>败者组（2 + 2 + 1 + 1 场）</h3>
%s
<h3>总决赛</h3>
%s

<div class="note"><b>看一眼这些概率再决定要不要照抄。</b><br>
八强那四场还有 %.0f%%–%.0f%%，到了败者组中段就只剩<b>百分之十几</b>了——
因为那时候「谁能走到那一场」本身就很不确定，你押的队多半根本没到场。
<b>越往后的格子越接近碰运气，这是题目的性质，不是模型不行。</b><br>
<span class="hint">这也是为什么期望只有 %.2f/14：比乱填多 %.2f 场，
但离「全对」差得远。跟小组赛那 16 格一样，它能帮你够保底，冲榜不够。</span></div>

<div class="note"><b>一个口径说明：这份填法用的是融合口径（模型 ⊕ 市场）。</b><br>
八强那四场 Polymarket 开了<b>单场盘</b>，是对这四场的直接定价；再往后没有盘口，
靠反解出的隐含实力展开。两个市场（冠军盘、单场盘）互相不完全一致，
调和时给单场盘多少权重是个判断——%s</div>
""" % (pages.PANEL_DEADLINE_CN,
       '<div class="bkwrap">%s</div>' % bracket_svg.render(pl, "page"),
       st["expected"], st["random"], st["greedy_upper"],
       st["expected"] / st["n_matches"] * 100, "{:,}".format(st["n_brackets"]),
       st["greedy_upper"], st["expected"], st["greedy_upper"] - st["expected"],
       block("ub", {"UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2", "UBF"}),
       block("lb", {"LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "LBF"}),
       block("gf", {"GF"}),
       min(r["p_pick"] for r in rows if r["stage"].startswith("UBQF")) * 100,
       max(r["p_pick"] for r in rows if r["stage"].startswith("UBQF")) * 100,
       st["expected"], st["expected"] - st["random"], stab)


def render_settled(base, score, fan, fan_rec, pl=None):
    """小组赛 16 格已全部揭晓时的版本：公布答案 + 给赛前那一版打分。

    为什么必须换一套渲染：揭晓之后 record_dist 退化成 0/1，solve() 会原样吐出
    标准答案、期望答对数变成 16。照旧渲染就是「建议你填正确答案，期望答对 16 格」——
    一句正确但毫无意义的话，而且看着像在吹牛。这一页的价值在揭晓那一刻从
    「帮你填」变成「我填的对了几格」，所以整页换成对账。
    """
    cards = []
    for row in score["buckets"]:
        picked = []
        for t in row["picks"]:
            ok = t in row["hit"]
            picked.append(
                '<div class="pick"><span class="t">%s%s</span>'
                '<span class="p">赛前 %.1f%%</span></div>'
                % ("✓ " if ok else "✗ ", esc(t), row["pre_p"].get(t, 0) * 100))
        missed = [t for t in row["truth"] if t not in row["hit"]]
        miss_line = ('<div class="picksub">没押中的实际是：%s</div>'
                     % "、".join(esc(t) for t in missed)) if missed else ""
        cards.append(
            '<div class="hwcard"><div class="hwhead"><b>%s</b>'
            '<span>%s · %d/%d</span></div>%s%s</div>'
            % (esc(row["bucket"]), esc(row["desc"]), len(row["hit"]), row["cap"],
               "".join(picked), miss_line))

    key_rows = "".join(
        "<tr><td class=lft>%s</td><td class=lft>%s</td></tr>"
        % (esc(row["bucket"]), "、".join(esc(t) for t in row["truth"]))
        for row in score["buckets"])

    fslots = []
    for key, cn, desc in SLOT_CN:
        d = fan_rec[key]
        best = d["rows"][0]
        alts = "".join(
            '<div class="pick"><span class="t">%s</span><span class="p">%+.1f%%</span></div>'
            % (esc(r["team"]), r["gap"] * 100) for r in d["rows"][1:4])
        fslots.append(
            '<div class="hwcard"><div class="hwhead"><b>%s</b><span>%s</span></div>'
            '<div class="pickbig">%s</div>'
            '<div class="picksub">备选（差距）</div>%s</div>'
            % (esc(cn), esc(desc), esc(best["team"]), alts))

    beat = score["hits"] - score["expected"]
    return ("""
<h1>抄作业</h1>
<p class="lede"><b>现在要填的是游戏内「赛事预测 → 国际邀请赛」那张对阵表</b>——
14 场逐场点胜者，<b>%(deadline)s 锁定</b>。下面第一张图就是照着客户端版式画的，
可以直接对着填；再往下是每一格的概率和理由。</p>
<p class="meta">另一个页签「小组赛」那 16 格已于 %(group_deadline)s 锁定并全部揭晓，
本页第三节公布标准答案并给我赛前那一版打分（%(hits_head)d/16）·
想看完整预测去<a href="%(base_head)s/">八强前瞻</a></p>

%(bracket)s

<h2>三、另一个页签：小组赛那 16 格，答案已经揭晓</h2>
<div class="pkbar">
  <div class="pkstats">
    <div><span class="pklab">赛前那版实际答对</span><span class="pkbig">%(hits)d</span><span class="pkunit">/ %(total)d 格</span></div>
    <div><span class="pklab">它当时自称的期望</span><span class="pkbig">%(expected).2f</span><span class="pkunit">格</span></div>
    <div><span class="pklab">闭眼乱填</span><span class="pkbig">%(random).2f</span><span class="pkunit">格</span></div>
  </div>
  <div class="pkmeter"><div style="width:%(pct).1f%%"></div></div>
  <div class="pkbtns"><span class="pkstat ok">比自己的期望多 %(beat).2f 格，比乱填多 %(over_random).2f 格</span></div>
</div>

<div class="note %(tone)s"><b>这个成绩比期望好，但别当成本事。</b><br>
16 格里押中 %(hits2)d 格，而赛前这一版自己算出来的期望是 %(expected2).2f 格——<b>超出了 %(beat2).2f 格</b>。
超出的部分主要是运气：每一格的命中概率赛前都写在下面，<b>最高的一格也只有 %(maxp).1f%%</b>——
没有哪一格是稳的，押中的每一格都是在赌一件多半不会发生的事。<br>
<span class="hint">要判断这套方法有没有用，该看的是<a href="%(base_review)s/review.html">复盘页</a>那 44 场系列赛的
Brier 分解，不是这 16 格的命中数。</span></div>

<h3>标准答案</h3>
<div class="tbl-wrap"><table class="rv">
<thead><tr><th class=lft>格子</th><th class=lft>实际是谁</th></tr></thead>
<tbody>%(key_rows)s</tbody></table></div>

<h3>我赛前是怎么填的，对了几格</h3>
<p>下面是 <b>8 月 13 日面板锁定前</b>挂在站上的那一版建议填法，逐格对答案。
用的是当时的冻结件，不是现在的产物——<b>拿知道答案之后的模型去算「赛前建议」，那是开卷考试。</b></p>
<div class="hwgrid">%(cards)s</div>

<h2>四、梦幻挑战还在计分</h2>
<p>梦幻挑战算的是<b>整届赛事</b>，淘汰赛这 14 场还在往里加分，所以这三格现在依然有效。</p>
<div class="hwgrid">%(fslots)s</div>
<div class="note"><b>决定分数的不是选谁打得好，而是选的队能走多远。</b>
小组赛就回家的队大概打 6 个系列赛，一路杀进决赛的能打 9 个以上——
这个差距比选手之间的每局表现差距大得多。<b>八支队各自能走多远，在<a href="%(base_f)s/">八强前瞻</a>那页。</b></div>

<div class="note good"><b>剩下的账还会继续对。</b>8 月 23 日打完，淘汰赛那 14 场也会逐场回填、
连同这 16 格一起公布最终成绩——好看不好看都发。</div>

<div class="cta">
  <div>
    <b>「TI15 抄作业群」还在</b>
    <span>8/20 淘汰赛开打，群里一起看这份预测被打成什么样。</span>
  </div>
  <a class="cta-btn" href="%(base_cta)s/group.html">扫码进群 →</a>
</div>
""" % {
        "deadline": pages.PANEL_DEADLINE_CN,
        "group_deadline": pages.GROUP_DEADLINE_CN,
        "hits_head": score["hits"],
        "base_head": base,
        "bracket": bracket_section(base, pl) if pl else "",
        "hits": score["hits"], "total": score["total"],
        "expected": score["expected"], "random": score["random"],
        "pct": score["hits"] / score["total"] * 100,
        "beat": beat, "over_random": score["hits"] - score["random"],
        "tone": "good" if beat > 0 else "crit",
        "hits2": score["hits"], "expected2": score["expected"], "beat2": beat,
        "maxp": max((p for row in score["buckets"] for p in row["pre_p"].values()),
                    default=0) * 100,
        "base_review": base,
        "key_rows": key_rows, "cards": "".join(cards), "fslots": "".join(fslots),
        "base_f": base, "base_cta": base,
    })


def render(base, hw, pred, fan, fan_rec, sens=None, banner=""):
    ep = hw["elim"]

    def esc(s):
        import html as _h
        return _h.escape(str(s), quote=True)

    cards = []
    for nm, cap, desc, _, _ in BUCKETS:
        picks = hw["answer"].get(nm, [])
        rows = "".join(
            '<div class="pick"><span class="t">%s</span><span class="p">%.1f%%</span></div>'
            % (esc(t), p * 100) for t, p in picks)
        cards.append(
            '<div class="hwcard"><div class="hwhead"><b>%s</b><span>%s · 选 %d 支</span></div>%s</div>'
            % (esc(nm), esc(desc), cap, rows))

    teams = list(pred["record_dist"])
    order = sorted(teams, key=lambda t: -pred["champion"][t])
    detail = "".join(
        "<tr><td>%s</td>%s<td class=num>%.1f%%</td><td class=num>%.1f%%</td></tr>"
        % (esc(t),
           "".join("<td class='num%s'>%.1f%%</td>"
                   % (" hi" if pred["record_dist"][t].get(k, 0) == max(
                       pred["record_dist"][t].get(x, 0) for x in ("4-0", "4-1", "3-2", "2-3", "1-4", "0-4")) else "",
                      pred["record_dist"][t].get(k, 0) * 100)
                   for k in ("4-0", "4-1", "3-2", "2-3", "1-4", "0-4")),
           pred["elim_round_survive"][t] * 100, pred["elim_round_out"][t] * 100)
        for t in order)

    fslots = []
    for key, cn, desc in SLOT_CN:
        d = fan_rec[key]
        best = d["rows"][0]
        alts = "".join(
            '<div class="pick"><span class="t">%s</span><span class="p">%+.1f%%</span></div>'
            % (esc(r["team"]), r["gap"] * 100) for r in d["rows"][1:4])
        fslots.append(
            '<div class="hwcard"><div class="hwhead"><b>%s</b><span>%s</span></div>'
            '<div class="pickbig">%s</div>'
            '<div class="picksub">备选（差距）</div>%s</div>'
            % (esc(cn), esc(desc), esc(best["team"]), alts))

    ftable = "".join(
        "<tr><td>%s</td><td class=num>%.1f</td><td class=num>%.1f</td><td class=num>%.1f</td>"
        "<td class=num>%.1f</td></tr>"
        % (esc(t),
           fan["proxy_score_by_slot"]["core"][t], fan["proxy_score_by_slot"]["mid"][t],
           fan["proxy_score_by_slot"]["support"][t],
           pred["series_dist"][t]["group"] + pred["series_dist"][t]["playoff"])
        for t in sorted(fan["proxy_score_by_slot"]["core"],
                        key=lambda x: -(pred["series_dist"][x]["group"] + pred["series_dist"][x]["playoff"])))

    # banner 是拼进格式化字符串的现成 HTML；先把 % 逃逸掉，否则它一旦含
    # 百分号（概率文案里迟早会有），% 格式化会在这里炸或者错位。
    banner = (banner or "").replace("%", "%%")
    return ("""
<h1>抄作业</h1>
<p class="lede">这一页是给<b>游戏里那两个要填的东西</b>准备的——<b>赛事预测</b>那 16 个格子，和<b>梦幻挑战</b>那三个位置。
不想看分析的，看这页就够了，照着填完关掉即可。</p>
<p class="meta">小组赛部分 %s 锁定</p>
""" + banner + """
<div class="note crit"><b>抄之前先知道一件事。</b><br>
这份预测的期望是<b>答对 %.1f 格</b>，闭着眼睛乱填是 <b>%.1f 格</b>——<b>只多一格多一点</b>。<br>
Valve 自己说过：<b>历史上没有任何人完整猜对过小组赛。</b>
它能帮你稳稳够到保底奖励，想靠它冲榜首是不够的。</div>

<h2>一、赛事预测 · 小组赛（16 格）</h2>
<p>下面每一格都列了全部 16 支队和它落到这格的可能性。<b>直接点就能改</b>——
一支队只能占一格，点别的格会自动把它从原来那格挪过来。</p>

<div class="pkbar">
  <div class="pkstats">
    <div><span class="pklab">期望答对</span><span class="pkbig" id="exp">—</span><span class="pkunit">格</span></div>
    <div><span class="pklab">比乱填多</span><span class="pkbig" id="delta">—</span><span class="pkunit">格</span></div>
    <div><span class="pklab">已填</span><span class="pkbig" id="cnt">—</span></div>
  </div>
  <div class="pkmeter"><div id="expbar"></div></div>
  <div class="pkbtns">
    <span class="pkstat" id="status"></span>
    <button id="btn-model">用模型推荐填</button>
    <button id="btn-clear">清空</button>
    <button id="btn-share" class="pri">复制我的填法链接</button>
  </div>
</div>

<div id="picker"></div>
<p class="hint">数字都不高很正常——16 支队水平太接近，任何一格都谈不上稳。
<b>底色条</b>表示相对高低，方便一眼看出哪几个是同一档。</p>

%s

<h2>二、梦幻挑战（3 个位置）</h2>
<p>这三格选的都是<b>队伍</b>不是选手。核心格算这支队两个核心的分，辅助格算两个辅助的分，中单格只算中单一个人。</p>
<div id="fpicker"></div>

<div class="note"><b>说实话：这三格怎么选，差别非常小。</b><br>
上面「备选」后面的百分比就是差距——前几名之间只差个位数。<br>
真正决定你分数的<b>不是选谁打得好，而是选的队能走多远</b>：小组赛就回家的队大概打 6 个系列赛，
一路杀进决赛的能打 9 个以上，这个差距比选手之间的每局表现差距大得多。<br>
<b>所以选队伍时，优先看它能不能走得远。</b></div>

<h2>三、想自己配一版</h2>
<p>下面两张表是原始数据，你可以按自己的判断重新组合。</p>

<h3>各队落到每一格的可能性</h3>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>全胜</th><th>四胜一负</th><th>三胜两负</th><th>两胜三负</th>
<th>一胜四负</th><th>全败</th><th>淘汰赛胜</th><th>淘汰赛败</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">加粗的是这支队最可能的结果。「三胜两负」和「两胜三负」两列加起来，就是它打进淘汰赛那一轮的可能性。</p>

<h3>梦幻挑战：各队三个位置的每局预期表现</h3>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>核心</th><th>中单</th><th>辅助</th><th>预计打多少个系列赛</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">分数用的是往届的计分规则换算的，只能用来<b>比较高低</b>，不是你实际会拿到的分。
今年每一项值多少分，游戏没有公开。</p>

<h2>三件要说在前面的事</h2>
<p><b>一、这一版用上了已经打完的比赛；分组官方仍没公布，我们也仍然没有猜。</b>
已完赛的系列赛结果已经当成事实代入重算，不再当随机变量抽；「谁跟谁一组」官方从没公布过，
但每打完一轮，已知对阵就会把可能的分法收紧一层（赛前 35 种 → 现在更少），
模拟时对剩下的可能性平均
（<a href="%s/predictions.html#draw">为什么不挑一种，写在这里</a>；
逐场对账见<a href="%s/review.html">复盘页</a>）。
知道分组也别抱期望：<b>我实测过了，知道完整分组只让期望答对数变约 %.2f 格</b>——
这一页相对乱填的价值是 %.1f 格，分组只在这上面再加不到 5%%。<br>
<span class="hint">原来这里写的是「那版会准不少」。我做了个对照实验才发现说大了：
换不同分组，建议填法确实经常变，看着像很重要；但把分组固定住、只换随机种子，
填法照样变——因为中间那几格在前八队之间只差一两个百分点，本来就是近似平局。
<b>变化不等于变准。</b>分组带来的波动只有随机噪声的 %.1f 倍，绝对量小到可以忽略。
个别队的概率会动，最多 %.1f 个百分点，所以重算仍然值得做——但只是把数字更新准确，不是变准。</span></p>
<p><b>二、辅助那一格我们算得最不准。</b>梦幻挑战的计分项里有两项数据是拿不到的，
而这两项恰好都算在辅助头上。所以辅助格的建议，可信度比另外两格低。</p>
<p><b>三、全胜那一格严格说不是最优解。</b>纯算下来把最强的队放在「四胜一负」更划算，
但两种选法的差距只有 <b>%.2f 格</b>，完全在误差里。这里给的是符合直觉、你也能跟人解释得通的那版。</p>

<div class="note"><b>想让别人看你怎么填的？</b>点上面的「复制我的填法链接」，
把链接发出去——别人打开就能看到你的完整填法和期望答对数，可以直接跟你的比。<br>
<span class="hint">填法是编在链接里的，没有账号、没有 cookie、也不会上传到任何地方。</span></div>

<div class="note good"><b>这份作业也会被打分。</b>8 月 23 日打完，我会公布这 16 格实际对了几格、
梦幻阵容拿了多少分——跟夺冠预测一起，好看不好看都发。</div>

<div class="cta">
  <div>
    <b>想跟别人比填法？进「TI15 抄作业群」</b>
    <span>群里可以互相看填法、开赛后跟进，8/23 一起对分数。</span>
  </div>
  <a class="cta-btn" href="%s/group.html">扫码进群 →</a>
</div>
""") % (pages.PANEL_DEADLINE_CN,
       hw["expected_correct"], hw["random_baseline"],
       elim_note(ep, base),
       detail, ftable,
       # 「一、分组是推的」那段：实测数字来自 reports/p6_draw_sensitivity.json
       base, base, sens["draw_spread"], hw["expected_correct"] - hw["random_baseline"],
       sens["ratio"], sens["max_p40_swing_pp"],
       hw["cost_of_intuition"], base)
