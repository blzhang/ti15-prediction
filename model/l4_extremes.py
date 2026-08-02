"""L4-P2：极值题。

设计文档 §4.4：经验频率 + 层次平滑优于拟合 GPD ——
26 杀约在 99.5 分位附近，阈值附近有几十上百个真实观测，
此时经验频率更稳，而 GPD 还引入「阈值怎么选」这个新的过拟合来源。
仅当某道题的阈值超出历史观测范围时（`needs_gpd`），GPD 才不可替代——
本模块不实现 GPD，命中这条边界时如实报告"超出可估计范围"，不假装能算。

对 task-9-brief.md Step 3 参考实现的两处修正（详见 task-9-report.md 的
repro 记录与理由，均已用新增测试锁定，不是"默默改"）：

  1) `test_smoothing_keeps_zero_count_thresholds_off_zero` 断言
     `threshold_prob([10]*200, 25, n_games=145, smooth=0.5) < 0.2`，但把
     brief 自己 Step 3 的参考实现（含其默认参数）原样代入这组 fixture，
     精确算出的是 0.30312...，不是 <0.2——这是本项目第 11 个"brief 自己
     的测试和参考实现互相矛盾"的真实例，但性质和前 10 个不同：前 10 个
     都是"测试和实现共享同一个错误前提、彼此自洽所以能骗过"，这次是
     压根跑不过（已用 tests/test_l4_extremes.py 原样抄录 brief Step 1/3
     独立复现：5 passed, 1 failed）。`threshold_prob` 本身的公式（Jeffreys
     型可加平滑 (hits+smooth)/(n+2·smooth)）没有问题——是数学上有据可查
     的标准做法，不是这次要修的对象；错的是 brief 测试里那个具体的数值
     字面量 0.2，像是作者没有真的算过。修法：把断言改成对解析解取
     pytest.approx（附安全区间 <0.5），不改变"经验频率为 0 时不应输出
     恰好 0"这条核心断言，也不改 threshold_prob 本身的实现。

  2) `who_leads` 原参考实现用 `rng.poisson(rates[a], size=g)` 模拟单局产出，
     等价于假设 Var(单局) ≈ rate（泊松假定）。但控制器实测（已被本任务
     独立复算证实，见 task-9-report.md）：局间标准差 / 泊松假定标准差，
     kills≈1.5x、deaths≈1.3x、**last_hits≈7.2-7.7x、gold_per_min≈4.1-4.3x、
     stuns≈5.9-6.1x**（teamfight_participation≈0.18x，反而比泊松假定更窄）。
     GPM/补刀/眩晕这三项差 4-8 倍不是舍入误差，是"泊松假定在这些计分项上
     根本不成立"。真实后果（已用真实 L3 rate 复现，见 task-9-report.md）：
     两名 1 号位选手 GPM 差距仅 20.2（767.1 vs 746.9，2.7%），brief 原实现
     在 20 局模拟下把"谁打出全场最高 GPM"算成 84.8% vs 15.2%——用的假定
     单局 sd 只有 ~27.7，而实测 gpm 局间 sd 约 110（约 4 倍）。均值差距被
     严重放大成近乎必胜。

     一个标量 rate 从结构上就不携带"这个计分项到底有多离散"这个信息，
     所以问题不能靠调参数解决，必须改接口：新增 `residual_pool` 参数——
     该计分项真实的、按选手自己历史均值中心化后跨选手池化的"局间残差"
     经验分布（`empirical_residuals` 产出）。每次抽样 = rates[a] + 从残差池
     里有放回抽一个残差，负值在 0 处截断（15 个可得计分项全部是计数或
     计数类比例，物理上不可能为负，跟 `model/l4_players.py::_interval`
     的下界处理同一个理由）。这是有意选择"直接自助重采样局间残差"而不是
     负二项/截断正态：不同计分项形状差异极大（kills/deaths 是小整数计数、
     last_hits/gpm 接近连续、teamfight_participation 是 [0,1] 比例、stuns
     是连续秒数），任何单一参数族都要么对某些项失真、要么要逐项调参；
     经验残差池不对形状做任何假设，直接沿用真实数据的离散度，跟 §4.4
     "优先信经验频率、不迷信参数族"是同一个方法论选择，只是从"阈值尾部"
     下沉到"单局离散度"这一层。`residual_pool` 可以是一个数组（所有选手
     共用）或 `{account_id: 数组}` 的 dict（每位选手/每个位置各自的残差池，
     真实报告用法——见 model/l4_extremes_report.py，按位置池化，因为不同
     位置的离散度形状本身也有差异，见 task-9-report.md 的分位置实测）。
"""
import numpy as np


def threshold_prob(samples, threshold, n_games, smooth=0.5):
    """全赛事 n_games 局中，至少出现一次「单局 ≥ threshold」的概率。

    smooth 为拉普拉斯/Jeffreys 型平滑量：经验计数为 0 时避免输出恰好 0。
    """
    s = np.asarray(samples, dtype=float)
    if s.size == 0:
        raise ValueError("samples 不能为空")
    hits = float((s >= threshold).sum())
    p_game = (hits + smooth) / (s.size + 2 * smooth) if smooth > 0 else hits / s.size
    p_game = min(max(p_game, 0.0), 1.0)
    return float(1.0 - (1.0 - p_game) ** max(int(n_games), 0))


