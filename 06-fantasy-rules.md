# 06 — TI15 Fantasy（梦幻竞猜）规则调研

> 调研日期：2026-08-02 ｜ TI15 开赛 2026-08-13（剩 11 天）
> 所有事实按 **已核实 / 存疑 / 未查到** 三档标注。
> **计分系数一律不凭记忆写。查不到就写「未查到」。**

---

## 完成度

| 任务 | 状态 | 结论摘要 |
|---|---|---|
| P0 TI15 是否有 Fantasy | ✅ 完成 | **有。但形态彻底改了 —— 是全新的「Fantasy Craft」，不是选手卡阵容制。** |
| P1 TI15 完整规则 | ✅ 结构完成 / ⚠️ 系数缺失 | 玩法、组队、锁定、奖励、加成体系全部拿到；**18 项基础分值是服务端下发，静态提取不到** |
| P2 TI13/TI14 历史规则对照 | ✅ 完成 | 见 §E |
| P3 计分项 × 本地数据可得性 | ✅ 完成 | **18 项：本地 CSV 直接 12 项 + OpenDota JSON 可解 3 项 = 15/18（83%）；Watcher/Lotus 确定拿不到；见 §F** |
| P4 历史分数分布 | ✅ 完成 | TI14 实测：场均 14.67±4.72，**单局 78% 是噪声**；见 §G |

---

# 🚨 P0 结论（最重要）

## TI15 **有** Fantasy，但它**不是**你以为的那个 Fantasy。

**已核实**（来源：Dota 2 客户端本地化文件 `dota_english.txt`，经 `github.com/dotabuff/d2vpkr` 获取，2026-08-01 更新；本地副本 `ti15-research/d2v_en.txt`）

存在性证据（直接字符串）：
```
"DOTA_Compendium2026_Tabs_Fantasy"           "Fantasy"
"DOTA_Compendium2026_ParticipationSummary"   "Participate in Fantasy and Predictions to unlock free rewards."
"DOTA_EventName_International2026"           "The International 2026"
"DOTA_FantasyCraft_NoCompendium"             "You must purchase The International Compendium to play this year's iteration of Fantasy Dota."
"DOTA_FantasyCraftHelp_BasicsDetails2026"    "Craft your own team from The International competitors! Choose the core, mid,
                                              and support players from three teams and use roll tokens to mutate and improve
                                              your team to increase their fantasy score."
```

### ⚠️ 对建模的致命影响：**2026 版选的是「队」，不是「人」**

```
"DOTA_FantasyCraft_Tutorial2026_ViewTablet_Body"
  "For each role, you choose a team instead of individual players.
   For core and support roles, you score points for both players on the team.
   You may freely change the chosen team by pressing the "Choose Team" button on the War Banner."

"DOTA_FantasyCraft_TeamChoice_Core"     "Choose your Core Duo"
"DOTA_FantasyCraft_TeamChoice_Mid"      "Choose your Mid Player"
"DOTA_FantasyCraft_TeamChoice_Support"  "Choose your Support Duo"
```

**这直接推翻了「选手层面预测」的默认假设。**
TI15 Fantasy 的决策单元是 **3 个「队 × 角色」组合**：
- Core 槽 → 选一支队，拿该队**两名核心**的分（Core Duo）
- Mid 槽 → 选一支队，拿该队**中单**的分
- Support 槽 → 选一支队，拿该队**两名辅助**的分（Support Duo）

三个槽可以来自三支不同的队。**所以我们要预测的是「某队的 core 组 / mid / support 组在某 period 的平均 fantasy 得分」，而不是单个选手的得分排名。**

---

# §A. TI15（2026）Fantasy Craft 完整规则

**全部已核实**，来源同上（客户端本地化文件）。

## A.1 准入门槛

| 项 | 内容 | key |
|---|---|---|
| 必须持有 | **The International Compendium**（通行证） | `DOTA_FantasyCraft_NoCompendium` |
| 账号资格 | **只有活动开始时已存在/活跃的账号有资格** | `DOTA_Fantasy2026_NoCompendium`："Only accounts active when the event began are eligible to play this year's iteration of Fantasy Dota." |

## A.2 核心循环

```
"DOTA_FantasyCraft_Tutorial_CreateRoster_Body"
  "Welcome to the newest iteration of Fantasy Dota! To begin, select players to fill out your roster."
"DOTA_FantasyCraft_Tutorial_ShowRoster"
  "...now you have much more control over how your roster will score points during a game."
```

1. **建阵容**：Core 队 / Mid 队 / Support 队（3 个槽）
2. **每个槽配一面 War Banner（战旗）**，战旗上镶嵌若干 **Emblem（徽记）**
3. **用 Roll Token（转蛋代币）改造**徽记 → 决定得分方式
4. 选 **Coach Titles（教练称号）**：一个前缀 + 一个后缀，给全队加成
5. 每个 period（阶段）结算、拿 Compendium Points

## A.3 ⚡ 最关键的机制改动：只有装了徽记的 stat 才计分

```
"DOTA_FantasyCraft_Tutorial_Emblems_Stat"
  "<b>Stat:</b> What fantasy stat the Emblem counts.
   Unlike previous seasons, you only score points for the stats you have an Emblem for.
   When rerolling a stat, the Emblem's Color controls what stats it could be."
```

**这意味着：TI15 的 fantasy 分数不是「选手全部数据的加权和」。**
你只拿到你镶嵌了徽记的那几项的分。选手再全能，你没装那个徽记就不得分。
→ **建模目标从「预测选手总分」变成「预测选手在特定 stat 子集上的产出」，再叠加徽记乘子。**

## A.4 徽记（Emblem）四属性

```
"DOTA_FantasyCraft_Tutorial_Emblems_Body"  "War Banners contain multiple Emblems that control
                                            how many fantasy points the player will score.
                                            Each emblem has four different attributes:"
"DOTA_FantasyCraft_Tutorial_Emblems_Type"  "Color: An Emblem will either be Red, Green, or Blue.
                                            The color distribution on a War Banner cannot be modified
                                            and is based on the Role of the player."
"DOTA_FantasyCraft_Tutorial_Emblems_Quality"  "Quality: Provides a percentage bonus base fantasy score."
"DOTA_FantasyCraft_Tutorial_Emblems_Trait"    "Trait: Can provide an additional percentage bonus..."
```

