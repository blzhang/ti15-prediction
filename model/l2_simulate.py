"""L2 赛制模拟：瑞士轮逐轮蒙特卡洛 + 附加淘汰轮 + 8 队双败。

赛制（Liquipedia 核实，见 01-ti15-facts.md §1.2）：
  小组赛  16 队瑞士轮 5 轮，全 BO3
          前 3 名直接进淘汰赛；4–13 名进附加淘汰轮；14–16 名出局
  附加轮  10 队 5 场 BO3，5 队晋级
  主赛事  8 队双败，UB 7 场 + LB 6 场，决赛 BO5，其余 BO3，**无 bracket reset**

三个关键实现点（设计文档 §3-L2）：
  1. 瑞士轮配对是内生的，必须逐轮重跑配对函数，不能用二项近似
  2. 同分按 Buchholz（对手总胜场）排序，不能掷硬币
  3. 实力参数按后验 N(θ̂, se) 每次模拟重抽，把估计不确定性传进结果
"""
import json, os, random, collections, itertools
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(f"{HERE}/l1_rating.json"))
TEAMS = list(R["rating"])
TH = np.array([R["rating"][t] for t in TEAMS])
SE = np.array([R["rating_se"][t] for t in TEAMS])
n = len(TEAMS)
N_SIM = 200000
rng = np.random.default_rng(20260802)


def swiss_pair(order, played, scores):
    """Dutch 式同分配对：按分组、组内上半区对下半区、避免重赛、奇数下浮。"""
    remaining = list(order)
    pairs = []
    while remaining:
        s = scores[remaining[0]]
        grp = [t for t in remaining if scores[t] == s]
        if len(grp) % 2 == 1:                       # 奇数组下浮一队
            rest = [t for t in remaining if scores[t] != s]
            if rest:
                grp.append(rest[0])
        half = len(grp) // 2
        top, bot = grp[:half], grp[half:]
        used = set()
        for a in top:
            cand = [b for b in bot if b not in used and b not in played[a]]
            if not cand:                            # 无法避免重赛就允许重赛
                cand = [b for b in bot if b not in used]
            b = cand[0]
            used.add(b)
            pairs.append((a, b))
        for t in grp:
            if t in remaining:
                remaining.remove(t)
    return pairs


def run_one(theta):
    p1 = 1.0 / (1.0 + np.exp(-(theta[:, None] - theta[None, :])))   # 单局胜率矩阵
    p3 = p1 ** 2 * (3 - 2 * p1)                                     # BO3
    q = 1 - p1
    p5 = p1 ** 3 * (1 + 3 * q + 6 * q ** 2)                         # BO5

    wins = [0] * n; losses = [0] * n
    gw = [0] * n; gl = [0] * n                                       # 小局胜负
    played = [set() for _ in range(n)]
    opponents = [[] for _ in range(n)]

    for rd in range(5):
        if rd == 0:
            order = list(rng.permutation(n))                          # R1 由赛事方指定，用随机近似
        else:
            order = sorted(range(n), key=lambda t: (-wins[t], losses[t],
                           -(gw[t] / max(gw[t] + gl[t], 1)),
                           -sum(wins[o] for o in opponents[t]), rng.random()))
        for a, b in swiss_pair(order, played, wins):
            aw = rng.random() < p3[a, b]
            # 小局比分：赢家 2 胜，输家 0 或 1
            loser_games = 1 if rng.random() < 0.4386 else 0
            if aw:
                wins[a] += 1; losses[b] += 1; gw[a] += 2; gl[a] += loser_games
                gw[b] += loser_games; gl[b] += 2
            else:
                wins[b] += 1; losses[a] += 1; gw[b] += 2; gl[b] += loser_games
                gw[a] += loser_games; gl[a] += 2
            played[a].add(b); played[b].add(a)
            opponents[a].append(b); opponents[b].append(a)

    swiss_rank = sorted(range(n), key=lambda t: (-wins[t], losses[t],
                        -(gw[t] / max(gw[t] + gl[t], 1)),
                        -sum(wins[o] for o in opponents[t]), rng.random()))
    rec = [(wins[t], losses[t]) for t in range(n)]

    direct = swiss_rank[:3]                       # 前 3 直接进淘汰赛
    elim_pool = swiss_rank[3:13]                  # 4–13 名进附加轮
    out3 = swiss_rank[13:]                        # 14–16 出局

    # 附加淘汰轮：高排位 vs 低排位（对应 Liquipedia 的 3-2 vs 2-3）
    elim_win, elim_lose = [], []
    for k in range(5):
        a, b = elim_pool[k], elim_pool[9 - k]
        if rng.random() < p3[a, b]:
            elim_win.append(a); elim_lose.append(b)
        else:
            elim_win.append(b); elim_lose.append(a)

    # 淘汰赛种子：3 直通队按瑞士轮名次占 1-3 号种子，5 附加轮晋级队按瑞士轮名次占 4-8
    seeds = direct + sorted(elim_win, key=lambda t: swiss_rank.index(t))
    place = [None] * n
    for t in out3:
        place[t] = 14
    for t in elim_lose:
        place[t] = 9

    # 双败：UB QF 1v8 2v7 3v6 4v5
    def m3(a, b): return a if rng.random() < p3[a, b] else b
    qf = [(seeds[0], seeds[7]), (seeds[3], seeds[4]), (seeds[1], seeds[6]), (seeds[2], seeds[5])]
    ubw, ubl = [], []
    for a, b in qf:
        w = m3(a, b); ubw.append(w); ubl.append(a if w == b else b)
    sfw, sfl = [], []
    for a, b in ((ubw[0], ubw[1]), (ubw[2], ubw[3])):
        w = m3(a, b); sfw.append(w); sfl.append(a if w == b else b)
    ubf_w = m3(sfw[0], sfw[1]); ubf_l = sfw[0] if ubf_w == sfw[1] else sfw[1]

    lb1w = []
    for a, b in ((ubl[0], ubl[1]), (ubl[2], ubl[3])):
        w = m3(a, b); lb1w.append(w); place[a if w == b else b] = 7
    lb2w = []
    for a, b in ((lb1w[0], sfl[1]), (lb1w[1], sfl[0])):
        w = m3(a, b); lb2w.append(w); place[a if w == b else b] = 5
    lbsf_w = m3(lb2w[0], lb2w[1]); place[lb2w[0] if lbsf_w == lb2w[1] else lb2w[1]] = 4
    lbf_w = m3(lbsf_w, ubf_l); place[lbsf_w if lbf_w == ubf_l else ubf_l] = 3
    champ = ubf_w if rng.random() < p5[ubf_w, lbf_w] else lbf_w      # 决赛 BO5，无 reset
    place[champ] = 1
    place[lbf_w if champ == ubf_w else ubf_w] = 2
    return rec, swiss_rank, place, set(direct) | set(elim_win)


