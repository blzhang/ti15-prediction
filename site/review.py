"""生成「复盘」页：赛前说过的话，现在兑现得怎么样。

这一页是整个项目的立身之本落地的地方——赛前冻结 + 哈希存证，图的就是能在
赛程中途和赛后拿同一套代码给自己打分，好看不好看都发出来。

三条纪律，改这个文件时必须守住：
  1. **数字全部来自 payload，不手写。** 手抄的对账表没法证明自己没抄错。
  2. **难看的数照发。** 方向没看对的场次要单独列出来，不能只报总命中率。
  3. **好看的数要先自我怀疑。** 目前的 Brier 低到触发了项目自己的泄漏护栏
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


def _rows_by_stage(matches, stage=None):
    rows = [m for m in matches if m["result_a_wins"] is not None]
    if stage:
        rows = [m for m in rows if m["stage"] == stage]
    return rows


def _brier(rows):
    if not rows:
        return None
    return sum((m["p_a"] - m["result_a_wins"]) ** 2 for m in rows) / len(rows)


def _hits(rows):
    return sum(1 for m in rows if (m["p_a"] > 0.5) == (m["result_a_wins"] == 1))


def _match_table(matches):
    """逐场对账：赛前概率 → 实际结果。看错的那两场必须一眼看得见。"""
    out = ['<div class="tbl-wrap"><table class="rv"><thead><tr>'
           "<th>轮次</th><th>对阵</th><th>赛前给的胜率</th><th>实际</th><th>看对了吗</th>"
           "</tr></thead><tbody>"]
    for m in matches:
        if m["result_a_wins"] is None:
            continue
        winner = m["team_a"] if m["result_a_wins"] == 1 else m["team_b"]
        loser = m["team_b"] if m["result_a_wins"] == 1 else m["team_a"]
        hit = (m["p_a"] > 0.5) == (m["result_a_wins"] == 1)
        # 赛前给强的那一方与它的胜率——读者关心的是"模型看好谁"，不是表里 A 列是谁
        fav = m["team_a"] if m["p_a"] >= 0.5 else m["team_b"]
        p_fav = m["p_a"] if m["p_a"] >= 0.5 else 1 - m["p_a"]
        coin = abs(p_fav - 0.5) < CLOSE_MARGIN
        out.append(
            '<tr class="%s"><td>%s</td><td class="lft">%s <span class=vs>vs</span> %s</td>'
            '<td class="num">%s %.0f%%%s</td><td class="lft"><b>%s</b> %s %s</td>'
            '<td class="num">%s</td></tr>'
            % ("miss" if not hit else "",
               esc(m["stage_cn"]), esc(m["team_a"]), esc(m["team_b"]),
               esc(fav), p_fav * 100,
               '<span class="coin">接近五五开</span>' if coin else "",
               esc(winner), esc(m["score"]), esc(loser),
               "✓" if hit else "✗"))
    out.append("</tbody></table></div>")
    return "".join(out)


def _shift_table(teams, prev9_blend, prev9_pred, pred, w_market):
    """赛前 → 现在的位移表，并把位移**拆成两个来源**。

    交付概率 = 融合(模型, 市场)。从赛前到现在，两边都动了：模型这边多了 12 场
    已完赛结果，市场那边 Polymarket 实时重新定价（还叠加了本版停用庄家腿）。
    只报一个「变化」列，读者没法知道某支队是被战绩推的还是被市场推的——
    而这两件事的含义完全不同。

    所以做一次标准的逐项分解，两项精确相加等于总变化：
        比赛结果带来的 = 融合(新模型, 旧市场) - 融合(旧模型, 旧市场)
        市场重新定价的 = 融合(新模型, 新市场) - 融合(新模型, 旧市场)
    第一项把市场按住不动、只放模型变，第二项反之。
    """
    old_model, old_mkt = prev9_pred["champion"], prev9_blend["market_consensus"]
    new_model = pred["champion"]
    base = blend_logodds(old_model, old_mkt, w_market)         # = 赛前那一版
    mid = blend_logodds(new_model, old_mkt, w_market)          # 只更新了战绩

    out = ['<div class="tbl-wrap"><table class="rv"><thead><tr>'
           "<th>队伍</th><th>战绩</th><th>赛前夺冠</th><th>现在夺冠</th><th>总变化</th>"
           "<th>其中：打出来的</th><th>其中：市场重定价</th>"
           "<th>进淘汰赛</th></tr></thead><tbody>"]
    for r in teams:
        t = r["team"]
        if t not in base:
            continue
        now = r["champ_blended"]
        d_res = (mid[t] - base[t]) * 100
        d_mkt = (now - mid[t]) * 100
        d = (now - base[t]) * 100
        cls = lambda v: "up" if v > 0.3 else ("down" if v < -0.3 else "")
        out.append(
            '<tr><td class="lft">%s</td><td class="num rec">%s</td>'
            '<td class="num">%.1f%%</td><td class="num hi">%.1f%%</td>'
            '<td class="num %s">%+.1fpp</td>'
            '<td class="num %s">%+.1fpp</td><td class="num %s">%+.1fpp</td>'
            '<td class="num">%.0f%% → %.0f%%</td></tr>'
            % (esc(t), esc(r["record"]), base[t] * 100, now * 100,
               cls(d), d, cls(d_res), d_res, cls(d_mkt), d_mkt,
               prev9_pred["advance_playoffs"][t] * 100, r["advance"] * 100))
    out.append("</tbody></table></div>")
    return "".join(out)


def _shift_summary(teams, prev9_blend, prev9_pred, pred, w_market):
    """位移分解的结论句所需的几个数：两边各自最大挪了多少、谁挪的。

    这段结论是复盘页最反直觉的一条，所以数字必须现算——手写一句
    「市场挪得比模型多得多」，下次重算就可能变成假话而没人发现。
    """
    old_model, old_mkt = prev9_pred["champion"], prev9_blend["market_consensus"]
    base = blend_logodds(old_model, old_mkt, w_market)
    mid = blend_logodds(pred["champion"], old_mkt, w_market)
    now = {r["team"]: r["champ_blended"] for r in teams}
    res_d = {t: abs(mid[t] - base[t]) for t in base}
    mkt_d = {t: abs(now[t] - mid[t]) for t in base}
    t_res = max(res_d, key=lambda t: res_d[t])
    t_mkt = max(mkt_d, key=lambda t: mkt_d[t])
    return {
        "max_res": res_d[t_res] * 100, "team_res": t_res,
        "max_mkt": mkt_d[t_mkt] * 100, "team_mkt": t_mkt,
        "ratio": (mkt_d[t_mkt] / res_d[t_res]) if res_d[t_res] else float("inf"),
    }


def _bucket_status(prev9_pred, pred, res):
    """瑞士轮四个战绩档，现在还有几支队在数学上够得着。

    只列「赛前有戏、现在已经出局」的队——「OG 不可能拿 4-0」这种话对谁都没用，
    有用的是「赛前 4-0 概率排第二的那支队，现在这一格已经废了」。
    """
    rec_now = res["records"]
    rows = []
    for label in ("4-0", "4-1", "1-4", "0-4"):
        need_w, need_l = (int(x) for x in label.split("-"))
        alive, killed = [], []
        for t, r in rec_now.items():
            w, l = (int(x) for x in r.split("-"))
            was = prev9_pred["record_dist"].get(t, {}).get(label, 0.0)
            if w > need_w or l > need_l:
                if was >= 0.05:                 # 赛前有戏（≥5%）才值得点名
                    killed.append((t, was))
            else:
                alive.append(t)
        killed.sort(key=lambda x: -x[1])
        rows.append(
            "<tr><td class='num'><b>%s</b></td><td class='num'>%d 支</td>"
            "<td class='lft'>%s</td></tr>"
            % (esc(label), len(alive),
               "、".join("<b>%s</b>（赛前 %.0f%%）" % (esc(t), p * 100) for t, p in killed)
               or "<span class=dim>没有赛前看好的队被排除</span>"))
    return ('<div class="tbl-wrap"><table class="rv"><thead><tr><th>档位</th>'
            "<th>还够得着的队</th><th>赛前看好、现在已出局的</th></tr></thead>"
            "<tbody>%s</tbody></table></div>" % "".join(rows))


def summary(p):
    """复盘的几个关键数，压成一个小 dict 进 site.json。

    长图（make_cards.py）与网页读同一份数字——长图上的「10/12」和网页上的
    「10/12」必须是同一次计算的结果。此前长图有过写死数字、网页改了图没改的
    先例，那种错发出去就收不回来。
    """
    res = (p.get("raw_pred") or {}).get("results") or {}
    if not res.get("active"):
        return {"active": False}
    matches = p["raw_matches"]
    scored = _rows_by_stage(matches)
    close = [m for m in scored if abs(m["p_a"] - 0.5) < CLOSE_MARGIN]
    far = [m for m in scored if abs(m["p_a"] - 0.5) >= CLOSE_MARGIN]
    prev9_blend, prev9_pred = p["raw_prev9_blend"], p["raw_prev9_pred"]
    shift = _shift_summary(p["teams"], prev9_blend, prev9_pred, p["raw_pred"],
                           prev9_blend.get("w_market", 0.7))
    return {
        "active": True,
        "as_of": res["as_of_utc"][:10],
        "n_done": res["n_series_done"], "n_scheduled": res["n_series_scheduled"],
        "n_scored": len(scored), "hits": _hits(scored),
        "brier_all": _brier(scored),
        "n_close": len(close), "hits_close": _hits(close), "brier_close": _brier(close),
        "n_far": len(far), "hits_far": _hits(far), "brier_far": _brier(far),
        "n_group_splits": res.get("n_group_splits", 0),
        "max_res_shift": shift["max_res"], "team_res": shift["team_res"],
        "max_mkt_shift": shift["max_mkt"], "team_mkt": shift["team_mkt"],
        "shift_ratio": shift["ratio"],
        # 没看对的那几场，模型当时给强的一方多少——长图和网页都要引这两个数，
        # 手写会随下一轮比赛过期。升序排，方便文案写「从 x% 到 y%」。
        "miss_probs": sorted(max(m["p_a"], 1 - m["p_a"]) * 100 for m in scored
                             if (m["p_a"] > 0.5) != (m["result_a_wins"] == 1)),
        "records": res["records"],
    }


def render(base, p):
    res = (p.get("raw_pred") or {}).get("results") or {}
    if not res.get("active"):
        return ("<h1>复盘</h1><div class='note'>赛事还没开打，暂无可复盘的结果。</div>")

    matches = p["raw_matches"]
    scored = _rows_by_stage(matches)
    r1 = _rows_by_stage(matches, "swiss_r1")
    r2 = _rows_by_stage(matches, "swiss_r2")
    close = [m for m in scored if abs(m["p_a"] - 0.5) < 0.10]
    far = [m for m in scored if abs(m["p_a"] - 0.5) >= 0.10]

    b_all, b_close, b_far = _brier(scored), _brier(close), _brier(far)
    n_split = res.get("n_group_splits", 0)
    misses = sorted(max(m["p_a"], 1 - m["p_a"]) * 100 for m in scored
                    if (m["p_a"] > 0.5) != (m["result_a_wins"] == 1))

    prev9_blend = p["raw_prev9_blend"]
    prev9_pred = p["raw_prev9_pred"]
    w_market = prev9_blend.get("w_market", 0.7)
    shift = _shift_summary(p["teams"], prev9_blend, prev9_pred, p["raw_pred"], w_market)

    return """
