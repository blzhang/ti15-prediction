"""L6 八强前瞻：小组赛结束后，对剩下 14 场淘汰赛的精确预测。

设计文档：docs/superpowers/specs/2026-08-16-playoffs-forecast-design.md

与 l2_simulate 的关系
---------------------
l2_simulate 是**全赛事**口径的主链路：它从瑞士轮第一轮开始 replay，把已完赛的照抄、
没打的模拟，一路走到冠军。它必须保持这个形状，因为复盘页要拿「赛前那一版」和
「打到第 N 场那一版」逐版对账。

本模块只回答一个**条件问题**：小组赛已经全部结束、八强对阵已经公布，
剩下这 14 场会怎样。因为条件已经很强，可以做两件 l2_simulate 做不到的事：

  1. **精确枚举，不抽样。** 8 队双败共 14 场，实质路径 8192 条，穷举得到的是精确
     概率。实测 0.3 秒（含对实力不确定性抽 6000 次后平均），比 20 万次蒙特卡洛
     又快又准（后者在冠军概率上仍有约 0.1pp 的抽样噪声）。
  2. **逐场、逐轮的对阵概率。** 「下一轮最可能是谁打谁」这种量在全赛事模拟里要
     额外埋计数器，在枚举里是天然产物——每条路径本来就带着完整的对阵序列。

两者的冠军概率必须互相吻合（差值只应来自 l2_simulate 的抽样噪声），
tests/test_l6_playoffs.py 把这条钉成断言。**本模块不修改 bracket.py 与 l2_simulate.py。**

三套口径
--------
model    赛前冻结的实力分。训练截止 2026-08-02，**没有见过 TI15 任何一局**。
updated  把 TI15 已打完的 109 局按贝叶斯折进实力分之后（诊断用，见下）。
blended  反解一组「隐含实力」，使枚举出的冠军概率恰好等于 model/l2_blended.json
         里的融合值（模型 ⊕ 市场，市场权重 0.7）；随后逐场胜率、各轮晋级、
         名次分布全部从这组隐含实力读出。

为什么要反解隐含实力：市场只开夺冠盘，没有「谁进四强」「QF 谁赢」的盘口。
若冠军概率用融合值、逐场胜率用纯模型值，同一页里两组数字来自两套参数，
读者按逐场胜率自己乘一遍得不到页面上的冠军概率。反解之后整页出自同一套参数。

**这个反解是恰好可辨识的，不是拟合**：8 支队概率和为 1 → 7 个独立目标；θ* 有 8 个
分量、锚定均值后 7 个自由度。恰好定解，不存在过参数化。

⚠️ 隐含实力的**局限**（页面上必须写出来）：这一步假定「融合后的冠军分布是由某组
BT 实力经这套赛制生成的」。市场若因赛制之外的理由（伤病、签表软硬的主观判断）
给某队定价，反解会把那部分理由**强行翻译成实力**。所以隐含实力是「市场若只通过
实力表达观点，它在说什么」，不是「这支队真实有多强」。

用法：
    python3 -m model.l6_playoffs                    # 写 reports/p8_playoffs.json
    python3 -m model.l6_playoffs --out /tmp/x.json  # 换个输出路径
"""
import argparse
import itertools
import json
import os
import sys

import numpy as np
from scipy.optimize import least_squares, minimize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)          # 与 l2_simulate.py / l3_player.py 一致的裸导入 shim
import results as results_mod

DEFAULT_OUT = os.path.join(ROOT, "reports", "p8_playoffs.json")
N_DRAW = 6000                     # 对 theta 后验的抽样次数（枚举本身是精确的）
SEED = 20260816

# 各阶段的开赛时间（Liquipedia The_International/2026，2026-08-16 抓取）。
# 只用于展示，不参与任何计算。
STAGE_TIME = {
    "UBQF1": "8/20 10:00", "UBQF2": "8/20 13:00",
    "UBQF3": "8/20 16:00", "UBQF4": "8/20 19:00",
    "LBR1-1": "8/21 10:00", "LBR1-2": "8/21 13:00",
    "UBSF1": "8/21 16:00", "UBSF2": "8/21 19:00",
    "LBQF-2": "8/22 10:00", "LBQF-1": "8/22 13:00",
    "UBF": "8/22 16:00", "LBSF": "8/22 19:00",
    "LBF": "8/23 10:00", "GF": "8/23 13:00",
}
STAGE_CN = {
    "UBQF1": "胜者组八强 1", "UBQF2": "胜者组八强 2",
    "UBQF3": "胜者组八强 3", "UBQF4": "胜者组八强 4",
    "UBSF1": "胜者组四强 1", "UBSF2": "胜者组四强 2", "UBF": "胜者组决赛",
    "LBR1-1": "败者组首轮 1", "LBR1-2": "败者组首轮 2",
    "LBQF-1": "败者组八强 1", "LBQF-2": "败者组八强 2",
    "LBSF": "败者组四强", "LBF": "败者组决赛", "GF": "总决赛（BO5）",
}
# 枚举里累计**对阵**概率的阶段（UBQF 的对阵是已知事实，不需要概率）
STAGES = ("UBSF1", "UBSF2", "LBR1-1", "LBR1-2", "UBF",
          "LBQF-1", "LBQF-2", "LBSF", "LBF", "GF")
# 累计**胜者**概率的阶段 = 全部 14 场。游戏内主赛事预测面板要逐场点胜者，
# 八强那四场也要填，所以它们必须在内。
ALL_STAGES = ("UBQF1", "UBQF2", "UBQF3", "UBQF4") + STAGES

