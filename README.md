# TI15 预测：一个赛后要认账的 Dota 2 量化预测

用 2020–2026 年的 **145,974 场职业比赛**，对 The International 2026（TI15，8/13–8/23，上海，16 队）
做的战队与选手层面量化预测。

**网站：https://shadowjacob.shop/dota2/** ｜ **更新日志：**[/changelog.html](https://shadowjacob.shop/dota2/changelog.html)

---

## 这个项目想做的不是「预测谁夺冠」

预测谁夺冠是大路货，TI 期间几万人在做。这个项目想做的是另一件事：

> **把预测在赛前冻结、留下哈希存证，等 8 月 23 日打完，用同一套代码给自己打分，好看不好看都发出来。**

做这个项目时查到一件事：**连 Noxville 都不公布自己的事后准确率**——他是 Dota 2 圈公信力最高的
公开预测者，做的正是蒙特卡洛那一套。整个领域没有公开的预测质量基准，所有人都在发概率，没人回头对账。

所以这个仓库里，**「我错在哪」和「我预测了什么」占的篇幅差不多**：

- [`00-DESIGN.md`](00-DESIGN.md) §10 列了 12 条已知限制，包括补不上的硬缺口
- 站内[更新日志](https://shadowjacob.shop/dota2/changelog.html)记录了发出去之后被读者抓到、又改掉的每一处
- `frozen/` 里是各版本的哈希存证，可逐条核对预测有没有被事后修改

## 结果概览

夺冠概率（已与博彩赔率融合，市场权重 0.7）：

| 队 | 夺冠 |
|---|---|
| TEAM VISION | 18.2% |
| Team Spirit | 14.2% |
| Team Yandex | 12.6% |
| Aurora Gaming | 10.6% |
| Iron Wing | 10.4% |
| Team Falcons | 10.3% |

头名只有 18.2%，前八名挤在 7%–18%。**没有真正的大热门**——16 队水平接近，且瑞士轮之后还要打双败，
路径太长，任何单一队伍的概率都被稀释。

模型质量（训练只用 2026-03 之前的数据，在之后 2,546 场没见过的比赛上实测）：

| 指标 | 值 |
|---|---|
| 准确率 | 60.6% |
| Brier 分数 | 0.2315（健康区间 0.21–0.24） |

**赛前预测的现实上限是 65–70%。** 几乎所有号称 85%+ 准确率的 Dota 预测研究，用的都是**实时游戏内数据**
而不是赛前数据（`03-academic-methods.md` 有完整的文献梳理）。看到有人说赛前能做 85%，基本可以断定是数据泄漏。

## 三个可能有复用价值的点

**1. 按「当前这五个人」算战绩，而不是按队名。**
一场比赛只有当某队现役首发出场 ≥3 人时才计入该队。转会问题在数据层就解决了，不需要事后打折。
副产品是它**自动认出了改名和转会**——没有人告诉它这些映射：

| TI15 参赛名 | 真身 | 继承场次 |
|---|---|---|
| Iron Wing | Tundra Esports | 437 |
| LGD Gaming（南美席位） | HEROIC | 385 |
| TEAM VISION | PARIVISION / PVISION | 75 |

按队名匹配是查不出来的：库里有 22,384 支队，搜 `falcons` 出来一堆 `Power Falcons` 之类的野队。
见 `model/l0_align.py`。

**2. TI 瑞士轮的分档数量是恒等式，不是概率。**
TI 的瑞士轮打到 **4 胜或 4 负即停**（跟 CS Major 一样），不是固定 5 轮人人打满。
在这个规则下，最终分档**每届必然是 1 / 2 / 5 / 5 / 2 / 1**（加起来正好 16 队）。
所以「本届会有几支 4-0」这种问题没有意义，永远是 1 支——模型该回答的是**哪一支**。
`tests/test_swiss.py` 把这条写成了跑 120 个随机种子的断言。

这一点我一开始搞错了，按固定 5 轮建模，产出了现实中不存在的 5-0。是读者在评论区抓到的。

**3. 别假设方差等于均值。**
初版用裸泊松估选手数据的方差，结果补刀的实测局内标准差是泊松假定的 **7.72 倍**、GPM 的 4.24 倍，
置信区间因此窄了 4–8 倍。见 `model/l3_player.py`。

## 复现

```bash
pip install -r requirements.txt
python3 -m pytest -q          # 162 个测试
```

**用仓库里已有的产出物直接建站**（不需要下载数据集）：

```bash
python3 site/build_site.py && open site/dist/index.html
```

**从零重跑整条链路**（需要先拉数据，约 350MB，走 OpenDota 公开 API）：

```bash
python3 fetch_pro_all.py              # 拉 2020-2026 全部职业比赛
python3 -m model.l0_align             # 按选手 ID 反查血统    → model/lineage.json
python3 -m model.l1_strength          # Bradley-Terry 实力评分 → model/l1_rating.json
python3 -m model.l2_simulate          # 蒙特卡洛 20 万届 TI    → model/l2_predictions.json
python3 -m model.l2_blend             # 与赔率做 log-odds 融合 → model/l2_blended.json
python3 -m model.l4_players_report    # 选手排名与数据预测     → reports/p3_p4_players.*
python3 -m model.l4_fantasy_report    # 梦幻挑战分项矩阵       → reports/p1_fantasy_matrix.json
python3 -m model.l4_extremes_report   # 极值题（谁打出最高纪录）→ reports/p2_extremes.*
```

> `model/l3_player.py`（层次泊松选手模型）是**库**，不是入口——由上面三个 `l4_*_report` 调用。
> 后三个脚本都有 `--help`，输出路径可用 `--out` 覆盖，不会意外盖掉仓库里的产出物。

数据集本身不入库（`.gitignore` 排除了 `data/`），用 `fetch_pro_all.py` 可完整重取。

## 仓库结构

| 目录 | 内容 |
|---|---|
| `00-DESIGN.md` / `00-PLAN.md` | 设计文档（含 §10 已知限制 12 条）与实施计划 |
| `01-` … `06-*.md` | 前期调研：赛事事实、数据源、方法论文献、舆论场、Fantasy 规则 |
| `model/` | 全部建模代码，L0 对齐 → L1 实力 → L2 模拟/融合 → L3 选手 → L4 各类题目 |
| `tests/` | 162 个测试。**部分测试是经过变异验证的**——改坏对应实现会让它们变红 |
| `frozen/` | 各版本预测的哈希存证，`model/freeze.py` 可校验 |
| `reports/` | 面向人读的产出：对阵胜率表、选手预测、Fantasy 矩阵、极值题 |
| `site/` | 静态站生成器。所有数字从产出物读取，不手抄 |

## 已知限制（节选）

完整 12 条见 [`00-DESIGN.md`](00-DESIGN.md) §10。最需要先知道的三条：

- **Fantasy 的辅助槽结构性偏弱。** 18 项计分项里 Watcher 和 Lotus 取不到，而 Support Duo 槽的
  徽记全是蓝色，蓝色池只有 4/6。这个没法靠努力弥补。
- **抄作业那 16 格用的是纯模型，没融合赔率。** 因为博彩只开夺冠盘，没有「谁会 4-1」的盘，
  没有市场价可参照。所以会出现 Falcons 在夺冠概率排第 6、在抄作业里却填进 4-1 的情况。
- **分组还没公布。** 首轮谁打谁由主办方决定。公布之后重算的版本会准不少。

## 声明

本项目**不提供任何投注建议**。它是一次公开的预测质量实验，不是投注工具。

## License

[MIT](LICENSE)。比赛数据来自 [OpenDota](https://www.opendota.com/) 与
[Liquipedia](https://liquipedia.net/dota2/)，各自的使用条款以其官方声明为准。
