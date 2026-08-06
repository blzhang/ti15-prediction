# 选手数据窗口版本切换回测 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 TI 2022/2023/2024/2025 四届配对回测，判定「选手数据窗口切到当届版本发布日起」是否比现行「开赛前 955 天」策略更能预测 TI 赛场上选手数据的同号位排序。

**Architecture:** 新增两个模块，不修改任何现有模块。`model/patches.py` 是版本发布时间常量表；`model/l5_window.py` 是纯函数库（窗口臂定义、号位推导、Spearman 评分、符号检验）；`model/l5_window_backtest.py` 是编排层与 CLI，读真实 CSV、跑四届 × 12 项 × 7 臂、出 `reports/p5_window_backtest.json` + `.md`。预测速率直接复用 `model.l3_player.fit_rate_model`，一行不改，每个臂只是喂不同的 df 时间切片。

**Tech Stack:** Python 3、pandas ≥2.0、numpy ≥1.24、scipy ≥1.10（`spearmanr` / `binomtest`）、pytest ≥7。

## Global Constraints

- **设计文档**：`docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md`。本计划的每个口径决定都以它为准。
- **不改产线**：不修改 `model/l3_player.py`、`model/l4_*.py`、`model/fantasy_stats.py`、`site/`、`frozen/`，不改任何现有 `since_ts` 默认值，不重新冻结存证。
- **测试不打网、不读真实数据**：`tests/` 下新增的测试全部走内联构造的小 fixture。真实数据只在 Task 9 手工跑 CLI 时使用。
- **判定规则已预注册**，写死为模块级常量，实现时不得改动：`ALPHA = 0.05`、`MIN_HOLDOUTS_POSITIVE = 3`、`BASELINE_ARM = "L955d"`、`TREATMENT_ARM = "patch"`。判定"支持切窗口"需同时满足：配对符号检验 `p < ALPHA` 且中位差 > 0；四届中至少 `MIN_HOLDOUTS_POSITIVE` 届届内中位差为正。
- **12 个计分项**（blob 三项 smokes/tormentor/courier 历史届取不到，排除）：`kills`、`deaths`、`creep_score`、`gpm`、`tower_kills`、`roshan`、`teamfight`、`wards`、`camps_stacked`、`runes`、`first_blood`、`stuns`。
- **七个臂**（全部相对各届开赛日定义，`until` 一律等于开赛时间）：`all`、`L955d`、`L365d`、`L180d`、`L105d`、`patch`、`prev_patch`。
- **不许悄悄丢数据**：臂间必须取选手交集；跳过的单元必须带原因进报告；版本表缺项直接抛错，不回退。
- **提交信息**：中文，结尾附 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`。

### 与 spec §5 的一处有意偏离

spec §5 把全部函数放在单个 `model/l5_window_backtest.py`。本计划改为拆成
`model/l5_window.py`（纯函数库）+ `model/l5_window_backtest.py`（编排 + CLI），
因为这正是本仓既有约定：`l4_fantasy.py` / `l4_fantasy_report.py`、
`l4_extremes.py` / `l4_extremes_report.py`、`l4_players.py` / `l4_players_report.py`
全是这个两层结构。函数名与职责与 spec 完全一致，只是落在两个文件里。

## 文件结构

| 文件 | 职责 |
|---|---|
| `model/patches.py`（新） | 版本名 → 发布时间戳常量表；`patch_ts` / `previous_patch` |
| `model/l5_window.py`（新） | 纯函数：`window_arms` / `sliding_arms` / `derive_positions` / `coarsen` / `score_arm` / `paired_sign_test` / `patch_boundaries_in` |
| `model/l5_window_backtest.py`（新） | 编排：`holdout_participants` / `holdout_actuals` / `intersect_players` / `fit_arm` / `run_holdout` / `decide` / `run_sliding` / `run_robustness` / `aggregate_robustness` / `build_report` / `render_markdown` / CLI |
| `tests/test_patches.py`（新） | 版本表测试 |
| `tests/test_l5_window.py`（新） | 纯函数库测试 |
| `tests/test_l5_window_backtest.py`（新） | 编排层测试 |
| `reports/p5_window_backtest.json` / `.md`（新，Task 9 产出） | 回测结果 |

---

### Task 1: 版本发布时间表 `model/patches.py`

**Files:**
- Create: `model/patches.py`
- Test: `tests/test_patches.py`

**Interfaces:**
- Consumes: 无
- Produces: `PATCH_RELEASE_UTC: dict[str, str]`、`patch_ts(name: str) -> int`、`previous_patch(name: str) -> str`、`FETCHED_AT: str`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_patches.py`：

```python
"""对 model/patches.py 的单元测试。

版本发布时间是整个回测的地基：patch 臂的起点就是这张表里的时间戳。
表错了，回测的 treatment 臂就是错的，而且不会有任何地方报错——所以
这里既钉死具体数值，也钉死"查不到必须抛错"这条不许静默回退的约定。
"""
import pytest

from model.patches import PATCH_RELEASE_UTC, patch_ts, previous_patch


def test_patch_ts_7_41_matches_opendota_constants():
    """7.41 = 2026-03-24T00:50:59Z，取自 OpenDota constants/patch。
    这是 TI15 的版本，也是这次回测要验证的那个切点，数值必须钉死。"""
    assert patch_ts("7.41") == 1774313459


def test_patch_ts_is_strictly_increasing_over_the_table():
    """表里的版本按名字升序排列时，发布时间必须也严格递增。
    抄错一个日期最容易表现为顺序颠倒，这条能直接抓到。"""
    names = sorted(PATCH_RELEASE_UTC)
    stamps = [patch_ts(n) for n in names]
    assert stamps == sorted(stamps)
    assert len(set(stamps)) == len(stamps)


def test_patch_ts_raises_on_unknown_patch_instead_of_falling_back():
    """查不到必须 KeyError。静默回退（例如返回 0）会让该届的 patch 臂
    悄悄退化成全历史臂，而报告里完全看不出来。"""
    with pytest.raises(KeyError):
        patch_ts("7.99")


def test_previous_patch_walks_back_by_release_time():
    assert previous_patch("7.41") == "7.40"
    assert previous_patch("7.39") == "7.38"


def test_previous_patch_raises_on_earliest_entry():
    """表里最早的版本没有上一个——不能悄悄返回它自己。"""
    earliest = sorted(PATCH_RELEASE_UTC, key=patch_ts)[0]
    with pytest.raises(KeyError):
        previous_patch(earliest)


def test_previous_patch_raises_on_unknown_patch():
    with pytest.raises(KeyError):
        previous_patch("7.99")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/test_patches.py -v
```

预期：全部 FAIL，`ModuleNotFoundError: No module named 'model.patches'`

- [ ] **Step 3: 写实现**

创建 `model/patches.py`：

```python
"""Dota 2 版本发布时间表。

来源：OpenDota `GET https://api.opendota.com/api/constants/patch`，
2026-08-06 取数。上游同一份数据也可在 odota/dotaconstants 的
build/patch.json 核对。

本仓既有约定是「跑的时候不打网」，所以取到的常量落盘并注明来源与取数日期，
不在运行时请求 API。只收录本次回测用得到的区间（7.31 起）。

