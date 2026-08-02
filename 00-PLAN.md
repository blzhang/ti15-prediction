# TI15 预测项目 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 TI15（2026-08-13 开赛）之前，把设计文档 `00-DESIGN.md` 里 L3/L4/L5 三层补完、把 L2 的六处近似假设收紧、并按 §4.2 与市场赔率融合，产出可冻结存证、赛后可评分的战队层面与选手层面预测。

**Architecture:** 分层管线。L0 数据地基与 L1 队伍实力（Bradley-Terry + 赛区随机效应 + 赛事级别自举加权）已实现；L2 赛制模拟（瑞士轮逐轮蒙特卡洛 + 8 队双败）已实现但含 6 处近似。本计划补 L3 选手能力层（层次泊松，按 1–5 号位分层）、L4 合成层（Fantasy 分项矩阵 / 极值 / 排名 / 个人数据）、L5 审计层（赛前冻结哈希 + 赛后 Brier 校准），并把 L2 的假设逐条收紧。

**Tech Stack:** Python 3.9.6 / numpy 2.0.2 / scipy 1.13.1 / pandas 2.3.3 / pytest 8.4.2。**无 sklearn，不引入任何新依赖。**

## Global Constraints

- **Python 3.9.6**：不可用 `match` 语句、不可用 `X | None` 运行时注解（需 `from __future__ import annotations` 或 `Optional[X]`）、不可用 `dict |` 合并运算符以外的 3.10+ 语法。
- **依赖冻结**：只允许 numpy / scipy / pandas / pytest + 标准库。**不装新包。**
- **严禁写入 `/Users/zhangbeilong/Documents/Claude/Projects/TACT`** —— 那是无关的 A 股量化仓库，装了 git 守卫。本项目所有产出只写本项目目录。
- **网络请求**：本机 shell 设了代理 `HTTP_PROXY=HTTPS_PROXY=http://127.0.0.1:7890`，会导致 TLS 握手失败（curl 退出码 35）。任何联网步骤必须 `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy` 且 `curl --noproxy '*' --compressed --max-time 30`。
- **OpenDota 限速**：60 次/分、3000 次/日，响应头带 `x-rate-limit-remaining-minute` / `-day`。大查询中**禁用 LEFT JOIN**（同样 3 万行，带 4 个 JOIN 需 300 秒，不带仅 11.5 秒）。
- **健全性护栏（设计文档 §5）**：赛前预测准确率现实上限 **65–70%**，Brier 健康区间 **0.21–0.24**。任何步骤跑出 >80% 准确率必须停下来查泄漏，不得当成好结果。
- **禁随机交叉验证**：一律时间切分（train 在切点前，test 在切点后）。
- **概率输出**：JSON 一律 float，保 6 位小数；表格展示保 1 位百分比。
- **随机种子**：所有蒙特卡洛固定 `np.random.default_rng(20260802)`，保证可复现。
- **每个 Task 结束必须 `pytest -q` 全绿再 commit。**

## 已有资产（不要重复造）

| 路径 | 内容 |
|---|---|
| `00-DESIGN.md` | 设计文档 v2，本计划的唯一需求来源 |
| `01`~`06-*.md` | 六份调研报告 |
| `data/pro_matches_2020_2026.csv` | 145,974 场，列见 §Task5 |
| `data/pro_player_matches_2020_2026.csv` | 1,459,742 行，32 列 |
| `data/pro_picks_bans_2020_2026.csv` | 3,436,132 行 |
| `data/pro_dim_leagues.csv` / `pro_dim_teams.csv` | 维表 |
| `model/rosters.py` | 16 队 × 5 人 account_id、位置、赛区、阵容变动等级 |
| `model/l0_align.py` | 实体对齐（选手 ID 反查血统） |
| `model/l1_strength.py` | BT 实力模型，产出 `l1_rating.json` |
| `model/l2_simulate.py` | 赛制模拟，产出 `l2_predictions.json` |

---

## File Structure

| 文件 | 职责 |
|---|---|
| `model/freeze.py` | L5：把任意预测 JSON 加时间戳 + sha256 冻结存证 |
| `model/market.py` | 赔率去水（remove overround）与 log-odds 融合 |
| `model/swiss.py` | 瑞士轮配对逻辑（从 `l2_simulate.py` 抽出，可独立测试） |
| `model/bracket.py` | 双败淘汰赛结构（从 `l2_simulate.py` 抽出） |
| `model/l2_simulate.py` | 改为编排层，调用 `swiss.py` / `bracket.py` |
| `model/fantasy_stats.py` | L3 数据：从原始 CSV 抽 18 项 fantasy 计分项 |
| `model/l3_player.py` | L3 模型：层次泊松，按号位分层 |
| `model/l4_fantasy.py` | L4-P1：Fantasy 分项矩阵（队×角色组 + 单选手两口径） |
| `model/l4_players.py` | L4-P3/P4：选手排名与个人数据预测 |
| `model/l4_extremes.py` | L4-P2：极值题（经验频率 + 层次平滑） |
| `model/score.py` | L5：赛后 Brier / LogLoss / 校准曲线 |
| `tests/` | 全部单元测试 |

---

### Task 1: 项目落地、git 存证基础设施、冻结当前预测

当前所有产出在会话级临时目录，**不保证留存**；且 L5 冻结存证（设计文档 §4.5）尚未做，而预测结果已经产出——每多等一天，"赛前预测"的可信度就掉一分。本任务把两件事一起解决。

**Files:**
- Create: `~/Documents/Claude/Projects/TI15-Prediction/`（新根目录，用户可改）
- Create: `model/freeze.py`
- Create: `tests/test_freeze.py`
- Create: `.gitignore`
- Create: `pytest.ini`

**Interfaces:**
- Produces: `freeze_predictions(src_path: str, out_dir: str, label: str) -> dict`
  返回 `{"label", "frozen_at_utc", "sha256", "src", "frozen_path"}`
- Produces: `verify_frozen(record_path: str) -> bool`

- [ ] **Step 1: 迁移目录并 git init**

```bash
SRC="/private/tmp/claude-501/-Users-zhangbeilong-Documents-Claude-Projects-TACT/d8f10102-b93b-4c9d-8535-8728cd41175a/scratchpad/ti15-research"
DST="$HOME/Documents/Claude/Projects/TI15-Prediction"
mkdir -p "$DST" && cp -R "$SRC"/. "$DST"/
cd "$DST" && git init && git branch -M main
```

预期：`Initialized empty Git repository`。**注意 `$DST` 必须不在 TACT 仓库内**，执行前用 `git -C "$DST" rev-parse --show-toplevel` 确认返回的是 `$DST` 自身。

- [ ] **Step 2: 写 .gitignore 与 pytest.ini**

`.gitignore`：
```
data/*.csv
data/*.parquet
*.pyc
__pycache__/
.pytest_cache/
html_*.json
raw_*.json
lp_*.json
lp_*.html
lp_*.txt
```
（数据 350MB，不进 git；脚本可重跑。）

`pytest.ini`：
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 3: 写失败的测试**

`tests/test_freeze.py`：
```python
import json, os, tempfile
from model.freeze import freeze_predictions, verify_frozen


def test_freeze_records_hash_and_is_verifiable():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "pred.json")
        json.dump({"champion": {"A": 0.5, "B": 0.5}}, open(src, "w"))
        rec = freeze_predictions(src, d, label="test-run")

        assert rec["label"] == "test-run"
        assert len(rec["sha256"]) == 64
        assert rec["frozen_at_utc"].endswith("Z")
        assert os.path.exists(rec["frozen_path"])
        assert verify_frozen(os.path.join(d, "freeze_test-run.json")) is True


def test_verify_fails_when_frozen_copy_tampered():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "pred.json")
        json.dump({"champion": {"A": 1.0}}, open(src, "w"))
        rec = freeze_predictions(src, d, label="t2")
        with open(rec["frozen_path"], "w") as f:
            f.write('{"champion": {"A": 0.9}}')
        assert verify_frozen(os.path.join(d, "freeze_t2.json")) is False
```

- [ ] **Step 4: 跑测试确认失败**

Run: `cd "$DST" && python3 -m pytest tests/test_freeze.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'model.freeze'`

- [ ] **Step 5: 实现 freeze.py**

```python
"""L5 审计层：赛前冻结存证。

设计文档 §4.5：预测产出后立即冻结 + 哈希存证，赛后才能诚实地评分。
不这么做，事后就没法证明预测是赛前做的。
"""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze_predictions(src_path, out_dir, label):
    """把 src_path 复制成不可变副本并记录 sha256 与 UTC 时间戳。"""
    os.makedirs(out_dir, exist_ok=True)
    frozen_path = os.path.join(out_dir, "frozen_%s.json" % label)
    shutil.copyfile(src_path, frozen_path)
    record = {
        "label": label,
        "frozen_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha256": _sha256(frozen_path),
        "src": os.path.abspath(src_path),
        "frozen_path": os.path.abspath(frozen_path),
    }
    with open(os.path.join(out_dir, "freeze_%s.json" % label), "w") as f:
        json.dump(record, f, indent=1, ensure_ascii=False)
    return record


def verify_frozen(record_path):
    """重算冻结副本的哈希，与存证记录比对。"""
    with open(record_path) as f:
        rec = json.load(f)
    if not os.path.exists(rec["frozen_path"]):
        return False
    return _sha256(rec["frozen_path"]) == rec["sha256"]
```

同时建 `model/__init__.py`（空文件）和 `tests/__init__.py`（空文件），否则 `from model.freeze import` 找不到包。

- [ ] **Step 6: 跑测试确认通过**

Run: `python3 -m pytest tests/test_freeze.py -q`
Expected: `2 passed`

- [ ] **Step 7: 冻结当前的 L1/L2 预测**

```bash
python3 -c "
from model.freeze import freeze_predictions
for f, lab in [('model/l2_predictions.json','v1-teamlevel'),
               ('model/l1_rating.json','v1-rating')]:
    r = freeze_predictions(f, 'frozen', lab)
    print(lab, r['frozen_at_utc'], r['sha256'][:16])
"
```
预期：打印两行，各带 UTC 时间戳与哈希前 16 位。

- [ ] **Step 8: 提交**

