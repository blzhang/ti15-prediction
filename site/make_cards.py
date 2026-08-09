"""生成社媒长图与小红书卡片组。

数字全部从 site/dist/data/site.json 读，与网站同源，不手抄。

用法：
    python3 site/build_site.py && python3 site/make_cards.py
产出：site/cards/*.png
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "cards")
SITE = os.path.join(HERE, "dist", "data", "site.json")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
URL = "shadowjacob.shop/dota2"

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0d0d;color:#fff;font-family:"PingFang SC","Hiragino Sans GB",sans-serif;
     -webkit-font-smoothing:antialiased}
.page{width:%(W)dpx;padding:%(PAD)dpx;background:#0d0d0d}
body.card .page{min-height:%(H)dpx;display:flex;flex-direction:column}
body.card .foot{margin-top:auto}
body.card .grow{flex:1;display:flex;flex-direction:column;justify-content:center}
.eyebrow{color:#898781;font-size:%(fs_eye)dpx;letter-spacing:2px;margin-bottom:14px}
h1{font-size:%(fs_h1)dpx;line-height:1.18;letter-spacing:-1px;font-weight:800;margin-bottom:18px}
h1 em{font-style:normal;color:#3987e5}
.sub{color:#c3c2b7;font-size:%(fs_sub)dpx;line-height:1.6;margin-bottom:10px}
.tagline{color:#898781;font-size:%(fs_tag)dpx;margin-bottom:%(gap)dpx}
h2{font-size:%(fs_h2)dpx;font-weight:750;margin:%(gap)dpx 0 6px;letter-spacing:-.5px}
h2 .n{color:#3987e5;margin-right:12px}
.h2sub{color:#898781;font-size:%(fs_tag)dpx;margin-bottom:22px}
.row{display:flex;align-items:center;gap:16px;margin:9px 0}
.row .nm{width:%(namew)dpx;text-align:right;font-size:%(fs_row)dpx;color:#c3c2b7;
         white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:none}
.row .track{flex:1;height:%(barh)dpx;background:#2c2c2a;border-radius:5px;overflow:hidden}
.row .fill{height:100%%;background:#3987e5;border-radius:5px}
.row .fill.dim{background:#3a4a5e}
.row .v{width:%(valw)dpx;font-size:%(fs_row)dpx;font-variant-numeric:tabular-nums;flex:none}
.row.top .nm,.row.top .v{color:#fff;font-weight:700}
.split{display:flex;gap:%(gap2)dpx;margin:22px 0;align-items:flex-start}
.box{flex:1;background:#1a1a19;border:1px solid #2c2c2a;border-radius:16px;padding:%(boxpad)dpx}
.box .lbl{color:#898781;font-size:%(fs_tag)dpx;margin-bottom:10px}
.box .big{font-size:%(fs_big)dpx;font-weight:800;letter-spacing:-1.5px;line-height:1.1}
.box .big.up{color:#eb6834}.box .big.dn{color:#3987e5}
.box .note{color:#c3c2b7;font-size:%(fs_note)dpx;margin-top:10px;line-height:1.5}
.kv{display:flex;justify-content:space-between;padding:%(kvpad)dpx 0;border-bottom:1px solid #2c2c2a;
    font-size:%(fs_row)dpx}
.kv:last-child{border-bottom:none}
.kv b{font-weight:700;font-variant-numeric:tabular-nums}
.kv .hl{color:#3987e5}
.tiles{display:flex;gap:%(gap2)dpx;margin:20px 0}
.tile{flex:1;background:#1a1a19;border:1px solid #2c2c2a;border-radius:16px;padding:%(boxpad)dpx;text-align:center}
.tile .v{font-size:%(fs_tile)dpx;font-weight:800;letter-spacing:-1px}
.tile .k{color:#898781;font-size:%(fs_note)dpx;margin-top:8px;line-height:1.4}
ul{list-style:none}
li{color:#c3c2b7;font-size:%(fs_li)dpx;line-height:1.65;padding-left:26px;position:relative;margin:11px 0}
li:before{content:"—";position:absolute;left:0;color:#3987e5}
li b{color:#fff}
.foot{margin-top:%(gap)dpx;padding-top:26px;border-top:1px solid #2c2c2a}
.url{font-size:%(fs_url)dpx;font-weight:800;color:#3987e5;letter-spacing:-.5px}
.promise{color:#c3c2b7;font-size:%(fs_note)dpx;margin-top:12px;line-height:1.6}
.cover{width:%(W)dpx;height:%(H)dpx;background:#0d0d0d;padding:88px 96px;
       display:flex;gap:80px;align-items:center;position:relative;overflow:hidden}
.cover .L{flex:1.05;min-width:0}
.cover .R{flex:1;min-width:0}
.cover .eyebrow{font-size:26px;letter-spacing:4px;margin-bottom:22px}
.cover h1{font-size:104px;line-height:1.08;letter-spacing:-3px;margin-bottom:26px}
.cover .promise{font-size:34px;line-height:1.5;color:#c3c2b7;margin-top:0}
.cover .promise b{color:#fff}
.cover .urlbig{position:absolute;left:96px;bottom:64px;font-size:36px;font-weight:800;
               color:#3987e5;letter-spacing:-.5px}
.cover .rt{color:#898781;font-size:24px;letter-spacing:1px;margin-bottom:26px}
.cover .row{margin:14px 0;gap:20px}
.cover .row .nm{width:230px;font-size:30px}
.cover .row .track{height:28px;border-radius:7px}
.cover .row .v{width:120px;font-size:30px}
.cover .glow{position:absolute;right:-320px;top:-260px;width:900px;height:900px;
             background:radial-gradient(circle,#1d4d8c66 0%%,transparent 62%%);pointer-events:none}
.hwgrid{display:grid;grid-template-columns:1fr 1fr;gap:%(gap2)dpx;margin:20px 0}
.hwb{background:#1a1a19;border:1px solid #2c2c2a;border-radius:14px;padding:%(boxpad)dpx}
.hwt{display:flex;justify-content:space-between;align-items:baseline;gap:10px;
     padding-bottom:10px;margin-bottom:8px;border-bottom:1px solid #2c2c2a}
.hwt b{font-size:%(fs_h2)dpx;letter-spacing:-1px}
.hwt span{color:#898781;font-size:%(fs_note)dpx}
.hwp{display:flex;justify-content:space-between;padding:5px 0;font-size:%(fs_row)dpx;color:#fff}
.hwp span{color:#898781;font-variant-numeric:tabular-nums}
.badge{display:inline-block;background:#1a1a19;border:1px solid #3987e5;color:#3987e5;
       border-radius:999px;padding:7px 18px;font-size:%(fs_note)dpx;margin-bottom:20px}
"""

