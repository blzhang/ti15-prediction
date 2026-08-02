"""L1 队伍实力层：正则化 Bradley-Terry + 时间衰减 + 赛事级别自适应加权。

关键设计：不按 team_id 建模，按「当前这五个人」建模。
某场比赛的一方若含 ≥3 名某 TI15 队的现役首发，该方即标记为那支队；
否则退回用 team_id 标识（对手只是 nuisance 参数）。
这样 Aurora 换了 3 人之后，旧阵容的比赛不会算进它头上——
直接解决「转会让历史战绩失效」这个头号陷阱，无需人工打折。

赛事级别不用人工表（OpenDota tier 字段 2024 年后已失效），改用迭代自举：
uniform 权重 → 拟合 BT → 用各赛事参赛者实力反推赛事权重 → 重拟合。

超参（半衰期 / 岭强度）由**时间切分**验证选出，不看测试期结果调参。
"""
import csv, json, math, collections, datetime, os, sys
import numpy as np
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
sys.path.insert(0, HERE)
from rosters import ROSTERS, ACCOUNT_TO_TEAM, REGION

MIN_SHARED  = 3
NOW         = datetime.datetime(2026, 8, 2).timestamp()
SINCE       = datetime.datetime(2022, 1, 1).timestamp()
MIN_GAMES   = 12
N_ITER_TIER = 3
DAY         = 86400.0

# ---------- 1. 读比赛 ----------
matches = []
for r in csv.DictReader(open(f"{D}/pro_matches_2020_2026.csv")):
    ts = int(r["start_time"])
    if ts < SINCE or r["radiant_win"] not in ("True", "False"):
        continue
    matches.append((r["match_id"], ts, r["leagueid"], r["radiant_team_id"],
                    r["dire_team_id"], r["radiant_win"] == "True"))
mids = {m[0] for m in matches}
print(f"候选比赛（2022 起、结果非空）：{len(matches):,}")

# ---------- 2. 用 80 名现役首发标记阵营 ----------
targets = set(map(str, ACCOUNT_TO_TEAM))
sidemap = collections.defaultdict(set)
with open(f"{D}/pro_player_matches_2020_2026.csv") as f:
    for r in csv.DictReader(f):
        if r["account_id"] not in targets:
            continue
        mid, slot = r["match_id"], r["player_slot"]
        if mid in mids and slot.isdigit():
            sidemap[(mid, "R" if int(slot) < 128 else "D")].add(int(r["account_id"]))

def label(mid, which, team_id):
    accts = sidemap.get((mid, which))
    if accts:
        t, n = collections.Counter(ACCOUNT_TO_TEAM[a] for a in accts).most_common(1)[0]
        if n >= MIN_SHARED:
            return t
    return f"tid:{team_id}" if team_id and team_id != "0" else None

games = []
for mid, ts, lg, rid, did, rwin in matches:
    a, b = label(mid, "R", rid), label(mid, "D", did)
    if a and b and a != b:
        games.append((a, b, rwin, ts, lg))
games.sort(key=lambda g: g[3])
print(f"两方均可标识：{len(games):,}")

hit = collections.Counter(x for g in games for x in (g[0], g[1]) if x in ROSTERS)

# ---------- 3. 实体索引 ----------
cnt = collections.Counter(x for g in games for x in (g[0], g[1]))
ents = sorted({e for e, c in cnt.items() if c >= MIN_GAMES} | set(ROSTERS))
idx = {e: i for i, e in enumerate(ents)}
OTHER = len(ents)
N = len(ents) + 1
A  = np.array([idx.get(g[0], OTHER) for g in games])
B  = np.array([idx.get(g[1], OTHER) for g in games])
Y  = np.array([1.0 if g[2] else 0.0 for g in games])
TS = np.array([g[3] for g in games], dtype=float)
LG = np.array([g[4] for g in games])
print(f"实体数：{N}（含并入 OTHER 的长尾）")