def needs_gpd(samples, threshold):
    """阈值是否超出历史观测范围 —— 只有这种情况才该回退到 GPD。

    本模块不实现 GPD：命中 True 时，调用方应如实报告"超出可估计范围"，
    而不是继续套用经验频率假装能算（见模块 docstring）。
    """
    return float(threshold) > float(np.max(np.asarray(samples, dtype=float)))


def empirical_residuals(values, account_ids):
    """按选手自己的历史均值中心化后池化的「局间残差」。

    values[i] 是 account_ids[i] 那名选手在某一局的真实观测值；返回等长的
    残差数组，每个值 = 该局真实值 - 该选手自己在样本内的均值。用全局均值
    中心化会把"选手之间的真实能力差异"错当成"同一个人局与局之间的噪声"
    混进残差池，弥散度会被系统性高估——必须按选手自己的均值中心化。
    """
    values = np.asarray(values, dtype=float)
    account_ids = np.asarray(account_ids)
    if values.shape != account_ids.shape:
        raise ValueError("values 与 account_ids 长度必须一致")
    out = np.empty_like(values)
    for a in np.unique(account_ids):
        mask = account_ids == a
        out[mask] = values[mask] - values[mask].mean()
    return out


def dispersion_ratio(values, account_ids, min_n=5):
    """验证泊松假定 Var(单局) ≈ rate 是否成立：逐选手算「实测局间标准差」
    对「泊松假定标准差 sqrt(rate)」的比值，再汇总。比值远离 1 说明
    `model/l3_player.py::shrink` 里 `obs_var = raw_rate/n` 这个假设对该
    计分项不成立（见 task-9-report.md 的独立复算与 model/l4_extremes_report.py
    --variance-check）。

    返回 {"ratio_mean", "ratio_median", "n_players", "per_player": [...]}。
    """
    values = np.asarray(values, dtype=float)
    account_ids = np.asarray(account_ids)
    per_player = []
    for a in np.unique(account_ids):
        vals = values[account_ids == a]
        vals = vals[~np.isnan(vals)]
        n = int(vals.size)
        if n < min_n:
            continue
        rate = float(vals.mean())
        if rate <= 0:
            continue
        emp_sd = float(vals.std(ddof=1))
        poisson_sd = float(np.sqrt(rate))
        per_player.append({
            "account_id": a, "n_games": n, "rate": rate,
            "empirical_sd": emp_sd, "poisson_sd": poisson_sd,
            "ratio": emp_sd / poisson_sd,
        })
    if not per_player:
        raise ValueError("没有足够样本（n>=%d 且 rate>0）计算弥散度比值" % min_n)
    ratios = np.array([p["ratio"] for p in per_player])
    return {
        "ratio_mean": float(ratios.mean()),
        "ratio_median": float(np.median(ratios)),
        "n_players": len(per_player),
        "per_player": per_player,
    }


def _residual_pool_for(residual_pool, account_id):
    pool = residual_pool[account_id] if isinstance(residual_pool, dict) else residual_pool
    pool = np.asarray(pool, dtype=float)
    if pool.size == 0:
        raise ValueError("account_id=%r 的 residual_pool 不能为空" % (account_id,))
    return pool


def who_leads(rates, n_games_by_player, residual_pool, n_sim=20000, seed=0):
    """「谁打出全场最高值」的概率。

    注意：这是身份题，本质是「哪支队走得深」的衍生题 ——
    局数方差远大于场均方差（05-applied-design.md），
    `test_who_leads_favours_players_with_more_games` 钉住这条。

    rates: {account_id: 该计分项的每局期望（L3 后验均值）}。
    n_games_by_player: {account_id: 预计在本届参赛局数}。
    residual_pool: 该计分项真实的「局间残差」经验分布（`empirical_residuals`
        的产出）——一个数组（所有选手共用）或 `{account_id: 数组}`。
        每次抽样 = rates[a] + 从对应残差池里有放回抽一个残差，下界在 0
        截断（计数类指标不可能为负，见模块 docstring）。不用泊松假定，
        故不会像 brief 原参考实现那样系统性低估 last_hits/gpm/stuns 这类
        过散计分项的局间波动。
    """
    rng = np.random.default_rng(seed)
    accts = list(rates)
    if not accts:
        return {}
    pools = {a: _residual_pool_for(residual_pool, a) for a in accts}

    sim_max = {}
    any_games = False
    for a in accts:
        g = int(n_games_by_player.get(a, 0))
        if g <= 0:
            sim_max[a] = np.full(n_sim, -np.inf)
            continue
        any_games = True
        draws = rates[a] + rng.choice(pools[a], size=(n_sim, g), replace=True)
        draws = np.maximum(draws, 0.0)
        sim_max[a] = draws.max(axis=1)

    if not any_games:
        raise ValueError("n_games_by_player 里没有任何一名选手的局数 > 0")

    # 同分时按极小随机噪声打破平局，避免系统性偏向遍历顺序靠前的选手
    # （数量级 1e-6，远小于任何计分项真实取值的分辨率，不改变实质排序）。
    tie_break = rng.random((len(accts), n_sim)) * 1e-6
    stacked = np.vstack([sim_max[a] for a in accts]) + tie_break
    winner_idx = np.argmax(stacked, axis=0)
    counts = np.bincount(winner_idx, minlength=len(accts))

    wins = {a: int(counts[i]) for i, a in enumerate(accts)}
    tot = sum(wins.values()) or 1
    return {a: wins[a] / tot for a in accts}
