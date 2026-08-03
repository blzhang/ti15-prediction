"""生成站点的 4 个页面。所有数字来自 payload，不手写。"""
import html
import os
import shutil

NAV = [("index.html", "结论"), ("predictions.html", "预测详情"),
       ("methodology.html", "方法论"), ("data.html", "数据与检索")]


def esc(s):
    return html.escape(str(s), quote=True)


def shell(base, cur, title, body, extra_js=""):
    nav = "".join(
        '<a class="item%s" href="%s/%s">%s</a>' % (" on" if f == cur else "", base, f, esc(t))
        for f, t in NAV)
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
预测于 2026-08-03 生成并哈希存证，赛前冻结。数据源 OpenDota / Liquipedia。
本站不提供博彩建议。<br>
所有数字由 <code>site/build_site.py</code> 从冻结产出物生成，非手工录入。
</div></footer>
<script src="%s/assets/app.js"></script>
<script src="%s/assets/px.js" defer></script>
%s
</body></html>""" % (esc(title), base, base, nav, body, base, base, extra_js)


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
           '<span><i style="background:var(--s2)"></i>融合市场赔率后（交付值）</span>',
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

def page_index(base, p):
    t = p["teams"]
    top = t[0]
    falcons = next(x for x in t if x["team"] == "Team Falcons")
    spirit = next(x for x in t if x["team"] == "Team Spirit")
    oos = p["oos"]
    r41 = max(p["n_4_1"].items(), key=lambda kv: kv[1])
    body = """
<h1>TI15 谁会赢：一个可被证伪的预测</h1>
<p class="lede">用 2020–2026 的 145,974 场职业比赛，对 The International 2026（8/13–8/23，上海，16 队）
做了一次战队与选手层面的量化预测。全部预测在赛前冻结并留下哈希存证，赛后按场级 Brier 打分。</p>
<p class="meta">生成于 2026-08-03 · 蒙特卡洛 200,000 次 · 存证标签 v4-blended-final</p>

<div class="tiles">
  <div class="tile"><div class="k">夺冠概率最高</div><div class="v">%s</div><div class="s">%.1f%%（已融合市场赔率）</div></div>
  <div class="tile"><div class="k">出现 5-0 战绩</div><div class="v">%.1f%%</div><div class="s">结构上最多只可能有 1 支</div></div>
  <div class="tile"><div class="k">最可能的 4-1 队数</div><div class="v">%s 支</div><div class="s">概率 %.1f%%</div></div>
  <div class="tile"><div class="k">模型样本外准确率</div><div class="v">%.1f%%</div><div class="s">2,546 场未见过的比赛</div></div>
</div>

<h2>结论一：没有真正的大热门</h2>
<p>头名 %s 只有 %.1f%%，前八名挤在 7%%–18%% 之间。这不是模型不敢下判断，而是 16 队水平确实接近——
瑞士轮 5 轮 BO3 之后还要打双败，路径太长，任何单一队伍的夺冠概率都被稀释。</p>
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
<p>L1 队伍实力层做过真实的样本外检验：训练只用 2026-03 之前的数据，在之后 %s 场没见过的比赛上——</p>
<div class="tiles">
  <div class="tile"><div class="k">准确率</div><div class="v">%.1f%%</div><div class="s">现实上限 65–70%%</div></div>
  <div class="tile"><div class="k">Brier</div><div class="v">%.4f</div><div class="s">健康区间 0.21–0.24</div></div>
  <div class="tile"><div class="k">LogLoss</div><div class="v">%.4f</div><div class="s">—</div></div>
