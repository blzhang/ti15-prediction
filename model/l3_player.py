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
     对 `available_items()` 全部 15 个 key 逐一实测：有 11 个会直接
     KeyError（除 kills/deaths/camps_stacked/stuns 外的全部可用项）。
     新增 `_resolve_item_values()` 做这层解析：先认 df 里的原始列名
     （向后兼容 kills 这种字面重合的调用方式），找不到再查 SCORING_ITEMS
     按 key 解析（单列改名或多列求和）。这层解析真正解决的是 11 个里的
     8 个（creep_score/gpm/tower_kills/roshan/teamfight/wards/runes/
     first_blood）；剩下 3 个（smokes/tormentor/courier）在 SCORING_ITEMS
     里 column=None——需要另外解 OpenDota JSON blob 左连接（见
     model/l4_fantasy_report.py::load_blob_joined_df），不在本模块范围内，
     两边都解析不到，修复前后都正确报 KeyError，不是本函数要补的缺口。

  3) 真实数据里 teamfight_participation / stuns 在目标选手 + 时间窗下
     各有 54 行是 NaN（fantasy_stats.load_player_games 的 fillna 列表
     没覆盖这两列——已用 data/pro_player_matches_2020_2026.csv 实测
     验证：49762 行里 gold_per_min/kills 0 个 NaN，teamfight_participation
     /stuns 各 54 个 NaN）。参考实现用 len(g)（原始行数）当 n 喂给
     shrink，会把这些 NaN 行也算进样本量，obs_var 因此被低估、se 被
     人为拉低。改为按该 item 的非空观测数计 n_games，raw 也只用非空值
     求均值。

【Critical 缺陷修复】（详见 .superpowers/sdd/fix-a-variance-report.md 的完整
repro，护栏测试见 tests/test_l3_player.py 新增的"修复【Critical】..."一节）：

  `shrink()` 原来用 `obs_var = raw_rate/n` 估观测方差——这是裸泊松假定
  （Var(单局)=均值）。15 个计分项里只有 kills/deaths 勉强算计数过程；
  实测「按选手自己去均值后的局内残差」算出的局内 sd / 泊松假定 sd：
  last_hits≈7.72x、stuns≈6.08x、gold_per_min≈4.24x、kills≈1.56x、
  deaths≈1.33x，teamfight_participation 反而只有≈0.20x（当前区间偏宽
  约 5 倍）——跟本仓库已有的独立复算（`model/l4_extremes.py::dispersion_ratio`、
  `reports/p2_variance_check.json`，Task 9 的 `--variance-check`）量级一致，
  不是新发现，是同一个问题在 L3 这一层第一次被真正修掉（Task 9 当时只在
  L4-P2 的 `who_leads` 绕开了这个假设，L3 的 `shrink()` 本身一直没改，
  见 `model/l4_extremes_report.py` 模块 docstring 的历史记录）。

  修法：`shrink()` 新增必填参数 `game_var`（该选手该项的实测局内方差，
  由调用方提供），`obs_var` 改为 `max(game_var, 1e-6) / n`，取代内部原来
  隐式的 `max(raw_rate, 1e-6) / n`。`post_var` 的结算公式同步简化为
  `1/(1/eff_prior_var + 1/obs_var)`——这在数学上与原公式
  `1/(1/eff_prior_var + n/max(raw_rate,1e-6))` 在 `obs_var=raw_rate/n` 时
  完全等价，只是不再把这个等价关系硬编码在公式里。**tail_heavy 收缩的
  数学形式（z2、eff_prior_var 的放大公式、w、post 的加权平均）一个字都
  没有改，只有 obs_var 的来源变了**——两条锁定重尾行为的护栏测试
  （2 局离群值必须被显著收缩、后验随样本量单调上升）因此换了参考数值
  但保留的是同样的性质，见 fix-a-variance-report.md 的新旧对照。

  `fit_rate_model` 里新增 `_position_game_var()`：优先用选手自己的局内
  方差（`n >= MIN_N_FOR_OWN_GAME_VAR` 时，样本方差的相对标准误
  ≈sqrt(2/(n-1))，n=20 时约 32%，勉强可信）；样本太小或自身方差恰好
  退化为 0（例如样本内取值巧合全同）时，回退到同号位的池化方差——
  每行减去它所属选手自己的均值、再对全体残差算方差，跟
  `model/l4_extremes.py::empirical_residuals`+`dispersion_ratio` 同一个
  "按选手自己中心化，不能用全局均值（会把选手间的强弱差异错当成局内
  噪声）"的思路，只是这里没有直接 import 那个模块（L3 不应该反向依赖
  L4），在本文件里独立实现同一个思路。整个号位都测不出方差（真实数据
  几乎不可能触发——本项目当前 since=2024-01-01 窗口下每名选手 n_games
  最少 250，见 fix-a-variance-report.md）时，再兜底退回 `max(prior_mean, 1e-6)`
  这个类泊松假定，避免 NaN 或 0 传播到下游的 `1/obs_var`。

  **本次修复只替换 obs_var 的估计方式，`fit_rate_model` 里 `prior_var` 的
  between-within 估计（`within = prior_mean / mean(n)`，同样隐含泊松假定）
  刻意不动**——评审给出的 Yatoro 三项新区间就是在这个约束下算出来的
  （只替换 obs_var，其余收缩逻辑不动）。这个 `within` 项本身很可能也有
  同一类偏差，但不在这次修复范围内，已在 fix-a-variance-report.md 里
  记成后续可选项，不在这里顺手改掉。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from fantasy_stats import SCORING_ITEMS

