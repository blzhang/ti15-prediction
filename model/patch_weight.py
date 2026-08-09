"""按版本号给历史比赛打折的权重层（L1 用）。

**为什么单有天数衰减不够。** 改动前 L1 只有一条按天数的指数衰减（半衰期
270 天），它隐含的假设是「时间过得越久越不像现在」。但 Dota 的变化不是
连续的，是跳变的：7.39→7.40 隔了 208 天，7.40→7.41 只隔了 98 天。同样是
「上一个版本的比赛」，纯天数衰减给它们的折扣差了一倍多；而同样是「隔了
100 天」，跨没跨版本对参考价值的影响完全不同。

**这一层做什么。** 给每场比赛算一个整数距离 k =「离参照时点隔了几个
版本」，权重乘 `gamma ** k`。它与天数衰减**相乘**而不是替换——两者管的
不是同一件事：天数管「阵容磨合、状态漂移」，版本管「这套打法还成不成立」。

**gamma 的默认值是 1（关闭）。** `GAMMA_OFF = 1.0` 时 `patch_weights` 返回
逐位精确的 1.0，改动前后的产出物字节级一致。gamma 由验证期与半衰期、岭
强度联合搜出来；搜到 1 就等于「数据说这一层没用」，那就该关掉。
`tests/test_patch_weight.py::test_patch_weights_gamma_one_is_bit_identical_to_all_ones`
把这条钉住。

**参照时点必须由调用方传，不许写死成 7.41。** 训练/验证/测试切分时，
anchor 得是**切点当时**的最新版本；写死成 7.41 就是拿未来的版本表去给
过去的数据打折，是泄漏。l1_strength.py 里三处调用分别传 CUT_V / CUT_T /
NOW，就是为了这个。

**版本表只有一张。** 直接读 `model/patches.py` 的 `PATCH_RELEASE_UTC`，
不另立副本。那张表最早只到 7.31（2022-02-23），而 L1 的训练数据从
2022-01-01 起，中间有 54 天无版本可归——这些比赛的索引落到 0，等价于
「比 7.31 再老一档」。这是刻意的地板行为，不是缺陷：它们本来就该拿到全
表最低的权重（在 270 天半衰期下这批比赛的时间权重已不足 1.5%）。
"""
import bisect

import numpy as np

from model.patches import PATCH_RELEASE_UTC, patch_ts

GAMMA_OFF = 1.0   # 关闭这一层；返回值逐位等于 1.0

# 全部版本发布时刻（升序），模块导入时算一次。索引 = 已发布的版本数。
_RELEASES = sorted(patch_ts(name) for name in PATCH_RELEASE_UTC)


def patch_index(ts):
    """时刻 ts 之前（含当秒）已经发布了几个版本。

    7.41 发布当秒即算进 7.41（`bisect_right`）。比表里最早的版本还早 -> 0。
    """
    return bisect.bisect_right(_RELEASES, int(ts))


def patch_distance(ts, ref_ts):
    """比赛时刻 ts 离参照时点 ref_ts 隔了几个版本，最小为 0。

    越老的比赛距离越**大**。比 ref_ts 还新的比赛截断到 0——负距离会让
    `gamma ** k` 变成放大系数，是一个跑得通但含义相反的结果，比报错难
    发现得多。
    """
    return max(0, patch_index(ref_ts) - patch_index(ts))


def patch_weights(ts_array, ref_ts, gamma):
    """向量化的 `gamma ** 版本距离`，形状与 ts_array 一致。

    gamma 必须落在 (0, 1]：>1 会让老比赛权重变大，=0 会把除当前版本外的
    一切直接抹零（半衰期已经在做温和衰减，这里再来一刀不是本层的用途）。
    两种都在入口报错，不静默夹取。
    """
    if not (0.0 < float(gamma) <= 1.0):
        raise ValueError(
            "gamma 必须在 (0, 1]，收到 %r。>1 会让越老的版本权重越大（方向反了），"
            "=0 会把非当前版本的比赛全部抹零。" % (gamma,))
    ts = np.asarray(ts_array, dtype=float)
    if float(gamma) == GAMMA_OFF:
        # 逐位还原：不走幂运算，避免 1.0**k 在任何平台上出现浮点尾差
        return np.ones(ts.shape, dtype=np.float64)
    ref_idx = patch_index(ref_ts)
    idx = np.searchsorted(np.asarray(_RELEASES, dtype=float), ts, side="right")
    k = np.maximum(0, ref_idx - idx)
    return np.power(float(gamma), k.astype(np.float64))
