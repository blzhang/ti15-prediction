# TI15 舆论场调研：社区热度能不能当预测信号

调研日期：2026-08-01
TI15（The International 2026）：2026-08-13 ~ 08-23，上海东方体育中心，16 队，瑞士轮+双败
（来源：[Liquipedia TI2026](https://liquipedia.net/dota2/The_International/2026)）

**一句话结论：热度本身没有增量信息（答案 b），且「最热的那支队」有轻微反向指标特征。真正有信息量的是预测市场价格，不是讨论量。**

---

## 0. 结论摘要（先看这个）

| 问题 | 答案 |
|---|---|
| 赛前赔率头名夺冠命中率（TI9-TI14） | **1/6 = 16.7%** |
| 赛前赔率头名进前四命中率 | **3/6 = 50%**（严格口径）/ 4/6 = 66.7%（媒体共识口径） |
| 冠军的赛前赔率排名（中位数） | **第 4.5 名** |
| 冠军的赛前隐含概率（均值） | **12.3%**（中位数 ~9.3%） |
| 每届平推头名的资金回报 | **-25% ROI**（6 单位本金亏 1.5 单位） |
| 民调/专家投票 vs 赔率 | **民调更差**：TI13 专家 10 票里冠军得 0 票；TI11 民调冠军排第 7、垫底那队打进前四 |
| 系统性赛区偏差 | 有，但方向和流传的说法**相反**：近三届是**中国队被系统性低估**、**东欧（Team Spirit）被系统性高估** |

统计诚实性警告：n=6，样本极小。赔率头名 6 届中 1 次夺冠，而按均值 ~26% 隐含概率期望是 1.55 次。二项检验 P(X≤1 | n=6, p=0.26) ≈ 0.55 —— **无法拒绝「博彩赔率是校准良好的」这个原假设**。赔率没被证伪，只是 TI 本身方差极大。下面所有「偏差」结论都必须带这个前提读。

---

## 1. 核心表：TI9-TI14 赛前热门 vs 实际战绩

（TI 无 2020 届，疫情取消。所有最终名次均取自 Liquipedia 的 prize pool 表，通过 MediaWiki API 拉取核实。）

| 届次 | 赛前赔率头名（隐含概率） | 民调/专家榜头名 | 实际冠军（赛前赔率 & 排名） | 实际前四 | 头名夺冠？ | 头名进前四？ |
|---|---|---|---|---|---|---|
| **TI9** 2019 上海 | Team Secret +250（28.6%） | Team Secret；OG 被普遍看衰 | **OG** — +1000，**第 7 热门**，9.1% | OG / Team Liquid / PSG.LGD / Team Secret | ✗ | ✓（Secret 第 4） |
| **TI10** 2021 布加勒斯特 | PSG.LGD +200（33.3%） | PSG.LGD（ONE Esports 力量榜第 1） | **Team Spirit** — +1400，**第 9 热门**，6.7%，**力量榜前十无名** | Spirit / PSG.LGD / Team Secret / Invictus Gaming | ✗ | ✓（LGD 第 2） |
| **TI11** 2022 新加坡 | PSG.LGD +250（28.6%） | PSG.LGD（Strawpoll 1.71 万票，4500 票第 1） | **Tundra Esports** — +1300，**并列第 4 档**，7.1%；民调第 7（735 票） | **Tundra / Team Secret / Team Liquid / Team Aster（四支全是 +1300 或更差）** | ✗ | **✗**（LGD 5-6） |
| **TI12** 2023 西雅图 | Team Spirit 4.50（22.2%） | Spirit / Gaimin Gladiators | **Team Spirit** — 头名本人 | Spirit / Gaimin Gladiators / LGD Gaming / Azure Ray | **✓** | ✓ |
| **TI13** 2024 哥本哈根 | Team Spirit 11/4（26.7%）；Falcons 13/4 被媒体称头名 | **Team Falcons**（BLAST 10 位解说投票，3 票） | **Team Liquid** — 9/1~10/1，**第 5 热门**，~9.5%，**专家票 0/10** | Liquid / Gaimin Gladiators / Tundra / Team Falcons | ✗ | 歧义：Spirit 9-12（✗）/ Falcons 第 4（✓） |
| **TI14** 2025 汉堡 | Team Spirit 3.8（26.3%） | Team Spirit（Hotspawn 力量榜第 1） | **Team Falcons** — 5.3，**第 4 热门**，18.9% | Falcons / **Xtreme Gaming（赔率 15.0，第 11 热门）** / PVISION / BB Team | ✗ | **✗（Spirit 掉到 9-13）** |

### 逐条溯源

**TI9（2019）**
- 开赛前赔率（2019-07-06）：Secret +250 / Vici +400 / Liquid +450 / VP +600 / EG +800 / PSG.LGD +800 / **OG +1000** — [SportsBettingDime 开盘赔率](https://www.sportsbettingdime.com/news/esports/opening-odds-for-the-international-2019-team-secret-opens-as-favorite/)
- 注意陷阱：另一篇 [8 月 19 日的同站文章](https://www.sportsbettingdime.com/news/esports/international-2019-betting-preview-team-secret-favored-odds/) 把 OG 列到 +350、Liquid 列到 +6600 —— 那是**小组赛打完之后**的盘口，不是赛前。做回测时必须锁定「开赛前」时间戳，否则会把赛中信息当赛前信号。
- 舆论：OG 作为卫冕冠军仍被看衰，"most fans were regarding OG as underdogs once again"，主 C ana 上半年休假 — [GosuGamers](https://www.gosugamers.net/dota2/features/72861-defenders-of-the-aegis-a-look-at-how-ti-champions-fared-in-protecting-their-title)
- 名次核实：[Liquipedia TI2019](https://liquipedia.net/dota2/The_International/2019)

**TI10（2021）**
- 赔率（BetOnline，2021-10-05 发布，标注 10-11 数据）：PSG.LGD +200 / iG +400 / VP +600 / OG·Secret·Vici +700 / EG +800 / T1 +1200 / **Team Spirit +1400** / Elephant +1500 / Aster +1700 — [GamblingNews](https://www.gamblingnews.com/news/dota-2-ti10-odds-picks-time-date-and-where-to-watch/)
- 力量榜（ONE Esports，2021-07-22，Nigel "Zim947" Zalamea）前十：LGD / EG / iG / Secret / T1 / Vici / Quincy Crew / VP / Alliance / OG —— **Team Spirit 榜上无名** — [ONE Esports](https://www.oneesports.gg/dota2/dota-2-ti10-global-power-rankings/)
- 名次核实：[Liquipedia TI2021](https://liquipedia.net/dota2/The_International/2021)

**TI11（2022）——本次调研最有价值的一届**
- 赔率（2022-10-13，开赛前两天）：PSG.LGD +250 / Team Spirit +350 / OG +500 / 然后一个 **+1300 大平层**：Aster、**Tundra**、Entity、RNG、Secret、Liquid — [PointSpreads](https://www.pointspreads.com/news/esports/the-international-11-odds-and-preview/)
- **社区民调（Strawpoll，17,100 票）**：PSG.LGD 4,500 / EG ~4,200 / Secret ~1,900 / … Liquid 914（第 6）/ **Tundra 735（第 7）** / **Aster 145（14 支里垫底）** — [GINX](https://www.ginx.tv/en/t11-prediction-who-will-win)
- **三个赛前头名（LGD、Spirit、OG）全部无缘前四**：LGD 5-6、**Team Spirit 13-16**、OG 7-8。
- **民调第 1（LGD）→ 5-6；民调第 2（EG）→ 9-12；民调垫底（Aster）→ 第 4。**
- 名次核实：[Liquipedia TI2022](https://liquipedia.net/dota2/The_International/2022)

**TI12（2023）——唯一一次头名兑现**
- 赔率：Team Spirit 4.50 / Gaimin Gladiators 5.00 / Team Liquid 6.00 — [bets.com.au](https://www.bets.com.au/esports/dota-2/the-international-odds-20231016-0012/)、[EsportsCompare](https://esportscompare.net/news/ti12-betting-preview/)
- 但前四里的第 3（LGD Gaming）和第 4（Azure Ray）都不在任何赛前头部梯队里；卫冕冠军 Tundra 掉到 13-16。
- 名次核实：[Liquipedia TI2023](https://liquipedia.net/dota2/The_International/2023)

**TI13（2024）**
- 赔率（2024-09-03，Unibet/Bluefox/Betway）：Spirit 11/4 · 3/1 · 3/1；GG 3/1 全线；Falcons 13/4 · 33/10 · 13/4；XG 11/2~8/1；**Liquid 9/1~10/1** — [legalbet](https://legalbet.uk/best-posts/who-will-win-the-international-2024-ti-13-odds-on-the/)
- **专家投票（BLAST.tv，2024-08-30，10 位官方解说）**：Falcons 3 票 / GG 2 / XG 2 / 1win 1 / Spirit 1 / Talon 1 —— **冠军 Team Liquid 得 0 票** — [BLAST.tv](https://blast.tv/dota/news/experts-vote-favourites-to-win-ti13)
- 名次核实：[Liquipedia TI2024](https://liquipedia.net/dota2/The_International/2024)

**TI14（2025）**
- 赔率：Spirit 3.8 / PARIVISION 4.0 / Liquid 4.4 / **Falcons 5.3** / Tundra 6.3 / BetBoom 7.0 / GG 7.0 / Aurora 8.5 / Tidebound 12.0 / Nigma 12.0 / **Xtreme Gaming 15.0** / NAVI Junior 20.0 / Heroic 20.0 / Nemesis·BOOM·Wildcard 30.0 — [Hawk Live](https://hawk.live/posts/bookmakers-have-predicted-the-winner-of-the-international-2025)（页面日期字段抓到 2025-12-22，疑为站点再发布时间戳；内容是赛前盘口，建议二次核对）
- 力量榜（Hotspawn，2025-09-03，Patrick Bonifacio）：1 Spirit / 2 PARIVISION / 3 Tundra / 4 Falcons / 5 Liquid / 6 BetBoom / 7 Tidebound / 8 Aurora / **9 Xtreme Gaming** / 10 Nigma … — [Hotspawn](https://www.hotspawn.com/dota2/news/ti14-power-rankings)
- **亚军 Xtreme Gaming 赔率第 11、力量榜第 9 —— 本样本里最大的一次低估。**
- 冠军 Team Falcons 3-2 击败 Xtreme Gaming — [Liquipedia TI2025](https://liquipedia.net/dota2/The_International/2025)、[The International 官推](https://x.com/dota2ti/status/1967310675430293793)

---

## 2. 「冷门」的基础概率（base rate）

三次著名冷门的赛前水位，已核实：

| 冠军 | 届次 | 赛前赔率 | 赔率排名 | 隐含概率 | 民调/榜单位置 |
|---|---|---|---|---|---|
| OG | TI9 | +1000 | 第 7 | 9.1% | 被普遍看衰 |
| Team Spirit | TI10 | +1400 | 第 9 | 6.7% | 力量榜前十无名 |
| Tundra Esports | TI11 | +1300 | 并列第 4 档 | 7.1% | 民调第 7 / 14 |
| （对照）Team Spirit | TI12 | 4.50 | 第 1 | 22.2% | 头名 |
| （对照）Team Liquid | TI13 | 9/1~10/1 | 第 5 | ~9.5% | 专家票 0/10 |
| （对照）Team Falcons | TI14 | 5.3 | 第 4 | 18.9% | 力量榜第 4 |

**「冷门」不是例外，是常态。** 6 届里 5 届的冠军赛前隐含概率 < 20%，4 届 < 10%。合理的先验：

- 赛前头名夺冠 ≈ **15~25%**
- 冠军出自赛前第 4~9 热门 ≈ **60~65%**（6 届里 4 届：TI9 第7、TI10 第9、TI13 第5、TI14 第4）
- 赛前前三热门**集体**无缘前四 ≈ **1/6 ≈ 17%**（TI11 发生过）

为什么 TI 方差这么大（机制解释，不是事后归因）：
1. **版本**：Valve 惯例在 TI 前几周发大版本补丁，赛季形态被重置。
2. **长休赛期 + 集训**：常规赛季的战绩信息随时间衰减。
3. **赛制**：小组 Bo3 + 双败淘汰，样本量小到不足以让强度差异稳定表达。
4. **顶端强度差很窄**：前 8 支队真实实力差距远小于赔率差距暗示的程度。

---

## 3. 系统性赛区偏差：方向和流行说法相反

| 赛区 | TI9 | TI10 | TI11 | TI12 | TI13 | TI14 | 近三届净方向 |
|---|---|---|---|---|---|---|---|
| **中国** | 高估（Vici 第2热门→5-6） | 准（LGD 头名→亚军，iG 第2→第4） | 高估（LGD 头名→5-6） | **低估**（LGD 第3、Azure Ray 第4，皆非热门） | 略高估（XG 第4热门→5-6） | **重度低估**（XG 第11→亚军；Tidebound 第9→7-8） | **系统性低估** |
| **东欧/CIS** | — | **重度低估**（Spirit +1400→冠军） | **重度高估**（Spirit 第2热门→13-16） | 准（Spirit 头名→冠军） | **高估**（Spirit ~头名→9-12） | **高估**（Spirit 头名→9-13）；PVISION 准 | **系统性高估** |
| **西欧** | — | — | **低估**（Tundra +1300→冠军） | — | **低估**（Liquid 9/1→冠军；Tundra→第3） | **低估**（Falcons 第4→冠军） | **系统性低估** |

**关键纠偏：**「英文社区低估东欧队伍」这个流传甚广的说法，在数据上**只在 2021 年成立过一次**，此后完全反转。Team Spirit 在 TI10 一战封神之后变成了市场宠儿，随后四届里有三届（TI11、TI13、TI14）相对赔率**严重跑输**——两次直接掉出前八。

真正稳定的偏差不是「某个赛区」，而是**结构性的**：
> 市场和社区把概率质量过度集中在「上赛季统治力最强的那一两支叙事队」，系统性低估赔率第 4~10 名区间。

近三届这个失效模式的具体表现 = **高估 Team Spirit + 低估中国队**。

---

## 4. 舆论场盘点与热度量化（含实测可达性）

以下每一条的 HTTP 状态都是 2026-08-01 本机实测结果，不是从文档抄的。

### 4.1 实测可用（免费、无需授权）

| 平台 | 端点 | 实测 | 能拿到什么 | 历史深度 |
|---|---|---|---|---|
| **Polymarket** ⭐ | `gamma-api.polymarket.com/events?slug=...` | **HTTP 200** | 每队实时隐含概率 + 每个子市场成交量；CLOB API 可拉历史价格序列 | 市场创建起（TI15 市场建于 2026-06-29） |
| **Liquipedia** ⭐ | `liquipedia.net/dota2/api.php` | **HTTP 200** | 最终名次、阵容、晋级方式、奖金池 | 全历史 |
| **B 站直播间** | `api.live.bilibili.com/room/v1/Room/get_info?room_id=` | **HTTP 200** | `attention`（关注数）、`online`（人气值）、`live_status`、标题 | 无历史，需自行轮询存储 |

Liquipedia 硬性要求（踩过的坑）：
- **必须 gzip**，否则返回 `406 Gzip encoding is required`（`curl --compressed`）
- 必须带描述性 User-Agent
- parse 类请求约 1 req / 2s
- 网页直连（非 api.php）对程序化访问返回 **403**
- 注意：TI2022 及以后的名次表用 `import=true` 从 LPDB 拉，wikitext 里**没有队名**，必须用 `prop=text` 取渲染后 HTML
- 另一个 `api.liquipedia.net/api/v3/`（LPDB）**需要 API key**（实测返回 `API key "" is not valid`）

B 站坑：
- 显示的**「人气值」是加权数，不是真实同时在线人数**，只能当序数用，绝不可当绝对观众数
- 搜索接口 `api.bilibili.com/x/web-interface/search/type` 返回 **HTTP 412**（需要 WBI 请求签名），搜索是被卡住的
- 实测样本：完美世界电竞频道一（room 21495945）关注数 290,437，曾直播 TI2026 各赛区预选赛

### 4.2 需要授权 / 付费

| 平台 | 实测 | 条件 |
|---|---|---|
| **Twitch Helix** | HTTP 401（端点存活） | 免费，需 app client-credentials token。给实时观众数，**无历史**，须自行轮询 |
| **Reddit** | 未授权 `.json` 返回 HTML（已失效）；`robots.txt` = `User-agent: * / Disallow: /` | **禁止爬取**。只能走官方 OAuth Data API：非商用/科研免费约 100 QPM；商用约 $0.24/1k 次 + 人工审批 |
| **VK** | `error_code 15: Access denied: token required` | 必须 token |

### 4.3 实测被墙 / 不可程序化访问

| 平台 | 实测 | 说明 |
|---|---|---|
| **Esports Charts** | **HTTP 403**，`robots.txt` 本身返回 Cloudflare error 1005 | 只能浏览器人工看，或走商务数据授权 |
| **TGStat**（Telegram 分析） | **HTTP 403** | 同上 |
| **Google Trends** | 未授权 explore 端点立即 **HTTP 429** | 且只给**相对重标定指数**，不给绝对量；两次独立查询之间不可比，必须带公共锚定词 |
| **cybersport.ru** | `robots.txt` 明确 `Disallow: /api/` | 文章页允许读；实用入口是其 Telegram 频道 [@csru_official](https://t.me/s/csru_official) |
| **Wikipedia** | 本环境 WebFetch 被网络策略拦截 | 改用 Liquipedia |

### 4.4 Reddit 历史数据（英文圈唯一有深度回溯的源）

- **Pushshift 公共版已死**（2023 API 改版后关停，幸存实例仅对版主开放）
- 继任者：**Arctic Shift**（[github.com/ArthurHeitmann/arctic_shift](https://github.com/ArthurHeitmann/arctic_shift)）—— 月度全量 dump + 有限查询 API + 网页检索，面向研究者
- 备选：Academic Torrents 上的 Reddit dump
- 历史 score/upvote 可回溯，但注意 Reddit 的 score 有模糊化（fuzzing），小数值不精确

### 4.5 直播观看数据：一个必须知道的坑

Esports Charts 的 TI 峰值观众序列（**明确声明不含中国平台**，见其[官方推文](https://x.com/esportscharts/status/1449825987911376902?lang=en)）：

| 届次 | 峰值观众 | 观看时长 |
|---|---|---|
| TI7 2017 | 925K | — |
| TI8 2018 | 1.2M | — |
| TI9 2019 | 1.9M | — |
| TI10 2021 | **2.7M**（历史最高） | — |
| TI11 2022 | 1.8M | — |
| TI12 2023 | 1.4M | — |
| TI13 2024 | 1.52M（决赛 1.437M） | 55.1M 小时 |
| TI14 2025 | 1.77~1.785M（系列第 3 高） | 63.1M 小时，均值 582,117 |

来源：[Esports Charts TI14 推文](https://x.com/EsportsCharts/status/1967322461193601253)、[TI13 推文](https://x.com/EsportsCharts/status/1835389361115775081?lang=en)、[escharts 新闻](https://escharts.com/news/most-viewed-esports-events-2025)

**对 TI15 的直接影响：TI15 在上海办，中文观众占比会暴涨，但这部分基本不进 Esports Charts 的统计口径。** 拿 TI15 的数字和往届横比会得出严重错误的「热度」结论。做时间序列前必须先确认口径。

### 4.6 中文舆论场

- **直播平台**：虎牙（[huya.com/473164](https://www.huya.com/473164) 有 TI14 赛事页）、B 站（完美世界电竞频道，TI2026 各赛区预选赛在此直播）、斗鱼、抖音均有 DOTA2 内容。TI 中文转播近年是多平台并行而非独家。
- **可量化指标**：B 站直播间关注数/人气值/弹幕数、视频播放量与三连；微博超话阅读量与讨论量；虎扑/贴吧发帖回复数。
- **可达性现状**：只有 B 站直播间接口实测可直接调用。微博开放平台、贴吧接口均需授权且限制严格；虎扑电竞板块近年活跃度远低于篮球足球板块。**未能核实** wanplus / Max+ 当前的运营状态和数据开放程度。
- 中文赛事资讯站 [dota2hub.com](https://www.dota2hub.com/the-international-2026) 有 TI15 上海专题（赛程/门票/队伍），并做过 [TI15 直邀分析与力量榜](https://www.dota2hub.com/analysis/ti15-direct-invites-power-ranking-20260528)，可作为中文侧「专家观点」采样点之一。

### 4.7 俄语/东欧舆论场

- **cybersport.ru** 是 CIS 最大电竞媒体，文章页可读、`/api/` 禁止；Telegram 频道 @csru_official 是实际分发主渠道。
- **Telegram 现在比 VK 更重要**；但 TGStat 等分析站对程序化访问返回 403。
- VK API 需 token。
- 其他：[cyber.sports.ru](https://cyber.sports.ru/)、escorenews.com（有多语种 TI compendium 预测汇总）。
- **重要纠偏**：本次调研没有找到证据支持「CIS 社区比英文社区更早看好 Team Spirit」。相反，TI10 时 Spirit **在所有语种的公开榜单和盘口里都是冷门**（赔率第 9、ONE Esports 力量榜前十无名）。TI10 的冷门不是「英文圈信息劣势」，是**全世界都没看出来**。

### 4.8 一个重要的负面发现：Valve 不公布民意分布

Valve 的 TI Compendium / Battle Pass **有**预测功能（Predictions、Fantasy、bracket predictions），但**从未公开发布过聚合的大众预测分布**（例如「X% 的玩家选了某队夺冠」）。这是本次调研最想要的那个数据——一个千万量级、有真实激励约束的群体智慧样本——**它不存在于公开域**。

所有搜到的「compendium predictions」文章都是媒体/选手在教你怎么填，不是 Valve 在公布大家填了什么。例如 [Escorenews TI15 compendium 预测指南](https://escorenews.com/en/dota-2/article/71279-predictions-guide-for-the-international-2026-compendium-ti15-predictions-from-pro-players-and-analysts)、[Hotspawn TI11 指南](https://www.hotspawn.com/dota2/news/ti11-compendium-predictions)。

**替代品：Polymarket。** 有真金白银约束、有公开 API、有历史序列。这是目前能拿到的最接近「有激励的群体预测」的东西。

---

## 5. 结论：热度是 (a) 有效信号 / (b) 赔率的噪声复读 / (c) 反向指标？

### 判断：**(b) 为主，叠加轻微的 (c)**。证据强度：中等偏弱（n=6）。

**为什么是 (b)：**

1. **原始热度 = 粉丝基数代理，不是强度代理。** 讨论量、upvote、直播观众数主要由「战队/赛区的粉丝盘子多大」决定，不是由「这队多强」决定。PSG.LGD 常年霸榜民调是因为中国观众基数，不是因为它更可能夺冠——它在 TI10 拿亚军、TI11 掉到 5-6。
2. **民调本质是赔率的有偏副本。** TI11 民调排序（LGD > EG > Secret）和盘口排序（LGD > Spirit > OG）高度重合但更极端——民调把更多质量压在叙事队上。没有独立信息，只有更大的方差和更强的偏见。
3. **可测的四个案例里，民调/榜单一致比赔率差**：
   - TI10 力量榜前十漏掉冠军；赔率至少给了 Spirit 第 9 位
   - TI11 民调冠军排第 7、垫底队打进前四
   - TI13 专家 10 票冠军得 0 票；赔率至少给了 Liquid 第 5 位
   - TI14 榜首掉到 9-13、亚军排第 9

**为什么叠加轻微的 (c)：**

「最热的那一支队」在 6 届里 5 届没夺冠，其中 2 届（TI11 Spirit、TI14 Spirit）直接掉出前八。作为**排除性信号**（把最热的那队的概率往下调）比作为**选择性信号**更有用。但 n=6，这个 (c) 属性统计上不显著，只能当先验的软约束，不能当交易信号。

### 哪种「热度」还有一点信息量？

按信息量从高到低：

1. **预测市场价格（Polymarket）+ 博彩赔率** —— 有资金约束，是唯一在 n=6 下无法被证伪为「未校准」的东西。**这是基准，不是「热度」。**
2. **跨语种分歧（divergence）** —— 唯一可能有增量的**情绪类**信号。当中文圈看好某支中国队而英文盘口给长赔率时，这个 gap 近两届是赚钱的（XG 赔率 15.0 打进决赛）。**注意：这是待检验假设，不是已验证结论**，样本只有 1~2 个点。
3. **量化模型**（如 Noxville 的蒙特卡洛/Glicko 评分）—— 这是模型不是舆情，但比任何专家投票强。TI11 小组赛后他的模型给 Tundra 38.14% 夺冠概率，事后看是对的。
4. **讨论量绝对值** —— **零增量**。别采。
5. **专家单选投票** —— **负增量**。10 位官方解说在 TI13 集体错过冠军。窄口径内行意见并不比宽口径大众意见强，只是错得更整齐。

---

## 6. 可落地的热度采集方案

### 采什么（5 个指标，全部已验证可得）

| # | 指标 | 来源 | 频率 | 用途 |
|---|---|---|---|---|
| 1 | **每队隐含概率 + 子市场成交量** | Polymarket Gamma API（免费，实测 200） | 每日 + T-7/T-1/小组赛后 | **锚**。所有其他信号都相对它来定义 |
| 2 | 博彩外围赔率快照 | 人工/oddsportal，T-7 与 T-1 各一次 | 2 次 | 交叉校验 #1，防单一市场流动性不足 |
| 3 | **r/DotA2 每队声量份额** | Reddit OAuth Data API（免费科研档 ~100 QPM）；历史用 Arctic Shift dump | 滚动 7 天 | **必须归一化成 share，不用绝对值**（绝对值是粉丝基数代理） |
| 4 | **中英分歧度** | B 站直播间 API（免费，实测 200）+ 微博/虎扑提及量代理，对照 #1 同队价格 | 每日 | 唯一可能有 alpha 的情绪信号。**交易 gap，不交易 level** |
| 5 | 赛后语种分观看数 | Esports Charts（人工读页，程序化 403） | 赛后一次 | **只用于校准，不用于预测**；必须标注「不含中国平台」 |

### 明确不要采

- 原始 upvote / 点赞总数
- Twitch 峰值观众当强度信号
- Google Trends 绝对水位（只有相对指数，且 429 严重）
- 专家单选投票（负增量）

### 工程注意事项（已踩过）

```
Liquipedia:  必须 --compressed（否则 406）+ 描述性 UA + 约 1 req/2s
             TI2022+ 名次要用 prop=text 取 HTML，wikitext 里没队名
Reddit:      robots.txt 全站 Disallow，禁止爬取，只能走 OAuth API
Bilibili:    直播间接口可用；搜索接口 412（需 WBI 签名）
             「人气值」是加权数，只能当序数
escharts:    403 + Cloudflare，只能人工读
赔率回测:     必须锁「开赛前」时间戳。TI9 的例子说明同一家媒体
             赛前和小组赛后的赔率能差 6 倍（Liquid +450 → +6600）
```

---

## 7. TI15 当前状态（2026-08-01，开赛前 12 天）

### 参赛 16 队（[Liquipedia](https://liquipedia.net/dota2/The_International/2026)）

- **直邀 7 队**：Aurora Gaming、BetBoom Team、1w Team、Team Falcons、Team Liquid、Team Yandex、Xtreme Gaming
- **欧洲预选 4 队**：Team Spirit、TEAM VISION、Nigma Galaxy、HULIGANI
- **中国预选 2 队**：Team Resilience、Vici Gaming
- 东南亚：OG ／ 北美：GamerLegion ／ 南美：LGD Gaming

注意：**Team Spirit 和 TEAM VISION 都没拿到直邀**，是从欧洲预选赛打上来的。

### Polymarket 实时价格（2026-08-01 实测）

原始价格总和 130.9%（多结果市场的 overround），下表已给归一化值：

| 队伍 | 原始 | 归一化 | 成交量 |
|---|---|---|---|
| TEAM VISION | 24.0% | **18.3%** | $3,882 |
| Team Yandex | 23.5% | **18.0%** | $2,751 |
| BoomBoys | 14.5% | 11.1% | $2,307 |
| Team Spirit | 10.5% | 8.0% | $1,526 |
| Team Falcons | 10.0% | 7.6% | $2,014 |
| Aurora Gaming | 6.5% | 5.0% | $1,430 |
| Team Liquid | 6.5% | 5.0% | $1,715 |
| 1w Team | 6.5% | 5.0% | $1,621 |
| Xtreme Gaming | 5.7% | 4.4% | $2,162 |
| **Team Resilience** | 5.65% | 4.3% | **$11,963** ⚠️ |
| Vici Gaming | 5.65% | 4.3% | $2,322 |
| LGD Gaming | 5.05% | 3.9% | $1,526 |
| HULIGANI | 2.65% | 2.0% | $1,353 |
| Nigma Galaxy | 2.25% | 1.7% | $1,529 |
| OG | 0.95% | 0.7% | $1,434 |
| GamerLegion | 0.95% | 0.7% | $1,409 |

**两个必须标注的观察：**

1. **市场很薄**（总成交量仅 $40,943）。薄市场的价格信息量弱，别当权威。
2. **Team Resilience 成交量 $11,963，是其他队（$1.4k~$2.8k）的 4~8 倍**，但价格只有 4.3%。这是本市场唯一的成交量异常。可能是单一大户，也可能是本土资金/知情资金。**值得单独盯**，但目前无法区分这两种解释。

### 把历史先验套到 TI15

- 按 6 届基础概率，**当前价格头名（TEAM VISION ~18%）夺冠概率约 15~25%**——和它的市场价基本一致，市场没有明显错价。
- **冠军出自赛前第 4~9 热门的历史频率约 60~65%**。对应到 TI15 就是 **Team Spirit / Team Falcons / Aurora / Team Liquid / 1w Team / Xtreme Gaming** 这一档。
- 两个方向性提示（**都是弱信号，不构成建议**）：
  - 近三届**中国队被系统性低估**，而 TI15 在上海主场，中国队有 4 支（Xtreme Gaming、Team Resilience、Vici Gaming、LGD Gaming），合计归一化仅 16.9%。
  - 近三届 **Team Spirit 相对赔率系统性跑输**；本届它已被市场降到第 4 档（8.0%），这个偏差可能已被 price in，不宜重复使用。
- TEAM VISION 是 PARIVISION 更名，刚拿下 Esports World Cup 2026 冠军——**这正是历史上最典型的「叙事队被过度定价」的形态**（对照 TI13 的 Gaimin Gladiators、TI14 的 Team Spirit）。这是一个明确的、可被后续验证的观察点。

---

## 8. 本报告的局限

1. **n=6**。所有比率的置信区间都极宽。「16.7% 命中率」的 95% CI 大致覆盖 0.4%~64%。
2. **「赛前赔率头名」的定义不唯一**。不同博彩公司、不同时间点会给出不同头名（TI13 就出现了 Unibet 头名是 Spirit、媒体共识头名是 Falcons 的分歧）。表里已标注歧义。
3. **民调数据极稀疏**。只找到 TI11 一次大样本社区民调（17.1k 票）和 TI13 一次专家投票（10 票）。其余届次靠媒体力量榜代理，代表性弱于真实民调。
4. **中文和俄语舆论场的深度不足**。多个平台的数据开放现状**未能核实**（wanplus、Max+、微博超话历史回溯深度、贴吧接口现状）。若要正式建模，这块需要单独补一轮。
5. **未做严格的时间点对齐**。部分赔率来源的发布时间戳存疑（尤其 TI14 的 Hawk Live 页面），建议在正式回测前用 web.archive.org 逐个复核开赛前快照。
