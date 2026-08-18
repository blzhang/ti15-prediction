# 主赛事对阵表编辑器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把抄作业页那张主赛事对阵表从一份写死的推荐填法，改成可以在图上直接点的编辑器——你钉住几格，剩下 13 格由页面在 16384 种自洽填法里重搜最优，期望答对数实时更新。

**Architecture:** 一份自洽填法 ↔ 一个 14 位整数（每场二选一）。展开函数 `expand(qf, bits)` 在 Python 与 JS 各实现一份，用 node 跑的 pytest 逐位比对 16384 种展开把两边钉死。算分是纯查表（`winners[阶段][队]` 是与填法无关的边缘概率），所以整个编辑器是纯前端、无后端、无 cookie。SVG 由构建时的 Python 渲染出模型最优那份当无 JS 回退，JS 只改其中的文本与属性节点。

**Tech Stack:** Python 3 + numpy/scipy（模型层）、无框架 ES5 JavaScript（前端，与 `site/assets_src/picker.js` 同风格）、pytest（测试）、node（仅用于跨语言对照测试，非运行时依赖）

## Global Constraints

- 设计文档：`docs/superpowers/specs/2026-08-18-bracket-editor-design.md`。位定义表在「决定一」，任何改动必须同步两侧实现。
- **不修改 `model/bracket.py` 与 `model/l2_simulate.py`**（`model/l6_playoffs.py` 模块注释里的既有纪律）。
- **卡片 PNG 渲染路径（`bracket_svg.render(pl, "card")`）的输出必须逐字节不变。**
- 前端 JS 用 ES5 语法，无构建步骤、无依赖，与 `site/assets_src/picker.js` 一致（`var`、`function`，不用 `let`/箭头函数/模板串）。
- 交互只在视口 ≥ **940px** 时启用，断点复用 `site/assets_src/style.css:387` 已有的那一个，不引入第二个阈值。
- 所有新增注释与文案用中文，与仓库现有风格一致。
- 每个任务结束时提交，提交信息用中文、首行 `<type>: <说明>`（见 `git log`）。

---

## File Structure

| 文件 | 责任 | 本次动作 |
|---|---|---|
| `model/l6_playoffs.py` | 八强前瞻模型；本次新增 bit 编码的权威实现 | 修改 |
| `tests/test_bracket_bits.py` | bit 编码的回归测试，含 Python↔JS 对照 | 新建 |
| `site/homework.py` | 抄作业页渲染；本次新增前端数据契约 `bracket_data()` | 修改 |
| `tests/test_homework_bracket_data.py` | `bracket_data()` 的形状与自洽测试 | 新建 |
| `site/bracket_svg.py` | 对阵表 SVG；本次新增 `interactive` 参数 | 修改 |
| `tests/test_bracket_svg.py` | 交互版含热区与 id、卡片版不受污染 | 新建 |
| `site/assets_src/bracket.js` | 编辑器全部前端逻辑（展开、算分、重搜、渲染、交互、分享） | 新建 |
| `site/assets_src/style.css` | 热区 hover / 钉住态 / 窄屏隐藏交互 UI | 修改 |
| `site/pages.py` | 页面组装；挂 `bracket.js` 与初始化数据 | 修改 |

`bracket.js` 会长到约 350 行。不拆分：它是一个单元（一张图的编辑器），拆成"逻辑/渲染/交互"三个文件会引入三个全局符号和一套加载顺序约定，而站点没有打包步骤——`picker.js` 190 行单文件是既有先例。

---

### Task 1: Python 侧 bit 编码的权威实现

把 `best_bracket` 的 10 层嵌套循环换成"遍历 0..16383 并按位展开"。前端要的正是这个展开函数；两边各写一份路径规则迟早会漂移，而漂移的表现是页面静静印出一个跟模型对不上的期望值。

**Files:**
- Modify: `model/l6_playoffs.py`（在 `best_bracket` 上方新增 `BIT_STAGE`/`N_BITS`/`expand`，重写 `best_bracket` 的枚举部分）
- Test: `tests/test_bracket_bits.py`（新建）

**Interfaces:**
- Consumes: `model/l6_playoffs.py` 现有的 `ALL_STAGES`、`enumerate_bracket`、`probs_from_theta`
- Produces:
  - `BIT_STAGE: tuple[str, ...]` — 14 项，bit 索引 → 阶段名
  - `N_BITS: int` — 14
  - `expand(qf, bits) -> dict[str, T]` — `qf` 是 4 个二元组，元素类型任意（索引或队名，原样返回）；返回 `{阶段名: 该阶段你选的那一方}`
  - `best_bracket(...)` 的 `stats` 新增 `"pick_bits": int`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_bracket_bits.py`：

```python
"""对阵表 bit 编码的回归测试。

守的是一件事：「一份自洽填法 ↔ 一个 14 位整数」这个对应关系。
Python 与前端 site/assets_src/bracket.js 各有一份实现，两份必须逐位一致——
漂移的表现不是崩溃，是抄作业页静静印出一个跟模型对不上的期望答对数。

位定义表在 docs/superpowers/specs/2026-08-18-bracket-editor-design.md 决定一。
"""
import itertools

import numpy as np

from model.l6_playoffs import (
    ALL_STAGES, BIT_STAGE, N_BITS, best_bracket, enumerate_bracket, expand,
    probs_from_theta,
)

THETA = [1.20, 1.00, 0.95, 0.90, 0.85, 0.60, 0.40, 0.10]
QF = [(0, 7), (1, 6), (2, 5), (3, 4)]


def _winners(theta=THETA):
    th = np.repeat(np.asarray(theta, float)[None, :], 1, axis=0)
    _, p3, p5 = probs_from_theta(th)
    _, _, winners = enumerate_bracket(QF, p3, p5, 1)
    return {s: {t: float(v[0]) for t, v in d.items()} for s, d in winners.items()}


def _assert_coherent(pick, qf):
    """填进后面几轮的队，必须是自己在前面几轮推上去的。

    与 tests/test_l6_playoffs.py:test_最优填法本身是自洽的 是同一套检查——
    那边只查最优那一份，这里查全部 16384 份。
    """
    w = [pick["UBQF%d" % (k + 1)] for k in range(4)]
    l = [qf[k][0] if w[k] == qf[k][1] else qf[k][1] for k in range(4)]
    for k in range(4):
        assert w[k] in qf[k]
    assert pick["UBSF1"] in (w[0], w[1])
    assert pick["UBSF2"] in (w[2], w[3])
    sf1_l = w[0] if pick["UBSF1"] == w[1] else w[1]
    sf2_l = w[2] if pick["UBSF2"] == w[3] else w[3]
    assert pick["LBR1-1"] in (l[0], l[1])
    assert pick["LBR1-2"] in (l[2], l[3])
    # 败者组交叉：败2上 = 败1上胜者 vs F 的败者；败2下 = 败1下胜者 vs E 的败者
    assert pick["LBQF-1"] in (pick["LBR1-1"], sf2_l)
    assert pick["LBQF-2"] in (pick["LBR1-2"], sf1_l)
    assert pick["LBSF"] in (pick["LBQF-1"], pick["LBQF-2"])
    assert pick["UBF"] in (pick["UBSF1"], pick["UBSF2"])
    ubf_l = pick["UBSF1"] if pick["UBF"] == pick["UBSF2"] else pick["UBSF2"]
    assert pick["LBF"] in (pick["LBSF"], ubf_l)
    assert pick["GF"] in (pick["UBF"], pick["LBF"])


def test_全部_16384_种_bits_展开后都是自洽填法():
    """这是 bit 编码的立身之本：任何一个 14 位整数都对应一份能真的填进面板的填法。"""
    assert N_BITS == 14 and len(BIT_STAGE) == 14
    assert set(BIT_STAGE) == set(ALL_STAGES)
    for bits in range(1 << N_BITS):
        _assert_coherent(expand(QF, bits), QF)


def test_bits_与自洽填法一一对应():
    """双射。少一种说明有填法漏了，重复说明有填法被算了两次。

    重构前这条由「10 层嵌套循环恰好转 16384 圈」的计数断言守着；
    换成位展开后计数变成同义反复，所以改由这条实打实的双射检查接手。
    """
    seen = {}
    for bits in range(1 << N_BITS):
        key = tuple(expand(QF, bits)[st] for st in BIT_STAGE)
        assert key not in seen, "bits %d 与 %d 展开出同一份填法" % (bits, seen[key])
        seen[key] = bits
    assert len(seen) == 16384


def _reference_best_bracket(qf, winners):
    """重构前那 10 层嵌套循环的逐字搬运，只当参照用。

    留着它的理由：这次重构把「枚举全部自洽填法」从显式分支结构换成了位展开，
    两者等价是整个改动的赌注。参照实现让这个赌注变成一条会变红的断言，
    而不是一句「我检查过了」。
    """
    a1, b1 = qf[0]; a2, b2 = qf[1]; a3, b3 = qf[2]; a4, b4 = qf[3]
    best, best_sc, total, n = None, -1.0, 0.0, 0
    for m in itertools.product((0, 1), repeat=4):
        w = [a1 if m[0] == 0 else b1, a2 if m[1] == 0 else b2,
             a3 if m[2] == 0 else b3, a4 if m[3] == 0 else b4]
        l = [b1 if m[0] == 0 else a1, b2 if m[1] == 0 else a2,
             b3 if m[2] == 0 else a3, b4 if m[3] == 0 else a4]
        for e, f in itertools.product((0, 1), repeat=2):
            sf_w = [w[0] if e == 0 else w[1], w[2] if f == 0 else w[3]]
            sf_l = [w[1] if e == 0 else w[0], w[3] if f == 0 else w[2]]
            for r1, r2 in itertools.product((0, 1), repeat=2):
                lb1 = [l[0] if r1 == 0 else l[1], l[2] if r2 == 0 else l[3]]
                q1_opts = (lb1[0], sf_l[1])
                q2_opts = (lb1[1], sf_l[0])
                for c1, c2 in itertools.product((0, 1), repeat=2):
                    lb2 = [q1_opts[c1], q2_opts[c2]]
                    for v in (0, 1):
                        lb3 = lb2[v]
                        for g in (0, 1):
                            ubf_w, ubf_l = ((sf_w[0], sf_w[1]) if g == 0
                                            else (sf_w[1], sf_w[0]))
                            for lf in (0, 1):
                                lbf = lb3 if lf == 0 else ubf_l
                                for gf in (0, 1):
                                    champ = ubf_w if gf == 0 else lbf
                                    pick = {
                                        "UBQF1": w[0], "UBQF2": w[1],
                                        "UBQF3": w[2], "UBQF4": w[3],
                                        "UBSF1": sf_w[0], "UBSF2": sf_w[1],
                                        "LBR1-1": lb1[0], "LBR1-2": lb1[1],
                                        "LBQF-1": lb2[0], "LBQF-2": lb2[1],
                                        "LBSF": lb3, "UBF": ubf_w,
                                        "LBF": lbf, "GF": champ,
                                    }
                                    sc = sum(winners[st][pick[st]] for st in ALL_STAGES)
                                    total += sc
                                    n += 1
                                    if sc > best_sc:
                                        best_sc, best = sc, pick
    assert n == 16384
    return best, best_sc, total / n