# ---------- 跑 ----------
champ_c = np.zeros(n); place_c = np.zeros((n, 17)); rec_c = collections.Counter()
adv_c = np.zeros(n); top3_c = np.zeros(n); r50 = np.zeros(n); r41 = np.zeros(n)
n50_hist = collections.Counter(); n41_hist = collections.Counter()

for s in range(N_SIM):
    theta = TH + SE * rng.standard_normal(n)        # 后验重抽
    rec, srank, place, advanced = run_one(theta)
    for t in range(n):
        rec_c[(t, rec[t])] += 1
        place_c[t, place[t]] += 1
        if rec[t] == (5, 0): r50[t] += 1
        if rec[t] == (4, 1): r41[t] += 1
    n50_hist[sum(1 for t in range(n) if rec[t] == (5, 0))] += 1
    n41_hist[sum(1 for t in range(n) if rec[t] == (4, 1))] += 1
    for t in advanced: adv_c[t] += 1
    for t in srank[:3]: top3_c[t] += 1
    champ_c[place.index(1)] += 1

P = lambda a: a / N_SIM
order = sorted(range(n), key=lambda t: -champ_c[t])

print(f"TI15 蒙特卡洛模拟  N={N_SIM:,}  （实力参数每次按后验 N(θ,se) 重抽）")
print("=" * 96)
print(f"{'队':<17}{'夺冠':>7}{'进前四':>8}{'进淘汰赛':>9}{'瑞前3':>7}{'5-0':>7}{'4-1':>7}{'瑞士轮出局':>10}")
print("-" * 96)
for t in order:
    top4 = P(place_c[t, 1:5].sum())
    print(f"{TEAMS[t]:<17}{P(champ_c[t]):>6.1%}{top4:>8.1%}{P(adv_c[t]):>9.1%}"
          f"{P(top3_c[t]):>7.1%}{P(r50[t]):>7.1%}{P(r41[t]):>7.1%}{1-P(adv_c[t]):>10.1%}")
print("-" * 96)
print(f"{'合计':<17}{P(champ_c.sum()):>6.1%}{P(place_c[:,1:5].sum()):>8.1%}{P(adv_c.sum()):>9.1%}")

se_champ = np.sqrt(P(champ_c) * (1 - P(champ_c)) / N_SIM)
print(f"\n夺冠概率蒙特卡洛标准误：最大 {se_champ.max():.4f}（{se_champ.max()*100:.2f}pp）")

print(f"\n本届出现 k 支 5-0 队的概率：")
for k in sorted(n50_hist):
    print(f"  {k} 支：{n50_hist[k]/N_SIM:>6.1%}")
print(f"本届出现 k 支 4-1 队的概率：")
for k in sorted(n41_hist):
    if n41_hist[k] / N_SIM > 0.005:
        print(f"  {k} 支：{n41_hist[k]/N_SIM:>6.1%}")

json.dump({"champion": {TEAMS[t]: float(P(champ_c[t])) for t in range(n)},
           "top4": {TEAMS[t]: float(P(place_c[t,1:5].sum())) for t in range(n)},
           "advance_playoffs": {TEAMS[t]: float(P(adv_c[t])) for t in range(n)},
           "swiss_top3": {TEAMS[t]: float(P(top3_c[t])) for t in range(n)},
           "record_5_0": {TEAMS[t]: float(P(r50[t])) for t in range(n)},
           "record_4_1": {TEAMS[t]: float(P(r41[t])) for t in range(n)},
           "n_5_0_dist": {str(k): v / N_SIM for k, v in n50_hist.items()},
           "n_4_1_dist": {str(k): v / N_SIM for k, v in n41_hist.items()},
           "n_sim": N_SIM},
          open(f"{HERE}/l2_predictions.json", "w"), indent=1, ensure_ascii=False)
print(f"\n→ 写入 {HERE}/l2_predictions.json")
