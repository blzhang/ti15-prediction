# TI15 (The International 2026) 事实底座调研

- 调研日期：2026-08-01 首轮 / **2026-08-02 第二轮补缺**（抓取时间点，所有"当前"数值均以此为准）
- 调研者：Claude research agent
- 可信度三档：**已核实**（≥2 个独立来源一致，或官方源）/ **存疑**（单一来源、来源间冲突、或来源为 SEO 站）/ **未查到**

---

## 0. 完成度

| 模块 | 状态 | 备注 |
|---|---|---|
| 1. 赛事本体（日期/地点） | ✅ 完成 | 已核实 |
| 1b. **赛制 / 总局数 N** | ✅ **完成** | Liquipedia 给出完整赛制；N 估算见 §1.6，**N ≈ 145（95% 带 138–153，硬边界 119–179）** |
| 1c. 奖金池 | ✅ 完成 | 底池 $1,600,000 + supporter bundle 销售额 30% 分成；见 §1.4 |
| 2. 参赛队全名单 | ✅ **完成** | Liquipedia 仲裁，§5 全部冲突已解；16 队正式名 + 别名对照见 §2.0 |
| 3. 首发名单 / 教练 / account_id | ✅ 完成 | 16×5 全部拿到，78/80 拿到 account_id；见 §2.3 |
| 3b. TI14→TI15 转会变动 | ✅ 完成 | 逐队 diff，见 §2.4 |
| 4. **官方预测面板题目原文** | ⚠️ **部分完成（但已查到边界在哪）** | 面板结构/分组/计分机制/奖励档位**已核实**（中英文原文都有）；**逐题题面仍未拿到，且已确认它不在客户端文件里、是服务端下发**；见 §3 |
| 5. 市场赔率 baseline | ⚠️ 部分完成 | Polymarket 已有（外部提供）；传统博彩拿到 5 队赔率（缺 11 队，无法精确去水，只能做条件归一）；见 §4 |

> 本文件采用增量落盘：每查完一小块立即更新。

**本轮新增的主力数据源：`liquipedia.net` MediaWiki API**（`action=parse&prop=text`）。
上一轮记录的"Liquipedia 被拦截"只对 WebFetch 成立；**用 curl 直连 API 完全可用**，是本轮突破口。
命令模板（注意 2 秒/次限速）：
```bash
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
curl --noproxy '*' --compressed -H 'User-Agent: TI15-research/1.0 (research use)' \
  'https://liquipedia.net/dota2/api.php?action=parse&page=The_International/2026&format=json&prop=text'
```
本地缓存：`lp_ti2026.json/.html/.txt`、`lp_ti2025.json/.html/.txt`、`rosters.json`、`account_ids.json`、`opendota_pros.json`（同目录）。

---

## 1. 赛事本体

### 1.1 日期 / 地点 / 场馆

| 项 | 内容 | 可信度 | 来源 |
|---|---|---|---|
| 赛事全称 | The International 2026（TI15） | 已核实 | 多源一致 + Liquipedia |
| 日期 | 2026-08-13 至 2026-08-23 | 已核实 | Liquipedia + GosuGamers/Hotspawn/Escorenews |
| 城市 | 中国上海 | 已核实 | Liquipedia + 多源 |
| 场馆 | 上海东方体育中心（Oriental Sports Center）—— Liquipedia 明确标注"(Playoffs)"，即**只有淘汰赛在该场馆** | 已核实 | Liquipedia infobox |
| 主办 | Valve；**执行方 PGL** | 已核实（新增 PGL） | Liquipedia infobox（Organizers: Valve, PGL） |
| Liquipedia 分级 | Tier 1 | 已核实 | Liquipedia |

> Liquipedia 页面顶部有 "This tournament page is under construction and is subject to major revisions." 的提示条——**赛前页面仍可能修订**，赛制与名单在开赛前应再核一次。

来源：
- https://liquipedia.net/dota2/The_International/2026
- https://www.gosugamers.net/dota2/news/77974-the-international-2026-venue-and-schedule-revealed

### 1.2 赛制（本轮全部补齐 —— Liquipedia 原文）

Liquipedia `Format` 节原文（英文）：

> **Group Stage (August 13 - 16)**
> - Swiss-system of sixteen teams
> - All matches are Bo3
> - **Top three teams** advance to playoffs
> - **4th to 13th place teams** proceed to an elimination round
> - **Remaining teams** are eliminated
> - **Elimination Round**
>   - Five teams advance to playoffs
>   - Remaining teams are eliminated
>
> **Main Event (August 20 - 23)**
> - **Double-elimination bracket**
> - **Grand Final is Bo5, all other matches are Bo3**

| 项 | 内容 | 可信度 | 来源 |
|---|---|---|---|
| 参赛队数 | 16 | 已核实 | Liquipedia |
| 小组赛形式 | 瑞士轮（Swiss-system），16 队 | 已核实 | Liquipedia + 多源 |
| **瑞士轮轮数** | **5 轮** | 已核实 | Hotspawn "sixteen teams, five rounds"；且 TI14 同结构确为 5 轮（Liquipedia TI2025 明列 Round 1–5 配对规则）；且预测题出现 "flawless(5-0)" 与 "4-1" 记录，只有 5 轮成立 |
| 小组赛 BO | **全部 BO3** | 已核实 | Liquipedia |
| 小组赛日期 | 8/13 – 8/16 | 已核实 | Liquipedia |
| 小组赛晋级线 | 前 3 名**直接进淘汰赛**；4–13 名进附加淘汰轮；14–16 名出局 | 已核实 | Liquipedia |
| 附加淘汰轮（Elimination Round） | 10 队打 **5 场 BO3**，5 队晋级、5 队出局。配对规则：**3-2 战绩队 vs 2-3 战绩队** | 已核实 | Liquipedia TI2026 bracket 表头 "3-2 vs 2-3 To Playoffs"；TI2025 原文 "Teams with a 3-2 record will be paired against teams with a 2-3 record" |
| 淘汰赛队数 | **8**（3 直接晋级 + 5 附加轮晋级） | 已核实 | Liquipedia |
| **淘汰赛是否双败** | **是，双败淘汰（Double-elimination）** | ✅ **已核实**（原缺口已解） | Liquipedia Format 节 |
| **胜者组/败者组结构** | UB: QF(4场) → SF(2场) → UBF(1场) = 7 场；LB: R1(2场) → QF(2场) → SF(1场) → LBF(1场) = 6 场；**无 bracket reset** | ✅ **已核实** | Liquipedia playoffs bracket，逐个 TBD 槽位点数得出 |
| **决赛 BO 几** | **BO5**（其余全部 BO3） | ✅ **已核实** | Liquipedia Format 节 |
| 淘汰赛日期/地点 | 8/20 – 8/23，上海东方体育中心 | 已核实 | Liquipedia |
| 小组赛地点 | 线上 / 非场馆（Liquipedia 只把场馆标给 Playoffs，与"8/20 才进场馆"一致） | 存疑（间接推定） | Liquipedia infobox + Escorenews |

> 8/16 到 8/20 的 3 天空档 = 小组赛结束到进场馆的转场期，与"只有淘汰赛在东方体育中心"吻合，原缺口的疑问解除。

### 1.3 瑞士轮配对规则（TI14 原文，TI15 页面尚未列出，**按惯例沿用但标存疑**）

TI2025（TI14）Liquipedia 明列，TI2026 页面尚未填这一节：

排名判据（依次）：1) 胜场数 → 2) 负场数 → 3) 小局胜率 → 4) 对手总胜场（Buchholz）→ 5) 对手平均小局胜率 → 6) 掷硬币。
配对：同战绩配对 / 尽量避免重复配对 / 尽量最小化排名距离。
分轮修正：R1 分两组、由赛事方指定对阵；R2/R3 只在组内配对；R4 只与另一组配对；R5 无特殊修正。

- 可信度：**存疑（这是 TI14 规则；TI15 页面此节为空，尚未确认是否照搬）**
- 来源：https://liquipedia.net/dota2/The_International/2025

### 1.4 奖金池 ✅（原缺口已解）

| 项 | 内容 | 可信度 | 来源 |
|---|---|---|---|
| TI15 底池（base prize pool） | **$1,600,000 USD** | 已核实 | Liquipedia TI2026 |
| 众筹分成机制 | **有** —— "An additional 30% from all supporter bundle sales are added to the prize pool" | 已核实 | Liquipedia TI2026 |
| 截至抓取时已众筹金额 | Liquipedia 显示 **$0 USD contributed** | 存疑（**几乎肯定是追踪器尚未更新**：supporter bundles 2026-07-31 才上线，抓取时只过了 1–2 天） | Liquipedia TI2026 |
| **TI14（2025）同机制实际终值** | 底池同为 $1,600,000 + 众筹 $1,281,791 = **最终 $2,881,791** | 已核实 | Liquipedia TI2025 |