### 颜色 → 可用 stat 池（已核实，硬编码在本地化文件里，**不是**服务端下发）

| 颜色 | 定位 | 可 roll 出的 stat（各 6 项） |
|---|---|---|
| **Red 红**（`GemType0`：carry oriented） | 核心向 | Kills, Deaths, Creep Score, GPM, Madstone Collected, Tower Kills |
| **Blue 蓝**（`GemType1`：support oriented） | 辅助向 | Wards Placed, Camps Stacked, Runes Grabbed, Watchers Taken, Smokes Used, Lotuses Grabbed |
| **Green 绿**（`GemType2`：playmaker oriented） | 节奏向 | Roshan Kills, Teamfight Participation, Stuns, Tormentor Kills, First Blood, Courier Kills |

来源 key：`DOTA_FantasyCraftHelp_RedStats` / `_BlueStats` / `_GreenStats`、`DOTA_FantasyCraft_GemType0_Body` / `1` / `2`。

> 注：**颜色分布由角色决定且不可改**（Core 槽偏红、Support 槽偏蓝，具体几红几蓝几绿**未查到**，需进客户端看）。
> 另：`DOTA_FantasyCraftHelp_StatBody` 明确「同一面 War Banner 上**没有重复 stat**」。

### 品质（Quality）→ 百分比加成（已核实，硬编码数值）

| 品质 | 加成 |
|---|---|
| Tier I | **+10%** |
| Tier II | **+30%** |
| Tier III | **+60%** |
| Tier IV | **+100%** |
| Tier V | **+150%** |

来源：`DOTA_FantasyCraft_Quality_Explainer0..4`（五条字符串互相印证，数值一致）。
`DOTA_FantasyCraftHelp_GemQualityDetails`："Qualities with a larger boost are more rare when crafting."

### 特性（Trait）→ 条件式加成（已核实，硬编码数值）

| 特性名 | 内部 key | 效果 |
|---|---|---|
| Base | `Trait_Base` | 无（基准） |
| **Incorruptible** | `Trait_Min` | 品质低于 Tier III 的徽记按 Tier III 计算 |
| **Benevolent** | `Trait_AdjBonus` | 给**相邻**徽记的 stat 值 **+20%** |
| **Vampiric** | `Trait_Steal` | 自身 stat 值 **+50%**，但相邻徽记 **−10%** |
| **Unique** | `Trait_Unique` | 若战旗上**只有这一个** Unique，**+30%** |
| **Friendly** | `Trait_Multiples` | 若战旗上**至少 3 个** Friendly，**+50%** |
| **Fractal** | `Trait_UniqueQualities` | 若战旗上**所有徽记品质各不相同**，**+60%** |

→ 「相邻（adjacent）」说明徽记在战旗上有**空间排布**，是个组合优化问题。
`DOTA_FantasyCraft_TotalStatBonusDesc`："Total combined score of Quality and Trait" → 品质与特性加成**合并计算**。

## A.5 教练称号（Coach Titles）—— 2026 新机制

```
"DOTA_FantasyCraftHelp_CoachDetails"
  "As the coach of your fantasy team, you can choose a prefix and suffix (known as Titles)
   to provide bonuses to all of your players during their games.
   Each title provides a percentage increase to the final score in a game if a condition is met.
   You may freely change your titles without spending roll tokens."
```

**2026 的重大变化：称号从「每个选手各有两个」上移到「教练层，全队共享」，且改称号免费、不花 roll token。**
（对比 2025 版 `DOTA_FantasyCraft_Tutorial_ViewTablet_Body`："Each player has two titles... You can spend roll tokens to generate new title options"）

### 前缀（Prefix）全集 — 已核实

| 显示名 | 触发条件 |
|---|---|
| Crimson | 使用**红色**英雄时 |
| Cerulean | 使用**蓝色**英雄时 |
| Emerald | 使用**绿色**英雄时 |
| **Royal**（2026 新增） | 使用**紫色**英雄时 |
| **Golden**（2026 新增） | 使用**黄/棕色**英雄时 |
| Bestial | 使用**有角或有翼**的英雄 |
| Elemental | 使用**水/火/冰**系英雄 |
| Otherworldly | 使用**亡灵/恶魔/精魂**系英雄 |
| Hirsute | 使用**有胡子或毛茸茸**的英雄 |
| **Heroic**（2026 新增） | 使用**带披风或面具**的英雄 |
| Canny | 使用**智力**英雄 |
| Brawny | 使用**力量**英雄 |
| Dashing | 使用**敏捷**英雄 |
| Balanced | 使用**全才**英雄 |
| Virtuoso | 使用该选手**大师/宗师级**熟练度的英雄 |
| Clutch | 打**系列赛最后一场**时 |
| Coveted | 该选手的英雄**最后被选**时 |
| Sacrificial | 该选手的英雄**第一个被选**时 |
| Glamorous | 该选手装备了 **Arcana（至宝）** 时 |

### 后缀（Suffix）全集 — 已核实

| 显示名 | 触发条件 |
|---|---|
| the Tormented | 任意选手**死于折磨者** |
| the Nothl Pilgrim | 该选手是**全场死亡最多** |
| the Pacifist | 该选手**零击杀**结束比赛 |
| the Flayed Twins Acolyte | 任意选手在**开局号角前**拿到一血 |
| the Patient | 一血发生在 **10 分钟之后** |
| the Underdog | 该选手**输掉**的比赛 |
| of the Raven | 任意选手打出 **rampage（团灭）** |
| the Decisive | 比赛**时长 < 25 分钟** |
| the Even-Keeled | 该选手被**打赏 ≥ 5 次** |
| the Loquacious | 该选手**语音台词用得最多** |
| the Divine Thief | 任意选手**偷走圣剑** |
| of the Ant | 该选手**净资产最低** |
| of the Mule | 该选手结束时**主背包和后备箱全满** |
| of the Octopus | 该选手结束时有 **≥ 4 件带主动技能**的装备 |
| of the Bull | 该选手在 **30 分钟前买活** |
| the Accomplice | 该选手**助攻最多** |
| the Clutch | 打**系列赛最后一场**时 |
| **the Lucky**（2026 新增） | **比赛时长以 8 结尾** |
| **the Gritty**（2026 新增） | 某队在**净资产落后超 10,000** 后翻盘获胜 |
| **the Cruel**（2026 新增） | 有选手**在自己泉水被击杀** |