```bash
git add -A && git commit -m "chore: 项目落地 + L5 冻结存证，冻结 v1 战队层面预测"
```

---

### Task 2: 赔率去水与市场融合

设计文档 §4.2 明确要求「市场权重 60–80%，log-odds 融合」，v2 的 §9.5 结果**尚未做这一步**，§9.8 把它列为影响「大」的假设 A6。这是当前对最终数字影响最大的一块。

**Files:**
- Create: `model/market.py`
- Create: `tests/test_market.py`
- Create: `model/market_odds.json`（人工录入的赔率快照）

**Interfaces:**
- Consumes: `model/l2_predictions.json` 的 `champion` 字段
- Produces: `devig(odds: dict) -> dict` —— 小数赔率 → 去水后概率，和为 1
- Produces: `blend_logodds(model_p: dict, market_p: dict, w_market: float) -> dict` —— 融合后概率，和为 1

- [ ] **Step 1: 写失败的测试**

`tests/test_market.py`：
```python
import math
import pytest
from model.market import devig, blend_logodds


def test_devig_removes_overround_and_normalises():
    # 三路盘，隐含概率和 = 1/2 + 1/3 + 1/4 = 1.0833（8.3% 抽水）
    p = devig({"A": 2.0, "B": 3.0, "C": 4.0})
    assert abs(sum(p.values()) - 1.0) < 1e-12
    # 去水后应保持原始顺序与相对比例
    assert p["A"] > p["B"] > p["C"]
    assert abs(p["A"] / p["B"] - (1 / 2) / (1 / 3)) < 1e-12


def test_devig_rejects_non_positive_odds():
    with pytest.raises(ValueError):
        devig({"A": 0.0, "B": 3.0})


def test_blend_is_identity_at_extremes():
    m = {"A": 0.7, "B": 0.3}
    k = {"A": 0.4, "B": 0.6}
    assert blend_logodds(m, k, 0.0)["A"] == pytest.approx(0.7)
    assert blend_logodds(m, k, 1.0)["A"] == pytest.approx(0.4)


def test_blend_geometric_midpoint_and_normalised():
    m = {"A": 0.8, "B": 0.2}
    k = {"A": 0.2, "B": 0.8}
    out = blend_logodds(m, k, 0.5)
    assert abs(sum(out.values()) - 1.0) < 1e-12
    # 对称输入，50/50 权重 → 各 0.5
    assert out["A"] == pytest.approx(0.5)


def test_blend_requires_same_keys():
    with pytest.raises(ValueError):
        blend_logodds({"A": 1.0}, {"B": 1.0}, 0.5)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_market.py -q`
Expected: FAIL — `No module named 'model.market'`

- [ ] **Step 3: 实现 market.py**

```python
"""赔率去水与 log-odds 融合。

设计文档 §4.2：
  - 夺冠盘 overround 常在 1.20–1.40，不去水直接当概率会看到「每支队都被高估」的假象
  - 文献共识是融合优于对抗，市场权重建议 60–80%
"""
import math

W_MARKET_DEFAULT = 0.7   # §4.2 建议区间 0.6–0.8 的中点


def devig(odds):
    """小数赔率 dict → 去水后概率 dict（比例法 / proportional normalisation）。"""
    if not odds:
        raise ValueError("odds 不能为空")
    for k, v in odds.items():
        if v is None or v <= 0:
            raise ValueError("赔率必须为正：%s=%r" % (k, v))
    raw = {k: 1.0 / v for k, v in odds.items()}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}


def blend_logodds(model_p, market_p, w_market=W_MARKET_DEFAULT):
    """在 log-odds 空间加权平均后重新归一化。

    w_market=0 → 纯模型；w_market=1 → 纯市场。
    """
    if set(model_p) != set(market_p):
        raise ValueError("两侧 key 必须一致")
    if not 0.0 <= w_market <= 1.0:
        raise ValueError("w_market 必须在 [0,1]")

    def logit(p):
        p = min(max(p, 1e-9), 1 - 1e-9)
        return math.log(p / (1 - p))

    z = {k: (1 - w_market) * logit(model_p[k]) + w_market * logit(market_p[k])
         for k in model_p}
    raw = {k: 1.0 / (1.0 + math.exp(-v)) for k, v in z.items()}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_market.py -q`
Expected: `5 passed`

- [ ] **Step 5: 录入赔率快照**

建 `model/market_odds.json`。**只填实际查到的数字，查不到的队留 `null`，不许编造。**
已知（`01-ti15-facts.md` §5，抓取于 2026-08-01，仅 5 队）：

```json
{
  "source": "bookmaker composite, 01-ti15-facts.md §5",
  "captured_utc": "2026-08-01",
  "note": "仅 5 队有盘口，其余为 null。null 项在融合时退回纯模型概率。",
  "decimal_odds": {
    "TEAM VISION": 4.50,
    "Team Spirit": 5.00,
    "Team Yandex": 6.00,
    "Iron Wing": 7.00,
    "Team Falcons": 9.00,
    "Aurora Gaming": null, "BoomBoys": null, "Team Liquid": null,
    "Xtreme Gaming": null, "Vici Gaming": null, "Team Resilience": null,
    "Nigma Galaxy": null, "HULIGANI": null, "OG": null,
    "GamerLegion": null, "LGD Gaming": null
  }
}
```

**开工前先重跑一次赔率抓取补齐 null**（联网步骤，遵守 Global Constraints 的代理规则）。补不齐就按下面的部分融合处理。

- [ ] **Step 6: 写部分融合的测试**

追加到 `tests/test_market.py`：
```python
from model.market import blend_partial


def test_blend_partial_leaves_unpriced_teams_on_model_only():
    model = {"A": 0.5, "B": 0.3, "C": 0.2}
    odds = {"A": 2.0, "B": 4.0, "C": None}
    out = blend_partial(model, odds, w_market=1.0)
    assert abs(sum(out.values()) - 1.0) < 1e-12
    # C 无盘口 → 其相对于总量的份额不应被市场信息改变方向
    assert out["C"] > 0.0
    # A/B 有盘口且 w=1 → 二者比例应贴近去水后的市场比例
    assert out["A"] / out["B"] == pytest.approx((1 / 2.0) / (1 / 4.0), rel=0.05)
```

- [ ] **Step 7: 实现 blend_partial**

追加到 `model/market.py`：
```python
def blend_partial(model_p, decimal_odds, w_market=W_MARKET_DEFAULT):
    """只有部分队有盘口时的融合。

    做法：对有盘口的子集做条件去水与融合，保持该子集的总概率质量不变；
    无盘口的队保留纯模型概率。这样避免用「假的 null 赔率」污染结果。
    """
    priced = {k: v for k, v in decimal_odds.items() if v}
    if not priced:
        return dict(model_p)
    mass = sum(model_p[k] for k in priced)
    cond_model = {k: model_p[k] / mass for k in priced}
    cond_market = devig(priced)
    blended = blend_logodds(cond_model, cond_market, w_market)
    out = dict(model_p)
    for k in priced:
        out[k] = blended[k] * mass
    s = sum(out.values())
    return {k: v / s for k, v in out.items()}
```

- [ ] **Step 8: 跑测试确认通过**

Run: `python3 -m pytest tests/test_market.py -q`
Expected: `6 passed`

- [ ] **Step 9: 产出融合后的预测并冻结**

```bash
python3 -c "
import json
from model.market import blend_partial
from model.freeze import freeze_predictions
pred = json.load(open('model/l2_predictions.json'))
odds = json.load(open('model/market_odds.json'))['decimal_odds']
out = blend_partial(pred['champion'], odds, w_market=0.7)
json.dump({'champion_blended': out, 'w_market': 0.7},
          open('model/l2_blended.json','w'), indent=1, ensure_ascii=False)
for k, v in sorted(out.items(), key=lambda kv: -kv[1]):
    print('%-17s %6.1f%%' % (k, v*100))
"
python3 -c "
from model.freeze import freeze_predictions
print(freeze_predictions('model/l2_blended.json','frozen','v2-blended')['sha256'][:16])
"
```
预期：16 行概率、合计 100.0%，并打印哈希。**若融合后 Falcons 的概率相对纯模型下降超过 5pp，在提交信息里记一句**——那正是设计文档 §9.7 标记的主动偏离被市场拉回的量。

- [ ] **Step 10: 提交**

```bash
git add -A && git commit -m "feat: 赔率去水与 log-odds 融合，产出并冻结 v2 融合预测"
```

---

### Task 3: 瑞士轮配对保真度（收紧假设 A1/A2/A4）

`00-DESIGN.md` §9.8 列了三处瑞士轮近似：R1 随机配对（A1）、未实现分轮修正（A2）、附加轮用排位近似（A4）。**A2 影响最大**——设计文档 §9.6 的 5-0 / 4-1 分布正是官方预测题的直接答案，配对逻辑错会直接改变这两个数。

TI14 原文规则（`01-ti15-facts.md` §1.3）：R1 分两组、由赛事方指定对阵；R2/R3 只在组内配对；R4 只与另一组配对；R5 无特殊修正。

**Files:**
- Create: `model/swiss.py`（从 `l2_simulate.py` 抽出配对与排名逻辑）
- Create: `tests/test_swiss.py`
- Modify: `model/l2_simulate.py`（改为调用 `swiss.py`）

**Interfaces:**
- Produces: `rank_teams(state: SwissState, rng) -> List[int]` —— 按 胜场→负场→小局胜率→Buchholz→对手平均小局胜率→掷硬币 排序
- Produces: `pair_round(state: SwissState, rnd: int, rng) -> List[Tuple[int,int]]` —— `rnd` 从 0 计
- Produces: `class SwissState` 字段 `wins/losses/game_wins/game_losses/played/opponents/group`

- [ ] **Step 1: 写失败的测试**