# 游戏内面板给每场比赛的字母编号（2026-08-17 由用户客户端截图核对）。
# 面板结构：胜者组第1轮 A-D、第2轮 E-F、胜者组决赛 G、总决赛；
# 败者组第1轮两场、第2轮两场（「F的败者」「E的败者」各配一场）、第3轮、败者组决赛。
PANEL_LABEL = {
    "UBQF1": "A", "UBQF2": "B", "UBQF3": "C", "UBQF4": "D",
    "UBSF1": "E", "UBSF2": "F", "UBF": "G", "GF": "总决赛",
    "LBR1-1": "败1上", "LBR1-2": "败1下",
    "LBQF-1": "败2上", "LBQF-2": "败2下",
    "LBSF": "败3", "LBF": "败决",
}


# ---------------------------------------------------------------- 枚举
def enumerate_bracket(qf, p3, p5, D):
    """精确枚举 8 队双败的全部路径。

    qf: [(a, b), (c, d), (e, f), (g, h)]，队伍索引；前两场进 UBSF1，后两场进 UBSF2。
    p3[i, j] / p5[i, j] 形状 (D,)：第 d 次抽样下 i 赢 j 的 BO3 / BO5 概率。

    返回 (place, pairs, winners)：
      place[t]        形状 (9, D)，place[t][k] = 该队拿第 k 名的概率（k=1..8）
      pairs[stage]    {(队, 队): 形状 (D,) 的概率}，该阶段由这两队相遇的概率
      winners[stage]  {队: 形状 (D,) 的概率}，该队赢下这一阶段那场比赛的概率

    ⚠️ 每个名次只在「该场胜负被决定的那一层」累加一次。写成嵌套循环时极易在外层
    多套一圈导致重复计数（本模块第一版就是这么错的：LBR1 的 7-8 名写在了 UBSF
    循环里面，被乘了 4 倍，而且**行列和自检照样过不了**——正是那条自检抓出来的）。
    所以下面每个 place[...] 的累加点都注明它依赖哪几层，且只依赖这几层。
    """
    teams = [t for pair in qf for t in pair]
    place = {t: np.zeros((9, D)) for t in teams}
    pairs = {s: {} for s in STAGES}
    # winners[stage][team] = P(该队赢下这一阶段的那场比赛)。抄作业要的就是它：
    # 游戏内的主赛事预测面板是一张对阵表，逐场点胜者，所以要回答的是
    # 「这一场谁赢」而不是「谁最后夺冠」。
    winners = {s: {t: np.zeros(D) for t in teams} for s in ALL_STAGES}

    def add(stage, a, b, w):
        key = (a, b) if a <= b else (b, a)
        cur = pairs[stage].get(key)
        pairs[stage][key] = w.copy() if cur is None else cur + w

    def win(stage, t, w):
        winners[stage][t] += w

    for mq in itertools.product((0, 1), repeat=4):          # 4 场 UBQF
        wq, lq, pq = [], [], np.ones(D)
        for k, (a, b) in enumerate(qf):
            hi, lo = (a, b) if mq[k] == 0 else (b, a)
            wq.append(hi); lq.append(lo); pq = pq * p3[hi, lo]
        for k in range(4):
            win("UBQF%d" % (k + 1), wq[k], pq)      # 只依赖 UBQF 这一层
        # 只依赖 UBQF
        add("UBSF1", wq[0], wq[1], pq)
        add("UBSF2", wq[2], wq[3], pq)
        add("LBR1-1", lq[0], lq[1], pq)
        add("LBR1-2", lq[2], lq[3], pq)

        # 7-8 名只依赖 UBQF + LBR1 —— 必须在 UBSF 循环之外结清
        for mr in itertools.product((0, 1), repeat=2):
            pr = pq.copy()
            lb1 = []
            for k, (a, b) in enumerate(((lq[0], lq[1]), (lq[2], lq[3]))):
                hi, lo = (a, b) if mr[k] == 0 else (b, a)
                lb1.append(hi); pr = pr * p3[hi, lo]
            for k, (a, b) in enumerate(((lq[0], lq[1]), (lq[2], lq[3]))):
                place[b if mr[k] == 0 else a][7] += pr
            win("LBR1-1", lb1[0], pr); win("LBR1-2", lb1[1], pr)

        for ms in itertools.product((0, 1), repeat=2):      # 2 场 UBSF
            sfw, sfl, ps = [], [], pq.copy()
            for k, (a, b) in enumerate(((wq[0], wq[1]), (wq[2], wq[3]))):
                hi, lo = (a, b) if ms[k] == 0 else (b, a)
                sfw.append(hi); sfl.append(lo); ps = ps * p3[hi, lo]
            win("UBSF1", sfw[0], ps); win("UBSF2", sfw[1], ps)
            add("UBF", sfw[0], sfw[1], ps)                  # 依赖 UBQF+UBSF

            for mr in itertools.product((0, 1), repeat=2):  # 2 场 LBR1
                lb1w, pr = [], ps.copy()
                for k, (a, b) in enumerate(((lq[0], lq[1]), (lq[2], lq[3]))):
                    hi, lo = (a, b) if mr[k] == 0 else (b, a)
                    lb1w.append(hi); pr = pr * p3[hi, lo]
                # 败者组交叉连接：LBR1-1 胜者对 UBSF2 负者，LBR1-2 胜者对 UBSF1 负者
                lbqf = ((lb1w[0], sfl[1]), (lb1w[1], sfl[0]))
                add("LBQF-1", lbqf[0][0], lbqf[0][1], pr)
                add("LBQF-2", lbqf[1][0], lbqf[1][1], pr)

                for m2 in itertools.product((0, 1), repeat=2):   # 2 场 LBQF → 5-6 名
                    lb2w, p2 = [], pr.copy()
                    for k, (a, b) in enumerate(lbqf):
                        hi, lo = (a, b) if m2[k] == 0 else (b, a)
                        lb2w.append(hi); p2 = p2 * p3[hi, lo]
                    for k, (a, b) in enumerate(lbqf):
                        place[b if m2[k] == 0 else a][5] += p2
                    win("LBQF-1", lb2w[0], p2); win("LBQF-2", lb2w[1], p2)
                    add("LBSF", lb2w[0], lb2w[1], p2)

                    for mv in (0, 1):                            # LBSF → 第 4 名
                        hi, lo = (lb2w[0], lb2w[1]) if mv == 0 else (lb2w[1], lb2w[0])
                        pv = p2 * p3[hi, lo]
                        place[lo][4] += pv
                        win("LBSF", hi, pv)

                        for mu in (0, 1):                        # UBF
                            ubfw, ubfl = (sfw[0], sfw[1]) if mu == 0 else (sfw[1], sfw[0])
                            pu = pv * p3[ubfw, ubfl]
                            win("UBF", ubfw, pu)
                            add("LBF", hi, ubfl, pu)

                            for mf in (0, 1):                    # LBF → 第 3 名
                                lbfw, lbfl = (hi, ubfl) if mf == 0 else (ubfl, hi)
                                pf = pu * p3[lbfw, lbfl]
                                place[lbfl][3] += pf
                                win("LBF", lbfw, pf)
                                add("GF", ubfw, lbfw, pf)
                                # 总决赛 BO5，无 bracket reset：两个结果一次结清
                                pw = p5[ubfw, lbfw]
                                place[ubfw][1] += pf * pw
                                place[lbfw][2] += pf * pw
                                place[lbfw][1] += pf * (1 - pw)
                                place[ubfw][2] += pf * (1 - pw)
                                win("GF", ubfw, pf * pw)
                                win("GF", lbfw, pf * (1 - pw))
    return place, pairs, winners