def fit(mask, w, lam, ref_ts):
    """加权 BT + 岭正则，L-BFGS。mask 选训练样本，ref_ts 为时间衰减基准点。"""
    a, b, y, ww = A[mask], B[mask], Y[mask], w[mask]

    def nll(th):
        d = th[a] - th[b]
        # logistic 负对数似然（数值稳定写法）
        ll = ww * (np.logaddexp(0.0, d) - y * d)
        g = np.zeros(N)
        r = ww * (1.0 / (1.0 + np.exp(-d)) - y)
        np.add.at(g, a,  r)
        np.add.at(g, b, -r)
        return ll.sum() + 0.5 * lam * th @ th, g + lam * th

    res = minimize(nll, np.zeros(N), jac=True, method="L-BFGS-B",
                   options={"maxiter": 900, "ftol": 1e-12})
    th = res.x - res.x.mean()
    return th


def evaluate(th, mask):
    d = th[A[mask]] - th[B[mask]]
    p = 1.0 / (1.0 + np.exp(-d))
    y = Y[mask]
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return dict(n=int(mask.sum()),
                acc=float(((p > .5) == (y > .5)).mean()),
                brier=float(((p - y) ** 2).mean()),
                logloss=float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()))


# ---------- 4. 时间切分调超参 ----------
# 训练 = 切点之前；验证 = 切点后 120 天。只用验证期选参，测试期最后才碰。
CUT_V = datetime.datetime(2025, 8, 1).timestamp()   # 验证切点
CUT_T = datetime.datetime(2026, 3, 1).timestamp()   # 测试切点（最终检验，只用一次）

CACHE = f"{HERE}/l1_rating.json"
PRESET = None
if os.path.exists(CACHE) and "--refit" not in sys.argv:
    _c = json.load(open(CACHE))
    if "half_life_days" in _c:
        PRESET = (_c["half_life_days"], _c["ridge"], _c.get("oos_test"))
        print(f"\n沿用已选超参：半衰期 {PRESET[0]} 天，岭 λ={PRESET[1]}（加 --refit 可重搜）")

print("\n=== 超参搜索（时间切分，只看验证期）===" if not PRESET else "")
if not PRESET:
    print(f"{'半衰期':>7}{'岭λ':>8}{'验证n':>8}{'准确率':>9}{'Brier':>9}{'LogLoss':>10}")
best = None
for hl in ((PRESET[0],) if PRESET else (120, 180, 270, 400)):
    for lam in ((PRESET[1],) if PRESET else (2.0, 6.0, 15.0, 40.0)):
        if PRESET:
            best = (PRESET[2], hl, lam); break
        w = 0.5 ** ((CUT_V - TS) / (hl * DAY))
        w = np.where(TS < CUT_V, w, 0.0)
        tr = TS < CUT_V
        va = (TS >= CUT_V) & (TS < CUT_T)
        th = fit(tr, w, lam, CUT_V)
        m = evaluate(th, va)
        star = ""
        if best is None or m["logloss"] < best[0]["logloss"]:
            best, star = (m, hl, lam), "  ←"
        print(f"{hl:>7}{lam:>8.1f}{m['n']:>8}{m['acc']:>8.1%}{m['brier']:>9.4f}{m['logloss']:>10.4f}{star}")

_, HL, LAM = best
print(f"\n选定：半衰期 {HL} 天，岭 λ={LAM}")

# ---------- 5. 用选定超参做样本外测试（只跑一次）----------
if PRESET:
    m = PRESET[2]
else:
    w = np.where(TS < CUT_T, 0.5 ** ((CUT_T - TS) / (HL * DAY)), 0.0)
    th_t = fit(TS < CUT_T, w, LAM, CUT_T)
    m = evaluate(th_t, TS >= CUT_T)
print(f"=== 样本外测试（2026-03 之后 {m['n']:,} 场，训练时完全没见过）===")
print(f"  准确率 {m['acc']:.1%}   Brier {m['brier']:.4f}   LogLoss {m['logloss']:.4f}")
print(f"  参照：设计文档 §5 护栏 —— 赛前预测现实上限 65–70%，Brier 健康区间 0.21–0.24")

