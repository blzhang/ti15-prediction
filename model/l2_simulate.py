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
import json, os, sys, random, collections, itertools
import numpy as np

# 让本文件既能当脚本跑（python3 model/l2_simulate.py），也能被
# `from model.l2_simulate import run_one` 当包导入（tests/test_l2_simulate.py，
# Task 7 新增）——两种导入方式下 __file__ 所在目录都要在 sys.path 上，
# 否则下面两行裸导入在"当包导入"这条路径下会 ModuleNotFoundError。
# 写法与 model/l3_player.py 已经用的 shim 一致。
sys.path.insert(0, os.path.dirname(__file__))
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

    # 每队瑞士轮 + 附加轮系列赛数（task-7-brief.md Step 5）：瑞士轮固定 5 场
    # （model/swiss.py 没有提前淘汰，16 队全部打满 5 轮），4-13 名多打 1 场
    # 附加轮——这是每次模拟都精确成立的确定性计数，不依赖谁赢谁输
    # （tests/test_l2_simulate.py::test_group_series_sums_to_ninety_every_single_simulation
    # 锁了 sum(group_series)==90 这条恒等式）。
    elim_pool_set = set(elim_pool)
    group_series = [5 + (1 if t in elim_pool_set else 0) for t in range(n)]

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

    # 双败：UB QF 1v8 2v7 3v6 4v5，决赛 BO5 无 reset（抽成独立模块 model/bracket.py）。
    # 名次不能反推系列赛数（同为 place=3 可能是 4 场也可能是 5 场，见
    # bracket.py 里 run_playoffs 新增的 docstring），所以让 run_playoffs
    # 在模拟过程中原地把每队打了几个系列赛记进 playoff_sc。
    playoff_sc = {}
    bracket_place = run_playoffs(seeds, p3, p5, rng, series_count=playoff_sc)
    for t, p in bracket_place.items():
        place[t] = p
    playoff_series = [playoff_sc.get(t, 0) for t in range(n)]
    return rec, swiss_rank, place, set(direct) | set(elim_win), group_series, playoff_series


def place_dist_from_counts(place_c, n_sim, teams):
    """把累计名次计数矩阵（16×17，列 0 恒为 0——名次从 1 开始编号，
    没有队伍会落在"第 0 名"）按 n_sim 归一化成
    {队名: {"1": 概率, ..., "16": 概率}} 的名次分布，按全局约束保 6 位
    小数（task-7-brief.md 起一直沿用的输出精度约定）。

    这是 00-DESIGN.md §2.1 T2「最终名次分布 / 16×名次档 概率矩阵」的
    落盘形式——§8 验收标准第 3 条「名次分布行列和自洽」在这里体现为：
    每支队伍的 16 个名次概率恰好和为 1（每次模拟每队必然落在恰好一个
    名次，见 test_place_assigns_exact_multiset_of_placements_every_single_simulation
    锁定的"名次赋值本身就是结构性恒等式，不是靠平均凑出来的"），全部
    队伍的概率总和恰好等于队伍数（16）。只输出第 1-16 名（列 0 从不会
    被任何队伍命中，不落盘）。
    """
    dist = {}
    for t, team in enumerate(teams):
        row = place_c[t]
        dist[team] = {str(p): round(float(row[p]) / n_sim, 6) for p in range(1, 17)}
    return dist


