"""L5 窗口回测的纯函数层。

回答的问题：选手层的数据窗口该不该切到当届版本发布日起（spec
docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md）。

本模块只放不碰磁盘、不碰网络的纯函数，方便全部用小 fixture 测；读真实
CSV、跑四届 holdout、出报告在 model/l5_window_backtest.py。
"""
from model.patches import patch_ts, previous_patch

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