def test_位展开枚举与重构前的嵌套循环给出同一个答案():
    """最优填法、期望答对数、随机基线三项都必须一致。"""
    teams = [str(i) for i in range(8)]
    w = _winners()
    ref_pick, ref_sc, ref_rand = _reference_best_bracket(QF, w)
    pick, _, stats = best_bracket(QF, w, teams)

    assert pick == {st: teams[t] for st, t in ref_pick.items()}
    assert stats["expected"] == ref_sc
    assert abs(stats["random"] - ref_rand) < 1e-12


def test_位展开在另一组实力下也与嵌套循环一致():
    """换一组实力再比一次——单点相等可能是巧合，两个不同的最优解不会都是巧合。"""
    teams = [str(i) for i in range(8)]
    w = _winners([0.10, 0.40, 0.60, 0.85, 0.90, 0.95, 1.00, 1.20])
    ref_pick, ref_sc, _ = _reference_best_bracket(QF, w)
    pick, _, stats = best_bracket(QF, w, teams)
    assert pick == {st: teams[t] for st, t in ref_pick.items()}
    assert stats["expected"] == ref_sc


def test_stats_里的_pick_bits_展开回同一份最优填法():
    """前端拿 pick_bits 当初始状态，它必须真的等于 pick。"""
    teams = [str(i) for i in range(8)]
    w = _winners()
    pick, _, stats = best_bracket(QF, w, teams)
    assert expand(QF, stats["pick_bits"]) == {st: teams.index(t) for st, t in pick.items()}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_bracket_bits.py -x`
Expected: FAIL，`ImportError: cannot import name 'BIT_STAGE' from 'model.l6_playoffs'`

- [ ] **Step 3: 实现 `expand` 与 bit 常量**

在 `model/l6_playoffs.py` 中 `def best_bracket` 这一行的**正上方**插入：

```python
# ---------------------------------------------------------------- bit 编码
# 一份自洽填法 = 一个 14 位整数，每一位是一场比赛的二选一，0 表示「上面那个候选」。
#
# 这是路径规则的**唯一权威实现**：抄作业页的前端编辑器要的正是同一个展开函数
# （site/assets_src/bracket.js 的 expand），两边各写一份迟早会漂移，
# 而漂移的表现不是崩溃，是页面静静印出一个跟本模块对不上的期望答对数。
# tests/test_bracket_bits.py 用 node 跑 JS 那一份，与本函数逐位比对 16384 种展开。
#
# 完整的位定义表：docs/superpowers/specs/2026-08-18-bracket-editor-design.md 决定一。
BIT_STAGE = ("UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2",
             "LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "UBF", "LBF", "GF")
N_BITS = len(BIT_STAGE)


def expand(qf, bits):
    """把 14 位整数展开成一份完整且自洽的填法 {阶段: 该阶段你选的那一方}。

    qf 的元素类型不限（队索引或队名都行，原样返回）——正是这一点让
    tests/test_bracket_bits.py 能拿同一份 qf 同时喂给 Python 和 JS 做对照。
    """
    b = [(bits >> k) & 1 for k in range(N_BITS)]
    w = [qf[k][b[k]] for k in range(4)]            # 四场八强的胜者
    l = [qf[k][1 - b[k]] for k in range(4)]        # 四场八强的败者
    e, f = b[4], b[5]
    sf_w = [w[e], w[2 + f]]                        # E / F 的胜者
    sf_l = [w[1 - e], w[3 - f]]                    # E / F 的败者
    lb1 = [l[b[6]], l[2 + b[7]]]                   # 败1上 / 败1下的胜者
    # 败者组交叉：败2上 = 败1上胜者 vs F 的败者；败2下 = 败1下胜者 vs E 的败者。
    # 这两行是整套规则里唯一容易写错的地方，改动前先看设计文档决定一那张表。
    lb2 = [(lb1[0], sf_l[1])[b[8]], (lb1[1], sf_l[0])[b[9]]]
    lb3 = lb2[b[10]]                               # 败3 的胜者
    ubf_w, ubf_l = sf_w[b[11]], sf_w[1 - b[11]]
    lbf = (lb3, ubf_l)[b[12]]                      # 败决的胜者
    champ = (ubf_w, lbf)[b[13]]
    return dict(zip(BIT_STAGE,
                    (w[0], w[1], w[2], w[3], sf_w[0], sf_w[1],
                     lb1[0], lb1[1], lb2[0], lb2[1], lb3, ubf_w, lbf, champ)))
```

- [ ] **Step 4: 用位展开重写 `best_bracket` 的枚举部分**

在 `best_bracket` 的 docstring 中，把这一段：

```
    自洽填法的数量：胜者组 A/B/C/D/E/F/G 各二选一 = 2^7；败者组 6 场各二选一
    = 2^6；总决赛二选一 = 2。合计 **2^14 = 16384** 种——可以穷举，不需要启发式。
```

替换为：

```
    自洽填法的数量：胜者组 A/B/C/D/E/F/G 各二选一 = 2^7；败者组 6 场各二选一
    = 2^6；总决赛二选一 = 2。合计 **2^14 = 16384** 种——可以穷举，不需要启发式。

    枚举方式是遍历 0..16383 并交给 expand() 按位展开。之所以不是显式嵌套循环
    （2026-08-18 前是 10 层嵌套），是因为抄作业页的前端编辑器需要同一个展开函数，
    而两边各写一份路径规则迟早会漂移。见 expand() 上方的说明。
```

然后把 `a1, b1 = qf[0]; ...` 那一行起、直到 `assert n == 16384, "自洽填法应恰好 16384 种，实为 %d" % n` 为止的整段枚举代码，替换为：

```python
    best_bits, best_sc, total = -1, -1.0, 0.0
    n = 1 << N_BITS
    for bits in range(n):
        pick = expand(qf, bits)
        sc = sum(winners[st][pick[st]] for st in ALL_STAGES)
        total += sc
        if sc > best_sc:
            best_sc, best_bits = sc, bits
    best = expand(qf, best_bits)
    # 这条断言在位展开下已是同义反复；真正守住「不多不少 16384 种自洽填法」的是
    # tests/test_bracket_bits.py 的双射检查。留着它只为让 stats 的口径一眼可见。
    assert n == 16384, "BIT_STAGE 被改成了 %d 位" % N_BITS
```

再把函数末尾的 return 中 stats 那一项：

```python
            {"expected": best_sc, "random": total / n, "greedy_upper": greedy,
             "n_brackets": n, "n_matches": len(ALL_STAGES)})
```

改为：

```python
            {"expected": best_sc, "random": total / n, "greedy_upper": greedy,
             "n_brackets": n, "n_matches": len(ALL_STAGES),
             # 前端编辑器的初始状态：这份最优填法对应的 14 位整数
             "pick_bits": best_bits})
```

- [ ] **Step 5: 运行新测试确认通过**

Run: `python3 -m pytest tests/test_bracket_bits.py -v`
Expected: PASS，5 passed（`test_js_的_expand...` 尚未存在，Task 5 才加）

- [ ] **Step 6: 运行既有测试确认没打破任何东西**

Run: `python3 -m pytest tests/test_l6_playoffs.py -v`
Expected: PASS，全部通过——尤其 `test_最优填法枚举恰好覆盖全部自洽填法`、`test_最优填法本身是自洽的`、`test_一边倒的实力下最优填法就是全押最强`

- [ ] **Step 7: 提交**

```bash
git add model/l6_playoffs.py tests/test_bracket_bits.py && git commit -m "refactor: 对阵表填法改用 14 位整数编码，前端要的就是这个展开函数

10 层嵌套循环换成遍历 0..16383 + expand() 按位展开，两者等价由参照实现对照测试钉死。
前端编辑器需要同一套路径规则，两边各写一份迟早漂移——而漂移的表现是页面静静印出
一个跟模型对不上的期望答对数，不会崩。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: 导出完整概率表与初始 bits

前端算分要查 `win_p[阶段][队]`，而现在只导出了每格 top4 且 `p > 0.005`——用户可以选到被截掉的那些队，查不到就会算成 0。

**Files:**
- Modify: `model/l6_playoffs.py:704`（`bracket_homework` 那个字典）
- Test: `tests/test_bracket_bits.py`（追加。需在文件顶部补 `import json`、`import os`、`import pytest`）

**Interfaces:**
- Consumes: Task 1 的 `best_bracket` stats 里的 `pick_bits`
- Produces: `reports/p8_playoffs.json` 的 `bracket_homework` 新增两项：
  - `win_p: {阶段: {队名: float}}` — 14×8 全表，融合口径
  - `pick_bits: int` — 模型最优填法对应的 14 位整数

- [ ] **Step 1: 写失败的测试**

在 `tests/test_bracket_bits.py` 末尾追加：

```python
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "p8_playoffs.json")


def _report():
    """读真实产物。测的就是**导出环节**——内存里的 winners 一直是全表，
    在序列化那一步被截断才是真正会发生的事故。"""
    if not os.path.exists(REPORT):
        pytest.skip("需要先跑 python3 model/l6_playoffs.py 生成产物")
    with open(REPORT) as fh:
        return json.load(fh)


def test_导出的_win_p_是全表而不是被截断的_top4():
    """前端算分靠查这张表，缺一支队就会把它算成 0 分。

    rows[].top 那份为了显示做了截断（top4 且 p>0.005），交互版必须用没截断的。
    """
    d = _report()["bracket_homework"]
    assert set(d["win_p"]) == set(ALL_STAGES)
    for st in ALL_STAGES:
        assert len(d["win_p"][st]) == 8, "%s 少了队：%s" % (st, sorted(d["win_p"][st]))
        assert abs(sum(d["win_p"][st].values()) - 1.0) < 1e-9, "%s 概率和不为 1" % st


def test_导出的_pick_bits_展开回同一份_pick():
    """前端拿它当初始状态。展不回去就意味着读者一进页面看到的填法与模型的不是同一份。"""
    r = _report()
    qf = [(m["a"], m["b"]) for m in r["ubqf"]]
    d = r["bracket_homework"]
    assert expand(qf, d["pick_bits"]) == d["pick"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_bracket_bits.py -k 导出 -v`
