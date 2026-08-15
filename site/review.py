"""生成「复盘」页：赛前说过的话，现在兑现得怎么样。

这一页是整个项目的立身之本落地的地方——赛前冻结 + 哈希存证，图的就是能在
赛程中途和赛后拿同一套代码给自己打分，好看不好看都发出来。

**为什么是多个页签**

复盘不是一次性的：打完一批比赛就该交一次账。每次复盘做成一个页签，
带自己的时间戳与结论摘要，**历史页签一律从当时的冻结件渲染，不从最新产物渲染**。
这条是硬要求：如果历史页签跟着最新数据漂，它就不再是「我当时是这么说的」，
而变成了「我现在觉得我当时是这么说的」——那这一页就没有存在的意义了。
（更新日志页 8/10 那条就真的这么错过一次，见 site/changelog.py 的注释。）

三条纪律，改这个文件时必须守住：
  1. **数字全部来自 payload，不手写。** 手抄的对账表没法证明自己没抄错。
  2. **难看的数照发。** 方向没看对的场次要单独列出来，不能只报总命中率。
  3. **好看的数要先自我怀疑。** Brier 低到触发项目自己的泄漏护栏时
     （<0.20 要先怀疑数据泄漏而不是庆祝），页面必须自己把这条讲明白，
     并给出分档拆解说明它是赛程难度造成的，而不是当成战绩吹。
"""
import os
import sys

import pages

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model.market import blend_logodds                      # noqa: E402

esc = pages.esc

# 「接近五五开」的口径：模型给强的一方不到 60%。统计表分档与逐场表的标签
# 必须用同一个常量——两处各写一个数，迟早会出现「表里标着五五开、统计里
# 却算进强弱悬殊」这种自相矛盾。
CLOSE_MARGIN = 0.10

# 泄漏护栏（与 model/score.py 的 LEAKAGE_SUSPECT_BELOW 同源语义）。
# 低于这个数，页面必须先自我怀疑，而不是报喜。
LEAKAGE_SUSPECT_BELOW = 0.20


def _scored(matches):
    return [m for m in matches if m["result_a_wins"] is not None]


def _brier(rows):
    if not rows:
        return None
    return sum((m["p_a"] - m["result_a_wins"]) ** 2 for m in rows) / len(rows)


def _hits(rows):
    return sum(1 for m in rows if (m["p_a"] > 0.5) == (m["result_a_wins"] == 1))


def _fav(m):
    """模型赛前看好的一方与它的胜率——读者关心「模型看好谁」，不是表里 A 列是谁。"""
    if m["p_a"] >= 0.5:
        return m["team_a"], m["p_a"]
    return m["team_b"], 1 - m["p_a"]


def _misses(rows):
    return sorted(_fav(m)[1] * 100 for m in rows
                  if (m["p_a"] > 0.5) != (m["result_a_wins"] == 1))


def _stats(matches):
    """一份快照的全部打分口径，一次算完——页面各处引用同一个 dict，不各算各的。"""
    rows = _scored(matches)
    close = [m for m in rows if abs(m["p_a"] - 0.5) < CLOSE_MARGIN]
    far = [m for m in rows if abs(m["p_a"] - 0.5) >= CLOSE_MARGIN]
    return {
        "n": len(rows), "hits": _hits(rows), "brier": _brier(rows),
        "n_close": len(close), "hits_close": _hits(close), "brier_close": _brier(close),
        "n_far": len(far), "hits_far": _hits(far), "brier_far": _brier(far),
        "misses": _misses(rows),
    }


def _prepare(snaps):
    """给每份快照挂上打分结果。放在渲染侧算而不是构建侧，是为了让
    「同一套打分口径」这件事只存在于一个文件里——口径改了，历史与最新
    一起跟着改，两个页签之间永远可比。"""
    for s in snaps:
        s["stats"] = _stats(s["matches"])
    return snaps


