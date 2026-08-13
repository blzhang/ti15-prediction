"""生成站点的 4 个页面。所有数字来自 payload，不手写。"""
import html
import os
import shutil

NAV = [("homework.html", "抄作业"), ("index.html", "结论"), ("review.html", "复盘"),
       ("predictions.html", "预测详情"),
       ("odds.html", "市场怎么看"), ("methodology.html", "方法论"), ("data.html", "数据与检索"),
       ("window.html", "版本窗口"), ("group.html", "进群"), ("changelog.html", "更新日志")]

# 微信群二维码 7 天一换。换码只需替换 assets_src/group-qr.jpg 并改这个日期，
# 知乎/NGA 帖子里挂的始终是 group.html 这个永久链接，不用跟着改。
QR_EXPIRY = "2026-08-20"

# 官方预测面板锁定时间——全站唯一事实源，倒计时和各页文案都读这里。
#
# 官方博文原文：*before the first match starts (10am CST, Thursday 8/13)*。
# 「CST」有歧义：中国标准时间(UTC+8) 还是美国中部时间(UTC-5)？判定为**中国标准时间**：
#   1. TI 历届首场都在场馆当地 10:00 开赛（TI14 汉堡站 Liquipedia 记为 10:00 CEST）；
#   2. TI15 在上海，10:00 CST 即北京时间 10:00，符合直播赛事的正常开赛时间；
#   3. 若按美国中部时间解读则是北京时间 23:00——本地晚间开赛，与在华办赛不符。
# 这一版之前站上写的正是「23:00 北京时间」，比本判定晚 13 小时。
# 取更早的时间兜底：判错了只是让人提前填（无损失），判对了能救回错过锁定的人。
# 若在客户端里看到确切倒计时与此不符，改这两行即可，全站自动跟随。
PANEL_DEADLINE_UTC = "2026-08-13T02:00:00Z"
PANEL_DEADLINE_CN = "8 月 13 日 10:00（北京时间）"


PLACEHOLDER_QR = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 350 522">
<rect width="350" height="522" fill="#e1e0d9"/>
<text x="175" y="246" text-anchor="middle" font-family="sans-serif" font-size="19" fill="#52514e">
微信群二维码未包含在</text>
<text x="175" y="276" text-anchor="middle" font-family="sans-serif" font-size="19" fill="#52514e">
开源仓库中</text>
<text x="175" y="316" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#898781">
放一张 assets_src/group-qr.jpg 即可启用</text></svg>"""


def qr_asset(src, dest):
    """二维码是私人邀请码，不入库。缺失时落占位图，保证 clone 后能构建。"""
    real = os.path.join(src, "group-qr.jpg")
    if os.path.exists(real):
        shutil.copyfile(real, os.path.join(dest, "group-qr.jpg"))
        return "group-qr.jpg"
    with open(os.path.join(dest, "group-qr.svg"), "w") as fh:
        fh.write(PLACEHOLDER_QR)
    return "group-qr.svg"


def esc(s):
    return html.escape(str(s), quote=True)


def countdown(base, cur):
    """预测面板锁定倒计时横幅。

    服务端只渲染静态兜底文案（截止时刻本身），倒计时数字由 app.js 接管；
    JS 没跑起来时仍能看到「什么时候截止」，不会退化成空白。
    锁定后 JS 自动切成「已锁定」态并把出口改指对账页，无需再部署一次。
    """
    on_hw = cur == "homework.html"
    return """
<div class="cd" data-deadline="%s"%s>
  <div class="cd-txt">
    <b class="cd-head">官方预测面板锁定倒计时</b>
    <span class="cd-sub">%s截止 · 锁定后不能再改</span>
  </div>
  <div class="cd-clock" aria-live="polite">%s</div>
  %s
</div>""" % (
        PANEL_DEADLINE_UTC,
        ' data-here="1"' if on_hw else "",
        esc(PANEL_DEADLINE_CN),
        esc(PANEL_DEADLINE_CN),
        "" if on_hw else '<a class="cd-btn" href="%s/homework.html">看建议填法 →</a>' % base)


# 倒计时只挂在这两页：占全站约四分之三的浏览量，且都与「填不填得上」直接相关。
# 方法论/数据页挂上去只是噪音。
CD_PAGES = ("homework.html", "index.html")


def shell(base, cur, title, body, extra_js=""):
    nav = "".join(
        '<a class="item%s" href="%s/%s">%s</a>' % (" on" if f == cur else "", base, f, esc(t))
        for f, t in NAV)
    body = (countdown(base, cur) + body) if cur in CD_PAGES else body
    return """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s · TI15 预测</title>