> ⚠️ 所有 prefix/suffix 的**加成幅度**都是 `{d:prefix_bonus}%` / `{d:suffix_bonus}%` 运行时插值 → **具体百分比未查到，服务端下发。**

## A.6 计分口径（2026 专属，已核实）

```
"DOTA_FantasyCraftHelp_ScoringDetails2026"
  "Once matches for a period begin, a snapshot of your roster is saved and used for scoring.
   For each role, each player's score is calculated individually in every game they participate in.
   Players receive points only for the stats present on their War Banner,
   amplified if any of the conditions of your coach Titles are met.
   We then average the score of all players for a role and use that to decide the final score for a game.
   The top two scoring games within a series are used to get the role's final score for the match.
   If a role participates in more than one series in a period, the best scoring series will be used.
   The base amount of points for each stat are listed below:"
```

**结算算法（可直接实现）：**
```
对每个角色槽 role ∈ {Core, Mid, Support}:
  1. 快照锁定：period 首场比赛开始时锁定阵容
  2. 对该 role 所选队伍的每名相关选手 p（Core/Support 为 2 人，Mid 为 1 人）:
       对该 series 内每一局 g:
         raw(p,g) = Σ_{stat ∈ 该 role 战旗上的徽记}  base_coef[stat] × player_stat[p,g,stat]
                                                     × (1 + quality_bonus + trait_bonus)
         final(p,g) = raw(p,g) × (1 + Σ 满足条件的 coach title 加成)
  3. game_score(role, g) = mean_p( final(p,g) )        ← 对该 role 的所有选手取平均
  4. series_score(role) = top2( game_score(role, ·) )   ← 系列赛内取最高的两局求和
  5. 若该 role 在本 period 打了多个 series → 取最高分的那个 series
```

> 对比 2025 版（`DOTA_FantasyCraftHelp_ScoringDetails`，单选手制）：
> "...We then add the top two scoring games within a series to get their final score.
>  If a player participates in more than one series in a period, their best scoring series will be used."
> 结构一致，**2026 多了「对角色内多名选手求平均」这一步**。

### 基础分值表（结构已核实 / **数值未查到**）

| idx | Stat | 客户端文案 | 基础系数 |
|---|---|---|---|
| 0 | Kills | `+{f:helpstat_0} per kill` | **未查到**（服务端） |
| 1 | Deaths | `{f:max_death} starting points, -{f:helpstat_1} per death` | **未查到** |
| 2 | Creep Score | `+{f:helpstat_2} per last hit or deny` | **未查到** |
| 3 | GPM | `Scores player's GPM multiplied by {f:helpstat_3}` | **未查到** |
| 4 | Tower Kills | `+{f:helpstat_4} per Tower last hit` | **未查到** |
| 5 | Roshan Kills | `+{f:helpstat_5} per Roshan kill` | **未查到** |
| 6 | Teamfight Participation | `Max {f:helpstat_6} points for participating in team fights` | **未查到** |
| 7 | Wards Placed | `+{f:helpstat_7} per observer ward placed` | **未查到** |
| 8 | Camps Stacked | `+{f:helpstat_8} per camp stacked` | **未查到** |
| 9 | Runes Grabbed | `+{f:helpstat_9} per rune bottled or taken` | **未查到** |
| 10 | First Blood | `{f:helpstat_10} points if the player gets first blood` | **未查到** |
| 11 | Stuns | `+{f:helpstat_11} per second of stun` | **未查到** |
| 12 | Smokes Used | `+{f:helpstat_12} per Smoke of Deceit used` | **未查到** |
| 13 | Madstone Collected | `+{f:helpstat_13} per Madstone collected` | **未查到** |
| 14 | Watchers Taken | `+{f:helpstat_14} per captured watcher` | **未查到** |
| 15 | Lotuses Grabbed | `+{f:helpstat_15} per lotus taken` | **未查到** |
| 16 | Tormentor Kills | `+{f:helpstat_16} per Tormentor kill` | **未查到** |
| 17 | Courier Kills | `+{f:helpstat_17} per Courier kill` | **未查到** |

**为什么拿不到：** 全部写作 `{f:helpstat_N}` 运行时插值 token，由服务端在渲染时填入。
与上一轮发现的「预测面板题面服务端下发」是同一个机制。**这是本次调研唯一的硬缺口，见 §H。**

## A.7 Roll Token（转蛋代币）与改造操作

```
"DOTA_FantasyCraftHelp_RollingDetails2026"
  "You always have 3 unique roll options for emblems available to you which are the same for every War Banner.
   Each roll costs a single roll token, only affects the currently selected War Banner,
   and will replace all available roll options when used."
```

可用操作（`DOTA_FantasyCraft_Operation_*`）：
- Increase Quality（提升品质）
- Reroll Quality / Reroll Trait / Reroll Stat（重摇品质/特性/stat）
- Randomly increase one Quality（随机升 1 个品质）
- Randomly increase two Qualities and reduce one（随机升 2 降 1）
- Choose Player / Draft Player / Reroll with Player from Region（换人/按赛区换人）
- Change Team（换队，2026）
- Choose/Draft/Reroll Prefix or Suffix（换称号）

作用目标粒度：单个徽记 / 某颜色全部 / 全部徽记 / 随机一个 / 第一个 / 最后一个。