def probs_from_theta(th):
    """th 形状 (D, n) → p1/p3/p5 形状 (n, n, D)。公式与 l2_simulate.run_one 顶部一致。"""
    d = th[:, :, None] - th[:, None, :]
    p1 = 1.0 / (1.0 + np.exp(-d))
    p3 = p1 ** 2 * (3 - 2 * p1)
    q = 1 - p1
    p5 = p1 ** 3 * (1 + 3 * q + 6 * q ** 2)
    return tuple(np.ascontiguousarray(x.transpose(1, 2, 0)) for x in (p1, p3, p5))


def integrate(qf, th_hat, se, n_draw=N_DRAW, seed=SEED):
    """对实力不确定性积分：抽 n_draw 次 theta ~ N(th_hat, se)，每次精确枚举后平均。

    与 l2_simulate 的方法论一致（那边是每次模拟重抽一次 theta）；差别只在于
    这里对每次抽样做的是精确枚举而不是走一条随机路径。
    """
    rng = np.random.default_rng(seed)
    th = th_hat[None, :] + se[None, :] * rng.standard_normal((n_draw, len(th_hat)))
    p1, p3, p5 = probs_from_theta(th)
    place, pairs, winners = enumerate_bracket(qf, p3, p5, n_draw)
    return ({t: place[t].mean(axis=1) for t in place},
            {s: {k: float(v.mean()) for k, v in d.items()} for s, d in pairs.items()},
            p3.mean(axis=2),
            {s: {t: float(v.mean()) for t, v in d.items()} for s, d in winners.items()})


# ---------------------------------------------------------------- 自检
# 各名次的席位数：1-4 名各 1 席，5-6 与 7-8 各 2 席。并列名次记在较小的那个
# 编号上，所以第 6、8 列恒为 0。加起来正好 8 支队。
SEATS = (1, 1, 1, 1, 2, 0, 2, 0)


def check_coherent(place):
    """名次分布的结构性自洽。两条都是恒等式，不是「应该差不多」。

    · 每支队恰好落在一个名次 → 每队 8 个名次概率和为 1
    · 每个名次的席位数固定 → SEATS

    接受 (9,) 的均值，也接受 (9, D) 的逐抽样矩阵——后者会**逐次抽样**检查，
    这更严：均值对了不代表每一次抽样都对（重复计数在某些抽样上可能相互抵消）。
    """
    rows = {t: np.asarray(r, dtype=float).reshape(9, -1) for t, r in place.items()}
    for t, r in rows.items():
        s = r[1:9].sum(axis=0)
        bad = np.argmax(np.abs(s - 1.0))
        if abs(s[bad] - 1.0) > 1e-9:
            raise AssertionError(
                "队伍 %r 的名次概率和为 %.12f，应为 1（第 %d 次抽样）"
                % (t, s[bad], bad))
    col = sum(rows.values())
    for k, w in zip(range(1, 9), SEATS):
        bad = np.argmax(np.abs(col[k] - w))
        if abs(col[k][bad] - w) > 1e-9:
            raise AssertionError(
                "第 %d 名的席位数为 %.12f，应为 %d（第 %d 次抽样）"
                % (k, col[k][bad], w, bad))


# ---------------------------------------------------------------- 隐含实力
def _logit(p):
    p = min(max(float(p), 1e-9), 1 - 1e-9)
    return np.log(p / (1 - p))