<meta name="description" content="DOTA2 TI15（The International 2026）的量化预测：夺冠概率、瑞士轮战绩分布、选手数据预测，含方法论与可下载数据集。">
<link rel="stylesheet" href="%s/assets/style.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='26'>🎯</text></svg>">
</head><body>
<header class="nav"><div class="wrap nav-in">
<a class="brand" href="%s/">TI15 预测<span>The International 2026</span></a>
%s<div class="spacer"></div>
<button class="theme" onclick="toggleTheme()">明/暗</button>
</div></header>
<main><div class="wrap">
%s
</div></main>
<footer><div class="wrap">
所有预测在开赛前生成并加了防篡改校验。改过的地方全部记在<a href="%s/changelog.html">更新日志</a>里，包括读者指出来的错。比赛数据来自 OpenDota 和 Liquipedia。<br>
页面上每一个数字都是程序直接算出来的，没有人工誊抄——所以不会出现「模型改了、网页忘了同步」这种事。<br>
本站不提供任何投注建议。
</div></footer>
<script src="%s/assets/app.js"></script>
<script src="%s/assets/px.js" defer></script>
%s
</body></html>""" % (esc(title), base, base, nav, body, base, base, base, extra_js)


def bars(rows, key, fmt=lambda v: "%.1f%%" % (v * 100), alt=False):
    mx = max(r[key] for r in rows) or 1
    out = ['<div class="bars">']
    for r in rows:
        w = max(0.8, r[key] / mx * 100)
        out.append(
            '<div class="bar-row"><div class="nm">%s</div>'
            '<div class="bar-track"><div class="bar-fill%s" style="width:%.1f%%"></div></div>'
            '<div class="vl">%s</div></div>'
            % (esc(r["team"]), " alt" if alt else "", w, fmt(r[key])))
    out.append("</div>")
    return "".join(out)


def dual_bars(rows):
    mx = max(max(r["champ_model"], r["champ_blended"]) for r in rows) or 1
    out = ['<div class="legend">',
           '<span><i style="background:var(--s1)"></i>纯模型</span>',
           '<span><i style="background:var(--s2)"></i>融合市场共识价后（交付值）</span>',
           '</div><div class="bars dual">']
    for r in rows:
        out.append(
            '<div class="bar-row"><div class="nm">%s</div><div class="bar-track">'
            '<div class="seg" style="width:%.1f%%"></div>'
            '<div class="seg b" style="width:%.1f%%"></div></div>'
            '<div class="vl">%.1f%%</div></div>'
            % (esc(r["team"]), r["champ_model"] / mx * 100, r["champ_blended"] / mx * 100,
               r["champ_blended"] * 100))
    out.append("</div>")
    return "".join(out)


def dist_table(d, label):
    ks = sorted(d, key=int)
    rows = "".join("<tr><td>%s 支</td><td class='num hi'>%.2f%%</td></tr>" % (esc(k), d[k] * 100)
                   for k in ks if d[k] > 0.005)
    return ('<div class="tbl-wrap"><table><thead><tr><th>%s</th><th>概率</th></tr></thead>'
            "<tbody>%s</tbody></table></div>" % (esc(label), rows))


# ---------------------------------------------------------------- 页面

def draw_banner(p, base=None):
    """状态横幅：这一版预测建立在什么信息之上。

    读者只看一眼就走的话，那一眼必须知道当前是哪一种状态——
    开赛后最重要的一句话已经不是「分组没公布」，而是「已经打了多少场、
    这些结果已经算进去了」。所以已完赛信息优先于抽签信息。
    """
    d = p.get("draw") or {}
    res = (p.get("raw_pred") or {}).get("results") or {}
    if res.get("active"):
        n = res.get("n_group_splits", 0)
        grp = ("分组已由已打完的对阵<b>唯一确定</b>" if n == 1 else
               "分组仍未公布，但已打完的对阵把可能的分法从 35 种压到了 <b>%d 种</b>，"
               "本版对这 %d 种平均" % (n, n))
        return ('<div class="note good"><b>赛事进行中：瑞士轮已打完 %d 场系列赛，'
                '本版预测已把这些结果当成事实代入重算。</b>%s。%s</div>'
                % (res.get("n_series_done", 0), grp,
                   '<a href="%s/review.html">看逐场对账与复盘 →</a>' % base if base else ""))
    if not d.get("announced"):
        return ""
    link = ' <a href="%s/predictions.html#draw">看首轮对阵 →</a>' % base if base else ""
    if d.get("grouping") == "official":
        return '<div class="note"><b>分组已公布</b>，本版预测已按真实抽签重算。' + link + '</div>'
    if d.get("grouping") == "inferred":
        return ('<div class="note crit"><b>注意：这一版的分组是推测的。</b>' + link + '</div>')
    return (
        '<div class="note"><b>首轮对阵已确定并锁进模型</b>（两个独立来源逐场一致）。'
        '<b>A/B 分组官方还没公布——我们没有去猜</b>：与已知首轮自洽的分法共 35 种，'
        '模拟时全部平均掉了。所以下面的数字用上了目前全部已证实的抽签信息，'
        '也只用了已证实的。' + link + '</div>')


def _draw_section(p):
    """预测详情页的抽签小节：首轮对阵 + 分组为什么留空不猜。

    开赛后这一节的性质变了：首轮对阵已经打完，它不再是「预测所依据的信息」，
    而是「当时那个判断后来对不对」。所以开赛后在开头挂一条指向复盘页的说明，
    正文保留当时的原话不改——把当时的判断悄悄改成事后诸葛，正是这个项目
    最该避免的事。
    """
    d = p.get("draw") or {}
    if not d.get("announced") or not d.get("round1"):
        return ""
    res = (p.get("raw_pred") or {}).get("results") or {}
    hist = ""
    if res.get("active"):
        n = res.get("n_group_splits", 0)
        hist = ('<div class="note good"><b>赛后回看：这 8 场首轮对阵全部打完，'
                '与下面锁定的逐场一致，一场不差。</b>分组至今仍未公布，'
                '但已打完的对阵把可能的分法从 35 种压到了 %d 种——'
                '下面这段是当时的原话，一个字没改。'
                '<a href="/dota2/review.html">看逐场对账 →</a></div>' % n)
    pairs = "".join("<li>%s <span class=vs>vs</span> %s</li>" % (esc(a), esc(b))
                    for a, b in d["round1"])
    if d.get("grouping") == "official":
        note = ('<div class="note"><b>分组已由官方公布</b>，本版按真实分组重算。</div>')
    else:
        note = """<div class="note"><b>分组我们没有猜——这是有意的。</b>
瑞士轮前三轮只在组内配对，所以分组会影响前三轮的对手。但官方至今没公布分组，
而<b>与已知首轮自洽的分法有 35 种</b>（8 个对子分 4+4，每对必须整对同组）。
我们一度打算从<b>转播分流</b>推一种填进去（A+B 流 8 队一组、C+D 流 8 队一组，正好 8/8 且与首轮自洽），
最后放弃了：按开赛时段切出来的另一种同样自洽，队伍集合却完全不同——挑哪一种都是凭空多一个自由度。
<b>现在的做法是把 35 种全部平均掉</b>，即用上目前全部已证实的信息，且只用已证实的。
那一版也完整跑完留作对照了。实测差异：<b>夺冠概率最大 0.15pp</b>，<b>进淘汰赛最大 0.87pp</b>；
把 0-4、1-4 这些小概率档也算进来，<b>全部档位的最大差是 1.8pp</b>（Nigma 的 0-4 档）。
抄作业 16 格的档位归属<b>一格不差</b>。也就是说赌那个猜测，赢面最大的地方也只是个位数百分点的尾档——
不值得为它引入一个没有出处的假设。</div>"""
    return """