# ---------- 6. 全量重拟合 + 赛事权重自举 ----------
allm = np.ones(len(games), dtype=bool)
w_lg = {l: 1.0 for l in set(LG.tolist())}
for it in range(N_ITER_TIER):
    w = 0.5 ** ((NOW - TS) / (HL * DAY)) * np.array([w_lg[l] for l in LG])
    th = fit(allm, w, LAM, NOW)
    s = collections.defaultdict(list)
    for k in range(len(games)):
        s[LG[k]].append(max(th[A[k]], th[B[k]]))
    raw = {l: float(np.mean(v)) for l, v in s.items()}
    lo, hi = np.percentile(list(raw.values()), [10, 95])
    w_lg = {l: float(np.clip(0.15 + 0.85 * (v - lo) / (hi - lo + 1e-9), 0.15, 1.0))
            for l, v in raw.items()}
    print(f"  赛事权重迭代 {it+1}：中位数 {np.median(list(w_lg.values())):.3f}")

w = 0.5 ** ((NOW - TS) / (HL * DAY)) * np.array([w_lg[l] for l in LG])
th = fit(allm, w, LAM, NOW)

# ---------- 7. 输出 ----------
leagues = {r["leagueid"]: r.get("name", "") for r in csv.DictReader(open(f"{D}/pro_dim_leagues.csv"))}
print("\n自适应赛事权重 最高 10（验证分级是否合理）：")
for l, v in sorted(w_lg.items(), key=lambda kv: -kv[1])[:10]:
    print(f"  {v:.3f}  {leagues.get(l,'?')[:56]}")

# 后验标准误：拉普拉斯近似，Fisher 信息对角 = Σ w·p(1-p)，再加岭项
d_all = th[A] - th[B]
p_all = 1.0 / (1.0 + np.exp(-d_all))
info = np.full(N, LAM, dtype=float)
contrib = w * p_all * (1 - p_all)
np.add.at(info, A, contrib)
np.add.at(info, B, contrib)
se = 1.0 / np.sqrt(info)

# 跨赛区连通性诊断：EU 与非 EU 之间到底有多少直接交手
lab = {t: REGION[t] for t in ROSTERS}
cross = collections.Counter()
for k in range(len(games)):
    ga, gb = games[k][0], games[k][1]
    if ga in lab and gb in lab and lab[ga] != lab[gb]:
        cross[tuple(sorted((lab[ga], lab[gb])))] += 1
print("\n跨赛区直接交手场次（仅统计 16 队之间，近 4 年）：")
for k, v in sorted(cross.items(), key=lambda kv: -kv[1]):
    print(f"  {k[0]}–{k[1]}: {v}")

rating = {t: float(th[idx[t]]) for t in ROSTERS}
rating_se = {t: float(se[idx[t]]) for t in ROSTERS}
order = sorted(rating, key=lambda t: -rating[t])
print("\n=== L1 实力评分（BT θ）===")
print(f"{'队':<17}{'θ':>8}{'±se':>7}{'样本':>7}  {'赛区':<5}{'对末位单局胜率':>12}")
lastθ = rating[order[-1]]
for t in order:
    p = 1 / (1 + math.exp(-(rating[t] - lastθ)))
    print(f"{t:<17}{rating[t]:>8.3f}{rating_se[t]:>7.3f}{hit[t]:>7}  {REGION[t]:<5}{p:>11.1%}")

json.dump({"rating": rating, "rating_se": rating_se,
           "games": {t: hit[t] for t in ROSTERS},
           "half_life_days": HL, "ridge": LAM,
           "oos_test": m, "cross_region": {f"{a}-{b}": v for (a, b), v in cross.items()},
           "league_weight": w_lg},
          open(f"{HERE}/l1_rating.json", "w"), indent=1)
print(f"\n→ 写入 {HERE}/l1_rating.json")