**Token 来源**（已核实 key，**具体数量未查到**）：
- `DOTA_FantasyCraft_GroupStageRolls` `+{d:rolls} Group Stage Crafting Rolls`
- `DOTA_FantasyCraft_PlayoffRolls` `+{d:rolls} The International Fantasy Crafting Rolls`
- `DOTA_FantasyCraft_MainEventRolls` `+{d:rolls} Fantasy Crafting Rolls (Unlocks for The International)`
- `DOTA_FantasyCraft_RollBundle` "Fantasy Crafting Roll Bundle" → **可付费购买**
- `FantasyCraftingMats` "Add Fantasy Crafting Rerolls"

> ⚠️ **Roll token 可以花钱买** → fantasy 排名不是纯预测能力竞赛，有付费维度。

## A.8 赛程结构与锁定

| 项 | 内容 | 来源 key |
|---|---|---|
| 计分单位 | **Period（阶段）**，不是「天」 | `DOTA_FantasyPeriodScore`, `DOTA_FantasyCraft_PeriodLockedTitle` |
| 阶段划分 | 至少 **Group Stage / Playoffs / Main Event** 三段 | `GroupStageRolls` / `PlayoffRolls` / `MainEventRolls` |
| 锁定时机 | **该 period 的比赛一开始就快照锁定** | `ScoringDetails2026`："Once matches for a period begin, a snapshot of your roster is saved" |
| 阶段解锁 | 下一 period 在上一 period 阵容锁定后才开放 | `DOTA_FantasyCraft_PeriodLockedBody`："This will unlock after rosters are locked for the preceding period." |
| 阵容继承 | **阵容跨 period 延续**，改造成果累积 | `Tutorial_Locked_Body`："Your roster carries over period to period, so any improvements you make now will boost your performance later!" |
| 每阶段可升级 | 是 | `Tutorial_Upgrade_Body`："Your roster is eligible for an upgrade at the beginning of every period." |
| 倒计时 UI | 有 | `DOTA_FantasyRosterLockCountdown` "Roster Locks in {t:d:t:T:countdown_time}" |

> ⚠️ **具体锁定时刻（几点、什么时区）未查到** —— 2026 的 key 里没有硬编码时间。
> 历史参考（DPC 时代 `DOTA_FantasyHelpDetailsSub3Text4`）："Rosters lock at the start of each day at **9:00 a.m. China Standard Time**"，
> 2021 版为 "9:00 AM EEST (GMT+3)"。**不可直接套用到 TI15。**

## A.9 排名与奖励（已核实，硬编码数值）

```
"DOTA_FantasyCraftHelp_RewardsDetails"
  "At the end of the matches for a period, your roster's fantasy score is compared
   against everyone else who submitted a roster for the period.
   Earn points based on your performance in the group."
```

| 档位 | 奖励 |
|---|---|
| **Top 1%** | 25,000 Compendium Points |
| **Top 10%** | 18,000 |
| **Top 25%** | 10,000 |
| **Top 50%** | 6,000 |
| **Top 75%** | 2,500 |
| **Bottom 25%** | 1,000 |

来源：`DOTA_FantasyCraftHelp_RewardsTop1 / Top10 / Top25 / Top50 / Top75 / RewardsBottom25`。
文案写的是「total Compendium Points」，**存疑：是全程累计总额还是每 period 发放，字面无法确定。**

排行榜：`DOTA_FantasyLeaderboardHeaderGlobal` "Global Top 100"、`HeaderFriends` "Friends"、
`DOTA_FantasyLeaderboardScore` "Total Score"、`PeriodScore` "Period Score"。
→ 有**全球总榜**和**分阶段榜**两种口径。

**建模含义：奖励是百分位分档的，不是名次线性的。目标函数应该是「进 top X%」的概率，而不是「最大化期望分数」。**

---

# §B. 必须排除的两套过时系统

调研时最大的坑：本地化文件里 `fantasy` 共 **1090 行**，分属**三个**不同世代的系统。混用会得出完全错误的规则。

| 世代 | key 特征 | 状态 | 判别字符串 |
|---|---|---|---|
| **1. Fantasy League（2015）** | `fantasy_league_*`, `DOTA_FantasyLeague*`, `DOTA_FantasyTeam*` | ☠️ 死代码 | `"fantasy_league_create_season" "Fantasy Season Two"`、`"DOTA_Fantasy_ComingSoon" "Coming in October"`、需要 `Fantasy Ticket`、有 draft/trade/veto/waiver/commissioner/4-6-8-10 队 |
| **2. Player Card Fantasy（TI6–TI13 时代 + DPC）** | `DOTA_PlayerCardBonus*`, `DOTA_FantasyHelpDetails*`, `fantasy_slot_*` | 🕰️ 历史 | 阵容 = 2 Core + 1 Mid + 2 Support **五张选手卡**；卡分金/银/普通；按**天**锁定 |
| **3. Fantasy Craft（TI14 起，TI15 为 2026 变体）** | `DOTA_FantasyCraft*`, `*2026` | ✅ **现行** | War Banner + Emblem + Roll Token + Coach Titles；按 **period** 锁定 |

> 非世代 1 的 fantasy 行共 895 行；其中 `FantasyCraft|Fantasy2026` 共 **371 行**。

---

# §E. P2 — 历史规则对照（TI13 / TI14）

## E.1 唯一一份**带硬编码数值**的官方计分表（DPC 时代，非 TI15）

`DOTA_FantasyHelpDetailsHeader` = "DPC Fantasy Details"；相邻 key `DOTA_FantasyHelpDetailsHeaderWinter2022` = "DPC Winter 2022 Fantasy"
→ **这组数值属于 DPC 2021–2022 赛季，不是 TI15。**

| Stat | 系数（DPC 时代） | key |
|---|---|---|
| Kill | **+0.3** / 击杀 | `Sub1Text1` |
| Death | **起始 +3 分，每死 −0.3** | `Sub1Text2` |
| Last Hit / Deny | **+0.003** / 个 | `Sub1Text3` |
| GPM | **+0.002** × GPM | `Sub1Text4` |
| Tower | **+1** / 最后一击 | `Sub1Text5` |
| Roshan | **+1** / 最后一击 | `Sub1Text6` |
| Teamfight Participation | **+3 × 参团率** | `Sub1Text7` |
| Observer Ward placed | **+0.5** / 个 | `Sub1Text8` |
| Camp Stacked | **+0.5** / 次 | `Sub1Text9` |
| Rune taken or bottled | **+0.25** / 个 | `Sub1Text10` |
| First Blood | **+4**（最后一击者） | `Sub1Text11` |
| Stun | **+0.05** / 秒 | `Sub1Text12` |

