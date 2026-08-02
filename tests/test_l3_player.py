import numpy as np
import pandas as pd
import pytest
from model.l3_player import shrink, fit_rate_model, MIN_N_FOR_OWN_GAME_VAR


# ---- brief 给定的 5 条测试（Step 1，原样使用，不可削弱） ----
#
# fix-a-variance-report.md（Critical 缺陷修复）：`shrink()` 新增必填参数
# `game_var`（该选手该项的实测局内方差），取代内部原来悄悄假设的
# `obs_var = raw_rate/n`（裸泊松）。下面 5 条测试原始断言逐字未改，唯一的
# 改动是补上这个新的必填参数——大多数调用传 `game_var=raw_rate`，即"重现
# 旧泊松假定隐含的方差"，因为这些测试测的是收缩算法本身的通用数学性质
# （样本越少收缩越强、se 随样本量下降等），不针对本次修复要校准的具体
# 倍数，这样选择使其数值结果保持不变，不需要重新推导参考值。两条明确
# 点名要"记录新值"的护栏测试（tail_heavy 的两条）例外，见下方专门注释。

def test_shrink_pulls_small_samples_toward_prior():
    prior, pv = 5.0, 1.0
    low_n, _ = shrink(raw_rate=12.0, n=2, prior_mean=prior, prior_var=pv, game_var=12.0)
    high_n, _ = shrink(raw_rate=12.0, n=200, prior_mean=prior, prior_var=pv, game_var=12.0)
    assert prior < low_n < high_n < 12.0, "样本越少越该被拉回先验"


def test_shrink_se_decreases_with_sample_size():
    _, se_small = shrink(8.0, 3, 5.0, 1.0, game_var=8.0)
    _, se_big = shrink(8.0, 300, 5.0, 1.0, game_var=8.0)
    assert se_small > se_big


def test_tail_heavy_prior_shrinks_outliers_less():
    """03-academic-methods.md 的 Clemente Problem：
    重尾先验应避免把真·离群选手过度收缩回均值。"""
    normal, _ = shrink(20.0, 30, 5.0, 1.0, game_var=20.0, tail_heavy=False)
    heavy, _ = shrink(20.0, 30, 5.0, 1.0, game_var=20.0, tail_heavy=True)
    assert heavy > normal


# 护栏测试专用：本次修复把 obs_var 从 raw_rate/n 换成实测局内方差/n，用一个
# 明显不等于 raw_rate 的 game_var 才能证明这两条测试真的在用新代码路径
# （如果继续传 game_var=raw_rate，数值会跟旧实现一模一样，测不出任何东西）。
# 用本项目实测的 GPM 局内 sd / 泊松假定 sd 比值（4.24x，见
# fix-a-variance-report.md 与 03-academic-methods.md:313"必须实测"的要求）
# 而不是凭空发明一个倍数：game_var = raw_rate * 4.24^2 ≈ 215.73。
_GPM_SD_RATIO = 4.24
_OVERDISPERSED_GAME_VAR = 12.0 * _GPM_SD_RATIO ** 2   # ≈ 215.73


def test_tail_heavy_must_not_defeat_shrinkage_on_tiny_samples():
    """护栏：重尾修正只能削弱收缩，不能取消收缩。

    只打 2 局的离群观测（12.0 对先验 5.0）必须仍被显著拉回，
    否则「Clemente 修正」就把收缩机制本身废掉了。

    fix-a-variance-report.md：obs_var 改用实测局内方差后，game_var 换成
    上面的 _OVERDISPERSED_GAME_VAR（≈215.73，而不是旧代码隐含的
    raw_rate=12.0），旧实现在这组输入下给出的后验是 7.20，新实现给出
    的后验是 5.0715（obs_var 变大 → 更不信 2 局观测 → 收缩得比旧实现更狠）
    ——阈值相应从 <9.0 收紧到 <6.0，如实反映这一变化，不是放松断言。
    """
    tiny, _ = shrink(12.0, n=2, prior_mean=5.0, prior_var=1.0,
                      game_var=_OVERDISPERSED_GAME_VAR, tail_heavy=True)
    assert tiny < 6.0, "2 局样本的离群值必须被显著收缩（新 obs_var 下应比旧实现收缩得更狠）"