Expected: FAIL，`KeyError: 'win_p'`——现有产物里还没有这一项

- [ ] **Step 3: 在 `build()` 里序列化 `win_p` 与 `pick_bits`**

在 `model/l6_playoffs.py` 中，把 `"bracket_homework": {` 那个字典里的：

```python
            "pick": bracket_pick,
            "rows": bracket_rows,
            "stats": bracket_stats,
```

改为：

```python
            "pick": bracket_pick,
            "rows": bracket_rows,
            "stats": bracket_stats,
            # 抄作业页的前端编辑器要用的两项。
            # win_p 必须是**没截断**的全表：rows[].top 为了显示只留了 top4 且 p>0.005，
            # 而读者在编辑器里可以选到被截掉的那些队，查不到就会被算成 0 分。
            "win_p": {st: {teams[t]: p for t, p in win_blend[st].items()}
                      for st in ALL_STAGES},
            "pick_bits": bracket_stats["pick_bits"],
```

- [ ] **Step 4: 重新生成产物并核对**

Run:
```bash
python3 model/l6_playoffs.py
```
Expected: 正常打印八强对阵与建议填法，末行 `→ reports/p8_playoffs.json`

Run: `python3 -m pytest tests/test_bracket_bits.py -k 导出 -v`
Expected: PASS，2 passed——此时测的是刚生成的真实产物

- [ ] **Step 5: 确认站点仍能构建**

Run: `python3 site/build_site.py`
Expected: 正常结束，无异常

- [ ] **Step 6: 提交**

```bash
git add model/l6_playoffs.py tests/test_bracket_bits.py reports/p8_playoffs.json && git commit -m "feat: 导出逐场胜率全表与最优填法的 bits，供前端编辑器查表

rows[].top 那份为显示做了截断，读者在编辑器里能选到被截掉的队——查不到会被算成 0 分。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: 前端数据契约 `bracket_data()`

前端需要一个自包含的初始化对象。与 `homework.picker_data()` 对称：模型层只管产概率，页面层负责挑出前端要的那几项并压小。

**Files:**
- Modify: `site/homework.py`（在 `picker_data` 下方新增 `bracket_data`）
- Test: `tests/test_homework_bracket_data.py`（新建）

**Interfaces:**
- Consumes: `reports/p8_playoffs.json` 的 `bracket_homework`（`win_p`/`pick_bits`/`rows`）与 `ubqf`；`bracket_svg.SHORT`
- Produces: `homework.bracket_data(pl) -> dict`，形状：
  ```python
  {
    "qf": [[队名, 队名], ...],          # 4 项，顺序 = UBQF1..4，元素顺序 = bit 0/1
    "win_p": {阶段: {队名: float}},      # 14×8
    "bits": int,                         # 模型最优填法
    "short": {队名: 简称},               # 客户端里的队伍简称
    "meta": {阶段: {"panel": str, "cn": str, "time": str}},
    "stats": {"expected": float, "random": float},
  }
  ```
  不带 `greedy_upper`：它解释的是"为什么不能每场都挑赢面大的"，与你怎么填无关，
  只出现在服务端渲染的静态文案里，前端拿了也用不上。

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_homework_bracket_data.py`：

```python
"""抄作业页前端编辑器的数据契约测试。

守的是「页面拿到的东西够不够它自己算完一遍」——前端不再回头找服务端，
所以缺一项都会变成页面上一个静悄悄的 0 或空白。
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site"))
import homework  # noqa: E402

STAGES = ("UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2",
          "LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "UBF", "LBF", "GF")
TEAMS = ["Iron Wing", "Team Spirit", "TEAM VISION", "BoomBoys",
         "Team Liquid", "Team Yandex", "Nigma Galaxy", "Team Falcons"]


def _pl():
    """最小可用的 p8_playoffs.json 切片。"""
    qf = [("Iron Wing", "Team Spirit"), ("TEAM VISION", "BoomBoys"),
          ("Team Liquid", "Team Yandex"), ("Nigma Galaxy", "Team Falcons")]
    win_p = {st: {t: 1.0 / 8 for t in TEAMS} for st in STAGES}
    return {
        "ubqf": [{"stage": "UBQF%d" % (k + 1), "a": a, "b": b,
                  "time_cst": "8/20 %02d:00" % (10 + k * 3)}
                 for k, (a, b) in enumerate(qf)],
        "bracket_homework": {
            "pick": {st: TEAMS[0] for st in STAGES},
            "pick_bits": 0,
            "win_p": win_p,
            "rows": [{"stage": st, "cn": "第%s场" % st, "panel": st,
                      "time_cst": "8/2x", "pick": TEAMS[0], "p_pick": 0.125,
                      "top": []} for st in STAGES],
            "stats": {"expected": 4.2, "random": 1.75, "greedy_upper": 5.0,
                      "n_matches": 14, "n_brackets": 16384},
        },
    }


def test_qf_顺序与元素顺序就是_bit_的_0_1():
    """qf[k][0] 必须是 UBQF{k+1} 的 a——bit 取 0 时选中的正是它。"""
    d = homework.bracket_data(_pl())
    assert d["qf"] == [["Iron Wing", "Team Spirit"], ["TEAM VISION", "BoomBoys"],
                       ["Team Liquid", "Team Yandex"], ["Nigma Galaxy", "Team Falcons"]]


def test_win_p_是全表且每格八支队():
    d = homework.bracket_data(_pl())
    assert set(d["win_p"]) == set(STAGES)
    for st in STAGES:
        assert len(d["win_p"][st]) == 8, st


def test_每格都有面板编号与时间():
    """图上和卡片上都要印它们；缺了就会渲染出「undefined · undefined」。"""
    d = homework.bracket_data(_pl())
    assert set(d["meta"]) == set(STAGES)
    for st in STAGES:
        assert d["meta"][st]["panel"] and d["meta"][st]["cn"] and d["meta"][st]["time"]


def test_简称表覆盖全部八支队():
    """图上印的是客户端里的简称（IW / TSpirit / FLCN…），缺一支就会印出全名撑破格子。"""
    d = homework.bracket_data(_pl())
    for t in TEAMS:
        assert t in d["short"], t


def test_统计只带前端真的会用的两项():
    """greedy_upper 与填法无关，只出现在服务端渲染的静态文案里，不进前端。"""
    d = homework.bracket_data(_pl())
    assert d["stats"] == {"expected": 4.2, "random": 1.75}


def test_bits_原样带出():
    assert homework.bracket_data(_pl())["bits"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_homework_bracket_data.py -x`
Expected: FAIL，`AttributeError: module 'homework' has no attribute 'bracket_data'`

- [ ] **Step 3: 实现 `bracket_data`**

在 `site/homework.py` 的 `picker_data` 函数下方（`def elim_pitfalls` 上方）插入：

```python
def bracket_data(pl):
    """喂给主赛事对阵表编辑器的数据：一次性给全，前端不再回头找服务端。

    与 picker_data 对称。区别在于这道题不是分配问题而是路径问题，
    所以给的不是「每格每队的命中概率 + 一份预设」，而是
    「逐场胜率全表 + 八强对阵 + 一个 14 位整数的初始填法」——
    有这三样，前端就能自己在 16384 种自洽填法里重搜。

    qf 的元素顺序（a 在前）就是 bit 取 0 时选中的那一方，
    与 model/l6_playoffs.py 的 expand() 是同一个约定。
    """
    bh = pl["bracket_homework"]
    return {
        "qf": [[m["a"], m["b"]] for m in pl["ubqf"]],
        "win_p": bh["win_p"],
        "bits": bh["pick_bits"],
        "short": dict(bracket_svg.SHORT),
        "meta": {r["stage"]: {"panel": r["panel"], "cn": r["cn"],
                              "time": r["time_cst"]}
                 for r in bh["rows"]},
        # 只给前端真的会用的两项。greedy_upper 与填法无关（它解释的是「为什么不能
        # 每场都挑赢面大的」），留在服务端渲染的静态文案里。
        "stats": {"expected": bh["stats"]["expected"],
                  "random": bh["stats"]["random"]},
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_homework_bracket_data.py -v`
Expected: PASS，6 passed

- [ ] **Step 5: 提交**

```bash
git add site/homework.py tests/test_homework_bracket_data.py && git commit -m "feat: 抄作业页新增对阵表编辑器的数据契约 bracket_data

与 picker_data 对称：一次性给全逐场胜率全表、八强对阵、初始填法的 bits，
前端拿到就能自己重搜，不再回头找服务端。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: SVG 加热区与可更新节点

**Files:**
- Modify: `site/bracket_svg.py`（`render` 签名 + `box` 内部）
- Test: `tests/test_bracket_svg.py`（新建）

**Interfaces:**
- Consumes: Task 3 无依赖；只用 `bracket_svg` 现有的 `_layout`
- Produces: `bracket_svg.render(pl, theme="page", show_prob=True, interactive=False)`。
  `interactive=True` 时每格每行产出：
  - `<circle id="bk-{stage}-{side}-dot">`
  - `<text id="bk-{stage}-{side}-nm">`
  - `<text id="bk-{stage}-{side}-p">`（未选中那行文本为空，**元素照样存在**）
  - `<rect class="bkhit" data-stage="{stage}" data-side="{side}">`（在最上层）

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_bracket_svg.py`：