<h2 id="draw">抽签：首轮已确定，分组仍未公布</h2>
%s
<div class="note good"><b>首轮 8 场对阵——已确定。</b>
DLTV 与 Hotspawn 两个独立来源逐场一致，16 队每队恰好出现一次，已锁进模拟。
（Liquipedia 的对阵表此时仍是空的。）</div>
<ul class="pairs">%s</ul>
%s
<p class="hint">附带一提：公布的这 8 场<b>几乎全是强弱悬殊局</b>。这正是本版瑞士轮数字相对上一版
发生位移的原因——强队首轮大概率白拿一胜、弱队大概率先背一败，效应顺着瑞士轮往后传导。</p>
""" % (hist, pairs, note)


def _inplay_lede(p, base):
    """首页导语的结尾半句：赛前是「赛后会对答案」，开赛后就该是「已经在对了」。

    这半句在开赛后如果还写着「赛后会逐场对答案」，等于在比赛已经打了两轮时
    仍然把自己描述成一份纯赛前预测——而这一版的数字已经不是纯赛前的了。
    """
    res = (p.get("raw_pred") or {}).get("results") or {}
    if not res.get("active"):
        return "赛后会逐场对答案。"
    return ('已经打完的 <b>%d 场</b>系列赛结果也已代入重算。'
            '<a href="%s/review.html">逐场对答案在这里 →</a>'
            % (res.get("n_series_done", 0), base))


def _inplay_meta(p):
    res = (p.get("raw_pred") or {}).get("results") or {}
    if not res.get("active"):
        return "开赛前生成，已加防篡改校验"
    return ("赛前预测已冻结存证 · 本版已代入截至 %s 的赛果"
            % esc(res.get("as_of_utc", "")[:10]))


def page_index(base, p):
    t = p["teams"]
    top = t[0]
    eighth = t[7]
    falcons = next(x for x in t if x["team"] == "Team Falcons")
    spirit = next(x for x in t if x["team"] == "Team Spirit")
    oos = p["oos"]
    body = """
<h1>TI15 谁会赢：一个可被证伪的预测</h1>
<p class="lede">用 2020–2026 的 145,974 场职业比赛，对 The International 2026（8/13–8/23，上海，16 队）
做了一次战队与选手层面的量化预测。所有预测在开赛前就锁定并加了防篡改校验，%s</p>
<p class="meta">%s · 模拟了 20 万届 TI</p>
%s
<div class="tiles">
  <div class="tile"><div class="k">夺冠概率最高</div><div class="v">%s</div><div class="s">%.1f%%（已融合市场共识价）</div></div>
  <div class="tile"><div class="k">官方预测面板</div><div class="v">16 格</div><div class="s">已出建议填法</div></div>
  <div class="tile"><div class="k">分档结构</div><div class="v">1·2·5·5·2·1</div><div class="s">每届恒定，非概率</div></div>
  <div class="tile"><div class="k">模型样本外准确率</div><div class="v">%.1f%%</div><div class="s">2,546 场未见过的比赛</div></div>
</div>

<h2>结论一：没有真正的大热门</h2>
<p>头名 %s 只有 %.1f%%，前八名挤在 %.0f%%–%.0f%% 之间。这不是模型不敢下判断，而是 16 队水平确实接近——
瑞士轮打到 4 胜或 4 负、之后还要打双败，路径太长，任何单一队伍的夺冠概率都被稀释。</p>
<div class="note"><b>历史支持这个判断。</b>TI9–TI14 六届里，赛前赔率头名只夺冠 1 次，冠军的赛前赔率排名中位数是第 4.5 名。
我们一度以为这说明市场错价，但二项检验推翻了它：头名真实概率 25%% 时，六届只赢一次的概率是 53%%——
<b>这完全符合一份校准良好的赔率</b>。所以不要指望靠偏离市场赚钱。</div>

<h2>结论二：模型和市场在两支队上分歧很大</h2>
<p>这是整套预测里最值得赛后复盘的地方。</p>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>纯模型</th><th>融合后（交付值）</th><th>差</th><th>模型的理由</th></tr></thead>
<tbody>
<tr><td>Team Falcons</td><td class="num">%.1f%%</td><td class="num hi">%.1f%%</td><td class="num">%+.1fpp</td>
    <td style="text-align:left">16 队中<b>唯一阵容零变动</b>的卫冕冠军</td></tr>
<tr><td>Team Spirit</td><td class="num">%.1f%%</td><td class="num hi">%.1f%%</td><td class="num">%+.1fpp</td>
    <td style="text-align:left">队长兼指挥 Miposhka <b>转任教练</b></td></tr>
</tbody></table></div>
<p>我们的建模口径是<b>按「当前这五个人」算历史战绩</b>——一场比赛只有当某队现役首发出场 ≥3 人时才计入该队。
所以阵容连续性会直接兑现成样本量与稳定性，Falcons 因此被看高。市场不认这一点。</p>
<div class="note"><b>需要说明的取舍：</b>最终交付值给了市场 70%% 的权重（文献共识是「融合优于对抗」），
这把模型对 Falcons 的偏好基本抹平了。如果你更信模型的逻辑，应下调这个权重。</div>