`tests/test_swiss.py`：
```python
import numpy as np
import pytest
from model.swiss import SwissState, pair_round, rank_teams


def fresh(n=16):
    s = SwissState(n)
    s.group = [0] * 8 + [1] * 8
    return s


def test_round1_pairs_across_the_two_groups():
    rng = np.random.default_rng(1)
    s = fresh()
    pairs = pair_round(s, 0, rng)
    assert len(pairs) == 8
    for a, b in pairs:
        assert s.group[a] != s.group[b], "R1 必须跨组配对"
    assert sorted([t for p in pairs for t in p]) == list(range(16))


def test_round2_pairs_only_within_group():
    rng = np.random.default_rng(2)
    s = fresh()
    for a, b in pair_round(s, 0, rng):
        s.record(a, b, a_wins=True, loser_games=1)
    for a, b in pair_round(s, 1, rng):
        assert s.group[a] == s.group[b], "R2 只在组内配对"


def test_round4_prefers_cross_group_but_score_group_wins():
    """R4 规则是「只与另一组配对」，但它是**次级**约束——
    同战绩配对优先。当某个战绩组内两队恰好同属一组时，跨组不可能满足。
    因此断言的是「绝大多数跨组」，而非「全部跨组」。
    """
    rng = np.random.default_rng(3)
    cross = same = 0
    for _ in range(50):
        s = fresh()
        for rnd in range(3):
            for a, b in pair_round(s, rnd, rng):
                s.record(a, b, a_wins=bool(rng.random() < 0.5), loser_games=0)
        for a, b in pair_round(s, 3, rng):
            if s.group[a] != s.group[b]:
                cross += 1
            else:
                same += 1
    assert cross / (cross + same) > 0.75, "R4 应以跨组为主"


def test_no_rematch_within_five_rounds():
    rng = np.random.default_rng(4)
    s = fresh()
    for rnd in range(5):
        for a, b in pair_round(s, rnd, rng):
            assert b not in s.played[a], "不得重赛"
            s.record(a, b, a_wins=bool(rng.random() < 0.5), loser_games=1)


def test_at_most_one_team_can_go_5_0():
    """瑞士轮结构性事实：同分配对强制不败队互碰，5 轮后至多 1 支 5-0。"""
    rng = np.random.default_rng(5)
    for _ in range(200):
        s = fresh()
        for rnd in range(5):
            for a, b in pair_round(s, rnd, rng):
                s.record(a, b, a_wins=bool(rng.random() < 0.5), loser_games=0)
        assert sum(1 for t in range(16) if s.wins[t] == 5) <= 1


def test_rank_uses_buchholz_before_coinflip():
    s = fresh()
    # 两队同为 1 胜 0 负、小局同为 2-0，但 0 号的对手更强（更多胜场）
    s.wins[0] = s.wins[1] = 1
    s.game_wins[0] = s.game_wins[1] = 2
    s.opponents[0] = [2]; s.wins[2] = 4
    s.opponents[1] = [3]; s.wins[3] = 0
    order = rank_teams(s, np.random.default_rng(6))
    assert order.index(0) < order.index(1), "Buchholz 高的应排前面"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_swiss.py -q`
Expected: FAIL — `No module named 'model.swiss'`

- [ ] **Step 3: 实现 swiss.py**

```python
"""瑞士轮配对与排名。

规则来源 01-ti15-facts.md §1.3（TI14 原文，TI15 页面此节为空，按惯例沿用）：
  排名判据：胜场 → 负场 → 小局胜率 → Buchholz（对手总胜场）
            → 对手平均小局胜率 → 掷硬币
  配对：同战绩配对 / 尽量避免重赛 / 尽量最小化排名距离
  分轮修正：R1 分两组由赛事方指定；R2/R3 只组内；R4 只跨组；R5 无修正
"""


class SwissState(object):
    def __init__(self, n=16):
        self.n = n
        self.wins = [0] * n
        self.losses = [0] * n
        self.game_wins = [0] * n
        self.game_losses = [0] * n
        self.played = [set() for _ in range(n)]
        self.opponents = [[] for _ in range(n)]
        self.group = [0] * (n // 2) + [1] * (n - n // 2)

    def record(self, a, b, a_wins, loser_games):
        """记一场 BO3 结果。loser_games = 输方拿到的小局数（0 或 1）。"""
        w, l = (a, b) if a_wins else (b, a)
        self.wins[w] += 1
        self.losses[l] += 1
        self.game_wins[w] += 2
        self.game_losses[w] += loser_games
        self.game_wins[l] += loser_games
        self.game_losses[l] += 2
        self.played[a].add(b)
        self.played[b].add(a)
        self.opponents[a].append(b)
        self.opponents[b].append(a)

    def game_rate(self, t):
        d = self.game_wins[t] + self.game_losses[t]
        return self.game_wins[t] / d if d else 0.0

    def buchholz(self, t):
        return sum(self.wins[o] for o in self.opponents[t])

    def opp_game_rate(self, t):
        if not self.opponents[t]:
            return 0.0
        return sum(self.game_rate(o) for o in self.opponents[t]) / len(self.opponents[t])


def rank_teams(state, rng):
    return sorted(
        range(state.n),
        key=lambda t: (-state.wins[t], state.losses[t], -state.game_rate(t),
                       -state.buchholz(t), -state.opp_game_rate(t), rng.random()),
    )


def _pair_pool(pool, state, must_differ_group=None):
    """在一个候选池内配对：上半区对下半区，避免重赛，必要时局部交换。"""
    pairs, used = [], set()
    half = len(pool) // 2
    top, bot = pool[:half], pool[half:]
    for a in top:
        cands = [b for b in bot if b not in used
                 and b not in state.played[a]
                 and (must_differ_group is None
                      or (state.group[a] != state.group[b]) == must_differ_group)]
        if not cands:   # 放宽：先放弃分组约束，再放弃避免重赛
            cands = [b for b in bot if b not in used and b not in state.played[a]]
        if not cands:
            cands = [b for b in bot if b not in used]
        b = cands[0]
        used.add(b)
        pairs.append((a, b))
    return pairs


def pair_round(state, rnd, rng):
    """rnd 从 0 计。返回 [(a,b), ...]。"""
    order = rank_teams(state, rng)

    if rnd == 0:                       # R1：跨组，赛事方指定，用同组内随机近似
        g0 = [t for t in order if state.group[t] == 0]
        g1 = [t for t in order if state.group[t] == 1]
        rng.shuffle(g0)
        rng.shuffle(g1)
        return list(zip(g0, g1))

    if rnd in (1, 2):                  # R2/R3：只在组内
        pairs = []
        for g in (0, 1):
            pool = [t for t in order if state.group[t] == g]
            pairs += _pair_by_score(pool, state, None)
        return pairs

    if rnd == 3:                       # R4：只跨组
        return _pair_by_score(order, state, must_differ_group=True)

    return _pair_by_score(order, state, None)      # R5：无修正


def _pair_by_score(pool, state, must_differ_group):
    """按战绩分组，组内上半区对下半区，奇数组下浮一队。"""
    remaining = list(pool)
    pairs = []
    while remaining:
        s = state.wins[remaining[0]]
        grp = [t for t in remaining if state.wins[t] == s]
        if len(grp) % 2 == 1:
            rest = [t for t in remaining if state.wins[t] != s]
            if rest:
                grp.append(rest[0])
        pairs += _pair_pool(grp, state, must_differ_group)
        for t in grp:
            if t in remaining:
                remaining.remove(t)
    return pairs
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_swiss.py -q`
Expected: `6 passed`

- [ ] **Step 5: 把 l2_simulate.py 改为调用 swiss.py**

删除 `l2_simulate.py` 里的 `swiss_pair` 函数和 `run_one` 中内联的瑞士轮循环，替换为：

```python
from model.swiss import SwissState, pair_round, rank_teams

def run_one(theta, rng):
    p1 = 1.0 / (1.0 + np.exp(-(theta[:, None] - theta[None, :])))
    p3 = p1 ** 2 * (3 - 2 * p1)
    q = 1 - p1
    p5 = p1 ** 3 * (1 + 3 * q + 6 * q ** 2)

    s = SwissState(n)
    s.group = list(rng.permutation([0] * 8 + [1] * 8))   # 分组未公布，随机化
    for rnd in range(5):
        for a, b in pair_round(s, rnd, rng):
            a_wins = rng.random() < p3[a, b]
            s.record(a, b, a_wins, 1 if rng.random() < 0.4386 else 0)

    swiss_rank = rank_teams(s, rng)
    rec = [(s.wins[t], s.losses[t]) for t in range(n)]
    # …以下淘汰赛部分保持原样…
```

- [ ] **Step 6: 重跑模拟，确认 5-0 / 4-1 分布变化在合理范围**

Run: `python3 model/l2_simulate.py`
Expected: 「0 支 5-0」与「1 支 5-0」两项仍合计 100%；夺冠列仍合计 100.0%；进淘汰赛合计 800.0%。
**把新旧 5-0 / 4-1 分布并排记进提交信息**——分轮修正会改变这两个数，这是本任务的目的，要留痕。

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "fix: 瑞士轮实现分轮配对修正(R1跨组/R2R3组内/R4跨组)，收紧假设 A1/A2"
```

---

### Task 4: 淘汰赛种子与让分小局（收紧假设 A3/A5）

A3：淘汰赛种子假定按瑞士轮名次排 1–8，Liquipedia 未列规则。A5：BO3 让分小局用固定 q=0.4386，未按实力差调整——强弱悬殊时更可能 2-0，接近时更可能 2-1。

**Files:**
- Create: `model/bracket.py`
- Create: `tests/test_bracket.py`
- Modify: `model/l2_simulate.py`

**Interfaces:**
- Produces: `run_playoffs(seeds: List[int], p3: np.ndarray, p5: np.ndarray, rng) -> Dict[int,int]` —— 返回 `{team_index: placement}`，placement ∈ {1,2,3,4,5,7}
- Produces: `loser_games_prob(p_game: float) -> float` —— BO3 中输方拿到 1 小局的条件概率

- [ ] **Step 1: 写失败的测试**

`tests/test_bracket.py`：
```python
import numpy as np
import pytest
from model.bracket import run_playoffs, loser_games_prob


def _matrix(theta):
    t = np.asarray(theta, dtype=float)
    p1 = 1.0 / (1.0 + np.exp(-(t[:, None] - t[None, :])))
    p3 = p1 ** 2 * (3 - 2 * p1)
    q = 1 - p1
    p5 = p1 ** 3 * (1 + 3 * q + 6 * q ** 2)
    return p3, p5