```python
"""对阵表 SVG 的渲染测试：交互版有热区、卡片版一个像素都不许变。"""
import os
import re
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site"))
import bracket_svg  # noqa: E402

STAGES = ("UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2",
          "LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "UBF", "LBF", "GF")
TEAMS = ["Iron Wing", "Team Spirit", "TEAM VISION", "BoomBoys",
         "Team Liquid", "Team Yandex", "Nigma Galaxy", "Team Falcons"]


def _pl():
    """最小 pl 切片：八强对阵 + 一份把每场都填成 UBQF 胜者的填法。"""
    qf = [("Iron Wing", "Team Spirit"), ("TEAM VISION", "BoomBoys"),
          ("Team Liquid", "Team Yandex"), ("Nigma Galaxy", "Team Falcons")]
    pick = {"UBQF1": "Iron Wing", "UBQF2": "TEAM VISION",
            "UBQF3": "Team Liquid", "UBQF4": "Nigma Galaxy",
            "UBSF1": "Iron Wing", "UBSF2": "Team Liquid", "UBF": "Iron Wing",
            "LBR1-1": "Team Spirit", "LBR1-2": "Team Yandex",
            "LBQF-1": "Team Spirit", "LBQF-2": "Team Yandex",
            "LBSF": "Team Spirit", "LBF": "Team Spirit", "GF": "Iron Wing"}
    return {
        "ubqf": [{"stage": "UBQF%d" % (k + 1), "a": a, "b": b} for k, (a, b) in enumerate(qf)],
        "bracket_homework": {
            "pick": pick,
            "rows": [{"stage": st, "p_pick": 0.5} for st in STAGES],
        },
    }


def test_交互版每格两行都有热区():
    svg = bracket_svg.render(_pl(), "page", interactive=True)
    assert svg.count('class="bkhit"') == 28, "14 格 × 2 行 = 28 个热区"
    for st in STAGES:
        assert 'data-stage="%s" data-side="0"' % st in svg
        assert 'data-stage="%s" data-side="1"' % st in svg


def test_交互版每行的队名圆点百分比都有稳定_id():
    """JS 只改这些节点的文本与属性，不重建 SVG——id 缺一个那一行就永远不刷新。"""
    svg = bracket_svg.render(_pl(), "page", interactive=True)
    for st in STAGES:
        for side in (0, 1):
            for kind in ("dot", "nm", "p"):
                assert 'id="bk-%s-%d-%s"' % (st, side, kind) in svg


def test_未选中那一行的百分比元素照样存在只是内容为空():
    """换选之后 JS 要把百分比挪到另一行。元素若不存在，JS 就得插节点——
    那等于把「只改属性」的约定破掉，也就没法保证不重排版式。"""
    svg = bracket_svg.render(_pl(), "page", interactive=True)
    # UBQF1 选的是 side 0（Iron Wing），所以 side 0 有数字、side 1 是空的
    on = re.search(r'<text id="bk-UBQF1-0-p"[^>]*>([^<]*)</text>', svg)
    off = re.search(r'<text id="bk-UBQF1-1-p"[^>]*>([^<]*)</text>', svg)
    assert on and on.group(1).endswith("%"), "选中那行该有百分比"
    assert off and off.group(1) == "", "未选中那行该是空的，但元素必须在" 


def test_卡片版没有任何交互痕迹():
    """长图是 PNG，热区与 id 对它毫无用处，只会让产物变大、diff 变脏。"""
    svg = bracket_svg.render(_pl(), "card")
    assert "bkhit" not in svg
    assert "id=\"bk-" not in svg


def test_不开交互时输出与开交互前完全一致():
    """默认参数不改变任何既有行为——卡片与无 JS 回退都依赖这一条。"""
    a = bracket_svg.render(_pl(), "page")
    b = bracket_svg.render(_pl(), "page", interactive=False)
    assert a == b
    assert "bkhit" not in a
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_bracket_svg.py -x`
Expected: FAIL，`TypeError: render() got an unexpected keyword argument 'interactive'`

- [ ] **Step 3: 改 `render` 签名与 `box`**

在 `site/bracket_svg.py` 中，把：

```python
def render(pl, theme="page", show_prob=True):
    c = PALETTE[theme]
```

改为：

```python
def render(pl, theme="page", show_prob=True, interactive=False):
    """interactive=True 时给每一行加透明热区与稳定 id，供 site/assets_src/bracket.js 更新。

    JS 只改这些节点的文本与属性，不重建整个 SVG——连线、坐标、列头都不随填法变，
    重建它们是白费；而且构建时输出的这一份正好当无 JS 回退。
    卡片路径（theme="card"）不传这个参数：长图是 PNG，热区对它毫无用处。
    """
    c = PALETTE[theme]
```

然后把 `box` 里的这一段：

```python
        for i, team in enumerate(x["pair"]):
            ty = y + HEADH + SLOTH * i + SLOTH / 2
            won = team == x["win"]
            # 单选钮：被推荐的一方点亮，对应客户端里你要点的那个圆点
            g.append('<circle cx="%d" cy="%.1f" r="6.5" fill="%s" stroke="%s" '
                     'stroke-width="1.4"/>'
                     % (X + 18, ty, c["pick"] if won else "none",
                        c["pick"] if won else c["dim"]))
            g.append('<text x="%d" y="%.1f" class="%s">%s</text>'
                     % (X + 33, ty + 4.5, "tm on" if won else "tm",
                        _esc(SHORT.get(team, team))))
            if show_prob and won:
                g.append('<text x="%d" y="%.1f" class="pb">%.0f%%</text>'
                         % (X + BOXW - 10, ty + 4.5, x["p"] * 100))
        g.append('</g>')
        return "".join(g)
```

替换为：

```python
        hits = []
        for i, team in enumerate(x["pair"]):
            ty = y + HEADH + SLOTH * i + SLOTH / 2
            won = team == x["win"]
            ids = ((' id="bk-%s-%d-dot"' % (x["stage"], i),
                    ' id="bk-%s-%d-nm"' % (x["stage"], i),
                    ' id="bk-%s-%d-p"' % (x["stage"], i))
                   if interactive else ("", "", ""))
            # 单选钮：被推荐的一方点亮，对应客户端里你要点的那个圆点
            g.append('<circle%s cx="%d" cy="%.1f" r="6.5" fill="%s" stroke="%s" '
                     'stroke-width="1.4"/>'
                     % (ids[0], X + 18, ty, c["pick"] if won else "none",
                        c["pick"] if won else c["dim"]))
            g.append('<text%s x="%d" y="%.1f" class="%s">%s</text>'
                     % (ids[1], X + 33, ty + 4.5, "tm on" if won else "tm",
                        _esc(SHORT.get(team, team))))
            # 交互版里两行都要有百分比元素：换选之后 JS 得把数字挪到另一行，
            # 元素若不存在就得插节点，那会破掉「只改属性、不动版式」的约定。
            if interactive:
                g.append('<text%s x="%d" y="%.1f" class="pb">%s</text>'
                         % (ids[2], X + BOXW - 10, ty + 4.5,
                            ("%.0f%%" % (x["p"] * 100)) if (show_prob and won) else ""))
                hits.append('<rect class="bkhit" x="%d" y="%d" width="%d" height="%d" '
                            'fill="transparent" data-stage="%s" data-side="%d"/>'
                            % (X, y + HEADH + SLOTH * i, BOXW, SLOTH,
                               _esc(x["stage"]), i))
            elif show_prob and won:
                g.append('<text x="%d" y="%.1f" class="pb">%.0f%%</text>'
                         % (X + BOXW - 10, ty + 4.5, x["p"] * 100))
        # 热区放在最后：SVG 里后面的元素在上层，压在文字之上才接得到点击。
        # fill="transparent" 而不是 "none"——后者不接收指针事件。
        g.extend(hits)
        g.append('</g>')
        return "".join(g)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_bracket_svg.py -v`
Expected: PASS，5 passed

- [ ] **Step 5: 确认卡片长图逐字节未变**

Run:
```bash
python3 -c "
import sys, os, json
sys.path.insert(0, 'site')
import bracket_svg
pl = json.load(open('reports/p8_playoffs.json'))
open('/tmp/card_after.svg','w').write(bracket_svg.render(pl, 'card'))
print('已写出 /tmp/card_after.svg')
"
git stash && python3 -c "
import sys, os, json
sys.path.insert(0, 'site')
import bracket_svg
pl = json.load(open('reports/p8_playoffs.json'))
open('/tmp/card_before.svg','w').write(bracket_svg.render(pl, 'card'))
" && git stash pop && diff /tmp/card_before.svg /tmp/card_after.svg && echo "卡片路径逐字节一致"
```
Expected: `卡片路径逐字节一致`（diff 无输出）

- [ ] **Step 6: 提交**

```bash
git add site/bracket_svg.py tests/test_bracket_svg.py && git commit -m "feat: 对阵图加可点热区与稳定 id，供前端编辑器就地更新

只在 interactive=True 时加；卡片 PNG 那条路径逐字节不变，测试钉住了这一条。
两行都输出百分比元素（未选中的为空），换选时 JS 只改文本不插节点。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `bracket.js` 核心逻辑与跨语言对照测试

这是整个改动的技术核心，也是唯一会静默出错的地方——所以它自己带一套用 node 跑的对照测试。

**Files:**
- Create: `site/assets_src/bracket.js`
- Test: `tests/test_bracket_bits.py`（追加两条跨语言测试）

**Interfaces:**
- Consumes: Task 1 的 `expand`（对照基准）、Task 4 的 `_layout`（候选顺序基准）
- Produces（`module.exports` 与 `window.BracketEditor` 上各挂一份）：
  - `derive(qf, bits) -> {picks: {阶段: 队}, pairs: {阶段: [队, 队]}}`
  - `expand(qf, bits) -> {阶段: 队}`（= `derive().picks`）
  - `score(winP, picks) -> number`
  - `bestGiven(qf, winP, pinned) -> number`（返回 bits，无解返回 -1）
  - `resolve(qf, winP, pins) -> {bits: number, pins: [{stage, team}]}`
  - `BIT_STAGE: string[]`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_bracket_bits.py` 顶部的 import 区补上：

```python
import json
import os
import shutil
import subprocess

import pytest
```

并在文件末尾追加：