缺项一律抛 KeyError，不静默回退——回退会让某届的 patch 臂悄悄退化成
全历史臂，而报告里看不出任何异常。
"""
import datetime

FETCHED_AT = "2026-08-06"

# 版本名 -> 发布时间（UTC，ISO 8601）。原样抄自 OpenDota constants/patch 的
# date 字段，只截掉毫秒（本仓所有时间窗都按秒比较）。
PATCH_RELEASE_UTC = {
    "7.31": "2022-02-23T23:46:14Z",
    "7.32": "2022-08-24T02:16:32Z",
    "7.33": "2023-04-21T01:22:56Z",
    "7.34": "2023-08-09T00:11:15Z",
    "7.35": "2023-12-14T16:07:43Z",
    "7.36": "2024-05-23T05:26:05Z",
    "7.37": "2024-08-01T07:30:27Z",
    "7.38": "2025-02-19T13:48:29Z",
    "7.39": "2025-05-22T23:36:01Z",
    "7.40": "2025-12-16T00:50:40Z",
    "7.41": "2026-03-24T00:50:59Z",
}


def patch_ts(name):
    """版本名 -> Unix 秒。查不到直接 KeyError（见模块 docstring）。"""
    if name not in PATCH_RELEASE_UTC:
        raise KeyError(
            "patches.py 里没有版本 %r；已收录 %s。不静默回退——回退会让该届的 "
            "patch 臂悄悄变成全历史臂。" % (name, sorted(PATCH_RELEASE_UTC)))
    dt = datetime.datetime.strptime(PATCH_RELEASE_UTC[name], "%Y-%m-%dT%H:%M:%SZ")
    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())


def previous_patch(name):
    """按发布时间排序取上一个版本名。最早的版本没有上一个 -> KeyError。"""
    patch_ts(name)   # 未知版本在这里统一抛 KeyError
    order = sorted(PATCH_RELEASE_UTC, key=patch_ts)
    i = order.index(name)
    if i == 0:
        raise KeyError("%r 是表里最早的版本，没有上一个版本" % name)
    return order[i - 1]
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/test_patches.py -v
```

预期：6 passed

- [ ] **Step 5: 提交**

```bash
git add model/patches.py tests/test_patches.py
git commit -m "$(printf 'feat: 版本发布时间常量表，缺项抛错不回退\n\n来源 OpenDota constants/patch，2026-08-06 取数，落盘不在运行时打网。\n查不到的版本直接 KeyError——静默回退会让该届的 patch 臂悄悄退化成\n全历史臂，而报告里看不出任何异常。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

### Task 2: 候选臂定义 `window_arms` / `sliding_arms`

**Files:**
- Create: `model/l5_window.py`
- Test: `tests/test_l5_window.py`

**Interfaces:**
- Consumes: `model.patches.patch_ts`、`model.patches.previous_patch`
- Produces: `ARM_LOOKBACK_DAYS: dict[str, int]`、`window_arms(event_start_ts: int, patch_name: str) -> dict[str, tuple[int, int]]`、`sliding_arms(event_start_ts: int, length_days: int = 105, n_steps: int = 4) -> dict[str, tuple[int, int]]`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_l5_window.py`：

```python
"""对 model/l5_window.py 的单元测试（纯函数层，全部走内联 fixture）。"""
import datetime

import pandas as pd
import pytest

from model.patches import patch_ts
from model.l5_window import window_arms, sliding_arms


def _utc(y, m, d):
    return int(datetime.datetime(y, m, d, tzinfo=datetime.timezone.utc).timestamp())


TI15_START = _utc(2026, 8, 13)


def test_baseline_arm_l955d_reproduces_the_production_2024_01_01_cutoff():
    """spec §3 的核心口径：现行产线写的是日历日期 2024-01-01，它对 TI15 的
    真实含义是「开赛前 955 天」。这条断言把两者的等价性钉死——baseline 臂
    的定义一旦漂了，整个回测比的就不再是产线策略。"""
    arms = window_arms(TI15_START, "7.41")
    assert arms["L955d"][0] == _utc(2024, 1, 1)


def test_window_arms_has_exactly_the_seven_preregistered_arms():
    arms = window_arms(TI15_START, "7.41")
    assert set(arms) == {"all", "L955d", "L365d", "L180d", "L105d", "patch", "prev_patch"}


def test_patch_arm_starts_exactly_at_the_patch_release_timestamp():
    arms = window_arms(TI15_START, "7.41")
    assert arms["patch"][0] == patch_ts("7.41")
    assert arms["prev_patch"][0] == patch_ts("7.40")


def test_all_arms_end_at_the_event_start():
    """任何一个臂都不许把开赛当天及以后的数据喂进训练——那是数据泄漏。"""
    arms = window_arms(TI15_START, "7.41")
    assert all(until == TI15_START for _, until in arms.values())


def test_all_arm_starts_at_zero():
    assert window_arms(TI15_START, "7.41")["all"][0] == 0


def test_sliding_arms_are_contiguous_non_overlapping_and_complete():
    """固定长度往前滑：段与段首尾相接、不重叠、不留空隙。"""
    arms = sliding_arms(TI15_START, length_days=105, n_steps=4)
    assert list(arms) == ["slide0", "slide1", "slide2", "slide3"]
    assert arms["slide0"][1] == TI15_START
    for k in range(3):
        assert arms["slide%d" % k][0] == arms["slide%d" % (k + 1)][1]
    for since, until in arms.values():
        assert until - since == 105 * 86400
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/test_l5_window.py -v
```

预期：全部 FAIL，`ModuleNotFoundError: No module named 'model.l5_window'`

- [ ] **Step 3: 写实现**

创建 `model/l5_window.py`：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/test_l5_window.py -v
```

预期：6 passed

- [ ] **Step 5: 提交**

```bash
git add model/l5_window.py tests/test_l5_window.py
git commit -m "$(printf 'feat: 七个候选窗口臂与等长滑动窗口\n\n臂全部相对各届开赛日定义，比的是策略不是日期。baseline 臂 L955d\n钉死了与产线 2024-01-01 的等价性（2024-01-01 到 TI15 开赛恰好 955 天）。\n所有臂 until 都等于开赛时间，杜绝把开赛当天数据喂进训练。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

### Task 3: 号位推导 `derive_positions` / `coarsen`

**Files:**
- Modify: `model/l5_window.py`
- Test: `tests/test_l5_window.py`

**Interfaces:**
- Consumes: `model.l5_window` 已有内容
- Produces: `derive_positions(df: pandas.DataFrame) -> dict[int, int]`（值为 1..5）、`coarsen(positions: dict[int, int]) -> dict[int, str]`（值为 `"core"` / `"support"`）

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_l5_window.py` 末尾：

```python
from model.l5_window import derive_positions, coarsen


def _pm_rows(match_id, side_offset, net_worths, account_ids):
    """造一方五个人的选手-比赛行。side_offset=0 是天辉，128 是夜魇。"""
    return [{"match_id": match_id, "account_id": a, "player_slot": side_offset + i,
             "net_worth": nw}
            for i, (a, nw) in enumerate(zip(account_ids, net_worths))]


def test_derive_positions_ranks_by_net_worth_within_each_team_side():
    """队内净资产降序 = 1..5 号位。这是本项目唯一可用的号位来源：
    ti_2021_2025_player_matches.csv 自带的 fantasy_role 列有 2240 个 NaN
    且出现 0/3/4 等无法解释的取值，不能用。"""
    rows = (_pm_rows(1, 0, [30000, 25000, 20000, 15000, 10000], [11, 12, 13, 14, 15])
            + _pm_rows(1, 128, [31000, 26000, 21000, 16000, 11000], [21, 22, 23, 24, 25]))
    pos = derive_positions(pd.DataFrame(rows))
    assert pos == {11: 1, 12: 2, 13: 3, 14: 4, 15: 5,
                   21: 1, 22: 2, 23: 3, 24: 4, 25: 5}


def test_derive_positions_follows_net_worth_not_player_slot_order():
    """把净资产顺序反过来，推出的号位必须跟着反——否则说明实现其实是
    在按 player_slot 顺序发号位，那就完全没有信息量了。"""
    rows = _pm_rows(1, 0, [10000, 15000, 20000, 25000, 30000], [11, 12, 13, 14, 15])
    pos = derive_positions(pd.DataFrame(rows))
    assert pos == {11: 5, 12: 4, 13: 3, 14: 2, 15: 1}


def test_derive_positions_takes_the_mode_across_matches():
    """一名选手在两场里是 1 号位、一场里是 2 号位 -> 取众数 1。
    单场的临时换位不该改变他的号位归属。"""
    rows = []
    for mid, nws in [(1, [30000, 25000, 20000, 15000, 10000]),
                     (2, [30000, 25000, 20000, 15000, 10000]),
                     (3, [25000, 30000, 20000, 15000, 10000])]:
        rows += _pm_rows(mid, 0, nws, [11, 12, 13, 14, 15])
    pos = derive_positions(pd.DataFrame(rows))
    assert pos[11] == 1
    assert pos[12] == 2


def test_derive_positions_ignores_rows_with_missing_account_or_net_worth():
    rows = _pm_rows(1, 0, [30000, 25000, 20000, 15000, 10000], [11, 12, 13, 14, 15])
    rows.append({"match_id": 2, "account_id": None, "player_slot": 0, "net_worth": 9999})
    rows.append({"match_id": 2, "account_id": 99, "player_slot": 1, "net_worth": None})
    pos = derive_positions(pd.DataFrame(rows))
    assert 99 not in pos
    assert set(pos) == {11, 12, 13, 14, 15}


def test_coarsen_splits_core_1_to_3_from_support_4_to_5():
    """稳健口径：这个划分在 TI15 的 80 名人工策展选手上与净资产排名
    100% 吻合（15 处不一致全部落在 core 内部或 support 内部）。"""
    assert coarsen({1: 1, 2: 2, 3: 3, 4: 4, 5: 5}) == {
        1: "core", 2: "core", 3: "core", 4: "support", 5: "support"}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/test_l5_window.py -k "derive_positions or coarsen" -v
```

预期：全部 FAIL，`ImportError: cannot import name 'derive_positions'`

- [ ] **Step 3: 写实现**

追加到 `model/l5_window.py` 末尾（本函数只用 DataFrame 自身的方法，不需要新增 import）：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/test_l5_window.py -v
```

预期：11 passed

- [ ] **Step 5: 提交**

```bash
git add model/l5_window.py tests/test_l5_window.py
git commit -m "$(printf 'feat: 号位由队内净资产排名众数推出，附 core/support 稳健口径\n\nti_2021_2025_player_matches.csv 自带的 fantasy_role 有 2240 个 NaN 且\n取值混乱，不可用。净资产排名众数在 TI15 的 80 名人工策展选手上实测\n81.2%% 完全一致，15 处不一致全部落在 core 内部或 support 内部。\n回测只要求跨臂一致，不要求标签绝对正确。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

### Task 4: 同号位内 Spearman 评分 `score_arm`

**Files:**
- Modify: `model/l5_window.py`
- Test: `tests/test_l5_window.py`

**Interfaces:**
- Consumes: `model.l5_window` 已有内容
- Produces: `SKIP_TOO_FEW: str`、`SKIP_CONSTANT_PRED: str`、`SKIP_CONSTANT_ACTUAL: str`、`MIN_CANDIDATES: int`、`score_arm(rates: dict[int, float], actual: dict[int, float], positions: dict) -> tuple[dict, dict]`（返回 `(scores, skipped)`，两者的键都是号位组）

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_l5_window.py` 末尾：

```python
from model.l5_window import (score_arm, SKIP_TOO_FEW, SKIP_CONSTANT_PRED,
                             SKIP_CONSTANT_ACTUAL)


def test_score_arm_returns_perfect_correlation_when_ranking_matches():
    rates = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0, 4: 40.0}
    positions = {1: 1, 2: 1, 3: 1, 4: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores[1] == pytest.approx(1.0)
    assert skipped == {}


def test_score_arm_returns_minus_one_when_ranking_is_reversed():
    rates = {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0}
    actual = {1: 40.0, 2: 30.0, 3: 20.0, 4: 10.0}
    positions = {1: 1, 2: 1, 3: 1, 4: 1}
    scores, _ = score_arm(rates, actual, positions)
    assert scores[1] == pytest.approx(-1.0)


def test_score_arm_scores_each_position_group_separately():
    """同号位内排序是主判据——绝不能把 1 号位和 5 号位混在一起算，
    那样算出来的高相关只反映"核心补刀比辅助多"，跟选人决策无关。"""
    rates = {1: 1.0, 2: 2.0, 3: 3.0, 4: 30.0, 5: 20.0, 6: 10.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0, 4: 1.0, 5: 2.0, 6: 3.0}
    positions = {1: 1, 2: 1, 3: 1, 4: 5, 5: 5, 6: 5}
    scores, _ = score_arm(rates, actual, positions)
    assert scores[1] == pytest.approx(1.0)
    assert scores[5] == pytest.approx(-1.0)


def test_score_arm_skips_groups_with_fewer_than_three_candidates():
    """候选人不足 3 人的组算不出有意义的 Spearman，跳过——但必须带原因
    出现在 skipped 里，不许静默丢掉。"""
    rates = {1: 1.0, 2: 2.0}
    actual = {1: 10.0, 2: 20.0}
    positions = {1: 1, 2: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores == {}
    assert skipped == {1: SKIP_TOO_FEW}


def test_score_arm_skips_constant_prediction_instead_of_scoring_zero():
    """预测值全同时 Spearman 未定义（NaN）。必须计入跳过，不能当成 0——
    记成 0 会把"算不出来"混进"预测力为零"，直接污染配对检验。"""
    rates = {1: 5.0, 2: 5.0, 3: 5.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0}
    positions = {1: 1, 2: 1, 3: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores == {}
    assert skipped == {1: SKIP_CONSTANT_PRED}


def test_score_arm_skips_constant_actual():
    rates = {1: 1.0, 2: 2.0, 3: 3.0}
    actual = {1: 7.0, 2: 7.0, 3: 7.0}
    positions = {1: 1, 2: 1, 3: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores == {}
    assert skipped == {1: SKIP_CONSTANT_ACTUAL}


def test_score_arm_only_uses_players_present_in_both_rates_and_actual():
    rates = {1: 1.0, 2: 2.0, 3: 3.0, 99: 9.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0}
    positions = {1: 1, 2: 1, 3: 1, 99: 1}
    scores, skipped = score_arm(rates, actual, positions)
    assert scores[1] == pytest.approx(1.0)


def test_score_arm_works_with_string_position_labels_from_coarsen():
    rates = {1: 1.0, 2: 2.0, 3: 3.0}
    actual = {1: 10.0, 2: 20.0, 3: 30.0}
    positions = coarsen({1: 1, 2: 2, 3: 3})
    scores, _ = score_arm(rates, actual, positions)
    assert scores["core"] == pytest.approx(1.0)
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/test_l5_window.py -k score_arm -v
```

预期：全部 FAIL，`ImportError: cannot import name 'score_arm'`

- [ ] **Step 3: 写实现**

追加到 `model/l5_window.py` 末尾（并在文件顶部 import 区加 `import numpy as np` 与 `from scipy.stats import spearmanr`）：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/test_l5_window.py -v
```

预期：19 passed

- [ ] **Step 5: 提交**

```bash
git add model/l5_window.py tests/test_l5_window.py
git commit -m "$(printf 'feat: 同号位内 Spearman 评分，算不出来的组带原因跳过\n\n主判据是同号位内排序：绝不能跨号位混算，那样的高相关只反映\n"核心补刀比辅助多"，跟选人决策无关。候选人不足 3、预测值全同、\n实际值全同三种情况一律计入 skipped 带原因，不记成 0——\n把"算不出来"混进"预测力为零"会直接污染配对符号检验。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

### Task 5: 配对符号检验 `paired_sign_test` 与版本边界计数

**Files:**
- Modify: `model/l5_window.py`
- Test: `tests/test_l5_window.py`

**Interfaces:**
- Consumes: `model.l5_window` 已有内容、`model.patches.PATCH_RELEASE_UTC`
- Produces: `paired_sign_test(diffs: list[float]) -> dict`（键：`n_pos` / `n_neg` / `n_zero` / `median` / `p`）、`patch_boundaries_in(since_ts: int, until_ts: int) -> list[str]`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_l5_window.py` 末尾：

```python
from model.l5_window import paired_sign_test, patch_boundaries_in


def test_paired_sign_test_matches_the_exact_binomial_two_sided_p():
    """8 正 2 负的双侧精确二项 p = 2*(C(10,8)+C(10,9)+C(10,10))/2^10
    = 112/1024 = 0.109375。数值钉死，防止实现悄悄换成正态近似。"""
    out = paired_sign_test([1, 1, 1, 1, 1, 1, 1, 1, -1, -1])
    assert out["n_pos"] == 8
    assert out["n_neg"] == 2
    assert out["p"] == pytest.approx(0.109375)


def test_paired_sign_test_discards_zeros_but_reports_how_many():
    """零差值按符号检验惯例丢弃，但丢了几个必须报出来——静默丢弃会让
    读者以为样本量比实际大。"""
    out = paired_sign_test([1, 1, 1, 0, 0, -1])
    assert out["n_pos"] == 3
    assert out["n_neg"] == 1
    assert out["n_zero"] == 2


def test_paired_sign_test_on_empty_input_is_not_significant():
    out = paired_sign_test([])
    assert out["p"] == 1.0
    assert out["n_pos"] == 0 and out["n_neg"] == 0


def test_paired_sign_test_reports_median_of_all_differences():
    out = paired_sign_test([0.1, 0.2, 0.3])
    assert out["median"] == pytest.approx(0.2)


def test_patch_boundaries_in_counts_releases_strictly_inside_the_window():
    """滑动窗口的台阶检验要知道每段跨了几个版本边界。
    7.39 发布于 2025-05-22，落在 2025-05-01 ~ 2025-06-01 之间。"""
    since = _utc(2025, 5, 1)
    until = _utc(2025, 6, 1)
    assert patch_boundaries_in(since, until) == ["7.39"]


def test_patch_boundaries_in_is_empty_for_a_window_inside_one_patch():
    assert patch_boundaries_in(_utc(2025, 6, 1), _utc(2025, 7, 1)) == []


def test_patch_boundaries_in_excludes_a_release_exactly_at_the_window_start():
    """区间语义 (since, until)：起点当天发布的版本不算"跨界"——那一段
    本来就是这个版本的数据。"""
    assert "7.41" not in patch_boundaries_in(patch_ts("7.41"), _utc(2026, 4, 1))
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/test_l5_window.py -k "sign_test or boundaries" -v
```

预期：全部 FAIL，`ImportError: cannot import name 'paired_sign_test'`

- [ ] **Step 3: 写实现**

在 `model/l5_window.py` 顶部 import 区加 `from scipy.stats import binomtest` 与
`from model.patches import PATCH_RELEASE_UTC`，然后追加到文件末尾：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/test_l5_window.py -v
```

预期：26 passed

- [ ] **Step 5: 提交**

```bash
git add model/l5_window.py tests/test_l5_window.py
git commit -m "$(printf 'feat: 配对符号检验（双侧精确二项）与版本边界计数\n\n用符号检验而不是配对 t：Spearman 之差既不正态也不等方差，只看符号\n是这个样本量下最不需要额外假设的做法。零差值按惯例丢弃但计数报出。\npatch_boundaries_in 给滑动窗口的台阶检验标注每段跨了几个版本边界。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

### Task 6: holdout 参赛者、实际值与臂间交集

**Files:**
- Create: `model/l5_window_backtest.py`
- Test: `tests/test_l5_window_backtest.py`

**Interfaces:**
- Consumes: `model.l3_player._resolve_item_values`
- Produces: `HOLDOUTS: list[dict]`、`ITEMS: list[str]`、`MIN_HOLDOUT_GAMES: int`、`BASELINE_ARM: str`、`TREATMENT_ARM: str`、`ALPHA: float`、`MIN_HOLDOUTS_POSITIVE: int`、`holdout_participants(pm, year, min_games) -> set[int]`、`holdout_actuals(pm, year, item, min_games) -> dict[int, float]`、`intersect_players(rates_by_arm: dict[str, dict]) -> set[int]`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_l5_window_backtest.py`：

```python
"""对 model/l5_window_backtest.py 编排层的单元测试（全部走内联 fixture，
不读真实 CSV、不打网）。"""
import pandas as pd
import pytest

from model.l5_window_backtest import (HOLDOUTS, ITEMS, BASELINE_ARM, TREATMENT_ARM,
                                      ALPHA, MIN_HOLDOUTS_POSITIVE,
                                      holdout_participants, holdout_actuals,
                                      intersect_players)


def test_preregistered_decision_constants_are_what_the_spec_says():
    """判定规则是预注册的（spec §2）：跑完再改这几个常量就等于事后挑指标。
    这条测试的作用是让任何改动都必须显式地改到测试，而不是悄悄改掉。"""
    assert ALPHA == 0.05
    assert MIN_HOLDOUTS_POSITIVE == 3
    assert BASELINE_ARM == "L955d"
    assert TREATMENT_ARM == "patch"


def test_holdouts_are_the_four_preregistered_ti_events():
    assert [(h["year"], h["patch"]) for h in HOLDOUTS] == [
        ("2022", "7.32"), ("2023", "7.34"), ("2024", "7.37"), ("2025", "7.39")]


def test_items_are_the_twelve_csv_direct_scoring_items():
    """blob 三项 smokes/tormentor/courier 历史届取不到（pro_blob_stats.csv
    只覆盖 TI15 的 80 名选手、2024-01-01 起），必须排除。"""
    assert ITEMS == ["kills", "deaths", "creep_score", "gpm", "tower_kills",
                     "roshan", "teamfight", "wards", "camps_stacked", "runes",
                     "first_blood", "stuns"]
    assert "smokes" not in ITEMS and "tormentor" not in ITEMS and "courier" not in ITEMS


def _pm(rows):
    return pd.DataFrame(rows)


def test_holdout_participants_requires_min_games_in_that_event():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 5}] * 4
            + [{"match_date": "2025-09-05", "account_id": 2, "kills": 5}] * 2
            + [{"match_date": "2024-09-05", "account_id": 3, "kills": 5}] * 9)
    out = holdout_participants(_pm(rows), "2025", min_games=4)
    assert out == {1}


def test_holdout_actuals_averages_per_game_for_the_requested_year_only():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 10}] * 2
            + [{"match_date": "2025-09-06", "account_id": 1, "kills": 20}] * 2
            + [{"match_date": "2024-09-05", "account_id": 1, "kills": 999}] * 5)
    out = holdout_actuals(_pm(rows), "2025", "kills", min_games=4)
    assert out == {1: pytest.approx(15.0)}


def test_holdout_actuals_resolves_creep_score_as_last_hits_plus_denies():
    """预测侧和实际侧必须走同一套列合成（l3_player._resolve_item_values）。
    两边用不同的合成方式是这类回测最容易出、也最难发现的错。"""
    rows = [{"match_date": "2025-09-05", "account_id": 1,
             "last_hits": 300, "denies": 20}] * 4
    out = holdout_actuals(_pm(rows), "2025", "creep_score", min_games=4)
    assert out == {1: pytest.approx(320.0)}


def test_holdout_actuals_drops_players_below_min_games():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 5}] * 4
            + [{"match_date": "2025-09-05", "account_id": 2, "kills": 5}] * 3)
    out = holdout_actuals(_pm(rows), "2025", "kills", min_games=4)
    assert set(out) == {1}


def test_holdout_actuals_counts_only_non_null_rows_toward_min_games():
    """teamfight_participation / stuns 在真实数据里有 NaN。口径必须与
    fit_rate_model 一致：n 按非空计，NaN 行不算出场。"""
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "stuns": 3.0}] * 3
            + [{"match_date": "2025-09-05", "account_id": 1, "stuns": None}] * 5)
    out = holdout_actuals(_pm(rows), "2025", "stuns", min_games=4)
    assert out == {}


def test_intersect_players_keeps_only_players_predicted_by_every_arm():
    """臂之间人群不同就不是配对比较：短窗口会漏掉赛前歇了几个月的人，
    不取交集等于拿"全历史臂上的 18 人"跟"patch 臂上的 12 人"比。"""
    rates_by_arm = {"all": {1: 0.1, 2: 0.2, 3: 0.3},
                    "patch": {1: 0.1, 3: 0.3},
                    "L955d": {1: 0.1, 2: 0.2, 3: 0.3}}
    assert intersect_players(rates_by_arm) == {1, 3}


def test_intersect_players_on_empty_input_is_empty():
    assert intersect_players({}) == set()
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/test_l5_window_backtest.py -v
```

预期：全部 FAIL，`ModuleNotFoundError: No module named 'model.l5_window_backtest'`

- [ ] **Step 3: 写实现**

创建 `model/l5_window_backtest.py`：

```python
"""L5 窗口回测：选手数据窗口该不该切到当届版本发布日起。