> 注意：**只有 12 项**（对应 stat idx 0–11）。
> Smokes(12) / Madstone(13) / Watchers(14) / Lotuses(15) / Tormentor(16) / Courier(17) **是后来加的，没有任何硬编码系数**。
>
> **可信度标注：已核实（字符串确实存在且数值明确），但适用性存疑（DPC 时代 ≠ TI15）。**
> 用作 TI15 系数的**代理值**是当前唯一可行的选择，但必须标注为「代理」而非「事实」。

## E.2 Player Card 时代（TI13 及更早）规则要点 — 已核实

| 项 | 内容 | key |
|---|---|---|
| 阵容 | **2 Core + 1 Mid + 2 Support** 共 5 张卡 | `DOTA_FantasyHelpText2` |
| 卡包 | 每包 5 张，**保底 1 张银或金** | `DOTA_FantasyHelpText1`, `Sub2Text1` |
| 卡加成 | 银卡 **3 条**随机 stat 加成，金卡 **5 条** | `Sub2Text3` |
| 加成幅度 | **+5% ~ +25%** 随机 | `DOTA_FantasyHelpDetailsSub2Text2` |
| 同选手限制 | **同一天不能用同一选手的多张卡** | `Sub2Text4` |
| 卡复用 | 一张卡可用于**任意多天** | `Sub2Text5` |
| 系列赛计分 | BO3 取**最高分的 2 局**；BO5 取**最高分的 3 局** | `Sub3Text2`, `Sub3Text3` |
| 多系列赛 | 一个 period 打多个系列赛时**只算最高分那个** | `Sub3Text2` |
| 锁定 | 每天 **09:00 中国标准时间** | `Sub3Text4` |
| 奖励（TI/BP） | Top 10% → 16,000 BP；Top 25% → 8,000；Top 50% → 4,000 | `Sub5Text1-3` |
| 奖励（Compendium 全程） | Top 10% → 6,000 CP；25% → 3,000；50% → 1,500 | `Sub5Text*_compendium` |
| 奖励（Compendium 每日） | Top 10% → 800 CP；25% → 400；50% → 200 | `Sub5Text*_Daily_compendium` |

> ⚠️ **BO5 取前 3 局** 在 2026 版文案里**消失了** —— 2026 只写 "The top two scoring games within a series"。
> **存疑：TI15 的 BO5 是否仍取 3 局，字面证据不支持，需进客户端确认。**

## E.3 TI14（2025）版 Fantasy Craft — 已核实

与 TI15 同属 Fantasy Craft，但有三处关键差异：

| 维度 | TI14（2025） | TI15（2026） |
|---|---|---|
| 选择单元 | **单个选手** | **队伍**（Core Duo / Mid / Support Duo） |
| 称号 | **每个选手 2 个**，换称号**要花 roll token** | **教练层全队共享 1 前缀 + 1 后缀**，换称号**免费** |
| 角色内聚合 | 无（单人直接算） | **对角色内多名选手求平均** |

来源对照：
- TI14：`DOTA_FantasyCraftHelp_BasicsDetails`、`DOTA_FantasyCraft_Tutorial_ViewTablet_Body`、`DOTA_FantasyCraftHelp_ScoringDetails`
- TI15：`..._BasicsDetails2026`、`DOTA_FantasyCraft_Tutorial2026_ViewTablet_Body`、`..._ScoringDetails2026`、`DOTA_FantasyCraftHelp_CoachDetails`

**共同点（TI14/TI15 一致）：** 徽记品质 5 档（10/30/60/100/150%）、Trait 全集、系列赛取前 2 局、best-series 规则、只对装了徽记的 stat 计分。

---

*（P3 / P4 见下节，增量写入中）*

---

# §F. P3 — 18 项计分项 × 数据可得性对照

## F.1 逐项核对表

图例：✅ 本地 CSV 直接有 ｜ 🟡 需 OpenDota explorer SQL 解 JSON ｜ ⚠️ 只有代理量 ｜ ❌ 拿不到

| idx | Stat | 颜色 | 本地 `pro_player_matches_2020_2026.csv` 字段 | OpenDota 取法 | 判定 |
|---|---|---|---|---|---|
| 0 | Kills | 红 | `kills` | — | ✅ |
| 1 | Deaths | 红 | `deaths` | — | ✅ |
| 2 | Creep Score | 红 | `last_hits` + `denies` | — | ✅ |
| 3 | GPM | 红 | `gold_per_min` | — | ✅ |
| 4 | Tower Kills | 红 | `towers_killed` | — | ✅ |
| 13 | Madstone Collected | 红 | **无** | `player_matches.item_uses->>'madstone_bundle'`（**是「使用疯石袋」≠「采集疯石」**） | ⚠️ **仅代理** |
| 7 | Wards Placed | 蓝 | `obs_placed` | — | ✅ |
| 8 | Camps Stacked | 蓝 | `camps_stacked` | — | ✅ |
| 9 | Runes Grabbed | 蓝 | `rune_pickups` | — | ✅ |
| 12 | Smokes Used | 蓝 | **无** | `player_matches.item_uses->>'smoke_of_deceit'` | 🟡 **可取** |
| 14 | Watchers Taken | 蓝 | **无** | **无任何字段** | ❌ **取不到** |
| 15 | Lotuses Gained | 蓝 | **无** | **无任何字段** | ❌ **取不到** |
| 5 | Roshan Kills | 绿 | `roshans_killed` | — | ✅ |
| 6 | Teamfight Participation | 绿 | `teamfight_participation` | — | ✅ |
| 11 | Stuns | 绿 | `stuns` | — | ✅ |
| 10 | First Blood | 绿 | `firstblood_claimed` | — | ✅ |
| 16 | Tormentor Kills | 绿 | **无** | `player_matches.killed->>'npc_dota_miniboss'` | 🟡 **可取** |
| 17 | Courier Kills | 绿 | **无** | `player_matches.killed->>'npc_dota_courier'` | 🟡 **可取** |