```python
JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "site", "assets_src", "bracket.js")
NO_NODE = shutil.which("node") is None


def _run_js(body):
    """在 node 里 require bracket.js 并跑一段脚本，取回 JSON。

    node 只是**测试**依赖，不是运行时依赖——站点没有构建步骤，
    bracket.js 是浏览器直接加载的普通脚本。所以 node 缺席时跳过而不是失败。
    """
    src = "const M = require(%s);\n%s" % (json.dumps(JS), body)
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True)
    assert r.returncode == 0, "node 执行失败：\n%s" % r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(NO_NODE, reason="需要 node 才能跑 JS 侧对照")
def test_js_的_expand_与_python_逐位一致():
    """两侧展开 16384 种 bits，逐项比对。

    这是设计文档决定一那条赌注的兑现处：漂移不会崩溃，只会让页面印出一个
    跟模型对不上的期望答对数——所以必须有一条会变红的断言盯着它。
    """
    got = _run_js("""
      const qf = [[0,7],[1,6],[2,5],[3,4]];
      const out = [];
      for (var b = 0; b < 16384; b++) out.push(M.expand(qf, b));
      process.stdout.write(JSON.stringify(out));
    """)
    assert len(got) == 16384
    for bits in range(1 << N_BITS):
        want = {k: v for k, v in expand(QF, bits).items()}
        assert got[bits] == want, "bits=%d 两侧展开不一致" % bits


@pytest.mark.skipif(NO_NODE, reason="需要 node 才能跑 JS 侧对照")
def test_js_排候选的顺序与_svg_画上下两行的顺序一致():
    """SVG 里「上面那一行」必须就是 pairs[st][0]。

    不一致的话，读者点上面一行会选中下面那支队——而且不报错、不崩溃，
    因为两个候选都是合法的。这种 bug 只能靠这条断言抓。

    Python 侧的基准是 site/bracket_svg.py 的 _layout()，它从 pick 反推每格候选，
    是 SVG 上下两行的实际来源。
    """
    import sys
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site"))
    import bracket_svg

    teams = ["T%d" % i for i in range(8)]
    qf_names = [[teams[a], teams[b]] for a, b in QF]
    got = _run_js("""
      const qf = %s;
      const out = [];
      for (var b = 0; b < 16384; b += 337) out.push([b, M.derive(qf, b).pairs]);
      process.stdout.write(JSON.stringify(out));
    """ % json.dumps(qf_names))

    for bits, js_pairs in got:
        pick = {st: teams[t] for st, t in expand(QF, bits).items()}
        pl = {"ubqf": [{"stage": "UBQF%d" % (k + 1), "a": a, "b": b}
                       for k, (a, b) in enumerate(qf_names)],
              "bracket_homework": {"pick": pick,
                                   "rows": [{"stage": st, "p_pick": 0.5}
                                            for st in BIT_STAGE]}}
        for cell in bracket_svg._layout(pl):
            assert list(cell["pair"]) == js_pairs[cell["stage"]], (
                "bits=%d 的 %s 格：SVG 画的是 %s，JS 认为是 %s"
                % (bits, cell["stage"], list(cell["pair"]), js_pairs[cell["stage"]]))


@pytest.mark.skipif(NO_NODE, reason="需要 node 才能跑 JS 侧对照")
def test_js_的_bestGiven_在无约束时给出与_python_相同的最优填法():
    teams = [str(i) for i in range(8)]
    w = _winners()
    _, _, stats = best_bracket(QF, w, teams)
    win_p = {st: {str(t): p for t, p in w[st].items()} for st in ALL_STAGES}
    got = _run_js("""
      const qf = [["0","7"],["1","6"],["2","5"],["3","4"]];
      const winP = %s;
      process.stdout.write(JSON.stringify(M.bestGiven(qf, winP, {})));
    """ % json.dumps(win_p))
    assert got == stats["pick_bits"]


@pytest.mark.skipif(NO_NODE, reason="需要 node 才能跑 JS 侧对照")
def test_js_的_bestGiven_尊重钉住的格子():
    """钉住一支队之后，重搜出来的填法那一格必须真的是它。"""
    w = _winners()
    win_p = {st: {str(t): p for t, p in w[st].items()} for st in ALL_STAGES}
    got = _run_js("""
      const qf = [["0","7"],["1","6"],["2","5"],["3","4"]];
      const winP = %s;
      const bits = M.bestGiven(qf, winP, {"UBQF1": "7"});
      process.stdout.write(JSON.stringify([bits, M.expand(qf, bits)]));
    """ % json.dumps(win_p))
    bits, picks = got
    assert bits >= 0
    assert picks["UBQF1"] == "7"


@pytest.mark.skipif(NO_NODE, reason="需要 node 才能跑 JS 侧对照")
def test_js_的_resolve_丢掉互相矛盾的旧钉但保住最后点的那一下():
    """A 格钉 0 号、E 格也钉 0 号，随后把 A 格改钉 7 号（0 号已被淘汰）。

    设计文档决定二：你最近点的那一下永远生效，被丢的是更老的那个钉。
    """
    w = _winners()
    win_p = {st: {str(t): p for t, p in w[st].items()} for st in ALL_STAGES}
    got = _run_js("""
      const qf = [["0","7"],["1","6"],["2","5"],["3","4"]];
      const winP = %s;
      const pins = [{stage:"UBSF1", team:"0"}, {stage:"UBQF1", team:"7"}];
      const r = M.resolve(qf, winP, pins);
      process.stdout.write(JSON.stringify([M.expand(qf, r.bits), r.pins]));
    """ % json.dumps(win_p))
    picks, pins = got
    assert picks["UBQF1"] == "7", "最后点的那一下没生效"
    assert [p["stage"] for p in pins] == ["UBQF1"], "该被丢的是更老的 UBSF1 那个钉"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_bracket_bits.py -k js -x`
Expected: FAIL，node 报 `Cannot find module ... bracket.js`

- [ ] **Step 3: 实现 `bracket.js` 的核心部分**

创建 `site/assets_src/bracket.js`：

```js
/* 抄作业页主赛事对阵表的编辑器：在图上直接点，钉住的格子保持不动，其余重搜最优。

   位定义（一份自洽填法 = 一个 14 位整数，0 表示「上面那个候选」）与
   model/l6_playoffs.py 的 expand() 完全一致。完整的表在
   docs/superpowers/specs/2026-08-18-bracket-editor-design.md 决定一。

   ⚠️ 改这里必须同步改 model/l6_playoffs.py——tests/test_bracket_bits.py 会用 node
   跑本文件的 expand，与 Python 版逐位比对全部 16384 种展开。两边漂移不会崩溃，
   只会让页面静静印出一个跟模型对不上的期望答对数，所以那条测试是必须的。

   纯前端：无后端、无 cookie，填法编进 URL 的 #hash。 */
(function (root) {
  "use strict";

  var BIT_STAGE = ["UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2",
                   "LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "UBF",
                   "LBF", "GF"];
  var N_BITS = BIT_STAGE.length;
  var N_BRACKETS = 1 << N_BITS;          // 16384

  /* ---------- 路径规则 ---------- */

  /* 把 14 位整数展开成一份自洽填法，并顺带给出每一格的两位候选。

     pairs[阶段][side] 就是该位取 side 时选中的那一方——这个顺序与
     site/bracket_svg.py 的 _layout() 画上下两行的顺序一致（有测试钉住），
     所以「点上面那一行」= side 0，不需要任何额外映射。 */
  function derive(qf, bits) {
    var b = [], k;
    for (k = 0; k < N_BITS; k++) b.push((bits >> k) & 1);
    var w = [], l = [];
    for (k = 0; k < 4; k++) { w.push(qf[k][b[k]]); l.push(qf[k][1 - b[k]]); }
    var e = b[4], f = b[5];
    var sfW = [w[e], w[2 + f]];            // E / F 的胜者
    var sfL = [w[1 - e], w[3 - f]];        // E / F 的败者
    var lb1 = [l[b[6]], l[2 + b[7]]];      // 败1上 / 败1下的胜者
    // 败者组交叉：败2上 = 败1上胜者 vs F 的败者；败2下 = 败1下胜者 vs E 的败者
    var q1 = [lb1[0], sfL[1]], q2 = [lb1[1], sfL[0]];
    var lb2 = [q1[b[8]], q2[b[9]]];
    var lb3 = lb2[b[10]];
    var ubfW = sfW[b[11]], ubfL = sfW[1 - b[11]];
    var lbfOpts = [lb3, ubfL], lbf = lbfOpts[b[12]];
    var gfOpts = [ubfW, lbf], champ = gfOpts[b[13]];

    var vals = [w[0], w[1], w[2], w[3], sfW[0], sfW[1],
                lb1[0], lb1[1], lb2[0], lb2[1], lb3, ubfW, lbf, champ];
    var picks = {};
    for (k = 0; k < N_BITS; k++) picks[BIT_STAGE[k]] = vals[k];

    return {
      picks: picks,
      pairs: {
        "UBQF1": qf[0], "UBQF2": qf[1], "UBQF3": qf[2], "UBQF4": qf[3],
        "UBSF1": [w[0], w[1]], "UBSF2": [w[2], w[3]],
        "LBR1-1": [l[0], l[1]], "LBR1-2": [l[2], l[3]],
        "LBQF-1": q1, "LBQF-2": q2,
        "LBSF": lb2, "UBF": sfW, "LBF": lbfOpts, "GF": gfOpts
      }
    };
  }

  function expand(qf, bits) { return derive(qf, bits).picks; }

  /* 期望答对数。winP[阶段][队] 是**边缘**概率——某队真的赢下某一场，
     与你在别的格子填了什么无关。所以算分永远是查表，不需要重跑任何模拟。 */
  function score(winP, picks) {
    var s = 0;
    for (var i = 0; i < N_BITS; i++) {
      var st = BIT_STAGE[i];
      s += winP[st][picks[st]] || 0;
    }
    return s;
  }

  /* 在满足 pinned 的自洽填法里搜期望最高的一份。无解返回 -1。
     16384 × 14 次查表，实测毫秒级，不需要任何剪枝。 */
  function bestGiven(qf, winP, pinned) {
    var bestBits = -1, bestSc = -1, st;
    for (var bits = 0; bits < N_BRACKETS; bits++) {
      var picks = expand(qf, bits), ok = true;
      for (st in pinned) {
        if (pinned.hasOwnProperty(st) && picks[st] !== pinned[st]) { ok = false; break; }
      }
      if (!ok) continue;
      var sc = score(winP, picks);
      if (sc > bestSc) { bestSc = sc; bestBits = bits; }
    }
    return bestBits;
  }

  /* 钉住集合可能互相矛盾：改了 A 格之后，E 格钉的那支队可能已经被淘汰了。

     规则（设计文档决定二）：从最老的钉开始逐个丢，直到有解。
     pins 数组的最后一个是本次点击，所以「丢最老的」天然跳过它——
     这正是要的行为：你最近点的那一下永远生效。

     通过 UI 点出来的钉一定有解（点的就是当前填法下的候选），
     所以循环最多丢到只剩本次点击。全丢光的兜底只服务于手改 URL 的情形。 */
  function resolve(qf, winP, pins) {
    var p = pins.slice();
    while (p.length) {
      var pinned = {};
      for (var i = 0; i < p.length; i++) pinned[p[i].stage] = p[i].team;
      var bits = bestGiven(qf, winP, pinned);
      if (bits >= 0) return { bits: bits, pins: p };
      p.shift();
    }
    return { bits: bestGiven(qf, winP, {}), pins: [] };
  }

  var API = {
    BIT_STAGE: BIT_STAGE, N_BITS: N_BITS, N_BRACKETS: N_BRACKETS,
    derive: derive, expand: expand, score: score,
    bestGiven: bestGiven, resolve: resolve
  };

  // 浏览器里挂 window，node 里（跨语言对照测试）走 module.exports
  root.BracketEditor = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : this);
```

