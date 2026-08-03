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
        "expected_correct": intuit,
        "expected_correct_optimal": best,
        "random_baseline": random_baseline,
        "cost_of_intuition": best - intuit,
    }


def render(base, hw, pred):
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

    return """
<h1>作业：官方预测面板怎么填</h1>
<p class="lede">游戏内 <b>赛事预测 → 小组赛</b> 那 16 格的建议填法。题面与档位取自客户端本地化文件
<code>DOTA_Predictions26_*</code>，并经实机截图核对。</p>
<p class="meta">截止 2026-08-13 15:00 GMT（北京时间 23:00）· 数字取自冻结产出物 v6</p>

<div class="note crit"><b>先看清楚这个再决定要不要抄。</b><br>
这份作业的期望答对是 <b>%.2f / 16 题</b>，随机乱填是 <b>%.2f 题</b>——<b>只多约 1.4 题</b>。<br>
Valve 自己说过：<b>历史上从来没有人完整猜对过小组赛结果。</b>
它对够到保底奖励档有用，想冲榜首靠它不够。</div>

<h2>建议填法</h2>
<div class="hwgrid">%s</div>
<p class="hint">百分比 = 该队真的落到这一档的模型概率。注意这些数字都不高——
16 队水平接近，任何单格都谈不上稳。</p>

<h2>⚠️ 最容易填错的一格</h2>
<p><b>「淘汰赛胜者」那 5 格，不要填最强的队。</b></p>
<p>模型算出来强队在这一格全挤在 37%%–39%%，而且<b>最强的那支反而更低</b>。原因是两个效应相互抵消：</p>
<div class="note"><b>越强的队，越可能直接拿到 4-0 / 4-1 直通淘汰赛，根本不打这一轮。</b><br>
所以这格奖励的是<b>中游队</b>——强到能赢附加轮，但没强到能直通。<br>
同理「淘汰赛败者」也别填最弱的两支：它们更可能直接掉进 1-4 / 0-4，压根进不了附加轮。</div>

<h2>为什么槽位是 1 / 2 / 5 / 5 / 2 / 1</h2>
<p>这不是 Valve 随手定的，是赛制推出来的<b>恒等式</b>——每届必然如此。瑞士轮<b>打到 4 胜或 4 负即停</b>：</p>
<ul>
<li>R1–R3 组内配对 → 每组 8 队打完必然是 3-0:1 / 2-1:3 / 1-2:3 / 0-3:1</li>
<li>R4 跨组 → 两支 3-0 的队互相碰，<b>必然恰好 1 支 4-0</b>；0-3 同理必然 1 支 0-4</li>
<li>R5 → 3-1 组 4 队出 2 支 4-1，1-3 组 4 队出 2 支 1-4，剩下 3-2 五支、2-3 五支进附加轮</li>
</ul>
<p>所以<b>「本届会有几支 4-0」这种问题没有意义</b>——永远是 1 支。模型该回答的是<b>哪一支</b>。</p>

<h2>完整概率表</h2>
<p>每支队落到各档的概率。想自己配一版跟我不一样的，用这张表。</p>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>4-0</th><th>4-1</th><th>3-2</th><th>2-3</th><th>1-4</th><th>0-4</th>
<th>淘汰赛胜</th><th>淘汰赛败</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">加粗 = 该队最可能落到的档位。3-2 与 2-3 两列合起来就是「进附加轮」的概率。</p>

<h2>两个诚实的说明</h2>
<p><b>一、4-0 那格严格来说不是数学最优。</b>纯最优解会把它让给别的队（因为最强队放在 4-1 格更值钱），
但差距只有 <b>%.3f 题</b>，完全在噪声里。所以这里给的是直觉版——同样好，而且你能跟人解释得通。</p>
<p><b>二、分组还没公布，这份作业之后会变。</b>模型对第一轮的分组是随机化处理的。
分组一公布我会重跑一版，那版会明显更准。</p>

<div class="note good"><b>这份作业本身也会被打分。</b>8 月 23 日赛后，我会公布这 16 格实际对了几格——
跟战队层面的预测一起，好看不好看都发。</div>
""" % (hw["expected_correct"], hw["random_baseline"], "".join(cards),
       detail, hw["cost_of_intuition"])