def solve_implied(qf, th_hat, se, target, alive_idx, n_draw=N_DRAW, seed=SEED,
                  damp=0.45, tol=2e-4, max_iter=400):
    """反解隐含实力：让枚举出的冠军概率等于 target。

    target: {队伍索引: 目标冠军概率}，8 支存活队，和为 1。
    不动点迭代 θᵢ += damp·[logit(目标ᵢ) − logit(当前ᵢ)]；冠军概率对自身实力单调
    递增，所以这个迭代稳定收敛。每轮把存活八队的均值锚回原水平——**BT 实力只有
    相对意义**，不锚的话整体会随机漂移，导致隐含实力没法和原实力分并排看。

    收敛失败直接抛错，不返回一个没收敛的结果：没收敛意味着页面上「逐场胜率」和
    「冠军概率」对不上，而这正是引入隐含实力要解决的问题。

    ⚠️ 这个函数只拟合冠军盘。有单场盘时应该用 solve_implied_joint——
    2026-08-17 实测证明只拟合冠军盘会在单场上错得很远（见那个函数的说明）。
    """
    th = th_hat.copy()
    anchor = th_hat[alive_idx].mean()
    for it in range(1, max_iter + 1):
        place, _, _, _ = integrate(qf, th, se, n_draw=n_draw, seed=seed)
        tot = sum(place[t][1] for t in alive_idx)
        cur = {t: place[t][1] / tot for t in alive_idx}
        err = max(abs(cur[t] - target[t]) for t in alive_idx)
        if err < tol:
            return th, it, err
        for t in alive_idx:
            th[t] += damp * (_logit(target[t]) - _logit(cur[t]))
        th[alive_idx] -= th[alive_idx].mean() - anchor
    raise RuntimeError(
        "隐含实力反解在 %d 轮内没收敛（最大偏差 %.6f > %.6f）。"
        "不返回未收敛的结果——那会让页面上的逐场胜率与冠军概率对不上。"
        % (max_iter, err, tol))


def solve_implied_joint(qf, th_hat, se, champ_target, match_target, alive_idx,
                        n_draw=2000, seed=SEED, w_match=3.0):
    """同时拟合**冠军盘**与**八强单场盘**的隐含实力（最小二乘）。

    为什么必须这么改（2026-08-17 实测）
    ----------------------------------
    只拟合冠军盘时，反解出的隐含实力在单场上错得很远：
        VISION vs BoomBoys   反解 65.4%，单场盘直接报 80.5%（低 15.1pp）
        Nigma  vs Falcons    反解 41.1%，单场盘直接报 34.5%（高  6.6pp）
    两个方向都错。原因正是这一版之前就写在页面上的那条局限——冠军盘里
    「市场给某队定价」的理由未必是实力（可能是对签表软硬的判断），把它硬翻译
    成实力，就会在单场上系统性偏掉。单场盘是**直接价格**，不需要翻译。

    所以现在两个市场一起拟合：7 个自由参数（8 队锚定均值）对 7+4=11 个目标，
    **超定**，只能最小二乘。这本身是个诚实的结构——**残差就是两个市场的分歧量**，
    落盘后写在页面上，而不是假装能同时满足。

    w_match：单场盘目标的权重。默认 **3.0**，理由是这四个是对**这四场**的直接价格，
    而冠军概率是往后推演 14 场的**间接**量；直接价格没道理被间接量推翻。
    实测 w=3 时单场残差降到 3.3pp，代价是冠军残差 6.0pp——两个市场就是差这么多，
    这个差本身要写在页面上，不能靠调权重藏起来。

    ⚠️ 这个权重是判断，不是算出来的。所以 build() 会扫一遍 w∈{0,1,3,10} 落盘，
    并且**检查建议填法在整个范围内稳不稳**。2026-08-17 实测：14 格里只有
    「C：Liquid vs Yandex」会翻，而那格本来就是 49.9% vs 50.1% 的抛硬币——
    也就是说这个权重怎么选，对抄作业的结论几乎没有影响。这条比权重本身更值得写。

    返回 (theta, info)，info 含逐目标残差（概率尺度，便于人读）。
    """
    idx = list(alive_idx)
    anchor = th_hat[idx].mean()

    def unpack(x):
        """7 个自由参数 → 8 队实力（第 8 个由均值锚定确定）。"""
        th = th_hat.copy()
        full = np.append(x, 0.0)
        full = full - full.mean() + anchor
        th[idx] = full
        return th

    def residuals(x):
        th = unpack(x)
        place, _, p3, _ = integrate(qf, th, se, n_draw=n_draw, seed=seed)
        tot = sum(place[t][1] for t in idx)
        res = [_logit(place[t][1] / tot) - _logit(champ_target[t]) for t in idx]
        for (a, b), p_a in match_target.items():
            res.append(w_match * (_logit(p3[a, b]) - _logit(p_a)))
        return np.array(res)

    x0 = th_hat[idx][:-1] - anchor
    sol = least_squares(residuals, x0, method="lm", xtol=1e-8, ftol=1e-8)
    th = unpack(sol.x)

    place, _, p3, _ = integrate(qf, th, se, n_draw=n_draw, seed=seed)
    tot = sum(place[t][1] for t in idx)
    info = {
        "n_targets": len(idx) + len(match_target),
        "n_free_params": len(idx) - 1,
        "w_match": w_match,
        "n_eval": int(sol.nfev),
        "champ_resid": {t: float(place[t][1] / tot - champ_target[t]) for t in idx},
        "match_resid": {"%d|%d" % (a, b): float(p3[a, b] - p_a)
                        for (a, b), p_a in match_target.items()},
    }
    info["max_abs_champ_resid"] = max(abs(v) for v in info["champ_resid"].values())
    info["max_abs_match_resid"] = (max(abs(v) for v in info["match_resid"].values())
                                   if info["match_resid"] else 0.0)
    return th, info


# ---------------------------------------------------------------- 贝叶斯稳健性
def bayesian_update(th_hat, se, games, idx):
    """把已打完的 TI15 逐局结果按贝叶斯折进实力分。

    先验：θ ~ N(θ̂, se²)，即赛前那次拟合的后验。
    似然：每一小局是一次 BT 伯努利试验。
    返回 MAP 估计。

    这不是要替换主模型，是要**量化一个质疑**：「模型没见过 TI15，所以它低估了
    打出好成绩的队」——这个说法对不对，算一下就知道。

    ⚠️ 局限：这里把「赛前实力到今天仍然有效」当成前提，没有为状态漂移放宽先验
    方差。所以它给出的是「TI15 战绩该挪多少」的**下界**。
    """
    if not games:
        return th_hat.copy()
    a = np.array([idx[g["a"]] for g in games])
    b = np.array([idx[g["b"]] for g in games])
    y = np.array([1.0 if g["a_won"] else 0.0 for g in games])

    def nll(th):
        p = 1.0 / (1.0 + np.exp(-(th[a] - th[b])))
        ll = np.sum(y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12))
        return -(ll - 0.5 * np.sum(((th - th_hat) / se) ** 2))

    return minimize(nll, th_hat.copy(), method="L-BFGS-B").x


