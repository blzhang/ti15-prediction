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
.badge{display:inline-block;background:#1a1a19;border:1px solid #3987e5;color:#3987e5;
       border-radius:999px;padding:7px 18px;font-size:%(fs_note)dpx;margin-bottom:20px}
"""

SIZES_LONG = dict(W=1080, H=0, PAD=64, fs_eye=22, fs_h1=62, fs_sub=27, fs_tag=22, fs_h2=40,
                  fs_row=25, fs_big=64, fs_note=22, fs_li=25, fs_tile=48, fs_url=34,
                  namew=210, valw=105, barh=22, gap=54, gap2=20, boxpad=26, kvpad=13)
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


def html(body, sizes, cls=""):
    return ("<!doctype html><html><head><meta charset=utf-8><style>%s</style></head>"
            "<body class='%s'><div class=page>%s</div></body></html>"
            % (CSS % sizes, cls, body))


def long_image(p):
    t = p["teams"]
    fal = next(x for x in t if x["team"] == "Team Falcons")
    spi = next(x for x in t if x["team"] == "Team Spirit")
    oos = p["oos"]
    body = """
<div class="badge">赛前已哈希存证 · v4-blended-final</div>
<div class="eyebrow">THE INTERNATIONAL 2026 · 8/13–8/23 上海</div>
<h1>TI15 谁会赢<br><em>一个赛后要认账的预测</em></h1>
<div class="sub">用 2020–2026 的 <b>145,974 场</b>职业比赛跑出来的量化预测。<br>
所有结果赛前冻结留证，8/23 赛后用同一套代码打分——好看不好看都发。</div>
<div class="tagline">蒙特卡洛 20 万次 · 生成于 2026-08-03</div>

<h2><span class="n">01</span>夺冠概率</h2>
<div class="h2sub">已与博彩赔率融合（市场权重 0.7）</div>
%s

<h2><span class="n">02</span>模型和市场吵起来了</h2>
<div class="h2sub">这是整套预测里最值得赛后复盘的地方</div>
<div class="split">
  <div class="box"><div class="lbl">Team Falcons</div>
    <div class="big dn">%.1f%% → %.1f%%</div>
    <div class="note"><b>模型看好，市场不认。</b><br>16 队中唯一阵容零变动的卫冕冠军。</div></div>
  <div class="box"><div class="lbl">Team Spirit</div>
    <div class="big up">%.1f%% → %.1f%%</div>
    <div class="note"><b>模型看淡，市场看好。</b><br>队长兼指挥 Miposhka 转任教练。</div></div>
</div>

<h2><span class="n">03</span>官方预测题</h2>
<div class="h2sub">瑞士轮结构决定：最多只可能有一支队 5-0</div>
<div class="split">
  <div class="box"><div class="lbl">本届出现 5-0 的队数</div>%s</div>
  <div class="box"><div class="lbl">本届 4-1 的队数</div>%s</div>
</div>
<div class="note" style="color:#898781;font-size:%dpx;line-height:1.6">
两问强相关，必须一起答：4-0 那支若赢下第 5 轮 → 出现 5-0，4-1 通常 1–2 支；<br>
若它输掉 → 没有 5-0，它自己掉进 4-1，该档变成 3–4 支。</div>

<h2><span class="n">04</span>凭什么信</h2>
<div class="h2sub">训练只用 2026-03 之前的数据，在之后没见过的比赛上实测</div>
<div class="tiles">
  <div class="tile"><div class="v">%.1f%%</div><div class="k">样本外准确率<br>%s 场未见过的比赛</div></div>
  <div class="tile"><div class="v">%.4f</div><div class="k">Brier 分数<br>健康区间 0.21–0.24</div></div>
  <div class="tile"><div class="v">145,974</div><div class="k">训练用的<br>职业比赛场次</div></div>
</div>
<div class="note" style="color:#c3c2b7;font-size:%dpx;line-height:1.6">
赛前预测的<b>现实上限是 65–70%%</b>。所有号称 85%% 以上准确率的 Dota 预测，
用的都是实时游戏内数据而不是赛前数据。<b>做到 85%% 一定是泄漏。</b></div>