def test_placements_are_structurally_valid():
    p3, p5 = _matrix([2, 1.5, 1, .5, 0, -.5, -1, -1.5])
    rng = np.random.default_rng(0)
    place = run_playoffs(list(range(8)), p3, p5, rng)
    assert sorted(place.keys()) == list(range(8))
    assert sorted(place.values()) == [1, 2, 3, 4, 5, 5, 7, 7]


def test_strongest_seed_wins_most_often():
    p3, p5 = _matrix([4, 0, 0, 0, 0, 0, 0, 0])
    rng = np.random.default_rng(1)
    champs = [min(run_playoffs(list(range(8)), p3, p5, rng).items(),
                  key=lambda kv: kv[1])[0] for _ in range(400)]
    assert champs.count(0) / 400 > 0.7


def test_loser_games_prob_is_higher_for_even_matchups():
    assert loser_games_prob(0.50) > loser_games_prob(0.85)
    assert 0.0 < loser_games_prob(0.99) < 1.0


def test_loser_games_prob_matches_bo3_conditional_algebra():
    # BO3 中赢方 2-1 的概率 = 2p^2(1-p)；赢方获胜概率 = p^2(3-2p)
    p = 0.6
    expected = 2 * p ** 2 * (1 - p) / (p ** 2 * (3 - 2 * p))
    assert loser_games_prob(p) == pytest.approx(expected)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_bracket.py -q`
Expected: FAIL — `No module named 'model.bracket'`

- [ ] **Step 3: 实现 bracket.py**

```python
"""8 队双败淘汰赛。

结构来源 01-ti15-facts.md §1.2（Liquipedia 逐槽位点数）：
  UB: QF 4 场 → SF 2 场 → UBF 1 场 = 7 场
  LB: R1 2 场 → QF 2 场 → SF 1 场 → LBF 1 场 = 6 场
  决赛 BO5，其余全 BO3，**无 bracket reset**
名次：1 冠 / 2 亚 / 3 = LBF 负 / 4 = LB SF 负 / 5-6 = LB QF 负 / 7-8 = LB R1 负
"""


def loser_games_prob(p_game):
    """BO3 中，在赢方获胜的条件下，输方拿到 1 小局的概率。

    收紧假设 A5：原实现用固定常数 0.4386（TI14 全局实测），
    但强弱悬殊时更可能 2-0、势均力敌时更可能 2-1，应随实力差变化。
    赢方 2-1 概率 = 2p²(1-p)；赢方总胜率 = p²(3-2p)。
    """
    p = min(max(float(p_game), 1e-9), 1 - 1e-9)
    return 2 * p * (1 - p) / (3 - 2 * p)


def run_playoffs(seeds, p3, p5, rng):
    """seeds 为长度 8 的队伍索引列表，seeds[0] 为 1 号种子。返回 {队伍索引: 名次}。"""
    place = {}

    def m3(a, b):
        return a if rng.random() < p3[a, b] else b

    # UB QF：1v8 4v5 2v7 3v6
    qf = [(seeds[0], seeds[7]), (seeds[3], seeds[4]),
          (seeds[1], seeds[6]), (seeds[2], seeds[5])]
    ubw, ubl = [], []
    for a, b in qf:
        w = m3(a, b)
        ubw.append(w)
        ubl.append(b if w == a else a)

    sfw, sfl = [], []
    for a, b in ((ubw[0], ubw[1]), (ubw[2], ubw[3])):
        w = m3(a, b)
        sfw.append(w)
        sfl.append(b if w == a else a)

    ubf_w = m3(sfw[0], sfw[1])
    ubf_l = sfw[1] if ubf_w == sfw[0] else sfw[0]

    lb1w = []
    for a, b in ((ubl[0], ubl[1]), (ubl[2], ubl[3])):
        w = m3(a, b)
        lb1w.append(w)
        place[b if w == a else a] = 7

    lb2w = []
    for a, b in ((lb1w[0], sfl[1]), (lb1w[1], sfl[0])):
        w = m3(a, b)
        lb2w.append(w)
        place[b if w == a else a] = 5

    lbsf_w = m3(lb2w[0], lb2w[1])
    place[lb2w[1] if lbsf_w == lb2w[0] else lb2w[0]] = 4

    lbf_w = m3(lbsf_w, ubf_l)
    place[ubf_l if lbf_w == lbsf_w else lbsf_w] = 3

    champ = ubf_w if rng.random() < p5[ubf_w, lbf_w] else lbf_w   # 无 bracket reset
    place[champ] = 1
    place[lbf_w if champ == ubf_w else ubf_w] = 2
    return place
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_bracket.py -q`
Expected: `4 passed`

- [ ] **Step 5: 在 l2_simulate.py 里接上 bracket.py 和动态让分**

替换 `s.record(a, b, a_wins, 1 if rng.random() < 0.4386 else 0)` 为：
```python
from model.bracket import loser_games_prob, run_playoffs

pw = p3[a, b] if a_wins else p3[b, a]
pg = p1[a, b] if a_wins else p1[b, a]
s.record(a, b, a_wins, 1 if rng.random() < loser_games_prob(pg) else 0)
```
并把淘汰赛整段替换为 `place = run_playoffs(seeds, p3, p5, rng)`。

- [ ] **Step 6: 加种子规则敏感性检验**

`tests/test_bracket.py` 追加：
```python
def test_seeding_matters_for_champion_odds():
    """种子规则未公布(假设 A3)：验证它到底影响多大，供文档记录。"""
    p3, p5 = _matrix([2, 1.6, 1.2, .8, .4, 0, -.4, -.8])
    rng = np.random.default_rng(7)
    def champ_rate(seeds, n=600):
        return sum(1 for _ in range(n)
                   if min(run_playoffs(seeds, p3, p5, rng).items(),
                          key=lambda kv: kv[1])[0] == 0) / n
    by_rank = champ_rate(list(range(8)))
    reversed_ = champ_rate(list(range(8))[::-1])
    assert abs(by_rank - reversed_) < 0.25, "种子规则影响应小于 25pp，否则必须查实真实规则"
```

- [ ] **Step 7: 跑全部测试并重跑模拟**

Run: `python3 -m pytest -q && python3 model/l2_simulate.py`
Expected: 全绿；模拟自洽校验仍通过（100% / 400% / 800%）。
把上一步测得的种子敏感度写进 `00-DESIGN.md` §9.8 的 A3 行。

- [ ] **Step 8: 提交**

```bash
git add -A && git commit -m "fix: 双败抽成独立模块，让分小局改随实力差变化，收紧假设 A3/A5"
```

---

### Task 5: L3 数据层 —— 抽取 18 项 Fantasy 计分项

`06-fantasy-rules.md` 查实 18 项计分项：本地 CSV 直接有 12 项，3 项需解 JSON blob（Smoke / Tormentor / Courier），**Watcher 与 Lotus 确认取不到**。缺口偏斜——蓝池（辅助向）只有 4/6，而 Support Duo 槽全是蓝色徽记。

**Files:**
- Create: `model/fantasy_stats.py`
- Create: `tests/test_fantasy_stats.py`

**Interfaces:**
- Consumes: `data/pro_player_matches_2020_2026.csv`
- Produces: `SCORING_ITEMS: List[Dict]` —— 18 项，每项 `{"idx","key","pool","column","available"}`
- Produces: `load_player_games(csv_path, account_ids, since_ts) -> pandas.DataFrame`
  列含 `match_id, account_id` 及**本地 CSV 直接可得的**计分项列。
  ⚠️ 三点澄清（Task 5 评审确认）：
  ① smokes / tormentor / courier 虽标 `available=True`，但 `column=None`，**永远不会出现在本函数返回值里**；
     需由调用方另按 `match_id + account_id` 左连接 `data/pro_blob_stats.csv`。
  ② **不产出 `position`**：号位来自 `model/rosters.py` 的策展数据（`POSITIONS`），由调用方 `map` 上去，
     不从单局特征推断。Task 6 Step 5 即如此使用。
  ③ **不产出 `duration_min`**：全项目无任何代码读取它。

`pro_player_matches_2020_2026.csv` 实际列（已核实）：
`match_id, account_id, player_slot, hero_id, kills, deaths, assists, gold_per_min, xp_per_min, net_worth, last_hits, denies, level, hero_damage, tower_damage, hero_healing, teamfight_participation, lane, lane_role, is_roaming, obs_placed, sen_placed, camps_stacked, rune_pickups, towers_killed, roshans_killed, firstblood_claimed, stuns, gold_spent, leaver_status, leagueid, start_time`

- [ ] **Step 1: 写失败的测试**

`tests/test_fantasy_stats.py`：
```python
import numpy as np
import pandas as pd
import pytest
from model.fantasy_stats import SCORING_ITEMS, available_items, load_player_games


def test_eighteen_items_declared_with_pools():
    assert len(SCORING_ITEMS) == 18
    pools = {i["pool"] for i in SCORING_ITEMS}
    assert pools == {"red", "blue", "green"}
    assert sum(1 for i in SCORING_ITEMS if i["pool"] == "red") == 6
    assert sum(1 for i in SCORING_ITEMS if i["pool"] == "blue") == 6
    assert sum(1 for i in SCORING_ITEMS if i["pool"] == "green") == 6


def test_watcher_and_lotus_marked_unavailable():
    unavailable = {i["key"] for i in SCORING_ITEMS if not i["available"]}
    assert "watchers" in unavailable
    assert "lotuses" in unavailable


def test_blue_pool_coverage_is_four_of_six():
    """06-fantasy-rules.md 的结构性缺口：蓝池只有 4/6，Support 槽因此偏弱。"""
    blue = [i for i in SCORING_ITEMS if i["pool"] == "blue"]
    assert sum(1 for i in blue if i["available"]) == 4