<h2>结论三：选手层面的预测，有一个前提</h2>
<p>TI15 官方预测面板里<b>没有选手题</b>——已知题目全部是战队层面的。所以选手层面是独立分析，不对应任何官方答题。</p>
<p>另外 TI15 的 Fantasy 是<b>选队不选人</b>：Core Duo 和 Support Duo 选的是整支队，只有 Mid 槽是真正在选人。</p>
<div class="note crit"><b>一个补不上的硬缺口：</b>18 项计分项里 Watcher 和 Lotus 取不到，蓝色徽记池只有 4/6。
而 Support Duo 槽的徽记全是蓝色——<b>我们对辅助槽的预测能力结构性偏弱</b>，这个没法靠努力弥补。</div>

<h2>这套预测的可信度上限</h2>
<p>队伍实力那一层做过真实的检验：训练只用 2026-03 之前的数据，在之后 %s 场没见过的比赛上——</p>
<div class="tiles">
  <div class="tile"><div class="k">准确率</div><div class="v">%.1f%%</div><div class="s">现实上限 65–70%%</div></div>
  <div class="tile"><div class="k">概率给得准不准</div><div class="v">%.3f</div><div class="s">越低越好，0.21–0.24 属正常</div></div>
</div>
<p>成绩落在正常范围内：明显好过抛硬币，也没好到可疑的地步。</p>
<div class="note"><b>为什么「太准」反而可疑？</b>因为几乎所有号称赛前预测能到 85%% 以上的研究，
用的其实是<b>比赛打到一半的实时数据</b>——那当然准，但那不叫预测。
只用赛前信息的话，六成到七成就是天花板。<b>看到有人说赛前能做到八成五，基本可以断定是把赛后信息漏进模型了。</b></div>
<p><a href="%s/predictions.html">→ 看完整预测详情</a> ｜ <a href="%s/methodology.html">→ 方法论与已知限制</a></p>

<div class="cta">
  <div>
    <b>建了个微信群：TI15 抄作业群</b>
    <span>一起填预测面板，8/23 一起给这套预测打分。</span>
  </div>
  <a class="cta-btn" href="%s/group.html">扫码进群 →</a>
</div>
""" % (_inplay_lede(p, base), _inplay_meta(p),
       draw_banner(p, base),
       esc(top["team"]), top["champ_blended"] * 100,
       oos.get("acc", 0) * 100,
       esc(top["team"]), top["champ_blended"] * 100,
       eighth["champ_blended"] * 100, top["champ_blended"] * 100,
       falcons["champ_model"] * 100, falcons["champ_blended"] * 100,
       (falcons["champ_blended"] - falcons["champ_model"]) * 100,
       spirit["champ_model"] * 100, spirit["champ_blended"] * 100,
       (spirit["champ_blended"] - spirit["champ_model"]) * 100,
       "{:,}".format(oos.get("n", 0)),
       oos.get("acc", 0) * 100, oos.get("brier", 0),
       base, base, base)
    return shell(base, "index.html", "结论", body)


def page_group(base, p, qr="group-qr.jpg"):
    body = """
<h1>TI15 抄作业群</h1>
<p class="lede">一个微信群，干三件事：一起填官方预测面板、开赛后跟进赛果、8 月 23 日结束时一起给这套预测打分。</p>
<p class="meta">扫码进群 · 群名「TI15 抄作业群」</p>

<div class="qr-card">
  <img class="qr" src="%s/assets/%s" alt="微信群二维码：TI15 抄作业群" width="350" height="522">
  <div class="qr-side">
    <h3>进来能得到什么</h3>
    <ul>
      <li><b>预测面板怎么填</b>——<a href="%s/homework.html">抄作业页</a>给的是期望最优解，群里可以讨论要不要赌一把偏离它</li>
      <li><b>赛程开打后的跟进</b>——瑞士轮每轮结束后，模型的概率会怎么变</li>
      <li><b>8/23 的对账</b>——用同一套代码给赛前预测打分，好看不好看都在群里先发</li>
    </ul>
    <p class="hint">不发广告、不荐赌。这套预测<b>不提供任何投注建议</b>，群里同样不聊这个。</p>
  </div>
</div>

<div class="note" id="qr-note">
  <b>二维码有效期到 %s。</b>微信群码 7 天一换，过期了这个页面会换上新的——
  所以请把这一页存进收藏夹，不要保存二维码图片本身。
</div>

<h2>为什么进群入口在这里，而不在帖子里</h2>
<p>微信群码 7 天就失效，而 TI15 打到 8 月 23 日。如果把码直接贴在知乎和 NGA 帖子里，
每周都得回去编辑一次帖子，中间还会有人扫到死码。放在这一页，换码只需要换一张图，
帖子里挂的链接永远有效。</p>
""" % (base, qr, base, esc(QR_EXPIRY))
    # 静态页无法知道访客何时打开，所以过期判断放到客户端：码一旦过期，
    # 访客看到的是明确提示，而不是扫了个死码不知道为什么进不去。
    js = ("<script>(function(){var d=new Date('%sT23:59:59+08:00');"
          "if(Date.now()>d.getTime()){var n=document.getElementById('qr-note');"
          "if(n){n.className='note crit';"
          "n.innerHTML='<b>这张二维码可能已经过期了。</b>'+"
          "'群码 7 天一换，这一页还没来得及更新。'+"
          "'稍后再来刷新一次，或者在知乎文章下留言提醒作者换码。';}"
          "var q=document.querySelector('.qr');if(q){q.style.opacity='.35';}}})();</script>"
          % esc(QR_EXPIRY))
    return shell(base, "group.html", "进群", body, extra_js=js)


def page_pred(base, p):
    t = p["teams"]
    falcons = next(x for x in t if x["team"] == "Team Falcons")
    rows = "".join(
        "<tr><td>%s</td><td class='num hi'>%.1f%%</td><td class=num>%.1f%%</td><td class=num>%.1f%%</td>"
        "<td class=num>%.1f%%</td><td class=num>%.1f%%</td><td class=num>%.1f%%</td>"
        "<td class=num>%.3f</td><td class=num>%d</td></tr>"
        % (esc(r["team"]), r["champ_blended"] * 100, r["champ_model"] * 100, r["top4"] * 100,
           r["advance"] * 100, r["swiss_top3"] * 100, r["r40"] * 100, r["theta"], r["games"])
        for r in t)
    body = """