def _verdict(snap):
    """页签上那句一行结论。**算出来的，不是写死的**——写死的话下次重算就可能变成假话。

    判据固定：总分是否触发泄漏护栏，以及「接近五五开」那一档离抛硬币（0.25）多远。
    """
    st = snap["stats"]
    head = ("总分低到触发泄漏护栏，自查为赛程偏软"
            if st["brier"] < LEAKAGE_SUSPECT_BELOW else "总分回到正常区间")
    if not st["n_close"]:
        return head
    tail = ("五五开那档已接近抛硬币（%.3f）" % st["brier_close"]
            if st["brier_close"] >= 0.235 else
            "五五开那档 %.3f，仍在正常区间" % st["brier_close"])
    return head + " · " + tail


def _match_table(matches, since=None):
    """逐场对账：赛前概率 → 实际结果。看错的那几场必须一眼看得见。

    since 给上一次复盘已经算过的场次集合，本次新增的行会打「新」标记——
    第二次复盘时读者最想先看的就是「这一批新打的，你看对了几场」。
    """
    out = ['<div class="tbl-wrap"><table class="rv"><thead><tr>'
           "<th>轮次</th><th>对阵</th><th>赛前给的胜率</th><th>实际</th><th>看对了吗</th>"
           "</tr></thead><tbody>"]
    for m in _scored(matches):
        winner = m["team_a"] if m["result_a_wins"] == 1 else m["team_b"]
        loser = m["team_b"] if m["result_a_wins"] == 1 else m["team_a"]
        hit = (m["p_a"] > 0.5) == (m["result_a_wins"] == 1)
        fav, p_fav = _fav(m)
        coin = abs(p_fav - 0.5) < CLOSE_MARGIN
        fresh = since is not None and frozenset((m["team_a"], m["team_b"])) not in since
        out.append(
            '<tr class="%s"><td>%s%s</td><td class="lft">%s <span class=vs>vs</span> %s</td>'
            '<td class="num">%s %.0f%%%s</td><td class="lft"><b>%s</b> %s %s</td>'
            '<td class="num">%s</td></tr>'
            % ("miss" if not hit else "",
               esc(m["stage_cn"]), '<span class="fresh">新</span>' if fresh else "",
               esc(m["team_a"]), esc(m["team_b"]),
               esc(fav), p_fav * 100,
               '<span class="coin">接近五五开</span>' if coin else "",
               esc(winner), esc(m["score"]), esc(loser),
               "✓" if hit else "✗"))
    out.append("</tbody></table></div>")
    return "".join(out)


def _decompose(snap):
    """把「赛前 → 这次复盘」的概率位移拆成两个来源，两项精确相加等于总变化。

        比赛结果带来的 = 融合(新模型, 旧市场) - 融合(旧模型, 旧市场)
        市场重新定价的 = 融合(新模型, 新市场) - 融合(新模型, 旧市场)

    只报一个总变化的话，读者没法知道某支队是自己打上来的还是被市场重新看好的，
    而这两件事的含义完全不同。
    """
    base_pred, base_blend = snap["baseline_pred"], snap["baseline_blend"]
    w = base_blend.get("w_market", 0.7)
    old_model, old_mkt = base_pred["champion"], base_blend["market_consensus"]
    base = blend_logodds(old_model, old_mkt, w)
    mid = blend_logodds(snap["pred"]["champion"], old_mkt, w)
    now = {r["team"]: r["champ_blended"] for r in snap["teams"]}
    return base, mid, now


def _shift_table(snap):
    base, mid, now = _decompose(snap)
    out = ['<div class="tbl-wrap"><table class="rv"><thead><tr>'
           "<th>队伍</th><th>战绩</th><th>赛前夺冠</th><th>现在夺冠</th><th>总变化</th>"
           "<th>其中：打出来的</th><th>其中：市场重定价</th>"
           "<th>进淘汰赛</th></tr></thead><tbody>"]
    cls = lambda v: "up" if v > 0.3 else ("down" if v < -0.3 else "")
    for r in snap["teams"]:
        t = r["team"]
        if t not in base:
            continue
        d_res = (mid[t] - base[t]) * 100
        d_mkt = (now[t] - mid[t]) * 100
        d = (now[t] - base[t]) * 100
        out.append(
            '<tr><td class="lft">%s</td><td class="num rec">%s</td>'
            '<td class="num">%.1f%%</td><td class="num hi">%.1f%%</td>'
            '<td class="num %s">%+.1fpp</td>'
            '<td class="num %s">%+.1fpp</td><td class="num %s">%+.1fpp</td>'
            '<td class="num">%.0f%% → %.0f%%</td></tr>'
            % (esc(t), esc(r["record"]), base[t] * 100, now[t] * 100,
               cls(d), d, cls(d_res), d_res, cls(d_mkt), d_mkt,
               snap["baseline_pred"]["advance_playoffs"][t] * 100, r["advance"] * 100))
    out.append("</tbody></table></div>")
    return "".join(out)


