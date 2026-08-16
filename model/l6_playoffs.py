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
from scipy.optimize import minimize

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
# 枚举里累计对阵概率的阶段（UBQF 是已知事实，不需要概率）
STAGES = ("UBSF1", "UBSF2", "LBR1-1", "LBR1-2", "UBF",
          "LBQF-1", "LBQF-2", "LBSF", "LBF", "GF")


# ---------------------------------------------------------------- 枚举
def enumerate_bracket(qf, p3, p5, D):
    """精确枚举 8 队双败的全部路径。

    qf: [(a, b), (c, d), (e, f), (g, h)]，队伍索引；前两场进 UBSF1，后两场进 UBSF2。
    p3[i, j] / p5[i, j] 形状 (D,)：第 d 次抽样下 i 赢 j 的 BO3 / BO5 概率。

    返回 (place, pairs)：
      place[t] 形状 (9, D)，place[t][k] = 该队拿第 k 名的概率（k=1..8）
      pairs[stage] = {(队, 队): 形状 (D,) 的概率}

    ⚠️ 每个名次只在「该场胜负被决定的那一层」累加一次。写成嵌套循环时极易在外层
    多套一圈导致重复计数（本模块第一版就是这么错的：LBR1 的 7-8 名写在了 UBSF
    循环里面，被乘了 4 倍，而且**行列和自检照样过不了**——正是那条自检抓出来的）。
    所以下面每个 place[...] 的累加点都注明它依赖哪几层，且只依赖这几层。
    """
    teams = [t for pair in qf for t in pair]
    place = {t: np.zeros((9, D)) for t in teams}
    pairs = {s: {} for s in STAGES}

    def add(stage, a, b, w):
        key = (a, b) if a <= b else (b, a)
        cur = pairs[stage].get(key)
        pairs[stage][key] = w.copy() if cur is None else cur + w

    for mq in itertools.product((0, 1), repeat=4):          # 4 场 UBQF
        wq, lq, pq = [], [], np.ones(D)
        for k, (a, b) in enumerate(qf):
            hi, lo = (a, b) if mq[k] == 0 else (b, a)
            wq.append(hi); lq.append(lo); pq = pq * p3[hi, lo]
        # 只依赖 UBQF
        add("UBSF1", wq[0], wq[1], pq)
        add("UBSF2", wq[2], wq[3], pq)
        add("LBR1-1", lq[0], lq[1], pq)
        add("LBR1-2", lq[2], lq[3], pq)

        # 7-8 名只依赖 UBQF + LBR1 —— 必须在 UBSF 循环之外结清
        for mr in itertools.product((0, 1), repeat=2):
            pr = pq.copy()
            for k, (a, b) in enumerate(((lq[0], lq[1]), (lq[2], lq[3]))):
                hi, lo = (a, b) if mr[k] == 0 else (b, a)
                pr = pr * p3[hi, lo]
            for k, (a, b) in enumerate(((lq[0], lq[1]), (lq[2], lq[3]))):
                place[b if mr[k] == 0 else a][7] += pr

        for ms in itertools.product((0, 1), repeat=2):      # 2 场 UBSF
            sfw, sfl, ps = [], [], pq.copy()
            for k, (a, b) in enumerate(((wq[0], wq[1]), (wq[2], wq[3]))):
                hi, lo = (a, b) if ms[k] == 0 else (b, a)
                sfw.append(hi); sfl.append(lo); ps = ps * p3[hi, lo]
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
                    add("LBSF", lb2w[0], lb2w[1], p2)

                    for mv in (0, 1):                            # LBSF → 第 4 名
                        hi, lo = (lb2w[0], lb2w[1]) if mv == 0 else (lb2w[1], lb2w[0])
                        pv = p2 * p3[hi, lo]
                        place[lo][4] += pv

                        for mu in (0, 1):                        # UBF
                            ubfw, ubfl = (sfw[0], sfw[1]) if mu == 0 else (sfw[1], sfw[0])
                            pu = pv * p3[ubfw, ubfl]
                            add("LBF", hi, ubfl, pu)

                            for mf in (0, 1):                    # LBF → 第 3 名
                                lbfw, lbfl = (hi, ubfl) if mf == 0 else (ubfl, hi)
                                pf = pu * p3[lbfw, lbfl]
                                place[lbfl][3] += pf
                                add("GF", ubfw, lbfw, pf)
                                # 总决赛 BO5，无 bracket reset：两个结果一次结清
                                pw = p5[ubfw, lbfw]
                                place[ubfw][1] += pf * pw
                                place[lbfw][2] += pf * pw
                                place[lbfw][1] += pf * (1 - pw)
                                place[ubfw][2] += pf * (1 - pw)
    return place, pairs


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
    place, pairs = enumerate_bracket(qf, p3, p5, n_draw)
    return ({t: place[t].mean(axis=1) for t in place},
            {s: {k: float(v.mean()) for k, v in d.items()} for s, d in pairs.items()},
            p3.mean(axis=2))


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
    """
    th = th_hat.copy()
    anchor = th_hat[alive_idx].mean()
    for it in range(1, max_iter + 1):
        place, _, _ = integrate(qf, th, se, n_draw=n_draw, seed=seed)
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


# ---------------------------------------------------------------- 组装
def view(qf, th, se, teams, alive, n_draw=N_DRAW):
    place, pairs, p3 = integrate(qf, th, se, n_draw=n_draw)
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

    # 三套口径
    v_model = view(qf, th_hat, se, teams, alive, n_draw)
    th_upd = bayesian_update(th_hat, se, games_from_results(observed, teams), idx)
    v_upd = view(qf, th_upd, se, teams, alive, n_draw)
    th_imp, n_iter, err = solve_implied(qf, th_hat, se, target, alive_idx, n_draw=n_draw)
    v_blend = view(qf, th_imp, se, teams, alive, n_draw)

    # 反解之后必须真的对上——这是引入隐含实力的全部理由，不能只在迭代里检查
    for t in alive:
        got = v_blend["place"][t]["champion"]
        if abs(got - target[idx[t]]) > 1e-3:
            raise AssertionError(
                "隐含实力反解后 %s 的冠军概率 %.6f 与融合目标 %.6f 不符"
                % (t, got, target[idx[t]]))

    pm = json.load(open(os.path.join(HERE, "polymarket_odds.json")))
    mid = {t: pm["prices"][t]["mid"] for t in alive}
    mtot = sum(mid.values())

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
        "implied_solve": {"iterations": n_iter, "max_abs_err": float(err)},
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
    rb = out["robustness"]
    print("\n稳健性：把 TI15 的 %d 小局折进实力分，实力分最大位移 %.3f，"
          "夺冠概率最大位移 %.1fpp"
          % (rb["n_games"], rb["max_abs_dtheta"], rb["max_abs_dchampion"] * 100))
    print("隐含实力反解：%d 轮收敛，最大偏差 %.6f"
          % (out["implied_solve"]["iterations"], out["implied_solve"]["max_abs_err"]))
    print("→ %s" % args.out)


if __name__ == "__main__":
    main()