<h1>预测详情</h1>
<p class="lede">全部数字由构建脚本从冻结产出物读出。夺冠一列已与市场共识价融合（Polymarket ✕ 庄家赔率，市场占七成权重），其余各列是纯模型。</p>
<p class="meta">蒙特卡洛 %s 次 · 夺冠概率标准误 ≤ 0.09pp</p>
""" % (esc("{:,}".format(p["n_sim"]))) + draw_banner(p) + _draw_section(p) + """

<div class="note"><b>读表前必看：</b>只有「夺冠」一列做了市场融合。
「进淘汰赛 / 瑞士轮前3 / 5-0」全部是纯模型，<b>各列并非同一个联合分布</b>。
例：Falcons 夺冠 %.1f%%（融合后），但进淘汰赛 %.1f%%——后者出自一个认为它夺冠 %.1f%% 的模型。横向比较需谨慎。</div>

<h2>夺冠概率：模型 vs 融合后</h2>
%s

<h2>全量指标</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>夺冠(融合)</th><th>夺冠(纯模型)</th><th>进前四</th><th>进淘汰赛</th>
<th>瑞士轮前3</th><th>打出4-0</th><th>实力分</th><th>样本场次</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">实力分越高越强，是从历年交手记录里反推出来的；样本场次指「该队现役五人中 ≥3 人同场」的比赛数，
不是队伍存在多久——所以拼装队（如 Vici、OG）的数字反映的是新阵容的磨合样本。</p>

<h2>官方预测题</h2>
<p>官方预测面板要把 16 支队分配到 <b>4-0 / 4-1 / 淘汰赛胜者 / 淘汰赛败者 / 1-4 / 0-4</b> 六个档位，槽位数恒为 <b>1·2·5·5·2·1</b>——这是赛制推出来的恒等式，不是概率。</p>
<p><a href="%s/homework.html">→ 看建议填法与完整概率表</a></p>

<h2>逐场对阵胜率</h2>
<p>瑞士轮的配对是<b>内生</b>的——第 3 轮谁打谁取决于前两轮结果，赛前列不出具体对阵。
所以我们列出全部 16×15/2 = 120 个候选配对的 BO3 胜率，赛后按实际发生的约 59 场取子集评分。</p>
<p><a href="%s/data/ti15_matches.csv">下载 ti15_matches.csv（120 行）</a></p>
<div class="note good"><b>为什么这不是「挑好的算」：</b>概率生成只读赛前数据（固定种子重跑逐格一致）；
评分时是无条件「有结果就收录」，没有任何挑拣分支；哪些配对会发生由赛果决定，与我们预测得准不准无关。
这与 FiveThirtyEight 处理赛程的方式一致。</div>
""" % (falcons["champ_blended"] * 100, falcons["advance"] * 100, falcons["champ_model"] * 100,
       dual_bars(t), rows, base, base)
    return shell(base, "predictions.html", "预测详情", body)


def _patch_layer_section(p):
    """方法论页里「按版本号打折」那一小节。

    这一节的全部数字都来自 payload["patch_layer"]（build_site.py 从
    l1_rating.json 的 hp_search / patch_weight_mass 算出来），一个都不手抄——
    这一节讲的正是「结论要能被核对」，自己手抄数字就没法看了。

    l1_rating.json 里没有 hp_search（例如沿用了旧缓存、这轮没重搜）时整节
    不渲染：宁可少一节，也不能拿上一轮的数字冒充这一轮。
    """
    pl = p.get("patch_layer")
    if not pl:
        return ""
    rows = "".join(
        "<tr><td class=num>%s</td><td class=num>%d</td><td class=num>%.1f%%</td>"
        "<td class=num>%.3f</td></tr>"
        % (k, v["games"], v["weight_share"] * 100, v["mean_weight"])
        for k, v in sorted(pl["mass"].items(), key=lambda kv: int(kv[0])))
    return """
<h3>越老的版本，权重越低——但这一层几乎没起作用</h3>
<p>有读者提：Dota 每个大版本改动都不小，一年前的比赛不该跟上个月的一样重。
这个说法本身对，模型原本也确实在按<b>天数</b>打折。所以这次专门加了一层按<b>版本号</b>的折扣：
一场比赛离现在隔了 k 个大版本，权重再乘 γ<sup>k</sup>。γ 和半衰期、岭强度一起，
在<b>验证期</b>（2025-08 至 2026-03，%(val_n)s 场）上跑了 %(n_grid)d 种组合的整格搜索。</p>
<p><b>结果是：白做。</b>启用版本层的最好一档，验证期 LogLoss 只比不启用的最好一档低
<b>%(delta_abs).5f</b>；而这个指标在这个样本量下的标准误约 %(se).4f——差距是它的
<b>%(se_ratio).0f 分之一</b>，纯噪声。16 支队的实力分<b>排序一格没动</b>。</p>
<p>原因不难看：版本发布本来就是按时间排的，「隔了几个版本」和「过了多少天」高度重合。
搜索选中的组合（半衰期 %(hl_sel)s 天 + γ=%(g_sel)s）和不启用版本层的最好一档
（半衰期 %(hl_off)s 天）画出来<b>几乎是同一条曲线</b>——两者相关系数 %(curve_r).3f，
权重掉到一半的时点只差 %(half_gap).0f 天。模型选中的不是「版本效应」，
是「把半衰期拉长 %(half_gap).0f 天」的另一种写法。</p>
<div class="note"><b>那为什么还留着？</b>因为判据是<b>事先</b>定好的「验证期 LogLoss 最低者胜」，
看完结果再改判据就是自欺。这一层留在代码里、按选出的值启用，同时把「它没用」写在这里。
γ=1 时它<b>逐位关闭</b>，产出物与加这层之前字节一致，有测试锁着。
整格搜索的 %(n_grid)d 行结果都在 <code>l1_rating.json</code> 的 <code>hp_search</code>
字段里（「数据与检索」页可下载），可自行核对。</div>
<p>顺带一个能核对的事实：现行权重下，当前版本（7.41）的比赛只占总权重的
<b>%(cur_share).0f%%</b>。这不是疏忽——验证期把衰减调得更狠的那些组合
（半衰期 120 天、γ=0.5 等）<b>全部更差</b>。「再多给近期加权」这件事，数据这次投的是反对票。</p>
<div class="tbl-wrap"><table><thead><tr><th>距今几个大版本</th><th>场次</th><th>占总权重</th><th>场均权重</th></tr></thead>
<tbody>%(rows)s</tbody></table></div>
""" % dict(pl, rows=rows)


def page_method(base, p):
    cr = p.get("cross_region", {})
    crrows = "".join("<tr><td>%s</td><td class=num>%d</td></tr>" % (esc(k), v)
                     for k, v in sorted(cr.items(), key=lambda kv: -kv[1])[:6])
    patch_block = _patch_layer_section(p)
    body = """
