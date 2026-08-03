"""生成「作业」页：官方游戏内预测面板的建议填法。

题型来自客户端本地化文件 DOTA_Predictions26_*（一手），并经用户客户端截图核对。
分档 1/2/5/5/2/1 是赛制的结构性恒等式，不是概率。
最优分配用匈牙利算法（题目是把 16 队分到 6 档，各档不能重复用队）。
"""
import json
import os

import numpy as np
from scipy.optimize import linear_sum_assignment

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


def compute(pred):
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
    }


def render(base, hw, pred, fan, fan_rec):
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

    return """
<h1>抄作业</h1>
<p class="lede">这一页是给<b>游戏里那两个要填的东西</b>准备的——<b>赛事预测</b>那 16 个格子，和<b>梦幻挑战</b>那三个位置。
不想看分析的，看这页就够了，照着填完关掉即可。</p>
<p class="meta">小组赛部分 8 月 13 日 23:00（北京时间）锁定</p>

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

<div class="note"><b>最容易填错的是「淘汰赛胜者」那 5 格：别填最强的队。</b><br>
听起来反直觉，但道理很简单——<b>越强的队越可能直接全胜或一负出线，压根不打淘汰赛那一轮。</b>
这 5 格奖励的是中游队：强到能赢，但没强到能直接晋级。<br>
同理，「淘汰赛败者」也别填最弱的两支，它们更可能直接垫底出局，也进不了那一轮。</div>

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
<p><b>一、分组还没公布。</b>第一轮谁打谁是主办方定的，还没出。等公布之后我会重算一版，那版会准不少。</p>
<p><b>二、辅助那一格我们算得最不准。</b>梦幻挑战的计分项里有两项数据是拿不到的，
而这两项恰好都算在辅助头上。所以辅助格的建议，可信度比另外两格低。</p>
<p><b>三、全胜那一格严格说不是最优解。</b>纯算下来把最强的队放在「四胜一负」更划算，
但两种选法的差距只有 <b>%.2f 格</b>，完全在误差里。这里给的是符合直觉、你也能跟人解释得通的那版。</p>

<div class="note"><b>想让别人看你怎么填的？</b>点上面的「复制我的填法链接」，
把链接发出去——别人打开就能看到你的完整填法和期望答对数，可以直接跟你的比。<br>
<span class="hint">填法是编在链接里的，没有账号、没有 cookie、也不会上传到任何地方。</span></div>

<div class="note good"><b>这份作业也会被打分。</b>8 月 23 日打完，我会公布这 16 格实际对了几格、
梦幻阵容拿了多少分——跟夺冠预测一起，好看不好看都发。</div>
""" % (hw["expected_correct"], hw["random_baseline"],
       detail, ftable, hw["cost_of_intuition"])