> 建模含义：TI15 用的是与 TI14 **完全相同**的"$1.6M 底池 + bundle 销售额 30%"机制。若销量与 TI14 相当，最终池约 $2.8–2.9M。**不要引用 TI10 时代的 $40M 量级数字。**
> TI14 奖金分配（可作 TI15 分配比例先验，存疑=未确认 TI15 沿用）：冠军 42.5% / 亚军 13% / 季军 9% / 第4 6% / 5–6 名各 5% / 7–8 名各 4% / 9–13 名各 1.8% / 14–15 名各 1% / 16 名 0.5%。

### 1.5 资格赛周期 / 补丁

| 项 | 内容 | 可信度 | 来源 |
|---|---|---|---|
| 直邀公布日 | **2026-05-25** | 已核实 | Liquipedia TI2026（"Invites were announced on May 25."） |
| 公开预选赛 | 2026-06-09 – 06-12 | 存疑（单源） | GosuGamers |
| 地区预选赛 | 2026-06-15 – 06-28 | 存疑（单源） | GosuGamers |
| TI15 使用补丁 | 7.41e | 存疑（单源；Liquipedia TI2026 infobox 的 Version 字段**为空**，TI2025 填的是 7.39d） | win.gg / GosuGamers |

### 1.6 ★ 全赛事总局数 N 的估算（下游 prop 建模直接用）★

#### 1.6.1 场次（match / series）结构 —— 已核实

| 阶段 | BO 制 | 场次数 | 推导 |
|---|---|---|---|
| 瑞士轮 | BO3 | **40** | 16 队 × 5 轮 ÷ 2 = 40 |
| 附加淘汰轮 | BO3 | **5** | 10 队（4–13 名）两两配对 = 5 场；Liquipedia bracket 正好 5 个槽 |
| 淘汰赛胜者组 | BO3 | **7** | UBQF 4 + UBSF 2 + UBF 1 |
| 淘汰赛败者组 | BO3 | **6** | LBR1 2 + LBQF 2 + LBSF 1 + LBF 1 |
| 总决赛 | **BO5** | **1** | 无 bracket reset |
| **合计** | — | **59 场**（58 场 BO3 + 1 场 BO5） | |

#### 1.6.2 小局数（game）N —— 三种口径

BO3 出 2 或 3 局；BO5 出 3/4/5 局。

**(a) 硬边界（结构上限下限，100% 确定不会越界）**

- 最少：58×2 + 3 = **119 局**
- 最多：58×3 + 5 = **179 局**

**(b) 抛硬币基准（p=0.5，两队等强）**

- BO3 期望 2.5 局 → 58 × 2.5 = 145.0
- BO5 期望 4.125 局
- **N ≈ 149.1**

**(c) TI14 实测频率外推（推荐用这个做中心值）**

TI14 实测（Liquipedia TI2025 全部比分逐场统计）：

| 阶段 | 场次 | 小局 | 局/场 |
|---|---|---|---|
| 瑞士轮 | 39*（结构应为 40，Liquipedia 赛程只列出 39，见下注） | 96 | 2.462 |
| 附加淘汰轮 | 5 | 12 | 2.400 |
| 淘汰赛 BO3 | 13 | 31 | 2.385 |
| 总决赛 BO5 | 1 | 5 | 5 |
| **TI14 合计** | **58** | **144** | **2.483** |

TI14 的 57 场 BO3 里，打满 3 局的有 **25 场**，即 **q = P(BO3 打满 3 局) = 25/57 = 0.4386**（低于抛硬币的 0.50，符合"强队更容易 2-0"的直觉）。

把 q 套到 TI15 的 58 场 BO3：
- BO3 小局期望 = 58×2 + 58×0.4386 = 116 + 25.4 = **141.4**
- BO5 小局期望 ≈ 4.1（TI14 实际打了 5 局）
- **N 中心值 ≈ 145.5**
- 标准差 ≈ √(58 × 0.4386 × 0.5614) ≈ 3.8 局
- **95% 区间 ≈ 138 – 153**

#### 1.6.3 结论（下游直接引用）

> **N（全赛事总小局数）**
> - **点估计：≈ 145**（TI14 实测频率外推；抛硬币口径为 149，取两者中偏低更稳）
> - **95% 区间：138 – 153**
> - **硬边界：119（最少）– 179（最多）**
> - 可信度：**已核实**（场次结构来自 Liquipedia 官方赛制；局数分布来自 TI14 同赛制实测）

⚠️ **两个必须提醒下游的点：**

1. **调用方提到的 193 和 130 两个数都不对。** 193 **超过了结构硬上限 179**，物理上不可能；130 低于 95% 区间下沿（要出现需要远多于历史的横扫率）。请用 145 重算。

2. **N 的口径（scope）必须先定清楚**，因为官方预测面板文案把赛事分成 "Swiss stage" 和 "the bracket" 两块，而 Liquipedia 把"附加淘汰轮"归在 Group Stage 下。三种口径的 N 差很多：

| 口径 | 场次 | N 点估计 | N 硬边界 | **对应官方预测题组** |
|---|---|---|---|---|
| 仅瑞士轮 5 轮 | 40 BO3 | **98.5** | 80 – 120 | —（题组不是按这个切的） |
| 瑞士轮 + 附加淘汰轮 | 45 BO3 | **110.7** | 90 – 135 | ✅ **Road to TI Predictions / TI之路赛事预测** |
| 仅主赛事（8 队双败，含决赛） | 13 BO3 + 1 BO5 | **35.1** | 29 – 44 | ✅ **The International Predictions / 国际邀请赛赛事预测** |
| **全赛事** | 58 BO3 + 1 BO5 | **145.5** | 119 – 179 | 两组之和 |

> ⚠️ **注意最后一列 —— 这是本轮从 Dota 2 客户端文件里挖出来的（见 §3.2b(1)）。**
> 官方预测题**本来就分成两组**，而且**分界线不在"瑞士轮 vs 淘汰赛"，而在"Road to TI（瑞士轮＋附加淘汰轮）vs The International（8 队主赛事）"**。
> 也就是说：**附加淘汰轮的 5 场 BO3 算在"Road to TI"这一组里，不算主赛事。** 如果按直觉把它划到淘汰赛那边，两组的 N 会各错约 12 局。

3. `P = 1 − (1−p)^N` 这个公式**假设每局独立同分布**。瑞士轮里强弱队对阵分布随轮次变化（第 1 轮随机、后面同战绩配对），而淘汰赛全是强队互殴，因此对"单场高击杀/高 GPM"这类阈值题，**各阶段的 p 并不相同**，直接用全赛事 N 会偏。建议分阶段算再合并：`P = 1 − Π_stage (1−p_stage)^(N_stage)`。

*注：TI14 瑞士轮结构上应为 40 场（16×5÷2），Liquipedia 赛程表只列出 39 场有比分的记录（9/4 16 场、9/5 12 场、9/6 11 场）。差 1 场原因未查明（可能是弃权/录入缺失）。上表按实测 39 场算局/场比率，而 TI15 的 N 按结构 40 场算，这是保守方向。*

---

## 2. 参赛队全名单（16 队）—— Liquipedia 仲裁版

> **§5 的全部队名冲突本轮已解决。** 仲裁源：Liquipedia `The_International/2026` 参赛队卡片（官方赛事页），并用 OpenDota `proPlayers` 接口的 `team_name` 字段做第二重交叉验证。

### 2.0 ★ 队名 / 别名对照表（下游做实体对齐必读）★