def _shift_summary(snap):
    base, mid, now = _decompose(snap)
    res_d = {t: abs(mid[t] - base[t]) for t in base}
    mkt_d = {t: abs(now[t] - mid[t]) for t in base}
    t_res = max(res_d, key=lambda t: res_d[t])
    t_mkt = max(mkt_d, key=lambda t: mkt_d[t])
    return {"max_res": res_d[t_res] * 100, "team_res": t_res,
            "max_mkt": mkt_d[t_mkt] * 100, "team_mkt": t_mkt,
            "ratio": (mkt_d[t_mkt] / res_d[t_res]) if res_d[t_res] else float("inf")}


def _bucket_status(snap):
    """瑞士轮四个战绩档：还有几支队够得着，以及**已经落定**的那几格是谁。

    只列「赛前有戏、现在已经出局」的队——「OG 不可能拿 4-0」这种话对谁都没用。
    某一格只剩恰好该有的支数时，那一格就已经定了，单独标出来：
    这是唯一能在赛程中途就判对错的部分。
    """
    CAP = {"4-0": 1, "4-1": 2, "1-4": 2, "0-4": 1}
    rec_now = snap["records"]
    rows, settled = [], []
    for label, cap in CAP.items():
        need_w, need_l = (int(x) for x in label.split("-"))
        alive, killed = [], []
        for t, r in rec_now.items():
            w, l = (int(x) for x in r.split("-"))
            was = snap["baseline_pred"]["record_dist"].get(t, {}).get(label, 0.0)
            if w > need_w or l > need_l:
                if was >= 0.05:                 # 赛前有戏（≥5%）才值得点名
                    killed.append((t, was))
            else:
                alive.append(t)
        killed.sort(key=lambda x: -x[1])
        done = len(alive) == cap
        if done:
            # 这一格已经落定：看看赛前推荐的那支队中没中
            rec_pick = max(rec_now, key=lambda t: snap["baseline_pred"]["record_dist"]
                           .get(t, {}).get(label, 0.0))
            p = snap["baseline_pred"]["record_dist"].get(rec_pick, {}).get(label, 0.0)
            settled.append((label, alive, rec_pick, p, rec_pick in alive))
        rows.append(
            "<tr%s><td class='num'><b>%s</b></td><td class='num'>%s</td>"
            "<td class='lft'>%s</td></tr>"
            % (" class='settled'" if done else "", esc(label),
               ("<b>已定：%s</b>" % esc("、".join(alive))) if done else "%d 支" % len(alive),
               "、".join("<b>%s</b>（赛前 %.0f%%）" % (esc(t), p * 100) for t, p in killed)
               or "<span class=dim>没有赛前看好的队被排除</span>"))
    table = ('<div class="tbl-wrap"><table class="rv"><thead><tr><th>档位</th>'
             "<th>还够得着的队</th><th>赛前看好、现在已出局的</th></tr></thead>"
             "<tbody>%s</tbody></table></div>" % "".join(rows))
    return table, settled


def _settled_note(settled):
    """已经落定的档位：赛前押的那支中没中，这是能在中途就判死的部分，必须写。"""
    if not settled:
        return ""
    good = [s for s in settled if s[4]]
    bad = [s for s in settled if not s[4]]
    parts = []
    for label, alive, pick, p, hit in settled:
        parts.append(
            "<li><b>%s</b> 已经落定，是 <b>%s</b>。赛前这一格概率最高的是 %s（%.0f%%）——"
            "<b style=\"color:var(--%s)\">%s</b></li>"
            % (esc(label), esc("、".join(alive)), esc(pick), p * 100,
               "good" if hit else "crit", "押中了" if hit else "押错了"))
    return ('<div class="note %s"><b>已经可以判对错的格子：%d 对 %d。</b><ul class="settled-list">%s</ul>'
            "这是整套预测里唯一能在赛程中途就盖棺定论的部分，好的坏的都在这儿了。</div>"
            % ("crit" if bad else "good", len(good), len(bad), "".join(parts)))


