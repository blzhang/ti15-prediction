# TI15 预测项目 — 数据源调研报告

调研日期：2026-08-01 首轮 / 2026-08-02 第二轮（本次）
调研人：数据源调研 agent
所有产出目录：`/private/tmp/claude-501/-Users-zhangbeilong-Documents-Claude-Projects-TACT/d8f10102-b93b-4c9d-8535-8728cd41175a/scratchpad/ti15-research/`

距 TI15 开赛（2026-08-13）剩 11 天。

---

## 完成度

（2026-08-02 更新。上一版的完成度表写着「PoC 真实落地数据 = 未开始」，与磁盘不符——首轮 agent 抓完数据后超时未及更新。本表已与 `data/` 目录实际内容对齐。）

| 模块 | 状态 |
|---|---|
| OpenDota REST 端点验证 | ✅ 已完成（proMatches / leagues / proPlayers 已验证） |
| OpenDota `/api/explorer` SQL 端点 | ✅ 已完成（12 张表 schema 全部实测，含超时行为） |
| **选手-队伍时间对齐难点** | ✅ **已解决**（派生名单法；§1.6 验证，§10 可复用规程 + 失效场景） |
| **PoC 真实落地数据（TI 2021-2025）** | ✅ 已完成（4 个 CSV，见 §7.1） |
| **全量职业比赛 2020-2026：match 级** | ✅ **145,974 场已落地**（§7.3） |
| **全量职业比赛 2020-2026：player-match 级** | ✅ **1,459,742 行已落地**（§7.3） |
| **全量职业比赛 2020-2026：picks_bans 级** | ✅ **3,436,132 行已落地**（§7.3） |
| 已落地数据质量核查 | ✅ 已完成（§8，3 个问题定位到成因） |
| 全量拉取成本估算 | ✅ 已完成（§9，基于实跑） |
| 字段需求对照表 | ✅ 已完成（§11，含总缺口清单） |
| Liquipedia | ✅ 已完成（§4，含合规边界；TI15 赛制已取，16 强名单页面在建） |
| datdota / Dotabuff / STRATZ 网站 | ✅ 已完成（§5，结论：**不要爬**） |
| 现成数据集（Kaggle/HF/GitHub） | ✅ 已完成（§6，结论：价值低于自建） |
| STRATZ GraphQL API | ⏸ 部分（已确认门槛，未拿 token；OpenDota 已覆盖需求，非必需） |
| Valve 官方 WebAPI | ⏸ 部分（已确认需 key；非必需） |
| 逐分钟曲线 / 事件流巨列 | ❌ 未拉（§11.2，需按场分片） |
| **赛事级别（tier-1/2/3）标注** | ❌ **最大缺口**（OpenDota `tier` 2024 年后失效，§7.2） |
| **TI15 完整 16 强名单** | ❌ 只拿到 5 支预选赛出线队，11 支直邀未确认（§11.4） |

---

## 0. 环境注意事项（重要，影响后续所有抓取脚本）

本机 shell 环境里设了本地代理：

```
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

**这个代理会让 TLS 握手失败**（curl 退出码 35，`LibreSSL SSL_connect: SSL_ERROR_SYSCALL`）。所有抓取必须绕过它：

```bash
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
curl --noproxy '*' ...
```

另外，**不加 `--compressed` 时长响应会被截断**。实测 `/api/leagues`：不加压缩拿到 242076 字节且 JSON 未闭合（解析失败）；加 `--compressed` 后拿到完整 1025867 字节（传输 162723 字节）。抓取脚本一律带 `--compressed` / Python 端用 `requests`（默认带 gzip）。

---

## 1. OpenDota API（api.opendota.com）

### 1.1 是否需要 key / 速率限制 —— 已实测

免费匿名可用，**不需要 key**。真实响应头（`curl -D - https://api.opendota.com/api/proMatches`）：

```
HTTP/2 200
date: Sat, 01 Aug 2026 07:06:06 GMT
content-type: application/json; charset=utf-8
x-powered-by: Express
x-rate-limit-remaining-minute: 58
x-ip-address: 64.176.50.243
x-rate-limit-remaining-day: 2998
cf-cache-status: DYNAMIC
server: cloudflare
```

→ **匿名免费额度：60 次/分钟，2000... 实测起始值 3000 次/天**（`remaining-day: 2998` 是发了 2 次之后的值）。
速率信息每次响应都带 `x-rate-limit-remaining-minute` / `x-rate-limit-remaining-day` 两个头，抓取脚本可以直接读它做自适应限速。

### 1.2 `/api/proMatches` —— 已实测

真实返回（截取前 2 条）：

```json
[{"match_id":8923506996,"duration":2968,"start_time":1785562031,
  "radiant_team_id":10207962,"radiant_name":"Midas Club",
  "dire_team_id":10207984,"dire_name":"Team resilience",
  "leagueid":19917,"league_name":"The Games of the Future 2026",
  "series_id":1126275,"series_type":1,
  "radiant_score":42,"dire_score":23,"radiant_win":true,"version":22},
 {"match_id":8923499263,"duration":1940,"start_time":1785561532,
  "radiant_team_id":10207960,"radiant_name":"Execration",
  "dire_team_id":10108655,"dire_name":"Amaru Gaming",
  "leagueid":19917,"league_name":"The Games of the Future 2026",
  "series_id":1126273,"series_type":1, ...}]
```

字段解读：
- `series_id` + `series_type` → **BO 制式可还原**，同一 `series_id` 的多局可聚合成一个系列赛 → 净胜局可算。
  **⚠️ 更正（2026-08-02 实测）**：首轮报告写的 `0=bo1, 1=bo3, 2=bo5` 不完整，漏了 `3`。
  按「同一 series_id 实际有几局」反查 2024 年至今全部系列赛，真实分布：

  | series_type | 实际局数分布 | 判定 |
  |---|---|---|
  | 0 | 全部恰好 1 局（4226 个系列） | **Bo1** |
  | 1 | 1局:5248 / 2局:13972 / 3局:9352 | **Bo3** |
  | 2 | 1局:84 / 2局:66 / 3局:175 / 4局:169 / 5局:107 | **Bo5** |
  | 3 | 1局:686 / 2局:1190 / 3局:1 | **Bo2**（小组赛循环赛制） |

  `series_type=3` 是 **Bo2**（小组赛双循环常用），任何公开文档里少见，是本次从数据反推出来的。
  另有 `series_type=1` 却出现 4/5/6 局的 31 个系列 → `series_id` 复用/串号的脏数据，建模时应按
  「同 series_id 且两队相同且时间跨度 < 8 小时」重新切分，不要盲信 series_id。
- `radiant_score`/`dire_score` 是**击杀数**，不是局分。
- `version` 是 parse 版本号，不是游戏 patch。patch 要另查。
- 单次返回 100 条，靠 `?less_than_match_id=` 翻页。

### 1.3 `/api/leagues` —— 已实测

返回全部 **10024** 个 league，字段 `['leagueid','ticket','banner','tier','name']`。

tier 分布（真实统计）：
```
excluded: 7174, professional: 2472, premium: 214, None: 105, amateur: 59
```

→ **tier=premium(214) + professional(2472) 就是我们要的 tier-1/tier-2 全集**，共 2686 个赛事。

**关键：TI15 已经在库里了。** 真实返回：

```
19719 | premium      | The International 2026            ← TI15 本体
19890 | professional | The International 2026 - Regional Qualifier North America
19891 | professional | The International 2026 - Regional Qualifier South America
19892 | professional | The International 2026 - Regional Qualifier Europe
19893 | professional | The International 2026 - Regional Qualifier China
19894 | professional | The International 2026 - Regional Qualifier Southeast Asia
19838-19842 | excluded | The International 2026 - Open Qualifiers (SEA/NA/SA/EU/CN)
```

历史 TI 的 leagueid（真实返回，建模直接可用）：
```
13256 | premium | The International 2021
14268 | premium | The International 2022
15728 | premium | The International 2023
16935 | premium | The International 2024
18324 | premium | The International 2025   ← TI14
19719 | premium | The International 2026   ← TI15（目标）
```
（TI 2020 不存在——2020 年因疫情取消，这点对「近 6 年」的样本量有影响，需在建模时注意。）