def test_load_player_games_filters_and_types(tmp_path):
    csv = tmp_path / "pm.csv"
    csv.write_text(
        "match_id,account_id,player_slot,hero_id,kills,deaths,assists,gold_per_min,"
        "xp_per_min,net_worth,last_hits,denies,level,hero_damage,tower_damage,"
        "hero_healing,teamfight_participation,lane,lane_role,is_roaming,obs_placed,"
        "sen_placed,camps_stacked,rune_pickups,towers_killed,roshans_killed,"
        "firstblood_claimed,stuns,gold_spent,leaver_status,leagueid,start_time\n"
        "1,100,0,5,10,2,8,600,700,20000,300,20,25,40000,3000,0,0.5,2,1,,3,2,4,9,1,0,1,3.5,18000,0,99,1700000000\n"
        "1,200,128,7,1,9,3,250,300,5000,20,1,15,8000,100,500,0.4,3,4,,12,10,0,2,0,0,0,7.25,4500,0,99,1700000000\n"
        "2,100,1,5,4,4,4,500,550,15000,200,10,22,30000,1000,0,0.45,2,1,,2,1,3,5,0,1,0,2.0,14000,0,99,1600000000\n"
    )
    df = load_player_games(str(csv), account_ids={100}, since_ts=1650000000)
    assert list(df["account_id"].unique()) == [100]
    assert len(df) == 1, "1600000000 早于 since_ts，应被过滤"
    assert df["kills"].dtype.kind in "iu"
    assert "is_roaming" in df.columns
    assert df["is_roaming"].isna().sum() == 0, "语义空必须 fillna(False)，不可 dropna"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_fantasy_stats.py -q`
Expected: FAIL — `No module named 'model.fantasy_stats'`

- [ ] **Step 3: 实现 fantasy_stats.py**

```python
"""L3 数据层：Fantasy 18 项计分项的抽取与可得性声明。

来源 06-fantasy-rules.md（客户端本地化文件一手核实）。
基础系数是服务端下发的 {f:helpstat_0..17}，静态提取不到 ——
因此本项目交付「分项产出矩阵」而非绝对总分（设计文档 §4.3）。
"""
import pandas as pd

# pool: red=核心向 / blue=辅助向 / green=节奏向（对应徽记颜色）
# column=None 表示本地 CSV 无直接列；available=False 表示完全取不到
SCORING_ITEMS = [
    {"idx": 0,  "key": "kills",          "pool": "red",   "column": "kills",              "available": True},
    {"idx": 1,  "key": "deaths",         "pool": "red",   "column": "deaths",             "available": True},
    {"idx": 2,  "key": "creep_score",    "pool": "red",   "column": "last_hits",          "available": True},
    {"idx": 3,  "key": "gpm",            "pool": "red",   "column": "gold_per_min",       "available": True},
    {"idx": 4,  "key": "madstone",       "pool": "red",   "column": None,                 "available": False},
    {"idx": 5,  "key": "tower_kills",    "pool": "red",   "column": "towers_killed",      "available": True},
    {"idx": 6,  "key": "wards",          "pool": "blue",  "column": "obs_placed",         "available": True},
    {"idx": 7,  "key": "camps_stacked",  "pool": "blue",  "column": "camps_stacked",      "available": True},
    {"idx": 8,  "key": "runes",          "pool": "blue",  "column": "rune_pickups",       "available": True},
    {"idx": 9,  "key": "watchers",       "pool": "blue",  "column": None,                 "available": False},
    {"idx": 10, "key": "smokes",         "pool": "blue",  "column": None,                 "available": True},
    {"idx": 11, "key": "lotuses",        "pool": "blue",  "column": None,                 "available": False},
    {"idx": 12, "key": "roshan",         "pool": "green", "column": "roshans_killed",     "available": True},
    {"idx": 13, "key": "teamfight",      "pool": "green", "column": "teamfight_participation", "available": True},
    {"idx": 14, "key": "stuns",          "pool": "green", "column": "stuns",              "available": True},
    {"idx": 15, "key": "tormentor",      "pool": "green", "column": None,                 "available": True},
    {"idx": 16, "key": "first_blood",    "pool": "green", "column": "firstblood_claimed", "available": True},
    {"idx": 17, "key": "courier",        "pool": "green", "column": None,                 "available": True},
]

# smokes / tormentor / courier 需从 OpenDota 的 JSON blob 解出，本地 CSV 无列。
# 对应 explorer SQL：item_uses->>'smoke_of_deceit'、killed->>'npc_dota_miniboss'、
# killed->>'npc_dota_courier'（06-fantasy-rules.md §4 实跑验证）。
NEEDS_BLOB = {"smokes", "tormentor", "courier"}

DIRECT_COLUMNS = [i["column"] for i in SCORING_ITEMS if i["available"] and i["column"]]


def available_items(include_blob=True):
    out = [i for i in SCORING_ITEMS if i["available"]]
    if not include_blob:
        out = [i for i in out if i["key"] not in NEEDS_BLOB]
    return out


def load_player_games(csv_path, account_ids, since_ts):
    """读选手-比赛表，过滤到目标选手与时间窗，做类型与空值处理。"""
    usecols = ["match_id", "account_id", "player_slot", "hero_id", "start_time",
               "leagueid", "lane_role", "is_roaming"] + DIRECT_COLUMNS
    df = pd.read_csv(csv_path, usecols=lambda c: c in set(usecols), low_memory=False)
    df = df[df["account_id"].isin(set(account_ids))]
    df = df[df["start_time"].astype("int64") >= int(since_ts)]
    # is_roaming 63.6% 空是语义空（不是缺失），必须 fillna(False)（02-data-sources.md）
    if "is_roaming" in df.columns:
        df["is_roaming"] = df["is_roaming"].fillna(False).astype(bool)
    for c in ("kills", "deaths", "assists", "last_hits", "obs_placed", "sen_placed",
              "camps_stacked", "rune_pickups", "towers_killed", "roshans_killed",
              "firstblood_claimed"):
        if c in df.columns:
            df[c] = df[c].fillna(0).astype("int64")
    return df.reset_index(drop=True)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_fantasy_stats.py -q`
Expected: `4 passed`

- [ ] **Step 5: 抽取三项 blob 字段**

用 OpenDota explorer SQL 拉 smokes / tormentor / courier（遵守 Global Constraints 的代理与限速规则）：

```bash
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
python3 od_sql.py --out data/pro_blob_stats.csv --sql "
SELECT pm.match_id, pm.account_id,
       COALESCE((pm.item_uses->>'smoke_of_deceit')::int, 0) AS smokes,
       COALESCE((pm.killed->>'npc_dota_miniboss')::int, 0)  AS tormentor,
       COALESCE((pm.killed->>'npc_dota_courier')::int, 0)    AS courier
FROM player_matches pm
JOIN matches m ON m.match_id = pm.match_id
WHERE m.start_time >= 1704067200"
```
**注意**：这里的 JOIN 是必要的（要按时间过滤），但只有 1 个 JOIN，不触发 Global Constraints 里那个 4-JOIN 的 300 秒问题。若仍超时，改为先取 match_id 白名单再分批。

校验：`npc_dota_roshan` 在 TI14 上应计得 342（06-fantasy-rules.md 的对照校验值）。

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "feat: L3 数据层，声明 18 项计分项与可得性，抽取 blob 字段"
```

---

### Task 6: L3 层次泊松选手能力模型

设计文档 §3-L3：带 局/选手/版本 随机效应的层次泊松，**按 1–5 号位分层**。
关键洞察（`03-academic-methods.md`）：**负二项 = gamma 混合的泊松**，所以不裸套 NB，
直接建层次模型，把局长、版本、双方强度差作协变量解释掉一部分过离散。

**Files:**
- Create: `model/l3_player.py`
- Create: `tests/test_l3_player.py`

**Interfaces:**
- Consumes: `fantasy_stats.load_player_games`、`l1_rating.json`
- Produces: `fit_rate_model(df, item_key, positions) -> Dict[int, Dict]`
  返回 `{account_id: {"rate": float, "se": float, "n_games": int, "position": int}}`
- Produces: `shrink(raw_rate, n, prior_mean, prior_var, tail_heavy=True) -> Tuple[float,float]`

- [ ] **Step 1: 写失败的测试**

`tests/test_l3_player.py`：
```python
import numpy as np
import pandas as pd
import pytest
from model.l3_player import shrink, fit_rate_model


def test_shrink_pulls_small_samples_toward_prior():
    prior, pv = 5.0, 1.0
    low_n, _ = shrink(raw_rate=12.0, n=2, prior_mean=prior, prior_var=pv)
    high_n, _ = shrink(raw_rate=12.0, n=200, prior_mean=prior, prior_var=pv)
    assert prior < low_n < high_n < 12.0, "样本越少越该被拉回先验"


def test_shrink_se_decreases_with_sample_size():
    _, se_small = shrink(8.0, 3, 5.0, 1.0)
    _, se_big = shrink(8.0, 300, 5.0, 1.0)
    assert se_small > se_big


def test_tail_heavy_prior_shrinks_outliers_less():
    """03-academic-methods.md 的 Clemente Problem：
    重尾先验应避免把真·离群选手过度收缩回均值。"""
    normal, _ = shrink(20.0, 30, 5.0, 1.0, tail_heavy=False)
    heavy, _ = shrink(20.0, 30, 5.0, 1.0, tail_heavy=True)
    assert heavy > normal


def test_tail_heavy_must_not_defeat_shrinkage_on_tiny_samples():
    """护栏：重尾修正只能削弱收缩，不能取消收缩。

    只打 2 局的离群观测（12.0 对先验 5.0）必须仍被显著拉回，
    否则「Clemente 修正」就把收缩机制本身废掉了。
    """
    tiny, _ = shrink(12.0, n=2, prior_mean=5.0, prior_var=1.0, tail_heavy=True)
    assert tiny < 9.0, "2 局样本的离群值必须被显著收缩"


def test_tail_heavy_weight_still_monotone_in_sample_size():
    """无论是否重尾，样本越多越该信观测。"""
    vals = [shrink(12.0, n, 5.0, 1.0, tail_heavy=True)[0] for n in (2, 5, 20, 100)]
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_l3_player.py -q`
Expected: FAIL — `No module named 'model.l3_player'`

- [ ] **Step 3: 实现 l3_player.py**