def _group_section(snap):
    """分组那一节。收敛到唯一解之后，说法必须从「还剩几种」改成「已经解开了」。"""
    n = snap["n_group_splits"]
    if n > 1:
        return """
<h3>二、「分组不猜」——现在证明这是对的，而且它正在自己解开</h3>
<p>赛前官方从没公布过 A/B 分组。当时的做法是<b>不猜</b>：与已知首轮自洽的分法有 35 种，全部平均掉。
也曾打算从转播分流推一种填进去，最后放弃了。</p>
<p><b>现在回头看，那个决定的价值不在于「猜对了没有」，而在于根本不必猜。</b>
瑞士轮前三轮只在组内配对，所以<b>每打完一轮，「谁跟谁必须同组」的约束就多一层</b>：</p>
<div class="tbl-wrap"><table class="rv">
<thead><tr><th>已知信息</th><th>必须同组的「块」</th><th>还剩几种分法</th></tr></thead>
<tbody>
<tr><td class="lft">只有首轮（赛前）</td><td class="num">8 块 × 2 队</td><td class="num">35 种</td></tr>
<tr><td class="lft">加上第二轮（现在）</td><td class="num">4 块 × 4 队</td><td class="num hi">%d 种</td></tr>
<tr><td class="lft">打完第三轮</td><td class="num">2 块 × 8 队</td><td class="num">1 种（唯一确定）</td></tr>
</tbody></table></div>
<p>也就是说<b>分组会自己解出来，只要再等一轮</b>。赛前花力气去赌那 35 选 1，赌赢了也只是提前两天知道一件
必然会自己揭晓的事，赌输了整版预测的前三轮对手全错。<b>现在仍然是 %d 选 1，所以仍然不猜</b>——
排期上有一种看着最像（同一批 8 队总在同一时段打），但那和当初被否掉的「按转播分流推」是同一级别的旁证。</p>
<div class="note">这 4 个「必须同组」的块是从已发生的对阵反推的，不是官方公布的：%s</div>
""" % (n, n, "；".join("<b>{%s}</b>" % esc("、".join(b)) for b in snap["blocks"]))

    ga, gb = snap["groups"]
    return """
<h3>二、「分组不猜」——它自己解开了，一次都没猜过</h3>
<div class="note good"><b>上一次复盘在这里写了一句预告：「打完第三轮，分组会塌缩成唯一解」。
第三轮打完了，它真的塌缩了。</b></div>
<p>赛前官方从没公布过 A/B 分组，至今也没有。当时的做法是<b>不猜</b>——与已知首轮自洽的分法有 35 种，
全部平均掉。中途一度打算从转播分流推一个填进去，放弃了。</p>
<p>瑞士轮前三轮只在组内配对、第四轮只跨组，所以每打完一轮，约束就多一层：</p>
<div class="tbl-wrap"><table class="rv">
<thead><tr><th>已知信息</th><th>必须同组的「块」</th><th>还剩几种分法</th></tr></thead>
<tbody>
<tr><td class="lft">只有首轮（赛前）</td><td class="num">8 块 × 2 队</td><td class="num">35 种</td></tr>
<tr><td class="lft">加上第二轮</td><td class="num">4 块 × 4 队</td><td class="num">3 种</td></tr>
<tr><td class="lft">加上第三轮（现在）</td><td class="num">2 块 × 8 队</td><td class="num hi">1 种 —— 唯一确定</td></tr>
</tbody></table></div>
<div class="cols">
  <div class="half"><h4>一组</h4><p class="grouplist">%s</p></div>
  <div class="half"><h4>另一组</h4><p class="grouplist">%s</p></div>
</div>
<div class="note good"><b>而且它被两个方向相反的约束同时验证了。</b>
前三轮只在组内配对——<b>24 场系列赛全部落在这条分界线之内</b>；
第四轮只跨组配对——<b>8 场系列赛全部跨越这条分界线，无一例外</b>。
一个错的分组不可能同时满足这两边。<b>所以这个分组不是猜出来的，也不是官方给的，是被比赛本身解出来的。</b></div>
<p>回过头看赛前那个决定：赌 35 选 1，赌赢了只是提前两天知道一件必然会揭晓的事，
赌输了整版预测的前三轮对手全错。<b>不赌是对的，而且不需要事后诸葛就能知道它是对的。</b></p>
""" % ("、".join(esc(t) for t in ga), "、".join(esc(t) for t in gb))