| Liquipedia 正式名（TI15 参赛名） | 常见别名 / 旧名 / 媒体误写 | 关系 | 可信度 |
|---|---|---|---|
| **BoomBoys** | BetBoom Team、BB Team | **同一队改名**。TI14 参赛名 "BB Team"，五人中 gpk~/MieRo/Save-/Kataomi 四人留任。OpenDota `team_name` 亦为 "BoomBoys" | 已核实 |
| **Iron Wing** | Tundra Esports、1win Team、1w Team | Liquipedia 注：**"The roster of Tundra Esports was transferred to 1w Team. The team will compete as Iron Wing."** 即 Tundra 阵容整体转会 1w Team，TI15 以 "Iron Wing" 名义参赛。OpenDota `team_name` 显示为 "1w" | 已核实 |
| **TEAM VISION** | PARIVISION、PVISION、"PARI" | **同一队改名**。TI14 参赛名 "PVISION"，五人中 Satanic/No[o]ne-/9Class/Dukalis 四人留任。OpenDota `team_name` = "TEAM VISION" | 已核实 |
| **HULIGANI** | L1GA Team、L1GA TEAM | **同一队**。Liquipedia 参赛名 HULIGANI；OpenDota 里这五人的 `team_name` 全部是 **"L1GA TEAM"**。上一轮 Hotspawn 写的 "L1GA Team (HULIGANI)" 是对的 | 已核实（双源交叉） |
| **LGD Gaming** | ex-HEROIC | **Hotspawn 原来是对的，之前"高度怀疑讹误"的判断作废**。LGD Gaming 确实占**南美 1 席**，阵容是全南美的 ex-HEROIC 班底（Yuma / Wisper / KJ / 教练 kaffs 均来自 TI14 的 HEROIC）。OpenDota `team_name` = "LGD Gaming" | 已核实（双源交叉） |
| **GamerLegion** | ex-Wildcard | 北美 1 席。5 人中 4 人（RCY/Fayde/Bignum/Speeed）来自 TI14 的 Wildcard | 已核实 |
| **Vici Gaming** | ex-Team Tidebound 核心 | 中国 2 席。shiro/Bach/y` 来自 TI14 的 Team Tidebound，Xm/XinQ 来自 TI14 的 Xtreme Gaming | 已核实 |

> **注意**：`PARIVISION` 与 `TEAM VISION` 不是两支队，是同一支队的两个名字；`BetBoom/BB Team` 与 `BoomBoys` 同理。Polymarket 盘口用的 "TEAM VISION"/"BoomBoys" 正是**当前正确名**，与 Liquipedia 一致——这也反向佐证了两处改名属实。

#### ★ 改名的真正原因（重要，会改变你对"这是不是同一支队"的判断）★

> **Valve 禁止博彩品牌名出现在 TI 赛场上，这三支队是被迫换的"参赛用名"，不是组织改名、更不是换队。**
>
> 原文（媒体转述）：*"Valve does not permit betting on brand names at TI. Teams will compete under their approved names—so BetBoom, for example, will be representing themselves as BoomBoys. Iron Wing is the 1win team (ex-Tundra Esports roster with 33 and bzm), and Team Vision is PARIVISION."*
>
> - **BetBoom**（俄罗斯博彩商）→ 参赛名 **BoomBoys**
> - **1win**（博彩商）→ 参赛名 **Iron Wing**
> - **PARI**（博彩商）/ PARIVISION → 参赛名 **TEAM VISION**
> - Team Yandex 的 Yandex 不是博彩商，不受影响
>
> - 可信度：**存疑（媒体转述，单源，未找到 Valve 规则原文）**，但**与 Liquipedia 的措辞完全吻合**（Liquipedia 用的是 "The team **will compete as** Iron Wing"，正是"参赛用名"的说法，而不是"更名为"）。
>
> **建模含义（关键）**：
> 1. 这三支队的 **org 本体和历史战绩都是连续的**，不要因为名字变了就当成新队。查历史要用 BetBoom / 1win / PARIVISION（或 TI14 参赛名 BB Team / Tundra / PVISION）。
> 2. 这也解释了为什么博彩盘口和 Polymarket 用的名字不一样：**博彩站用 org 真名（PARIVISION、1win Team、BetBoom），Polymarket 和 Liquipedia 用 TI 参赛名（TEAM VISION、Iron Wing、BoomBoys）**。做赔率交叉验证时**必须先把这两套名字对齐**，否则会把同一支队当成两支。

### 2.1 直邀（Invited，7 队）

| # | Liquipedia 正式名 | 备注 | 可信度 |
|---|---|---|---|
| 1 | Aurora Gaming | | 已核实 |
| 2 | BoomBoys | ex-BB Team / BetBoom | 已核实 |
| 3 | Iron Wing | ex-Tundra 阵容 → 1w Team | 已核实 |
| 4 | Team Falcons | **TI14 卫冕冠军** | 已核实 |
| 5 | Team Liquid | | 已核实 |
| 6 | Team Yandex | | 已核实 |
| 7 | Xtreme Gaming | TI14 亚军 | 已核实 |

### 2.2 地区预选赛（Qualified，9 席）

| # | Liquipedia 正式名 | 席位 | 可信度 |
|---|---|---|---|
| 8 | Team Spirit | Europe 1st–2nd | 已核实 |
| 9 | TEAM VISION | Europe 1st–2nd | 已核实 |
| 10 | Nigma Galaxy | Europe 3rd–4th | 已核实 |
| 11 | HULIGANI | Europe 3rd–4th | 已核实 |
| 12 | Team Resilience | China 1st | 已核实 |
| 13 | Vici Gaming | China 2nd | 已核实 |
| 14 | OG | Southeast Asia 1st | 已核实 |
| 15 | GamerLegion | North America 1st | 已核实 |
| 16 | LGD Gaming | **South America 1st** | 已核实 |

槽位分配（实测）：**Europe 4 + China 2 + SEA 1 + NA 1 + SA 1 = 9**。与上一轮记录一致；东欧/西欧本届合并为单一 Europe 预选赛得到确认（TI14 分 Western/Eastern Europe，TI15 只有 "Europe"）。

赛区分布：中国队 3 支（Xtreme Gaming 直邀 + Team Resilience + Vici Gaming）。

### 2.3 各队首发五人 / 位置 / 教练 / OpenDota account_id ✅（原缺口已解）

位置编号 = Liquipedia 标注（1=carry / 2=mid / 3=offlane / 4=soft support / 5=hard support）。
`account_id` 来自 OpenDota `https://api.opendota.com/api/proPlayers`（5081 条 pro 名录），按 `name` 精确匹配 + `team_name` 交叉确认。

**可信度说明**：78/80 名选手拿到 account_id。标 ⚠️ 的是 Liquipedia 昵称与 OpenDota `name` 字段拼写不完全一致、靠队伍归属推定的，请下游二次核对。

#### 直邀队

| 队 | 1 (carry) | 2 (mid) | 3 (off) | 4 (soft sup) | 5 (hard sup) | 教练 |
|---|---|---|---|---|---|---|
| **Aurora Gaming** | Nightfall `124801257` (RU) | Mikoto `301750126` (ID) | Ws `126842529`⚠️(MY) | Mira `256156323` (UA) | kaori `320219866` (UA) | kpii (AU) |
| **BoomBoys** | Kiritych~ `172099728` (RU) | gpk~ `480412663` (RU) | MieRo `165564598` (RU) | Save- `317880638` (MD) | Kataomi `196878136`⚠️(RU) | boolk (RU) |
| **Iron Wing** | Pure `331855530` (RU) | bzm `93618577` (BG) | 33 `86698277` (IL) | Ari `346412363` (UK) | Whitemon `136829091` (ID) | MoonMeander (CA) |
| **Team Falcons** | skiter `100058342` (SK) | Malr1ne `898455820` (RU) | ATF `183719386`⚠️(JO) | Cr1t- `25907144` (DK) | Sneyking `10366616` (US) | Aui_2000 (CA) |
| **Team Liquid** | m1CKe `152962063` (SE) | Nisha `201358612` (PL) | Ace `97590558`⚠️(DK) | Boxi `77490514` (SE) | tOfu `16497807` (DE) | Blitz (US) + Jabbz (DE) |
| **Team Yandex** | watson `171262902`⚠️(KZ) | CHIRA_JUNIOR `312436974` (RU) | DM `56351509` (RU) | Saksa `103735745` (MK) | Malady `93817671`⚠️(KZ) | Accell (RU) |
| **Xtreme Gaming** | Ame `898754153` (CN) | NothingToSay `173978074` (MY) | Xxs `129958758` (CN) | fy `101695162` (CN) | xNova `94296097` (MY) | LaNm (CN, Head) + Maps (CN, Asst) |

#### 预选赛队

