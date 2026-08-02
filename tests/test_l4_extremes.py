"""task-9-brief.md Step 1：先原样抄录 brief 给的 6 条测试（threshold_prob x3、
needs_gpd x1、who_leads x2），配 brief Step 3 的参考实现原样跑一遍
（repro 见 task-9-report.md）：**5 passed, 1 failed**——
`test_smoothing_keeps_zero_count_thresholds_off_zero` 断言
`threshold_prob([10]*200, 25, n_games=145, smooth=0.5) < 0.2`，但代入
brief 自己的参考实现精确算出 0.30312...，不是 <0.2。

这是本项目第 11 个"brief 自己的测试和参考实现互相矛盾"的真实例，但和前 10
个性质不同：前 10 个都是"测试和实现共享同一个错误前提，彼此自洽所以能
骗过"（brief 自己都不知道错在哪）；这次是压根跑不过，属于"brief 作者显然
没有把这个数值真的算一遍"。`threshold_prob` 的公式本身（Jeffreys 型可加
平滑）没有问题，问题在 brief 测试里那个具体字面量 0.2——已改成对解析解
取 pytest.approx，不改变"经验频率为 0 时不应输出恰好 0"这条核心断言，
也没有改 threshold_prob 的实现本身。

who_leads 的两条 brief 测试（`_probabilities_sum_to_one` /
`_favours_players_with_more_games`）在 brief 自己的 `rng.poisson` 参考实现
下能通过（不是这次要修的对象——它们和实现共享同一个前提："单局方差可以
用 rate 本身当泊松参数近似"）。但这个共享前提本身被控制器实测证伪并被
本任务独立复算证实（task-9-report.md）：局间标准差 / 泊松假定标准差，
last_hits≈7.2-7.7x / gold_per_min≈4.1-4.3x / stuns≈5.9-6.1x 等，一个标量
rate 结构上就不携带"这项有多离散"的信息。所以 who_leads 的接口必须变——
新增 `residual_pool` 参数（真实局间残差的经验分布，`empirical_residuals`
产出），不再是"喂个 rate 就靠 rng.poisson 自己编方差"。下面两条测试保留
brief 原本想测的行为（概率归一、打得多者更易夺魁），只是把喂入方式换成
新接口；新增测试锁定"过散项不能退化成均值最高者近乎必胜"这条本任务的
核心修正，以及新增的 `empirical_residuals`/`dispersion_ratio` 两个辅助函数
（这两个不在 brief 的 Interfaces 列表里，是修 who_leads 时必须新增的支撑
函数，见 model/l4_extremes.py 模块 docstring）。
"""
import numpy as np
import pytest
from model.l4_extremes import (
    threshold_prob, who_leads, needs_gpd, empirical_residuals, dispersion_ratio,
)


# ---- brief 给定的测试（Step 1，threshold_prob 前两条 + needs_gpd 原样使用） ----

def test_threshold_prob_matches_one_minus_miss_all():
    samples = [10] * 90 + [30] * 10          # 单局超过 25 的经验频率 = 0.1
    p = threshold_prob(samples, threshold=25, n_games=10, smooth=0.0)
    assert p == pytest.approx(1 - 0.9 ** 10)


def test_threshold_prob_grows_with_more_games():
    s = [10] * 99 + [30]
    assert threshold_prob(s, 25, 50) > threshold_prob(s, 25, 10)


def test_needs_gpd_only_when_threshold_exceeds_observed_range():
    s = [1, 5, 12, 26, 31]
    assert needs_gpd(s, threshold=20) is False
    assert needs_gpd(s, threshold=40) is True


# ---- 修正：brief 第 11 个真问题（见文件头 docstring 与 task-9-report.md） ----