### 1.4 `/api/proPlayers` —— 已实测

返回 **5074** 名职业选手。真实单条：

```json
{"account_id":1111506,"steamid":"76561197961377234",
 "personaname":"LineDOTA2","name":"LINE","country_code":"us",
 "last_login":"2026-02-16T09:18:34.196Z",
 "last_match_time":"2026-08-01T05:44:32.000Z",
 "fantasy_role":2,
 "team_id":9885271,"team_name":"TRIES","team_tag":"TRIES",
 "is_locked":null,"is_pro":null,"locked_until":null}
```

- `fantasy_role` 给了**位置**（1=核心/Carry, 2=中单/Mid, 3=辅助/Support 的粗分类，待进一步确认取值含义）。
- `team_id`/`team_name` 是**当前队伍快照，没有时间区间** → 这正是「选手-队伍时间对齐」难点的核心。**OpenDota 的这个端点解决不了历史归属。**（解法见后文，待补）

### 1.5 `/api/explorer` SQL 端点 —— 已确认可用（关键发现）

**这是本次调研最重要的发现：OpenDota 暴露了一个只读 PostgreSQL 查询端点，不需要 key。**

真实验证：
```bash
curl "https://api.opendota.com/api/explorer?sql=SELECT%20count(*)%20FROM%20matches"
```
真实返回：
```json
{"command":"SELECT","rowCount":1,"oid":null,
 "rows":[{"count":251144}],
 "fields":[{"name":"count","tableID":0,"columnID":0,"dataTypeID":20,...}],
 ...}
```

→ `matches` 表 251144 行。返回体是 node-postgres 的原始结果对象，`rows` 是数据，`fields` 带类型信息。

意义：**一次请求可以返回上千行**，而不是 REST 端点的一场一请求。这把「6 年全量」从几十万次请求压到几百次请求量级。

#### 1.5.1 完整表清单（实测）

```sql
SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name
```
真实返回 **12 张表**：
```
heroes, items, leagues, matches, match_patch, notable_players,
picks_bans, player_matches, public_matches, team_match, team_rating, teams
```

#### 1.5.2 各表字段（全部实测，非记忆）

**`matches` (40 列)** — 比赛级
```
match_id:i8, match_seq_num:i8, radiant_win:boolean, start_time:i8, duration:int,
tower_status_radiant:int, tower_status_dire:int, barracks_status_radiant:int,
barracks_status_dire:int, cluster:int, first_blood_time:int, lobby_type:int,
human_players:int, leagueid:int, positive_votes:int, negative_votes:int,
game_mode:int, engine:int, picks_bans:ARRAY, radiant_team_id:int, dire_team_id:int,
radiant_team_name:text, dire_team_name:text, radiant_team_complete:smallint,
dire_team_complete:smallint, radiant_captain:i8, dire_captain:i8, chat:ARRAY,
objectives:ARRAY, radiant_gold_adv:ARRAY, radiant_xp_adv:ARRAY, teamfights:ARRAY,
version:int, cosmetics:json, radiant_score:int, dire_score:int, draft_timings:ARRAY,
series_id:int, series_type:int, replay_salt:int
```
→ 一血(`first_blood_time`)、推塔/兵营(`tower_status_*`/`barracks_status_*` 位掩码)、
肉山与推塔事件(`objectives`)、**逐分钟经济/经验差曲线**(`radiant_gold_adv`/`radiant_xp_adv`)、
BO 制式(`series_id`/`series_type`)、队长(`radiant_captain`/`dire_captain`)、
团战(`teamfights`)、BP 计时(`draft_timings`) —— 战队层面要的宏观指标**一张表全齐**。

**`player_matches` (90 列)** — 选手-比赛级（建模主力表）
```
match_id, account_id, player_slot, hero_id, item_0..item_5,
kills, deaths, assists, leaver_status, gold, last_hits, denies,
gold_per_min, xp_per_min, gold_spent, hero_damage, tower_damage, hero_healing, level,
stuns:real, max_hero_hit:json, times:ARRAY, gold_t:ARRAY, lh_t:ARRAY, xp_t:ARRAY, dn_t:ARRAY,
obs_log, sen_log, purchase_log, kills_log, buyback_log, lane_pos:json,
obs, sen, actions, pings, purchase, gold_reasons, xp_reasons, killed, item_uses,
ability_uses, hero_hits, damage, damage_taken, damage_inflictor, runes, killed_by,
kill_streaks, multi_kills, life_state, damage_inflictor_received,
obs_placed, sen_placed, creeps_stacked, camps_stacked, rune_pickups,
obs_left_log, sen_left_log, ability_upgrades_arr, party_id, permanent_buffs,
backpack_0..3, runes_log, lane:int, lane_role:int, is_roaming:boolean,
firstblood_claimed, teamfight_participation:real, towers_killed, roshans_killed,
observers_placed, party_size, ability_targets, damage_targets, connection_log,
item_neutral, net_worth, hero_variant, neutral_tokens_log, neutral_item_history
```
→ **选手层面要的全部有**：K/D/A、`gold_per_min`/`xp_per_min`、`last_hits`/`denies`、
`hero_damage`、**`teamfight_participation`（参战率，直接给现成字段）**、
`lane`/`lane_role`/`is_roaming`（分路与位置）、`net_worth`、
`gold_t`/`xp_t`/`lh_t`/`dn_t`（**逐分钟曲线数组**）。

**`picks_bans` (5 列)** — BP 阵容
```
match_id:i8, is_pick:boolean, hero_id:int, team:smallint, ord:smallint
```
→ 完整 BP 序列，`ord` 是顺位，`team` 是 0/1（对应 radiant/dire）。

**`match_patch` (2)**：`match_id:bigint, patch:text` → **版本 patch 直接可关联**。
**`team_rating` (7)**：`team_id, rating:real, wins, losses, last_match_time, delta, match_id` → **现成的战队 Elo 评分**。
**`team_match` (3)**：`team_id, match_id, radiant:boolean` → 队伍-比赛映射。
**`teams` (4)**：`team_id, name, tag, logo_url`。
**`leagues` (5)**：`leagueid, ticket, banner, tier, name`。
**`heroes` (7)**：`id, name, localized_name, primary_attr, attack_type, roles:ARRAY, legs`。
**`notable_players` (10)**：`account_id, name, country_code, fantasy_role, team_id, team_name, team_tag, is_locked, is_pro, locked_until`
→ **注意：只有当前队伍，没有时间区间**（与 REST `/proPlayers` 同源）。
**`public_matches`**、**`items`**：路人局与物品表，本项目用不上。

#### 1.5.3 超时行为（实测，很重要）

explorer 有**服务端查询读超时**。实测：

- 全表扫描 `SELECT extract(year from to_timestamp(start_time)) ... FROM matches GROUP BY 1`（251k 行）
  → 真实返回 `{"err":"Error: Query read timeout"}`
- `information_schema.columns` 的 GROUP BY 聚合 → 客户端等 120s 无返回

**结论：必须按 `leagueid` 分片查询，禁止无谓的全表扫描。** 加了 `WHERE leagueid=...` 之后
同类查询 1-3 秒返回。这直接决定了全量拉取方案的形状（见 §9）。

#### 1.5.4 真实数据验证：各届 TI 比赛数

```sql
SELECT leagueid, count(*) AS n FROM matches
WHERE leagueid IN (13256,14268,15728,16935,18324,19719) GROUP BY 1 ORDER BY 1
```
真实返回：
```
{'leagueid': 13256, 'n': 487}   -- TI 2021
{'leagueid': 14268, 'n': 231}   -- TI 2022
{'leagueid': 15728, 'n': 151}   -- TI 2023
{'leagueid': 16935, 'n': 121}   -- TI 2024
{'leagueid': 18324, 'n': 144}   -- TI 2025 (TI14)
                                -- TI 2026 (19719) 查得 n=0，赛事尚未开打
```

TI14 时间范围（真实返回）：`{'n':144, 't0':1756973096, 't1':1757872818}`
→ 2025-09-04 至 2025-09-14。

### 1.6 「选手-队伍时间对齐」难点 —— 已解决（派生名单法）

**问题**：`notable_players` / `/api/proPlayers` 只给**当前**队伍快照，没有 valid_from / valid_to。
直接用它会把「今天在 A 队」错误地回填到三年前的比赛上，造成严重的标签泄漏。