# ---------- 跑 ----------
# 用 `if __name__ == "__main__":` 包住（Task 7 新增）：run_one 本身是纯函数
# （只依赖形参 theta/rng 与本模块顶部已经算好的 n/TEAMS 等常量，不依赖这个循环
# 产生的任何状态），之前这段跑 20 万次模拟 + 打印 + 落盘的代码直接摆在模块
# 顶层，意味着任何 `import model.l2_simulate`（包括未来想单元测试 run_one 的
# tests/test_l2_simulate.py）都会被迫先跑一遍完整的 20 万次蒙特卡洛
# （实测约 100 秒）才能拿到函数本身。加这层 guard 后：
#   - `python3 model/l2_simulate.py` 直接跑的行为完全不变（这是 brief 里
#     "改完要重跑模拟"要求的唯一调用方式，__name__ 在这种调用下就是
#     "__main__"）；
#   - `from model.l2_simulate import run_one` 现在零成本，不再顺带跑一遍
#     20 万次模拟——这条改动只挪了代码位置、不改变任何一行计算逻辑，
#     用重跑前后 l2_predictions.json 字节级 diff 验证过完全不变
#     （task-7-report.md 有实测记录）。
if __name__ == "__main__":
    champ_c = np.zeros(n); place_c = np.zeros((n, 17)); rec_c = collections.Counter()
    adv_c = np.zeros(n); top3_c = np.zeros(n); r50 = np.zeros(n); r41 = np.zeros(n)
    n50_hist = collections.Counter(); n41_hist = collections.Counter()
    series_group = np.zeros(n)      # 瑞士轮 + 附加轮系列赛数（Task 7 Step 5）
    series_playoff = np.zeros(n)    # 主赛事系列赛数（Task 7 Step 5）

    for s in range(N_SIM):
        theta = TH + SE * rng.standard_normal(n)        # 后验重抽
        rec, srank, place, advanced, g_series, p_series = run_one(theta, rng)
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
        series_group += g_series
        series_playoff += p_series

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

    # 每队分阶段期望系列赛数（Task 7 Step 5，供 model/l4_fantasy.py 的
    # expected_slot_score 消费）。两条与结果无关的精确自洽校验（见
    # tests/test_l2_simulate.py 与 task-7-report.md）：
    #   sum(series_group)   == 90（16 队 ×5 瑞士轮 + 10 队 ×1 附加轮，恒定）
    #   sum(series_playoff) == 28（14 场主赛事系列赛 × 每场 2 支队伍，恒定）
    print(f"\n每队分阶段期望系列赛数合计核对：group={series_group.sum()/N_SIM:.6f}（应为 90）"
          f"  playoff={series_playoff.sum()/N_SIM:.6f}（应为 28）")

    # T2「最终名次分布」矩阵（00-DESIGN.md §2.1；task-final-fix【4】新增）：
    # place_c 之前只被拆出 top4（1-4 名求和）落盘，完整的 16×名次档矩阵本身
    # 从未写进 l2_predictions.json，§8 验收标准第 3 条"名次分布行列和自洽"
    # 因此无从核对。place_dist_from_counts 详见其 docstring。
    place_dist = place_dist_from_counts(place_c, N_SIM, TEAMS)
    row_sums = [sum(place_dist[t].values()) for t in TEAMS]
    col_sum_total = sum(row_sums)
    print(f"\nT2 名次分布行列和自洽核对：行和范围=[{min(row_sums):.6f}, {max(row_sums):.6f}]"
          f"（应约为 1）  列和之和={col_sum_total:.6f}（应约为 {n}）")

    json.dump({"champion": {TEAMS[t]: float(P(champ_c[t])) for t in range(n)},
               "top4": {TEAMS[t]: float(P(place_c[t,1:5].sum())) for t in range(n)},
               "advance_playoffs": {TEAMS[t]: float(P(adv_c[t])) for t in range(n)},
               "swiss_top3": {TEAMS[t]: float(P(top3_c[t])) for t in range(n)},
               "record_5_0": {TEAMS[t]: float(P(r50[t])) for t in range(n)},
               "record_4_1": {TEAMS[t]: float(P(r41[t])) for t in range(n)},
               "n_5_0_dist": {str(k): v / N_SIM for k, v in n50_hist.items()},
               "n_4_1_dist": {str(k): v / N_SIM for k, v in n41_hist.items()},
               "place_dist": place_dist,
               "series_dist": {TEAMS[t]: {"group": round(float(series_group[t] / N_SIM), 6),
                                           "playoff": round(float(series_playoff[t] / N_SIM), 6)}
                               for t in range(n)},
               "n_sim": N_SIM},
              open(f"{HERE}/l2_predictions.json", "w"), indent=1, ensure_ascii=False)
    print(f"\n→ 写入 {HERE}/l2_predictions.json")
