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
from swiss import SwissState, pair_round, rank_teams, active_teams
from bracket import loser_games_prob, run_playoffs
import draw as draw_mod
import results as results_mod

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(f"{HERE}/l1_rating.json"))
TEAMS = list(R["rating"])
TH = np.array([R["rating"][t] for t in TEAMS])
SE = np.array([R["rating_se"][t] for t in TEAMS])
n = len(TEAMS)
N_SIM = 200000
rng = np.random.default_rng(20260802)

# 赛事方公布的分组/首轮对阵。未公布时为 None，run_one 走原来的随机分支。
# 模块级只读一次，与 TEAMS/TH 同级——测试要覆盖时传 run_one(..., drawn=...)。
DRAW = draw_mod.load(TEAMS)

# 已打完 / 已排定的系列赛。开赛前为 None，run_one 全程模拟；开赛后已发生的
# 结果照抄、不再当随机变量抽（model/results.py 的完整说明）。
OBSERVED = results_mod.load(TEAMS)


def group_vec_from_pairs(pairs, rng):
    """在「与已知首轮对阵自洽」的全部分组里均匀抽一种。

    首轮只在组内打，所以每个已公布的对子必须整对落在同一组。8 个对子分 4+4
    进两组，共 C(8,4)/2 = 35 种切法——洗牌后取前 4 个对子归 0 组即为均匀抽样。

    这是 2026-08-10 的正确做法：首轮对阵有两个独立来源、可以当事实，A/B 分组
    官方从没公布过。把 35 种切法平均掉，等于「用上全部已证实的信息，且只用
    已证实的信息」；从转播分流之类的旁证挑一种当事实，是凭空多一个自由度。

    开赛之后这条路径被 results.json 接管：多打一轮就多一层「必须同组」约束，
    候选切法从 35 → 3 → 1 自动收紧（见 model/results.py 与下面的 sample_split）。
    """
    gv = [0] * 16
    for k, pi in enumerate(rng.permutation(len(pairs))):
        i, j = pairs[pi]
        gv[i] = gv[j] = (0 if k < len(pairs) // 2 else 1)
    return gv


def sample_split(splits, rng):
    """在「与全部已知对阵自洽」的候选分组里均匀抽一种。

    候选只剩一种时直接返回它，不消耗随机数——分组已经由对阵唯一确定，
    再抽一次只是浪费，且会让「分组确定」与「分组待定」两种情形的随机数流
    莫名其妙地不同。
    """
    if len(splits) == 1:
        return list(splits[0])
    return list(splits[rng.integers(len(splits))])


def seeds_from_ubqf(pairs):
    """把 Liquipedia 槽位顺序的四场八强对阵（R1M1–R1M4）编码成 bracket.py 的
    seeds 列表，使 run_playoffs 内部构造的 QF 恰好逐场还原这四场对阵。

    bracket.py 的 QF 构造顺序是 [(s0,s7), (s3,s4), (s1,s6), (s2,s5)]，对应
    R1M1–R1M4——这个映射被 tests/test_results.py 里的往返测试钉住：编码后
    再按 bracket.py 的构造展开，必须逐场还原输入。
    """
    (m1a, m1b), (m2a, m2b), (m3a, m3b), (m4a, m4b) = pairs
    return [m1a, m3a, m4a, m2a, m2b, m4b, m3b, m1b]


def run_one(theta, rng, drawn=None, observed=None):
    p1 = 1.0 / (1.0 + np.exp(-(theta[:, None] - theta[None, :])))   # 单局胜率矩阵
    p3 = p1 ** 2 * (3 - 2 * p1)                                     # BO3
    q = 1 - p1
    p5 = p1 ** 3 * (1 + 3 * q + 6 * q ** 2)                         # BO5

    s = SwissState(n)
    # 分组来源三选一，优先级 = 信息量从高到低：
    #   1. observed：已完赛/已排定的对阵反推出的候选集（R1-R3 组内、R4 跨组）。
    #      每多打一轮候选就少一批，打完 R3 收敛到唯一解——分组不需要猜。
    #   2. drawn：赛事方公布的分组，或只公布了首轮时的 35 种切法。
    #   3. 都没有：完全随机化。
    # drawn 与 observed 都为 None 时，这里的 rng 调用与加这两个开关之前完全一致。
    if observed and observed.get("splits"):
        s.group = sample_split(observed["splits"], rng)
    elif drawn and drawn.get("group_vec"):
        s.group = list(drawn["group_vec"])
    elif drawn and drawn.get("r1_pairs"):
        # 首轮已知、分组未知：只在与首轮自洽的 35 种切法里抽
        s.group = group_vec_from_pairs(drawn["r1_pairs"], rng)
    else:
        s.group = list(rng.permutation([0] * 8 + [1] * 8))   # 分组未公布，随机化

    fixed_r1 = drawn.get("r1_pairs") if drawn else None
    obs_rounds = (observed or {}).get("rounds", {})
    # 打到 4 胜或 4 负即停（见 swiss.active_teams 的说明）。最多 5 轮：
    # 第 5 轮只有 3-1 / 2-2 / 1-3 三组共 14 队 = 7 场，4-0 与 0-4 已停赛。
    for rnd in range(5):
        act = active_teams(s)
        if len(act) < 2:
            break
        # 这一轮已知的对阵（打完的、或排好/正在打还没分胜负的）照用；**这一轮里
        # 还没排到的队，按战绩现配**——这是「半轮」情形，赛程推进到一半时必然出现：
        # 比如第 5 轮 7 场只开了 3 场，另外 8 队的对阵官方还没出。
        # 早先的写法是「这一轮有已知对阵就整轮照用」，那会让剩下 8 队整轮不打球，
        # 直接破坏 1/2/5/5/2/1 的分档恒等式（模块末尾那条 assert 会炸）。
        # obs_rounds 的键从 1 计（与对外文案一致），rnd 从 0 计。
        known = obs_rounds.get(rnd + 1) or []
        schedule = [(a, b, a_wins, lg) for a, b, a_wins, lg in known]
        fixed = {t for a, b, _, _ in known for t in (a, b)}
        rest = [t for t in act if t not in fixed]
        if rest:
            # 已知对阵占掉一部分时，只对剩下的队配对；fixed_r1 只在第一轮
            # 完全没有已知对阵时才有意义（有已知对阵的话它已经包含在 known 里了）。
            schedule += [(a, b, None, None)
                         for a, b in pair_round(s, rnd, rng, active=rest,
                                                fixed_r1=None if known else fixed_r1)]
        for a, b, a_wins, loser_games in schedule:
            if a_wins is not None:
                # 已经打完了：这是事实，每次模拟都照抄，一个随机数都不消耗。
                s.record(a, b, a_wins, loser_games)
                continue
            a_wins = rng.random() < p3[a, b]
            pg = p1[a, b] if a_wins else p1[b, a]      # 赢方单局胜率，喂给让分小局公式
            s.record(a, b, a_wins, 1 if rng.random() < loser_games_prob(pg) else 0)

    swiss_rank = rank_teams(s, rng)
    rec = [(s.wins[t], s.losses[t]) for t in range(n)]

    # 分档**直接由战绩决定**，不再用排名硬凑——这是本模型的赛制修正：
    # 预测面板问的就是「哪支 4-0 / 哪两支 4-1 / …」，而战绩分档在
    # 「4 胜或 4 负即停」的赛制下是结构性恒等式（恒为 1/2/5/5/2/1）。
    by_rec = collections.defaultdict(list)
    for t in range(n):
        by_rec["%d-%d" % rec[t]].append(t)
    rank_of = {t: i for i, t in enumerate(swiss_rank)}
    key = lambda g: sorted(g, key=lambda t: rank_of[t])

    direct = key(by_rec["4-0"]) + key(by_rec["4-1"])   # 3 队直通淘汰赛
    hi, lo = key(by_rec["3-2"]), key(by_rec["2-3"])    # 各 5 队，进附加轮
    out3 = key(by_rec["1-4"]) + key(by_rec["0-4"])     # 3 队直接出局
    elim_pool = hi + lo

    # 每队瑞士轮 + 附加轮系列赛数（task-7-brief.md Step 5）：瑞士轮固定 5 场
    # （model/swiss.py 没有提前淘汰，16 队全部打满 5 轮），4-13 名多打 1 场
    # 附加轮——这是每次模拟都精确成立的确定性计数，不依赖谁赢谁输
    # （tests/test_l2_simulate.py::test_group_series_sums_to_ninety_every_single_simulation
    # 锁了 sum(group_series)==90 这条恒等式）。
    elim_pool_set = set(elim_pool)
    group_series = [s.wins[t] + s.losses[t] + (1 if t in elim_pool_set else 0)
                    for t in range(n)]

    # 附加淘汰轮。实际规则是**选人制**（最高排位的 3-2 队先挑 2-3 的对手），
    # 选择本身没法模拟，所以分两层：
    #   · observed 里已录的附加轮对阵（选人结果）当事实照用；已有比分的连胜负
    #     都照抄，一个随机数不消耗——与瑞士轮 replay 同一条纪律。
    #   · 还没被选走的队，退回「hi[k] vs lo[倒数第 k]」的规则近似（对应
    #     Liquipedia 原文「3-2 will be paired against 2-3」，赛前只能这么近似）。
    obs_elim = (observed or {}).get("elim") or []
    elim_win, elim_lose = [], []
    picked = set()
    for a, b, a_wins, _ in obs_elim:
        if a_wins is None:
            a_wins = rng.random() < p3[a, b]
        w_, l_ = (a, b) if a_wins else (b, a)
        elim_win.append(w_); elim_lose.append(l_)
        picked.add(a); picked.add(b)
    hi_rest = [t for t in hi if t not in picked]
    lo_rest = [t for t in lo if t not in picked]
    for k in range(len(hi_rest)):
        a, b = hi_rest[k], lo_rest[len(lo_rest) - 1 - k]
        if rng.random() < p3[a, b]:
            elim_win.append(a); elim_lose.append(b)
        else:
            elim_win.append(b); elim_lose.append(a)

    # 淘汰赛种子。官方公布的八强对阵优先（TI15 实际对阵与名次规则近似完全
    # 对不上，8/16 实测）；未公布时退回规则近似：3 直通队按瑞士轮名次占
    # 1-3 号种子，5 附加轮晋级队按瑞士轮名次占 4-8。
    obs_qf = (observed or {}).get("ubqf")
    if obs_qf:
        seeds = seeds_from_ubqf(obs_qf)
    else:
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
    # ⚠️ 新增返回字段一律追加在末尾，不要插在中间——本函数的返回值已被追加过两次
    # （Task 7 加 group/playoff_series，本次加附加轮生还/出局集合），每次插在中间
    # 都撞坏了 tests/test_l2_simulate.py 的位置解包。测试侧已改用 `, *_` 尾部星号
    # 解包，只要新字段追加在末尾就不会再破。
    return (rec, swiss_rank, place, set(direct) | set(elim_win),
            group_series, playoff_series, set(elim_win), set(elim_lose))


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
    # 分组状态先打出来供肉眼复核——填错分组会静默产出一份错的预测，
    # 而这份预测会被直接发布，所以每次跑都要看见自己在算哪一种情况。
    print(draw_mod.describe(DRAW, TEAMS))
    print()
    print(results_mod.describe(OBSERVED, TEAMS))
    print()
    champ_c = np.zeros(n); place_c = np.zeros((n, 17)); rec_c = collections.Counter()
    rec_dist = [collections.Counter() for _ in range(n)]   # 逐队完整瑞士轮战绩分布
    elim_survive = np.zeros(n); elim_out = np.zeros(n)     # 附加轮生还 / 出局
    adv_c = np.zeros(n); top3_c = np.zeros(n); r40 = np.zeros(n); r41 = np.zeros(n)
    n40_hist = collections.Counter(); n41_hist = collections.Counter()
    series_group = np.zeros(n)      # 瑞士轮 + 附加轮系列赛数（Task 7 Step 5）
    series_playoff = np.zeros(n)    # 主赛事系列赛数（Task 7 Step 5）

    for s in range(N_SIM):
        theta = TH + SE * rng.standard_normal(n)        # 后验重抽
        rec, srank, place, advanced, g_series, p_series, ew, el = run_one(
            theta, rng, DRAW, OBSERVED)
        for t in ew: elim_survive[t] += 1
        for t in el: elim_out[t] += 1
        for t in range(n):
            rec_c[(t, rec[t])] += 1
            rec_dist[t]["%d-%d" % rec[t]] += 1
            place_c[t, place[t]] += 1
            if rec[t] == (4, 0): r40[t] += 1
            if rec[t] == (4, 1): r41[t] += 1
        n40_hist[sum(1 for t in range(n) if rec[t] == (4, 0))] += 1
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
    print(f"{'队':<17}{'夺冠':>7}{'进前四':>8}{'进淘汰赛':>9}{'瑞前3':>7}{'4-0':>7}{'4-1':>7}{'瑞士轮出局':>10}")
    print("-" * 96)
    for t in order:
        top4 = P(place_c[t, 1:5].sum())
        print(f"{TEAMS[t]:<17}{P(champ_c[t]):>6.1%}{top4:>8.1%}{P(adv_c[t]):>9.1%}"
              f"{P(top3_c[t]):>7.1%}{P(r40[t]):>7.1%}{P(r41[t]):>7.1%}{1-P(adv_c[t]):>10.1%}")
    print("-" * 96)
    print(f"{'合计':<17}{P(champ_c.sum()):>6.1%}{P(place_c[:,1:5].sum()):>8.1%}{P(adv_c.sum()):>9.1%}")

    se_champ = np.sqrt(P(champ_c) * (1 - P(champ_c)) / N_SIM)
    print(f"\n夺冠概率蒙特卡洛标准误：最大 {se_champ.max():.4f}（{se_champ.max()*100:.2f}pp）")

    # 分档是结构性恒等式（恒为 1/2/5/5/2/1），不是分布——留作回归自检
    assert list(n40_hist) == [1] and list(n41_hist) == [2], (
        "4-0 必恒为 1 支、4-1 必恒为 2 支，实为 %s / %s" % (dict(n40_hist), dict(n41_hist)))
    print("\n分档结构自检：4-0 恒 1 支、4-1 恒 2 支、3-2/2-3 各恒 5 支、1-4 恒 2 支、0-4 恒 1 支 ✓")
    
    # 每队分阶段期望系列赛数（Task 7 Step 5，供 model/l4_fantasy.py 的
    # expected_slot_score 消费）。两条与结果无关的精确自洽校验（见
    # tests/test_l2_simulate.py 与 task-7-report.md）：
    #   sum(series_group)   == 90（16 队 ×5 瑞士轮 + 10 队 ×1 附加轮，恒定）
    #   sum(series_playoff) == 28（14 场主赛事系列赛 × 每场 2 支队伍，恒定）
    print(f"\n每队分阶段期望系列赛数合计核对：group={series_group.sum()/N_SIM:.6f}（应为 88）"
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
               "record_dist": {TEAMS[t]: {k: round(v / N_SIM, 6) for k, v in sorted(rec_dist[t].items(), reverse=True)}
                           for t in range(n)},
           "elim_round_survive": {TEAMS[t]: float(P(elim_survive[t])) for t in range(n)},
           "elim_round_out": {TEAMS[t]: float(P(elim_out[t])) for t in range(n)},
           "record_4_0": {TEAMS[t]: float(P(r40[t])) for t in range(n)},
               "record_4_1": {TEAMS[t]: float(P(r41[t])) for t in range(n)},
               "n_4_0_dist": {str(k): v / N_SIM for k, v in n40_hist.items()},
               "n_4_1_dist": {str(k): v / N_SIM for k, v in n41_hist.items()},
               "place_dist": place_dist,
               "series_dist": {TEAMS[t]: {"group": round(float(series_group[t] / N_SIM), 6),
                                           "playoff": round(float(series_playoff[t] / N_SIM), 6)}
                               for t in range(n)},
               # 这一版预测建立在什么抽签信息之上，必须跟着产物走。
               # 站点、更新日志、赛后打分都要靠它区分「什么都不知道」「首轮已证实
               # 但分组未知」「分组已公布」几种版本——写在文案里会漏，写在这里不会。
               # grouping=unknown 时 group_vec 是 None：分组名单不存在，落盘为空数组，
               # 并写明模拟对多少种切法做了平均（n_group_splits）。
               "draw": ({"announced": False} if not DRAW else {
                   "announced": True,
                   "grouping": DRAW["grouping"],
                   "round1_fixed": DRAW["r1_pairs"] is not None,
                   "source": DRAW["source"],
                   "group_a": ([] if DRAW["group_vec"] is None else
                               [TEAMS[i] for i, g in enumerate(DRAW["group_vec"]) if g == 0]),
                   "group_b": ([] if DRAW["group_vec"] is None else
                               [TEAMS[i] for i, g in enumerate(DRAW["group_vec"]) if g == 1]),
                   "n_group_splits": (35 if DRAW["group_vec"] is None and DRAW["r1_pairs"]
                                      else None),
                   "round1": [[TEAMS[i], TEAMS[j]] for i, j in (DRAW["r1_pairs"] or [])],
               }),
               # 这一版预测条件化在哪些**已经发生的结果**之上。与 draw 块同理：
               # 站点、复盘页、赛后打分都要靠它区分「纯赛前预测」和「打了 N 场之后
               # 的预测」——两者拿同一套标准打分是不公平的，必须能分辨。
               # n_group_splits 记录分组还剩几种可能：3 表示仍在平均，1 表示已由
               # 对阵唯一确定（打完第三轮就会到 1）。
               "results": ({"active": False} if not OBSERVED else {
                   "active": True,
                   "as_of_utc": OBSERVED["as_of_utc"],
                   "source": OBSERVED["source"],
                   "n_series_done": OBSERVED["n_done"],
                   "n_series_scheduled": OBSERVED["n_scheduled"],
                   "n_group_splits": len(OBSERVED["splits"]),
                   "records": {t: "%d-%d" % wl
                               for t, wl in results_mod.records(OBSERVED, TEAMS).items()},
                   "rounds": [
                       {"round": rnd,
                        "series": [{"a": TEAMS[i], "b": TEAMS[j],
                                    "score": ([2, lg] if aw else [lg, 2]) if aw is not None else None}
                                   for i, j, aw, lg in series]}
                       for rnd, series in sorted(OBSERVED["rounds"].items())],
                   # 附加淘汰轮的实际对阵（选人制，不是规则近似）。复盘页要拿它
                   # 逐场对账，没有就是空数组——键始终存在，读侧不用判空。
                   "elimination": [{"a": TEAMS[i], "b": TEAMS[j],
                                    "score": ([2, lg] if aw else [lg, 2]) if aw is not None else None}
                                   for i, j, aw, lg in (OBSERVED.get("elim") or [])],
                   # 八强真实对阵（Liquipedia R1M1–R1M4 槽位顺序）；未公布为 null。
                   # 这一版预测的夺冠概率就条件化在它之上，站点要能看见这个前提。
                   "playoff_ubqf": ([[TEAMS[i], TEAMS[j]] for i, j in OBSERVED["ubqf"]]
                                    if OBSERVED.get("ubqf") else None),
               }),
               "n_sim": N_SIM},
              open(f"{HERE}/l2_predictions.json", "w"), indent=1, ensure_ascii=False)
    print(f"\n→ 写入 {HERE}/l2_predictions.json")