**解法**：不要用名册表，**从实际出场记录反推归属**。
`player_matches.player_slot < 128` 即 radiant 方，否则 dire 方；再关联
`matches.radiant_team_id` / `dire_team_id`，就得到 (选手, 队伍, 比赛时间) 三元组。

实测 SQL（TI14）：
```sql
SELECT pm.account_id, np.name AS player,
       CASE WHEN pm.player_slot < 128 THEN m.radiant_team_id ELSE m.dire_team_id END AS team_id,
       count(*) AS games,
       to_char(to_timestamp(min(m.start_time)),'YYYY-MM-DD') AS first_game,
       to_char(to_timestamp(max(m.start_time)),'YYYY-MM-DD') AS last_game
FROM matches m
JOIN player_matches pm ON pm.match_id = m.match_id
LEFT JOIN notable_players np ON np.account_id = pm.account_id
WHERE m.leagueid = 18324
GROUP BY 1,2,3 ORDER BY games DESC
```
真实返回（前 12 行）：
```
{'account_id':183719386,'player':'AMMAR_THE_F','team_id':9247354,'games':29,'first_game':'2025-09-04','last_game':'2025-09-14'}
{'account_id':898455820,'player':'Malr1ne',    'team_id':9247354,'games':29,'first_game':'2025-09-04','last_game':'2025-09-14'}
{'account_id':25907144, 'player':'Cr1t-',      'team_id':9247354,'games':29,'first_game':'2025-09-04','last_game':'2025-09-14'}
{'account_id':100058342,'player':'skiter',     'team_id':9247354,'games':29,'first_game':'2025-09-04','last_game':'2025-09-14'}
{'account_id':10366616, 'player':'Sneyking',   'team_id':9247354,'games':29,'first_game':'2025-09-04','last_game':'2025-09-14'}
{'account_id':129958758,'player':'Xxs',        'team_id':8261500,'games':26,...}
{'account_id':898754153,'player':'Ame',        'team_id':8261500,'games':26,...}
{'account_id':157475523,'player':'XinQ',       'team_id':8261500,'games':26,...}
{'account_id':137129583,'player':'Xm',         'team_id':8261500,'games':26,...}
{'account_id':94296097, 'player':'xNova',      'team_id':8261500,'games':26,...}
{'account_id':111620041,'player':'SumaiL-',    'team_id':7554697,'games':24,...}
{'account_id':101356886,'player':'GH',         'team_id':7554697,'games':24,...}
```
→ 完美还原出 5 人首发阵容（9247354 = Team Falcons 五人整齐 29 场；8261500 = Xtreme Gaming 五人整齐 26 场）。

**这个方法的优点**：
1. 归属完全由**事实出场**决定，不依赖任何名册表，天然 point-in-time 正确，无泄漏。
2. 顺带识别替补/教练代打（该选手 games 数明显低于队友）。
3. 转会点自动浮现：同一 account_id 在时间轴上 team_id 发生切换的那一刻。

**局限**（需在报告中如实说明）：
1. 只能覆盖**有比赛的时间段**。选手转会后如果长期没打职业赛，中间的空窗期归属未知。
2. 拿不到「签约日期」这种合同事实，只有「首次代表新队出场日期」。两者通常差几天到几周。
3. 队伍换名/改组（如 OG 重组、组织出售）在 `team_id` 层面可能不连续，需要人工映射表补。
   → 这三点正是需要 **Liquipedia 做补充源**的地方（Liquipedia 有正式转会日期）。

---

## 2. STRATZ API（api.stratz.com，GraphQL）—— 部分验证

### 已实测的事实

1. **裸请求会被 Cloudflare 拦**。默认 curl UA 或普通浏览器 UA 都返回 Cloudflare 挑战页：
```html
<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>
```

2. **必须带 `User-Agent: STRATZ_API` 才能穿透 Cloudflare**。带上之后拿到干净的 API 错误：
```bash
curl -X POST https://api.stratz.com/graphql \
  -H "Content-Type: application/json" -H "User-Agent: STRATZ_API" \
  -d '{"query":"{ constants { gameVersions { id name } } }"}'
```
真实返回：
```json
{ "message":"A bearer token is required for a request. View more at https://stratz.com/api" }
--HTTP:403
```

→ **STRATZ 结论：必须 (a) UA 设成 `STRATZ_API`，(b) 带 Bearer token。** 两个条件缺一不可。token 获取途径与配额待验证。

---

## 3. Valve 官方 WebAPI —— 部分验证

真实实测，不带 key：

```bash
curl "https://api.steampowered.com/IDOTA2Match_570/GetMatchHistory/v1/?matches_requested=1"
curl "https://api.steampowered.com/IDOTA2Match_570/GetMatchDetails/v1/?match_id=8923506996"
```
两个都返回：
```html
<html><head><title>Forbidden</title></head><body><h1>Forbidden</h1>
Access is denied. Retrying will not help.
Please verify your <pre>key=</pre> parameter.</body></html>
--HTTP:403
```

→ 确认必须有 Steam Web API key。key 申请与实际配额待验证。

---

## 4. Liquipedia —— 可用，但有明确的合规边界

### 4.1 实测：MediaWiki API 可用

```bash
curl --noproxy '*' --compressed -A 'TI15-Research/1.0 (...; email)' \
  'https://liquipedia.net/dota2/api.php?action=query&meta=siteinfo&siprop=general&format=json'
```
真实返回（截取）：
```json
{"batchcomplete":"","query":{"general":{"sitename":"Liquipedia Dota 2 Wiki",
 "generator":"MediaWiki 1.43.9","articlepath":"/dota2/$1","case":"first-letter", ...}}}
```
→ HTTP 200，标准 MediaWiki 1.43.9。**不加 `--compressed` 会被拒**（ToS 明文要求客户端支持 gzip）。

### 4.2 ⚠️ 合规：两份文件互相矛盾，必须读懂再用

**(a) `https://liquipedia.net/robots.txt`（实测原文）**

```
User-agent: GPTBot
User-agent: ClaudeBot
User-agent: Claude-Web
User-agent: cohere-ai
User-agent: ChatGPT-User
...（共约 30 个 UA）
Disallow: /

User-agent: *
...
Disallow: /dota2/api.php          ← 对所有 UA 禁 API 路径
Disallow: /dota2/Special:Ask
Disallow: /dota2/index.php
...
```

**(b) `https://liquipedia.net/api-terms-of-use`（实测原文，站方自己发布的 API 条款）**

> "Liquipedia is pleased to provide free access to the information in our wikis through the MediaWiki API for use in your own projects."
>
> - Rate limit all HTTP requests to no more than 1 request per 2 seconds.
>   **`action=parse` requests should not exceed 1 request per 30 seconds**（更耗资源）。
> - 必须用自定义 `User-Agent`，含项目标识与联系方式；`Python-requests` / `node-fetch` 这类通用 UA「likely to be blocked」。
> - 客户端必须支持 `Content-Encoding: gzip`。
> - 复用 HTTP 连接；尽量缓存，不要重复请求同样的数据。
> - **"Automated access to non-API endpoints (ie, generated HTML pages) is not permitted."**
> - 内容 CC-BY-SA 3.0，必须署名 Liquipedia。
> - 违规先临时封 IP（做 CAPTCHA 可解封），屡犯转永久封禁。

**怎么解读这个矛盾**：robots.txt 的 `Disallow: /dota2/api.php` 是给**搜索引擎爬虫**的收录指令
（不希望 API 响应进搜索索引），而 API 条款是站方对**程序化客户端**的明示授权。
Wikipedia 也是完全一样的组合。**站方明示授权 > robots 的收录指令**，所以走 API 是站方允许的路径。

**但 `User-agent: ClaudeBot / Claude-Web → Disallow: /` 是另一回事**——它明确针对 AI 代理。
本轮采取的立场，请用户知悉并自行决定是否延续：

- ✅ **只走 MediaWiki API，严格按条款限速**（普通请求 ≥2s，`action=parse` ≥30s），带含联系方式的自定义 UA，带 gzip。
- ✅ **优先复用磁盘上已缓存的响应**（条款明文要求 "re-use / cache your API results for as long as possible"）。
  本轮 TI15 信息全部从首轮已缓存的 `lp_ti2026.json` 本地解析得出，**没有新发请求**。