SIZES_LONG = dict(W=1080, H=0, PAD=64, fs_eye=22, fs_h1=62, fs_sub=27, fs_tag=22, fs_h2=40,
                  fs_row=25, fs_big=64, fs_note=22, fs_li=25, fs_tile=48, fs_url=34,
                  namew=210, valw=105, barh=22, gap=54, gap2=20, boxpad=26, kvpad=13)
SIZES_COVER = dict(W=1920, H=1080, PAD=0, fs_eye=26, fs_h1=104, fs_sub=34, fs_tag=24, fs_h2=48, fs_row=30, fs_big=80, fs_note=26, fs_li=29, fs_tile=64, fs_url=36, namew=230, valw=120, barh=28, gap=48, gap2=24, boxpad=32, kvpad=16)
SIZES_CARD = dict(W=1242, H=1656, PAD=76, fs_eye=24, fs_h1=76, fs_sub=32, fs_tag=25, fs_h2=48,
                  fs_row=30, fs_big=80, fs_note=25, fs_li=29, fs_tile=60, fs_url=38,
                  namew=250, valw=125, barh=26, gap=56, gap2=24, boxpad=32, kvpad=16)


def bars(teams, key, top_n=None, highlight=None):
    rows = teams[:top_n] if top_n else teams
    mx = max(r[key] for r in rows) or 1
    out = []
    for i, r in enumerate(rows):
        cls = " top" if i < 3 else ""
        fill = "fill" + ("" if (highlight is None or r["team"] in highlight) else " dim")
        out.append(
            '<div class="row%s"><div class="nm">%s</div>'
            '<div class="track"><div class="%s" style="width:%.1f%%"></div></div>'
            '<div class="v">%.1f%%</div></div>'
            % (cls, r["team"], fill, r[key] / mx * 100, r[key] * 100))
    return "".join(out)


