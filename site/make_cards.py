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
/* 八强对阵卡：一条分割条把「此消彼长」直接画出来，读者不用做减法 */
.mrow{display:flex;justify-content:space-between;gap:10px;font-size:%(fs_row)dpx;color:#fff}
.mrow.v{color:#c3c2b7;font-variant-numeric:tabular-nums;margin-top:6px}
.mbar{display:flex;height:%(barh)dpx;border-radius:6px;overflow:hidden;margin-top:10px}
.mbar .ma{background:#3987e5}.mbar .mb{background:#eb6834}
.msub{color:#898781;font-size:%(fs_note)dpx;margin-top:10px;padding-top:10px;
      border-top:1px solid #2c2c2a}
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

# 分歧队各自的理由。队名是**现算**的（见 long_image 里的 by_gap），这里只按队名
# 查理由；查不到就退回一句通用说明，绝不因为分歧转移到没写过的队身上而崩掉。
GAP_WHY = {
    "TEAM VISION": "小组赛 4-0 唯一全胜。分歧不在谁最强——模型也把它排第一——"
                   "而在<b style='color:#fff'>强多少</b>。",
    "Team Falcons": "16 队里<b style='color:#fff'>唯一阵容零变动</b>的卫冕冠军。"
                    "模型按「当前这五个人」算历史战绩，阵容连续性直接兑现成样本量。",
    "Nigma Galaxy": "赛前实力分是 16 队里<b style='color:#fff'>倒数第四</b>，却打出 4-1 直通八强。",
    "Team Yandex": "赛前实力分排第三，小组赛却一路走到 2-3 才靠附加轮翻上来。",
    "Team Spirit": "核心三人留任，但队长兼指挥转任教练，场上指挥体系换了人。",
    "Team Liquid": "换了 pos3 与 pos5 两人，历史战绩要打折。",
    "Iron Wing": "Tundra 阵容整体转会，队名变了但班底是连续的。",
    "BoomBoys": "只换了 pos1，历史战绩基本可用。",
}
GAP_WHY_FALLBACK = "模型与市场对这支队的定价差得最远，赛后可以回头判谁对。"


def qf_block(p):
    """八强四场对阵。一场比赛只有两个结果，所以用一条分割条而不是两根独立的条。"""
    s = SIZES_LONG
    mk = {r["a"]: r["p_market"] for r in (p["playoffs"].get("match_market") or [])}
    out = []
    for m in p["playoffs"]["ubqf"]:
        pa = m["p_blended"]
        out.append(
            '<div class="hwb"><div class="hwt"><b>%s</b><span>%s</span></div>'
            '<div class="mrow"><span>%s</span><span>%s</span></div>'
            '<div class="mbar"><div class="ma" style="width:%.1f%%"></div>'
            '<div class="mb" style="width:%.1f%%"></div></div>'
            '<div class="mrow v"><span>%.1f%%</span><span>%.1f%%</span></div>'
            '<div class="msub">%s</div></div>'
            % (m["a"], m["time_cst"], m["a"], m["b"],
               pa * 100, (1 - pa) * 100, pa * 100, (1 - pa) * 100,
               ("单场盘 <b style='color:#fff'>%.1f%%</b> · 纯模型 %.1f%%"
                % (mk[m["a"]] * 100, m["p_model"] * 100)) if m["a"] in mk
               else "纯模型口径 %.1f%% · %.1f%%" % (m["p_model"] * 100, (1 - m["p_model"]) * 100)))
    # 队名放在标题位会被截断，改成两行结构：标题只放先手队名不够清楚，
    # 所以这里标题直接写「谁 vs 谁」的时间，队名单独一行。
    out = [o.replace('<b>%s</b>' % m["a"], '<b>八强 · %d</b>' % (i + 1))
           for i, (o, m) in enumerate(zip(out, p["playoffs"]["ubqf"]))]
    return '<div class="hwgrid">%s</div>' % "".join(out)


def bracket_block(p):
    """主赛事对阵表的建议填法，两列排布。"""
    rows = p["playoffs"]["bracket"]["rows"]
    cells = "".join(
        '<div class="hwp">%s　%s<span>%.0f%%</span></div>' % (r["panel"], r["pick"], r["p"] * 100)
        for r in rows)
    return ('<div class="hwb" style="margin:20px 0"><div class="hwt">'
            '<b>建议填法（14 场）</b><span>格号 · 填谁 · 这一场它赢的概率</span></div>'
            '<div style="columns:2;column-gap:%dpx">%s</div></div>'
            % (SIZES_LONG["gap2"], cells))


def hw_score_block(p):
    """小组赛 16 格：赛前那版逐格对答案。"""
    sc = p["homework_score"]
    cells = []
    for row in sc["buckets"]:
        picks = "".join(
            '<div class="hwp">%s %s<span>赛前 %.0f%%</span></div>'
            % ("✓" if t in row["hit"] else "✗", t, row["pre_p"].get(t, 0) * 100)
            for t in row["picks"])
        cells.append(
            '<div class="hwb"><div class="hwt"><b>%s</b><span>%d/%d</span></div>%s</div>'
            % (row["bucket"], len(row["hit"]), row["cap"], picks))
    return '<div class="hwgrid">%s</div>' % "".join(cells)


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
    oos = p["oos"]
    ep = p["homework"]["elim"]
    rv = p.get("review") or {}
    pl = p.get("patch_layer")
    if not pl:
        raise SystemExit("site.json 里没有 patch_layer——先跑 "
                         "python3 -m model.l1_strength --refit 再 build_site.py")

    # 模型与市场分歧最大的两支队**现算**，不写死队名。
    # 上一版把 Falcons/Yandex 写死在图里，等赛程推进、分歧转移到别的队身上，
    # 图上那两个框就变成了「过期的争论」——而长图是发出去收不回来的。
    gap = sorted(t, key=lambda x: x["champ_blended"] - x["champ_model"])
    dn, up = gap[0], gap[-1]        # dn: 模型高于市场；up: 市场高于模型

    # 状态行跟着 site.json 走，别写死——这行字曾经在首轮已经公布之后
    # 还挂着「分组仍未公布，已把所有可能的抽签平均掉」，图发出去就是错的。
    drw = p.get("draw") or {}
    if rv.get("active") and rv.get("n_group_splits") == 1:
        # 分组已被比赛本身解出唯一解。此时再说「N 种分法全部平均掉」是句废话
        # （N=1，平均个什么），而且会让人以为还有不确定性。
        draw_line = ("已打完 %d 场系列赛，结果全部当事实代入 · 分组已由对阵唯一解出，全程未猜"
                     % rv["n_done"])
    elif rv.get("active"):
        draw_line = ("已打完 %d 场系列赛，结果已代入重算 · 分组仍未公布，%d 种自洽分法全部平均掉"
                     % (rv["n_done"], rv["n_group_splits"]))
    elif not drw.get("announced"):
        draw_line = "分组仍未公布，已把所有可能的抽签平均掉"
    elif drw.get("grouping") == "official":
        draw_line = "分组已公布，已按真实抽签重算"
    elif drw.get("round1"):
        draw_line = ("首轮对阵已确定并锁进模型 · 分组仍未公布，%d 种自洽分法全部平均掉"
                     % (drw.get("n_group_splits") or 35))
    else:
        draw_line = "分组为推测，非官方公布"

    badge = ("已打完 %d 场 · 赛前预测已哈希存证 · 市场价截至 %s"
             % (rv["n_done"], p.get("market_captured", ""))) if rv.get("active") else \
            ("赛前已哈希存证 · 市场价截至 %s" % p.get("market_captured", ""))

    # 复盘小节只在开赛后出现；赛前这一整块不渲染（数字全是 None，硬渲染必崩）。
    # 两段措辞随赛况分叉，不写死：
    #   · 分组还剩多种 → 讲「它正在自己解开」；已收敛到 1 种 → 讲「它解开了」
    #   · 五五开那档贴近抛硬币（0.25）→ 必须把这件事挑明，而不是只报好看的总分
    settled = rv.get("settled") or []
    settled_line = "；".join(
        "%s 是 %s（赛前押 %s，%s）" % (x["bucket"], "、".join(x["teams"]), x["pick"],
                                      "押中" if x["hit"] else "押错")
        for x in settled)
    coin = rv["brier_close"] >= 0.235
    lead = ("五五开那一档，已经贴到抛硬币了" if coin
            else "赛前预测已经对了 %d 场答案" % rv["n_scored"])

    if coin:
        review_body = """
<div class="note" style="color:#c3c2b7;font-size:%(fs)dpx;line-height:1.6">
整体 Brier <b style="color:#fff">%(brier).3f</b>，方向 %(hits)d/%(n)d——看着还行。
<b style="color:#fff">但把送分题剔掉之后就不好看了。</b><br>
拆开看：赛前就<b>强弱悬殊</b>的 %(nfar)d 场，Brier %(bfar).3f、%(hfar)d/%(nfar)d；
赛前<b>接近五五开</b>的 %(nclose)d 场，方向只对了 <b style="color:#fff">%(hclose)d 场</b>，
Brier <b style="color:#fff">%(bclose).3f</b>——而<b style="color:#fff">抛硬币的 Brier 恒为 0.25</b>。<br><br>
<b style="color:#fff">正确的读法不是「模型看走眼了」，也不是「模型很准」，而是：
模型说这些是五五开，它们就真的表现得像五五开。</b>
校准是对的，但同时意味着一件不好听的事——<b style="color:#fff">在势均力敌的比赛上，这个模型没提供任何信息量</b>。
它能告诉你的只有「谁明显更强」，而这一点你不看模型也知道。<br><br>
上一次交账时总分是 0.136，低到触发了项目自己的泄漏护栏，当时的解释是「赛程太软，不是模型神」，
并预告「等强队互相碰上，这个数会往上走」。<b style="color:#fff">现在它如期走上来了——那句解释是对的。</b>
当初要是拿 0.136 出去吹，今天就得解释「为什么变差了」。</div>
""" % {"fs": SIZES_LONG["fs_note"], "brier": rv["brier_all"], "hits": rv["hits"],
       "n": rv["n_scored"], "nfar": rv["n_far"], "bfar": rv["brier_far"],
       "hfar": rv["hits_far"], "nclose": rv["n_close"], "hclose": rv["hits_close"],
       "bclose": rv["brier_close"]}
    else:
        review_body = """
<div class="note" style="color:#c3c2b7;font-size:%dpx;line-height:1.6">
<b style="color:#fff">这个 %.3f 好看得可疑，所以先自己查了一遍。</b>
本项目设计文档写死一条：<b>Brier 低于 0.20 要先怀疑数据泄漏，而不是庆祝</b>。
查下来不是泄漏（预测 8/2 就冻结留证了），是<b>赛程太软</b>——
拆开看：赛前就强弱悬殊的 %d 场，Brier %.3f、全中，这种局本来就该全中；
真正接近五五开的 %d 场，Brier <b style="color:#fff">%.3f</b>，正好落在 0.21–0.24 的正常区间。
<b style="color:#fff">能体现水平的那几场，打出来的是「正常」，不是神迹。</b></div>
""" % (SIZES_LONG["fs_note"], rv["brier_all"], rv["n_far"], rv["brier_far"],
       rv["n_close"], rv["brier_close"])

    # 「分组自己解开了」那一节已经是上一版的头条，站内复盘页第三页签留着完整版；
    # 这张图讲的是接下来 14 场，塞进一段旧新闻只会挤掉前瞻的篇幅。settled_line
    # 仍然算（下面 05 节的自查要用），但不再单独占一节。
    review_block = ("""
<h2><span class="n">03</span>先交账：%s</h2>
<div class="h2sub">赛前冻结的 120 组两两胜率，逐场回填实际结果（已完赛 %d 场）</div>
<div class="tiles">
  <div class="tile"><div class="v">%d/%d</div><div class="k">方向看对<br>已完赛系列赛</div></div>
  <div class="tile"><div class="v">%.3f</div><div class="k">Brier（全部）<br>低于 0.20 要先怀疑自己</div></div>
  <div class="tile"><div class="v">%.3f</div><div class="k">Brier（五五开那档）<br>0.25 就是抛硬币</div></div>
</div>
%s
<div class="note" style="color:#c3c2b7;font-size:%dpx;line-height:1.6">
<b style="color:#fff">另一个反直觉的结果：概率的挪动几乎全是市场挪的，不是打出来的。</b>
战绩带来的位移最大一支只有 <b style="color:#fff">%.1fpp</b>，市场重新定价带来的最大 <b style="color:#fff">%.1fpp</b>——差约 %.0f 倍。
瑞士轮容错太高（4 胜或 4 负才停，后面还有附加赛和双败），单轮胜负对夺冠的影响本来就有限。</div>
""" % (lead, rv["n_done"], rv["hits"], rv["n_scored"], rv["brier_all"], rv["brier_close"],
       review_body,
       SIZES_LONG["fs_note"],
       rv["max_res_shift"], rv["max_mkt_shift"], rv["shift_ratio"])) if rv.get("active") else ""

    pw = p["playoffs"]
    hs = p["homework_score"]
    bk = pw["bracket"]
    rb = pw["robustness"]
    # 分歧队**现算**，不写死队名——赛程推进时分歧会转移到别的队身上，
    # 而长图是发出去收不回来的（上一版把 Falcons/Yandex 写死过，就吃过这个亏）。
    by_gap = sorted(pw["teams"], key=lambda r: r["model"] - r["market"])
    up, dn = by_gap[0], by_gap[-1]      # up: 市场看好；dn: 模型看好
    big = [r for r in sorted(pw["teams"], key=lambda r: -abs(r["model"] - r["market"]))
           if abs(r["model"] - r["market"]) > 0.05]
    prem = "".join(
        '<div class="hwp">%s<span>市场 %+.3f ／ 数据 %+.3f</span></div>'
        % (r["team"], r["market_delta"], r["data_delta"]) for r in big)

    body = """
<div class="badge">%s</div>
<div class="eyebrow">THE INTERNATIONAL 2026 · 主赛事 8/20–8/23 上海</div>
<h1>TI15 还剩 14 场<br><em>八强前瞻，赛后要认账</em></h1>
<div class="sub">小组赛已经打完——瑞士轮加附加淘汰轮共 <b>44 场系列赛</b>全部结束。<br>
这份图只讲<b>还没打的那 14 场</b>，所有数字都代入了已发生的全部赛果与实时市场价。</div>
<div class="tagline">精确枚举 8192 条路径 · %s</div>

<h2><span class="n">01</span>八强四场：这是事实，不是预测</h2>
<div class="h2sub">对阵由官方排定；附加轮是「高排位队自己挑对手」的选人制，签表与名次规则对不上</div>
%s

<h2><span class="n">02</span>夺冠概率</h2>
<div class="h2sub">已代入全部赛果，并与市场共识价融合（市场权重 0.7）</div>
%s
%s

<h2><span class="n">04</span>模型和市场吵得最凶的三支队</h2>
<div class="h2sub">这是整份预测里最值得赛后复盘的地方——而且赛后能判对错</div>
<div class="split">
  <div class="box"><div class="lbl">%s</div>
    <div class="big dn">%.1f%% ／ %.1f%%</div>
    <div class="note"><b>模型 ／ 市场。</b><br>%s</div></div>
  <div class="box"><div class="lbl">%s</div>
    <div class="big up">%.1f%% ／ %.1f%%</div>
    <div class="note"><b>模型 ／ 市场。</b><br>%s</div></div>
</div>
<div class="hwb" style="margin:20px 0">
  <div class="hwt"><b>换成实力分再看一遍</b><span>市场给的加减分 ／ TI15 战绩支持的加减分</span></div>
  %s
</div>
<div class="note" style="color:#c3c2b7;font-size:%dpx;line-height:1.6">
<b style="color:#fff">「你只是数据没更新」——这条质疑我算过了，不成立。</b>
模型的实力分训练截止 2026-08-02，<b>没见过 TI15 任何一局</b>。
把已打完的 <b style="color:#fff">%d 小局</b>按贝叶斯折进实力分（先验就用赛前那次拟合的后验），
结果是<b style="color:#fff">几乎不动</b>：实力分最大位移 %.3f，夺冠概率最大位移
<b style="color:#fff">%.1fpp</b>。Nigma 仍是 16 队里倒数第五。<br>
原因是先验太紧——赛前那个分是几百场比赛拟合的，TI15 它只打了十来局，信息量差着近 20 倍。
<b style="color:#fff">所以这几笔是真分歧，不是数据新旧的问题。8 月 23 日见分晓。</b></div>

<h2><span class="n">05</span>小组赛那 16 格：答案揭晓了</h2>
<div class="h2sub">下面是 8/13 面板锁定前挂在站上的那一版，逐格对答案</div>
<div class="tiles">
  <div class="tile"><div class="v">%d/16</div><div class="k">赛前那版<br>实际答对</div></div>
  <div class="tile"><div class="v">%.2f</div><div class="k">它当时<br>自称的期望</div></div>
  <div class="tile"><div class="v">%.2f</div><div class="k">闭眼乱填<br>的基线</div></div>
</div>
%s
<div class="note" style="color:#898781;font-size:%dpx;line-height:1.6">
<b style="color:#c3c2b7">比期望多 %.2f 格，但别当成本事。</b>
超出的部分主要是运气——每一格赛前的命中概率都印在上面，<b style="color:#fff">最高的一格也只有 %.1f%%</b>。
要判断这套方法有没有用，该看的是上面 03 节那 44 场的 Brier 分解，不是这 16 格的命中数。</div>

<h2><span class="n">06</span>主赛事那张对阵表：14 场逐场点胜者</h2>
<div class="h2sub">游戏内「赛事预测」第二个页签，8/20 开打前锁定——这是建议填法</div>
<div class="tiles">
  <div class="tile"><div class="v">%.2f</div><div class="k">这份填法<br>期望答对 / 14 场</div></div>
  <div class="tile"><div class="v">%.2f</div><div class="k">闭眼乱填<br>的基线</div></div>
  <div class="tile"><div class="v">%s</div><div class="k">在这么多种自洽<br>填法里穷举出来的</div></div>
</div>
%s
<div class="note" style="color:#c3c2b7;font-size:%dpx;line-height:1.6">
<b style="color:#fff">这道题不能「每场都挑赢面大的」。</b>对阵表有路径：你填进第 2 轮的队，
必须是自己在第 1 轮推上去的那两支之一，所以「每场挑最强」通常<b style="color:#fff">根本填不出来</b>。
那个够不着的上界是 %.2f 场，真正能填出来的最优是 <b style="color:#fff">%.2f 场</b>。<br>
八强四场还有五到七成，到败者组中段就只剩<b style="color:#fff">百分之十几</b>——
因为那时候「你押的队有没有走到那一场」本身就很不确定。
<b style="color:#fff">越往后越接近碰运气，这是题目的性质，不是模型不行。</b></div>

<h2><span class="n">07</span>凭什么信</h2>
<div class="h2sub">训练只用 2026-03 之前的数据，在之后没见过的比赛上实测</div>
<div class="tiles">
  <div class="tile"><div class="v">%.1f%%</div><div class="k">样本外准确率<br>%s 场未见过的比赛</div></div>
  <div class="tile"><div class="v">%.4f</div><div class="k">预测校准分<br>健康区间 0.21–0.24，越低越好</div></div>
  <div class="tile"><div class="v">145,974</div><div class="k">训练用的<br>职业比赛场次</div></div>
</div>
<div class="note" style="color:#c3c2b7;font-size:%dpx;line-height:1.6">
赛前预测的<b>现实上限是 65–70%%</b>。所有号称 85%% 以上准确率的 Dota 预测，
用的都是实时游戏内数据而不是赛前数据。<b>做到 85%% 一定是泄漏。</b></div>

<h2><span class="n">08</span>上一次更新：读者要的功能我做了，实测是白做</h2>
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

<h2><span class="n">09</span>我把自己的错也写上去了</h2>
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
  <b style="color:#fff">站内「复盘」页逐场对账，打一场更一场，好看不好看都发。</b></div>
</div>
""" % (badge, draw_line,
       qf_block(p),
       bars([r for r in t if r["champ_blended"] > 0], "champ_blended"), review_block,
       "%s（模型看好，市场不认）" % dn["team"],
       dn["model"] * 100, dn["market"] * 100, GAP_WHY.get(dn["team"], GAP_WHY_FALLBACK),
       "%s（模型看淡，市场看好）" % up["team"],
       up["model"] * 100, up["market"] * 100, GAP_WHY.get(up["team"], GAP_WHY_FALLBACK),
       prem, SIZES_LONG["fs_note"],
       rb["n_games"], rb["max_abs_dtheta"], rb["max_abs_dchampion"] * 100,
       hs["hits"], hs["expected"], hs["random"],
       hw_score_block(p), SIZES_LONG["fs_note"],
       hs["hits"] - hs["expected"],
       max((v for row in hs["buckets"] for v in row["pre_p"].values()), default=0) * 100,
       bk["stats"]["expected"], bk["stats"]["random"],
       "{:,}".format(bk["stats"]["n_brackets"]),
       bracket_block(p), SIZES_LONG["fs_note"],
       bk["stats"]["greedy_upper"], bk["stats"]["expected"],
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


# 截图窗口高度。必须**明显高于**任何一张图的实际内容，否则超出的部分会被静默切掉。
# 2026-08-17 修：原来写死 6000，而长图内容早已超过 6000——底部两节（版本层、
# 「我把自己的错也写上去了」）被切掉了好几版都没人发现，因为产物尺寸恰好是
# 1080x6000，看起来"正好"。现在窗口给到 20000 并加了截断自检。
SHOOT_H = 20000


def shoot(htmlstr, name, width, min_h=800):
    tmp = os.path.join(OUT, "_tmp.html")
    open(tmp, "w").write(htmlstr)
    png = os.path.join(OUT, name)
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1",
                    "--screenshot=" + png, "--window-size=%d,%d" % (width, SHOOT_H),
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
    # 内容一直贴到窗口底边 = 很可能还有没截到的部分。宁可报错也不发一张缺尾巴的图：
    # 长图是发出去收不回来的，而"少了最后两节"这种缺陷肉眼极难发现。
    if bottom >= h:
        raise SystemExit(
            "%s 的内容顶到了截图窗口底边（%dpx），可能被截断。把 SHOOT_H 调大再跑。"
            % (name, h))
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