- ❌ **绝不抓 HTML 页面**（条款明文禁止）。
- ⚠️ 由于 robots.txt 里点名封了 Claude 系 UA，**不建议把 Liquipedia 做成常态化自动抓取管道**。
  建议方式：(1) 人工从页面导出需要的名单；或 (2) 申请官方 LiquipediaDB API key（条款里的另一条路径，
  限速 60 请求/小时，需申请审批）。**LiquipediaDB key 本轮未申请，配额与字段未验证。**

### 4.3 已从缓存解析出的 TI15 事实（来源：Liquipedia，CC-BY-SA 3.0）

从 `lp_ti2026.json`（页面 `The International/2026`，pageid 183825）本地解析：

```
The International 2026 (TI 15)
主办: Valve + PGL          地点: 中国上海，Oriental Sports Center（淘汰赛）
赛制: Group Stage 瑞士轮 / Playoffs 双败淘汰
奖金池: $1,600,000 USD     参赛队: 16      Liquipedia Tier: Tier 1
日期: 2026-08-13 ~ 2026-08-23
  小组赛 8/13-8/16  瑞士轮 16 队，全部 Bo3，前 3 名直进淘汰赛，
                    第 4-13 名进 Elimination Round（再出线 5 队），其余淘汰
  正赛   8/20-8/23  双败淘汰，总决赛 Bo5
页面自带提示: "This tournament page is under construction and is subject to major revisions."
```

⚠️ **`Participants` 小节在缓存快照里是空的**（页面在建），所以 **16 强名单没能从 Liquipedia 拿到**。
不过 OpenDota 侧的预选赛数据已经能补上（见 §4.4）。

**⚠️ 瑞士轮是建模的重要变化**：TI13/TI14 的小组赛是循环赛，TI15 改瑞士轮。
瑞士轮的对阵是**按战绩动态配对**的，意味着 (1) 无法预先枚举全部对阵，(2) 模拟赛程必须实现瑞士轮配对逻辑，
(3) 强队之间的对局密度显著高于循环赛。沿用往届赛制的模拟器会算错晋级概率。

### 4.4 TI15 五个赛区预选赛：已全部打完（OpenDota 实测）

```
19890 NA   n=13  2026-06-24..06-27
19891 SA   n=39  2026-06-15..06-19
19892 EU   n=63  2026-06-21..06-28
19893 CN   n=29  2026-06-15..06-18
19894 SEA  n=44  2026-06-19..06-23
19719 TI15 正赛 n=0（未开打）
```

各赛区决赛胜者（按每个 league 最后 3 场推断）：
```
NA  : GamerLegion   （3-0 击败 "4 Anchors + Ilmeria"）
SA  : LGD Gaming    （team_id=10150538，见下方警告）
EU  : Nigma Galaxy  （击败 Yellow Submarine）
CN  : Vici Gaming   （击败 Yakult Brothers）
SEA : OG            （team_id=2586976，3-0 击败 TEAM GRIND）
```

> ⚠️ **`teams.name` 不是唯一键，也不是 point-in-time 的。** SA 冠军显示为 "LGD Gaming"，
> 但其 `team_id=10150538` 是新近创建的 ID，与中国的 PSG.LGD **不是同一实体**——只是重名。
> 而 SEA 冠军 "OG" 的 `team_id=2586976` 确实是老牌 OG（2015-11-02 至今 2,190 场）。
> **建模一律以 `team_id` 为键，`name` 只作展示；且要意识到 `teams.name` 存的是「当前名」，
> 组织改名后历史比赛会被回填成新名字。**

---

## 5. datdota / Dotabuff / STRATZ 网站 —— 结论：不要爬

三站都在用 Cloudflare Content Signals，`User-agent: *` 段一致为：
```
Content-Signal: search=yes, ai-train=no, use=reference
```
即：允许搜索引擎收录，**明确拒绝用于 AI 训练**，AI 系统只可作 "reference" 使用。

### 5.1 Dotabuff —— **明确不能爬**（两重禁止）

`https://www.dotabuff.com/robots.txt` 实测：
```
User-agent: ClaudeBot          →  Disallow: /
User-agent: GPTBot             →  Disallow: /
User-agent: CCBot              →  Disallow: /
User-agent: Google-Extended    →  Disallow: /
User-agent: Bytespider / Amazonbot / Applebot-Extended / meta-externalagent → Disallow: /

User-agent: *
Disallow: /esports/events/*/matches
Disallow: /esports/events/*/drafts
Disallow: /esports/events/*/players
Disallow: /esports/events/*/picks
Disallow: /esports/events/*/series
Disallow: /esports/events/*/teams
Disallow: /esports/leagues/*/matches
Disallow: /esports/leagues/*/drafts
Disallow: /esports/leagues/*/picks
...
```
→ **我们想要的每一类数据路径（matches / drafts / players / picks / series / teams）
都对所有 UA 明文 Disallow**，另外 ClaudeBot 被整站封。**结论：Dotabuff 完全排除，不抓。**

### 5.2 datdota —— **不能自动抓**

`https://www.datdota.com/robots.txt` 实测：`User-agent: *` 是 `Allow: /`（无路径限制），
但 **`User-agent: ClaudeBot → Disallow: /`**，且 Content-Signal `ai-train=no`。
→ **作为 AI 代理不应抓取。** datdota 的独特价值（历史 BP 统计、选手长周期趋势）需要人工浏览获取，
或直接用 OpenDota 原始数据自己算——本项目 §7.3 的 343 万条 picks_bans 已经覆盖了 datdota 的主要用途。

### 5.3 STRATZ

网站 robots 同上（`ai-train=no`）。API 侧首轮已实测门槛（§2）：必须 `User-Agent: STRATZ_API` + Bearer token。
→ **官方 API 是唯一合规路径，需要注册 token。本轮未申请，因为 OpenDota 已覆盖全部需求。**
STRATZ 的独有增量主要是官方战队/选手 rating 与更细的位置标注；**若要用，走 API 不走网页。**

---

## 6. 现成数据集（Kaggle / HuggingFace / GitHub）—— 价值低于自建

### 6.1 实测可达性

| 源 | 实测结果 |
|---|---|
| `blog.opendota.com/2017/03/24/datadump/`（传说中的官方 dump） | **HTTP 404**，已下线 |
| `academictorrents.com`（搜 dota） | **HTTP 000**，本机网络不可达（未验证内容） |
| `huggingface.co/api/datasets?search=dota` | **HTTP 000**，本机网络不可达（重试 2 次均失败，未验证内容） |
| `api.github.com` 搜索 | ✅ HTTP 200 可用 |

GitHub 搜索 `dota2 matches data` 按星标排序的真实返回：
```
★ 32  masterhood13/dota2predictor              最后更新 2024-11-11
★ 19  dota2-bkb/ti14-vision                    最后更新 2025-11-16
★ 19  bugman-007/dota2predictor                最后更新 2025-11-22
★ 14  shibotong/D2A                            最后更新 2026-08-01
★ 10  leamare/D2-LRG-lrg2                      最后更新 2026-07-20
★  6  basinlocustmattock/dota2-predictor-analytics  最后更新 2026-06-13
★  4  hkaanengin/opendota-mcp-server           最后更新 2026-01-28
```

### 6.2 结论

**都是个人项目量级（最高 32 星），没有权威的、持续维护的公开数据集。**
而且它们绝大多数就是 OpenDota 的二手转存 —— 我们已经用 15 分钟拿到了一手全量。

→ **本项目不依赖任何现成数据集。** 唯一可能有参考价值的是 `dota2-bkb/ti14-vision`（TI14 专项）
和 `leamare/D2-LRG-lrg2`（近期仍在更新），**但内容未核验**，仅建议当作方法论参考、不作数据源。
Kaggle 需要登录，本轮未验证。

---

## 7. 已落地数据（真实文件，2026-08-02 核对）