```python
"""L3 选手能力层：按号位分层的层次泊松 + 收缩。

设计要点（03-academic-methods.md）：
  - 负二项 = gamma 混合的泊松，故不裸套 NB，直接建层次模型
  - 必须按 1–5 号位分层：1 号位与 5 号位的分布完全不是一回事
  - 用重尾先验防止 James-Stein 把真·离群选手过度收缩（"Clemente Problem"）
"""
import numpy as np

TAIL_HEAVY_DF = 4.0     # t 先验自由度，越小尾越重


def shrink(raw_rate, n, prior_mean, prior_var, tail_heavy=True):
    """经验贝叶斯收缩。返回 (后验均值, 后验标准误)。

    高斯共轭：w = prior_var / (prior_var + obs_var)，obs_var = lambda/n。

    重尾修正的正确做法是**放大有效先验方差**（t 先验的尾更厚，
    极端观测因此没那么"意外"），而不是直接抬高观测权重。
    偏离度必须用**总方差**（先验 + 观测）来标准化，否则小样本的
    大偏离会被误判成"真离群"，收缩机制会被完全废掉：
    实测中错误写法给 2 局样本的权重是 0.935、100 局是 0.992，
    样本量几乎不起作用，与收缩的目的正好相反。
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
    post_var = 1.0 / (1.0 / max(prior_var, 1e-9) + n / max(raw_rate, 1e-6))
    return float(post), float(np.sqrt(post_var))


def fit_rate_model(df, item_key, positions):
    """按号位分层估计每名选手的「每局速率」。

    df 需含列：account_id, match_id, position, <item_key 对应的原始列>
    （`position` 由调用方从 rosters.POSITIONS map 上去；`duration_min` 无人使用，不需要）
    positions: {account_id: 1..5}
    """
    if item_key not in df.columns:
        raise KeyError("df 中没有列 %r" % item_key)

    out = {}
    for pos in sorted(set(positions.values())):
        accts = [a for a, p in positions.items() if p == pos]
        sub = df[df["account_id"].isin(accts)]
        if sub.empty:
            continue
        prior_mean = float(sub[item_key].mean())
        # 号位内的选手间方差 = 总方差 - 局内方差（泊松部分）
        per_player = sub.groupby("account_id")[item_key].mean()
        between = float(per_player.var(ddof=1)) if len(per_player) > 1 else 0.0
        within = prior_mean / max(sub.groupby("account_id").size().mean(), 1.0)
        prior_var = max(between - within, prior_mean * 0.05)

        for a in accts:
            g = sub[sub["account_id"] == a]
            if g.empty:
                continue
            raw = float(g[item_key].mean())
            rate, se = shrink(raw, len(g), prior_mean, prior_var)
            out[a] = {"rate": rate, "se": se, "n_games": int(len(g)),
                      "position": pos, "raw_rate": raw}
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_l3_player.py -q`
Expected: `5 passed`

- [ ] **Step 5: 在真实数据上跑一遍并做健全性检查**

```bash
python3 -c "
import json, sys; sys.path.insert(0,'.')
from model.rosters import ROSTERS, POSITIONS, ACCOUNT_TO_TEAM, ACCOUNT_TO_NAME
from model.fantasy_stats import load_player_games
from model.l3_player import fit_rate_model
pos = {aid: POSITIONS[t][p] for t, r in ROSTERS.items() for p, aid in r.items()}
df = load_player_games('data/pro_player_matches_2020_2026.csv',
                       set(ACCOUNT_TO_TEAM), since_ts=1704067200)
df['position'] = df['account_id'].map(pos)
res = fit_rate_model(df, 'kills', pos)
for pk in (1,2,3,4,5):
    rs=[v['rate'] for v in res.values() if v['position']==pk]
    print('%d 号位 平均击杀 %.2f  (n=%d 人)' % (pk, sum(rs)/len(rs), len(rs)))
"
```
预期：击杀率呈 **1 号位 > 2 号位 > 3 号位 > 4/5 号位** 的单调趋势。
**若 5 号位击杀高于 1 号位，说明号位映射错了，停下来查 `rosters.py`。**

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "feat: L3 层次泊松选手能力模型，按号位分层 + 重尾收缩"
```

---

### Task 7: L4-P1 Fantasy 分项产出矩阵

设计文档 §2.2 的口径提醒：TI15 Fantasy **选队不选人**，Core Duo / Support Duo 选的是队，
只有 Mid 槽是真·选人。因此本任务的产出要同时服务两种用法。
§4.3 的 A/B 分支未定 —— **两种口径都算，各出一份**。

**Files:**
- Create: `model/l4_fantasy.py`
- Create: `tests/test_l4_fantasy.py`

**Interfaces:**
- Consumes: `l3_player.fit_rate_model` 的输出、`l2_predictions.json` 的每队系列赛数分布
- Produces: `player_matrix(rates, items) -> Dict[int, Dict[str, float]]`
- Produces: `slot_aggregate(matrix, rosters, slot) -> Dict[str, Dict[str, float]]`，`slot` ∈ `{"core","mid","support"}`
- Produces: `expected_slot_score(matrix, series_dist, branch) -> Dict[str, float]`，`branch` ∈ `{"A","B"}`

- [ ] **Step 1: 写失败的测试**

`tests/test_l4_fantasy.py`：
```python
import pytest
from model.l4_fantasy import player_matrix, slot_aggregate, expected_slot_score


RATES = {
    11: {"rate": 9.0, "se": 1.0, "position": 1},
    12: {"rate": 7.0, "se": 1.0, "position": 2},
    13: {"rate": 5.0, "se": 1.0, "position": 3},
    14: {"rate": 3.0, "se": 1.0, "position": 4},
    15: {"rate": 2.0, "se": 1.0, "position": 5},
}
ROSTER = {"T1": {"c": 11, "m": 12, "o": 13, "s4": 14, "s5": 15}}
POS = {11: 1, 12: 2, 13: 3, 14: 4, 15: 5}


def test_player_matrix_has_one_row_per_player_per_item():
    m = player_matrix({"kills": RATES}, items=["kills"])
    assert set(m) == set(RATES)
    assert m[11]["kills"] == pytest.approx(9.0)


def test_core_slot_averages_the_two_cores_not_all_five():
    """Core Duo 计分只算该队两名核心（1、2 号位）。"""
    m = player_matrix({"kills": RATES}, items=["kills"])
    agg = slot_aggregate(m, ROSTER, POS, slot="core")
    assert agg["T1"]["kills"] == pytest.approx((9.0 + 7.0) / 2)


def test_support_slot_averages_positions_four_and_five():
    m = player_matrix({"kills": RATES}, items=["kills"])
    agg = slot_aggregate(m, ROSTER, POS, slot="support")
    assert agg["T1"]["kills"] == pytest.approx((3.0 + 2.0) / 2)


def test_mid_slot_is_a_single_player_not_averaged():
    m = player_matrix({"kills": RATES}, items=["kills"])
    agg = slot_aggregate(m, ROSTER, POS, slot="mid")
    assert agg["T1"]["kills"] == pytest.approx(7.0)


def test_branch_b_penalises_early_exit_far_more_than_branch_a():
    """§4.3：分支 B 缺席阶段记 0，深度压倒能力；分支 A 只取最好系列赛。"""
    m = {"T1": {"kills": 6.0}}
    deep = {"T1": {"group": 5, "playoff": 4}}
    early = {"T1": {"group": 5, "playoff": 0}}
    a_deep = expected_slot_score(m, deep, branch="A")["T1"]
    a_early = expected_slot_score(m, early, branch="A")["T1"]
    b_deep = expected_slot_score(m, deep, branch="B")["T1"]
    b_early = expected_slot_score(m, early, branch="B")["T1"]
    assert (b_deep - b_early) > (a_deep - a_early) * 2


def test_max_order_statistic_grows_slowly_not_logarithmically_in_scale():
    """护栏：取最大值随系列赛数增长**极慢**。

    早期 plan 用 `per_game * (1 + ln(n))` 近似，实测相对误差 43%→130%
    且随 n 放大（真实 2→9 场只涨约 17%，该近似涨 89%），会系统性
    高估深跑收益，直接污染 A/B 分支对比。必须用真实模拟。
    """
    m = {"T1": {"k": 14.67}}
    s2 = expected_slot_score(m, {"T1": {"g": 2}}, branch="A", per_game_sd=4.72)["T1"]
    s9 = expected_slot_score(m, {"T1": {"g": 9}}, branch="A", per_game_sd=4.72)["T1"]
    assert s9 > s2, "系列赛越多，取到的最好成绩应更高"
    assert (s9 - s2) / s2 < 0.35, "增幅必须远小于 log 近似的 89%"


def test_calibrates_to_ti14_measured_distribution():
    """用 TI14 实测口径（场均 14.67、单局 sd 4.72）校准，
    5 个系列赛的取最大值期望应落在 19 分附近（06-fantasy-rules.md）。"""
    m = {"T1": {"k": 14.67}}
    got = expected_slot_score(m, {"T1": {"g": 5}}, branch="A", per_game_sd=4.72)["T1"]
    assert 18.0 < got < 21.0


def test_unknown_branch_raises():
    with pytest.raises(ValueError):
        expected_slot_score({"T1": {"kills": 1.0}}, {"T1": {"group": 1}}, branch="C")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_l4_fantasy.py -q`
Expected: FAIL — `No module named 'model.l4_fantasy'`

- [ ] **Step 3: 实现 l4_fantasy.py**

```python
"""L4-P1：Fantasy 分项产出矩阵。

设计文档 §4.3：基础系数服务端下发、静态取不到，因此**不出绝对总分**，
只出「选手 × 计分项」的每局期望，由使用者按自己装的徽记取用。

TI15 Fantasy 选队不选人：Core Duo / Support Duo 是队级（两人取平均），
Mid 是单人。三种口径都要能出。
"""
SLOT_POSITIONS = {"core": (1, 2), "mid": (2,), "support": (4, 5)}


def player_matrix(rates_by_item, items):
    """{item: {account: {...}}} → {account: {item: rate}}"""
    out = {}
    for item in items:
        for acct, v in rates_by_item[item].items():
            out.setdefault(acct, {})[item] = float(v["rate"])
    return out


def slot_aggregate(matrix, rosters, positions, slot):
    """按槽位把选手矩阵聚合到队级。mid 槽不做平均，直接取该队 2 号位。"""
    if slot not in SLOT_POSITIONS:
        raise ValueError("未知槽位 %r" % slot)
    want = SLOT_POSITIONS[slot]
    out = {}
    for team, roster in rosters.items():
        members = [a for a in roster.values()
                   if positions.get(a) in want and a in matrix]
        if not members:
            continue
        items = set().union(*(matrix[a].keys() for a in members))
        out[team] = {it: sum(matrix[a].get(it, 0.0) for a in members) / len(members)
                     for it in items}
    return out