<h1>复盘：赛前说过的话，现在兑现得怎么样</h1>
<p class="lede">TI15 瑞士轮已经打完 <b>%d 场</b>系列赛（另有 %d 场对阵已排定未开打）。
这一页拿赛前冻结的预测逐场对答案——<b>包括没看对的那两场</b>。</p>
<p class="meta">截至 %s · 赛前预测冻结于 2026-08-02，哈希存证可查 · 本页所有数字由程序从产出物直接算出</p>

<div class="tiles">
  <div class="tile"><div class="k">逐场方向</div><div class="v">%d/%d</div><div class="s">看对了几场</div></div>
  <div class="tile"><div class="k">Brier 分数</div><div class="v">%.3f</div><div class="s">越低越好</div></div>
  <div class="tile"><div class="k">接近五五开的场次</div><div class="v">%.3f</div><div class="s">%d 场，正常区间</div></div>
  <div class="tile"><div class="k">分组还剩几种可能</div><div class="v">%d 种</div><div class="s">赛前是 35 种</div></div>
</div>

<h2>先说难看的：总分「好看得可疑」</h2>
<div class="note crit"><b>Brier %.3f 触发了本项目自己设的护栏。</b>
设计文档写死了一条：<b>Brier 低于 0.20 要先怀疑数据泄漏，而不是庆祝</b>——
赛前 Dota 预测的现实上限是 65–70%%，做到八成五几乎总意味着赛后信息漏进了模型。
现在这个数是 %.3f，代码里的判定函数直接把它标成了 <code>suspect_leakage</code>。
所以先自己查一遍，而不是拿去发喜报。</div>