spec：docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md

结构与本仓既有的 l4_* 一致：纯函数在 model/l5_window.py，本模块负责
读真实 CSV、跑四届 holdout、出报告。预测速率直接复用
model.l3_player.fit_rate_model，一行不改——每个臂只是喂不同的时间切片。

**本模块不修改任何产线默认值。** 结论出来之后是否改 l4_* 的 since_ts、
是否重新冻结存证，是另一次任务的事。
"""
import numpy as np
import pandas as pd

from model.l3_player import _resolve_item_values

# ---- 预注册的判定规则（spec §2）。跑完再改这几个常量就等于事后挑指标。----
ALPHA = 0.05
MIN_HOLDOUTS_POSITIVE = 3
BASELINE_ARM = "L955d"     # 现行产线策略：开赛前 955 天
TREATMENT_ARM = "patch"    # 当届版本发布日起

HOLDOUTS = [
    {"year": "2022", "patch": "7.32"},
    {"year": "2023", "patch": "7.34"},
    {"year": "2024", "patch": "7.37"},
    {"year": "2025", "patch": "7.39"},
]
# TI2021 排除：训练侧只有 2020-01 起半年多数据，all 与所有短臂差别过小，
# 没有对照价值（spec §4）。

# 12 个 CSV 直取计分项。blob 三项 smokes/tormentor/courier 需解 OpenDota
# JSON blob，data/pro_blob_stats.csv 只覆盖 TI15 的 80 名选手、2024-01-01 起，
# 历史届取不到，明确排除（报告须写明覆盖 12/15 项）。
ITEMS = ["kills", "deaths", "creep_score", "gpm", "tower_kills", "roshan",
         "teamfight", "wards", "camps_stacked", "runes", "first_blood", "stuns"]

MIN_HOLDOUT_GAMES = 4


def _year_rows(pm, year):
    return pm[pm["match_date"].astype(str).str[:4] == str(year)]


def holdout_participants(pm, year, min_games=MIN_HOLDOUT_GAMES):
    """该届出场 >= min_games 的选手集合（不分计分项）。"""
    sub = _year_rows(pm, year).dropna(subset=["account_id"])
    counts = sub.groupby(sub["account_id"].astype("int64")).size()
    return {int(a) for a, c in counts.items() if c >= min_games}


def holdout_actuals(pm, year, item, min_games=MIN_HOLDOUT_GAMES):
    """该届每名选手该项的每局均值 -> {account_id: mean}。

    item 走 l3_player._resolve_item_values 同一套解析（creep_score =
    last_hits + denies 等）——预测侧和实际侧用不同的列合成方式是这类
    回测最容易出、也最难发现的错。

    n 按该项的**非空**观测计：teamfight_participation / stuns 在真实数据
    里有 NaN，口径必须与 fit_rate_model 一致。
    """
    sub = _year_rows(pm, year).copy()
    sub["_value"] = _resolve_item_values(sub, item)
    sub = sub.dropna(subset=["_value", "account_id"])
    if sub.empty:
        return {}
    stats = sub.groupby(sub["account_id"].astype("int64"))["_value"].agg(["mean", "count"])
    return {int(a): float(r["mean"]) for a, r in stats.iterrows()
            if r["count"] >= min_games}


def intersect_players(rates_by_arm):
    """所有臂都给出了预测的选手交集。

    臂之间人群不同就不是配对比较：短窗口会漏掉赛前歇了几个月的人，
    不取交集等于拿"全历史臂上的 18 人"跟"patch 臂上的 12 人"比。
    """
    sets = [set(r) for r in rates_by_arm.values()]
    return set.intersection(*sets) if sets else set()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/test_l5_window_backtest.py -v
```

预期：11 passed

- [ ] **Step 5: 提交**

```bash
git add model/l5_window_backtest.py tests/test_l5_window_backtest.py
git commit -m "$(printf 'feat: holdout 参赛者/实际值/臂间交集，判定常量预注册\n\n实际值走 l3_player._resolve_item_values 同一套列合成，保证预测侧与\n实际侧口径一致（creep_score = last_hits + denies）。n 按非空观测计，\n与 fit_rate_model 对齐。臂间必须取选手交集，否则比的是不同人群。\nALPHA / MIN_HOLDOUTS_POSITIVE / BASELINE_ARM / TREATMENT_ARM 四个\n判定常量用测试钉死，改动必须显式改到测试。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

### Task 7: 单届回测编排 `run_holdout` 与判定 `decide`

**Files:**
- Modify: `model/l5_window_backtest.py`
- Test: `tests/test_l5_window_backtest.py`

**Interfaces:**
- Consumes: Task 6 的全部产出、`model.l5_window` 的 `window_arms` / `sliding_arms` / `derive_positions` / `score_arm` / `paired_sign_test`、`model.l3_player.fit_rate_model`
- Produces: `fit_arm(train, since, until, item, positions) -> dict[int, float]`、`run_holdout(train, pm, holdout, positions, arms, min_games=MIN_HOLDOUT_GAMES) -> dict`、`decide(units: list[dict]) -> dict`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_l5_window_backtest.py` 末尾：

```python
from model.l5_window_backtest import fit_arm, run_holdout, decide

# fit_rate_model / holdout_actuals 会解析全部 12 个计分项，所以 fixture 必须
# 把这些原始列都带上，缺一列就是 KeyError。
_STAT_COLS = ["kills", "deaths", "last_hits", "denies", "gold_per_min",
              "towers_killed", "roshans_killed", "teamfight_participation",
              "obs_placed", "camps_stacked", "rune_pickups",
              "firstblood_claimed", "stuns"]


def _stat_row(base, **over):
    """一行选手-比赛数据：12 个计分项全部填成 base 的倍数，便于造出可预期的排序。"""
    row = {c: float(base) for c in _STAT_COLS}
    row.update(over)
    return row


def _train_rows(account_id, start_times, kills):
    """训练侧的选手-比赛行。fit_rate_model 需要 account_id + 计分列；
    derive_positions 不在这里跑，所以 net_worth/player_slot 只是占位。"""
    return [dict(_stat_row(kills), match_id=1000 + i, account_id=account_id,
                 player_slot=0, net_worth=20000, start_time=t)
            for i, t in enumerate(start_times)]


def test_fit_arm_only_uses_rows_inside_the_half_open_window():
    """区间语义 [since, until)：开赛当天那一行必须被排除，否则是数据泄漏。

    三名选手窗口内的 kills 分别是 1 / 5 / 9，窗口外那一行是 99。
    正确排除时 3 号位选手的收缩后速率约 8.5；如果 99 那行漏进来，
    他的速率会跳到 38 上下——所以阈值取 10，能真正把泄漏抓出来
    （写成 50 就抓不到了）。"""
    rows = (_train_rows(1, [100, 200, 300], 1)
            + _train_rows(2, [100, 200, 300], 5)
            + _train_rows(3, [100, 200, 300], 9))
    # 把每人第三行（start_time=300，等于 until）改成异常值
    train = pd.DataFrame(rows)
    train.loc[train["start_time"] == 300, "kills"] = 99.0
    positions = {1: 1, 2: 1, 3: 1}
    rates = fit_arm(train, since=0, until=300, item="kills", positions=positions)
    assert rates[1] < rates[2] < rates[3]
    assert rates[3] < 10


def test_fit_arm_returns_empty_when_the_window_has_no_rows():
    train = pd.DataFrame(_train_rows(1, [100], 5))
    assert fit_arm(train, since=1000, until=2000, item="kills",
                   positions={1: 1}) == {}


def test_run_holdout_uses_the_positions_it_was_given_for_every_arm():
    """号位必须跨臂固定（spec §4）：每臂各推一次会让各臂连分组都不同，
    那就不是配对比较了。这里传入一组正常推导绝不会产生的标签 "X"，
    断言输出单元的 position 正是 "X" —— 若实现内部偷偷重推号位，
    会得到 1..5，测试立刻变红。"""
    train_rows = []
    for a, base in [(1, 1.0), (2, 5.0), (3, 9.0)]:
        train_rows += _train_rows(a, list(range(100, 130)), base)
    train = pd.DataFrame(train_rows)
    pm_rows = []
    for a, base in [(1, 2.0), (2, 6.0), (3, 10.0)]:
        for _ in range(4):
            pm_rows.append(dict(_stat_row(base), match_date="2025-09-05",
                                account_id=a))
    pm = pd.DataFrame(pm_rows)

    positions = {1: "X", 2: "X", 3: "X"}
    arms = {"L955d": (0, 200), "patch": (110, 200)}
    res = run_holdout(train, pm, {"year": "2025", "patch": "7.39"}, positions, arms)

    assert res["units"], "至少要产出一个单元"
    assert {u["position"] for u in res["units"]} == {"X"}


def test_run_holdout_records_intersection_coverage_for_every_item():
    """交集丢掉多少人必须逐项记账——静默截断是这个项目最容易被抓的地方。"""
    train_rows = []
    for a, base in [(1, 1.0), (2, 5.0), (3, 9.0)]:
        train_rows += _train_rows(a, list(range(100, 130)), base)
    # 4 号选手只在早期有数据，短窗口臂里会消失 -> 交集必然收缩
    train_rows += _train_rows(4, list(range(100, 108)), 3.0)
    train = pd.DataFrame(train_rows)
    pm_rows = []
    for a, base in [(1, 2.0), (2, 6.0), (3, 10.0), (4, 4.0)]:
        for _ in range(4):
            pm_rows.append(dict(_stat_row(base), match_date="2025-09-05",
                                account_id=a))
    pm = pd.DataFrame(pm_rows)

    positions = {1: 1, 2: 1, 3: 1, 4: 1}
    arms = {"L955d": (0, 200), "patch": (110, 200)}
    res = run_holdout(train, pm, {"year": "2025", "patch": "7.39"}, positions, arms)

    assert len(res["coverage"]) == len(ITEMS)
    kills_cov = next(c for c in res["coverage"] if c["item"] == "kills")
    assert kills_cov["n_union"] == 4
    assert kills_cov["n_intersection"] == 3
    assert kills_cov["n_dropped_by_intersection"] == 1


def _units(holdout, n_pos, n_neg):
    """造一届的配对单元：n_pos 个 +0.3、n_neg 个 -0.1。"""
    return ([{"holdout": holdout, "item": "kills", "position": i, "diff": 0.3}
             for i in range(n_pos)]
            + [{"holdout": holdout, "item": "deaths", "position": i, "diff": -0.1}
               for i in range(n_neg)])


def test_decide_refuses_to_support_when_only_two_holdouts_agree():
    """预注册的两条判定必须同时满足（spec §2）。这组输入的符号检验
    p = 0.0293（< 0.05）、中位差 +0.3 > 0——第 1 条过了——但只有 2 届
    届内中位差为正，所以结论仍然是"不支持"。这正是加第 2 条的目的：
    挡住"某一两届的特殊情况撑起了全局显著"。"""
    units = _units("2022", 11, 1) + _units("2023", 11, 1) \
        + _units("2024", 5, 7) + _units("2025", 5, 7)
    out = decide(units)
    assert out["sign_test"]["n_pos"] == 32 and out["sign_test"]["n_neg"] == 16
    assert out["sign_test"]["p"] == pytest.approx(0.0293049, abs=1e-6)
    assert out["sign_test"]["median"] > 0
    assert out["n_holdouts_positive"] == 2
    assert out["supported"] is False


def test_decide_supports_when_significant_and_three_of_four_holdouts_positive():
    units = (_units("2022", 12, 0) + _units("2023", 12, 0)
             + _units("2024", 12, 0) + _units("2025", 0, 12))
    out = decide(units)
    assert out["sign_test"]["p"] < ALPHA
    assert out["n_holdouts_positive"] == 3
    assert out["supported"] is True


def test_decide_reports_median_diff_per_holdout():
    units = [{"holdout": "2022", "item": "kills", "position": 1, "diff": 0.1},
             {"holdout": "2022", "item": "kills", "position": 2, "diff": 0.3},
             {"holdout": "2023", "item": "kills", "position": 1, "diff": -0.2}]
    out = decide(units)
    assert out["median_diff_by_holdout"]["2022"] == pytest.approx(0.2)
    assert out["median_diff_by_holdout"]["2023"] == pytest.approx(-0.2)


def test_decide_ignores_units_whose_diff_is_none():
    """某臂在该单元被跳过时 diff 是 None，不能当成 0 参与检验。"""
    units = [{"holdout": "2022", "item": "kills", "position": 1, "diff": 0.1},
             {"holdout": "2022", "item": "roshan", "position": 5, "diff": None}]
    out = decide(units)
    assert out["n_units_compared"] == 1


def test_decide_on_empty_units_is_not_supported():
    out = decide([])
    assert out["supported"] is False
```

注：`test_decide_refuses_to_support_when_only_two_holdouts_agree` 里的
`p = 0.0293049` 是 `scipy.stats.binomtest(32, 48, 0.5).pvalue` 的精确值，
已实测核对；`_units("2024", 5, 7)` 的届内中位差是 −0.1（7 负 5 正，中位落在负值上）。

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/test_l5_window_backtest.py -k "fit_arm or run_holdout or decide" -v
```

预期：全部 FAIL，`ImportError: cannot import name 'fit_arm'`

- [ ] **Step 3: 写实现**

在 `model/l5_window_backtest.py` 顶部 import 区加：

```python
from model.l3_player import fit_rate_model
from model.l5_window import (window_arms, sliding_arms, derive_positions, coarsen,
                             score_arm, paired_sign_test, patch_boundaries_in)
```

追加到文件末尾：

```python
def fit_arm(train, since, until, item, positions):
    """在时间切片 [since, until) 上跑 fit_rate_model -> {account_id: rate}。

    区间是左闭右开：until 等于开赛时间，开赛当天那一行必须排除，
    否则是数据泄漏。
    """
    ts = train["start_time"].astype("int64")
    sub = train[(ts >= int(since)) & (ts < int(until))]
    if sub.empty:
        return {}
    fitted = fit_rate_model(sub, item, positions)
    return {int(a): float(v["rate"]) for a, v in fitted.items()}


def run_holdout(train, pm, holdout, positions, arms, min_games=MIN_HOLDOUT_GAMES):
    """跑一届 holdout 的全部臂 × 全部计分项。

    positions 与 min_games 都由调用方传入，不在内部推导——Task 9 的稳健性
    检查要用同一个函数换口径重跑（换 core/support 分组、换入选门槛）。

    返回 {"units": [...], "coverage": [...], "skipped": [...]}：
      units    —— 每个 (item, position) 单元下各臂的 Spearman
      coverage —— 每个 item 的臂间交集前后人数（不许悄悄丢数据）
      skipped  —— 每个被跳过的单元及原因
    """
    year = holdout["year"]
    units, coverage, skipped = [], [], []
    for item in ITEMS:
        actual = holdout_actuals(pm, year, item, min_games)
        rates_by_arm = {arm: fit_arm(train, since, until, item, positions)
                        for arm, (since, until) in arms.items()}
        union = set().union(*[set(r) for r in rates_by_arm.values()]) if rates_by_arm else set()
        keep = intersect_players(rates_by_arm) & set(actual)
        coverage.append({"holdout": year, "item": item,
                         "n_union": len(union), "n_intersection": len(keep),
                         "n_dropped_by_intersection": len(union) - len(keep)})
        scores_by_arm = {}
        for arm, rates in rates_by_arm.items():
            kept = {a: v for a, v in rates.items() if a in keep}
            scores, skips = score_arm(kept, actual, positions)
            scores_by_arm[arm] = scores
            for pos, reason in skips.items():
                skipped.append({"holdout": year, "item": item, "arm": arm,
                                "position": pos, "reason": reason})
        all_pos = sorted({p for s in scores_by_arm.values() for p in s}, key=str)
        for pos in all_pos:
            row = {"holdout": year, "item": item, "position": pos,
                   "spearman": {arm: s.get(pos) for arm, s in scores_by_arm.items()}}
            t, b = row["spearman"].get(TREATMENT_ARM), row["spearman"].get(BASELINE_ARM)
            row["diff"] = None if (t is None or b is None) else float(t - b)
            units.append(row)
    return {"units": units, "coverage": coverage, "skipped": skipped}


def decide(units):
    """预注册的两条判定（spec §2），两条都满足才算"支持切窗口"。

    第 1 条（配对符号检验）单独用不行：同一届的 12 个计分项用的是同一批
    选手，单元之间不独立，符号检验会高估显著性。第 2 条（四届中至少 3 届
    同向）是按届聚类的一致性检查，挡住"某一届的特殊情况撑起了全局显著"。
    第 2 条单独用也不行：四届最多给到 p = 0.0625，永远够不到 0.05。
    """
    diffs = [u["diff"] for u in units if u.get("diff") is not None]
    test = paired_sign_test(diffs)
    by_holdout = {}
    for h in sorted({u["holdout"] for u in units}):
        d = [u["diff"] for u in units if u["holdout"] == h and u.get("diff") is not None]
        if d:
            by_holdout[h] = float(np.median(d))
    n_pos = sum(1 for v in by_holdout.values() if v > 0)
    supported = bool(test["p"] < ALPHA and test["median"] > 0
                     and n_pos >= MIN_HOLDOUTS_POSITIVE)
    return {"sign_test": test, "median_diff_by_holdout": by_holdout,
            "n_holdouts_positive": n_pos, "n_units_compared": len(diffs),
            "supported": supported}
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/test_l5_window_backtest.py -v
```

预期：20 passed

- [ ] **Step 5: 提交**

```bash
git add model/l5_window_backtest.py tests/test_l5_window_backtest.py
git commit -m "$(printf 'feat: 单届回测编排与预注册的两条判定规则\n\n窗口区间左闭右开，开赛当天那一行必须排除，否则是数据泄漏。\n判定要求符号检验显著 + 四届中至少三届同向：单元之间不独立\n（同一届 12 个计分项用同一批选手），只用符号检验会高估显著性；\n只用四届一致性又永远够不到 0.05，两条合起来才是这个样本量下\n能给出的最诚实判据。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

### Task 8: 滑动窗口台阶检验、报告产出与 CLI

**Files:**
- Modify: `model/l5_window_backtest.py`
- Test: `tests/test_l5_window_backtest.py`

**Interfaces:**
- Consumes: Task 6 / Task 7 的全部产出
- Produces: `run_sliding(train, pm, holdout, positions, event_start_ts) -> list[dict]`、`build_report(csv_path, ti_pm_path) -> dict`、`render_markdown(report) -> str`、`main()` CLI（`--csv` / `--ti-pm` / `--out`）、`TRAIN_COLUMNS: list[str]`、`DEFAULT_CSV` / `DEFAULT_TI_PM` / `DEFAULT_OUT`

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_l5_window_backtest.py` 末尾：

```python
from model.l5_window_backtest import render_markdown


def _minimal_report(supported=False):
    return {
        "generated_by": "model/l5_window_backtest.py",
        "spec": "docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md",
        "baseline_arm": "L955d", "treatment_arm": "patch",
        "alpha": 0.05, "min_holdouts_positive": 3,
        "items_covered": "12/15",
        "excluded_items": ["smokes", "tormentor", "courier"],
        "holdouts": ["2022", "2023", "2024", "2025"],
        "holdout_meta": [{"holdout": y, "patch": p} for y, p in
                         [("2022", "7.32"), ("2023", "7.34"),
                          ("2024", "7.37"), ("2025", "7.39")]],
        "decision": {"sign_test": {"n_pos": 100, "n_neg": 110, "n_zero": 0,
                                   "median": -0.01, "p": 0.55},
                     "median_diff_by_holdout": {"2022": -0.02, "2023": 0.01,
                                                "2024": -0.03, "2025": 0.00},
                     "n_holdouts_positive": 1, "n_units_compared": 210,
                     "supported": supported},
        "coverage": [{"holdout": "2022", "item": "kills", "n_union": 20,
                      "n_intersection": 14, "n_dropped_by_intersection": 6}],
        "skipped": [{"holdout": "2022", "item": "roshan", "arm": "patch",
                     "position": 5, "reason": "预测值全同"}],
        "sliding": [{"holdout": "2025", "arm": "slide0", "mean_spearman": 0.21,
                     "patch_boundaries": []}],
    }


def test_render_markdown_states_the_conclusion_without_overclaiming():
    """判不出显著时，报告必须说"没有证据支持"，不能说成"证明了两者一样"
    ——那是本次样本量给不出的结论（spec §8）。"""
    md = render_markdown(_minimal_report(supported=False))
    assert "没有证据支持" in md
    assert "证明两者一样" not in md


def test_render_markdown_always_reports_dropped_and_skipped_counts():
    """静默截断是这个项目最容易再被读者抓的地方——交集丢掉的人数和
    跳过的单元数必须出现在报告正文里。"""
    md = render_markdown(_minimal_report())
    assert "6" in md          # n_dropped_by_intersection
    assert "跳过" in md
    assert "预测值全同" in md


def test_render_markdown_states_item_coverage_is_12_of_15():
    md = render_markdown(_minimal_report())
    assert "12/15" in md
    assert "smokes" in md
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/test_l5_window_backtest.py -k render_markdown -v
```

预期：全部 FAIL，`ImportError: cannot import name 'render_markdown'`

- [ ] **Step 3: 写实现**

在 `model/l5_window_backtest.py` 顶部 import 区加 `import argparse`、`import json`、`import os`，并加常量：

```python
DEFAULT_CSV = os.path.join("data", "pro_player_matches_2020_2026.csv")
DEFAULT_TI_PM = os.path.join("data", "ti_2021_2025_player_matches.csv")
DEFAULT_OUT = os.path.join("reports", "p5_window_backtest")

# 训练侧只读这些列：全表 32 列 × 约 146 万行读进来没必要，而且号位推导
# 需要每场十个人都在（不能预先按选手过滤），所以列上省一点是值得的。
TRAIN_COLUMNS = ["match_id", "account_id", "player_slot", "start_time", "net_worth",
                 "kills", "deaths", "last_hits", "denies", "gold_per_min",
                 "towers_killed", "roshans_killed", "teamfight_participation",
                 "obs_placed", "camps_stacked", "rune_pickups",
                 "firstblood_claimed", "stuns"]
```

追加到文件末尾：

```python
def run_sliding(train, pm, holdout, positions, event_start_ts):
    """等长滑动窗口的台阶检验（spec §3）。

    每段长度相同，只有起点离开赛日的距离不同——长度一变，Spearman 的
    差异就分不清是"窗口更短"还是"离开赛更远"造成的。每段标注跨了哪些
    版本边界：曲线平滑下降 = 单纯的近期性；边界处掉档 = 版本效应。
    """
    out = []
    for arm, (since, until) in sliding_arms(event_start_ts).items():
        rhos = []
        for item in ITEMS:
            actual = holdout_actuals(pm, holdout["year"], item)
            rates = fit_arm(train, since, until, item, positions)
            kept = {a: v for a, v in rates.items() if a in actual}
            scores, _ = score_arm(kept, actual, positions)
            rhos += list(scores.values())
        out.append({"holdout": holdout["year"], "arm": arm,
                    "since_ts": since, "until_ts": until,
                    "n_scored_units": len(rhos),
                    "mean_spearman": float(np.mean(rhos)) if rhos else None,
                    "patch_boundaries": patch_boundaries_in(since, until)})
    return out


def build_report(csv_path=DEFAULT_CSV, ti_pm_path=DEFAULT_TI_PM):
    """跑完四届 × 12 项 × 7 臂，外加滑动窗口，返回完整报告 dict。"""
    train_all = pd.read_csv(csv_path, usecols=lambda c: c in set(TRAIN_COLUMNS),
                            low_memory=False)
    pm = pd.read_csv(ti_pm_path, low_memory=False)

    units, coverage, skipped, sliding = [], [], [], []
    per_holdout_meta = []
    for h in HOLDOUTS:
        year = h["year"]
        event_start = int(_year_rows(pm, year)["start_time"].astype("int64").min())
        participants = holdout_participants(pm, year)
        pre = train_all[train_all["start_time"].astype("int64") < event_start]
        # 号位在**全部赛前历史**上算一次，跨臂固定——每臂各算会让各臂
        # 连分组都不同，那就不是配对比较了（spec §4）。
        positions_all = derive_positions(pre)
        positions = {a: p for a, p in positions_all.items() if a in participants}
        train = pre[pre["account_id"].isin(set(positions))].reset_index(drop=True)

        arms = window_arms(event_start, h["patch"])
        res = run_holdout(train, pm, h, positions, arms)
        units += res["units"]
        coverage += res["coverage"]
        skipped += res["skipped"]
        sliding += run_sliding(train, pm, h, positions, event_start)
        per_holdout_meta.append({
            "holdout": year, "patch": h["patch"], "event_start_ts": event_start,
            "n_participants": len(participants),
            "n_with_position": len(positions),
            "n_participants_without_pre_event_history": len(participants) - len(positions),
            "arms": {a: {"since_ts": s, "until_ts": u} for a, (s, u) in arms.items()},
        })

    return {
        "generated_by": "model/l5_window_backtest.py",
        "spec": "docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md",
        "baseline_arm": BASELINE_ARM, "treatment_arm": TREATMENT_ARM,
        "alpha": ALPHA, "min_holdouts_positive": MIN_HOLDOUTS_POSITIVE,
        "items_covered": "%d/15" % len(ITEMS),
        "excluded_items": ["smokes", "tormentor", "courier"],
        "holdouts": [h["year"] for h in HOLDOUTS],
        "holdout_meta": per_holdout_meta,
        "decision": decide(units),
        "units": units, "coverage": coverage, "skipped": skipped, "sliding": sliding,
    }


def render_markdown(report):
    """人读版报告。

    措辞纪律（spec §8）：判不出显著时只能写"没有证据支持"，不能写成
    "证明了两者一样"——后者是本次样本量给不出的结论。
    """
    d = report["decision"]
    t = d["sign_test"]
    L = []
    L.append("# 选手数据窗口是否该切到当前版本 · 回测报告\n")
    L.append("产出：`%s` ｜ 设计：`%s`\n" % (report["generated_by"], report["spec"]))
    L.append("## 结论\n")
    if d["supported"]:
        L.append("**支持把窗口切到当届版本发布日起。**"
                 "配对符号检验 p=%.4f（<%.2f），中位差 %+.4f，"
                 "四届中 %d 届届内中位差为正（>=%d）。两条预注册判定均满足。\n"
                 % (t["p"], report["alpha"], t["median"],
                    d["n_holdouts_positive"], report["min_holdouts_positive"]))
    else:
        L.append("**没有证据支持把窗口切到当届版本发布日起。**"
                 "配对符号检验 p=%.4f，中位差 %+.4f，"
                 "四届中 %d 届届内中位差为正（需要 >=%d）。\n"
                 % (t["p"], t["median"], d["n_holdouts_positive"],
                    report["min_holdouts_positive"]))
        L.append("> 「没有证据支持」不等于「证明两者一样」。"
                 "单届单号位的候选人只有十几人，Spearman 的标准误约 0.25，"
                 "本次样本量下的检验力本来就有限，给不出等价性结论。\n")
    L.append("对照：treatment = `%s`，baseline = `%s`（现行产线策略）。"
             "参与配对的单元 %d 个（正 %d / 负 %d / 零 %d）。\n"
             % (report["treatment_arm"], report["baseline_arm"],
                d["n_units_compared"], t["n_pos"], t["n_neg"], t["n_zero"]))
    L.append("## 各届届内中位差\n")
    L.append("| 届 | 版本 | 中位差（patch − baseline） |")
    L.append("|---|---|---|")
    patch_of = {m["holdout"]: m["patch"] for m in report["holdout_meta"]}
    for h, v in d["median_diff_by_holdout"].items():
        L.append("| TI%s | %s | %+.4f |" % (h, patch_of.get(h, "?"), v))
    L.append("\n## 覆盖与丢弃\n")
    L.append("计分项覆盖 **%s**，排除 %s（需解 OpenDota JSON blob，"
             "`data/pro_blob_stats.csv` 只覆盖 TI15 的 80 名选手、2024-01-01 起，"
             "历史届取不到）。\n"
             % (report["items_covered"], "/".join(report["excluded_items"])))
    dropped = sum(c["n_dropped_by_intersection"] for c in report["coverage"])
    L.append("臂间取交集共丢弃 **%d** 人次（短窗口下没有数据的选手；"
             "不取交集就不是配对比较）。\n" % dropped)
    L.append("跳过的单元 **%d** 个，按原因：" % len(report["skipped"]))
    reasons = {}
    for s in report["skipped"]:
        reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
    for r, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        L.append("- %s：%d" % (r, n))
    L.append("\n## 滑动窗口台阶检验\n")
    L.append("等长 105 天、起点逐段往前滑。曲线平滑下降 = 单纯的近期性；"
             "版本边界处掉档 = 版本效应。\n")
    L.append("| 届 | 段 | 平均 Spearman | 段内跨越的版本 |")
    L.append("|---|---|---|---|")
    for s in report["sliding"]:
        ms = "—" if s["mean_spearman"] is None else "%.4f" % s["mean_spearman"]
        L.append("| TI%s | %s | %s | %s |"
                 % (s["holdout"], s["arm"], ms,
                    "、".join(s["patch_boundaries"]) or "无"))
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description="选手数据窗口版本切换回测（不改产线）")
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--ti-pm", default=DEFAULT_TI_PM)
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="输出前缀，会写 <out>.json 与 <out>.md")
    args = ap.parse_args()
    report = build_report(csv_path=args.csv, ti_pm_path=args.ti_pm)
    with open(args.out + ".json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(args.out + ".md", "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    print("写出 %s.json 与 %s.md" % (args.out, args.out))
    print("结论：%s" % ("支持切窗口" if report["decision"]["supported"]
                        else "没有证据支持切窗口"))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/test_l5_window_backtest.py -v && python3 -m pytest -q
```

预期：`test_l5_window_backtest.py` 23 passed；全仓 `python3 -m pytest -q` 全绿（既有 181 个测试一个都不许变红——本计划不修改任何现有模块）。

- [ ] **Step 5: 提交**

```bash
git add model/l5_window_backtest.py tests/test_l5_window_backtest.py
git commit -m "$(printf 'feat: 滑动窗口台阶检验、报告渲染与 CLI\n\n报告措辞有纪律：判不出显著时只能写"没有证据支持"，不能写成\n"证明了两者一样"——后者是本次样本量给不出的结论，用测试钉死。\n交集丢弃人次、跳过单元数与原因一律进正文，不许静默截断。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

### Task 9: 稳健性变体（core/support 分组、入选门槛 3 与 8）

spec §4 要求"附带跑一遍 core(1-3)/support(4-5) 两组"，并对入选门槛做
"敏感性另跑 3 和 8"。这三个变体不参与主判定，作用是暴露"结论是不是靠
某一个口径撑起来的"。为控制成本，变体只跑 treatment 与 baseline 两个臂。

**Files:**
- Modify: `model/l5_window_backtest.py`
- Test: `tests/test_l5_window_backtest.py`

**Interfaces:**
- Consumes: Task 7 的 `run_holdout` / `decide`、`model.l5_window.coarsen`
- Produces: `ROBUSTNESS_MIN_GAMES: tuple[int, ...]`、`run_robustness(train, pm, holdout, positions, arms) -> list[dict]`、`aggregate_robustness(all_variant_runs: list[dict]) -> dict[str, dict]`；`build_report` 的返回值新增 `"robustness"` 键

- [ ] **Step 1: 写失败的测试**

追加到 `tests/test_l5_window_backtest.py` 末尾：

```python
from model.l5_window_backtest import (ROBUSTNESS_MIN_GAMES, run_robustness,
                                      aggregate_robustness)


def test_robustness_min_games_are_the_preregistered_three_and_eight():
    assert ROBUSTNESS_MIN_GAMES == (3, 8)


def _tiny_holdout_frames():
    """三名选手、训练侧各 30 局、TI 侧各 8 局，12 个计分项列齐。"""
    train_rows = []
    for a, base in [(1, 1.0), (2, 5.0), (3, 9.0)]:
        train_rows += _train_rows(a, list(range(100, 130)), base)
    pm_rows = []
    for a, base in [(1, 2.0), (2, 6.0), (3, 10.0)]:
        for _ in range(8):
            pm_rows.append(dict(_stat_row(base), match_date="2025-09-05",
                                account_id=a))
    return pd.DataFrame(train_rows), pd.DataFrame(pm_rows)


def test_run_robustness_produces_exactly_three_variants():
    train, pm = _tiny_holdout_frames()
    arms = {"L955d": (0, 200), "patch": (110, 200), "all": (0, 200)}
    out = run_robustness(train, pm, {"year": "2025", "patch": "7.39"},
                         {1: 1, 2: 1, 3: 1}, arms)
    assert [r["variant"] for r in out] == ["coarse_position", "min_games=3",
                                           "min_games=8"]


def test_run_robustness_only_uses_the_treatment_and_baseline_arms():
    """变体只为交叉验证主结论，不需要另外五个臂——跑全套是三倍的成本
    换不来信息。"""
    train, pm = _tiny_holdout_frames()
    arms = {"L955d": (0, 200), "patch": (110, 200), "all": (0, 200)}
    out = run_robustness(train, pm, {"year": "2025", "patch": "7.39"},
                         {1: 1, 2: 1, 3: 1}, arms)
    arms_seen = {a for r in out for u in r["units"] for a in u["spearman"]}
    assert arms_seen == {BASELINE_ARM, TREATMENT_ARM}


def test_run_robustness_coarse_variant_groups_by_core_and_support():
    train, pm = _tiny_holdout_frames()
    arms = {"L955d": (0, 200), "patch": (110, 200)}
    out = run_robustness(train, pm, {"year": "2025", "patch": "7.39"},
                         {1: 1, 2: 2, 3: 3}, arms)
    coarse = next(r for r in out if r["variant"] == "coarse_position")
    assert {u["position"] for u in coarse["units"]} == {"core"}


def test_aggregate_robustness_merges_units_by_variant_and_decides_each():
    runs = [
        {"variant": "coarse_position",
         "units": [{"holdout": "2022", "item": "kills", "position": "core",
                    "diff": 0.4}]},
        {"variant": "coarse_position",
         "units": [{"holdout": "2023", "item": "kills", "position": "core",
                    "diff": 0.2}]},
        {"variant": "min_games=3",
         "units": [{"holdout": "2022", "item": "kills", "position": 1,
                    "diff": -0.1}]},
    ]
    out = aggregate_robustness(runs)
    assert set(out) == {"coarse_position", "min_games=3"}
    assert out["coarse_position"]["n_units_compared"] == 2
    assert out["min_games=3"]["sign_test"]["n_neg"] == 1


def test_render_markdown_includes_a_robustness_section_when_present():
    report = _minimal_report()
    report["robustness"] = {
        "coarse_position": {"sign_test": {"p": 0.42, "median": -0.01,
                                          "n_pos": 30, "n_neg": 34, "n_zero": 0},
                            "median_diff_by_holdout": {}, "n_holdouts_positive": 1,
                            "n_units_compared": 64, "supported": False}}
    md = render_markdown(report)
    assert "稳健性" in md
    assert "coarse_position" in md
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python3 -m pytest tests/test_l5_window_backtest.py -k "robustness" -v
```

预期：全部 FAIL，`ImportError: cannot import name 'ROBUSTNESS_MIN_GAMES'`

- [ ] **Step 3: 写实现**

在 `model/l5_window_backtest.py` 的常量区加：

```python
# 稳健性变体的入选门槛（spec §4「敏感性另跑 3 和 8」）。主判据仍用
# MIN_HOLDOUT_GAMES = 4，这两个只用来交叉验证结论对门槛是否敏感。
ROBUSTNESS_MIN_GAMES = (3, 8)
```

追加到文件末尾：

```python
def run_robustness(train, pm, holdout, positions, arms):
    """稳健性变体（spec §4），只跑 treatment 与 baseline 两个臂。

      coarse_position —— 号位换成 core(1-3)/support(4-5)。这个划分在 TI15 的
                         80 名人工策展选手上与净资产排名 100% 吻合，是最不
                         依赖号位推导准确性的口径。
      min_games=3     —— 门槛放宽，多收小组赛就出局的队。
      min_games=8     —— 门槛收紧，只留打得深的队。

    三个变体都不参与主判定，作用是暴露"结论是不是靠某一个口径撑起来的"。
    只跑两个臂：另外五个臂对交叉验证没有增量信息，跑全套是三倍成本。
    """
    pair = {a: w for a, w in arms.items() if a in (BASELINE_ARM, TREATMENT_ARM)}
    out = [{"variant": "coarse_position",
            "units": run_holdout(train, pm, holdout, coarsen(positions), pair)["units"]}]
    for mg in ROBUSTNESS_MIN_GAMES:
        out.append({"variant": "min_games=%d" % mg,
                    "units": run_holdout(train, pm, holdout, positions, pair,
                                         min_games=mg)["units"]})
    return out


def aggregate_robustness(all_variant_runs):
    """把各届的变体结果按变体名合并，各自跑一遍 decide。"""
    by_variant = {}
    for run in all_variant_runs:
        by_variant.setdefault(run["variant"], []).extend(run["units"])
    return {v: decide(u) for v, u in by_variant.items()}
```

在 `build_report` 里接上（`sliding += ...` 那行之后加一行，返回值里加一个键）：

```python
        robustness_runs += run_robustness(train, pm, h, positions, arms)
```

`build_report` 开头的累加器改成：

```python
    units, coverage, skipped, sliding, robustness_runs = [], [], [], [], []
```

返回值 dict 里加：

```python
        "robustness": aggregate_robustness(robustness_runs),
```

在 `render_markdown` 的滑动窗口表之后追加（用 `.get`，这样没有该键的旧报告也能渲染）：

```python
    rb = report.get("robustness") or {}
    if rb:
        L.append("\n## 稳健性变体\n")
        L.append("不参与主判定，只用来看结论是不是靠某一个口径撑起来的。"
                 "变体只跑 treatment 与 baseline 两个臂。\n")
        L.append("| 变体 | 配对单元 | 正/负 | 中位差 | p | 结论同向？ |")
        L.append("|---|---|---|---|---|---|")
        for name, dv in rb.items():
            tv = dv["sign_test"]
            L.append("| %s | %d | %d/%d | %+.4f | %.4f | %s |"
                     % (name, dv["n_units_compared"], tv["n_pos"], tv["n_neg"],
                        tv["median"], tv["p"],
                        "是" if dv["supported"] == d["supported"] else "否"))
```

- [ ] **Step 4: 跑测试确认通过**

```bash
python3 -m pytest tests/test_l5_window_backtest.py -v && python3 -m pytest -q
```

预期：`test_l5_window_backtest.py` 29 passed；全仓全绿。

- [ ] **Step 5: 提交**

```bash
git add model/l5_window_backtest.py tests/test_l5_window_backtest.py
git commit -m "$(printf 'feat: 稳健性变体——core/support 分组与入选门槛 3/8\n\nspec 要求的三个交叉验证口径。都不参与主判定，作用是暴露"结论是不是\n靠某一个口径撑起来的"。变体只跑 treatment 与 baseline 两个臂：另外\n五个臂对交叉验证没有增量信息，跑全套是三倍成本换不来信息。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

### Task 10: 真实数据跑一遍并落盘结果

**Files:**
- Create: `reports/p5_window_backtest.json`
- Create: `reports/p5_window_backtest.md`

**Interfaces:**
- Consumes: Task 8 / Task 9 的 CLI 与报告结构
- Produces: 两份报告产出物

- [ ] **Step 1: 确认数据文件在位**

```bash
ls -la data/pro_player_matches_2020_2026.csv data/ti_2021_2025_player_matches.csv
```

预期：两个文件都存在（约 191MB 与 2.3MB）。若 `data/` 为空，先按 README 跑 `python3 fetch_pro_all.py` 重取——`data/` 已 gitignore，不入库。

- [ ] **Step 2: 跑回测**

```bash
python3 -m model.l5_window_backtest
```

预期：终端打印 `写出 reports/p5_window_backtest.json 与 reports/p5_window_backtest.md`，以及一行结论。运行时间数分钟量级：主回测 4 届 × 12 项 × 7 臂 = 336 次 `fit_rate_model`，滑动窗口 4 × 12 × 4 = 192 次，稳健性 4 × 12 × 2 臂 × 3 变体 = 288 次，合计约 816 次，每次都在已按参赛者过滤的数万行上跑。

- [ ] **Step 3: 人工核对四项一致性**

```bash
python3 - <<'PY'
import json
r = json.load(open("reports/p5_window_backtest.json"))
for m in r["holdout_meta"]:
    print(m["holdout"], m["patch"], "参赛", m["n_participants"],
          "有号位", m["n_with_position"],
          "无赛前历史", m["n_participants_without_pre_event_history"])
print("参与配对单元", r["decision"]["n_units_compared"])
print("跳过单元", len(r["skipped"]))
print("交集丢弃人次", sum(c["n_dropped_by_intersection"] for c in r["coverage"]))
print("结论 supported =", r["decision"]["supported"])
for name, dv in r["robustness"].items():
    print("  稳健性", name, "supported =", dv["supported"],
          "p =", round(dv["sign_test"]["p"], 4))
PY
```

必须核对的四点：

1. 每届 `n_participants` 落在 80–110 之间（TI 16–20 队 × 5 人，加少量替补）。数字离谱说明 `match_date` 的年份切分出错。
2. `n_participants_without_pre_event_history` 应该很小（个位数）。数字大说明训练侧的时间过滤或列读取出了问题。
3. `n_units_compared` 上限是 4 届 × 12 项 × 5 号位 = 240。远低于 240 说明跳过太多，要回头看 `skipped` 的原因分布。
4. `holdout_meta[*].arms["L955d"].since_ts` 应等于 `event_start_ts - 955*86400`。

- [ ] **Step 4: 通读 markdown 报告**

```bash
cat reports/p5_window_backtest.md
```

确认：结论段的措辞与 `supported` 一致；判不出显著时出现"没有证据支持"且带上那句"不等于证明两者一样"的限定；滑动窗口表里每段的"跨越的版本"与该段时间区间对得上；稳健性表里三个变体都在，且"结论同向？"那一列如果出现"否"，必须在报告里补一句说明——主结论被某个口径推翻是最值得写出来的信息，不能只留在表格里。

- [ ] **Step 5: 提交产出物**

```bash
git add reports/p5_window_backtest.json reports/p5_window_backtest.md
git commit -m "$(printf 'feat: 窗口版本切换回测首份结果入库\n\n四届 TI holdout × 12 个计分项 × 7 个候选臂，主判据同号位内 Spearman。\n结论按预注册的两条判定得出，好看不好看都如实记录。\n本次不改产线：l4_* 的 since_ts 仍是 2024-01-01，未重跑 reports 其余\n产出物，未重新冻结存证。\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>')"
```

---

## 完成后的交接

回测结果出来之后，按 spec §8 的三种结局分别处理，**都不在本计划范围内，另开任务**：

| 结局 | 下一步 |
|---|---|
| 两条判定都满足 | 改 `l4_fantasy_report.py` / `l4_players_report.py` / `l4_extremes_report.py` 的 `since_ts`、重出三份报告、更新站点数字、写更新日志、重新冻结存证 |
| 判不出显著 | 产线不动；`00-DESIGN.md` §10 已知限制加一条，说明这个窗口选择做过验证但检验力不足 |
| 滑动曲线显示平滑衰减、无版本台阶 | 产线不动；把时间衰减加权（半衰期）列为后续候选方案，注意它要动 `l3_player.py` 的 `shrink`/`fit_rate_model`，是更大的改动 |