def test_smoothing_keeps_zero_count_thresholds_off_zero():
    """经验频率为 0 时不应输出 0 概率 —— 层次平滑的意义所在。

    brief 原文断言 `< 0.2`；代入 brief 自己的参考实现（含默认 smooth=0.5）
    精确算出 0.30312267659527714，断言不成立（独立复现：5 passed, 1
    failed，见文件头 docstring）。threshold_prob 的公式没有问题，问题
    在 brief 那个未经验算的字面量。改为对解析解取 pytest.approx，核心
    断言"不能恰好是 0、也不能逼近 1"保留。
    """
    s = [10] * 200
    p = threshold_prob(s, 25, n_games=145, smooth=0.5)
    exact = 1.0 - (1.0 - 0.5 / 201.0) ** 145
    assert p == pytest.approx(exact)
    assert 0.0 < p < 0.5, "远离 0（平滑生效）也远离 1（145 局内没有失控）"


# ---- 新增：empirical_residuals / dispersion_ratio（who_leads 修正的支撑函数）----

def test_empirical_residuals_centers_per_player_not_globally():
    """残差必须按选手自己的均值中心化，不能用全局均值——否则不同能力的
    选手之间的真实差异会被误当成"局间噪声"混进残差池，弥散度会被
    系统性高估。"""
    values = [10, 12, 8, 100, 104, 96]      # 选手1: 10/12/8(均值10)；选手2: 100/104/96(均值100)
    accounts = [1, 1, 1, 2, 2, 2]
    resid = empirical_residuals(values, accounts)
    assert resid.tolist() == pytest.approx([0, 2, -2, 0, 4, -4])
    assert resid.mean() == pytest.approx(0.0)


def test_dispersion_ratio_is_near_one_for_true_poisson_data():
    """自建真泊松数据校验 dispersion_ratio 本身的计算没有算错——
    真泊松数据的实测/假定比值应落在 1 附近。"""
    rng = np.random.default_rng(3)
    account_ids = np.repeat(np.arange(20), 300)
    per_player_rates = rng.uniform(3, 10, size=20)
    values = np.concatenate([rng.poisson(r, size=300) for r in per_player_rates])
    out = dispersion_ratio(values, account_ids)
    assert 0.85 < out["ratio_mean"] < 1.15
    assert out["n_players"] == 20


def test_dispersion_ratio_detects_overdispersion():
    """人为构造一批弥散度为泊松假定 4 倍的数据（模拟 last_hits/gpm 的真实
    情形），dispersion_ratio 必须能正确识别出来，不能被压回 1 附近。"""
    rng = np.random.default_rng(4)
    account_ids = np.repeat(np.arange(20), 300)
    per_player_rates = rng.uniform(200, 300, size=20)
    values = np.concatenate([rng.normal(r, 4 * np.sqrt(r), size=300) for r in per_player_rates])
    out = dispersion_ratio(values, account_ids)
    assert out["ratio_mean"] > 3.0


# ---- who_leads：接口因修正 Poisson 假定而变（见文件头 docstring）----
# 下面两条沿用 brief 原本想测的行为，只是把喂入方式换成 residual_pool。

def test_who_leads_probabilities_sum_to_one():
    rng = np.random.default_rng(0)
    rates = {1: 9.0, 2: 7.0, 3: 5.0}
    games = {1: 20, 2: 20, 3: 20}
    residual_pool = rng.normal(0.0, 2.0, size=5000)   # 玩具残差池，只测排序/归一逻辑
    out = who_leads(rates, games, residual_pool, n_sim=3000, seed=0)
    assert abs(sum(out.values()) - 1.0) < 1e-9
    assert out[1] > out[2] > out[3]


def test_who_leads_favours_players_with_more_games():
    rng = np.random.default_rng(1)
    rates = {1: 6.0, 2: 6.0}
    residual_pool = rng.normal(0.0, 2.0, size=5000)
    out = who_leads(rates, {1: 30, 2: 6}, residual_pool, n_sim=3000, seed=1)
    assert out[1] > out[2], "同等能力下，打得多的更可能拿到全场之最"


def test_who_leads_accepts_per_player_residual_pool_dict():
    """真实报告用法：不同位置/不同计分项的残差池形状不同，按
    {account_id: 残差池} 传入。均值相同时，局间波动更大的一方应更容易
    偶然打出全场最高——这条断言在"共用同一个残差池"的写法下测不出来，
    必须两个人的池子本身不同才能验证 dict 分支被正确消费。"""
    rng = np.random.default_rng(5)
    rates = {1: 10.0, 2: 10.0}
    games = {1: 20, 2: 20}
    pools = {1: rng.normal(0.0, 0.5, size=4000),
             2: rng.normal(0.0, 5.0, size=4000)}
    out = who_leads(rates, games, pools, n_sim=5000, seed=2)
    assert out[2] > out[1]