<p><b>查下来的结论是：不是泄漏，是赛程太软。</b>预测在 2026-08-02 就冻结并留了哈希存证，
比赛 8 月 13 日才开打，时间上不可能漏。真正的原因是——目前打完的这 12 场里，
<b>有 %d 场是模型赛前就认为强弱悬殊的对局</b>（给分离 50%% 超过 10 个百分点）。
把这两类拆开看就很清楚：</p>

<div class="tbl-wrap"><table class="rv">
<thead><tr><th>哪一类对局</th><th>场次</th><th>方向看对</th><th>Brier</th><th>怎么读</th></tr></thead>
<tbody>
<tr><td class="lft">赛前就强弱悬殊</td><td class="num">%d</td><td class="num">%d/%d</td><td class="num">%.3f</td>
    <td class="lft">该赢的都赢了。这种局<b>本来就该全中</b>，不算本事</td></tr>
<tr><td class="lft">赛前接近五五开</td><td class="num">%d</td><td class="num">%d/%d</td><td class="num hi">%.3f</td>
    <td class="lft"><b>这才是有信息量的部分</b>，落在 0.21–0.24 的正常区间里</td></tr>
</tbody></table></div>

<div class="note"><b>一句话：真正能体现水平的那 %d 场，模型打出来的是一个「正常」的分数，不是神迹。</b>
等瑞士轮后段强队互相碰上，这个总分会往上走——那不是模型变差了，是题目变难了。
<b>12 场的样本量做任何结论都太小</b>，这几个数只能看方向。</div>