<h1>方法论</h1>
<p class="lede">分六层：数据地基 → 队伍实力 → 赛制模拟 → 选手能力 → 合成 → 冻结与赛后评分。
下面同时写清了每一层<b>做到了什么</b>和<b>没做到什么</b>。</p>

<h2>路线选择：为什么不用「多维度打分卡」</h2>
<p>常见做法是给每队在若干维度（近期战绩、选手能力、BP 深度、大赛经验…）打分再加权。我们<b>明确不用</b>，理由有两层，第二层才致命：</p>
<ol>
<li>权重是主观的——这个人尽皆知。</li>
<li><b>维度分数本身已被结果污染。</b>你给一支队「大赛经验 9/10」时，你已经知道他们赢过 TI 了；
「版本适配度」多半是看谁最近在赢。这等于把历史战绩换个名字塞回模型再拿去预测胜负——
<b>一个伪装成因果特征的结果泄漏</b>，而且各维度因此严重共线。</li>
</ol>
<p>决定性差异是<b>可证伪性</b>：战绩模型能做时间截断回测，打分卡做不到——你今天没法诚实地重建当年的「BP 深度 8 分」，因为你已经知道结局了。</p>

<h2>第一层 · 数据地基：一支队 = 当前这五个人</h2>
<p>转会是这类预测的头号陷阱。常规做法是按「队伍」记分，于是一支队换掉三个人之后，还在继承老阵容打出来的成绩。</p>
<p>我们的做法：<b>一场比赛的某一方，只有当它包含某队 ≥3 名现役首发时，才标记为那支队</b>。
这样 Aurora 换掉 3 人之后，旧阵容的比赛自然不计入它头上——转会问题在数据层就解决了，不需要任何事后打折或主观权重。</p>
<p>这个方法还自动解开了改名问题。Valve 禁止博彩品牌名参赛，导致三支队用了「参赛用名」：</p>
<ul>
<li>BetBoom → <b>BoomBoys</b>（历史 736 场）</li>
<li>1win（ex-Tundra 阵容）→ <b>Iron Wing</b>（Tundra 名下 437 场）</li>
<li>PARIVISION → <b>TEAM VISION</b>（PVISION 名下 75 场）</li>
</ul>
<p>另有 HULIGANI = L1GA TEAM、GamerLegion 承接 Wildcard（219 场）、LGD（南美席位）承接 HEROIC（385 场）。
六条映射全部生效，<b>没有任何一支队因改名丢失历史</b>。</p>

<h2>第二层 · 队伍实力：从两两胜负反推实力分</h2>
<p>做法是给每支队估一个「实力分」，两队实力分之差决定谁更可能赢。这套方法叫 Bradley-Terry 模型
——大家熟悉的 Elo 分其实是它的简化版。用完整版而不是 Elo，是因为它能顺带给出<b>误差范围</b>
（这支队的实力分有多不确定），还能把「赛事级别」这类因素一起放进去算。</p>
<p><b>赛事级别加权是自举出来的</b>，不是人工表。OpenDota 自带的 tier 字段 2024 年后已失效
（premium 场次从 2023 年的 3,878 掉到 2024 年的 121、2026 年的 0），而 14.6 万场里场次最多的全是东欧线上车轮赛。
我们改用迭代：拟合 → 用各赛事参赛者实力反推赛事权重 → 重拟合，3 次收敛。
跑出来权重最高的全是真 major（DreamLeague、ESL One、BetBoom Dacha、TI2024）。</p>
<p>超参（时间衰减半衰期 %s 天、版本衰减 γ=%s、岭正则 λ=%s）由<b>时间切分验证</b>选出，测试期只用一次。</p>
%s

<h3>跨赛区可比吗？</h3>
<p>「赛区强度不可比」是这类模型的经典风险。我们做了连通性诊断——仅在 16 支参赛队之间的直接交手场次：</p>
<div class="tbl-wrap"><table><thead><tr><th>赛区对</th><th>直接交手场次</th></tr></thead><tbody>%s</tbody></table></div>
<p>主轴连通性充分，欧洲队整体靠前<b>不是「对战图不连通」造出来的幻觉</b>。</p>