## F.2 覆盖率总结

| 口径 | 数量 | 百分比 |
|---|---|---|
| 本地 CSV 直接可用 | **12 / 18** | **66.7%** |
| 加上 OpenDota JSON 可解出的 3 项（Smoke / Tormentor / Courier） | **15 / 18** | **83.3%** |
| 再加 Madstone 代理量 | 16 / 18 | 88.9% |
| **确定性缺口（Watchers Taken、Lotuses Gained）** | **2 / 18** | **11.1%** |

> **对既有情报的验证结果：**
> 「OpenDota 能取到 17 个计分项里的 15 个，Watcher 和 Lotus 取不到」
> → **基本成立，但需两处修正**：
> 1. 计分项现在是 **18 项**（不是 17），2026 版加了 Courier Kills。
> 2. 15 项里有 **3 项不是现成列，必须解 JSON blob**（`item_uses` / `killed`），本地 CSV 里没有。
> 3. Madstone 只有代理量（`madstone_bundle` 使用次数 ≠ 采集数），严格说应算**半个缺口**。

## F.3 ⚠️ 按徽记颜色看，缺口是**严重偏斜**的

这是本节最重要的结论 —— 缺失项不是均匀分布的，全部砸在**蓝色（辅助向）**池子里：

| 颜色 | 可得 / 总数 | 覆盖率 | 缺失项 |
|---|---|---|---|
| 🔴 Red（核心向） | 5(+1代理) / 6 | **83–100%** | Madstone（仅代理） |
| 🔵 **Blue（辅助向）** | **4 / 6** | **66.7%** | **Watchers Taken、Lotuses Gained** |
| 🟢 Green（节奏向） | 6 / 6 | **100%** | 无 |

**含义：** TI15 阵容的三个槽里，**Support Duo 槽的战旗全是蓝色徽记**（颜色分布由角色决定）。
也就是说，**我们对辅助槽的预测能力结构性弱于核心槽和中单槽 —— 三分之一的辅助徽记我们盲。**

## F.4 缺失项对总分的影响有多大？

**无法精确量化**，原因：TI15 各项的基础系数是服务端下发的（§A.6），没有系数就算不出占比。

能给出的两个边界：

1. **上界（悲观）：** 若某个蓝色战旗恰好 roll 出 Watchers + Lotuses 两个徽记，且该战旗只有 6 个槽位，
   则该角色槽最多有 **2/6 ≈ 33%** 的得分来源完全不可预测。
2. **实际期望：** 蓝池 6 选若干，Watchers/Lotuses 被 roll 中的概率各约 1/6 → 期望缺失比例约 **1/3 的蓝色徽记**。
   由于只有 Support 槽是纯蓝，对**整个阵容**（3 槽）的期望影响量级约 **10% 左右**。
   **标注：估算，非核实。** 依赖「颜色分布由角色决定」的具体数字，而那个数字**未查到**。

3. 参考旁证（**代理证据，非 TI15**）：用 DPC 时代系数在 TI14 真实数据上算，12 项里没有任何一项占比超过 13.8%（见 §G.3）。
   Valve 明显在刻意做**均衡配比**。若 TI15 延续这个设计，单项缺失的影响大概率在 **5–15%** 区间。

## F.5 要补数据该查哪里（可执行）

OpenDota Explorer（`https://api.opendota.com/api/explorer?sql=...`，已实测可用，需 `unset` 代理）：

```sql
SELECT pm.match_id, pm.account_id,
  COALESCE((pm.item_uses->>'smoke_of_deceit')::int, 0)  AS smokes_used,     -- idx 12
  COALESCE((pm.killed->>'npc_dota_miniboss')::int, 0)   AS tormentor_kills, -- idx 16
  COALESCE((pm.killed->>'npc_dota_courier')::int, 0)    AS courier_kills,   -- idx 17
  COALESCE((pm.item_uses->>'madstone_bundle')::int, 0)  AS madstone_proxy   -- idx 13（代理）
FROM player_matches pm
JOIN matches m USING (match_id)
WHERE m.leagueid = 18324;   -- TI14
```

**实测结果（TI14，leagueid=18324，1440 行）— 已核实：**

| 字段 | 合计 | 有值行数 |
|---|---|---|
| `smoke_of_deceit` | **2,043** | 628 |
| `npc_dota_courier` | **409** | — |
| `npc_dota_miniboss`（Tormentor） | **299** | — |
| `npc_dota_roshan`（对照校验） | **342** | — |
| `healing_lotus` / `greater_healing_lotus` | **0** | 0 |
| `npc_dota_watcher` | **0** | 0 |
| `neutral_tokens_log` 数组长度合计 | **0** | 数组全空 |

> `npc_dota_roshan = 342` 与本地 `roshans_killed` 口径吻合 → **证明 `killed` blob 解析方法本身是对的**，
> 因此 Watcher / Lotus 的 0 是**真·没有数据**，不是查询写错。
> 另注：`item_uses` 里的 `lotus_orb`（87 次）是**装备「莲花之球」**，与 fantasy 的「莲花池采莲」是两回事，**不可混用**。

**相关表/字段速查：**
- 表：`player_matches`（90 列）、`matches`（40 列）
- JSON blob 列：`item_uses`、`killed`、`purchase`、`runes`、`obs_log`、`neutral_tokens_log`
- ⚠️ 这些 blob **只有 parsed（已解析）比赛才有**。TI14 是 100% parsed（`has_detailed` 全为 True），
  但**普通职业赛不保证**，全量 146 万行里的覆盖率需另行核验。

---

# §G. P4 — TI14 真实 Fantasy 分数分布

**方法论声明（重要）：**
TI15 系数拿不到，本节用 **DPC 时代的 12 项系数**（§E.1）作代理，在 **TI14 真实比赛数据**（`data/ti14_player_matches.csv`，1,440 人-局，全部 parsed）上计算。
**这是「类 fantasy 综合评分」的现实标尺，不是 TI15 的真实分数。** 缺失的 6 项未计入。