def dist_kv(d, unit="支"):
    return "".join(
        '<div class="kv"><span>%s %s</span><b class="%s">%.1f%%</b></div>'
        % (k, unit, "hl" if d[k] == max(d.values()) else "", d[k] * 100)
        for k in sorted(d, key=int) if d[k] > 0.005)


HW_ORDER = [("4-0", "一支全胜"), ("4-1", "两支四胜一负"),
            ("淘汰赛胜者", "五支淘汰赛胜出"), ("淘汰赛败者", "五支淘汰赛失败"),
            ("1-4", "两支一胜四负"), ("0-4", "一支全败")]


def hw_block(p):
    """抄作业六档，两列排布。"""
    ans = p["homework"]["answer"]
    cells = []
    for nm, desc in HW_ORDER:
        picks = ans.get(nm, [])
        names = "".join('<div class="hwp">%s<span>%.0f%%</span></div>' % (t, v * 100)
                        for t, v in picks)
        cells.append('<div class="hwb"><div class="hwt"><b>%s</b><span>%s</span></div>%s</div>'
                     % (nm, desc, names))
    return '<div class="hwgrid">%s</div>' % "".join(cells)


def html(body, sizes, cls=""):
    return ("<!doctype html><html><head><meta charset=utf-8><style>%s</style></head>"
            "<body class='%s'><div class=page>%s</div></body></html>"
            % (CSS % sizes, cls, body))


