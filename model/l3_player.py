"""L3 选手能力层：按号位分层的层次泊松 + 收缩。

设计要点（03-academic-methods.md）：
  - 负二项 = gamma 混合的泊松，故不裸套 NB，直接建层次模型，把局长、版本、
    双方强度差当协变量解释掉一部分过离散，剩下的用随机效应吸收
    （§4.3）。本任务的落地范围是这条架构里"选手层 + 位置分层随机效应"
    的部分：按 1-5 号位分组，把组内选手间方差当层级先验方差，
    用经验贝叶斯收缩单个选手的每局速率。局/版本随机效应与双方强度差
    协变量不在本任务接口范围内（`fit_rate_model(df, item_key, positions)`
    没有局长/版本/对手强度参数，Step 5 的真实数据校验脚本也没有构造
    这些协变量）——这条留给后续任务按需扩展，本任务不做超出接口范围的
    协变量建模。
  - 必须按 1-5 号位分层：1 号位与 5 号位的分布完全不是一回事
  - 用重尾先验防止 James-Stein 把真·离群选手过度收缩（"Clemente Problem"）

对 task-6-brief.md Step 3 参考实现的三处修正（详见 task-6-report.md 的
repro 记录与理由，均已用新增测试锁定，不是"默默改"）：

  1) 后验标准误（se）原样直接用未放大的 prior_var 结算，跟用来算后验
     均值的 eff_prior_var（重尾放大后的有效先验方差）不是同一个数。
     只要 raw_rate 偏离 prior_mean（z2>0，几乎是真实数据里的常态），
     eff_prior_var 就会被放大用于均值，但方差还是用没放大的 prior_var——
     模型一边说"这可能是真实水平，不做收缩"，一边却报一个和没做重尾
     修正时一样小的标准误，精度被凭空夸大，会直接污染 Task 8 用 se
     撑开的置信区间。改为后验方差也用同一个 eff_prior_var 结算：
     post_var = 1 / (1/eff_prior_var + 1/obs_var)。

  2) 参考实现的 fit_rate_model 只认与 df 列名完全相同的 item_key。但
     model/fantasy_stats.py 的模块级 docstring 已经明确交代："只做
     『抽取可得原始列』，不做跨列合成（例如 Creep Score 的 last_hits +
     denies 求和）...具体怎么合成留给下游（L3 速率模型）按 item 处理"——
     "下游（L3 速率模型）"指的就是本模块。SCORING_ITEMS 18 项里，
     除 kills/deaths/camps_stacked/stuns 外，可用项的 key 与实际列名
     全部不同（例如 gpm→gold_per_min、tower_kills→towers_killed、
     roshan→roshans_killed），Creep Score 更是要 last_hits+denies
     逐局求和。不解析的话，下游若直接用 SCORING_ITEMS 的 key 调用，
     15 个可得项里有 9 个会直接 KeyError。新增 `_resolve_item_values()`
     做这层解析：先认 df 里的原始列名（向后兼容 kills 这种字面重合的
     调用方式），找不到再查 SCORING_ITEMS 按 key 解析（单列改名或
     多列求和），两边都找不到才 KeyError。

  3) 真实数据里 teamfight_participation / stuns 在目标选手 + 时间窗下
     各有 54 行是 NaN（fantasy_stats.load_player_games 的 fillna 列表
     没覆盖这两列——已用 data/pro_player_matches_2020_2026.csv 实测
     验证：49762 行里 gold_per_min/kills 0 个 NaN，teamfight_participation
     /stuns 各 54 个 NaN）。参考实现用 len(g)（原始行数）当 n 喂给
     shrink，会把这些 NaN 行也算进样本量，obs_var 因此被低估、se 被
     人为拉低。改为按该 item 的非空观测数计 n_games，raw 也只用非空值
     求均值。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from fantasy_stats import SCORING_ITEMS

TAIL_HEAVY_DF = 4.0     # t 先验自由度，越小尾越重


def shrink(raw_rate, n, prior_mean, prior_var, tail_heavy=True):
    """经验贝叶斯收缩。返回 (后验均值, 后验标准误)。

    高斯共轭：w = eff_prior_var / (eff_prior_var + obs_var)，obs_var = lambda/n。
    tail_heavy=False 时 eff_prior_var 就是 prior_var 本身，退化为标准共轭更新。

    重尾修正的正确做法是**放大有效先验方差**（t 先验的尾更厚，
    极端观测因此没那么"意外"），而不是直接抬高观测权重。
    偏离度必须用**总方差**（先验 + 观测）来标准化，否则小样本的
    大偏离会被误判成"真离群"，收缩机制会被完全废掉：
    实测中错误写法给 2 局样本的权重是 0.935、100 局是 0.992，
    样本量几乎不起作用，与收缩的目的正好相反。

    后验标准误必须用同一个 eff_prior_var 结算（而不是原始 prior_var）：
    否则对被重尾修正"少收缩"的离群观测，模型一边几乎不把均值往先验拉，
    一边却报一个跟没做重尾修正时一样小的标准误——精度被凭空夸大，
    等于白做了重尾修正（见 test_tail_heavy_se_reflects_inflated_uncertainty_not_just_mean）。
    """
    n = max(int(n), 0)
    if n == 0:
        return float(prior_mean), float(np.sqrt(prior_var))
    obs_var = max(raw_rate, 1e-6) / n          # 泊松：Var(mean) ≈ lambda/n
    eff_prior_var = max(prior_var, 1e-9)
    if tail_heavy:
        z2 = (raw_rate - prior_mean) ** 2 / (eff_prior_var + obs_var)
        eff_prior_var = eff_prior_var * (1.0 + z2 / TAIL_HEAVY_DF)
    w = eff_prior_var / (eff_prior_var + obs_var)
    post = w * raw_rate + (1.0 - w) * prior_mean
    post_var = 1.0 / (1.0 / eff_prior_var + n / max(raw_rate, 1e-6))
    return float(post), float(np.sqrt(post_var))


def _resolve_item_values(df, item_key):
    """把 item_key 解析成 df 里逐局的取值 Series。

    item_key 可以是：
      1) df 里已经存在的原始列名（例如 "kills"，两者字面相同）；
      2) SCORING_ITEMS 里声明的 key（例如 "gpm" → 列 "gold_per_min"，
         "creep_score" → 列 "last_hits" + "denies" 逐局求和）。
    两边都解析不到就 KeyError —— fantasy_stats.py 的 docstring 明确把
    这层合成留给了"下游（L3 速率模型）"，也就是本函数。
    """
    if item_key in df.columns:
        return df[item_key]
    item = next((i for i in SCORING_ITEMS if i["key"] == item_key), None)
    if item is None or item["column"] is None:
        raise KeyError(
            "df 中没有列 %r，SCORING_ITEMS 里也没有可解析出原始列的同名 key" % item_key)
    cols = item["column"] if isinstance(item["column"], (tuple, list)) else (item["column"],)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError("解析 item_key=%r 需要列 %r，但 df 缺少 %r" % (item_key, cols, missing))
    values = df[cols[0]]
    for c in cols[1:]:
        values = values + df[c]
    return values


def fit_rate_model(df, item_key, positions):
    """按号位分层估计每名选手的「每局速率」。

    df 需含列：account_id、position（通过 model.rosters 拼接），以及
    item_key 能解析到的原始列（见 _resolve_item_values：可以是字面同名
    的原始列，也可以是 SCORING_ITEMS 声明的 key）。
    positions: {account_id: 1..5}

    返回 {account_id: {"rate", "se", "n_games", "position", "raw_rate"}}。
    """
    values = _resolve_item_values(df, item_key)
    work = df[["account_id"]].copy()
    work["_value"] = values

    out = {}
    for pos in sorted(set(positions.values())):
        accts = [a for a, p in positions.items() if p == pos]
        sub = work[work["account_id"].isin(accts)]
        if sub.empty:
            continue
        prior_mean = float(sub["_value"].mean())
        # 号位内的选手间方差 = 总方差 - 局内方差（泊松部分）
        per_player = sub.groupby("account_id")["_value"].mean()
        between = float(per_player.var(ddof=1)) if len(per_player) > 1 else 0.0
        within = prior_mean / max(sub.groupby("account_id").size().mean(), 1.0)
        prior_var = max(between - within, prior_mean * 0.05)

        for a in accts:
            g = sub.loc[sub["account_id"] == a, "_value"].dropna()
            if g.empty:
                continue
            raw = float(g.mean())
            n = len(g)
            rate, se = shrink(raw, n, prior_mean, prior_var)
            out[a] = {"rate": rate, "se": se, "n_games": int(n),
                      "position": pos, "raw_rate": raw}
    return out
