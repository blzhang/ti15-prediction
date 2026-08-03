"""生成「市场怎么看」页：转载公开博彩赔率，换算成胜率，与模型对照。

赔率数据来自 model/market_odds.json，人工核实后录入，每条带来源与抓取时间。
查不到的队伍留空——不编造。
"""
import json
import os


def _devig(odds):
    """去掉抽水：把小数赔率换成和为 1 的概率。"""
    raw = {k: 1.0 / v for k, v in odds.items() if v}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}, s


def render(base, pred, blended, market):
    import html as _h

    def esc(s):
        return _h.escape(str(s), quote=True)

    od = market["decimal_odds"]
    priced = {k: v for k, v in od.items() if v}
    imp, overround = _devig(priced)
    mass = sum(blended[t] for t in priced)

    rows = "".join(
        "<tr><td>%s</td><td class='num hi'>%.2f</td><td class=num>%.1f%%</td>"
        "<td class=num>%.1f%%</td><td class=num>%+.1f</td></tr>"
        % (esc(t), od[t], imp[t] * mass * 100, blended[t] * 100,
           (blended[t] - imp[t] * mass) * 100)
        for t in sorted(priced, key=lambda x: od[x]))

    unpriced = [t for t in blended if not od.get(t)]
    un = "".join(
        "<tr><td>%s</td><td class=num>—</td><td class=num>—</td><td class=num>%.1f%%</td>"
        "<td class=num>—</td></tr>" % (esc(t), blended[t] * 100)
        for t in sorted(unpriced, key=lambda x: -blended[x]))

    return """
<h1>市场怎么看</h1>
<p class="lede">公开博彩网站给 TI15 各队开出的夺冠赔率，换算成胜率之后，和我们模型的结果放在一起对比。</p>
<p class="meta">赔率抓取于 %s · 仅供参考，本站不提供任何投注建议</p>

<div class="note crit"><b>先讲清楚覆盖范围。</b>
目前只核实到 <b>%d 支队</b>的公开赔率，另外 %d 支查不到。<br>
查不到的我<b>留空，不做估算、不编数字</b>——宁可这张表不好看，也不放没有出处的东西。</div>

<h2>怎么读赔率</h2>
<p>博彩网站给的是「小数赔率」，比如 <b>4.50</b> 意思是押 1 块钱赢了拿回 4.5 块。
把它倒过来（1 ÷ 4.50 = 22.2%%）就是市场认为的大致胜率。</p>
<div class="note"><b>但直接倒过来算是不准的，因为里面含着庄家的抽水。</b><br>
把所有队的倒数加起来，如果市场是公平的应该正好等于 1。实际这次加起来是 <b>%.2f</b>——
多出来的部分就是庄家留给自己的利润空间。<br>
所以下表的「市场胜率」一列，是<b>去掉抽水之后</b>的数字，不是简单的倒数。
夺冠这种多路盘的抽水通常比单场比赛高得多，<b>不去抽水直接看，会觉得每支队都被高估了。</b></div>

<h2>市场 vs 模型</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>赔率</th><th>市场胜率</th><th>本站预测</th><th>差</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">「本站预测」这一列本身已经融合了市场信息（市场占七成权重），所以两列不会差太多——
这是有意的，不是巧合。</p>

<h3>没有公开赔率的队伍</h3>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>赔率</th><th>市场胜率</th><th>本站预测</th><th>差</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">这些队的预测值完全来自模型，没有掺市场信息。</p>

<h2>一个反直觉的历史事实</h2>
<p>很多人觉得「跟着赔率买最稳」或者反过来「赔率总是错的」。两种说法都不太对。</p>
<p>我们查了 TI9 到 TI14 六届：<b>赛前赔率排第一的队，只夺冠过 1 次</b>；
冠军在赛前赔率里的排名，中位数是<b>第 4.5 名</b>。</p>
<div class="note"><b>但这不能说明赔率算错了。</b><br>
16 支队的比赛里，最被看好的那支大概也就两成半的夺冠机会。
那么六届里只赢一届，本来就是最正常不过的结果——概率上比抛硬币还平常。<br>
换句话说：<b>赔率其实挺准的，只是 TI 本来就没有稳的。</b>指望靠「反着买冷门」赚钱，
历史数据不支持这个想法。</div>

<h2>为什么我们的预测要参考赔率</h2>
<p>做这套模型时查过学术文献，结论挺一致的：<b>想靠统计模型系统性打赢博彩公司，非常难。</b>
包含大量变量的模型在对比开盘者时并没有占到便宜，少数成功案例也都是很窄的口径，
而且有作者提到账号很快就被限制了。</p>
<p>所以我们的做法不是「跟市场对着干」，而是<b>把市场当成一个很强的参考</b>，
只在有明确理由的地方才偏离它——比如某支队换了人、而市场好像还没反应过来。</p>

<div class="note good"><b>想自己核对？</b>这张表的每个赔率都可以去公开博彩网站查证。
赔率是会变的，我们标了抓取时间；到了开赛前如果有明显变化，我会更新这一页。</div>
""" % (esc(market.get("captured_utc", "—")), len(priced), len(unpriced),
       overround, rows, un)