## G.1 单局（per-game）分布

| 统计量 | 值 |
|---|---|
| n | 1,440 人-局 |
| 均值 | **14.67** |
| 标准差 | **4.72** |
| 最小 | 4.07 |
| p10 / p25 | 8.90 / 11.18 |
| **中位数** | **14.22** |
| p75 / p90 | 17.60 / 21.04 |
| p99 / 最大 | 26.73 / 43.72 |

→ 分布轻微右偏（均值 > 中位数），变异系数 CV ≈ **0.32**。

## G.2 按角色分（OpenDota `fantasy_role`）

| 角色 | n | 均值 | 标准差 | 中位数 | p90 |
|---|---|---|---|---|---|
| **Mid** | 139 | **17.12** | 5.30 | 16.25 | 23.39 |
| Support | 576 | 14.55 | 4.06 | 14.01 | 19.66 |
| Core | 593 | 14.16 | 4.90 | 13.87 | 20.90 |
| （未标注 unknown） | 116 | 15.73 | 4.76 | 15.45 | 22.21 |

**两个反直觉但很重要的发现：**
1. **中单显著最高**（比 Core 高约 21%）。TI15 阵容里 Mid 是**独立一槽且只算 1 个人**（不像 Core/Support 要对 2 人取平均）→ **Mid 槽的选择既高分又高方差，是最值得下功夫的槽位。**
2. **Support 均值反而略高于 Core**（14.55 vs 14.16）。Valve 的系数设计刻意让辅助有竞争力（眼位 0.5/个、堆野 0.5/次占比很高）。
   → **「选核心稳赢」是错的直觉。**

## G.3 各计分项对总分的贡献占比（TI14 实测）

| 计分项 | 贡献分 | 占比 |
|---|---|---|
| Observer Wards | 2.017 | **13.8%** |
| Teamfight Participation | 2.012 | **13.7%** |
| Deaths（净额，含 +3 基底） | 1.651 | 11.3% |
| Stuns | 1.519 | 10.4% |
| Camps Stacked | 1.456 | 9.9% |
| Kills | 1.332 | 9.1% |
| Runes | 1.089 | 7.4% |
| Towers | 1.079 | 7.4% |
| GPM | 1.009 | 6.9% |
| Creep Score | 0.877 | 6.0% |
| First Blood | 0.392 | 2.7% |
| Roshan | 0.237 | 1.6% |

→ **极度均衡，最高单项仅 13.8%。**
→ **辅助向指标（眼位 + 堆野 = 23.7%）合计超过核心向指标（GPM + 补刀 = 12.9%）近一倍。**

## G.4 选手层面（≥6 局，n=80 人）

| 统计量 | 值 |
|---|---|
| 选手均分的均值 | 14.31 |
| **选手间标准差** | **2.19** |
| 最低 – 最高 | 8.82 – **19.62** |
| 极差 | 10.80 |

**TI14 场均前 12：**

| 场均分 | 局数 | 选手 | 战队 | 角色 |
|---|---|---|---|---|
| **19.62** | 29 | Malr1ne | Team Falcons | Mid |
| 18.10 | 29 | skiter | Team Falcons | Core |
| 17.73 | 29 | Cr1t- | Team Falcons | Support |
| 17.68 | 16 | shiro | Team Tidebound | Core |
| 17.40 | 23 | gpk~ | BoomBoys | Mid |
| 17.39 | 23 | No[o]ne- | TEAM VISION | Mid |
| 17.33 | 26 | xNova | Xtreme Gaming | Support |
| 17.22 | 26 | Ame | Xtreme Gaming | (未标注) |
| 17.18 | 24 | OmaR | Nigma Galaxy | Support |
| 17.09 | 16 | Nisha | Team Liquid | Mid |
| 17.04 | 19 | KingJungles | HEROIC | Support |
| 16.91 | 19 | Yuma | HEROIC | Core |

> **Team Falcons 包揽前三名**（三个不同角色）→ 印证「fantasy 分数高度受**队伍走多远 + 队伍强度**驱动」，
> 这对 TI15「按队选」的新机制是**利好**：队级信号本来就是主要信号。

## G.5 🔴 方差分解 —— 最该记住的一个数

| 来源 | 方差 | 占比 |
|---|---|---|
| 单局总方差 | 22.30 | — |
| **选手间（可预测的技术差异）** | **4.78** | **21.9%** |
| **选手内（局与局的随机波动）** | **17.07** | **78.1%** |

**结论：单局 fantasy 分数里约 78% 是噪声，只有约 22% 来自选手本身的稳定差异。**

对建模的直接含义：
- 任何号称能精准预测单局 fantasy 得分的模型都是在拟合噪声。
- **正确做法是预测「多局累计/期望值」的排序，而不是单局分数。**
- TI15 的规则其实**放大了**这个问题：取「系列赛内最高的两局」+「多系列赛取最好那个」= 双重取最大值 →
  **结果被右尾主导，运气权重进一步上升。**
- 但同时 TI15 的「角色内多人取平均」（Core Duo / Support Duo）会**降低**方差 →
  两个效应方向相反，净效应**未量化**。

## G.6 TI15 口径下的「队 × 角色组」分布（用 TI14 数据模拟）

按 TI15 规则把选手聚合成 Core Duo / Mid / Support Duo（≥10 人-局的组）：

| 角色槽 | 组数 | 均值 | 标准差 | 最好 | 最差 |
|---|---|---|---|---|---|
| **Core Duo** | 16 | 13.72 | 1.47 | **16.39**（Team Falcons） | 10.82（Team Nemesis） |
| **Mid** | 7 | **16.71** | 1.67 | **19.62**（Team Falcons） | 14.19（Team Spirit） |
| **Support Duo** | 16 | 14.25 | 1.27 | **16.26**（Team Falcons） | 11.48（Team Nemesis） |

**关键读数：**
- 取平均后，组间标准差降到 **1.3–1.7**（对比选手层 2.19、单局层 4.72）→ **TI15 的取平均机制大幅压缩了可操作空间。**
- **最好与最差的差距只有 ~5 分/局**，而单局噪声标准差是 4.72 → **信噪比很差，选队的边际收益不如想象中大。**
- **Mid 槽方差最大（1.67）且均值最高（16.71）** → 再次确认：**Mid 是三个槽里最值得投入分析资源的。**