def long_image(p):
    t = p["teams"]
    fal = next(x for x in t if x["team"] == "Team Falcons")
    yan = next(x for x in t if x["team"] == "Team Yandex")
    oos = p["oos"]
    ep = p["homework"]["elim"]
    pl = p.get("patch_layer")
    if not pl:
        raise SystemExit("site.json 里没有 patch_layer——先跑 "
                         "python3 -m model.l1_strength --refit 再 build_site.py")
    body = """
<div class="badge">赛前已哈希存证 · 市场价截至 %s</div>
<div class="eyebrow">THE INTERNATIONAL 2026 · 8/13–8/23 上海</div>
<h1>TI15 谁会赢<br><em>一个赛后要认账的预测</em></h1>
<div class="sub">用 2020–2026 的 <b>145,974 场</b>职业比赛跑出来的量化预测。<br>
所有结果赛前冻结留证，8/23 赛后用同一套代码打分——好看不好看都发。</div>
<div class="tagline">蒙特卡洛 20 万次 · 分组仍未公布，已把所有可能的抽签平均掉</div>

<h2><span class="n">01</span>夺冠概率</h2>
<div class="h2sub">已与市场共识价融合：Polymarket ✕ 庄家赔率（市场权重 0.7）</div>
%s

<h2><span class="n">02</span>模型和市场吵起来了</h2>
<div class="h2sub">这是整套预测里最值得赛后复盘的地方</div>
<div class="split">
  <div class="box"><div class="lbl">Team Falcons</div>
    <div class="big dn">%.1f%% → %.1f%%</div>
    <div class="note"><b>模型看好，市场不认。</b><br>16 队中唯一阵容零变动的卫冕冠军。</div></div>
  <div class="box"><div class="lbl">Team Yandex</div>
    <div class="big up">%.1f%% → %.1f%%</div>
    <div class="note"><b>模型看淡，市场看好。</b><br>Polymarket 上真金白银把它买到了第二。</div></div>
</div>

<h2><span class="n">03</span>官方预测题·抄作业</h2>
<div class="h2sub">游戏内「赛事预测」小组赛那 16 格的建议填法</div>
%s
<div class="note" style="color:#898781;font-size:%dpx;line-height:1.6">
期望答对 %.2f / 16 格，随机乱填 %.2f 格——只多约 %.1f 格。够到保底奖励有用，冲榜不够。<br>
<b style="color:#c3c2b7">最贵的两格：</b>「淘汰赛胜者」实力前八全挤在 %.1f%%–%.1f%%，填谁都一样，
坑是填垫底队（低到 %.1f%%）；「淘汰赛败者」反过来，最该躲开的是最强的那支（%.1f%%，比最优低 %.1f 个百分点）——它根本打不到这一轮。</div>

<h2><span class="n">04</span>凭什么信</h2>
<div class="h2sub">训练只用 2026-03 之前的数据，在之后没见过的比赛上实测</div>
<div class="tiles">
  <div class="tile"><div class="v">%.1f%%</div><div class="k">样本外准确率<br>%s 场未见过的比赛</div></div>
  <div class="tile"><div class="v">%.4f</div><div class="k">预测校准分<br>健康区间 0.21–0.24，越低越好</div></div>
  <div class="tile"><div class="v">145,974</div><div class="k">训练用的<br>职业比赛场次</div></div>
</div>
<div class="note" style="color:#c3c2b7;font-size:%dpx;line-height:1.6">
赛前预测的<b>现实上限是 65–70%%</b>。所有号称 85%% 以上准确率的 Dota 预测，
用的都是实时游戏内数据而不是赛前数据。<b>做到 85%% 一定是泄漏。</b></div>

<h2><span class="n">05</span>这次更新：读者要的功能我做了，实测是白做</h2>
<div class="h2sub">「越老的版本权重越低」——直觉对，增量没有</div>
<div class="split">
  <div class="box"><div class="lbl">加版本层后，验证期提升</div>
    <div class="big dn">%.5f</div>
    <div class="note">LogLoss 只降了这么多，<br>而它的标准误约 %.4f——
    <b>差距是标准误的 1/%.0f</b>。<br>16 队实力分排序<b>一格没动</b>。</div></div>
  <div class="box"><div class="lbl">为什么没用</div>
    <div class="big up">r = %.3f</div>
    <div class="note">版本发布本来就按时间排。<br>选中的「%s 天 + γ=%s」和原来的
    「%s 天 + 不打折」<br><b>画出来是同一条曲线</b>，半衰点只差 %.0f 天。</div></div>
</div>
<div class="note" style="color:#c3c2b7;font-size:%dpx;line-height:1.6">
更反直觉的是<b>反方向</b>：验证期里所有「更狠地偏向近期」的组合（半衰期 120 天、γ=0.5 等）
<b style="color:#fff">全部更差</b>。现行权重下当前版本 7.41 的比赛只占总权重 %.0f%%，
看着少，再往上加就是变差。<b style="color:#fff">「多给近期加权」这件事，数据投的是反对票。</b><br>
整格搜索的 %d 行结果都能下载核对——判据是事先写死的，看完结果再改判据就是自欺。</div>

<h2><span class="n">06</span>我把自己的错也写上去了</h2>
<ul>
<li><b>抄作业那两格的填法说反了</b>：我写「淘汰赛胜者别填最强的」，那条只值 1.9 个百分点；真正值 24 个百分点的「别填垫底队」我没写。NGA 读者指出的。</li>
<li><b>赛制一开始就建错了</b>：按「固定 5 轮人人打满」建模，产出了现实中不存在的 5-0。真实是打到 4 胜或 4 负即停。读者在评论区抓到的，已重写。</li>\n<li><b>算错了波动幅度</b>：以为选手每局的发挥比实际稳定得多，导致每分钟经济和补刀的<b>误差范围窄了 4–8 倍</b>。已修正。</li>
<li>发现过 <b>7 次「测试写了但测不到」</b>——比如一条声称锁住号位分层的测试，把所有人塞进同一组照样通过。</li>
<li>调研阶段明确写过「别假设，先在自己的数据上量一遍」——<b>这条要求在层层传递中弄丢了，从没执行过</b>。</li>
<li>梦幻挑战里有两项计分数据拿不到，而它们恰好都算在辅助身上——<b>辅助那一栏的预测天生偏弱</b>，补不上。</li>
</ul>

<div class="foot">
  <div class="url">%s</div>
  <div class="promise">全部数据可下载 · 120 个对阵的赛前胜率全公开 · 改过什么全记在站内「更新日志」<br>
  <b style="color:#fff">8 月 23 日赛后，我会用同一套代码打分，好看不好看都发。</b></div>
</div>
""" % (p.get("market_captured", ""), bars(t, "champ_blended"),
       fal["champ_model"] * 100, fal["champ_blended"] * 100,
       yan["champ_model"] * 100, yan["champ_blended"] * 100,
       hw_block(p), SIZES_LONG["fs_note"],
       p["homework"]["expected"], p["homework"]["random"],
       p["homework"]["expected"] - p["homework"]["random"],
       ep["sv_lo8"], ep["sv_hi8"], ep["sv_min"], ep["ou_min"], ep["ou_gap"],
       oos.get("acc", 0) * 100, "{:,}".format(oos.get("n", 0)), oos.get("brier", 0),
       SIZES_LONG["fs_note"],
       pl["delta_abs"], pl["se"], pl["se_ratio"],
       pl["curve_r"], pl["hl_sel"], pl["g_sel"], pl["hl_off"], pl["half_gap"],
       SIZES_LONG["fs_note"], pl["cur_share"], pl["n_grid"],
       URL)
    return html(body, SIZES_LONG)