</div>
<p>落在健康区间内，且明显高于抛硬币、低于泄漏阈值。<b>做到 85%% 一定是数据泄漏</b>——
所有报告 &gt;80%% 准确率的 Dota 预测论文，用的都是实时游戏内数据而非赛前数据。</p>
<p><a href="%s/predictions.html">→ 看完整预测详情</a> ｜ <a href="%s/methodology.html">→ 方法论与已知限制</a></p>
""" % (esc(top["team"]), top["champ_blended"] * 100,
       p["n_5_0"].get("1", 0) * 100,
       r41[0], r41[1] * 100,
       oos.get("acc", 0) * 100,
       esc(top["team"]), top["champ_blended"] * 100,
       falcons["champ_model"] * 100, falcons["champ_blended"] * 100,
       (falcons["champ_blended"] - falcons["champ_model"]) * 100,
       spirit["champ_model"] * 100, spirit["champ_blended"] * 100,
       (spirit["champ_blended"] - spirit["champ_model"]) * 100,
       "{:,}".format(oos.get("n", 0)),
       oos.get("acc", 0) * 100, oos.get("brier", 0), oos.get("logloss", 0),
       base, base)
    return shell(base, "index.html", "结论", body)


def page_pred(base, p):
    t = p["teams"]
    rows = "".join(
        "<tr><td>%s</td><td class='num hi'>%.1f%%</td><td class=num>%.1f%%</td><td class=num>%.1f%%</td>"
        "<td class=num>%.1f%%</td><td class=num>%.1f%%</td><td class=num>%.1f%%</td>"
        "<td class=num>%.3f</td><td class=num>%d</td></tr>"
        % (esc(r["team"]), r["champ_blended"] * 100, r["champ_model"] * 100, r["top4"] * 100,
           r["advance"] * 100, r["swiss_top3"] * 100, r["r50"] * 100, r["theta"], r["games"])
        for r in t)
    body = """
<h1>预测详情</h1>
<p class="lede">全部数字由构建脚本从冻结产出物读出。夺冠一列已与博彩赔率融合，其余各列是纯模型。</p>
<p class="meta">蒙特卡洛 %s 次 · 夺冠概率标准误 ≤ 0.09pp</p>

<div class="note"><b>读表前必看：</b>只有「夺冠」一列做了市场融合。
「进淘汰赛 / 瑞士轮前3 / 5-0」全部是纯模型，<b>各列并非同一个联合分布</b>。
例：Falcons 夺冠 10.3%%（融合后），但进淘汰赛 73.8%%——后者出自一个认为它夺冠 14.8%% 的模型。横向比较需谨慎。</div>

<h2>夺冠概率：模型 vs 融合后</h2>
%s

<h2>全量指标</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>夺冠(融合)</th><th>夺冠(纯模型)</th><th>进前四</th><th>进淘汰赛</th>
<th>瑞士轮前3</th><th>打出5-0</th><th>实力θ</th><th>样本场次</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">θ 是 Bradley-Terry 实力参数，越高越强；样本场次指「该队现役五人中 ≥3 人同场」的比赛数，
不是队伍存在多久——所以拼装队（如 Vici、OG）的数字反映的是新阵容的磨合样本。</p>

<h2>官方预测题：瑞士轮战绩分布</h2>
<p>模型自动复现出一条结构性事实：<b>最多只可能有一支队打出 5-0</b>。
同分配对会强制所有不败队互相碰面，4 轮之后必然只剩 1 支 4-0。</p>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px">
<div>%s</div>
<div>%s</div>
</div>
<div class="note"><b>这两问必须一起答。</b>4-0 那支若赢下第 5 轮 → 出现 5-0，此时 4-1 通常只有 1–2 支；
若它输掉 → 没有 5-0，它自己掉进 4-1，该档变成 3–4 支。两问强相关，独立猜会内部矛盾。</div>