目录：`.../ti15-research/data/`。抓取器：
- `od_sql.py` — 通用 explorer SQL 执行器（清代理 / 限速 / 指数退避重试），可 import 可 CLI。
- `fetch_opendota_explorer.py` — 首轮按 leagueid 抓 TI 的脚本（带 JOIN，慢，已被下面取代）。
- `fetch_pro_all.py` — **全量职业比赛抓取器，按时间窗分片、逐片落盘、断点续跑**。

### 7.1 TI 专项数据（首轮产出，已验证）

| 文件 | 行数 | 内容 |
|---|---|---|
| `ti_2021_2025_matches.csv` | 1,134 | TI10-TI14 比赛级（30 列，含队名/patch/BO 制式） |
| `ti_2021_2025_player_matches.csv` | 11,340 | 选手-比赛级（40 列） |
| `ti_2021_2025_picks_bans.csv` | 27,131 | BP 序列 |
| `ti_2021_2025_roster_derived.csv` | 663 | 派生名单（§1.6 方法） |
| `ti14_*.csv` | — | TI14 单届子集（4 个文件，与上面重复，可删） |

覆盖 leagueid `13256,14268,15728,16935,18324`。TI 2026（19719）此刻 `n=0`，赛事未开打。

### 7.2 全量职业比赛（2020-01-01 ~ 2026-08-02）—— P0 目标

**先估算再拉取。** 真实 count 查询结果（`matches JOIN leagues`，`start_time >= 1577836800`）：

| tier | 场次（2020 至今） |
|---|---|
| professional | 132,365 |
| premium | 13,609 |
| **premium + professional 合计** | **145,974** |
| （excluded，不取） | 23,314 |

逐年分布（实测）：

| 年 | premium | professional | 合计 |
|---|---|---|---|
| 2020 | 891 | 21,493 | 22,384 |
| 2021 | 4,694 | 12,113 | 16,807 |
| 2022 | 3,881 | 21,070 | 24,951 |
| 2023 | 3,878 | 26,624 | 30,502 |
| 2024 | **121** | 26,362 | 26,483 |
| 2025 | **144** | 20,100 | 20,244 |
| 2026(至 8/2) | **0** | 4,603 | 4,603 |
| **合计** | 13,609 | 132,365 | **145,974** |

#### ⚠️ 重大发现 1：`tier` 字段 2024 年后失效，不能拿来切 tier-1

2024 年 premium 只有 **121** 场、2025 只有 **144** 场——而这两个数字**恰好等于 TI13(121) 和 TI14(144) 的全部场次**。
也就是说 **2024 年起 OpenDota 只把 TI 本体标成 premium，ESL One / DreamLeague / Riyadh Masters /
PGL Wallachia 等全部降标成 `professional`**。2026 年 premium 干脆是 0。

→ **结论：`tier='premium'` ≠ tier-1。不要用它做赛事分级。** 它只能当「是不是有组织的职业赛」的粗筛。
真正的 tier-1 分级必须外部引入（Liquipedia 的 Tier 标注，见 §4）。

#### ⚠️ 重大发现 2：145,974 场里绝大多数是低级别车轮赛

按场次排序 2024 年至今的赛事 top 6（实测）：

```
17366 n=5488  Ultras Dota Pro League 2024-25
15901 n=4412  Ultras Dota Pro League 2023-24
16059 n=3504  Destiny League
16312 n=1652  Ancients League
16325 n=1550  Ancients League
17381 n=1107  European Pro League 2024-2025 Season
```

这些是常年开的**东欧/独联体线上车轮赛**（tier-3/tier-4），场次碾压真正的 major。
ESL One / DreamLeague 出现在榜上的条目还都是它们的 **Qualifiers**（预选赛），正赛场次只有几十场。

→ **建模含义**：`professional` 池不是「tier-1/tier-2」，是「所有有组织的联赛」，tier 跨度极大。
对 Glicko/Elo 来说这**未必是坏事**——低级别赛事提供了连接图的连通性和大量样本；
但**必须给每场加权或分层**，否则一支只打 Ultras 联赛的队会靠刷场次拿到虚高分。
可行做法：(a) 用 Liquipedia tier 给赛事打标签做权重；(b) 或直接把 rating 的 K 值 / Glicko RD 按赛事级别缩放。

#### 实际拉取结果（match 级 —— 已完成）

```
[matches] 7 chunks total, 7 to run
[matches] 1/7 key=2020 22384 rows in 8.6s
[matches] 2/7 key=2021 16807 rows in 3.8s
[matches] 3/7 key=2022 24951 rows in 5.5s
[matches] 4/7 key=2023 30502 rows in 6.9s
[matches] 5/7 key=2024 26483 rows in 6.0s
[matches] 6/7 key=2025 20244 rows in 5.8s
[matches] 7/7 key=2026  4603 rows in 3.0s
[merge] matches: 7 parts -> 145974 rows -> data/pro_matches_2020_2026.csv
```

**`data/pro_matches_2020_2026.csv`：145,974 行，17.1 MB，22 列，7 次请求，总耗时 41 秒。**

列：`match_id, leagueid, start_time, duration, radiant_win, radiant_team_id, dire_team_id,
radiant_score, dire_score, series_id, series_type, game_mode, lobby_type, human_players,
first_blood_time, tower_status_radiant, tower_status_dire, barracks_status_radiant,
barracks_status_dire, radiant_captain, dire_captain, version`

维表（本地拼接用，不在主查询里 JOIN）：
- `data/pro_dim_leagues.csv` — 10,024 行（leagueid, name, tier）
- `data/pro_dim_teams.csv` — 22,384 行（team_id, name, tag）

#### 🔑 性能关键：**不要在大查询里做 LEFT JOIN**

这是本轮最有价值的工程发现，直接把全量拉取从「跑不完」变成「41 秒」：

| 查询 | 行数 | 耗时 |
|---|---|---|
| 首轮：matches + 4 个 LEFT JOIN（leagues/match_patch/teams×2），5 个 TI league | 1,134 | 7.8s |
| 首轮：picks_bans + JOIN，5 个 TI league | 27,131 | **309.8s** |
| 本轮：matches 无 JOIN（只留 leagues 做 tier 过滤），整个 2023 年 | 30,502 | **11.5s** |
| 本轮：player_matches 无附加 JOIN，单月 | 18,680 | **6.0s** |

→ 差了 **一到两个数量级**。规程：**主表只 JOIN 必需的过滤表，维表整表单独 dump，本地 pandas merge。**

### 7.3 P0 最终交付：全量三件套已全部落地 ✅

| 文件 | 行数 | 大小 | 分片 | 耗时 |
|---|---|---|---|---|
| `data/pro_matches_2020_2026.csv` | **145,974** | 16.3 MB | 7（按年） | 41s |
| `data/pro_player_matches_2020_2026.csv` | **1,459,742** | 182.4 MB | 80（按月） | ~5 分钟 |
| `data/pro_picks_bans_2020_2026.csv` | **3,436,132** | 138.7 MB | 80（按月） | ~4 分钟 |
| `data/pro_dim_leagues.csv` | 10,024 | 0.4 MB | 整表 | 14s |
| `data/pro_dim_teams.csv` | 22,384 | 0.6 MB | 整表 | 2.4s |

**合计约 169 次 API 请求、约 15 分钟墙钟、338 MB，全程匿名无 key，日额度只用掉 ~220/3000。**

年度覆盖校验（对落地 CSV 重新统计，非查询回显）：
```
2020: 22384   2021: 16807   2022: 24951   2023: 30502
2024: 26483   2025: 20244   2026:  4603   TOTAL: 145974  ✅ 与 count 估算完全一致
```

分片中间产物在 `data/pro_parts/`（162 个文件），进度日志 `data/pro_fetch.log`，
断点状态 `data/pro_fetch_state.json`。重跑 `fetch_pro_all.py <task>` 会自动跳过已完成分片。

> **注意**：`player_matches` / `picks_bans` 两份是**全量**（不是原计划的「只保 tier-1」）。
> 因为实测吞吐远超预期（单月 3-6 秒），没有必要降级。原「tier-1 白名单」方案作废。

---

## 8. 数据质量核查（P1，全部实跑）

### 8.1 `roster_derived.player_name` 空值 —— 成因已定位

实测（`ti_2021_2025_roster_derived.csv`，663 行）：

```
player_name 空值      211/663 行     = 31.8%
按出场加权             2240/11340 人-场 = 19.8%
唯一 account_id        200/490        = 40.8%
同一 account 既有名又无名的情况：0 个
```