- [ ] **Step 4: 运行跨语言测试确认通过**

Run: `python3 -m pytest tests/test_bracket_bits.py -v`
Expected: PASS，全部通过（含 5 条 `test_js_*`）

- [ ] **Step 5: 手测重搜速度**

Run:
```bash
node -e '
const M = require("./site/assets_src/bracket.js");
const qf = [["a","b"],["c","d"],["e","f"],["g","h"]];
const winP = {};
M.BIT_STAGE.forEach(s => { winP[s] = {}; "abcdefgh".split("").forEach(t => winP[s][t] = 1/8); });
const t0 = Date.now();
for (let i = 0; i < 10; i++) M.bestGiven(qf, winP, {});
console.log("单次重搜 " + ((Date.now() - t0) / 10).toFixed(1) + " ms");
'
```
Expected: 每次远低于 100ms（设计假设是"毫秒级、不需要剪枝"；若超过 100ms，说明假设不成立，停下来先解决，别继续往上堆渲染）

- [ ] **Step 6: 提交**

```bash
git add site/assets_src/bracket.js tests/test_bracket_bits.py && git commit -m "feat: 对阵表编辑器的核心逻辑——展开、算分、按钉住重搜

Python 与 JS 两份 expand 由 node 跑的 pytest 逐位比对 16384 种展开钉死；
另有一条测试保证 JS 排候选的顺序与 SVG 画上下两行的顺序一致——
不一致的话读者点上面一行会选中下面那支队，而且不报错。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: 渲染——SVG 就地更新、卡片重建、分数条

**Files:**
- Modify: `site/assets_src/bracket.js`（在 `var API = {` 之前插入渲染层）

**Interfaces:**
- Consumes: Task 3 的 `bracket_data()` 形状、Task 4 的 SVG id 约定、Task 5 的 `derive`/`score`
- Produces:
  - `initBracket(data)` — 全局入口（`window.initBracket`），由页面内联脚本调用
  - 内部：`paint()` 重绘全部三处（SVG、卡片、分数条）

- [ ] **Step 1: 实现渲染层**

在 `site/assets_src/bracket.js` 中 `var API = {` 那一行的**正上方**插入：

```js
  /* ---------- 状态 ---------- */
  var D = null;          // bracket_data() 给的那个对象
  var bits = 0;          // 当前填法
  var pins = [];         // [{stage, team}]，按点击时间从老到新
  var editable = false;  // 窄屏只读（见 Task 7）

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function $(id) { return document.getElementById(id); }

  function pinnedMap() {
    var m = {};
    for (var i = 0; i < pins.length; i++) m[pins[i].stage] = pins[i].team;
    return m;
  }

  /* ---------- 渲染：SVG ---------- */

  /* 只改文本与属性，不重建 SVG。连线、坐标、列头都不随填法变，重建它们是白费；
     而且构建时 Python 输出的那一份正好当无 JS 回退。 */
  function paintSvg(picks, pairs, pinMap) {
    for (var i = 0; i < N_BITS; i++) {
      var st = BIT_STAGE[i], pair = pairs[st], isPinned = pinMap[st] !== undefined;
      for (var side = 0; side < 2; side++) {
        var nm = $("bk-" + st + "-" + side + "-nm");
        if (!nm) continue;                       // 非交互版渲染，什么都不做
        var dot = $("bk-" + st + "-" + side + "-dot");
        var pv = $("bk-" + st + "-" + side + "-p");
        var team = pair[side], on = team === picks[st];
        nm.textContent = D.short[team] || team;
        nm.setAttribute("class", on ? "tm on" : "tm");
        dot.setAttribute("fill", on ? "var(--s1)" : "none");
        dot.setAttribute("stroke", on ? "var(--s1)" : "var(--ink-muted)");
        // 钉住的那一格描粗一圈，与「它替我算的」区分开
        dot.setAttribute("stroke-width", on && isPinned ? "3.2" : "1.4");
        pv.textContent = on ? (D.win_p[st][team] * 100).toFixed(0) + "%" : "";
      }
    }
  }

  /* ---------- 渲染：逐场卡片 ---------- */

  /* 「这一格还可能出现」列的是与填法无关的全表 top——它是卡片相对于图的增量信息。
     八强那四场对阵固定，其余队概率为 0，这一段自然不显示。 */
  function alsoPossible(st, pair) {
    var rows = [], t;
    for (t in D.win_p[st]) {
      if (D.win_p[st].hasOwnProperty(t) && pair.indexOf(t) < 0 && D.win_p[st][t] > 0.005) {
        rows.push([t, D.win_p[st][t]]);
      }
    }
    rows.sort(function (a, b) { return b[1] - a[1]; });
    return rows.slice(0, 3);
  }

  function cardHtml(st, picks, pairs, pinMap) {
    var pair = pairs[st], pick = picks[st];
    var other = pair[0] === pick ? pair[1] : pair[0];
    var meta = D.meta[st];
    var also = alsoPossible(st, pair);
    var alsoHtml = also.length
      ? '<div class="picksub">这一格还可能出现</div>' + also.map(function (r) {
          return '<div class="pick"><span class="t">' + esc(r[0]) +
                 '</span><span class="p">' + (r[1] * 100).toFixed(0) + "%</span></div>";
        }).join("")
      : "";
    return '<div class="hwcard' + (pinMap[st] !== undefined ? " pinned" : "") + '">' +
           '<div class="hwhead"><b>' + esc(meta.panel) + "</b><span>" +
           esc(meta.cn) + " · " + esc(meta.time) +
           (pinMap[st] !== undefined ? ' · <i class="pinlab">你钉的</i>' : "") +
           "</span></div>" +
           '<div class="pickbig">' + esc(pick) + "</div>" +
           '<div class="picksub">这一场它赢的概率 ' +
           (D.win_p[st][pick] * 100).toFixed(1) + "%　｜　另一个候选</div>" +
           '<div class="pick"><span class="t">' + esc(other) + '</span><span class="p">' +
           (D.win_p[st][other] * 100).toFixed(1) + "%</span></div>" + alsoHtml + "</div>";
  }

  /* ⚠️ 分组标题与 site/homework.py:bracket_section 里那三个 <h3> 是重复的一份：
     JS 覆盖 #bkcards 的全部内容，所以两处都要写。改一处必须改另一处，
     否则读者在 JS 加载前后会看到两套不同的小标题。 */
  function paintCards(picks, pairs, pinMap) {
    var wrap = $("bkcards");
    if (!wrap) return;
    var groups = [
      ["胜者组（4 + 2 + 1 场）", ["UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2", "UBF"]],
      ["败者组（2 + 2 + 1 + 1 场）", ["LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "LBF"]],
      ["总决赛", ["GF"]]
    ];
    var html = "";
    for (var g = 0; g < groups.length; g++) {
      html += "<h3>" + groups[g][0] + '</h3><div class="hwgrid">';
      for (var i = 0; i < groups[g][1].length; i++) {
        html += cardHtml(groups[g][1][i], picks, pairs, pinMap);
      }
      html += "</div>";
    }
    wrap.innerHTML = html;
  }

  /* ---------- 渲染：分数条 ---------- */
  function paintStats(picks) {
    var mine = score(D.win_p, picks), best = D.stats.expected;
    var set = function (id, txt) { var el = $(id); if (el) el.textContent = txt; };
    set("bk-exp", mine.toFixed(2));
    set("bk-best", best.toFixed(2));
    set("bk-delta", (mine - D.stats.random).toFixed(2));
    var bar = $("bk-bar");
    if (bar) bar.style.width = Math.max(0, Math.min(100, mine / 14 * 100)).toFixed(1) + "%";
    var st = $("bk-status");
    if (!st) return;
    if (!pins.length) {
      st.textContent = "这是模型算出来的最优填法";
      st.className = "pkstat ok";
    } else if (mine >= best - 1e-9) {
      st.textContent = "钉了 " + pins.length + " 格，仍然是最优填法";
      st.className = "pkstat ok";
    } else {
      st.textContent = "钉了 " + pins.length + " 格，期望少了 " +
                       (best - mine).toFixed(2) + " 场";
      st.className = "pkstat warn";
    }
  }

  function paint() {
    var d = derive(D.qf, bits), pinMap = pinnedMap();
    paintSvg(d.picks, d.pairs, pinMap);
    paintCards(d.picks, d.pairs, pinMap);
    paintStats(d.picks);
  }
```

- [ ] **Step 2: 加最小的 `init` 并挂上全局入口（交互留到 Task 7）**

在 `function paint() {` 之后、`var API = {` 之前插入：

```js
  /* ---------- 入口 ---------- */
  function init(data) {
    D = data;
    bits = data.bits;
    pins = [];
    paint();
  }
```

把 `var API = {` 那个对象：

```js
  var API = {
    BIT_STAGE: BIT_STAGE, N_BITS: N_BITS, N_BRACKETS: N_BRACKETS,
    derive: derive, expand: expand, score: score,
    bestGiven: bestGiven, resolve: resolve
  };
```

改为：

```js
  var API = {
    BIT_STAGE: BIT_STAGE, N_BITS: N_BITS, N_BRACKETS: N_BRACKETS,
    derive: derive, expand: expand, score: score,
    bestGiven: bestGiven, resolve: resolve, init: init
  };
```

并在文件末尾 `root.BracketEditor = API;` 之后加：

```js
  root.initBracket = init;
```

`init` 与 API 的改动必须在同一步完成——分成两步的话，第一步结束时 `API` 会引用一个
还不存在的 `init`，整个文件在浏览器里直接报 ReferenceError。

- [ ] **Step 3: 用 node 验证渲染不依赖真实 DOM 时也不炸**

Run:
```bash
node -e '
const M = require("./site/assets_src/bracket.js");
// 渲染层全部走 document.getElementById；node 里没有 document，
// 所以这里只验证纯逻辑部分仍可用（init 需要 DOM，不在此测）
const qf = [["a","b"],["c","d"],["e","f"],["g","h"]];
const winP = {};
M.BIT_STAGE.forEach(s => { winP[s] = {}; "abcdefgh".split("").forEach(t => winP[s][t] = 1/8); });
const picks = M.expand(qf, 0);
console.log("score =", M.score(winP, picks).toFixed(2), "(应为 1.75 = 14/8)");
'
```
Expected: `score = 1.75 (应为 1.75 = 14/8)`

- [ ] **Step 4: 运行全部测试确认没有回归**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add site/assets_src/bracket.js && git commit -m "feat: 编辑器的渲染层——SVG 就地改节点、卡片重建、分数条显示偏离代价

分数条不只报你的期望，还报「钉了这几格让期望少了多少场」——
自定义编辑的信息价值就在这个数上。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: 交互、窄屏门控与分享链接

交互与分享放在一个任务里：`init` 在启动时就要读 hash、每次点击后要写 hash，拆开做会让前一半带着三个什么都不做的空函数交付。

**Files:**
- Modify: `site/assets_src/bracket.js`（在 `function paint() {` 与 `/* ---------- 入口 ---------- */` 之间插入交互层与分享层，并替换 Task 6 的最小 `init`）

**Interfaces:**
- Consumes: Task 5 的 `resolve`/`expand`/`derive`、Task 6 的 `paint`/`pinnedMap`/`$`
- Produces:
  - 点击热区 → 钉住该队 → 重搜 → 重绘 → 写 hash
  - `#bk-reset` 清空全部钉；`#bk-share` 复制链接
  - hash 格式 `#b=` + 3 位 base36 的填法 + 3 位 base36 的钉住掩码
  - 窄屏（<940px）不绑点击，但**照常渲染**——别人在电脑上改好发来的链接，手机上要能读

- [ ] **Step 1: 实现分享链接的编解码**

在 `site/assets_src/bracket.js` 的 `function paint() {` 那一段之后、`/* ---------- 入口 ---------- */` 之前插入：

```js
  /* ---------- 分享链接 ---------- */

  /* 编码 = 14 位填法 + 14 位钉住掩码，各 3 个 base36 字符（36^3 = 46656 > 16384）。

     钉住掩码必须一起编：只编填法的话，别人打开你的链接看到的是一份「全部由模型
     算出来的」填法，分不出哪几格是你自己的判断——而那恰恰是你想分享的东西。

     顺序不编码。pins 的先后只在冲突解钉时起作用，而接收方拿到的状态本身是自洽的，
     他继续点时按位序恢复的顺序照样能工作。为 6 个字符再加一段顺序编码不划算。 */
  function pad3(n) {
    var s = n.toString(36);
    return "000".slice(s.length) + s;
  }

  function encode() {
    var mask = 0, pinMap = pinnedMap();
    for (var i = 0; i < N_BITS; i++) {
      if (pinMap[BIT_STAGE[i]] !== undefined) mask |= (1 << i);
    }
    return pad3(bits) + pad3(mask);
  }

  function readHash() {
    var m = /(?:^|[#&])b=([0-9a-z]{6})(?:&|$)/.exec(location.hash || "");
    if (!m) return false;
    var v = parseInt(m[1].slice(0, 3), 36), mask = parseInt(m[1].slice(3), 36);
    if (isNaN(v) || isNaN(mask) || v < 0 || v >= N_BRACKETS || mask < 0 ||
        mask >= N_BRACKETS) return false;
    var picks = expand(D.qf, v), p = [];
    for (var i = 0; i < N_BITS; i++) {
      if (mask & (1 << i)) p.push({ stage: BIT_STAGE[i], team: picks[BIT_STAGE[i]] });
    }
    // 走一遍 resolve 而不是直接采信：链接可以被手改，非法的钉在这里被丢掉，
    // 页面退回到一份合法填法，而不是渲染出一张自相矛盾的表。
    var r = resolve(D.qf, D.win_p, p);
    bits = r.bits;
    pins = r.pins;
    return true;
  }

  function writeHash() {
    try { history.replaceState(null, "", "#b=" + encode()); } catch (e) {}
  }

  function share(btn) {
    var url = location.origin + location.pathname + "#b=" + encode();
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "已复制链接 ✓";
      setTimeout(function () { btn.textContent = old; }, 1800);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, done);
    else window.prompt("复制这个链接分享给别人：", url);
  }
```

- [ ] **Step 2: 实现交互，并把 Task 6 的最小 `init` 换成完整版**

紧接着 Step 1 插入的代码之后插入：

```js
  /* ---------- 交互 ---------- */

  /* 点某格的某一侧 = 钉住「这支队赢下这一格」。

     钉的是**队伍**不是位置：位置（「上面那一行」）的含义随前面的选择变化，
     钉位置会让读者看到「我明明钉了这一格，怎么队伍自己变了」。 */
  function pick(stage, side) {
    if (!editable) return;
    var team = derive(D.qf, bits).pairs[stage][side];
    var kept = [];
    for (var i = 0; i < pins.length; i++) {
      if (pins[i].stage !== stage) kept.push(pins[i]);
    }
    kept.push({ stage: stage, team: team });      // 本次点击永远排在最后
    var r = resolve(D.qf, D.win_p, kept);
    bits = r.bits;
    pins = r.pins;
    paint();
    writeHash();
  }

  function reset() {
    pins = [];
    bits = D.bits;
    paint();
    writeHash();
  }

  /* 窄屏只读（设计文档决定五）。

     每行热区在窄屏约 159×21 CSS px，且要横向滚动才能找到格子——在手机上这是个
     **会点错**的功能，不是个不好用的功能：任何一次点击都产生一份合法填法，
     点错不报错。所以窄屏干脆不绑。

     断点复用 style.css 里 SVG 开始横滚的那一个（940px），不引入第二个阈值。
     用 change 事件跟随窗口变化，而不是只在加载时判一次——否则读者把窗口拉宽后
     会发现还是点不动。 */
  function watchWidth() {
    var mq = window.matchMedia("(min-width: 940px)");
    var apply = function () {
      editable = mq.matches;
      var wrap = $("bkwrap");
      if (wrap) wrap.className = "bkwrap" + (editable ? " editable" : "");
    };
    apply();
    if (mq.addEventListener) mq.addEventListener("change", apply);
    else if (mq.addListener) mq.addListener(apply);      // Safari < 14
  }

  function init(data) {
    D = data;
    bits = data.bits;
    pins = [];
    watchWidth();
    if (!readHash()) { bits = data.bits; pins = []; }
    paint();

    document.addEventListener("click", function (ev) {
      var hit = ev.target.closest && ev.target.closest(".bkhit");
      if (hit) { pick(hit.getAttribute("data-stage"), +hit.getAttribute("data-side")); return; }
      if (ev.target.id === "bk-reset") reset();
      if (ev.target.id === "bk-share") share(ev.target);
    });

    window.addEventListener("hashchange", function () { if (readHash()) paint(); });
  }
```

然后把 Task 6 加的那个最小 `init` 整个删掉——它已被上面这一版取代：

```js
  /* ---------- 入口 ---------- */
  function init(data) {
    D = data;
    bits = data.bits;
    pins = [];
    paint();
  }
```

（文件末尾的 `root.initBracket = init;` 与 `API` 里的 `init: init` 保持不动。）

- [ ] **Step 3: 用 node 验证 base36 编码的边界**

Run:
```bash
node -e '
const M = require("./site/assets_src/bracket.js");
// pad3 与掩码逻辑是纯算术，这里直接复演一遍验证边界
const pad3 = n => ("000" + n.toString(36)).slice(-3);
for (const v of [0, 1, 35, 36, 16383]) {
  const s = pad3(v);
  if (s.length !== 3 || parseInt(s, 36) !== v) { console.log("FAIL", v, s); process.exit(1); }
}
console.log("pad3 往返 OK（含 0 / 35 / 36 / 16383 边界）");
'
```
Expected: `pad3 往返 OK（含 0 / 35 / 36 / 16383 边界）`

- [ ] **Step 4: 用 node 验证「钉住 A 格之后 E 格候选跟着变」**

这是整个功能的核心行为，在接线之前先用纯逻辑验一遍——页面上点不出来的话，先怀疑渲染，不必怀疑这一层。

Run:
```bash
node -e '
const M = require("./site/assets_src/bracket.js");
const qf = [["0","7"],["1","6"],["2","5"],["3","4"]];
const winP = {};
M.BIT_STAGE.forEach(s => { winP[s] = {}; ["0","1","2","3","4","5","6","7"].forEach((t,i) => winP[s][t] = [0.3,0.2,0.15,0.12,0.1,0.06,0.04,0.03][i]); });
// 钉 A 格下面那一行（side 1 = "7"），再看 E 格候选是否跟着变
let bits = M.bestGiven(qf, winP, {});
console.log("初始 A 格 =", M.expand(qf, bits)["UBQF1"], "  E 格候选 =", M.derive(qf, bits).pairs["UBSF1"]);
const team = M.derive(qf, bits).pairs["UBQF1"][1];
const r = M.resolve(qf, winP, [{stage:"UBQF1", team: team}]);
console.log("钉 A 格 =", team, "后 A 格 =", M.expand(qf, r.bits)["UBQF1"], "  E 格候选 =", M.derive(qf, r.bits).pairs["UBSF1"]);
'
```
Expected: 第二行的「E 格候选」里出现被钉住的那支队——这就是"A 格改了，E 格跟着变"

- [ ] **Step 5: 运行全部测试**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add site/assets_src/bracket.js && git commit -m "feat: 编辑器的点击、钉住、窄屏门控与填法分享

钉的是队伍不是位置——位置的含义随前面的选择变化，钉位置会让人看到
「我明明钉了这一格，怎么队伍自己变了」。
窄屏不绑点击：每行热区约 159x21px 且要横滚，那是个会点错的功能，
而点错不报错（任何一次点击都产生合法填法）。断点跟随窗口变化，不是只判一次。
分享链接把钉住掩码一起编码——只编填法的话，别人打开看到的是一份「全是模型算的」
填法，分不出哪几格是你自己的判断，而那正是你想分享的东西。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: 接线、文案与样式，端到端跑通

**Files:**
- Modify: `site/homework.py:bracket_section`（分数条、卡片容器、提示文案、SVG 开交互）
- Modify: `site/pages.py:write_all`（资源清单 + settled 分支的 `extra_js`）
- Modify: `site/assets_src/style.css`（热区 hover、钉住态、窄屏隐藏交互 UI、两段文案切换）

**Interfaces:**
- Consumes: 全部前序任务
- Produces: 构建产物 `site/dist/homework.html` 上可点的对阵表

- [ ] **Step 1: 改 `bracket_section` 的三处**

在 `site/homework.py` 的 `bracket_section` 中：

**(a)** 把 SVG 渲染那一行（在函数末尾的格式化参数里）：

```python
       '<div class="bkwrap">%s</div>' % bracket_svg.render(pl, "page"),
```

改为：

```python
       '<div class="bkwrap" id="bkwrap">%s</div>'
       % bracket_svg.render(pl, "page", interactive=True),
```

**(b)** 把图下面那段提示：

```html
<p class="hint">客户端里后面几轮显示「?」，这里填的是模型的推荐——那正是这张图的用处。
<b>注意后面几轮的候选是被前面的选择锁死的</b>：你如果在 A 格改填 Iron Wing，
E 格的候选也会跟着变，不能照抄下面这份了。</p>
```

替换为：

```html
<p class="hint">客户端里后面几轮显示「?」，这里填的是模型的推荐——那正是这张图的用处。
<span class="wide-only"><b>不同意哪一格，直接点图上那支队就能改</b>：
你在 A 格改填 Iron Wing，E 格的候选会跟着变，剩下没被你钉住的格子会重新算一遍最优，
上面的期望答对数实时更新。</span>
<span class="narrow-only"><b>这张表可以自己改</b>——后面几轮的候选被前面的选择锁死，
改一格后面就得跟着重算，所以编辑功能只在电脑上开。换电脑打开就能点。</span></p>
```

**(c)** 把分数条那一段：

```html
<div class="pkbar">
  <div class="pkstats">
    <div><span class="pklab">这份填法期望答对</span><span class="pkbig">%.2f</span><span class="pkunit">/ 14 场</span></div>
    <div><span class="pklab">闭眼乱填</span><span class="pkbig">%.2f</span><span class="pkunit">场</span></div>
    <div><span class="pklab">理论上界</span><span class="pkbig">%.2f</span><span class="pkunit">场</span></div>
  </div>
  <div class="pkmeter"><div style="width:%.1f%%"></div></div>
  <div class="pkbtns"><span class="pkstat ok">在 %s 种自洽填法里穷举出来的最优解</span></div>
</div>
```

替换为：

```html
<div class="pkbar">
  <div class="pkstats">
    <div><span class="pklab">这份填法期望答对</span><span class="pkbig" id="bk-exp">%.2f</span><span class="pkunit">/ 14 场</span></div>
    <div><span class="pklab">模型最优</span><span class="pkbig" id="bk-best">%.2f</span><span class="pkunit">场</span></div>
    <div><span class="pklab">比乱填多</span><span class="pkbig" id="bk-delta">%.2f</span><span class="pkunit">场</span></div>
  </div>
  <div class="pkmeter"><div id="bk-bar" style="width:%.1f%%"></div></div>
  <div class="pkbtns">
    <span class="pkstat ok" id="bk-status">在 %s 种自洽填法里穷举出来的最优解</span>
    <button id="bk-reset" class="wide-only">恢复模型推荐</button>
    <button id="bk-share" class="pri wide-only">复制我的填法链接</button>
  </div>
</div>
```

对应的格式化参数由：

```python
       st["expected"], st["random"], st["greedy_upper"],
       st["expected"] / st["n_matches"] * 100, "{:,}".format(st["n_brackets"]),
```

改为：

```python
       st["expected"], st["expected"], st["expected"] - st["random"],
       st["expected"] / st["n_matches"] * 100, "{:,}".format(st["n_brackets"]),
```

**(d)** 把三段卡片：

```html
<h3>胜者组（4 + 2 + 1 场）</h3>
%s
<h3>败者组（2 + 2 + 1 + 1 场）</h3>
%s
<h3>总决赛</h3>
%s
```

替换为：

```html
<div id="bkcards">
<h3>胜者组（4 + 2 + 1 场）</h3>
%s
<h3>败者组（2 + 2 + 1 + 1 场）</h3>
%s
<h3>总决赛</h3>
%s
</div>
```

（三个 `block(...)` 参数保持原样——构建时渲染的这一份是无 JS 回退，JS 加载后整体覆盖。）

**(e)** 「闭眼乱填 / 理论上界」两个数从分数条挪走了，把它们补进下面那段说明。找到：

```
那个填法的分数是 <b>%.2f 场</b>——它是个够不着的上界，不是可选项。真正能填出来的最优是
<b>%.2f 场</b>，中间这 <b>%.2f 场</b>就是「路径必须自洽」这条约束的代价。<br>
```

在其后、`<span class="hint">16384 = 2^14` 之前插入一行：

```
闭眼乱填是 <b>%.2f 场</b>——这两个数都与你怎么填无关，是题目本身的性质，所以不跟着上面的填法变。<br>
```

并在对应的格式化参数中，把：

```python
       st["greedy_upper"], st["expected"], st["greedy_upper"] - st["expected"],
```

改为：

```python
       st["greedy_upper"], st["expected"], st["greedy_upper"] - st["expected"],
       st["random"],
```

- [ ] **Step 2: 改 `pages.py` 的两处**

在 `site/pages.py` 的 `write_all` 中，把：

```python
    for f in ("style.css", "app.js", "px.js", "picker.js"):
```

改为：

```python
    for f in ("style.css", "app.js", "px.js", "picker.js", "bracket.js"):
```

并把 `"homework.html"` 那一项的 `extra_js`：

```python
            extra_js="" if payload.get("homework_score") else
                     '<script src="%s/assets/picker.js"></script>'
                     '<script>initPicker(%s);</script>'
                     % (base, __import__("json").dumps(
                         homework.picker_data(payload["raw_pred"], hw, fan_rec),
                         ensure_ascii=False, separators=(",", ":")))),
```

改为：

```python
            # 小组赛揭晓后 picker.js 撤掉（答案都出来了还让人点着填是浪费读者时间），
            # 但主赛事那张对阵表还没打完，它的编辑器要挂上。
            extra_js=(
                '<script src="%s/assets/bracket.js"></script>'
                '<script>initBracket(%s);</script>'
                % (base, __import__("json").dumps(
                    homework.bracket_data(payload["raw_playoffs"]),
                    ensure_ascii=False, separators=(",", ":")))
                if payload.get("homework_score") and payload.get("raw_playoffs") else
                '<script src="%s/assets/picker.js"></script>'
                '<script>initPicker(%s);</script>'
                % (base, __import__("json").dumps(
                    homework.picker_data(payload["raw_pred"], hw, fan_rec),
                    ensure_ascii=False, separators=(",", ":")))),
```

- [ ] **Step 3: 加样式**

在 `site/assets_src/style.css` 的 `.bkwrap` 那一段（384–390 行）之后插入：

```css
/* 对阵表编辑器：热区只在宽屏可点（见 bracket.js 的 watchWidth） */
.bkwrap .bkhit { cursor: default; }
.bkwrap.editable .bkhit { cursor: pointer; }
.bkwrap.editable .bkhit:hover { fill: var(--s1); fill-opacity: .10; }
.hwcard.pinned { border-color: var(--s1); }
.pinlab { font-style: normal; color: var(--s1); font-weight: 700; }
.wide-only { display: inline; }
.narrow-only { display: none; }
button.wide-only { display: inline-block; }
@media (max-width: 940px) {
  .wide-only, button.wide-only { display: none; }
  .narrow-only { display: inline; }
}
```

- [ ] **Step 4: 构建并核对产物**

Run: `python3 site/build_site.py`
Expected: 正常结束

Run:
```bash
python3 - <<'PY'
import re
h = open("site/dist/homework.html").read()
assert h.count('class="bkhit"') == 28, "热区数量不对：%d" % h.count('class="bkhit"')
assert 'id="bkcards"' in h and 'id="bkwrap"' in h
assert 'initBracket(' in h and '/assets/bracket.js' in h
assert 'initPicker(' not in h, "小组赛已揭晓，picker.js 不该再挂"
assert '不能照抄下面这份了' not in h, "旧提示文案没换掉"
assert 'id="bk-exp"' in h and 'id="bk-status"' in h and 'id="bk-reset"' in h
import os
assert os.path.exists("site/dist/assets/bracket.js"), "bracket.js 没被复制"
print("产物核对通过：28 个热区、编辑器已挂、旧文案已换、资源已复制")
PY
```
Expected: `产物核对通过：28 个热区、编辑器已挂、旧文案已换、资源已复制`

- [ ] **Step 5: 在浏览器里实点一遍**

Run: `open site/dist/homework.html`

逐项确认（窗口宽度 ≥ 940px）：
1. 图上鼠标移到任一队名那一行，底色变浅蓝、光标变手型
2. 点 A 格下面那一行 → 该行圆点点亮且**描粗一圈**（钉住标记），E 格的候选跟着换人
3. 分数条第一格的数字变了，状态文字变成"钉了 1 格，期望少了 X.XX 场"（或"仍然是最优填法"）
4. 图下面的卡片跟着变，被钉的那一格卡片有蓝边和"你钉的"标记
5. 点「恢复模型推荐」→ 全部回到初始，状态文字回到"这是模型算出来的最优填法"
6. 点「复制我的填法链接」→ 按钮变"已复制链接 ✓"；地址栏是 `#b=` 加 6 个字符
7. 新开一个标签粘贴那个链接 → 打开后填法与钉住标记都在
8. 把窗口拖窄到 940px 以下 → 两个按钮消失、光标变回箭头、点击无反应，提示文字变成"换电脑打开就能点"
9. 再拖宽回去 → 交互恢复（**不需要刷新**）

- [ ] **Step 6: 运行全部测试**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add site/homework.py site/pages.py site/assets_src/style.css && git commit -m "feat: 抄作业页的主赛事对阵表接上编辑器

图可点、卡片跟着变、分数条报偏离代价、填法可分享。
窄屏只读并换一段文案告诉读者这功能在电脑上有——不说的话手机读者永远不知道。
「闭眼乱填」与「理论上界」从分数条挪进说明文字：它们与你怎么填无关，
留在实时区里会让人以为它们也在跟着变。

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## 完成后

全部 8 个任务通过后，本分支的改动是自洽的、可部署的。部署命令（**需用户确认后再执行**）：

```bash
bash site/deploy.sh
```

⚠️ 部署前请注意 `deploy.sh` 走 `vultr` 主机、依赖 1Password SSH agent，非交互会话会挂。