TAIL_HEAVY_DF = 4.0     # t 先验自由度，越小尾越重

MIN_N_FOR_OWN_GAME_VAR = 20   # 选手自身局内方差估计的最低样本量门槛：
                              # 样本方差的相对标准误 ≈ sqrt(2/(n-1))，n=20
                              # 时约 32%——低于这个门槛的选手改用同号位
                              # 池化方差（见 _position_game_var），不让
                              # 一两局的巧合方差冒充"真"方差喂进收缩。


def shrink(raw_rate, n, prior_mean, prior_var, game_var, tail_heavy=True):
    """经验贝叶斯收缩。返回 (后验均值, 后验标准误)。

    高斯共轭：w = eff_prior_var / (eff_prior_var + obs_var)，
    obs_var = max(game_var, 1e-6) / n——`game_var` 是调用方提供的、该选手
    该项**实测的局内方差**（不是本函数内部猜的）。见模块 docstring
    【Critical 缺陷修复】一节：早期实现在这里悄悄假设
    `game_var ≈ raw_rate`（泊松：Var=均值），对 last_hits/gpm/stuns 这类
    计分项实测偏差达 4-8 倍。tail_heavy=False 时 eff_prior_var 就是
    prior_var 本身，退化为标准共轭更新。

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
    obs_var = max(float(game_var), 1e-6) / n   # 实测局内方差 / n = Var(选手自己的样本均值)
    eff_prior_var = max(prior_var, 1e-9)
    if tail_heavy:
        z2 = (raw_rate - prior_mean) ** 2 / (eff_prior_var + obs_var)
        eff_prior_var = eff_prior_var * (1.0 + z2 / TAIL_HEAVY_DF)
    w = eff_prior_var / (eff_prior_var + obs_var)
    post = w * raw_rate + (1.0 - w) * prior_mean
    post_var = 1.0 / (1.0 / eff_prior_var + 1.0 / obs_var)
    return float(post), float(np.sqrt(post_var))


def _position_game_var(sub):
    """给同一号位分组的 df（列 account_id、_value）算两样东西：

      1) 每名选手自己的局内方差（`groupby(...).var(ddof=1)`，样本数<2 时
         是 NaN，`.var()`/`.mean()` 默认 skipna=True，自动跳过 NaN 观测，
         口径与 n_games/raw_rate 的计算一致）；
      2) 该号位的池化方差——每行减去它所属选手自己的均值，再对全体残差
         算方差（跟 `model/l4_extremes.py::empirical_residuals` +
         `dispersion_ratio` 同一个思路：按选手自己中心化，不能用全局
         均值/全局方差——那会把选手之间的真实强弱差异错当成局内噪声，
         系统性高估到 12.0x/7.8x 这类虚高数字，见模块 docstring）。
         供个人样本量太小或自身方差退化为 0 时回退。

    返回 (per_player_var: pandas Series[account_id->var], pooled_var: float)。
    """
    per_player_var = sub.groupby("account_id")["_value"].var(ddof=1)
    resid = sub["_value"] - sub.groupby("account_id")["_value"].transform("mean")
    pooled_var = float(resid.var(ddof=1))
    if not np.isfinite(pooled_var) or pooled_var <= 0:
        # 兜底：整个号位都测不出方差——真实数据几乎不可能触发（本项目
        # 当前 since=2024-01-01 窗口下每名选手 n_games 最少 250），只有
        # 极端合成 fixture（例如单一选手、且取值恒定）才会撞见。退回
        # 类泊松假定而不是让 NaN/0 传播到下游的 1/obs_var。
        pooled_var = max(float(sub["_value"].mean()), 1e-6)
    return per_player_var, pooled_var


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

    返回 {account_id: {"rate", "se", "n_games", "position", "raw_rate",
    "prior_var_floored"}}。

    `prior_var_floored`（【Important 缺陷修复】）：`prior_var` 的下限
    `prior_mean * 0.05` 在 `between <= within` 时会完全主导先验方差，且
    原实现没有任何字段说明地板被触发——触发条件包括单选手分组、或组内
    选手水平非常接近。

    **这不是一个只在未来小分组场景下才会发生的假设性问题**：本次加上
    这个标记后，在当前真实数据（80 名花名册选手，2024-01-01 起，16 人/
    位置）上实测跑了一遍全部 15 个可得计分项 × 5 个号位 = 75 个分组，
    结果是 **37/75（约一半）已经被地板主导**——`roshan`/`teamfight`/
    `first_blood`/`tormentor` 四项在全部 5 个号位都被地板主导，
    `kills`/`deaths`/`courier` 在 4 个号位、`smokes`/`tower_kills` 在 2 个、
    `wards` 在 1 个（2 号位）；只有 `creep_score`/`gpm`/`camps_stacked`/
    `runes`/`stuns` 五项在全部号位都没有触发。用「同一份数据、只把
    `within` 的分母从 `.size()` 换成 `.count()`」核对过：37/75 这个集合在
    两种 `within` 算法下逐项逐位置完全一致，说明这是本任务 Minor 3 修复
    之前就已经存在的既有现象，不是这次改动引入或放大的副作用——纯粹是
    此前从未有代码把它暴露出来。这个布尔字段按位置分组算一次，同一位置
    组内所有选手共享同一个值，让下游能够察觉"这组的先验方差其实是地板值，
    不是真的从数据估出来的"。
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
        # 号位内的选手间方差 = 总方差 - 局内方差（泊松部分）——between-within
        # 的估计方式本次修复刻意不动（只替换 obs_var，见模块 docstring
        # 【Critical 缺陷修复】一节末尾），within 项同样隐含泊松假定，
        # 留作后续可选项。
        #
        # 【Minor 缺陷修复】within 的分母改用非空观测数（.count()），不再用
        # 含 NaN 行的原始行数（.size()）——与 n_games/raw_rate 排除 NaN 的
        # 口径保持一致。teamfight_participation/stuns 在真实数据里各有
        # 54/49762 行 NaN，用 .size() 会把这些 NaN 行也算进 within 的分母，
        # 让 within 被系统性拉低、prior_var 被拉高，见
        # test_fit_rate_model_within_term_ignores_nan_rows_in_denominator。
        per_player = sub.groupby("account_id")["_value"].mean()
        between = float(per_player.var(ddof=1)) if len(per_player) > 1 else 0.0
        n_nonnull_mean = sub.groupby("account_id")["_value"].count().mean()
        within = prior_mean / max(n_nonnull_mean, 1.0)
        floor = prior_mean * 0.05
        raw_prior_var = between - within
        prior_var = max(raw_prior_var, floor)
        prior_var_floored = bool(raw_prior_var <= floor)

        per_player_var, pooled_game_var = _position_game_var(sub)

        for a in accts:
            g = sub.loc[sub["account_id"] == a, "_value"].dropna()
            if g.empty:
                continue
            raw = float(g.mean())
            n = len(g)
            own_var = per_player_var.get(a, float("nan"))
            if n >= MIN_N_FOR_OWN_GAME_VAR and np.isfinite(own_var) and own_var > 0:
                game_var = own_var          # 样本足够大，信选手自己的实测局内方差
            else:
                game_var = pooled_game_var   # 样本太小或自身方差退化为 0，回退池化方差
            rate, se = shrink(raw, n, prior_mean, prior_var, game_var)
            out[a] = {"rate": rate, "se": se, "n_games": int(n),
                      "position": pos, "raw_rate": raw,
                      "prior_var_floored": prior_var_floored}
    return out