| 队 | 1 (carry) | 2 (mid) | 3 (off) | 4 (soft sup) | 5 (hard sup) | 教练 |
|---|---|---|---|---|---|---|
| **Team Spirit** | Yatoro `321580662` (UA) | Larl `106305042` (RU) | Collapse `302214028` (RU) | not me `218231587` (RU) | rue `847565596` (RU) | Miposhka (RU) + MiLAN (BA) |
| **TEAM VISION** | Satanic `1044002267` (RU) | No[o]ne- `106573901` (UA) | Noticed `195108598` (RU) | 9Class `164199202` (RU) | Dukalis `73401082` (RU) | **Puppey** (EE) |
| **Nigma Galaxy** | SumaiL `111620041` (PK) | lorenof `210053851` (UA) | Davai `138880576` (BE) | OmaR `152168157` (LB) | GH `101356886` (LB) | KuroKy (DE) |
| **HULIGANI** | ssnovv1 `320017600` (RU) | Mirage\` `140251702`⚠️(KZ) | Corrupted `92487440` (RU) | sayuw `145065875` (RU) | RESPECT `123787715` (BY) | TheChosenOne (BY) |
| **Team Resilience** | YSR-04E `170896543` (CN) | Echozz `315272623` (CN) | niu `145957968` (CN) | planet `150961567` (CN) | zzq `249835593` (CN) | Super (CN) |
| **Vici Gaming** | shiro `320252024` (CN) | Xm `137129583` (CN) | Bach `118134220` (CN) | XinQ `157475523` (CN) | y\` `111114687` (CN) | Yao (CN) |
| **OG** | Natsumi `355168766` (PH) | Yopaj- `324277900` (PH) | Raven `132309493` (PH) | TIMS `155494381` (PH) | skem `100594231` (PH) | 343 (MY) |
| **GamerLegion** | Ghost `206642367` (MY) | RCY `154974246` (US) | Fayde `160119017` (US) | Bignum `90423751` (UA) | Speeed `191362875` (US) | Mangusu (RO) |
| **LGD Gaming** | Yuma `177203952` (NI) | TaiLung `1026694469` (PE) | Wisper `292921272` (BO) | Thiolicor `105045291` (BR) | KJ `81306398`⚠️(BR) | kaffs (BR) + fcr (BR, Asst) |

**⚠️ 需二次核对的 6 个 account_id**（Liquipedia 昵称 ↔ OpenDota `name` 字段不完全一致，靠队伍归属推定）：
- `Ws` → OpenDota name `Ws\`` (126842529)
- `Kataomi` → OpenDota name `Kataomi\`` (196878136)
- `ATF` → OpenDota name `AMMAR_THE_F` (183719386)（ATF = Ammar The F，业内公认缩写，可信度较高）
- `Ace` → OpenDota name `Ace ♠` (97590558)
- `watson` → OpenDota name `医者watson\`` (171262902)
- `Malady` → OpenDota name `Maladych` (93817671)
- `Mirage\`` → OpenDota name `Mirage\`雨` (140251702)
- `KJ` → OpenDota name `KingJungles` (81306398)（**这条最弱**，纯靠 LGD Gaming 队伍归属 + 巴西籍推定）

**另外两个易踩的坑：**
- `Yatoro` 在 OpenDota 名录里有 9 个同名/近名条目，其中 `134658652` 的 `name` 是小写 "yatoro" 但 `team_name` 是 "avice moment creator"（山寨号）。**正主是 `321580662`（team_name = Team Spirit）。**
- `Satanic` 同样有 4 个候选，`241107899` 的 team_name 是 "Grey Track"（不是 TI15 这位）。**正主是 `1044002267`（team_name = TEAM VISION）。**
- OpenDota 的 `team_name` 字段**含历史成员、有滞后**（例如 OG 名下还挂着 Ceb、TORONTOTOKYO；Nigma Galaxy 名下挂着 11 人含 Miracle-/No!ob）。**首发五人以 Liquipedia 为准，OpenDota 只用来取 account_id。**

### 2.4 ★ TI14（2025）→ TI15 转会变动 ★ ✅（原缺口已解，建模关键项）

方法：逐队对比 Liquipedia `The_International/2025` 与 `The_International/2026` 的参赛名单。
**"历史战绩有效性"是我给下游的判断，不是来源里的原话。**

#### A. 阵容完全没动（历史战绩全额可用）

| 队 | 变动 | 历史战绩有效性 |
|---|---|---|
| **Team Falcons** | **0 人变动**（skiter/Malr1ne/ATF/Cr1t-/Sneyking + 教练 Aui_2000 全部留任） | ✅ **完全有效**。TI14 冠军原班人马 |

#### B. 换 1 人（历史战绩基本可用）

| 队 | 变动 | 去向/来源 |
|---|---|---|
| **BoomBoys**（ex-BB Team） | pos1 **Pure → Kiritych~**；教练 boolk 留任 | Pure 去了 Iron Wing |
| **TEAM VISION**（ex-PVISION） | pos3 **DM → Noticed**；教练 **Astini → Puppey** | DM 去了 Team Yandex。**Puppey 首次以教练身份带队** |

#### C. 换 2 人 / 有重大角色变动（历史战绩打折）

| 队 | 变动 | 说明 |
|---|---|---|
| **Team Spirit** | pos4 位置来了 **not me**（新）；**rue 从 pos4 挪到 pos5**；**队长 Miposhka 从选手转任教练**；教练 Silent → Miposhka + MiLAN | ⚠️ **重大**。Miposhka 是 Spirit 多年的队长/指挥/pos5，转教练意味着场上指挥体系换人。Yatoro/Larl/Collapse 核心三人留任 |
| **Team Liquid** | pos3 **SaberLight → Ace**；pos5 **Insania → tOfu**；教练组 kpii 离开（去 Aurora 当教练） | SaberLight 现在是 TI15 英文解说台的分析师（等于确认已退出 Liquid 首发） |
| **Xtreme Gaming** | pos2 **Xm → NothingToSay**；pos4 **XinQ → fy**；教练 **xiao8 → LaNm**（+ Maps 助教） | Xm、XinQ 双双转会 Vici Gaming。Ame/Xxs/xNova 留任 |
| **Nigma Galaxy** | pos1 **Ghost 走**（→ GamerLegion）；**SumaiL 从 pos2 挪到 pos1**；pos2 来 **lorenof**；pos3 **No!ob → Davai**；教练 KuroKy 留任 | 2 进 2 出 + 核心位置变动 |
| **Iron Wing**（ex-Tundra） | pos1 **Crystallis → Pure**；pos4 **Saksa → Ari**；pos5 Whitemon 归位（TI14 因签证问题由 Tobi 顶替）；教练 MoonMeander 留任 | Saksa 去了 Team Yandex。bzm/33 留任 |

#### D. 换 3 人及以上 / 全新阵容（**历史战绩基本作废**）

