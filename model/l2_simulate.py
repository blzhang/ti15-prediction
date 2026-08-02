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

from swiss import SwissState, pair_round, rank_teams
from bracket import loser_games_prob, run_playoffs

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(f"{HERE}/l1_rating.json"))
TEAMS = list(R["rating"])
TH = np.array([R["rating"][t] for t in TEAMS])
SE = np.array([R["rating_se"][t] for t in TEAMS])
n = len(TEAMS)
N_SIM = 200000
rng = np.random.default_rng(20260802)


def run_one(theta, rng):
    p1 = 1.0 / (1.0 + np.exp(-(theta[:, None] - theta[None, :])))   # 单局胜率矩阵
    p3 = p1 ** 2 * (3 - 2 * p1)                                     # BO3
    q = 1 - p1
    p5 = p1 ** 3 * (1 + 3 * q + 6 * q ** 2)                         # BO5

    s = SwissState(n)
    s.group = list(rng.permutation([0] * 8 + [1] * 8))   # 分组未公布，随机化
    for rnd in range(5):
        for a, b in pair_round(s, rnd, rng):
            a_wins = rng.random() < p3[a, b]
            pg = p1[a, b] if a_wins else p1[b, a]      # 赢方单局胜率，喂给让分小局公式
            s.record(a, b, a_wins, 1 if rng.random() < loser_games_prob(pg) else 0)

    swiss_rank = rank_teams(s, rng)
    rec = [(s.wins[t], s.losses[t]) for t in range(n)]

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

    # 双败：UB QF 1v8 2v7 3v6 4v5，决赛 BO5 无 reset（抽成独立模块 model/bracket.py）
    bracket_place = run_playoffs(seeds, p3, p5, rng)
    for t, p in bracket_place.items():
        place[t] = p
    return rec, swiss_rank, place, set(direct) | set(elim_win)


# ---------- 跑 ----------
champ_c = np.zeros(n); place_c = np.zeros((n, 17)); rec_c = collections.Counter()
adv_c = np.zeros(n); top3_c = np.zeros(n); r50 = np.zeros(n); r41 = np.zeros(n)
n50_hist = collections.Counter(); n41_hist = collections.Counter()

for s in range(N_SIM):
    theta = TH + SE * rng.standard_normal(n)        # 后验重抽
    rec, srank, place, advanced = run_one(theta, rng)
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