**成因**：`player_name` 来自 `LEFT JOIN notable_players np ON np.account_id = pm.account_id`。
`notable_players` 全表只有 **5,081** 行，而它是 OpenDota 人工策展的「知名选手」子集，**不是完整选手注册表**。
用户抽查的 `account_id=94738847`（EHOME，11 场）实测 **`SELECT count(*) FROM notable_players WHERE account_id=94738847` → 0**，
即该 account 根本不在表里。

「同一 account 既有名又无名 = 0」这条证明它是**干净的 join miss**（要么整个 account 有名、要么整个没名），
而不是某些行的数据损坏。

**影响**：
- 对建模**几乎无影响**——`account_id` 是 100% 完整的，它才是选手的稳定主键。`player_name` 只是给人看的展示名。
- 唯一实际影响：出报告/可视化时 40.8% 的选手显示为空白。

**补名方案（按代价排序）**：
1. `/api/players/{account_id}` REST 端点逐个查 `personaname`（490 个选手 = 490 次请求，
   在 3000/天 额度内，约 9 分钟）。**未验证该端点对无名 account 是否有返回**。
2. Liquipedia 按 Steam ID 反查正式选手名（还能顺带拿到国籍、位置、战队履历）。
3. `proPlayers`（5,074 行）与 `notable_players`（5,081 行）同源，补不了。

### 8.2 TI 正赛 vs 预选赛 —— 只有 TI 2021 混了，其余干净

实测每个 TI leagueid 的时间跨度与场次：

```
13256 The International 2021  n=487  2021-06-23 .. 2021-10-17   ← 混了预选赛
14268 The International 2022  n=231  2022-10-15 .. 2022-10-30
15728 The International 2023  n=151  2023-10-12 .. 2023-10-29
16935 The International 2024  n=121  2024-09-04 .. 2024-09-15
18324 The International 2025  n=144  2025-09-04 .. 2025-09-14
```

leagueid 13256 的按月直方（实测）：
```
2021-06  124
2021-07  169     ← 这 293 场是各赛区预选赛
(8月、9月无比赛 —— 2.5 个月的天然断档)
2021-10  194     ← TI10 正赛（布加勒斯特，10/7-10/17）
```

**194 场与 TI10 正赛赛制吻合**：18 队分 2 组各 9 队，组内 Bo2 循环 = 2×(36 系列×2 局) = 144 局，
加淘汰赛 Bo3/Bo5 约 50 局 → ≈194。

**有没有字段能切开？——没有。** `matches` 表 40 列里不存在「阶段 / stage / 正赛-预选」字段。
实测 `leagues` 表也只有 `leagueid, ticket, banner, tier, name` 五列，无层级信息。

**答案：靠 leagueid + 日期切，规则如下（可直接落代码）**

| 届 | 正赛 leagueid | 正赛日期过滤 | 预选赛在哪 |
|---|---|---|---|
| TI10 (2021) | 13256 | **`start_time >= 2021-10-01`**（取 194 场） | 同一 leagueid 的 6-7 月，293 场 |
| TI11 (2022) | 14268 | 全取（231 场） | 独立 league `14642` = Last Chance Qualifiers |
| TI12 (2023) | 15728 | 全取（151 场） | 不在库内（未找到对应 league） |
| TI13 (2024) | 16935 | 全取（121 场） | 独立 league `16839-16844` = Road To TI2024 Regional Qualifiers |
| TI14 (2025) | 18324 | 全取（144 场） | 独立 `18304-18309`(Regional) + `18178-18186`(Open, tier=excluded) |
| TI15 (2026) | 19719 | 全取（现 0 场） | 独立 `19890-19894`(Regional) + `19838-19842`(Open, tier=excluded) |

注意还有一个 `18681 | excluded | The International 2025 (Practice)` —— 训练赛，tier 是 excluded，
默认过滤条件已经排掉，但如果有人放宽 tier 过滤要记得剔。

**「TI 正赛局数」的正确口径**：TI10=194，TI11=231，TI12=151，TI13=121，TI14=144。合计 **841 场**
（不是首轮那张表里 487+231+151+121+144=1,134，那个数把 TI10 的 293 场预选赛算进去了）。

### 8.3 关键字段空值率 / 异常值

**`matches` 级（先看 TI 子集 1,134 行）**
```
radiant_win        空值 0        取值 True 577 / False 557（radiant 胜率 50.9%）
radiant_captain    空值 3 (0.3%)
dire_captain       空值 3 (0.3%)
human_players      全部 = 10（无异常）
game_mode          全部 = 2（Captains Mode）
lobby_type         全部 = 1（tournament）
radiant/dire_team_id 空或 0：0 场
duration           min=569s  p1=1172s  中位=2348s  max=6440s；<600s 仅 1 场
```

**`matches` 级（全量 145,974 行，2020-2026）—— 逐年实测**

| 年 | 场次 | unparsed(`version` 空) | `radiant_win` 空 | **无 team_id** | duration<10min |
|---|---|---|---|---|---|
| 2020 | 22,384 | 51 (0.2%) | 0 | 1,111 (5.0%) | 34 |
| 2021 | 16,807 | 169 (1.0%) | 0 | 736 (4.4%) | 34 |
| 2022 | 24,951 | 20 (0.1%) | 0 | 1,322 (5.3%) | 26 |
| 2023 | 30,502 | 61 (0.2%) | **7** | 877 (2.9%) | 37 |
| 2024 | 26,483 | 36 (0.1%) | 0 | 1,506 (5.7%) | 52 |
| 2025 | 20,244 | 6 (0.0%) | 0 | 1,535 (7.6%) | 35 |
| 2026 | 4,603 | 7 (0.2%) | 0 | **473 (10.3%)** | 15 |

- **`radiant_win` 极干净**：全量 145,974 场只有 **7 场**为空（都在 2023），空值率 **0.005%**。直接 dropna 即可。
- **最大的质量问题是 `team_id` 缺失**：合计约 **7,560 场（5.2%）** 至少一方没有 `team_id`，
  且**逐年恶化，2026 年已达 10.3%**。这些场次**无法进入战队 Elo/Glicko**（不知道是谁在打）。
  成因是低级别赛事里战队未在 Valve 侧注册战队 ID（打散排/临时队名）。
  → 处置：战队评分建模时直接剔除这 5.2%；但**可以用 §10 的派生名单法按「五人选手集合」反查队伍身份**，抢回一部分。
- unparsed（`version` 为空 = 详细数据未解析）全量 < 1%，可忽略。**注意：`version` 为空只影响
  `player_matches` 里的细粒度列，不影响胜负/时长/队伍等基础列。**
- duration < 10 分钟 233 场（0.16%），是 remake / 秒退，建模前剔掉。

**`player_matches` 级空值率（TI 子集 11,340 行实测）**
```
account_id                 0.0%   ← 主键完整
hero_id / kills / gpm / net_worth / xpm   0.0%
player_name               19.8%   ← notable_players 覆盖不全（见 8.1）
fantasy_role              19.8%   ← 同源同因
country_code              42.2%   ← 同源，更差
teamfight_participation    0.4%   ← 4 场未解析
lane / lane_role           0.4%
obs_placed / sen_placed / stuns  0.4%
is_roaming                63.6%   ← ⚠️ 不是缺失，见下
```

**`is_roaming` 的 63.6% 空值是陷阱**：它是 `boolean`，OpenDota 对「不是游走位」的选手写 `NULL` 而非 `false`。
**必须 `fillna(False)`，不能 dropna**，否则会把 2/3 的样本删掉。
（推断依据：0.4% 是真正的未解析率，`lane`/`lane_role` 都是 0.4%，而 `is_roaming` 是 63.6%，
两者同属解析产物，差值只能是语义空。**此为推断，未做逐行交叉验证。**）

**结构完整性（TI 子集）**
```
每场选手数分布: {10: 1134}      ← 1,134 场全部恰好 10 人，无缺人
matches 有而 player_matches 无: 0  ← 无孤儿比赛
```

---

## 9. 全量拉取成本估算（基于实跑，非拍脑袋）

实测吞吐（`/api/explorer`，匿名，无 key）：