| 队 | 变动 | 说明 |
|---|---|---|
| **Aurora Gaming** | **换 3 人**：kiyotaka / TORONTOTOKYO / panto 全部离队；**Mikoto / Ws / kaori 进队**；教练 **G → kpii** | ⚠️ 只剩 Nightfall(1)、Mira(4) 两人。TI14 的 Aurora 数据对 TI15 的 Aurora 参考价值很低 |
| **Vici Gaming** | **TI14 未参赛，全新拼装队**：shiro/Bach/y\` 来自 TI14 的 **Team Tidebound**，Xm/XinQ 来自 TI14 的 **Xtreme Gaming** | ⚠️ VG 这个"队"在 TI14 不存在。要建模只能拆成"Tidebound 三人组 + XG 两人"的组合先验 |
| **Team Yandex** | **TI14 未参赛**：DM 来自 PVISION、Saksa 来自 Tundra，watson/CHIRA_JUNIOR/Malady 为新组合 | ⚠️ 无 TI 层级的队级历史 |
| **OG** | **TI14 未参赛，全菲律宾新阵容**：Raven 来自 TI14 的 **Team Nemesis**(pos3)，TIMS 来自 TI14 的 **BOOM Esports**(pos4)，**skem 从 TI14 的 Team Nemesis 教练改回当选手(pos5)**，Natsumi/Yopaj- 为新血 | ⚠️ OG 阔别 TI 四年，队级历史完全断档 |
| **GamerLegion** | 主体是 TI14 的 **Wildcard**（RCY/Fayde/Bignum/Speeed 四人留任），pos1 **Yamsun → Ghost**（ex-Nigma）；教练 BliNcc → Mangusu（ex-HEROIC 助教） | 若把它当 "Wildcard 换 1 人" 处理，历史战绩**可用**；若按队名 GamerLegion 查则查不到历史 |
| **LGD Gaming** | 主体是 TI14 的 **HEROIC**（Yuma/Wisper/KJ + 教练 kaffs 留任），**4nalog / Scofield 出**，**TaiLung / Thiolicor 进** | 换 2 人。同上：按 "HEROIC" 查历史才有数据 |
| **Team Resilience** | TI14 未参赛。planet 来自 TI14 的 **Team Tidebound**(pos4)，niu 是 TI14 Tidebound 的教练、现在当 pos3 选手 | ⚠️ 无队级历史 |
| **HULIGANI / L1GA TEAM** | TI14 未参赛，五人全部无 TI 履历 | ⚠️ 无队级历史 |

#### E. TI14 参赛但 TI15 缺席的队（做历史 baseline 时要剔除）

Team Tidebound（解散/人员分流至 VG 与 Team Resilience）、Yakutou Brothers、Natus Vincere、Team Nemesis、BOOM Esports、Wildcard（→GamerLegion）、HEROIC（→LGD）、Gaimin Gladiators（TI14 前退赛，由 Yakutou Brothers 替补）。

#### F. 建模含义速查（我的判断，非来源原话）

| 历史战绩可用度 | 队 |
|---|---|
| 🟢 高（0–1 人变动） | Team Falcons、BoomBoys、TEAM VISION |
| 🟡 中（2 人变动或需按旧队名查） | Team Liquid、Xtreme Gaming、Nigma Galaxy、Iron Wing、Team Spirit、GamerLegion(查 Wildcard)、LGD Gaming(查 HEROIC) |
| 🔴 低（3+ 人变动或队级历史断档） | Aurora Gaming、Vici Gaming、Team Yandex、OG、Team Resilience、HULIGANI |

> **实体对齐提醒**：做 TI14→TI15 的队级时间序列时，必须按 **org 改名映射**（BB Team→BoomBoys、PVISION→TEAM VISION、Tundra→Iron Wing、Wildcard→GamerLegion、HEROIC→LGD Gaming）来拼历史，直接按队名字符串 join 会丢掉 5 支队的全部历史。

---

## 3. 「TI15 预测出了」到底指什么（最高优先级，⚠️ 仍有缺口）

### 3.1 结论：官方游戏内预测面板**确认存在**（沿用上一轮，已核实）

| 项 | 内容 | 可信度 | 来源 |
|---|---|---|---|
| 存在性 | The International 2026 Compendium 内含 **Predictions** 面板 | 已核实（多源一致） | Valve 官方公告转载 / Hotspawn / GosuGamers |
| 发布日期 | **2026-07-30 / 07-31**（Valve 官方博文标题："The International: Predictions, Fantasy, and Supporter Bundles"，与 7.41e 补丁、重做的 fantasy、16 队 supporter bundles 同期） | 已核实 | changelog.gg / patchbot.io（均为 Valve 官方博文镜像）/ GosuGamers |
| 覆盖范围 | **同时覆盖瑞士轮小组赛与主赛事正赛（main bracket）** —— 官方文案分两段问："How will the Swiss matches shake out?" 与 "What about the bracket?" | 已核实（官方博文镜像原文） | changelog.gg |
| 截止时间 | **在首场比赛开打前**，官方原文：*before the first match starts (10am CST, Thursday 8/13)* | 已核实（官方博文镜像原文） | changelog.gg |
| Valve 的挑衅式说明 | 官方原文：*Exactly zero have ever gotten the full Swiss stage results correct.* | 已核实（官方博文镜像原文） | changelog.gg |
| 详细规则所在位置 | 官方博文明确指路：*Look for more information, including reward tiers and lots of details, in the **Rewards section of the main Dota 2 menu**.* | 已核实 | changelog.gg |
| 奖励 | 预测与 Fantasy 顶尖玩家可得 Tyrian Regalia（Disruptor / Nyx Assassin / Drow Ranger / Storm Spirit / Timbersaw 五件 Immortal 重制，紫色配色）；另有 Terrain Token、$150 实体 Aegis 复刻折扣 | 存疑（单源为主） | Hotspawn / VGTimes |

**用户说的「TI15 预测出了」，最可能指的就是 2026-07-30/31 上线的 Compendium 预测面板**，时间线高度吻合。

### 3.2 已知题目内容（**题面仍不完整** —— 面板结构见下面 3.2b，已突破）

已确认的题目线索：

| 题目 | 原文 | 题型分类 | 层面 | 可信度 | 来源 |
|---|---|---|---|---|---|
| 瑞士轮全胜队 | "pick the team that has a flawless run"（即 5-0 的那支队） | **「是谁」型** | **战队层面** | 存疑（媒体转述，非官方原文） | Escorenews / Hotspawn |
| 瑞士轮 4-1 队 | "then two teams that finish with a 4-1 match record" | **「是谁」型**（多选 2） | **战队层面** | 存疑（同上） | Escorenews / Hotspawn |
| 其余瑞士轮题 | 媒体用 "et cetera" 带过，未列全 | 未知 | 未知 | 未查到 | — |
| 主赛事（bracket）题 | 官方只说 "What about the bracket?"，未展开 | 未知 | 未知 | 未查到 | — |

**从"5-0 + 两支 4-1"这个结构可以反推**：瑞士轮预测题是**按最终战绩分档填人**的（1 支 5-0、2 支 4-1、…），这与 §1.2 的晋级线（前 3 名直接晋级 = 5-0 那 1 支 + 4-1 那 2 支）完全吻合，互为佐证。**可信度：已核实（结构自洽）**，但**具体题面文字仍是转述**。

### 3.2b ★ 从 Dota 2 客户端本地化文件挖出的面板结构（本轮最大进展）★

**方法**：Dota 2 客户端资源镜像仓库 `github.com/dotabuff/d2vpkr`（最后更新 **2026-08-01**，是当前版本）里的
`dota/resource/localization/dota_english.txt` 与 `dota_schinese.txt`，逐 key 提取所有 `*2026*` 的赛事通行证字符串。
可信度：**已核实（这是 Valve 客户端一手文件，不是媒体转述）**。

#### (1) ★ 预测题分成**两组**，不是一组 ★

| key | 英文原文 | 中文原文 |
|---|---|---|
| `DOTA_Score2026_PredictionsRTTI` | `<b>Road to TI Predictions</b>: {d:correct_predictions_rtti} Correct Predictions ({d:predictions_rtti_score} Points)` | `<b>TI之路赛事预测</b>：{d:correct_predictions_rtti}项预测正确（{d:predictions_rtti_score}点积分）` |
| `DOTA_Score2026_PredictionsTI` | `<b>The International Predictions</b>: {d:correct_predictions_ti} Correct Predictions ({d:predictions_ti_score} Points)` | `<b>国际邀请赛赛事预测</b>：{d:correct_predictions_ti}项预测正确（{d:predictions_ti_score}点积分）` |

**"Road to TI" 与 "The International" 是 Valve 的正式阶段品牌名**，含义在 TI14 页面上有明确定义（Liquipedia TI2025 原文）：
> *"the group stage and the elimination round were branded as part of **The Road to The International**, while the playoffs were branded as **The International** itself."*

⇒ **两组预测题的覆盖范围因此可以确定**（可信度：已核实）：

| 预测组 | 中文 | 覆盖阶段 | 对应场次 | 对应小局 N |
|---|---|---|---|---|
| **Road to TI Predictions** | TI之路赛事预测 | 瑞士轮 5 轮 **+ 附加淘汰轮** | 45 场 BO3 | **≈ 110.7**（硬边界 90–135） |
| **The International Predictions** | 国际邀请赛赛事预测 | 主赛事 8 队双败（含决赛） | 13 场 BO3 + 1 场 BO5 | **≈ 35.1**（硬边界 29–44） |

> 这解答了 §3.3 里"主赛事题是否一并截止"的疑问的一半：**题目本身是分两组的**。（是否分两次开放/截止仍未确认。）

#### (2) ★ 计分机制：按"答对题数"记分，每题二元判定 ★

字符串模板是 `{d:correct_predictions} Correct Predictions ({d:predictions_score} Points)` —— **计的是"答对了几项"，不是连续分数**。

⇒ **每道题都是二元的对/错**，没有部分得分、没有连续量的偏差惩罚。
可信度：**已核实**（客户端字符串结构）。
**每题具体多少分仍未查到**（`{d:predictions_score}` 是运行时填入的变量）。

#### (3) 奖励档位（原"reward tiers"缺口，已解）

| key | 英文 | 中文 |
|---|---|---|
| `..._Rewards_RankReq_Top100` | Top 100 Players | 前100名玩家 |
| `..._Rewards_RankReq_Top1500` | Top 1500 Players | 前1500名玩家 |
| `..._Rewards_RankReq_Top5Pct` | 95th Percentile | 第95百分位 |
| `..._Rewards_RankReq_Top10Pct` | 90th Percentile | 第90百分位 |
| `..._Rewards_RankReq_Top15Pct` | 85th Percentile | 第85百分位 |
| `..._Rewards_Header_Witness` | Tyrian Regalias | 云紫上品 |
| `..._Rewards_Header_Terrain` | Terrain Tokens | — |
| `..._Rewards_Header_Aegis` | Aegis Discount（`{d:reward_count}% Off`） | — |
| `..._Rewards_Header_DotaPlus` | Dota Plus（`{reward_count} Month(s)`） | — |
| `..._ShardsRewardDescription` | Earn {d:shard_reward} Dota+ Shards for every {d:shard_interval} points | — |

最低奖励档是 **85th Percentile**，与媒体说的"只有 15% 的参与者能拿到奖励"完全吻合（互为佐证，可信度提升为已核实）。

**排名结算日** —— ⚠️ **中英文本身对不上，如实记录**：
- 英文 `DOTA_Compendium2026_Rewards_RankBody` = *"Determined after The International on **August 27th**"*
- 中文同 key = *"国际邀请赛结束后**8月28日**确定"*
- 差 1 天，倾向是时区差（Valve 本地化常见），但**未核实**。

#### (4) 分成比例（佐证 §1.4）

`DOTA_Compendium2026_RevenueDistributionSummary`
- EN: *"50% of all purchases goes directly to the team or talent and 30% goes to The International prize pool."*
- CN: *"50%的销售所得将归于战队或解说，30%将进入国际邀请赛的总奖金。"*

⇒ 与 Liquipedia 的"30% 进奖金池"完全一致（可信度：已核实，双源）。Valve 自留 20%。

#### (5) ★ 决定性发现：题面**不在客户端文件里** ★

在 43,971 条英文本地化条目中：
- 存在的 2026 通行证 key 共 68 条，**全部是界面框架文字**（页签名、奖励档位、分成说明、结算日…）
- **没有任何一条是预测题的题面**。搜 `Predictions2026` = 0 命中；搜 `swiss` 只命中 TI10 时代的两条旧 key；搜值里含 `flawless` 只命中德鲁伊/卓尔的饰品文本，与 TI 无关。
- 对比：TI6–TI10 时代的题面是硬编码在本地化文件里的（仓库里还留着 `DOTA_Compendium_Predictions_First_NA_Team`、`DOTA_ChangeLog_Ti6BracketPredictions` 等历史 key）。

⇒ **结论：TI15 的预测题面由服务端（GC）下发，不随客户端资源分发。**
⇒ **这意味着任何离线/网页途径都拿不到题面**，包括本地化文件、SteamDB、社区镜像。**唯一途径是登录 Dota 2 客户端打开预测面板。**
可信度：**已核实**（穷举了当前版本的全部本地化条目）。

### 3.2c ★★ 2026-08-17：主赛事面板题面拿到了（用户客户端截图，一手）★★

§3.3 长期挂着的头号缺口——「主赛事题面由服务端下发，离线途径全部排除」——**已解**。
判断本身是对的（离线确实拿不到），补上它的方式正是 §3.5 路径 1：**用户本人打开客户端截图**。

**「国际邀请赛」页签不是分档填空，是一整张双败对阵表，14 场逐场点胜者。**

| 项 | 内容 | 可信度 |
|---|---|---|
| 面板入口 | 赛事预测 → 页签二「国际邀请赛」（页签一是「小组赛」） | 已核实（截图） |
| 锁定时间 | 截图显示「3 天后锁定」，即 **8/20 主赛事开打前** | 已核实（截图） |
| 题型 | **逐场点胜者**（每支队旁边一个圆钮），不是在 16 队里分档 | 已核实（截图） |
| 题数 | **14**：胜者组 A/B/C/D（第 1 轮）+ E/F（第 2 轮）+ G（胜者组决赛）+ 总决赛 + 败者组 6 场 | 已核实（截图逐格点数） |
| 小组赛页签状态 | 「未开放 ✓7/16」——**官方判分与本项目独立算出的 7/16 一致** | 已核实（截图） |

**截图同时第一手证实了败者组的交叉连法**（此前是从 TI14 页面反解出来的）：
败者组第 1 轮两场分别是「A 的败者 vs B 的败者」「C 的败者 vs D 的败者」；
败者组第 2 轮上半区标着「**F 的败者**」、下半区标着「**E 的败者**」——即
上半区 LBR1 胜者对的是**下半区**的 UBSF 负者，确实是交叉。与 `model/bracket.py` 的实现一致。

> **建模含义**：这道题与小组赛那 16 格**不是同一类问题**。16 格是分配问题
> （每档坑数固定，匈牙利算法）；对阵表是**路径**问题——填进第 2 轮的队必须是自己
> 在第 1 轮推上去的，所以「每场挑赢面最大的」通常不可行。
> 14 场各二选一 = 2^14 = 16384 种自洽填法，规模小到可以直接穷举求最优。
> 实现见 `model/l6_playoffs.py::best_bracket`。

---

### 3.3 ⚠️ 仍未拿到的关键信息 + **原因**

| 缺口 | 状态 | 原因 |
|---|---|---|
| 每题英文原文 | ✅ **2026-08-17 已解（主赛事部分）** | 原因判断是对的：题面由服务端下发，**不在客户端本地化文件里**（见 §3.2b(5)，已穷举 43,971 条条目），离线途径全部排除。补上它的方式是 §3.5 路径 1——**用户本人开客户端截图**。主赛事面板结构见 **§3.2c**。（小组赛那组已于 8/13 锁定并揭晓，16 格答案见站内抄作业页。）|
| 每题中文原文 | **未查到** | 同上。中文题面同样不在 `dota_schinese.txt` 里（该文件只有 67 条 2026 相关 key，全是界面框架） |
| 每题选项集合 | **未查到** | 同上 |
| 每题赋分/权重 | **未查到** | 已知计分是"答对题数 → 积分"（`{d:predictions_score}` 为运行时变量），但**每题几分未查到** |
| 题目总数 | **未查到** | `{d:correct_predictions_rtti}` / `{d:correct_predictions_ti}` 是运行时变量，客户端文件里没有题数 |
| **是否存在"选手个人层面"题**（单场最高击杀 / 最高 GPM / first blood 等） | **未查到 —— 且证据倾向"不存在"** | ①所有已知线索（flawless、4-1、bracket）**全部是战队层面题**；②客户端本地化里**没有任何选手统计类题面残留**；③ TI6–TI10 时代那批 `DOTA_Compendium_Predictions_*` 旧 key 仍在文件里，但**没有对应的 2026 版本**。⚠️ 仍属"未查到"，**不是"已证明不存在"** |
| **是否存在"阈值型"题** | **未查到 —— 且证据倾向"不存在"** | 已知题型都是「是谁」型（在 16 队里选队）。且计分是**二元对错**（§3.2b(2)），阈值题也可以是二元，故这条**不构成排除**，只能说没找到证据 |
| 主赛事题是否也在 8/13 一并截止 | **存疑（有新进展）** | ✅ 已确认题目**分成 Road to TI 与 The International 两组**（§3.2b(1)）。但官方只公布了一个截止时间（8/13 10am CST），**两组是否分批开放/截止仍未确认** |

> ⚠️ **给下游的强提醒（这一条比数据本身更重要）**
>
> 调用方的任务描述预设了预测面板里存在「选手个人层面题」和「阈值型题」（单场最高击杀 / 最高 GPM / first blood 会不会出现某数值以上），并据此要用 `P = 1−(1−p)^N` 建模。
>
> **但本轮调研没有找到任何证据表明 TI15 预测面板里存在这两类题。** 目前**全部**已知题目都是"在 16 支队里选出战绩符合某档的队"——这是**战队层面 + 「是谁」型**，跟 `1−(1−p)^N` 这个"至少发生一次"的公式**根本不是一回事**（选队题该用多项分布/排列组合，不是伯努利试验累积）。
>
> 历史上 TI 的 Compendium 确实出过赛事统计题（最长比赛时长、某英雄 ban 数等），但**不得据历史惯例填充 TI15**。
>
> **建议：在拿到客户端内逐题原文之前，不要开工建 prop 模型**——很可能靶子根本不是那个形状。拿题面的唯一可靠路径见 §3.5。

### 3.4 替代解释（若 3.1 判断有误）

用户所指也可能是以下之一，但优先级低于 3.1：
- 媒体/分析师的 power ranking 与预测稿（Hotspawn 出了小组赛预测稿、teamsmurf 出了 data-backed guide、dota2protips 有预测页、Escorenews 有"pro players and analysts"预测汇总）
- 博彩赔率盘口开出（见 §4）

### 3.5 拿到逐题原文的可行路径（给下游的行动建议）

按可行性排序：

1. ✅ **打开 Dota 2 客户端 → 主菜单 → Rewards → Predictions**（官方指定位置）。**本轮验证后，这是唯一可行路径**：中英文题面、选项、赋分全在这里。**本 agent 无客户端，做不到——需要用户本人或有客户端的机器去截图/抄题。**
2. ❌ **Dota 2 本地化文件 —— 本轮已试，此路不通。** `dota_english.txt` / `dota_schinese.txt` 里**没有 2026 预测题面**（详见 §3.2b(5)）。不要再花时间在这条路上。
3. 🟡 **社区数据站**：往年有第三方站（dota2protips 等）会把题目列全。本轮 WebSearch 未命中，但**开赛前几天（8/10–8/13）通常会出现**，届时可再搜一次。
4. 🟡 **Reddit r/DotA2** 的 compendium 讨论帖截图。本轮搜索未命中（搜索引擎结果里没有匹配的 Reddit 线程）。同样建议临近开赛再试。
5. 🟡 **Steam 社区讨论区** `steamcommunity.com/app/570/discussions`：搜索结果里出现过多条 TI 相关讨论帖，本轮未逐条打开。若要继续挖，这是下一个值得试的地方。

---

## 4. 市场基准（赔率 / 隐含概率）

### 4.1 Polymarket（外部已提供，本轮未重复抓取）

抓取时间点：2026-08-01 前后。归一化后前五：

| 队 | 隐含概率 |
|---|---|
| TEAM VISION | 18.3% |
| Team Yandex | 18.0% |
| BoomBoys | 11.1% |
| Team Spirit | 8.0% |
| Team Falcons | 7.6% |

- 总成交额仅 **$40,943**，**盘极薄**，价格信息量有限。
- 来源：https://polymarket.com/event/the-international-2026-winner-20260629212545745
- ✅ **本轮附带验证**：Polymarket 用的队名 "TEAM VISION" / "BoomBoys" 与 Liquipedia 正式名**完全一致**，说明盘口实体是对的（不是挂着 PARIVISION/BetBoom 的旧盘）。

### 4.2 传统博彩交叉验证 —— ⚠️ 部分完成

**本轮拿到 5 支队的十进制赔率（均为二手转述），缺另外 11 队。**

| 队（TI 参赛名） | org 真名 | 十进制赔率 | 原始隐含概率 1/O（含水） | 可信度 |
|---|---|---|---|---|
| TEAM VISION | PARIVISION | **4.50** | 22.2% | **存疑** |
| Team Spirit | Team Spirit | **5.00** | 20.0% | **存疑** |
| Team Yandex | Team Yandex | **6.00** | 16.7% | **存疑** |
| Iron Wing | 1win Team | **7.00** | 14.3% | **存疑** |
| Team Falcons | Team Falcons | **9.00** | 11.1% | **存疑** |
| 其余 11 队 | — | **未查到** | — | 未查到 |

- 可信度全部标**存疑**的原因：来自 esportbet.com / bookmaker-expert.com 的**搜索结果摘要转述**，两个原页面均 HTTP 403 打不开，**未标明具体庄家、未标明报价时间**。
- 摘要原话：*"Team Vision are the early favourites at $4.50, with Team Spirit close behind at $5.00. Defending champions Team Falcons are listed at $9.00."* 以及 *"Team Vision, Team Spirit, Team Yandex and 1win Team sitting at the top of the betting."*

**去水（remove overround）—— 只能做条件归一，不能做精确归一：**

已知 5 队的原始概率和 = 0.222+0.200+0.167+0.143+0.111 = **0.843**。
缺 11 队，**无法直接算出总 book（overround）**。但可以反推：若总 book 为 T，剩余 11 队合计只有 (T − 0.843)。
- 若 T = 1.00（无水，不可能）→ 11 队合计仅 0.157，人均 1.4%（赔率 ~70），**明显不合理**
- 若 T = 1.20（16 选手 outright 的典型水位）→ 11 队合计 0.357，人均 3.2%（赔率 ~31），**合理**
- 若 T = 1.30 → 11 队合计 0.457，人均 4.2%（赔率 ~24），**也合理**

⇒ 这 5 个赔率**内部自洽，像是真实盘口**，但**精确去水做不到**。下表给出 T=1.20 与 T=1.25 两种假设下的归一化结果，**归一化用的 T 是我的假设，不是查到的事实**：

| 队 | T=1.20 归一 | T=1.25 归一 |
|---|---|---|
| TEAM VISION | 18.5% | 17.8% |
| Team Spirit | 16.7% | 16.0% |
| Team Yandex | 13.9% | 13.3% |
| Iron Wing | 11.9% | 11.4% |
| Team Falcons | 9.3% | 8.9% |

**抓取失败记录**：
- `esportbet.com/dota-2/the-international/` → **HTTP 403**（WebFetch）
- `cyberscore.live/en/news/the-international-2026-winner-odds/` → **HTTP 403**（WebFetch）
- Pinnacle / Bet365 / GG.bet / Thunderpick 官网：未尝试直连（均需要地区/登录，且属博彩站点）

### 4.3 ★ 交叉验证结果 ★

**先解决一个陷阱**：博彩站用 org 真名（PARIVISION / 1win Team / BetBoom），Polymarket 与 Liquipedia 用 TI 参赛名（TEAM VISION / Iron Wing / BoomBoys）。下表已对齐（见 §2.0）。

| 队 | Polymarket 归一（调用方提供） | 博彩去水（T=1.20 假设） | 差 | 判读 |
|---|---|---|---|---|
| TEAM VISION | 18.3% | 18.5% | **+0.2pp** | ✅ **两个市场高度一致**，都把它当头号热门 |
| Team Yandex | 18.0% | 13.9% | −4.1pp | Polymarket 更看好 |
| Team Spirit | 8.0% | 16.7% | **+8.7pp** | ⚠️ **最大分歧，博彩是 Polymarket 的两倍多** |
| Iron Wing (1win) | 未进前五（< 7.6%） | 11.9% | **> +4pp** | ⚠️ **第二大分歧，博彩明显更看好** |
| Team Falcons | 7.6% | 9.3% | +1.7pp | 基本一致 |
| BoomBoys (BetBoom) | 11.1% | **未查到** | — | 无法比对 |

**结论（可信度：存疑 —— 博彩侧只有 5 队且水位是假设值）：**

1. **头号热门两边都认 TEAM VISION（≈18%）**，这一条最可靠，两个独立市场撞上了。
2. **两处显著分歧都指向同一个方向：Polymarket 系统性低估欧洲传统强队（Spirit、1win/Iron Wing），高估 Yandex。**
   考虑到 Polymarket 该盘**总成交只有 $40,943**（极薄），**更可能是 Polymarket 有噪声，而不是博彩定错价**。薄盘被少量单子推偏是常态。
3. ⚠️ **给下游的建议**：不要把 Polymarket 当先验。**若必须选一个，倾向传统博彩**；更稳的做法是等开赛前拿到完整博彩盘口再定。

**可能的基本面解释（这是我的推测，不是查到的事实）：**
- 博彩看好 PARIVISION/TEAM VISION 与 Team Yandex，媒体给的理由是近期战绩——摘要称 *"PARIVISION are the main favorites after recently claiming the **Esports World Cup 2026** title"*，以及 Team Yandex *"winning **BLAST SLAM VII, PGL Wallachia Season 7 and DreamLeague Season 27**, while also finishing in the top three at EWC 2026"*。这两条战绩本身可信度**存疑**（单一媒体转述，未在 Liquipedia 核对）。
- Team Spirit 的分歧可能与队长兼指挥 **Miposhka 转任教练**（见 §2.4C）有关：博彩开盘模型可能还没定价这一变动，Polymarket 散户已经反映了。**纯推测，未核实。**

### 4.4 ⚠️ Polymarket 两个快照对不上（如实记录）

| 来源 | TEAM VISION | Team Yandex | BoomBoys | Team Falcons | Team Spirit |
|---|---|---|---|---|---|
| 调用方提供（归一化后） | 18.3% | 18.0% | 11.1% | **7.6%** | **8.0%** |
| 媒体转述"截至 2026-07-31 的 Polymarket" | 22% | 20% | 13% | **11%** | **9%** |

- 两组数**排序不同**：调用方版本 Spirit(8.0%) > Falcons(7.6%)，媒体版本 Falcons(11%) > Spirit(9%)。
- 媒体那组是**原始价格（含水，5 队合计 75%）**，调用方那组是**归一化后**，量纲不同不能直接比；但**排序本不该受归一化影响**，所以这是真分歧——**大概率是两个不同时间点的快照**。
- **无倾向**，两组都记录在案。下游若要用 Polymarket，请自己重抓一次并记录抓取时间戳。

---

## 5. 来源冲突表 —— ✅ 本轮已全部裁决

| 冲突项 | 上一轮的两种说法 | **本轮裁决** | 仲裁依据 | 可信度 |
|---|---|---|---|---|
| Tundra vs 1win Team | "Tundra Esports" vs "1win Team（former Tundra）" | **两个都不是 TI15 参赛名。正确参赛名是 `Iron Wing`** | Liquipedia 注释原文："The roster of Tundra Esports was transferred to 1w Team. The team will compete as Iron Wing."；OpenDota `team_name` = "1w" | 已核实 |
| BetBoom vs BoomBoys | "BoomBoys" vs "BetBoom Team" | **`BoomBoys` 是对的**（上一轮判"检索摘要讹误"→**该判断作废**） | Liquipedia 参赛名 = BoomBoys；OpenDota `team_name` = BoomBoys；TI14 参赛名是 "BB Team"，四人留任 | 已核实 |
| TEAM VISION vs PARIVISION | "TEAM VISION 晋级" vs Hotspawn 名单里是 PARIVISION | **同一支队。TI15 正式名 `TEAM VISION`，TI14 参赛名 `PVISION`（即 PARIVISION）** | Liquipedia 两届名单对比：Satanic/No[o]ne-/9Class/Dukalis 四人跨届留任；OpenDota `team_name` = TEAM VISION | 已核实 |
| L1GA Team vs HULIGANI | "HULIGANI 打进" vs "L1GA Team (HULIGANI)" | **同一支队。TI15 参赛名 `HULIGANI`，org 名 `L1GA TEAM`** | Liquipedia 参赛名 = HULIGANI；OpenDota 这五人 `team_name` 全部 = "L1GA TEAM" | 已核实（双源交叉） |
| LGD Gaming 占南美席 | 上一轮"强烈怀疑 Hotspawn 有误" | **Hotspawn 是对的，上一轮的怀疑作废。** LGD Gaming 确实占 South America 1st，阵容是全南美 ex-HEROIC 班底 | Liquipedia 参赛卡片明标 "Qualified South America 1st"，五人国籍 NI/PE/BO/BR/BR；OpenDota `team_name` = LGD Gaming | 已核实（双源交叉） |
| 淘汰赛结构 | "历史惯例双败" vs 无来源 | **双败确认。**UB 7 场 + LB 6 场 + GF 1 场；GF 为 BO5，其余全 BO3；无 bracket reset | Liquipedia Format 节 + bracket 槽位 | 已核实 |
| Vici Gaming 阵容 | Hotspawn 提"Faith_bian、XinQ、y\` 在队" | **XinQ、y\` 对；"Faith_bian" 部分对** —— Liquipedia 显示 pos3 选手当前 ID 是 `Bach`，但其 Liquipedia 页面链接是 `/dota2/Faith_bian`，**即 Faith_bian 改 ID 为 Bach，是同一人** | Liquipedia 参赛卡片链接目标 | 已核实 |

**本轮新发现的、上一轮没记的冲突：**

| 冲突项 | 说法 A | 说法 B | 倾向 | 可信度 |
|---|---|---|---|---|
| TI14 瑞士轮场次 | 结构应为 40 场（16×5÷2） | Liquipedia TI2025 赛程表只有 39 条有比分记录 | 无倾向，两者都记录在案。差 1 场原因未查明 | 存疑 |
| TI15 已众筹金额 | Liquipedia 显示 $0 | supporter bundles 7/31 才上线，抓取时仅过 1–2 天 | 倾向"追踪器未更新"，不代表真的零众筹 | 存疑 |
| **预测排名结算日** | Valve 英文客户端文案："**August 27th**" | Valve 中文客户端文案："**8月28日**" | 倾向时区差，但**未核实**。两者都是 Valve 一手文案，如实并列 | 存疑 |
| **Polymarket 快照** | 调用方提供（归一后）：Spirit 8.0% > Falcons 7.6% | 媒体转述 7/31 原始价：Falcons 11% > Spirit 9% | **排序相反**，无倾向。大概率是不同时间点的快照。详见 §4.4 | 存疑 |
| **Team Spirit 夺冠概率** | Polymarket 8.0% | 传统博彩去水后约 16.7% | 倾向传统博彩（Polymarket 该盘总成交仅 $4 万，极薄）。**但这是我的判断，不是查到的事实** | 存疑 |

---

## 6. 未查到 / 待补清单（按优先级，本轮更新）

1. 🔴 **Compendium 预测题目逐题原文**（英文 + 中文）、选项、每题赋分、题目总数、战队题 vs 选手题分类、「是谁」型 vs 阈值型分类 —— **最高优先级，本轮未突破**。
   **本轮已查实：题面是服务端下发的，客户端本地化文件里没有（§3.2b(5)），离线途径全部排除。**
   **唯一可行路径 = 登录 Dota 2 客户端打开 Rewards → Predictions 页面抄题。这一步只能由用户本人或有客户端的机器完成，agent 做不到。**
   ⚠️ 距 8/13 10:00 CST 截止只剩约 11 天，**建议尽快让用户去客户端截图**。
2. 🟡 **传统博彩完整盘口**（16 队全赔率）用于精确去水 —— 本轮拿到 5 队，缺 11 队；两个候选站点（esportbet.com、cyberscore.live）均 403
3. 🟡 **Team Spirit 的 Polymarket(8.0%) vs 博彩去水(~16.7%) 巨大分歧**、以及 **Iron Wing 的类似分歧**的成因 —— 待查
3b. 🟡 **Polymarket 两个快照排序矛盾**（§4.4）—— 建议下游自行重抓并记录时间戳
3c. 🟡 媒体称的近期战绩（PARIVISION 夺 EWC 2026、Team Yandex 夺 BLAST SLAM VII / PGL Wallachia S7 / DreamLeague S27）**未在 Liquipedia 核对**
4. 🟡 TI15 瑞士轮配对规则是否照搬 TI14（Liquipedia TI2026 该节为空）
5. 🟡 TI15 奖金分配比例是否照搬 TI14（42.5%/13%/9%/...）
6. 🟡 TI15 补丁版本（7.41e 单源；Liquipedia infobox Version 字段为空）
7. 🟢 8 个 ⚠️ 标记的 account_id 二次核对（尤其 `KJ → KingJungles`）
8. 🟢 TI14 瑞士轮 39 vs 40 场差异的原因
9. 🟢 Valve 官方一手页面（dota2.com 博客原文，非镜像）—— 目前用的是 changelog.gg / patchbot.io 两个镜像

---

## 7. 方法论备注：来源可达性（本轮更新）

### ✅ 本轮打通的

- **`liquipedia.net` MediaWiki API —— 用 `curl` 直连完全可用**（上一轮记的"被拦截"只对 WebFetch 成立）。这是本轮最大突破，赛制/名单/roster/转会/历史赛果全部来自它。必须 `unset` 代理 + 加 `--compressed`（不加会返 406）+ 自觉遵守 2 秒/次限速。
- **`api.opendota.com/api/proPlayers`** —— 一次调用返回 5081 条职业选手记录（含 `account_id` / `name` / `personaname` / `team_name` / `country_code`），是把选手名映射到 account_id 的最快路径。同样需要 `unset` 代理。
- **`changelog.gg`** —— Valve 官方 Dota 2 更新博文的可抓镜像。官方一手页 dota2.com 抓不到时用它。
- ★ **`github.com/dotabuff/d2vpkr` —— Dota 2 客户端资源文件镜像，最后更新 2026-08-01，是当前版本。** 这是本轮的第二个突破口：不装游戏也能读客户端本地化文件。
  ```bash
  curl --noproxy '*' --compressed -sL \
    'https://raw.githubusercontent.com/dotabuff/d2vpkr/master/dota/resource/localization/dota_english.txt'
  # 中文换 dota_schinese.txt；文件约 1MB，UTF-8，格式 "KEY" "VALUE" 逐行
  ```
  **注意**：`SteamDatabase/GameTracking-Dota2` 这个更知名的仓库**不含本地化 txt**（本轮已验证：21,797 个文件里没有 dota_english.txt），别去那里找。

### ❌ 仍然不可达

| 域名 | 症状 |
|---|---|
| `escorenews.com` | HTTP 403（WebFetch 与 curl 均是） |
| `gosugamers.net` 详情页 | HTTP 403（检索摘要可用） |
| `esportbet.com` | HTTP 403 |
| `cyberscore.live` | HTTP 403 |
| `patchbot.io` | 返回页面只有标题、无正文（疑为 JS 渲染） |
| `dota2.com/international/` | 返回空内容（纯 JS 渲染页） |
| `en.wikipedia.org/wiki/The_International_2026` | HTTP 404，条目尚不存在 |
| `blast.tv` | 网络策略拦截 |

### 环境注记

本机 shell 设了 `HTTP_PROXY=HTTPS_PROXY=http://127.0.0.1:7890`，会导致 TLS 握手失败（curl exit 35）。所有 curl 必须：

```bash
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
curl --noproxy '*' --compressed --max-time 30 ...
```