def test_tail_heavy_weight_still_monotone_in_sample_size():
    """无论是否重尾，样本越多越该信观测。

    fix-a-variance-report.md：game_var 换成 _OVERDISPERSED_GAME_VAR 后，
    新参考值 n=2→5.0715 / n=5→5.2013 / n=20→6.1130 / n=100→9.8541
    （旧值 n=2→7.20/n=5→9.60/n=20→11.55/n=100→11.93）。两条要保留的
    性质不变：仍然单调、样本量仍然实质性地改变结论（gap 从 4.73 变成
    约 4.78，量级相当，仍 > 2.0）。
    """
    vals = [shrink(12.0, n, 5.0, 1.0, game_var=_OVERDISPERSED_GAME_VAR,
                   tail_heavy=True)[0] for n in (2, 5, 20, 100)]
    assert vals == sorted(vals), "后验应随样本量单调上升"
    assert vals[-1] - vals[0] > 2.0, "样本量必须实质性地改变结论"


def test_fit_rate_model_stratifies_by_position():
    rng = np.random.default_rng(0)
    rows = []
    for acct, pos, lam in [(1, 1, 9.0), (2, 5, 3.0)]:
        for g in range(40):
            rows.append({"account_id": acct, "match_id": g, "position": pos,
                         "kills": rng.poisson(lam), "duration_min": 38.0})
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "kills", positions={1: 1, 2: 5})
    assert out[1]["rate"] > out[2]["rate"], "1 号位击杀率应显著高于 5 号位"
    assert out[1]["position"] == 1 and out[2]["position"] == 5
    assert out[1]["n_games"] == 40


def test_fit_rate_model_rejects_unknown_item():
    df = pd.DataFrame({"account_id": [1], "match_id": [1],
                       "position": [1], "duration_min": [30.0]})
    with pytest.raises(KeyError):
        fit_rate_model(df, "no_such_column", positions={1: 1})


# ---- 补充测试：锁定对 brief Step 3 参考实现的三处修正 ----
#
# 1) 参考实现里后验标准误（se）直接用未放大的 prior_var 结算，跟用来算
#    后验均值的 eff_prior_var（重尾放大后的有效先验方差）不是同一个数。
#    对几乎所有真实选手（raw_rate 只要偏离 prior_mean 一点，z2>0，
#    eff_prior_var 就会被放大）这会让 se 系统性偏小——模型一边说
#    "这可能是真实水平，不收缩"，一边却报一个跟没做重尾修正时一样小的
#    标准误，精度被凭空夸大，会直接污染 Task 8 用 se 撑开的置信区间。
#
# 2) 参考实现的 fit_rate_model 只认与 df 列名完全相同的 item_key。但
#    model/fantasy_stats.py 的 docstring 明确写了"跨列合成留给下游
#    （L3 速率模型）"处理：SCORING_ITEMS 18 项里，除 kills/deaths/
#    camps_stacked/stuns 外，其余可用项的 key 与实际列名全部不同
#    （例如 gpm→gold_per_min、tower_kills→towers_killed），Creep Score
#    更是要 last_hits+denies 逐局求和。不解析的话，Task 7 若直接用
#    SCORING_ITEMS 的 key 调用，15 个可得项里有 9 个会直接 KeyError。
#
# 3) 真实数据里 teamfight_participation / stuns 在目标选手+时间窗下
#    各有 54 行是 NaN（fantasy_stats.load_player_games 的 fillna 列表
#    没覆盖这两列——已用 data/pro_player_matches_2020_2026.csv 实测
#    验证：49762 行里 gold_per_min/kills 0 个 NaN，teamfight_participation
#    /stuns 各 54 个 NaN）。参考实现用 len(g)（原始行数）当 n 喂给
#    shrink，会把这些 NaN 行也算进样本量，n_games 偏大、se 被人为拉低。