| 数据集 | 分片方式 | 单片行数 | 单片耗时 | 分片数 | 总请求 | 总耗时 | 落地大小 |
|---|---|---|---|---|---|---|---|
| matches 2020-2026 | 按年 | 4.6k-30.5k | 3.0-8.6s | 7 | 7 | **41s** | 17.1 MB |
| dim leagues + teams | 整表 | 10.0k / 22.4k | 14.0s / 2.4s | 2 | 2 | 16s | 1.0 MB |
| player_matches 2020-2026 | 按月 | ~13k-29k | 3.2-6.0s | 80 | 80 | **~7 分钟** | ~250 MB |
| picks_bans 2020-2026 | 按月 | ~44k | 待测 | 80 | 80 | 待测 | ~200 MB |

**额度消耗**：全量 match 级 + 维表 + player_matches 全量 ≈ **90 次请求**，
而匿名日额度是 **3,000 次/天**。→ **额度完全不是瓶颈，一天可以重跑 30 次。**
（实测本轮从 day=2998 用到 day≈2940，一整轮全量拉取只花掉约 60 次。）

**真正的瓶颈是服务端单查询读超时**，不是额度。所以规则是：
1. 分片要小（月级最稳，年级对 match 表够用）；
2. 不做 LEFT JOIN（见 §7.2）；
3. 只 SELECT 需要的列——`matches` 表有 `chat`/`objectives`/`radiant_gold_adv`/`teamfights`
   等 ARRAY/json 巨列，一旦 `SELECT *` 响应体会炸掉且必然超时。**本项目所有查询都显式列名，从不 `SELECT *`。**

**成本结论：OpenDota 全量抓取对本项目是「分钟级、零成本、零 key」的操作。**
不需要 STRATZ token，不需要 Steam key，不需要付费。

---

## 10. 「选手-队伍时间对齐」可复用方法说明（P3）

> 这是整个项目最关键的一块。§1.6 已证明方法可行，本节把它写成可直接落代码的规程，
> 并列出全部已知边界情况与失效场景（全部有实测证据）。

### 10.1 问题重述

要给战队/选手建 Glicko 或 Elo，必须知道**在某场比赛发生的那一刻**，某个选手属于哪支队。
OpenDota 唯一的名册来源 `notable_players` / `/api/proPlayers`（5,081 行）
**只有 `team_id` 当前快照，没有 `valid_from` / `valid_to`**。
直接用它 = 把今天的归属回填到三年前 = **标签泄漏**，模型会「知道未来」。

### 10.2 核心方法：派生名单法（Derived Roster）

**不用名册表，从实际出场记录反推归属。**

**Step 1 — 逐场求 (选手, 队伍, 时刻) 三元组**

`player_matches.player_slot` 是位置槽：`0-4` 为天辉，`128-132` 为夜魇。判据：

```sql
CASE WHEN pm.player_slot < 128 THEN m.radiant_team_id ELSE m.dire_team_id END AS team_id
```

配合 `m.start_time`，得到事实层的 `(account_id, team_id, start_time)`。
**这一层天然 point-in-time 正确**——它只陈述「某人在某天代表某队打了一场」，不含任何未来信息。

**Step 2 — 压成带区间的名册**

按 `(account_id, team_id)` 分组，取 `min(start_time)` / `max(start_time)` / `count(*)`，
即 `first_game` / `last_game` / `games`。这就是 `*_roster_derived.csv` 的形态。

**Step 3 — 查询时点归属**

对任意 `(account_id, T)`，取满足 `first_game <= T <= last_game` 的 `team_id`；
若命中多条（转会重叠期），取**离 T 最近的一场实际出场**所对应的队伍。

> **实现要点**：Step 3 不要用 Step 2 的区间做「区间包含」判定，那会在转会重叠期出错。
> 更稳的做法是**直接在 Step 1 的三元组上做 as-of join**：
> 「取该 account 在 T 之前（含 T）最近一场比赛的 team_id」。
> 这样天然无泄漏、天然处理重叠，且不需要维护区间表。**as-of join 才是生产实现，区间表只用于人看。**

**Step 4 — 反向用法：由五人集合反查队伍身份**

`team_id` 缺失的比赛（全量里占 5.2%，见 §8.3）可以靠这个抢救：
把该场 5 人的 `account_id` 集合，与已知名册做 Jaccard 相似度匹配，≥4/5 命中即可认定队伍身份。

### 10.3 实测验证：TI14 完美还原

见 §1.6 的真实返回——Team Falcons(9247354) 五人整齐 29 场、
Xtreme Gaming(8261500) 五人整齐 26 场，首发阵容 100% 还原。

补充验证（本轮实测）：**TI14 全部队伍中，出场人数 > 5 的队伍数 = 0。**
即 TI14 没有任何替补，方法在该届是无歧义的。

### 10.4 边界情况与处理（全部有实测案例）

#### (1) 赛中换人 / stand-in —— 有真实案例，可自动识别

实测 TI10（leagueid 13256）里出场人数 > 5 的队伍恰好有 2 支：

```
Team Aster (正赛 2021-10-07..10-12)
  89423756  (无名)     17 场   10-07..10-12
  148215639 Monet      17 场   10-07..10-12
  129958758 Xxs        17 场   10-07..10-12
  207829314 BoBoKa     17 场   10-07..10-12
  373520478 (无名)     13 场   10-08..10-12   ← 从 10-08 开始接手
  182439266 (无名)      4 场   10-07..10-07   ← 只打了 10-07 这一天

BOOM Esports (SEA 预选赛 2021-06-30..07-03)
  389033587 Straight Edge 14 场  06-30..07-03
  237325411 (无名)        14 场  06-30..07-03
  301750126 Mikoto        14 场  06-30..07-03
  143278997 (无名)        14 场  06-30..07-03
  297926352 (无名)         8 场  07-02..07-03  ← 从 07-02 接手
  156328257 Fbz            6 场  06-30..07-01  ← 只打前两天
```

**识别规则（可直接落代码）**：同一 `team_id` 在同一赛事内出场人数 > 5，
且存在选手的 `games` 明显低于队内中位数 → 该选手是替补/stand-in，
且**两人的 `[first_game, last_game]` 区间基本不重叠 = 一次换人交接**。

**处理建议**：
- 战队级 Elo/Glicko：**不受影响**，评分对象是 `team_id`，换谁上都算这支队。
- 选手级评分：按 as-of join 自然处理，替补只在他实际出场的日期段计入。
- 若要做「阵容完整度」特征：用「本场 5 人中有几人属于该队近 30 天的主力五人」作为特征，
  这恰好能捕捉「带伤/代打导致战力下降」，对 TI 这种有签证/健康问题的赛事很有用。

#### (2) 一个选手同期出现在多支队 —— 低级别联赛里极其普遍

实测 2025-01-01 至今，按「同一 account 打过几支不同 team_id」排序：

```
account=1029972951   148 支队   2300 场
account=1811371866   147 支队   1300 场
account=1868210186   144 支队   1281 场
account=130433320    128 支队   1104 场
account=399588134    128 支队   1541 场
...（前 12 名全部 ≥120 支队）
```

一年半打 120-148 支「不同队伍」，显然不是转会。真相是：
**在 Ultras / Destiny / Ancients 这类天天开的线上车轮赛里，`team_id` 是临时报名注册的，
不代表稳定的组织身份。** 同一批人今天叫 A 队明天叫 B 队。

→ **这是派生名单法的头号失效场景。** 处理：**必须先做赛事级别过滤**，
只在 tier-1/tier-2 赛事上派生名册。在低级别赛事池上跑，得到的「名册」是垃圾。

#### (3) 队伍改名 / 重组 / `team_id` 复用

- `teams.name` 存的是**当前名**，组织改名后**历史比赛会被回填成新名字**（非 point-in-time）。
- 名字**不唯一**：实测 TI15 SA 预选赛冠军显示 "LGD Gaming"，`team_id=10150538`，
  与中国 PSG.LGD 完全无关，只是重名。
- 长寿 `team_id` 确实存在（实测 `team_id=5` 跨 2012-07-19 至 2024-09-10 共 2,724 场；
  `team_id=2586976`(OG) 跨 2015-11-02 至 2026-08-01 共 2,190 场），
  所以 `team_id` 本身**够稳**，问题只在 `name`。