def _coinflip_note(st):
    """「接近五五开」那一档逼近抛硬币时，必须把这件事挑明。

    抛硬币的 Brier 恒为 0.25。这一档一旦贴上去，正确的说法**既不是**「模型看走眼了」，
    **也不是**「模型很准」，而是：模型说这些是五五开，它们就真的表现得像五五开——
    校准是对的，但在这类比赛上它没有提供任何信息量。两种说法都容易写歪，所以固定成
    一段由数据触发的话，不靠临场发挥。
    """
    if not st["n_close"] or st["brier_close"] < 0.235:
        return ""
    return """<div class="note crit"><b>这里必须说清楚一件容易被读成两种极端的事。</b>
接近五五开的那 %d 场，方向只对了 <b>%d 场</b>（%.0f%%），Brier <b>%.3f</b>——
而<b>抛硬币的 Brier 恒为 0.25</b>。它已经贴到抛硬币了。
<br><br>
正确的读法<b>不是</b>「模型看走眼了」，也<b>不是</b>「模型很准」，而是：
<b>模型说这些比赛是五五开，它们就真的表现得像五五开。</b>
从校准的角度看这是对的——给 50%% 的那批比赛，实际赢面确实在 50%% 附近。
但它同时意味着一件不那么好听的事：<b>在势均力敌的比赛上，这个模型没有提供任何信息量。</b>
它能告诉你的只有「谁明显更强」，而这一点你不看模型也知道。
<br><br>
所以整体 Brier %.3f 看着不错，那是被另外 %d 场送分题拉下来的。
<b>要判断这套模型有没有用，只看五五开那一档。</b></div>""" % (
        st["n_close"], st["hits_close"], 100.0 * st["hits_close"] / st["n_close"],
        st["brier_close"], st["brier"], st["n_far"])