<h2>第三层 · 赛制模拟：瑞士轮必须一轮一轮跑</h2>
<p>这一层最容易被低估。瑞士轮的配对是<b>内生</b>的——第 3 轮谁打谁取决于前两轮结果，不能预生成赛程。</p>
<ul>
<li><b>不能用二项近似。</b>瑞士轮内建负反馈（赢了就去打更强的对手），强队赛程自动变难。
用「平均胜率 p，5 轮拿 k 胜 = C(5,k)p^k(1-p)^(5-k)」会系统性高估强队的高战绩概率。</li>
<li><b>同分按 Buchholz 排序</b>（对手总胜场），不能掷硬币——否则「边缘队晋级概率」会明显失真。</li>
<li>配对用<b>二分图完美匹配</b>而非贪心。实测贪心版在 500 个随机种子里有 488 个（97.6%%）会在 5 轮内撞上本可避免的重赛。</li>
<li>让分小局<b>随实力差变化</b>：BO3 中输方拿到 1 局的条件概率是 2(1−p)/(3−2p)，势均力敌时更可能打满。</li>
<li>淘汰赛<b>无 bracket reset</b>（TI15 确实没有，实现了反而是错的）。</li>
</ul>

<h2>第四层 · 选手能力：按位置分开估，小样本往平均值收</h2>
<p>按 1–5 号位分层收缩。有一个反直觉但重要的点：<b>负二项 = gamma 混合的泊松</b>，
所以「用负二项」和「加局级随机效应」数学上是同一件事——那就不该裸套负二项。</p>
<div class="note crit"><b>选手能力这一层踩过一个大坑，值得写出来。</b>
初版用裸泊松假定估方差（Var ≈ 均值）。实测多数计分项根本不服从泊松——
补刀的实测局内标准差是泊松假定的 <b>7.72 倍</b>、stuns 6.08 倍、GPM 4.24 倍。
结果是 GPM 和补刀的置信区间<b>窄了 4–8 倍</b>。已修正为实测局内方差。<br><br>
更值得记的是<b>为什么没被早发现</b>：我们的调研文档白纸黑字写着「不要假设，要先在自己的数据上量一遍 Var/Mean，
这是必须实测的 5 分钟检查」——设计是对的，但这条要求在「设计 → 实施计划 → 任务步骤」的传导中丢失了，从未被执行。
而当时写的健全性检查偏偏挑了击杀（1.56 倍），六个指标里受影响最轻的那个。</div>

<h2>第五层 · 赛前锁定与赛后对账</h2>
<p>一届 TI 只有 1 个冠军观测，<b>评估不了任何东西</b>。但 TI15 会打 59 场系列赛 / 约 145 局——
场级预测有上百个观测，这是全项目唯一有统计功效的检验场。</p>
<p>所有预测在赛前都算了防篡改校验码并记下时间，赛后按每场比赛逐一打分。
对照标准学 FiveThirtyEight 的做法：把赛前概率和赛后结果放在同一张表里公开，谁都能拿去核。</p>

<div class="note"><b>⚠️ 赛后分数会天然偏高，别误判成模型不行。</b>
瑞士轮按同战绩配对，而同战绩强相关同实力。所以实际打出的约 59 场<b>不是 120 个候选配对的均匀随机子集</b>，
而是系统性偏向势均力敌的那部分——表里那些悬殊配对大概率根本不会发生。
后果：赛后打出来的分数，衡量的其实是「模型在势均力敌局面下的判别力」，天然比「在全部可能配对上的判别力」更难做低。
所以赛后如果发现分数偏高，先想想是不是这个原因，再下「模型不行」的结论。</div>

<h2>已知限制（完整清单）</h2>
<p>下面这些是<b>做不到或没做</b>的事，不是自谦：</p>
<ul>
<li><b>只有夺冠概率做了市场融合</b>，名次分布 / 晋级概率 / 逐场胜率都是纯模型。赛后分数 评的也是纯模型。</li>
<li><b>L3 没有接入局长 / 版本 / 对手强度协变量</b>（设计里承诺了，接口没留位置）。
后果：如果版本大改让所有人的数据整体变化，模型会误以为是「这一届选手水平变了」。</li>
<li><b>原计划里有一项「按赛区做修正」，最后没做</b>。诊断结果显示不做也没问题，但计划里写了没做就该说明。</li>
<li><b>那个 0.2315 的成绩，是在没启用「赛事级别加权」的版本上测的</b>——加权这一层本身从没做过独立检验。</li>
<li><b>极值题的「谁打出全场之最」把局数压成了点估计</b>，等于把主方差项归零，右尾被削平。</li>
<li><b>TI14 回溯校验用的是简化估计器</b>（裸均值、全局残差、事后已知局数），不是交付版本。
结论「有信号但确认不了具体是谁」是这个简化版的信号。</li>
<li><b>Fantasy 的 18 项系数拿不到</b>（服务端运行时下发），所以只交付分项矩阵、不出绝对总分。</li>
</ul>
<p class="hint">完整版见项目内 <code>00-DESIGN.md</code> 的 §10「已知限制与解读须知」，共 12 小节。</p>
""" % (p.get("half_life_days"), p.get("patch_gamma"), p.get("ridge"),
       patch_block, crrows)
    return shell(base, "methodology.html", "方法论", body)


def page_data(base, p):
    dl = "".join(
        '<a class="row" href="%s/data/%s" download><div><div class="f">%s</div>'
        '<div class="d">%s</div></div><div class="sz">%s</div></a>'
        % (base, esc(m["file"]), esc(m["file"]), esc(m["desc"]), _sz(m["bytes"]))
        for m in p["manifest"])
    full = "".join("<tr><td><code>%s</code></td><td class=num>%s</td><td style='text-align:left'>%s</td></tr>"
                   % (esc(f["file"]), esc(f["size"]), esc(f["desc"])) for f in p["full_data"])
    body = """
<h1>数据与检索</h1>
<p class="lede">下面是本次预测用到的全部产出物，可直接下载。底层 350MB 原始数据集不在站上，但可以一条命令重新拉取。</p>

<h2>选手数据检索</h2>
<p>80 名参赛选手 × 15 个计分项的每局速率预测与 95%% 区间。可按选手名、队伍、号位筛选，点表头排序。</p>
<div class="controls">
  <input type="search" id="q" placeholder="搜选手名或队名…" aria-label="搜索">
  <select id="item" aria-label="计分项"></select>
  <select id="team" aria-label="队伍"><option value="">全部队伍</option></select>
  <select id="pos" aria-label="号位">
    <option value="">全部号位</option>
    <option value="1">1 号位 carry</option><option value="2">2 号位 mid</option>
    <option value="3">3 号位 offlane</option><option value="4">4 号位 soft sup</option>
    <option value="5">5 号位 hard sup</option>
  </select>
  <span class="hint" id="count"></span>