import numpy as np

TI15_Q_THREE_GAME = 0.4386   # BO3 打满三局的比例（TI14 实测 25/57）
TI14_PER_GAME_SD = 4.72      # 单局 fantasy 分标准差（06-fantasy-rules.md）


def _best_series(rng, mu, sd, n_series):
    """模拟 n_series 个系列赛，每个取最高两局的均值，返回其中最好的那个。

    不能用解析近似：取最大值是顺序统计量，随 n 增长极慢。
    早期用 `1 + ln(n)` 近似，实测相对误差 43%→130% 且随 n 放大。
    """
    n_series = int(n_series)
    if n_series <= 0:
        return 0.0
    best = -np.inf
    for _ in range(n_series):
        n_games = 2 + int(rng.random() < TI15_Q_THREE_GAME)
        g = np.sort(rng.normal(mu, sd, size=n_games))[::-1][:2]
        best = max(best, float(g.mean()))
    return best


def expected_slot_score(matrix, series_dist, branch,
                        per_game_sd=TI14_PER_GAME_SD, n_sim=4000, seed=20260802):
    """把每局速率与「打多少系列赛」合成一个期望分。

    branch A：全程只取最好的一个系列赛 —— 多打只是多抽几次，边际递减
    branch B：分阶段计分、缺席阶段记 0 —— 缺席直接损失整段
    两个分支的量化对比见设计文档 §4.3。

    series_dist 的值可以是小数（模拟出来的期望系列赛数），
    按概率取上下整，避免直接截断丢掉半场的信息。
    """
    if branch not in ("A", "B"):
        raise ValueError("branch 必须是 'A' 或 'B'")

    rng = np.random.default_rng(seed)
    out = {}
    for key, items in matrix.items():
        mu = float(sum(items.values()))
        stages = series_dist.get(key, {})
        total = 0.0
        for _ in range(n_sim):
            def draw(v):
                lo = int(np.floor(v))
                return lo + int(rng.random() < (v - lo))
            if branch == "A":
                total += _best_series(rng, mu, per_game_sd,
                                      draw(sum(stages.values())))
            else:
                total += sum(_best_series(rng, mu, per_game_sd, draw(v))
                             for v in stages.values())
        out[key] = total / n_sim
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_l4_fantasy.py -q`
Expected: `6 passed`

- [ ] **Step 5: 让 l2_simulate.py 额外导出每队分阶段系列赛数**

在 `l2_simulate.py` 的统计区加：
```python
series_group = np.zeros(n)      # 瑞士轮 + 附加轮系列赛数
series_playoff = np.zeros(n)    # 主赛事系列赛数
```
在 `run_one` 返回值里带上每队两段的系列赛计数，累加后写进 `l2_predictions.json` 的 `series_dist` 字段，形如
`{"Team Falcons": {"group": 5.4, "playoff": 2.1}, ...}`（期望值）。

- [ ] **Step 6: 产出 P1 三张表**

```bash
python3 -c "
import json, sys; sys.path.insert(0,'.')
# 分别导出：选手级矩阵、Core 槽队级、Support 槽队级、Mid 槽单人
# 并对 A/B 两个分支各出一份期望分
" > /dev/null
python3 model/l4_fantasy_report.py --out reports/p1_fantasy_matrix.json
```
（`l4_fantasy_report.py` 为本步新建的编排脚本，把上面的接口串起来并落盘。）

产出必须包含一行说明：**「蓝池 6 项中 Watcher/Lotus 取不到，Support 槽预测结构性偏弱」**——
这是 §6 R4 的已知缺口，不能在报告里静默掉。

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "feat: L4-P1 Fantasy 分项矩阵，支持 core/mid/support 三口径与 A/B 双分支"
```

---

### Task 8: L4-P3/P4 选手排名与个人数据预测

这两项是 L3 的直接副产品（设计文档 §3-L4），边际成本最低，但要把不确定区间带出来。

**Files:**
- Create: `model/l4_players.py`
- Create: `tests/test_l4_players.py`

**Interfaces:**
- Produces: `rank_players(rates, by_position=True) -> List[Dict]`，含 `rank, account_id, name, team, position, rate, lo, hi`
- Produces: `predict_player_stats(rates_by_item, items) -> Dict[int, Dict[str, Tuple[float,float,float]]]`（值为 `(均值, lo, hi)`）

- [ ] **Step 1: 写失败的测试**

`tests/test_l4_players.py`：
```python
import pytest
from model.l4_players import rank_players, predict_player_stats

RATES = {
    1: {"rate": 9.0, "se": 0.5, "position": 1, "n_games": 100},
    2: {"rate": 8.0, "se": 2.5, "position": 1, "n_games": 6},
    3: {"rate": 4.0, "se": 0.4, "position": 5, "n_games": 90},
}
META = {1: ("Yatoro", "Team Spirit"), 2: ("Rookie", "HULIGANI"), 3: ("rue", "Team Spirit")}


def test_ranking_is_within_position_when_requested():
    out = rank_players(RATES, META, by_position=True)
    pos1 = [r for r in out if r["position"] == 1]
    assert [r["account_id"] for r in pos1] == [1, 2]
    assert pos1[0]["rank"] == 1 and pos1[1]["rank"] == 2
    assert [r["rank"] for r in out if r["position"] == 5] == [1]


def test_interval_is_wider_for_small_sample_players():
    out = {r["account_id"]: r for r in rank_players(RATES, META, by_position=True)}
    assert (out[2]["hi"] - out[2]["lo"]) > (out[1]["hi"] - out[1]["lo"])


def test_predict_stats_returns_mean_and_bounds_in_order():
    got = predict_player_stats({"kills": RATES}, ["kills"])
    mean, lo, hi = got[1]["kills"]
    assert lo < mean < hi


def test_missing_meta_falls_back_without_crashing():
    out = rank_players(RATES, {}, by_position=False)
    assert all(r["name"] for r in out)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_l4_players.py -q`
Expected: FAIL — `No module named 'model.l4_players'`

- [ ] **Step 3: 实现 l4_players.py**

```python
"""L4-P3/P4：选手实力排名与个人数据预测。

两者都是 L3 后验的直接读出。关键是把不确定区间带出来 ——
HULIGANI 只有 109 场样本，它的选手区间必须明显比 Liquid 的宽。
"""
Z95 = 1.959964


def _interval(rate, se):
    return rate - Z95 * se, rate + Z95 * se


def rank_players(rates, meta, by_position=True):
    """meta: {account_id: (name, team)}。缺失时回退为 account_id 字符串。"""
    rows = []
    for acct, v in rates.items():
        name, team = meta.get(acct, (str(acct), "?"))
        lo, hi = _interval(v["rate"], v["se"])
        rows.append({"account_id": acct, "name": name, "team": team,
                     "position": v["position"], "rate": v["rate"],
                     "se": v["se"], "lo": lo, "hi": hi,
                     "n_games": v.get("n_games", 0)})
    if by_position:
        out = []
        for pos in sorted({r["position"] for r in rows}):
            grp = sorted([r for r in rows if r["position"] == pos],
                         key=lambda r: -r["rate"])
            for i, r in enumerate(grp, 1):
                r["rank"] = i
            out += grp
        return out
    rows.sort(key=lambda r: -r["rate"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def predict_player_stats(rates_by_item, items):
    out = {}
    for item in items:
        for acct, v in rates_by_item[item].items():
            lo, hi = _interval(v["rate"], v["se"])
            out.setdefault(acct, {})[item] = (v["rate"], lo, hi)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_l4_players.py -q`
Expected: `4 passed`

- [ ] **Step 5: 出真实排名并人工抽查**

```bash
python3 model/l4_players_report.py --out reports/p3_p4_players.md
```
抽查：**Yatoro（Team Spirit 1 号位）应在 1 号位榜前列**；HULIGANI 的选手区间应明显更宽。
若排名结果与圈内共识严重不符，先查号位映射与 as-of 对齐，不要直接调参迎合直觉。

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "feat: L4-P3/P4 选手排名与个人数据预测，带 95% 区间"
```

---

### Task 9: L4-P2 极值题

设计文档 §4.4：**用经验频率 + 层次平滑，不用 EVT/GPD**。
GPD 在我们的阈值范围属于过度工程，且引入「阈值选择」这个新的过拟合来源。
仅当某道题的阈值超出历史观测范围时才回退到 GPD。

**Files:**
- Create: `model/l4_extremes.py`
- Create: `tests/test_l4_extremes.py`

**Interfaces:**
- Produces: `threshold_prob(samples, threshold, n_games, smooth=0.5) -> float` —— 全赛事至少出现一次的概率
- Produces: `who_leads(rates, n_games_by_player, item, n_sim) -> Dict[int,float]`
- Produces: `needs_gpd(samples, threshold) -> bool`

- [ ] **Step 1: 写失败的测试**

`tests/test_l4_extremes.py`：
```python
import numpy as np
import pytest
from model.l4_extremes import threshold_prob, who_leads, needs_gpd


def test_threshold_prob_matches_one_minus_miss_all():
    samples = [10] * 90 + [30] * 10          # 单局超过 25 的经验频率 = 0.1
    p = threshold_prob(samples, threshold=25, n_games=10, smooth=0.0)
    assert p == pytest.approx(1 - 0.9 ** 10)


def test_threshold_prob_grows_with_more_games():
    s = [10] * 99 + [30]
    assert threshold_prob(s, 25, 50) > threshold_prob(s, 25, 10)


def test_smoothing_keeps_zero_count_thresholds_off_zero():
    """经验频率为 0 时不应输出 0 概率 —— 层次平滑的意义所在。"""
    s = [10] * 200
    assert 0.0 < threshold_prob(s, 25, n_games=145, smooth=0.5) < 0.2


def test_needs_gpd_only_when_threshold_exceeds_observed_range():
    s = [1, 5, 12, 26, 31]
    assert needs_gpd(s, threshold=20) is False
    assert needs_gpd(s, threshold=40) is True


def test_who_leads_probabilities_sum_to_one():
    rates = {1: 9.0, 2: 7.0, 3: 5.0}
    games = {1: 20, 2: 20, 3: 20}
    out = who_leads(rates, games, n_sim=3000, seed=0)
    assert abs(sum(out.values()) - 1.0) < 1e-9
    assert out[1] > out[2] > out[3]