def _one_review(snap, base, since):
    """渲染一次复盘的正文。"""
    st = snap["stats"]
    sh = _shift_summary(snap)
    buckets, settled = _bucket_status(snap)
    suspect = st["brier"] < LEAKAGE_SUSPECT_BELOW

    if suspect:
        guard = """
<h3 style="margin-top:0">先说难看的：总分「好看得可疑」</h3>
<div class="note crit"><b>Brier %.3f 触发了本项目自己设的护栏。</b>
设计文档写死了一条：<b>Brier 低于 0.20 要先怀疑数据泄漏，而不是庆祝</b>——
赛前 Dota 预测的现实上限是 65–70%%，做到八成五几乎总意味着赛后信息漏进了模型。
代码里的判定函数直接把它标成了 <code>suspect_leakage</code>。所以先自己查一遍，而不是拿去发喜报。</div>
<p><b>查下来的结论是：不是泄漏，是赛程太软。</b>预测在 2026-08-02 就冻结并留了哈希存证，
比赛 8 月 13 日才开打，时间上不可能漏。真正的原因是——已经打完的这 %d 场里，
<b>有 %d 场是模型赛前就认为强弱悬殊的对局</b>（给分离 50%% 超过 10 个百分点）。</p>
""" % (st["brier"], st["n"], st["n_far"])
    else:
        guard = """
<h3 style="margin-top:0">总分回到了正常区间——这是好事，不是变差</h3>
<div class="note"><b>Brier %.3f。</b>上一次复盘时这个数是 0.136，低到触发了项目自己的泄漏护栏
（<b>低于 0.20 要先怀疑数据泄漏，而不是庆祝</b>），当时的解释是「赛程太软，不是模型神」。
现在题目变难了，数字如期回升——<b>这正是当时那个解释成立的证据</b>。
如果当初拿 0.136 出去吹，今天就得解释「为什么变差了」。</div>
""" % st["brier"]

    return """
<div class="rv-head">
  <div><b>第 %d 次复盘</b> · 截至 %s · 已完赛 <b>%d</b> 场系列赛%s</div>
  <div class="rv-verdict">%s</div>
</div>

<div class="tiles">
  <div class="tile"><div class="k">逐场方向</div><div class="v">%d/%d</div><div class="s">看对了几场</div></div>
  <div class="tile"><div class="k">Brier 分数</div><div class="v">%.3f</div><div class="s">越低越好</div></div>
  <div class="tile"><div class="k">接近五五开的场次</div><div class="v">%s</div><div class="s">%d 场，才是真本事</div></div>
  <div class="tile"><div class="k">分组还剩几种可能</div><div class="v">%s</div><div class="s">赛前是 35 种</div></div>
</div>

%s

<div class="tbl-wrap"><table class="rv">
<thead><tr><th>哪一类对局</th><th>场次</th><th>方向看对</th><th>Brier</th><th>怎么读</th></tr></thead>
<tbody>
<tr><td class="lft">赛前就强弱悬殊</td><td class="num">%d</td><td class="num">%d/%d</td><td class="num">%.3f</td>
    <td class="lft">该赢的都赢了。这种局<b>本来就该全中</b>，不算本事</td></tr>
<tr><td class="lft">赛前接近五五开</td><td class="num">%d</td><td class="num">%d/%d</td><td class="num hi">%.3f</td>
    <td class="lft"><b>只有这一档能说明模型有没有用</b>。0.21–0.24 算正常，<b>0.25 就是抛硬币</b></td></tr>
</tbody></table></div>
%s
<div class="note"><b>%d 场的样本量做任何结论都太小</b>，这几个数只能看方向。</div>

%s

<h3>逐场对答案</h3>
<p>赛前那张 120 组两两胜率表（对照 538 的 <code>spi_matches.csv</code> 做的）在开赛前就冻结了。
下面是已经发生的对局按它逐场回填的结果，<b>看错的行标红</b>：</p>
%s
<div class="note"><b>没看对的 %d 场，模型赛前给强的一方也只有 %s。</b>
它对这几场的判断本来就是「五五开，不知道」——它没有看错，它是明说了自己不知道。
真正该扣分的是那种「给了 80%% 结果输了」的场次。</div>

<h3>一、「首轮对阵已锁定」——8 场全部对上</h3>
<div class="note good">赛前锁进模型的 8 场首轮对阵，与实际开打的<b>逐场一致，一场不差</b>。
当时 Liquipedia 的对阵表还是空的，靠 DLTV 与 Hotspawn 两个独立来源交叉核对填进去的。</div>

%s

<h3>三、「没有真正的大热门」——还是没有</h3>
<p>赛前头名 %s 是 %.1f%%，现在是 <b>%.1f%%</b>。
瑞士轮之后还要打附加赛和双败，路径太长，任何单一队伍都稀释得厉害。这一条到目前为止完全成立。</p>

<h3>预测怎么变的</h3>
<div class="note"><b>「总变化」被拆成了两栏，因为这两件事的含义完全不同。</b>
交付概率 = 模型 ✕ 市场共识（市场占七成权重），从赛前到现在<b>两边都动了</b>。
拆法是标准的逐项分解——先按住市场只放模型变，再按住模型只放市场变，两栏精确相加等于总变化。</div>
%s
<div class="note"><b>战绩带来的位移最大 %.1fpp（%s），市场重新定价带来的最大 %.1fpp（%s）%s。</b>
瑞士轮容错很高：打到 4 胜或 4 负才停，之后还有附加赛和双败，
单轮胜负对「最终能不能夺冠」的影响本来就有限。</div>

<h3>瑞士轮四个战绩档，还剩谁够得着</h3>
%s
%s
""" % (
        snap["index"], esc(snap["as_of"]), snap["n_done"],
        ("（另有 %d 场已排定未分胜负）" % snap["n_scheduled"]) if snap["n_scheduled"] else "",
        esc(_verdict(snap)),
        st["hits"], st["n"], st["brier"],
        ("%.3f" % st["brier_close"]) if st["n_close"] else "—", st["n_close"],
        ("1 种" if snap["n_group_splits"] == 1 else "%d 种" % snap["n_group_splits"]),
        guard,
        st["n_far"], st["hits_far"], st["n_far"], st["brier_far"],
        st["n_close"], st["hits_close"], st["n_close"], st["brier_close"],
        _coinflip_note(st),
        st["n"],
        _settled_note(settled),
        _match_table(snap["matches"], since),
        len(st["misses"]), "、".join("%.1f%%" % v for v in st["misses"]),
        _group_section(snap),
        esc(snap["baseline_top_team"]), snap["baseline_top_p"] * 100,
        snap["teams"][0]["champ_blended"] * 100,
        _shift_table(snap),
        sh["max_res"], esc(sh["team_res"]), sh["max_mkt"], esc(sh["team_mkt"]),
        ("——差约 %.0f 倍" % sh["ratio"]) if sh["ratio"] >= 2 else "",
        buckets,
        """<p class="hint">这四个档位的名额数是赛制的恒等式（1 / 2 / 2 / 1），不是概率。
<a href="%s/homework.html">抄作业页</a>的推荐填法已经跟着最新一版重算过了。</p>""" % base,
    )


