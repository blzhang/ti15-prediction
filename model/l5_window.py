"""L5 窗口回测的纯函数层。

回答的问题：选手层的数据窗口该不该切到当届版本发布日起（spec
docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md）。

本模块只放不碰磁盘、不碰网络的纯函数，方便全部用小 fixture 测；读真实
CSV、跑四届 holdout、出报告在 model/l5_window_backtest.py。
"""
import numpy as np
from scipy.stats import spearmanr, binomtest

from model.patches import patch_ts, previous_patch, PATCH_RELEASE_UTC

DAY = 86400

# 固定回看长度的臂。L955d 是 baseline：现行产线写的是日历日期 2024-01-01，
# 它对 TI15（2026-08-13 开赛）的真实含义正是「开赛前 955 天」。历史届必须
# 取各自开赛前 955 天，比的才是同一个策略而不是同一个日期。
ARM_LOOKBACK_DAYS = {"L955d": 955, "L365d": 365, "L180d": 180, "L105d": 105}


def window_arms(event_start_ts, patch_name):
    """七个候选臂 -> {臂名: (since_ts, until_ts)}。

    until 一律是开赛时间：任何一个臂都不许把开赛当天及以后的数据喂进
    训练，那是数据泄漏。区间语义是 [since, until)。
    """
    e = int(event_start_ts)
    arms = {"all": (0, e)}
    for name, days in ARM_LOOKBACK_DAYS.items():
        arms[name] = (e - days * DAY, e)
    arms["patch"] = (patch_ts(patch_name), e)
    arms["prev_patch"] = (patch_ts(previous_patch(patch_name)), e)
    return arms


def sliding_arms(event_start_ts, length_days=105, n_steps=4):
    """固定长度、起点相对开赛日往前滑的等长窗口（spec §3 台阶检验）。

    第 k 段 = [开赛 - (k+1)*L, 开赛 - k*L)，首尾相接、不重叠、不留空隙。
    等长是关键：长度一变，Spearman 的差异就分不清是「窗口更短」还是
    「离开赛更远」造成的。
    """
    e = int(event_start_ts)
    L = int(length_days) * DAY
    return {"slide%d" % k: (e - (k + 1) * L, e - k * L) for k in range(int(n_steps))}


def derive_positions(df):
    """按每场每方净资产降序排名的众数推 1..5 号位 -> {account_id: 1..5}。

    df 需含 match_id / account_id / player_slot / net_worth。
    player_slot >= 128 是夜魇方（OpenDota 约定）。

    为什么不用 ti_2021_2025_player_matches.csv 自带的 fantasy_role：那一列
    有 2240 个 NaN，且出现 0/3/4 等无法解释的取值，不可用。

    实测校验（spec §4）：本推导与 TI15 的 80 名人工策展选手 65/80（81.2%）
    完全一致，15 处不一致全部落在 core(1-3) 内部或 support(4-5) 内部，没有
    一处跨越核心/辅助边界。回测其实不要求标签"正确"，只要求跨臂一致——
    同一套分组同时用于所有臂，系统性的 4↔5 对调不引入臂间偏差。

    名次并列用 method="first" 打破（稳定、可复现）；众数并列取最小值
    （pandas `Series.mode()` 返回升序，取 iat[0]），同样是为了可复现。
    """
    work = df.dropna(subset=["account_id", "net_worth"]).copy()
    work["account_id"] = work["account_id"].astype("int64")
    work["_side"] = (work["player_slot"].astype("int64") >= 128).astype(int)
    work["_rank"] = (work.groupby(["match_id", "_side"])["net_worth"]
                     .rank(ascending=False, method="first").astype(int))
    mode = work.groupby("account_id")["_rank"].agg(lambda s: int(s.mode().iat[0]))
    return {int(a): int(p) for a, p in mode.items()}


def coarsen(positions):
    """5 组 -> core(1-3) / support(4-5) 两组（spec §4 稳健口径）。"""
    return {a: ("core" if p <= 3 else "support") for a, p in positions.items()}


MIN_CANDIDATES = 3   # Spearman 至少要 3 个点才有意义

SKIP_TOO_FEW = "候选人不足%d" % MIN_CANDIDATES
SKIP_CONSTANT_PRED = "预测值全同"
SKIP_CONSTANT_ACTUAL = "实际值全同"


def score_arm(rates, actual, positions):
    """按号位组算 Spearman(预测速率, 该届实际每局均值)。

    rates:     {account_id: 预测速率}（fit_rate_model 输出里的 "rate"）
    actual:    {account_id: 该届实际每局均值}
    positions: {account_id: 号位组}，组标签可以是 1..5，也可以是
               coarsen() 给出的 "core"/"support"

    返回 (scores, skipped)：scores = {号位组: rho}，skipped = {号位组: 原因}。
    算不出来的组必须落到 skipped 里带原因，不能记成 0——把「算不出来」
    混进「预测力为零」会直接污染下游的配对符号检验。
    """
    scores, skipped = {}, {}
    for pos in sorted({positions[a] for a in positions}, key=str):
        accts = sorted(a for a in rates if a in actual and positions.get(a) == pos)
        if len(accts) < MIN_CANDIDATES:
            skipped[pos] = SKIP_TOO_FEW
            continue
        x = [float(rates[a]) for a in accts]
        y = [float(actual[a]) for a in accts]
        if len(set(x)) == 1:
            skipped[pos] = SKIP_CONSTANT_PRED
            continue
        if len(set(y)) == 1:
            skipped[pos] = SKIP_CONSTANT_ACTUAL
            continue
        rho = float(spearmanr(x, y)[0])
        if not np.isfinite(rho):
            skipped[pos] = SKIP_CONSTANT_PRED
            continue
        scores[pos] = rho
    return scores, skipped


def paired_sign_test(diffs):
    """配对符号检验（双侧精确二项）。

    用符号检验而不是配对 t 检验：Spearman 之差既不正态也不等方差，
    只看符号是这个样本量下最不需要额外假设的做法。

    零差值按惯例丢弃，但 n_zero 一并返回——静默丢弃会让读者以为样本量
    比实际大。
    """
    vals = [float(d) for d in diffs if np.isfinite(d)]
    n_pos = sum(1 for d in vals if d > 0)
    n_neg = sum(1 for d in vals if d < 0)
    n = n_pos + n_neg
    p = float(binomtest(n_pos, n, 0.5).pvalue) if n else 1.0
    return {"n_pos": n_pos, "n_neg": n_neg, "n_zero": len(vals) - n,
            "median": float(np.median(vals)) if vals else 0.0, "p": p}


def patch_boundaries_in(since_ts, until_ts):
    """区间 (since, until) 内发布的版本名列表，按时间升序。

    给滑动窗口的台阶检验用：某一段跨了几个版本边界，决定这一段的
    Spearman 掉档该不该归因到版本。起点当天发布的版本不算跨界——
    那一段本来就是这个版本的数据。
    """
    out = [(patch_ts(n), n) for n in PATCH_RELEASE_UTC
           if int(since_ts) < patch_ts(n) < int(until_ts)]
    return [n for _, n in sorted(out)]