→ **规程：一切以 `team_id` 为主键。需要人读的名字，用「该 team_id 在目标时间段内比赛所显示的名字」，
不要用 `teams` 维表的当前名。** 组织层面的连续性（如 OG 重组、战队被收购换 ID）需要人工映射表，
Liquipedia 有正式转会/改名日期，但受 §4.2 的合规限制。

#### (4) 赛事跨阶段（预选赛 → 正赛）名册变化

TI10 的 BOOM Esports 案例就在预选赛阶段。**如果按整个 leagueid 派生名册，
会把预选赛阵容和正赛阵容合并成一个「6-7 人名册」**，看起来像替补，实际是两套阵容。

→ 规程：**派生名册的时间窗要比 leagueid 更细**。建议按「赛事阶段」或直接用 as-of join
（§10.2 Step 3 的做法天然规避这个问题）。

#### (5) 空窗期归属未知

选手转会后若长期不打职业赛，中间的归属无法从出场记录推出。
as-of join 会把他一直判给「上一次出场的队」，直到他为新队出场为止。
→ 这是**已知偏差**，方向是「滞后」。对 TI 预测影响小（TI 前各队都有热身赛），
但对「新签约选手」类特征会失真。**只能靠 Liquipedia 的合同日期修正。**

#### (6) 拿不到「签约日期」，只有「首次代表新队出场日期」

两者通常差几天到几周。**对建模其实是好事**——我们要的是「这套阵容一起打过多少场」，
出场日期比合同日期更贴近真实战力形成时间。**但报告口径要说清楚，别把它称作转会日期。**

### 10.5 失效场景总结（一句话版）

| 场景 | 是否失效 | 处理 |
|---|---|---|
| 顶级赛事稳定五人 | ✅ 完美 | 直接用 |
| 赛中换人 / stand-in | ✅ 能识别 | 用 as-of join，可派生「阵容完整度」特征 |
| 低级别车轮赛的临时 team_id | ❌ **完全失效** | **必须先按赛事级别过滤** |
| 队伍改名 / 重名 | ⚠️ 部分失效 | 一律用 `team_id`，不信 `name` |
| 赛事跨阶段名册变化 | ⚠️ 会误判为替补 | 时间窗切细，或直接 as-of join |
| 转会空窗期 | ⚠️ 归属滞后 | 已知偏差，需 Liquipedia 修正 |
| 缺 `team_id` 的比赛（5.2%） | ⚠️ 无队伍身份 | 用五人集合 Jaccard 反查（§10.2 Step 4） |

---

## 11. 字段需求对照表：建模要什么 × 哪个源能给

「可得性」列全部基于本轮实测，未验证的明确标注。

### 11.1 战队实力评分（Glicko / Elo）—— 最低要求

| 需要的字段 | OpenDota | 落地文件 | 状态 |
|---|---|---|---|
| 比赛唯一键 | `matches.match_id` | `pro_matches_2020_2026.csv` | ✅ 145,974 场 |
| 时间戳（排序/时间衰减） | `matches.start_time` | 同上 | ✅ 0 缺失 |
| 双方队伍 | `radiant_team_id` / `dire_team_id` | 同上 | ⚠️ 5.2% 缺失 |
| 胜负 | `matches.radiant_win` | 同上 | ✅ 缺失 0.005%（7/145,974） |
| 赛事身份 | `matches.leagueid` + `pro_dim_leagues.csv` | ✅ | ✅ |
| **赛事级别（tier-1/2/3）** | `leagues.tier` | — | ❌ **2024 年后失效，见 §7.2** |
| BO 制式 / 系列赛 | `series_id` + `series_type` | 同上 | ⚠️ series_type 语义已更正；series_id 有串号 |
| 净胜局 | 由 `series_id` 聚合得出 | 同上 | ✅ 可算 |
| 版本 patch | `match_patch` 表 | 未落地 | ⏸ 单表可拉，本轮未拉（TI 子集里已有） |

→ **战队评分所需字段已 100% 齐备**，唯一外部缺口是**赛事级别标注**。

### 11.2 战队打法特征

| 需要的字段 | 来源 | 状态 |
|---|---|---|
| 比赛时长（快攻/后期倾向） | `matches.duration` | ✅ |
| 一血时间 | `matches.first_blood_time` | ✅ |
| 推塔/兵营进度 | `tower_status_*` / `barracks_status_*`（位掩码） | ✅ |
| 击杀数 | `radiant_score` / `dire_score` | ✅ |
| 队长（BP 决策人） | `radiant_captain` / `dire_captain` | ✅ 缺失 0.3% |
| 逐分钟经济/经验差曲线 | `matches.radiant_gold_adv` / `radiant_xp_adv`（ARRAY） | ⏸ **未拉**（巨列，会撑爆查询，需单独按场分片） |
| 肉山/推塔事件流 | `matches.objectives`（ARRAY） | ⏸ 同上 |
| 团战 | `matches.teamfights`（ARRAY） | ⏸ 同上 |
| BP 序列（顺位/pick/ban） | `picks_bans` | ✅ **3,436,132 条已落地** |
| BP 计时（犹豫时长） | `matches.draft_timings`（ARRAY） | ⏸ 未拉 |

### 11.3 选手层特征

| 需要的字段 | 来源 | 状态 |
|---|---|---|
| 选手主键 | `player_matches.account_id` | ✅ 0 缺失 |
| 选手展示名 | `notable_players.name` | ⚠️ **覆盖不全，19.8% 空**（见 §8.1） |
| 国籍 | `notable_players.country_code` | ⚠️ 42.2% 空 |
| 位置（fantasy_role） | `notable_players.fantasy_role` | ⚠️ 19.8% 空 |
| 分路 / 位置（每场实测） | `player_matches.lane` / `lane_role` | ✅ 0.4% 空（比名册可靠得多） |
| 游走位标记 | `player_matches.is_roaming` | ⚠️ **63.6% 是语义空，须 fillna(False)** |
| K/D/A | `kills` / `deaths` / `assists` | ✅ |
| 经济/经验效率 | `gold_per_min` / `xp_per_min` / `net_worth` | ✅ |
| 补刀/反补 | `last_hits` / `denies` | ✅ |
| 参战率 | `teamfight_participation` | ✅ 现成字段，0.4% 空 |
| 视野 | `obs_placed` / `sen_placed` | ✅ |
| 英雄池 | `player_matches.hero_id` | ✅ 3 个粒度全有 |
| **选手-队伍时点归属** | **派生名单法**（§10） | ✅ **已解决，无外部依赖** |
| 正式转会日期 | Liquipedia | ⚠️ 合规受限（§4.2），本轮未取 |

### 11.4 赛事结构 / TI15 专属

| 需要的字段 | 来源 | 状态 |
|---|---|---|
| TI15 赛制（瑞士轮+双败） | Liquipedia（缓存） | ✅ 已取（§4.3） |
| TI15 日期/地点/奖金 | Liquipedia（缓存） | ✅ 已取 |
| **TI15 16 强名单** | Liquipedia `Participants` 段 | ❌ **页面在建，空** |
| TI15 预选赛出线队 | OpenDota leagueid 19890-19894 | ✅ 已取 5 支（§4.4） |
| TI15 直邀队伍 | — | ❌ **未拿到**（需 Liquipedia 或官方公告） |
| 各届 TI 正赛场次口径 | OpenDota + §8.2 切分规则 | ✅ 841 场（TI10-TI14） |

### 11.5 总缺口清单

1. **赛事级别标注（tier-1/2/3）** —— OpenDota 的 `tier` 2024 年后失效。这是最重要的缺口，
   直接影响 Glicko 的样本加权。**需要外部赛事分级表。**
2. **TI15 完整 16 强名单** —— 只拿到 5 支预选赛出线队，11 支直邀队未确认。
3. **逐分钟曲线 / 事件流**（`radiant_gold_adv` / `objectives` / `teamfights` / `draft_timings`）
   —— 技术上可拉，需按场分片，本轮未做。
4. **选手展示名与国籍** —— 40.8% 的 account 不在 `notable_players` 里，不影响建模只影响出报告。
5. **正式转会/合同日期** —— Liquipedia 有，但合规受限。