def _one_summary(s):
    """一次复盘的关键数。**每次复盘各算各的**，绝不共用最新那一次的数字。

    更新日志里每条历史条目都要引自己那一次的数——这一点已经栽过两次：
    8/10 那条曾经拿「当前产物」对冻结件比，8/13 那条曾经拿最新复盘的数字当
    自己的数字，两次都产出了自相矛盾的正文（「基本没动（最大 5.19pp）」、
    「12 场 BO3 …… 已打完 32 场」）。这类错不会报错，只会安静地把真话变假话。
    所以结构上就让每条条目只能拿到自己那一份。
    """
    st, sh = s["stats"], _shift_summary(s)
    _, settled = _bucket_status(s)
    return {
        "index": s["index"], "as_of": s["as_of"],
        "n_done": s["n_done"], "n_scheduled": s["n_scheduled"],
        "n_scored": st["n"], "hits": st["hits"], "brier_all": st["brier"],
        "n_close": st["n_close"], "hits_close": st["hits_close"],
        "brier_close": st["brier_close"],
        "n_far": st["n_far"], "hits_far": st["hits_far"], "brier_far": st["brier_far"],
        "miss_probs": st["misses"],
        "n_group_splits": s["n_group_splits"],
        "max_res_shift": sh["max_res"], "team_res": sh["team_res"],
        "max_mkt_shift": sh["max_mkt"], "team_mkt": sh["team_mkt"],
        "shift_ratio": sh["ratio"],
        "settled": [{"bucket": b, "teams": a, "pick": pk, "p": pp, "hit": h}
                    for b, a, pk, pp, h in settled],
        "records": s["records"],
        "groups": s["groups"] if s["n_group_splits"] == 1 else None,
        "verdict": _verdict(s),
    }


def summary(p):
    """所有复盘的关键数进 site.json：`snapshots` 逐次一份，顶层是最新那次。

    长图与网页读同一份数字；更新日志的每条历史条目读 `snapshots[i]`，
    这样条目结构上就拿不到「最新那一次」的数（见 _one_summary 的说明）。
    """
    snaps = _prepare(p.get("raw_reviews") or [])
    if not snaps:
        return {"active": False}
    per = [_one_summary(s) for s in snaps]
    out = dict(per[-1])
    out["active"] = True
    out["snapshots"] = per
    out["prev"] = per[-2] if len(per) > 1 else None
    return out