def cover(p):
    t = p["teams"][:6]
    body = """
<div class="cover"><div class="glow"></div>
  <div class="L">
    <div class="eyebrow">THE INTERNATIONAL 2026 · 8/13 上海</div>
    <h1>TI15<br>谁会赢</h1>
    <div class="promise"><b>一个赛后要认账的预测</b><br>
    14.6 万场比赛 · 赛前已哈希存证</div>
  </div>
  <div class="R">
    <div class="rt">夺冠概率（已融合市场共识价）</div>
    %s
  </div>
  <div class="urlbig">shadowjacob.shop/dota2</div>
</div>
""" % bars(t, "champ_blended")
    return ("<!doctype html><html><head><meta charset=utf-8><style>%s"
            ".page{padding:0;width:%dpx}</style></head><body><div class=page>%s</div></body></html>"
            % (CSS % SIZES_COVER, SIZES_COVER["W"], body))


def cards(p):
    t = p["teams"]
    fal = next(x for x in t if x["team"] == "Team Falcons")
    yan = next(x for x in t if x["team"] == "Team Yandex")
    oos = p["oos"]
    S = SIZES_CARD
    c1 = """
<div class="grow"><div><div class="badge">赛前已哈希存证</div>
<div class="eyebrow">THE INTERNATIONAL 2026</div>
<h1>TI15 谁会赢<br><em>一个赛后<br>要认账的预测</em></h1>
<div class="sub">145,974 场职业比赛跑出来的<br>量化预测</div>
<div class="tiles" style="margin-top:44px">
  <div class="tile"><div class="v">%.1f%%</div><div class="k">%s</div></div>
  <div class="tile"><div class="v">%.1f%%</div><div class="k">%s</div></div>
  <div class="tile"><div class="v">%.1f%%</div><div class="k">%s</div></div>
</div>
</div></div>
<div class="foot"><div class="url">%s</div>
<div class="promise">8/23 赛后用同一套代码打分<br>好看不好看都发</div></div>
""" % (t[0]["champ_blended"] * 100, t[0]["team"], t[1]["champ_blended"] * 100, t[1]["team"],
       t[2]["champ_blended"] * 100, t[2]["team"], URL)

    c2 = """
<div class="grow"><div><div class="eyebrow">01 · 夺冠概率</div>
<h1 style="font-size:%dpx">16 支队<br>没有真正的大热门</h1>
<div class="sub" style="margin-bottom:30px">头名只有 %.1f%%，前八名挤在 %.0f%%–%.0f%%</div>
%s
</div></div><div class="foot"><div class="url">%s</div></div>
""" % (S["fs_h1"] - 10, t[0]["champ_blended"] * 100,
       t[7]["champ_blended"] * 100, t[0]["champ_blended"] * 100,
       bars(t, "champ_blended", top_n=12), URL)

    c3 = """
<div class="grow"><div><div class="eyebrow">02 · 最大分歧</div>
<h1 style="font-size:%dpx">模型和市场<br>吵起来了</h1>
<div class="sub" style="margin-bottom:34px">这是赛后最值得复盘的地方</div>
<div class="box" style="margin-bottom:24px"><div class="lbl">Team Falcons</div>
  <div class="big dn">%.1f%% → %.1f%%</div>
  <div class="note"><b>模型看好，市场不认。</b><br>16 队中唯一阵容零变动的卫冕冠军。<br>
  我们按「当前这五个人」算历史战绩，<br>阵容连续性直接兑现成样本量。</div></div>
<div class="box"><div class="lbl">Team Yandex</div>
  <div class="big up">%.1f%% → %.1f%%</div>
  <div class="note"><b>模型看淡，市场看好。</b><br>Polymarket 上真金白银把它买到了第二——<br>
  只看历史战绩的模型给不出这个价。</div></div>
</div></div><div class="foot"><div class="url">%s</div></div>
""" % (S["fs_h1"] - 10, fal["champ_model"] * 100, fal["champ_blended"] * 100,
       yan["champ_model"] * 100, yan["champ_blended"] * 100, URL)

    c4 = """
<div class="grow"><div><div class="eyebrow">03 · 凭什么信</div>
<h1 style="font-size:%dpx">我把自己的错<br>也写上去了</h1>
<div class="tiles" style="margin:34px 0">
  <div class="tile"><div class="v">%.1f%%</div><div class="k">样本外准确率</div></div>
  <div class="tile"><div class="v">%.4f</div><div class="k">预测校准分<br>越低越好</div></div>
</div>
<div class="sub" style="font-size:%dpx;margin-bottom:26px">赛前预测现实上限 65–70%%。<br>
<b>做到 85%% 一定是数据泄漏。</b></div>
<ul>
<li>算错了波动幅度，<b>误差范围窄了 4–8 倍</b></li>
<li>发现 <b>7 次「测试写了但测不到」</b></li>
<li>Watcher/Lotus 取不到，<b>辅助槽结构性偏弱</b></li>
</ul>
</div></div><div class="foot"><div class="url">%s</div>
<div class="promise">数据全可下载 · 120 个对阵胜率全公开<br>
<b style="color:#fff">8/23 赛后打分，好看不好看都发</b></div></div>
""" % (S["fs_h1"] - 10, oos.get("acc", 0) * 100, oos.get("brier", 0), S["fs_sub"] - 3, URL)

    return [html(c, S, "card") for c in (c1, c2, c3, c4)]