def test_tail_heavy_se_reflects_inflated_uncertainty_not_just_mean():
    """重尾修正放大的是「有效先验方差」，喂给后验均值的 eff_prior_var
    必须同样喂给后验方差——否则对真·离群值，模型一边几乎不收缩均值，
    一边却报一个和没做重尾修正时一样小的标准误。"""
    _, se_normal = shrink(20.0, 30, 5.0, 1.0, game_var=20.0, tail_heavy=False)
    _, se_heavy = shrink(20.0, 30, 5.0, 1.0, game_var=20.0, tail_heavy=True)
    assert se_heavy > se_normal, "重尾修正减少收缩的同时必须相应放大标准误，否则精度被凭空夸大"


def test_fit_rate_model_resolves_creep_score_by_summing_last_hits_and_denies():
    """item_key 用 SCORING_ITEMS 的 key "creep_score"（不是原始列名），
    模型必须自己按 SCORING_ITEMS 声明的 ("last_hits","denies") 逐局求和。"""
    rows = [{"account_id": 1, "match_id": g, "position": 1,
             "last_hits": 300 + g, "denies": 10}
            for g in range(10)]
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "creep_score", positions={1: 1})
    expected_raw = float((df["last_hits"] + df["denies"]).mean())
    assert out[1]["raw_rate"] == pytest.approx(expected_raw)


def test_fit_rate_model_resolves_key_to_mismatched_column_name():
    """SCORING_ITEMS 多数 key 与实际列名不同（gpm→gold_per_min）。
    item_key 传 key 时必须能解析到正确的列，而不是报 KeyError。"""
    rows = [{"account_id": 1, "match_id": g, "position": 1,
             "gold_per_min": 600 + g}
            for g in range(10)]
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "gpm", positions={1: 1})
    assert out[1]["raw_rate"] == pytest.approx(float(df["gold_per_min"].mean()))


def test_fit_rate_model_still_rejects_item_with_no_resolvable_column():
    """madstone 在 SCORING_ITEMS 里 available=False、column=None，
    既不是 df 里的列，也解析不出原始列，必须继续 KeyError，
    不能被 SCORING_ITEMS 兜底成"假装存在"。"""
    df = pd.DataFrame({"account_id": [1], "match_id": [1], "position": [1]})
    with pytest.raises(KeyError):
        fit_rate_model(df, "madstone", positions={1: 1})


def test_fit_rate_model_does_not_inflate_n_games_with_nan_observations():
    """item_key 存在 NaN（例如真实数据里 teamfight_participation /
    stuns 各有 54 行 NaN）时，n_games 必须是有效观测数，不能把 NaN 行
    也计入样本量（否则 obs_var 被低估、se 被人为拉低）。"""
    rows = [{"account_id": 1, "match_id": g, "position": 1, "stuns": 2.0}
            for g in range(8)]
    rows += [{"account_id": 1, "match_id": 100 + g, "position": 1, "stuns": np.nan}
             for g in range(2)]
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "stuns", positions={1: 1})
    assert out[1]["n_games"] == 8, "2 行 NaN 不能被算进样本量"
    assert out[1]["raw_rate"] == pytest.approx(2.0)


# ---- 补充测试：修复【Critical】L3 的方差假设对多数计分项不成立 ----
#
# model/l3_player.py::shrink() 曾经用 obs_var = raw_rate/n 估观测方差——
# 裸泊松假定（Var=均值）。真实数据实测（按选手自己去均值后的局内残差，
# 不是全体选手合并的跨选手方差——那会把选手之间的强弱差异错当成局内
# 噪声，高估到 12.0x/7.8x 这类虚高数字）：last_hits 局内 sd 约是泊松假定
# 的 7.72x、stuns 约 6.08x、gold_per_min 约 4.24x、kills 约 1.56x、
# deaths 约 1.33x；teamfight_participation 反而只有约 0.20x（当前区间
# 偏宽约 5 倍）。fix-a-variance-report.md 有完整复现记录，与本仓库已有的
# 独立复算（model/l4_extremes.py::dispersion_ratio，reports/p2_variance_check.json）
# 量级一致。
#
# 修法：shrink() 新增必填参数 game_var（该选手该项的实测局内方差），
# obs_var 改为 max(game_var, 1e-6)/n；fit_rate_model 按选手自己的局内
# 方差估计 game_var，样本太小（< MIN_N_FOR_OWN_GAME_VAR）或方差退化为 0
# 时回退到同号位的池化方差（_position_game_var，做法与
# model/l4_extremes.py::empirical_residuals 同一个"按选手自己中心化"
# 思路）。tail_heavy 收缩的数学形式（z2/eff_prior_var/w/post 的公式）
# 完全不动，只是 obs_var 的来源变了。