def test_who_leads_does_not_degenerate_for_overdispersed_item():
    """核心回归锁：过散项（如 GPM，本任务独立实测局间 sd 约为泊松假定
    sd 的 4 倍以上，见 task-9-report.md）即便两名选手能力（rate）有一定
    差距，真实局间波动这么大时"打得少的那位偶然打出全场最高"应保留
    不可忽视的概率——不能让"均值最高者近乎必胜"。

    对照组：如果错误套用 brief 原参考实现的 rng.poisson(rate)（等价于
    sd=sqrt(rate)，远小于实测），同样的输入会给出明显更极端（更接近
    确定性）的结果——用真实复现的量级（rate_a/rate_b 与 sd 均取自本任务
    对 gpm 的独立实测，见 task-9-report.md）验证修正确实改变了结论，
    不是"换了个接口但数值上什么都没变"。
    """
    rng = np.random.default_rng(7)
    rate_a, rate_b = 767.0, 747.0     # 取自真实 1 号位 GPM 后验（Satanic vs Pure）
    real_sd = 110.0                   # 本任务独立实测 gpm 局间 sd 量级（≈4x 泊松假定）
    games = {1: 20, 2: 20}

    residual_pool = rng.normal(0.0, real_sd, size=20000)
    out_real = who_leads({1: rate_a, 2: rate_b}, games, residual_pool, n_sim=20000, seed=1)
    assert out_real[1] < 0.75, "真实弥散度下，2.7%的均值差距不该被放大成近乎必胜"

    poisson_sd = float(np.sqrt(rate_a))
    poisson_like_pool = rng.normal(0.0, poisson_sd, size=20000)
    out_poisson = who_leads({1: rate_a, 2: rate_b}, games, poisson_like_pool, n_sim=20000, seed=1)
    assert out_poisson[1] > out_real[1] + 0.05, "泊松低估方差会让结果比真实弥散度下明显更极端"


# ---- who_leads 的两个防御分支：补测试锁定（Minor 缺陷修复） ----
#
# 这两个分支此前零测试覆盖：一是全部选手预计参赛局数都是 0（比如整批
# 预测都提前出局/数据缺失），二是 residual_pool 为空数组（调用方传参
# 出错）。两者都已经在实现里有清晰的 ValueError 防护，这里只是补上
# 回归测试锁定这个行为，不是修复新发现的 bug。

def test_who_leads_raises_when_all_players_have_zero_games():
    """防御分支之一：n_games_by_player 里所有选手的局数都是 0 时，
    `any_games` 恒为 False，应该清晰地报错，而不是静默返回一个
    全 -inf/无意义的结果。"""
    rates = {1: 9.0, 2: 7.0}
    residual_pool = np.array([0.0, 1.0, -1.0])
    with pytest.raises(ValueError):
        who_leads(rates, {1: 0, 2: 0}, residual_pool, n_sim=100, seed=0)


def test_who_leads_raises_when_residual_pool_is_empty():
    """防御分支之二：residual_pool 是空数组时，`_residual_pool_for` 应该
    清晰报错，而不是让 rng.choice 在空数组上抛一个更难懂的底层异常，
    或者静默产出 NaN。

    必须用 `match=` 锁定消息里的 "residual_pool"：numpy 的
    `Generator.choice` 对空数组自己也会抛 ValueError（消息是"a cannot be
    empty unless no samples are taken"），如果只断言异常类型是
    ValueError、不看消息内容，这条测试在 `_residual_pool_for` 的显式
    检查被删掉之后仍然会「误通过」——因为调用链后面 `rng.choice(pools[a],
    ...)` 恰好也会抛同一个异常类型，测不出我们自己这层防护是否存在。"""
    rates = {1: 9.0}
    with pytest.raises(ValueError, match="residual_pool"):
        who_leads(rates, {1: 20}, residual_pool=np.array([]), n_sim=100, seed=0)