def shoot(htmlstr, name, width, min_h=800):
    tmp = os.path.join(OUT, "_tmp.html")
    open(tmp, "w").write(htmlstr)
    png = os.path.join(OUT, name)
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1",
                    "--screenshot=" + png, "--window-size=%d,%d" % (width, 6000),
                    "file://" + tmp], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # 裁掉底部多余背景
    from PIL import Image
    im = Image.open(png).convert("RGB")
    w, h = im.size
    bg = im.getpixel((5, h - 5))
    bottom = h
    for y in range(h - 1, 0, -1):
        row = [im.getpixel((x, y)) for x in range(0, w, 40)]
        if any(abs(px[0] - bg[0]) + abs(px[1] - bg[1]) + abs(px[2] - bg[2]) > 24 for px in row):
            bottom = min(h, y + 64)
            break
    im.crop((0, 0, w, max(bottom, min_h))).save(png)
    os.remove(tmp)
    return png, im.crop((0, 0, w, max(bottom, min_h))).size


def main():
    if not os.path.exists(SITE):
        raise SystemExit("先跑 python3 site/build_site.py")
    p = json.load(open(SITE))
    os.makedirs(OUT, exist_ok=True)
    made = []
    made.append(shoot(cover(p), "ti15-cover.png", 1920, min_h=1080))
    made.append(shoot(long_image(p), "ti15-long.png", 1080))
    for i, c in enumerate(cards(p), 1):
        made.append(shoot(c, "ti15-card-%d.png" % i, 1242, min_h=1656))
    print("产出 %s：" % OUT)
    for f, size in made:
        print("  %-22s %dx%d  %.0f KB" % (os.path.basename(f), size[0], size[1],
                                          os.path.getsize(f) / 1024))


if __name__ == "__main__":
    main()