---

# §H. 还有什么必须靠用户进客户端才能拿到

以下**全部靠公开渠道拿不到**，是本次调研的硬缺口。按重要性排序：

| # | 缺什么 | 为什么拿不到 | 影响 | 怎么拿 |
|---|---|---|---|---|
| **1** | **18 项的基础系数 `helpstat_0..17`** | 客户端文案全是 `{f:helpstat_N}` 运行时插值，服务端下发 | 🔴 **致命**。没有系数就算不出任何绝对分数 | 进客户端 → Compendium → Fantasy → Help/Scoring 页，**截图那张「base amount of points for each stat」表** |
| **2** | **死亡项的起始分 `max_death`** | 同上 | 🔴 高。它是常数项，直接影响均值 | 同上，同一张表 |
| **3** | **各角色槽的徽记颜色分布**（Core/Mid/Support 各几红几蓝几绿、共几个槽） | 文案只说「由角色决定且不可改」，无数字 | 🔴 高。决定了每槽的 stat 组合空间，也决定 Watcher/Lotus 缺口的真实权重 | 进客户端看三面 War Banner 的徽记排布，**截图** |
| **4** | **Prefix / Suffix 的加成百分比** `{d:prefix_bonus}` / `{d:suffix_bonus}` | 服务端下发 | 🟠 中。影响 title 选择的最优解 | 客户端 Coach Titles 面板，鼠标悬停看渲染值 |
| **5** | **Period 的具体划分与锁定时刻** | 2026 key 里无硬编码时间 | 🟠 中。决定我们的预测交付节奏 | 客户端 Fantasy 页的 `Roster Locks in ...` 倒计时 |
| **6** | **Roll Token 的发放数量与节奏** | `{d:rolls}` 插值 | 🟡 低-中。影响能改造多少次 | 客户端 Rewards / Fantasy 页 |
| **7** | **BO5 是否仍取前 3 局** | 2026 文案只提「top two games」，旧版有 BO5 取 3 局 | 🟡 中。TI 淘汰赛全是 BO3/BO5，口径错会系统性偏 | 客户端 Scoring 帮助页全文 |
| **8** | **奖励是每 period 发放还是全程累计** | 文案 "total Compendium Points" 有歧义 | 🟢 低。不影响预测，只影响目标函数解释 | 客户端 Rewards 页 |
| **9** | **可选队伍/选手名单**（哪些队进了 fantasy 池） | 服务端 | 🟠 中 | 客户端 Choose Team 面板 |

## 建议给用户的取数清单（一次进客户端全搞定）

> 打开 Dota 2 → Compendium（The International 2026）→ **Fantasy** 标签页
> 1. 点右上帮助/问号 → **Scoring** 章节，截图那张 18 行的分值表 ← **最重要**
> 2. 同一帮助页往下翻：Emblem Quality 列表、Trait 列表、Stats by Emblem Color
> 3. 回到 Fantasy 主页，分别点开 **Core / Mid / Support** 三面 War Banner，截图徽记排布（数颜色和数量）
> 4. Coach Titles 面板：把几个 prefix / suffix 悬停一下，记下 `+X%` 的实际数字
> 5. 截图顶部的 **Roster Locks in ...** 倒计时和 period 划分

---

# §I. 来源清单

| 来源 | URL | 用途 | 可信度 |
|---|---|---|---|
| Dota 2 客户端本地化文件 `dota_english.txt` | `https://github.com/dotabuff/d2vpkr`（2026-08-01 更新） | §A/§B/§E 全部规则文本 | **已核实**（一手，客户端原文） |
| 本地副本 | `ti15-research/d2v_en.txt`（4.03 MB）、`fcraft.txt`（371 行）、`fx_all.txt`（895 行） | 可复查 | — |
| OpenDota Schema API | `https://api.opendota.com/api/schema` | §F 字段清单 | **已核实** |
| OpenDota Explorer API | `https://api.opendota.com/api/explorer?sql=...` | §F.5 实测计数 | **已核实**（实跑，含 roshan 对照校验） |
| 本地比赛数据 | `data/ti14_player_matches.csv`（1,440 行）、`data/pro_player_matches_2020_2026.csv`（146 万行） | §F/§G | **已核实** |

**未使用/未查到的来源：** Liquipedia 与 Reddit 未查询 —— 客户端本地化文件是**一手来源**，
已完整覆盖 P1/P2 的结构性问题；二手 wiki 无法提供服务端系数，查了也补不上唯一的缺口（§H #1）。
**若用户仍希望交叉验证，建议方向：** TI14 期间的 Reddit r/DotA2 讨论帖可能有玩家抄录的 `helpstat` 实际数值。

---

# §J. 给建模的五条结论

1. **TI15 有 Fantasy，但选的是「队 × 角色」不是「人」。** 预测目标必须改成
   「某队 Core Duo / Mid / Support Duo 在某 period 的平均 fantasy 得分」。
2. **只有装了徽记的 stat 才计分。** 我们的交付物不能是「选手综合排名」，
   而应是**「选手/队伍在 18 个 stat 上的分项产出预测矩阵」**，让用户自己按手上的徽记组合去匹配。
   这反而**降低**了对精确系数的依赖 —— 分项预测不需要系数，只有换算成绝对分才需要。
3. **数据覆盖 15/18（83%），缺口全在蓝色（辅助向）池。** Support 槽的预测能力结构性偏弱，交付时要标注这个不确定性。
4. **单局 78% 是噪声。** 只做期望值排序，不承诺单局精度。TI15 的「取最好两局 + 取最好系列赛」进一步放大右尾。
5. **Mid 槽 = 最高价值。** 均值最高（16.71）、组间方差最大（1.67）、且只算 1 个人不被平均稀释。
   资源优先投 Mid 槽预测。**Core 与 Support 的均值差异极小（13.72 vs 14.25），不要用「核心得分高」的直觉。**
