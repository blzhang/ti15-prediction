"""生成「市场怎么看」页：庄家赔率 ✕ Polymarket ✕ 模型，三方对照。

庄家赔率来自 model/market_odds.json（人工核实录入）；Polymarket 价来自
model/polymarket_odds.json（fetch_polymarket.py 抓取）。都带抓取时间。
庄家查不到的队留空——不编造。
"""
import json
import os


def _devig(odds):
    """去掉抽水：把小数赔率换成和为 1 的概率。"""
    raw = {k: 1.0 / v for k, v in odds.items() if v}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}, s


def render(base, pred, blended, market, pm):
    import html as _h

    def esc(s):
        return _h.escape(str(s), quote=True)

    od = market["decimal_odds"]
    priced = {k: v for k, v in od.items() if v}
    imp, overround = _devig(priced)
    mass = sum(blended[t] for t in priced)

    mids = {t: rec["mid"] for t, rec in pm["prices"].items()}
    pm_sum = sum(mids.values())
    pm_p = {t: v / pm_sum for t, v in mids.items()}

    def book_cells(t):
        if od.get(t):
            return ("<td class=num>%.2f</td><td class=num>%.1f%%</td>"
                    % (od[t], imp[t] * mass * 100))
        return "<td class=num>—</td><td class=num>—</td>"

    rows = "".join(
        "<tr><td>%s</td>%s<td class=num>%.1f%%</td><td class='num hi'>%.1f%%</td></tr>"
        % (esc(t), book_cells(t), pm_p[t] * 100, blended[t] * 100)
        for t in sorted(blended, key=lambda x: -blended[x]))

    return """
<h1>市场怎么看</h1>
<p class="lede">两个公开市场对 TI15 各队夺冠的定价——传统博彩网站的赔率，和
Polymarket 预测市场的合约价——换算成胜率之后，与我们模型的结果放在一起对比。</p>
<p class="meta">庄家赔率抓取于 %s · Polymarket 抓取于 %s · 仅供参考，本站不提供任何投注建议</p>

<div class="note"><b>覆盖范围。</b>
庄家的夺冠盘只核实到 <b>%d 支队</b>，查不到的留空——不做估算、不编数字。<br>
Polymarket 的冠军盘 <b>16 支队全有价</b>（盘内资金约 <b>%.0f 万美元</b>），
这也是把它接进来的主要原因。</div>

<h2>怎么读这两种价</h2>
<p>博彩网站给的是「小数赔率」，比如 <b>4.50</b> 意思是押 1 块钱赢了拿回 4.5 块。
把它倒过来（1 ÷ 4.50 = 22.2%%）就是市场认为的大致胜率。</p>
<div class="note"><b>但这次不能拿「倒数和」直接看抽水。</b><br>
完整 16 队的夺冠盘，把倒数加起来会因为抽水明显大于 1；
而这里庄家只开了 5 支队的盘，倒数和只有 <b>%.2f</b>——小于 1 是因为缺了 11 支队，说明不了抽水。<br>
所以下表「庄家胜率」的算法是：先在这 5 支队<b>内部</b>按比例去掉抽水，
再按它们在本站预测里合计的份额折算，保证和另外两列放在同一个口径下可比。</div>
<p>Polymarket 上买的是「某队夺冠」的合约：比如某队的合约卖 0.24 美元，
真夺冠了每份兑 1 美元——所以<b>价格本身就是市场估的概率</b>。
不过 16 份合约的价格加起来是 <b>%.2f</b>，同样带着溢价，
下表「Polymarket 胜率」也是按比例归一之后的数字。</p>

<h2>市场 vs 模型</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>庄家赔率</th><th>庄家胜率</th><th>Polymarket 胜率</th><th>本站预测</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">「本站预测」已经融合了市场信息：两个市场源先<b>等权</b>合成一个「市场共识价」
（庄家只开了 5 支队的盘，所以它只影响这 5 队内部的排序），
共识价再占<b>七成</b>权重与纯模型融合。所以最后一列和前面两列不会差太多——
这是有意的，不是巧合。</p>

<h2>一个反直觉的历史事实</h2>
<p>很多人觉得「跟着赔率买最稳」或者反过来「赔率总是错的」。两种说法都不太对。</p>
<p>我们查了 TI9 到 TI14 六届：<b>赛前赔率排第一的队，只夺冠过 1 次</b>；
冠军在赛前赔率里的排名，中位数是<b>第 4.5 名</b>。</p>
<div class="note"><b>但这不能说明赔率算错了。</b><br>
16 支队的比赛里，最被看好的那支大概也就两成半的夺冠机会。
那么六届里只赢一届，本来就是最正常不过的结果——概率上比抛硬币还平常。<br>
换句话说：<b>赔率其实挺准的，只是 TI 本来就没有稳的。</b>指望靠「反着买冷门」赚钱，
历史数据不支持这个想法。</div>

<h2>为什么我们的预测要参考市场</h2>
<p>做这套模型时查过学术文献，结论挺一致的：<b>想靠统计模型系统性打赢博彩公司，非常难。</b>
包含大量变量的模型在对比开盘者时并没有占到便宜，少数成功案例也都是很窄的口径，
而且有作者提到账号很快就被限制了。</p>
<p>所以我们的做法不是「跟市场对着干」，而是<b>把市场当成一个很强的参考</b>，
只在有明确理由的地方才偏离它——比如某支队换了人、而市场好像还没反应过来。</p>

<div class="note good"><b>想自己核对？</b>庄家赔率可以去公开博彩网站查证，
Polymarket 的价格在它官网的冠军盘页面就能看到，本站的快照文件也在
「数据与检索」页提供下载。价格是会变的，我们标了抓取时间；
到了开赛前如果有明显变化，我会更新这一页。</div>
""" % (esc(market.get("captured_utc", "—")), esc(pm.get("captured_utc", "—")),
       len(priced), (pm.get("event_liquidity") or 0) / 1e4,
       overround, pm_sum, rows)