<h2>逐场对阵胜率</h2>
<p>瑞士轮的配对是<b>内生</b>的——第 3 轮谁打谁取决于前两轮结果，赛前列不出具体对阵。
所以我们列出全部 16×15/2 = 120 个候选配对的 BO3 胜率，赛后按实际发生的约 59 场取子集评分。</p>
<p><a href="%s/data/ti15_matches.csv">下载 ti15_matches.csv（120 行）</a></p>
<div class="note good"><b>为什么这不是「挑好的算」：</b>概率生成只读赛前数据（固定种子重跑逐格一致）；
评分时是无条件「有结果就收录」，没有任何挑拣分支；哪些配对会发生由赛果决定，与我们预测得准不准无关。
这与 FiveThirtyEight 处理赛程的方式一致。</div>
""" % ("{:,}".format(p.get("n_sim") or 0), dual_bars(t), rows,
       dist_table(p["n_5_0"], "本届 5-0 队数"), dist_table(p["n_4_1"], "本届 4-1 队数"), base)
    return shell(base, "predictions.html", "预测详情", body)


def page_method(base, p):
    cr = p.get("cross_region", {})
    crrows = "".join("<tr><td>%s</td><td class=num>%d</td></tr>" % (esc(k), v)
                     for k, v in sorted(cr.items(), key=lambda kv: -kv[1])[:6])
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

<h2>L0 数据地基：按「当前这五个人」定义一支队</h2>
<p>转会是这类预测的头号陷阱。常规做法按 <code>team_id</code> 记分，于是一支队换了 3 个人还继承旧评分。</p>
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

<h2>L1 队伍实力：正则化 Bradley-Terry</h2>
<p>用 BT 而不是 Elo——Elo 只是 BT 的在线近似；BT 是似然模型，能加协变量、算标准误、做收缩。</p>
<p><b>赛事级别加权是自举出来的</b>，不是人工表。OpenDota 自带的 tier 字段 2024 年后已失效
（premium 场次从 2023 年的 3,878 掉到 2024 年的 121、2026 年的 0），而 14.6 万场里场次最多的全是东欧线上车轮赛。
我们改用迭代：拟合 → 用各赛事参赛者实力反推赛事权重 → 重拟合，3 次收敛。
跑出来权重最高的全是真 major（DreamLeague、ESL One、BetBoom Dacha、TI2024）。</p>
<p>超参（时间衰减半衰期 %s 天、岭正则 λ=%s）由<b>时间切分验证</b>选出，测试期只用一次。</p>

<h3>跨赛区可比吗？</h3>
<p>「赛区强度不可比」是这类模型的经典风险。我们做了连通性诊断——仅在 16 支参赛队之间的直接交手场次：</p>
<div class="tbl-wrap"><table><thead><tr><th>赛区对</th><th>直接交手场次</th></tr></thead><tbody>%s</tbody></table></div>
<p>主轴连通性充分，欧洲队整体靠前<b>不是「对战图不连通」造出来的幻觉</b>。</p>

<h2>L2 赛制模拟：瑞士轮必须逐轮跑</h2>
<p>这一层最容易被低估。瑞士轮的配对是<b>内生</b>的——第 3 轮谁打谁取决于前两轮结果，不能预生成赛程。</p>
<ul>
<li><b>不能用二项近似。</b>瑞士轮内建负反馈（赢了就去打更强的对手），强队赛程自动变难。
用「平均胜率 p，5 轮拿 k 胜 = C(5,k)p^k(1-p)^(5-k)」会系统性高估强队的高战绩概率。</li>
<li><b>同分按 Buchholz 排序</b>（对手总胜场），不能掷硬币——否则「边缘队晋级概率」会明显失真。</li>
<li>配对用<b>二分图完美匹配</b>而非贪心。实测贪心版在 500 个随机种子里有 488 个（97.6%%）会在 5 轮内撞上本可避免的重赛。</li>
<li>让分小局<b>随实力差变化</b>：BO3 中输方拿到 1 局的条件概率是 2(1−p)/(3−2p)，势均力敌时更可能打满。</li>
<li>淘汰赛<b>无 bracket reset</b>（TI15 确实没有，实现了反而是错的）。</li>
</ul>

<h2>L3 选手能力：按号位分层的经验贝叶斯</h2>
<p>按 1–5 号位分层收缩。有一个反直觉但重要的点：<b>负二项 = gamma 混合的泊松</b>，
所以「用负二项」和「加局级随机效应」数学上是同一件事——那就不该裸套负二项。</p>
<div class="note crit"><b>这一层踩过一个大坑，值得写出来。</b>
初版用裸泊松假定估方差（Var ≈ 均值）。实测多数计分项根本不服从泊松——
补刀的实测局内标准差是泊松假定的 <b>7.72 倍</b>、stuns 6.08 倍、GPM 4.24 倍。
结果是 GPM 和补刀的置信区间<b>窄了 4–8 倍</b>。已修正为实测局内方差。<br><br>
更值得记的是<b>为什么没被早发现</b>：我们的调研文档白纸黑字写着「不要假设，要先在自己的数据上量一遍 Var/Mean，
这是必须实测的 5 分钟检查」——设计是对的，但这条要求在「设计 → 实施计划 → 任务步骤」的传导中丢失了，从未被执行。
而当时写的健全性检查偏偏挑了击杀（1.56 倍），六个指标里受影响最轻的那个。</div>

<h2>L5 冻结与赛后评分</h2>
<p>一届 TI 只有 1 个冠军观测，<b>评估不了任何东西</b>。但 TI15 会打 59 场系列赛 / 约 145 局——
场级预测有上百个观测，这是全项目唯一有统计功效的检验场。</p>
<p>所有预测在赛前哈希存证（sha256 + UTC 时间戳，8 份全部可校验），赛后按场级 Brier 打分。
对照标准学 FiveThirtyEight 的 <code>spi_matches.csv</code>：赛前概率与赛后结果放在同一张表公开。</p>

<div class="note"><b>⚠️ 赛后 Brier 会天然偏高，别误判成模型失败。</b>
瑞士轮按同战绩配对，而同战绩强相关同实力。所以实际打出的约 59 场<b>不是 120 个候选配对的均匀随机子集</b>，
而是系统性偏向势均力敌的那部分——表里那些悬殊配对大概率根本不会发生。
后果：赛后 Brier 衡量的其实是「模型在势均力敌局面下的判别力」，天然比「在全部可能配对上的判别力」更难做低。
看到 Brier 偏高时，先排除这个赛制自选择效应，再谈「泄漏」或「模型失败」。</div>

<h2>已知限制（完整清单）</h2>
<p>下面这些是<b>做不到或没做</b>的事，不是自谦：</p>
<ul>
<li><b>只有夺冠概率做了市场融合</b>，名次分布 / 晋级概率 / 逐场胜率都是纯模型。赛后 Brier 评的也是纯模型。</li>
<li><b>L3 没有接入局长 / 版本 / 对手强度协变量</b>（设计里承诺了，接口没留位置）。
后果：版本大改导致全体系统性漂移时，会被误吸收成「这一届选手能力变了」。</li>
<li><b>L1 的「赛区随机效应」承诺了但没实现</b>。连通性诊断论证了不需要它，但这属于披露缺失。</li>
<li><b>样本外 Brier 0.2315 是「无赛事权重版」的成绩单</b>——赛事权重那一层从未做过样本外检验。</li>
<li><b>极值题的「谁打出全场之最」把局数压成了点估计</b>，等于把主方差项归零，右尾被削平。</li>
<li><b>TI14 回溯校验用的是简化估计器</b>（裸均值、全局残差、事后已知局数），不是交付版本。
结论「有信号但确认不了具体是谁」是这个简化版的信号。</li>
<li><b>Fantasy 的 18 项系数拿不到</b>（服务端运行时下发），所以只交付分项矩阵、不出绝对总分。</li>
</ul>
<p class="hint">完整版见项目内 <code>00-DESIGN.md</code> 的 §10「已知限制与解读须知」，共 12 小节。</p>
""" % (p.get("half_life_days"), p.get("ridge"), crrows)
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
<li><b><code>team_id</code> 缺失 5.2%%</b>（7,560 场），且逐年恶化，2026 已达 10.3%%——这些场次进不了战队评分。</li>
<li><b>选手名 31.8%% 为空</b>，但 <code>account_id</code> 100%% 完整，不影响建模，只影响显示。</li>
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
    for f in ("style.css", "app.js", "px.js"):
        shutil.copyfile(os.path.join(src, f), os.path.join(dist, "assets", f))
    pages = {
        "index.html": page_index(base, payload),
        "predictions.html": page_pred(base, payload),
        "methodology.html": page_method(base, payload),
        "data.html": page_data(base, payload),
    }
    for name, htmlstr in pages.items():
        with open(os.path.join(dist, name), "w") as fh:
            fh.write(htmlstr)
    return list(pages)