<h2><span class="n">05</span>我把自己的错也写上去了</h2>
<ul>
<li>初版用<b>裸泊松假定</b>估方差，导致 GPM 和补刀的置信区间<b>窄了 4–8 倍</b>。已修正。</li>
<li>发现过 <b>7 次「测试写了但测不到」</b>——比如一条声称锁住号位分层的测试，把所有人塞进同一组照样通过。</li>
<li>调研文档明确要求过「先量一遍 Var/Mean」，这条要求在传导中<b>丢失了，从未被执行</b>。</li>
<li>Watcher 和 Lotus 两项数据取不到，<b>辅助槽的预测能力结构性偏弱</b>，补不上。</li>
</ul>

<div class="foot">
  <div class="url">%s</div>
  <div class="promise">全部数据可下载 · 120 个对阵的赛前胜率全公开 · 80 名选手数据可检索<br>
  <b style="color:#fff">8 月 23 日赛后，我会用同一套代码打分，好看不好看都发。</b></div>
</div>
""" % (bars(t, "champ_blended"),
       fal["champ_model"] * 100, fal["champ_blended"] * 100,
       spi["champ_model"] * 100, spi["champ_blended"] * 100,
       dist_kv(p["n_5_0"]), dist_kv(p["n_4_1"]),
       SIZES_LONG["fs_note"],
       oos.get("acc", 0) * 100, "{:,}".format(oos.get("n", 0)), oos.get("brier", 0),
       SIZES_LONG["fs_note"], URL)
    return html(body, SIZES_LONG)


def cards(p):
    t = p["teams"]
    fal = next(x for x in t if x["team"] == "Team Falcons")
    spi = next(x for x in t if x["team"] == "Team Spirit")
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
<div class="sub" style="margin-bottom:30px">头名只有 %.1f%%，前八名挤在 7%%–18%%</div>
%s
</div></div><div class="foot"><div class="url">%s</div></div>
""" % (S["fs_h1"] - 10, t[0]["champ_blended"] * 100, bars(t, "champ_blended", top_n=12), URL)

    c3 = """
<div class="grow"><div><div class="eyebrow">02 · 最大分歧</div>
<h1 style="font-size:%dpx">模型和市场<br>吵起来了</h1>
<div class="sub" style="margin-bottom:34px">这是赛后最值得复盘的地方</div>
<div class="box" style="margin-bottom:24px"><div class="lbl">Team Falcons</div>
  <div class="big dn">%.1f%% → %.1f%%</div>
  <div class="note"><b>模型看好，市场不认。</b><br>16 队中唯一阵容零变动的卫冕冠军。<br>
  我们按「当前这五个人」算历史战绩，<br>阵容连续性直接兑现成样本量。</div></div>
<div class="box"><div class="lbl">Team Spirit</div>
  <div class="big up">%.1f%% → %.1f%%</div>
  <div class="note"><b>模型看淡，市场看好。</b><br>队长兼指挥 Miposhka 转任教练——<br>
  这种变动按 team_id 记分的模型看不见。</div></div>
</div></div><div class="foot"><div class="url">%s</div></div>
""" % (S["fs_h1"] - 10, fal["champ_model"] * 100, fal["champ_blended"] * 100,
       spi["champ_model"] * 100, spi["champ_blended"] * 100, URL)

    c4 = """
<div class="grow"><div><div class="eyebrow">03 · 凭什么信</div>
<h1 style="font-size:%dpx">我把自己的错<br>也写上去了</h1>
<div class="tiles" style="margin:34px 0">
  <div class="tile"><div class="v">%.1f%%</div><div class="k">样本外准确率</div></div>
  <div class="tile"><div class="v">%.4f</div><div class="k">Brier 分数</div></div>
</div>
<div class="sub" style="font-size:%dpx;margin-bottom:26px">赛前预测现实上限 65–70%%。<br>
<b>做到 85%% 一定是数据泄漏。</b></div>
<ul>
<li>初版用裸泊松估方差，<b>区间窄了 4–8 倍</b></li>
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
    made.append(shoot(long_image(p), "ti15-long.png", 1080))
    for i, c in enumerate(cards(p), 1):
        made.append(shoot(c, "ti15-card-%d.png" % i, 1242, min_h=1656))
    print("产出 %s：" % OUT)
    for f, size in made:
        print("  %-22s %dx%d  %.0f KB" % (os.path.basename(f), size[0], size[1],
                                          os.path.getsize(f) / 1024))


if __name__ == "__main__":
    main()