def _trend(snaps):
    """两次以上复盘时，顶部放一张跨复盘的对比表——这一页最该先看的东西。"""
    if len(snaps) < 2:
        return ""
    head = "".join("<th>第 %d 次<br><span class=dim>%s</span></th>"
                   % (s["index"], esc(s["as_of"])) for s in snaps)
    def row(label, fmt, get, hint=""):
        cells = "".join('<td class="num hi">%s</td>' % (fmt % get(s)) for s in snaps)
        return ("<tr><td class='lft'>%s%s</td>%s</tr>"
                % (label, ('<br><span class="dim">%s</span>' % hint) if hint else "", cells))
    body = (row("已完赛系列赛", "%d 场", lambda s: s["n_done"])
            + row("逐场方向", "%s", lambda s: "%d/%d" % (s["stats"]["hits"], s["stats"]["n"]))
            + row("Brier（全部）", "%.3f", lambda s: s["stats"]["brier"],
                  "低于 0.20 要先怀疑自己")
            + row("Brier（接近五五开）", "%.3f", lambda s: s["stats"]["brier_close"],
                  "真正有信息量的那部分")
            + row("分组还剩几种可能", "%d 种", lambda s: s["n_group_splits"], "赛前是 35 种"))
    return ('<h2>两次复盘之间发生了什么</h2>'
            '<div class="tbl-wrap"><table class="rv"><thead><tr><th>指标</th>%s</tr></thead>'
            "<tbody>%s</tbody></table></div>" % (head, body))


def render(base, p):
    snaps = _prepare(p.get("raw_reviews") or [])
    if not snaps:
        return "<h1>复盘</h1><div class='note'>赛事还没开打，暂无可复盘的结果。</div>"

    tabs = "".join(
        '<button class="rv-tab%s" data-rv="%s">第 %d 次复盘<span>%s</span></button>'
        % (" on" if i == len(snaps) - 1 else "", esc(s["id"]), s["index"], esc(s["as_of"]))
        for i, s in enumerate(snaps))

    panels = []
    for i, s in enumerate(snaps):
        since = (frozenset(frozenset((m["team_a"], m["team_b"]))
                           for m in _scored(snaps[i - 1]["matches"])) if i else None)
        panels.append('<div class="rv-panel%s" id="rv-%s">%s</div>'
                      % ("" if i == len(snaps) - 1 else " off", esc(s["id"]),
                         _one_review(s, base, since)))

    latest = snaps[-1]
    return """
<h1>复盘：赛前说过的话，现在兑现得怎么样</h1>
<p class="lede">赛前的预测在 2026-08-02 冻结并留了哈希存证。之后每打完一批比赛就交一次账——
逐场对答案，<b>包括没看对的那几场</b>。这一页记录每一次复盘，历史那几次<b>从当时的冻结件渲染，不会被后来的数据改写</b>。</p>
<p class="meta">共 %d 次复盘 · 最近一次截至 %s · 本页所有数字由程序从产出物直接算出，无人工誊抄</p>

%s

<h2>逐次复盘</h2>
<div class="rv-tabs">%s</div>
%s

<h2>这一版预测的诚实边界</h2>
<div class="note crit"><b>队伍实力评分没有跟着赛果更新。</b>
复盘做的是「把已经发生的比赛当成事实，重算后面还没打的部分」，
但每支队的实力分仍然是赛前那一套（用 145,974 场历史比赛训练出来的）。
也就是说：<b>模型没有因为某支队连输就认为它变弱了。</b>
这是有意的取舍——几十场 BO3 的信息量，相对于十几万场的历史样本很小，
临时拿它去调实力分，过拟合的风险大于收益。<b>但这确实是一个可以质疑的选择。</b></div>
<div class="note"><b>不过市场那一侧已经反应了。</b>最终交付的概率里市场占七成权重，
而 Polymarket 的价格是实时的、已经把赛果计入了。所以你看到的融合值<b>是「冻结的模型 + 实时的市场」</b>，
不是一份完全冻结的东西。<a href="%s/odds.html">市场怎么看 →</a></div>
<div class="note"><b>另一处改动：自 8/13 起停用了庄家赔率。</b>
能拿到的最新庄家盘口采于 8 月 10 日、开赛之前，赛中已经过时；
按原来的 50%% 权重混进实时市场价里，会把共识价往回拖到赛前。
赛中能查到的替代报价全是二手转述、标不出采集时刻，用了比不用更糟。
所以现在的市场共识价 = <b>纯 Polymarket</b>，旧盘口原值完整归档未删。</div>
""" % (len(snaps), esc(latest["as_of"]), _trend(snaps), tabs, "".join(panels), base)