def test_shrink_se_scales_with_measured_game_var_not_poisson():
    """核心护栏：直接证明 shrink() 的 se 现在跟着 game_var 走，而不是继续
    暗中假设 Var(单局)=raw_rate。用一个极大的 prior_var（约等于"没有先验
    信息"）隔离掉先验的耦合影响，这样 se 应该精确正比于 sqrt(game_var)：
    game_var 变成 raw_rate 的 4.24^2≈17.98 倍（本项目 GPM 实测 sd 比值）
    时，se 也应该跟着变成约 4.24 倍——如果 se 几乎不变（还停留在旧的
    sqrt(raw_rate/n) 量级），说明 obs_var 又在偷偷走 raw_rate/n 的老路，
    这类"方差假设整体错一个数量级"的问题会被这条测试当场抓到。"""
    raw_rate, n, prior_mean = 300.0, 50, 300.0
    uninformative_prior_var = 1e6      # 隔离先验耦合，让 se 几乎只由 obs_var 决定

    _, se_poisson_like = shrink(raw_rate, n, prior_mean, uninformative_prior_var,
                                game_var=raw_rate, tail_heavy=False)
    _, se_measured = shrink(raw_rate, n, prior_mean, uninformative_prior_var,
                            game_var=raw_rate * (4.24 ** 2), tail_heavy=False)

    assert se_measured == pytest.approx(se_poisson_like * 4.24, rel=0.02), (
        "se 没有精确正比于 sqrt(game_var)——obs_var 像是没有真正吃到 game_var 参数"
    )
    assert se_measured > 3.5 * se_poisson_like, (
        "game_var 增大约 18 倍时 se 几乎没变——obs_var 没有真正吃到 game_var，"
        "像是又回到了 raw_rate/n 的泊松假定"
    )


def test_shrink_handles_zero_game_var_without_dividing_by_zero():
    """观测方差为 0 的退化情形要处理：某选手该项局内方差恰好测出 0
    （例如极小样本巧合取值全同），obs_var 不能真的是 0，否则
    1/obs_var 除零。必须有正的地板，se 必须是有限正数。"""
    post, se = shrink(5.0, n=10, prior_mean=5.0, prior_var=1.0, game_var=0.0)
    assert np.isfinite(post) and np.isfinite(se), "game_var=0 不能产出 NaN/inf"
    assert se > 0.0, "地板后的 obs_var 必须严格为正，否则 se 无意义"


def test_fit_rate_model_se_reflects_measured_dispersion_not_poisson_assumption():
    """回归护栏（wiring 版）：合成一个真实局内方差远大于均值的计分项
    （sd/sqrt(mean)≈8.7x，量级对齐本项目 last_hits 实测的 7.72x），大样本
    单选手（n=300，经验方差估计足够稳），断言 fit_rate_model 报出的 se
    确实吃到了这份过散，而不是继续假装 Var(单局)=mean。"""
    rng = np.random.default_rng(42)
    mu, true_sd = 300.0, 150.0     # true_sd/sqrt(mu) ≈ 8.66，量级对齐 last_hits 实测
    n = 300
    values = np.maximum(rng.normal(mu, true_sd, size=n), 0.0)
    df = pd.DataFrame({"account_id": [1] * n, "match_id": range(n),
                       "position": [1] * n, "last_hits": values,
                       "duration_min": [38.0] * n})
    out = fit_rate_model(df, "last_hits", positions={1: 1})

    poisson_implied_se = (out[1]["raw_rate"] / n) ** 0.5
    assert out[1]["se"] > 2.5 * poisson_implied_se, (
        "se 太接近泊松假定隐含的量级——obs_var 像是又变回了 raw_rate/n"
    )
    assert np.isfinite(out[1]["se"]) and np.isfinite(out[1]["rate"])