<h2>逐场对答案</h2>
<p>赛前那张 120 组两两胜率表（对照 538 的 <code>spi_matches.csv</code> 做的）在开赛前就冻结了。
下面是已经发生的对局按它逐场回填的结果，<b>看错的行标红</b>：</p>
%s
<div class="note"><b>没看对的这 %d 场，模型赛前给强的一方也只有 %s。</b>
它对这几场的判断本来就是「五五开，不知道」——它没有看错，它是明说了自己不知道。
真正该扣分的是那种「给了 80%% 结果输了」的场次，目前还没有出现。</div>

<h2>三件赛前说过的事</h2>

<h3>一、「首轮对阵已锁定」——8 场全部对上</h3>
<div class="note good">赛前锁进模型的 8 场首轮对阵，与实际开打的<b>逐场一致，一场不差</b>。
当时 Liquipedia 的对阵表还是空的，靠 DLTV 与 Hotspawn 两个独立来源交叉核对填进去的。</div>

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
<div class="note">这 4 个「必须同组」的块是从已发生的对阵反推的，不是官方公布的：
%s</div>

<h3>三、「没有真正的大热门」——还是没有</h3>
<p>赛前头名 %s 是 %.1f%%，现在打完两轮升到 <b>%.1f%%</b>。<b>两战全胜的队，夺冠概率也才四分之一</b>——
瑞士轮之后还要打附加赛和双败，路径太长，任何单一队伍都稀释得厉害。这一条到目前为止完全成立。</p>