def games_from_results(observed, teams):
    """把 results.json 里的系列赛比分摊成逐局的 BT 观测。

    BO3 记的是 2-0 / 2-1，也就是「赢方赢 2 局、输方赢 lg 局」——把系列赛拆成
    小局，样本量从 44 涨到 109，且与 L1 层「按小局拟合」的口径一致
    （l1_strength 用的是逐局 radiant_win，不是系列赛胜负）。
    """
    out = []
    series = [s for r in observed["rounds"].values() for s in r] + list(observed.get("elim") or [])
    for i, j, a_wins, lg in series:
        if a_wins is None:
            continue
        win, lose = (i, j) if a_wins else (j, i)
        for _ in range(2):
            out.append({"a": teams[win], "b": teams[lose], "a_won": True})
        for _ in range(lg or 0):
            out.append({"a": teams[lose], "b": teams[win], "a_won": True})
    return out


# ---------------------------------------------------------------- bit 编码
# 一份自洽填法 = 一个 14 位整数，每一位是一场比赛的二选一，0 表示「上面那个候选」。
#
# 这是路径规则的**唯一权威实现**：抄作业页的前端编辑器要的正是同一个展开函数
# （site/assets_src/bracket.js 的 expand），两边各写一份迟早会漂移，
# 而漂移的表现不是崩溃，是页面静静印出一个跟本模块对不上的期望答对数。
# tests/test_bracket_bits.py 用 node 跑 JS 那一份，与本函数逐位比对 16384 种展开。
#
# 完整的位定义表：docs/superpowers/specs/2026-08-18-bracket-editor-design.md 决定一。
BIT_STAGE = ("UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2",
             "LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "UBF", "LBF", "GF")
N_BITS = len(BIT_STAGE)


def expand(qf, bits):
    """把 14 位整数展开成一份完整且自洽的填法 {阶段: 该阶段你选的那一方}。

    qf 的元素类型不限（队索引或队名都行，原样返回）——正是这一点让
    tests/test_bracket_bits.py 能拿同一份 qf 同时喂给 Python 和 JS 做对照。
    """
    b = [(bits >> k) & 1 for k in range(N_BITS)]
    w = [qf[k][b[k]] for k in range(4)]            # 四场八强的胜者
    l = [qf[k][1 - b[k]] for k in range(4)]        # 四场八强的败者
    e, f = b[4], b[5]
    sf_w = [w[e], w[2 + f]]                        # E / F 的胜者
    sf_l = [w[1 - e], w[3 - f]]                    # E / F 的败者
    lb1 = [l[b[6]], l[2 + b[7]]]                   # 败1上 / 败1下的胜者
    # 败者组交叉：败2上 = 败1上胜者 vs F 的败者；败2下 = 败1下胜者 vs E 的败者。
    # 这两行是整套规则里唯一容易写错的地方，改动前先看设计文档决定一那张表。
    lb2 = [(lb1[0], sf_l[1])[b[8]], (lb1[1], sf_l[0])[b[9]]]
    lb3 = lb2[b[10]]                               # 败3 的胜者
    ubf_w, ubf_l = sf_w[b[11]], sf_w[1 - b[11]]
    lbf = (lb3, ubf_l)[b[12]]                      # 败决的胜者
    champ = (ubf_w, lbf)[b[13]]
    return dict(zip(BIT_STAGE,
                    (w[0], w[1], w[2], w[3], sf_w[0], sf_w[1],
                     lb1[0], lb1[1], lb2[0], lb2[1], lb3, ubf_w, lbf, champ)))


# ---------------------------------------------------------------- 抄作业：整张对阵表
def best_bracket(qf, winners, teams):
    """游戏内主赛事预测面板的最优填法。

    面板长什么样（2026-08-17 由用户客户端截图核对，此前一直是未解缺口——
    01-ti15-facts.md §3.3 记录过「题面由服务端下发，离线途径全部排除」）：
    **它不是分档填空，是一整张对阵表，14 场逐场点胜者**，8/20 前锁定。

    所以这道题的形状与小组赛那 16 格完全不同，不能照搬匈牙利算法：
      · 小组赛那题是**分配**问题（16 队塞进 6 个档位，每档坑数固定）
      · 这题是**路径**问题——你填进「胜者组第2轮」的队，必须是你自己在第1轮
        推上去的那两支之一。后面每一轮的可选项都被前面的选择锁死。

    因此「每场都挑赢面最大的那支」通常不可行（你挑的队可能根本没被你推上来），
    而且即使可行也未必最优。正确做法是在**全部自洽的填法**里搜期望答对最多的一种。

    自洽填法的数量：胜者组 A/B/C/D/E/F/G 各二选一 = 2^7；败者组 6 场各二选一
    = 2^6；总决赛二选一 = 2。合计 **2^14 = 16384** 种——可以穷举，不需要启发式。

    枚举方式是遍历 0..16383 并交给 expand() 按位展开。之所以不是显式嵌套循环
    （2026-08-18 前是 10 层嵌套），是因为抄作业页的前端编辑器需要同一个展开函数，
    而两边各写一份路径规则迟早会漂移。见 expand() 上方的说明。

    期望答对数 = Σ_场次 P(你填的那支队真的赢下这一场)，其中 P 来自精确枚举的
    winners[阶段][队]。注意这个 P 已经包含了「这支队根本没走到这一场」的情形
    （那种路径下它赢不了这一场，概率自然不计入），所以不需要额外乘晋级概率。

    返回 (best, rows, stats)：
      best   {阶段: 队名}
      rows   逐场明细，含该场每个候选的命中概率
      stats  期望答对数、随机填法基线、最优与「逐场贪心」的差距
    """
    best_bits, best_sc, total = -1, -1.0, 0.0
    n = 1 << N_BITS
    for bits in range(n):
        pick = expand(qf, bits)
        sc = sum(winners[st][pick[st]] for st in ALL_STAGES)
        total += sc
        if sc > best_sc:
            best_sc, best_bits = sc, bits
    best = expand(qf, best_bits)
    # 这条断言在位展开下已是同义反复；真正守住「不多不少 16384 种自洽填法」的是
    # tests/test_bracket_bits.py 的双射检查。留着它只为让 stats 的口径一眼可见。
    assert n == 16384, "BIT_STAGE 被改成了 %d 位" % N_BITS

    # 「逐场贪心」对照：每一场都无视自洽性、直接挑该场赢面最大的队。
    # 它给出的是**上界**（通常填不出来，因为路径对不上），用来说明约束值多少分。
    greedy = sum(max(winners[st].values()) for st in ALL_STAGES)

    rows = []
    for st in ALL_STAGES:
        cand = sorted(winners[st].items(), key=lambda kv: -kv[1])
        rows.append({
            "stage": st, "cn": STAGE_CN[st], "panel": PANEL_LABEL[st],
            "time_cst": STAGE_TIME[st],
            "pick": teams[best[st]],
            "p_pick": winners[st][best[st]],
            "top": [{"team": teams[t], "p": p} for t, p in cand[:4] if p > 0.005],
        })
    return ({st: teams[t] for st, t in best.items()}, rows,
            {"expected": best_sc, "random": total / n, "greedy_upper": greedy,
             "n_brackets": n, "n_matches": len(ALL_STAGES),
             # 前端编辑器的初始状态：这份最优填法对应的 14 位整数
             "pick_bits": best_bits})


# ---------------------------------------------------------------- 组装
def view(qf, th, se, teams, alive, n_draw=N_DRAW):
    place, pairs, p3, winners = integrate(qf, th, se, n_draw=n_draw)
    check_coherent(place)
    out = {"place": {}, "stage_pairs": {}, "h2h": {}}
    for t, row in place.items():
        out["place"][teams[t]] = {
            "champion": float(row[1]),
            "final": float(row[1] + row[2]),
            "top4": float(row[1:5].sum()),
            "dist": {str(k): float(row[k]) for k in (1, 2, 3, 4, 5, 7)},
        }
    for stage, d in pairs.items():
        out["stage_pairs"][stage] = sorted(
            [{"a": teams[a], "b": teams[b], "p": v} for (a, b), v in d.items()],
            key=lambda r: -r["p"])
    for x in alive:
        for y in alive:
            if x != y:
                out["h2h"]["%s|%s" % (x, y)] = float(p3[teams.index(x), teams.index(y)])
    return out


def build(n_draw=N_DRAW):
    rating = json.load(open(os.path.join(HERE, "l1_rating.json")))
    teams = list(rating["rating"])
    idx = {t: i for i, t in enumerate(teams)}
    th_hat = np.array([rating["rating"][t] for t in teams])
    se = np.array([rating["rating_se"][t] for t in teams])

    observed = results_mod.load(teams)
    if not observed:
        raise SystemExit("model/results.json 未启用——八强前瞻需要已完赛结果做条件。")
    ubqf = observed.get("ubqf")
    if not ubqf:
        raise SystemExit(
            "model/results.json 里没有 playoffs.ubqf。八强对阵是本模块的前提条件，"
            "缺了它就只能按种子规则近似——而 TI15 的实际对阵与种子规则对不上，"
            "近似出来的是一份错的预测，所以这里直接退出而不是猜。")
    qf = [(a, b) for a, b in ubqf]
    alive = [teams[t] for pair in qf for t in pair]
    alive_idx = [t for pair in qf for t in pair]

    blended = json.load(open(os.path.join(HERE, "l2_blended.json")))
    champ_blend = blended["champion_blended"]
    missing = [t for t in alive if champ_blend.get(t, 0) <= 0]
    if missing:
        raise SystemExit(
            "这些队还在八强里，融合后的夺冠概率却是 0：%s。"
            "多半是 l2_blended.json 比 results.json 旧，请先跑 l2_blend。" % missing)
    tot = sum(champ_blend[t] for t in alive)
    target = {idx[t]: champ_blend[t] / tot for t in alive}

    # 八强单场盘（model/polymarket_matches.json）。有就把它一起拟合进隐含实力——
    # 只拟合冠军盘会在单场上系统性偏掉，见 solve_implied_joint 的说明。
    mpath = os.path.join(HERE, "polymarket_matches.json")
    mkt_matches = json.load(open(mpath)) if os.path.exists(mpath) else None

    # 三套口径
    v_model = view(qf, th_hat, se, teams, alive, n_draw)
    th_upd = bayesian_update(th_hat, se, games_from_results(observed, teams), idx)
    v_upd = view(qf, th_upd, se, teams, alive, n_draw)

    w_mkt = blended.get("w_market") or 0.7
    match_target, match_rows = {}, []
    if mkt_matches:
        for r in mkt_matches["matches"]:
            a, b = idx[r["a"]], idx[r["b"]]
            if (a, b) not in [(x, y) for x, y in qf]:
                raise SystemExit(
                    "单场盘里的 %s vs %s 不在已公布的八强对阵里——"
                    "polymarket_matches.json 与 results.json 的 ubqf 不同步。"
                    % (r["a"], r["b"]))
            p_model = v_model["h2h"]["%s|%s" % (r["a"], r["b"])]
            # 与冠军盘同一套融合规则：log-odds 空间按 w_market 加权
            p_blend = 1.0 / (1.0 + np.exp(
                -((1 - w_mkt) * _logit(p_model) + w_mkt * _logit(r["p_a"]))))
            match_target[(a, b)] = float(p_blend)
            match_rows.append({
                "stage": r["stage"], "a": r["a"], "b": r["b"],
                "p_market": r["p_a"], "p_model": p_model, "p_blended": float(p_blend),
                "volume": r["volume"], "best_bid": r["best_bid"], "best_ask": r["best_ask"],
            })

    if match_target:
        nd_fit = max(1500, n_draw // 4)
        th_imp, solve_info = solve_implied_joint(
            qf, th_hat, se, target, match_target, alive_idx, n_draw=nd_fit)
        solve_info["mode"] = "joint（冠军盘 + 八强单场盘，最小二乘）"
        # w_match 是个判断，不是算出来的。所以把它扫一遍，把「这个判断值多少
        # 个百分点」直接落盘——w=0 就是只信冠军盘，w 越大越偏向单场盘。
        sens, sens_pick, sens_h2h = {}, {}, {}
        for w in (0.0, 1.0, 3.0, 10.0):
            th_w, _ = solve_implied_joint(qf, th_hat, se, target, match_target,
                                          alive_idx, n_draw=nd_fit, w_match=w)
            pl_w, _, _, _ = integrate(qf, th_w, se, n_draw=nd_fit)
            tot_w = sum(pl_w[t][1] for t in alive_idx)
            sens["%.1f" % w] = {teams[t]: float(pl_w[t][1] / tot_w) for t in alive_idx}
            _, _, p3_w, win_w = integrate(qf, th_w, se, n_draw=nd_fit)
            sens_pick["%.1f" % w] = best_bracket(qf, win_w, teams)[0]
            # 逐场胜率也存一份：w=0 那一档就是「只从冠军盘翻译」的结果，
            # 页面要拿它跟单场盘的直接报价对比，说明上一版偏了多少。
            sens_h2h["%.1f" % w] = {
                "%s|%s" % (teams[a], teams[b]): float(p3_w[a, b]) for a, b in qf}
        solve_info["w_match_sensitivity"] = sens
        solve_info["w_match_h2h"] = sens_h2h
        solve_info["w_match_swing_pp"] = max(
            abs(sens["10.0"][t] - sens["0.0"][t]) for t in alive) * 100
        # 权重怎么选，对**建议填法**有没有影响——这比概率摆动更决定读者要不要在意
        base = sens_pick["3.0"]
        solve_info["pick_unstable_stages"] = sorted(
            st for st in ALL_STAGES
            if len({sens_pick[k][st] for k in sens_pick}) > 1)
        solve_info["pick_stable_count"] = len(ALL_STAGES) - len(solve_info["pick_unstable_stages"])
    else:
        th_imp, n_iter, err = solve_implied(qf, th_hat, se, target, alive_idx, n_draw=n_draw)
        solve_info = {"mode": "champion-only（无单场盘，恰好可辨识）",
                      "iterations": n_iter, "max_abs_err": float(err),
                      "max_abs_champ_resid": float(err), "max_abs_match_resid": 0.0}
    v_blend = view(qf, th_imp, se, teams, alive, n_draw)

    # 拟合完之后逐项复核。联合拟合是**超定**的，不可能全中——所以这里不是断言
    # 「必须相等」，而是断言「偏差不至于大到让页面上的数字自相矛盾」，
    # 并把逐项残差原样落盘（那就是两个市场的分歧量，页面上要写出来）。
    for t in alive:
        got = v_blend["place"][t]["champion"]
        if abs(got - target[idx[t]]) > 0.12:
            raise AssertionError(
                "隐含实力拟合后 %s 的冠军概率 %.4f 与冠军盘目标 %.4f 差了 %.4f，"
                "超过 12pp。这个阈值不是「必须相等」——联合拟合是超定的，残差"
                "本来就该有（它就是两个市场的分歧量，页面上会写出来）。但超过 12pp"
                "说明两个市场已经在讲两件不同的事，需要人工看一眼再决定怎么呈现。"
                % (t, got, target[idx[t]], abs(got - target[idx[t]])))
    for r in match_rows:
        r["p_implied"] = v_blend["h2h"]["%s|%s" % (r["a"], r["b"])]
        r["resid"] = r["p_implied"] - r["p_blended"]

    pm = json.load(open(os.path.join(HERE, "polymarket_odds.json")))
    mid = {t: pm["prices"][t]["mid"] for t in alive}
    mtot = sum(mid.values())

    # 抄作业：游戏内主赛事预测面板的最优填法。用**融合口径**的逐场胜者概率
    # （既然交付值是融合值，抄作业也该基于同一套口径，而不是纯模型）。
    _, _, _, win_blend = integrate(qf, th_imp, se, n_draw=n_draw)
    _, _, _, win_model = integrate(qf, th_hat, se, n_draw=n_draw)
    bracket_pick, bracket_rows, bracket_stats = best_bracket(qf, win_blend, teams)
    model_pick, _, model_stats = best_bracket(qf, win_model, teams)

    return {
        "generated_from": "model/l6_playoffs.py",
        "as_of_utc": observed.get("as_of_utc", ""),
        "method": "8 队双败精确枚举（8192 条路径），对 theta~N(theta_hat, se) 抽样 %d 次后平均" % n_draw,
        "n_draw": n_draw,
        "ubqf": [{"stage": "UBQF%d" % (k + 1), "a": teams[a], "b": teams[b],
                  "time_cst": STAGE_TIME["UBQF%d" % (k + 1)]}
                 for k, (a, b) in enumerate(qf)],
        "stage_meta": {s: {"cn": STAGE_CN[s], "time_cst": STAGE_TIME[s]} for s in STAGE_CN},
        "alive": alive,
        "market": {
            "source": "Polymarket", "captured_utc": pm.get("captured_utc", ""),
            "event_volume": pm.get("event_volume"),
            "mid": mid,
            "implied": {t: mid[t] / mtot for t in alive},
            "overround": mtot,
        },
        "w_market": blended.get("w_market"),
        "theta": {t: float(th_hat[idx[t]]) for t in teams},
        "theta_se": {t: float(se[idx[t]]) for t in teams},
        "theta_updated": {t: float(th_upd[idx[t]]) for t in teams},
        "theta_implied": {t: float(th_imp[idx[t]]) for t in alive},
        "implied_solve": solve_info,
        # 八强单场盘：市场对这四场的**直接**定价，不需要经过隐含实力翻译。
        # p_market/p_model/p_blended/p_implied 四列并排，读者可以自己看
        # 「从冠军盘翻译出来的」和「单场盘直接报的」差多少。
        "match_market": {
            "source": "Polymarket 单场盘（与冠军盘是两个独立市场）",
            "captured_utc": (mkt_matches or {}).get("captured_utc", ""),
            "rows": match_rows,
        } if match_rows else None,
        # 游戏内主赛事预测面板的建议填法（面板是一整张对阵表，14 场逐场点胜者）
        "bracket_homework": {
            "panel": "游戏内「赛事预测 → 国际邀请赛」页签，8/20 主赛事开打前锁定",
            "pick": bracket_pick,
            "rows": bracket_rows,
            "stats": bracket_stats,
            # 抄作业页的前端编辑器要用的两项。
            # win_p 必须是**没截断**的全表：rows[].top 为了显示只留了 top4 且 p>0.005，
            # 而读者在编辑器里可以选到被截掉的那些队，查不到就会被算成 0 分。
            "win_p": {st: {teams[t]: p for t, p in win_blend[st].items()}
                      for st in ALL_STAGES},
            "pick_bits": bracket_stats["pick_bits"],
            "model_only_pick": model_pick,
            "model_only_stats": model_stats,
            "differs_from_model": sorted(
                st for st in ALL_STAGES if bracket_pick[st] != model_pick[st]),
        },
        "views": {"model": v_model, "blended": v_blend, "updated": v_upd},
        "robustness": {
            "note": ("把 TI15 已完赛的 109 小局按贝叶斯折进实力分（先验=赛前后验），"
                     "看「模型没见过 TI15」这条质疑值多少。先验方差未为状态漂移放宽，"
                     "所以这是位移的下界。"),
            "n_games": len(games_from_results(observed, teams)),
            "dtheta": {t: float(th_upd[idx[t]] - th_hat[idx[t]]) for t in teams},
            "dchampion": {t: v_upd["place"][t]["champion"] - v_model["place"][t]["champion"]
                          for t in alive},
            "max_abs_dtheta": float(np.max(np.abs(th_upd - th_hat))),
            "max_abs_dchampion": max(
                abs(v_upd["place"][t]["champion"] - v_model["place"][t]["champion"])
                for t in alive),
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--n-draw", type=int, default=N_DRAW)
    args = ap.parse_args(argv)

    out = build(n_draw=args.n_draw)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    m, b, mk = out["views"]["model"], out["views"]["blended"], out["market"]["implied"]
    print("八强对阵（%s）" % out["as_of_utc"])
    for r in out["ubqf"]:
        key = "%s|%s" % (r["a"], r["b"])
        print("  %s  %-16s vs %-16s   模型 %5.1f%%   融合 %5.1f%%"
              % (r["time_cst"], r["a"], r["b"],
                 m["h2h"][key] * 100, b["h2h"][key] * 100))
    print("\n%-17s %8s %8s %8s %8s" % ("队", "模型", "市场", "融合", "折TI15"))
    for t in sorted(out["alive"], key=lambda t: -b["place"][t]["champion"]):
        print("%-17s %7.1f%% %7.1f%% %7.1f%% %7.1f%%"
              % (t, m["place"][t]["champion"] * 100, mk[t] * 100,
                 b["place"][t]["champion"] * 100,
                 out["views"]["updated"]["place"][t]["champion"] * 100))
    if out.get("match_market"):
        print("\n八强单场盘对照（Polymarket 直接报价 vs 从冠军盘翻译出来的）")
        print("%-30s %8s %8s %8s %8s" % ("对阵", "单场盘", "纯模型", "融合目标", "隐含实力"))
        for r in out["match_market"]["rows"]:
            print("%-30s %7.1f%% %7.1f%% %7.1f%% %7.1f%%"
                  % ("%s vs %s" % (r["a"], r["b"]), r["p_market"] * 100,
                     r["p_model"] * 100, r["p_blended"] * 100, r["p_implied"] * 100))
    si = out["implied_solve"]
    print("\n隐含实力拟合：%s | 冠军残差最大 %.4f，单场残差最大 %.4f"
          % (si["mode"], si.get("max_abs_champ_resid", 0), si.get("max_abs_match_resid", 0)))
    rb = out["robustness"]
    print("稳健性：把 TI15 的 %d 小局折进实力分，实力分最大位移 %.3f，"
          "夺冠概率最大位移 %.1fpp"
          % (rb["n_games"], rb["max_abs_dtheta"], rb["max_abs_dchampion"] * 100))

    bh = out["bracket_homework"]
    st = bh["stats"]
    print("\n游戏内主赛事预测面板 · 建议填法（%d 种自洽填法里搜出来的最优）" % st["n_brackets"])
    print("期望答对 %.2f / %d 场 · 随机填 %.2f · 逐场贪心上界 %.2f（那个填法通常不自洽）"
          % (st["expected"], st["n_matches"], st["random"], st["greedy_upper"]))
    for r in bh["rows"]:
        print("  %-5s %-12s %-13s → %-16s %5.1f%%"
              % (r["panel"], r["time_cst"], r["cn"], r["pick"], r["p_pick"] * 100))
    print("→ %s" % args.out)


if __name__ == "__main__":
    main()