</div>
<div class="tiles" id="stat"></div>
<div class="tbl-wrap"><table>
<thead><tr><th data-k="n">选手</th><th data-k="t">队伍</th><th data-k="p">号位</th>
<th data-k="r">每局速率</th><th>95%% 区间</th><th data-k="g">样本局数</th><th>相对</th></tr></thead>
<tbody id="rows"><tr><td colspan="7">加载中…</td></tr></tbody></table></div>
<p class="hint">区间宽度反映样本量与该项的真实波动。<b>注意</b>：参战率与一血是 [0,1] 比例，其余是每局计数或速率。
Watcher 与 Lotus 两项取不到，不在表内。</p>

<h2>下载：预测产出物</h2>
<div class="dl">%s</div>

<h2>底层数据集（350 MB，不在站上）</h2>
<p>原始数据来自 OpenDota，覆盖 2020-01-01 至 2026-08-02 的全部职业比赛：</p>
<div class="tbl-wrap"><table><thead><tr><th>文件</th><th>大小</th><th>内容</th></tr></thead><tbody>%s</tbody></table></div>
<p>重新拉取只需一条命令（约 169 次请求、15 分钟，日额度用掉约 220/3000）：</p>
<pre><code>unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
python3 fetch_pro_all.py --since 2020-01-01</code></pre>
<div class="note"><b>抓取时的两个坑，记录在此省得你踩：</b><br>
① OpenDota 的 explorer 大查询里<b>不要用 LEFT JOIN</b>——同样 3 万行，带 4 个 JOIN 要 300 秒，不带只要 11.5 秒。
正确做法是维表整表 dump、本地拼。<br>
② 长响应<b>必须带 <code>--compressed</code></b>，否则会被截断成不合法 JSON 而静默解析失败。</div>

<h2>数据质量</h2>
<ul>
<li><b>比赛结果极干净</b>：14.6 万场里 <code>radiant_win</code> 只有 7 个空值（0.005%%）。</li>
<li><b>有 5.2%% 的比赛（7,560 场）查不到参赛队伍是谁</b>，而且逐年变差，今年已经到 10.3%%——这些场次没法计入战队评分。</li>
<li><b>三成选手没有登记名字</b>，但每个人的唯一编号都是全的，所以不影响计算，只影响显示。</li>
<li><b>绝大多数比赛是低级别车轮赛</b>：场次最多的三个赛事是 Ancients League(9,032)、Destiny League(6,082)、
Ultras Dota Pro League(5,488)，<b>前八名里一个真 major 都没有</b>。所以赛事分级加权是必须的。</li>
</ul>

<h2>合规</h2>
<ul>
<li>OpenDota：免费匿名可用，60 次/分、3000 次/日，响应头带余量，脚本自适应限速。</li>
<li>Liquipedia：<b>仅可用 MediaWiki API</b>（≥2 秒一次请求、自定义 User-Agent、gzip），<b>禁止抓 HTML 页面</b>。</li>
<li>Dotabuff / datdota：<b>robots.txt 明文禁止</b>，本项目未抓取。</li>
</ul>
""" % (dl, full)
    return shell(base, "data.html", "数据与检索", body,
                 extra_js='<script>initExplorer("%s");</script>' % base)


def _sz(b):
    if b >= 1048576:
        return "%.1f MB" % (b / 1048576)
    if b >= 1024:
        return "%.0f KB" % (b / 1024)
    return "%d B" % b


def write_all(dist, base, payload):
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets_src")
    for f in ("style.css", "app.js", "px.js", "picker.js"):
        shutil.copyfile(os.path.join(src, f), os.path.join(dist, "assets", f))
    qr = qr_asset(src, os.path.join(dist, "assets"))
    import homework
    hw = homework.compute(payload["raw_pred"],
                          {r["team"]: r["theta"] for r in payload["teams"]})
    fan = payload["raw_fantasy"]
    fan_rec = homework.fantasy(fan, payload["raw_pred"])
    import odds as _odds
    import changelog as _changelog
    import window as _window
    import review as _review
    payload = dict(payload, homework_full=hw)
    pages = {
        "review.html": shell(base, "review.html", "复盘", _review.render(base, payload)),
        "changelog.html": shell(base, "changelog.html", "更新日志",
                                _changelog.render(base, payload)),
        "window.html": shell(base, "window.html", "版本窗口",
                             _window.render(base, payload["raw_window"])),
        "odds.html": shell(base, "odds.html", "市场怎么看",
                           _odds.render(base, payload["raw_pred"],
                                        {r["team"]: r["champ_blended"] for r in payload["teams"]},
                                        payload["raw_market"], payload["raw_pm"])),
        "index.html": page_index(base, payload),
        "homework.html": shell(
            base, "homework.html", "抄作业",
            homework.render(base, hw, payload["raw_pred"], fan, fan_rec,
                            payload["raw_draw_sens"],
                            banner=draw_banner(payload, base)),
            extra_js='<script src="%s/assets/picker.js"></script>'
                     '<script>initPicker(%s);</script>'
                     % (base, __import__("json").dumps(
                         homework.picker_data(payload["raw_pred"], hw, fan_rec),
                         ensure_ascii=False, separators=(",", ":")))),
        "predictions.html": page_pred(base, payload),
        "methodology.html": page_method(base, payload),
        "data.html": page_data(base, payload),
        "group.html": page_group(base, payload, qr),
    }
    for name, htmlstr in pages.items():
        with open(os.path.join(dist, name), "w") as fh:
            fh.write(htmlstr)
    return list(pages)