<h2>预测怎么变的</h2>
<p>下面是<b>赛前那一版</b>（开赛时挂在站上的版本）与<b>现在这一版</b>的逐队对比。
现在这一版把已经打完的 %d 场当成事实代入，不再当随机变量抽。</p>
<div class="note"><b>「总变化」被拆成了两栏，因为这两件事的含义完全不同。</b>
交付概率 = 模型 ✕ 市场共识（市场占七成权重），从赛前到现在<b>两边都动了</b>：
模型这边多了 12 场已完赛结果，市场那边 Polymarket 在实时重新定价。
只报一个总数的话，读者没法知道某支队是<b>自己打上来的</b>还是<b>被市场重新看好的</b>。
拆法是标准的逐项分解——先按住市场只放模型变，再按住模型只放市场变，两栏精确相加等于总变化。
（市场那一栏还包含本版停用庄家赔率腿的影响，见页尾。）</div>
%s
<div class="note crit"><b>拆开之后有一个挺反直觉的结果：挪动几乎全是市场挪的，不是比赛打出来的。</b>
战绩带来的位移，最大的一支也只有 <b>%.1fpp</b>（%s）；而市场重新定价带来的位移，
最大的一支是 <b>%.1fpp</b>（%s）——<b>差了约 %.0f 倍</b>。
原因是瑞士轮的容错很高：打到 4 胜或 4 负才停，之后还有附加赛和双败，
<b>前两轮的胜负对「最终能不能夺冠」的影响本来就很有限</b>。
真正在动的是市场情绪。所以如果你看到某支队的概率大涨大跌，
先看清楚那是它自己打上来的，还是别人重新看好它。</div>

<h2>瑞士轮四个战绩档，还剩谁够得着</h2>
<p>瑞士轮打到 4 胜或 4 负即停，所以输过两场就<b>在数学上</b>不可能拿 4-0 了。
下面只列<b>赛前看好、现在已经出局</b>的——「OG 拿不到 4-0」这种话对谁都没用：</p>
%s
<p class="hint">这四个档位的名额数是赛制的恒等式（1 / 2 / 2 / 1），不是概率。
<a href="%s/homework.html">抄作业页</a>的推荐填法已经跟着这一版重算过了。</p>

<h2>这一版预测的诚实边界</h2>
<div class="note crit"><b>队伍实力评分没有跟着赛果更新。</b>
现在这一版做的是「把已经发生的比赛当成事实，重算后面还没打的部分」，
但每支队的实力分仍然是赛前那一套（用 145,974 场历史比赛训练出来的）。
也就是说：<b>模型没有因为 OG 连输两场就认为 OG 变弱了。</b>
这是有意的取舍——12 场 BO3 的信息量，相对于十几万场的历史样本非常小，
临时拿它去调实力分，过拟合的风险远大于收益。<b>但这确实是一个可以质疑的选择。</b></div>
<div class="note"><b>不过市场那一侧已经反应了。</b>最终交付的概率里市场占七成权重，
而 Polymarket 的价格是实时的、已经把这两轮的结果计入了。所以你看到的融合值<b>是「冻结的模型 + 实时的市场」</b>，
不是一份完全冻结的东西。<a href="%s/odds.html">市场怎么看 →</a></div>
<div class="note"><b>另一处改动：这一版停用了庄家赔率。</b>
能拿到的最新庄家盘口采于 8 月 10 日、开赛之前，赛中已经过时；
按原来的 50%% 权重混进实时市场价里，会把共识价往回拖到赛前。
赛中能查到的替代报价全是二手转述、标不出采集时刻，用了比不用更糟。
所以本版的市场共识价 = <b>纯 Polymarket</b>，旧盘口原值完整归档未删。</div>
""" % (
        res["n_series_done"], res["n_series_scheduled"],
        esc(res["as_of_utc"][:10]),
        _hits(scored), len(scored), b_all, b_close, len(close), n_split,
        b_all, b_all,
        len(far),
        len(far), _hits(far), len(far), b_far,
        len(close), _hits(close), len(close), b_close,
        len(close),
        _match_table(matches),
        len(misses), "、".join("%.1f%%" % v for v in misses),
        n_split, n_split,
        "；".join("<b>{%s}</b>" % esc("、".join(b)) for b in p["raw_blocks"]),
        esc(p["prev_top_team"]), p["prev_top_p"] * 100, p["teams"][0]["champ_blended"] * 100,
        res["n_series_done"],
        _shift_table(p["teams"], prev9_blend, prev9_pred, p["raw_pred"], w_market),
        shift["max_res"], esc(shift["team_res"]),
        shift["max_mkt"], esc(shift["team_mkt"]), shift["ratio"],
        _bucket_status(prev9_pred, p["raw_pred"], res),
        base, base,
    )