def test_fit_rate_model_falls_back_to_pooled_variance_for_small_sample_players():
    """样本极少的选手自身方差估计本身不稳——必须向同号位池化方差回退，
    不能被自己那几局巧合出的方差主导。4 名"老将"（每人 200 局，真实
    局内 sd≈130，量级对齐 last_hits 实测）定出该号位的池化方差；1 名
    "新秀"只打 3 局，且这 3 局刻意取得几乎一样（299/300/301，样本方差
    仅 1.0）——如果模型错误地直接采用新秀自己这 3 局測出的方差，se 会
    小得离谱；正确回退到池化方差后，新秀的 se 应该显著更接近老将量级的
    不确定性，而不是被这 3 局的巧合"骗"成过度自信。"""
    rookie_n_games = 3
    veteran_n_games = MIN_N_FOR_OWN_GAME_VAR * 10   # 远高于门槛，稳稳吃"自身方差"分支
    assert rookie_n_games < MIN_N_FOR_OWN_GAME_VAR, (
        "先确认新秀的局数确实低于门槛，否则本测试测不出『小样本回退』这件事"
    )
    rng = np.random.default_rng(7)
    mu, true_sd = 300.0, 130.0
    rows = []
    for acct in (1, 2, 3, 4):
        vals = np.maximum(rng.normal(mu, true_sd, size=veteran_n_games), 0.0)
        for g, v in enumerate(vals):
            rows.append({"account_id": acct, "match_id": f"{acct}-{g}",
                         "position": 1, "last_hits": v, "duration_min": 38.0})
    for g, v in enumerate([299.0, 300.0, 301.0][:rookie_n_games]):
        rows.append({"account_id": 5, "match_id": f"5-{g}",
                     "position": 1, "last_hits": v, "duration_min": 38.0})
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "last_hits", positions={1: 1, 2: 1, 3: 1, 4: 1, 5: 1})

    assert out[5]["n_games"] == rookie_n_games
    rookie_own_var = float(np.var([299.0, 300.0, 301.0], ddof=1))     # == 1.0
    naive_se_from_own_var = (rookie_own_var / rookie_n_games) ** 0.5   # 若错误直接用自身方差
    assert out[5]["se"] > 10 * naive_se_from_own_var, (
        "新秀的 se 太接近『直接用自己 3 局方差』会给出的量级——"
        "小样本没有正确回退到同号位池化方差"
    )
    # 更稳健的第二个校验：不依赖手推的绝对数值（那依赖随机种子下 prior_var
    # 具体算出多少），而是跟老将自己的 se 比——两者共享同一个池化方差，
    # 新秀样本更少、se 只应该更大或至少同量级，不该远小于老将。
    veteran_ses = [out[a]["se"] for a in (1, 2, 3, 4)]
    assert out[5]["se"] > 0.5 * min(veteran_ses), (
        "新秀的 se 远小于老将的 se——两者共享同一个池化方差，"
        "新秀样本更少，se 不该反而小很多"
    )


def test_fit_rate_model_handles_zero_variance_player_without_crashing():
    """整个号位里所有选手的取值都恒定（局内方差恰好为 0）是最极端的退化
    情形——_position_game_var 的池化方差也会测出 0/NaN，必须有兜底，
    不能让 NaN 或 ZeroDivisionError 传播出去。"""
    rows = [{"account_id": 1, "match_id": g, "position": 1, "kills": 5}
            for g in range(10)]
    df = pd.DataFrame(rows)
    out = fit_rate_model(df, "kills", positions={1: 1})
    assert np.isfinite(out[1]["se"]) and out[1]["se"] >= 0.0
    assert np.isfinite(out[1]["rate"])