def test_who_leads_favours_players_with_more_games():
    rates = {1: 6.0, 2: 6.0}
    out = who_leads(rates, {1: 30, 2: 6}, n_sim=3000, seed=1)
    assert out[1] > out[2], "同等能力下，打得多的更可能拿到全场之最"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_l4_extremes.py -q`
Expected: FAIL — `No module named 'model.l4_extremes'`

- [ ] **Step 3: 实现 l4_extremes.py**

```python
"""L4-P2：极值题。

设计文档 §4.4：经验频率 + 层次平滑优于拟合 GPD ——
26 杀约在 99.5 分位，阈值附近有几十上百个真实观测，
此时经验频率更稳，而 GPD 还引入「阈值怎么选」这个新的过拟合来源。
"""
import numpy as np


def threshold_prob(samples, threshold, n_games, smooth=0.5):
    """全赛事 n_games 局中，至少出现一次「单局 ≥ threshold」的概率。

    smooth 为拉普拉斯平滑量：经验计数为 0 时避免输出恰好 0。
    """
    s = np.asarray(samples, dtype=float)
    if s.size == 0:
        raise ValueError("samples 不能为空")
    hits = float((s >= threshold).sum())
    p_game = (hits + smooth) / (s.size + 2 * smooth) if smooth > 0 else hits / s.size
    p_game = min(max(p_game, 0.0), 1.0)
    return float(1.0 - (1.0 - p_game) ** max(int(n_games), 0))


def needs_gpd(samples, threshold):
    """阈值是否超出历史观测范围 —— 只有这种情况才该回退到 GPD。"""
    return float(threshold) > float(np.max(np.asarray(samples, dtype=float)))


def who_leads(rates, n_games_by_player, n_sim=20000, seed=0):
    """「谁打出全场最高值」的概率。

    注意：这是身份题，本质是「哪支队走得深」的衍生题 ——
    局数方差远大于场均方差（05-applied-design.md）。
    """
    rng = np.random.default_rng(seed)
    accts = list(rates)
    wins = {a: 0 for a in accts}
    for _ in range(n_sim):
        best_val, best_a = -1.0, None
        for a in accts:
            g = int(n_games_by_player.get(a, 0))
            if g <= 0:
                continue
            v = rng.poisson(rates[a], size=g).max()
            # 同分时随机打破平局，避免系统性偏向遍历顺序靠前的选手
            v = v + rng.random() * 1e-6
            if v > best_val:
                best_val, best_a = v, a
        if best_a is not None:
            wins[best_a] += 1
    tot = sum(wins.values()) or 1
    return {a: wins[a] / tot for a in accts}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_l4_extremes.py -q`
Expected: `6 passed`

- [ ] **Step 5: 用 TI14 做回溯校验**

```bash
python3 model/l4_extremes_report.py --backtest-ti14
```
拿 TI14 之前的数据预测 TI14 的极值，与 TI14 实际发生的比对。
**这是 P2 唯一能做的诚实检验**，结果必须写进报告，哪怕不好看。

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "feat: L4-P2 极值题，经验频率+层次平滑，含 TI14 回溯校验"
```

---

### Task 10: L5 赛后评分工具

设计文档 §4.5：TI15 会打 59 场系列赛 / 约 145 局，**场级预测有上百个观测——这是唯一有统计功效的检验场**。
对照标准学 538 的 `spi_matches.csv`：赛前概率与赛后结果放在同一张表公开。

**Files:**
- Create: `model/score.py`
- Create: `tests/test_score.py`
- Create: `reports/ti15_matches.csv`（赛前生成，赛后填结果）

**Interfaces:**
- Produces: `brier(probs, outcomes) -> float`
- Produces: `log_loss(probs, outcomes) -> float`
- Produces: `calibration_bins(probs, outcomes, n_bins=10) -> List[Dict]`
- Produces: `score_report(csv_path) -> Dict`

- [ ] **Step 1: 写失败的测试**

`tests/test_score.py`：
```python
import pytest
from model.score import brier, log_loss, calibration_bins


def test_brier_is_zero_for_perfect_and_one_for_inverted():
    assert brier([1.0, 0.0], [1, 0]) == pytest.approx(0.0)
    assert brier([0.0, 1.0], [1, 0]) == pytest.approx(1.0)


def test_brier_of_coinflip_is_quarter():
    assert brier([0.5] * 4, [1, 0, 1, 0]) == pytest.approx(0.25)


def test_log_loss_clips_and_stays_finite():
    assert log_loss([0.0], [1]) < 40.0


def test_calibration_bins_group_and_report_counts():
    probs = [0.05] * 10 + [0.95] * 10
    out = [1] * 0 + [0] * 10 + [1] * 10
    bins = calibration_bins(probs, out, n_bins=10)
    filled = [b for b in bins if b["n"] > 0]
    assert len(filled) == 2
    assert filled[0]["observed"] == pytest.approx(0.0)
    assert filled[-1]["observed"] == pytest.approx(1.0)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        brier([0.5], [1, 0])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_score.py -q`
Expected: FAIL — `No module named 'model.score'`

- [ ] **Step 3: 实现 score.py**

```python
"""L5：赛后评分与校准。

健康区间（设计文档 §5）：Brier 0.21–0.24，对应约 63–67% 准确率。
高于 0.25 说明比抛硬币还差；低于 0.20 要先怀疑泄漏而不是庆祝。
"""
import math

EPS = 1e-15


def _check(probs, outcomes):
    if len(probs) != len(outcomes):
        raise ValueError("probs 与 outcomes 长度必须一致")
    if not probs:
        raise ValueError("不能为空")


def brier(probs, outcomes):
    _check(probs, outcomes)
    return sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / len(probs)


def log_loss(probs, outcomes):
    _check(probs, outcomes)
    tot = 0.0
    for p, y in zip(probs, outcomes):
        p = min(max(p, EPS), 1 - EPS)
        tot += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return tot / len(probs)


def calibration_bins(probs, outcomes, n_bins=10):
    _check(probs, outcomes)
    bins = [{"lo": i / n_bins, "hi": (i + 1) / n_bins,
             "n": 0, "predicted": 0.0, "observed": 0.0} for i in range(n_bins)]
    acc = [[0.0, 0] for _ in range(n_bins)]
    for p, y in zip(probs, outcomes):
        i = min(int(p * n_bins), n_bins - 1)
        bins[i]["n"] += 1
        bins[i]["predicted"] += p
        acc[i][0] += y
        acc[i][1] += 1
    for i, b in enumerate(bins):
        if b["n"]:
            b["predicted"] /= b["n"]
            b["observed"] = acc[i][0] / acc[i][1]
    return bins
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_score.py -q`
Expected: `5 passed`

- [ ] **Step 5: 生成赛前对阵概率表**

```bash
python3 model/emit_match_table.py --out reports/ti15_matches.csv
```
表头：`stage,team_a,team_b,p_a_wins_series,frozen_at,result_a_wins`
赛前只填前五列，`result_a_wins` 留空；赛后回填。**这张表就是我们的 `spi_matches.csv`。**

- [ ] **Step 6: 冻结并提交**

```bash
python3 -c "
from model.freeze import freeze_predictions
print(freeze_predictions('reports/ti15_matches.csv','frozen','v3-matchtable')['sha256'][:16])"
python3 -m pytest -q
git add -A && git commit -m "feat: L5 赛后评分工具与赛前对阵概率表，冻结存证"
```

---

## Self-Review

**1. Spec coverage**

| 设计文档要求 | 对应任务 |
|---|---|
| §2.1 T1–T4 战队层面 | 已实现（v2 §9.5）；Task 3/4 提升保真度，Task 2 融合市场 |
| §2.2 P1 Fantasy 矩阵 | Task 5 + Task 7 |
| §2.2 P2 极值 | Task 9 |
| §2.2 P3 排名 / P4 个人数据 | Task 8 |
| §3 L0/L1/L2 | 已实现 |
| §3 L3 | Task 6 |
| §3 L4 | Task 7/8/9 |
| §3 L5 | Task 1 + Task 10 |
| §4.1 不做打分卡 | 已在 v2 §9.2 以数据层方案落实 |
| §4.2 市场融合 | Task 2 |
| §4.3 A/B 双分支 | Task 7 Step 3（两分支都算） |
| §4.4 不用 GPD | Task 9（`needs_gpd` 明确边界） |
| §4.5 冻结 + Brier | Task 1 + Task 10 |
| §5 护栏 | Global Constraints + Task 6 Step 5 / Task 8 Step 5 的健全性检查 |
| §6 R4 蓝池缺口 | Task 7 Step 6 强制在报告中声明 |
| §8 验收标准 1 可复现 | 固定种子 + 全部脚本化 |
| §8 验收标准 2 无泄漏 | 时间切分已实现；Global Constraints 禁随机 CV |
| §8 验收标准 3 概率自洽 | Task 3 Step 6 / Task 4 Step 7 校验 |
| §8 验收标准 4 对齐完整 | 已实现（v2 §9.2 表） |
| §8 验收标准 5 已冻结 | Task 1 Step 7、Task 2 Step 9、Task 10 Step 6 |
| §8 验收标准 6 诚实标注 | Task 2 Step 5（赔率 null 不编造）、Task 7 Step 6 |
| §8 验收标准 7 赛后可评 | Task 10 |
| §9.8 A1/A2 | Task 3 |
| §9.8 A3/A5 | Task 4 |
| §9.8 A4 | Task 3（`_pair_by_score` 覆盖附加轮排位配对） |
| §9.8 A6 | Task 2 |

**无未覆盖项。**

**2. 未纳入本计划的设计文档内容（有意为之）**

- §6 需用户客户端截图的 5 项：**这些是外部输入，不是可实施任务**。Task 2 Step 5 与 Task 7 都设计成「拿不到也能跑」，拿到后只需替换常量。
- §7 排期表已被本计划取代。

**3. 已知的执行顺序约束**

Task 1 必须最先（建目录与 git，否则后续 commit 无处可提）。
Task 5 → Task 6 → Task 7/8/9（数据层在前）。
Task 2/3/4 相互独立，可并行。
Task 10 可随时做，但 Step 5 依赖 Task 3/4 的最终模拟。
