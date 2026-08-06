# Polymarket 双源市场融合 · 设计文档

日期：2026-08-05 ｜ 状态：已与用户逐节确认

## 1. 背景与目标

当前夺冠概率的市场侧只有手工录入的庄家赔率（`model/market_odds.json`，
2026-08-01 抓取，仅 5 队有盘口），另外 11 队在融合时退回纯模型。
Polymarket 的 TI 2026 冠军盘（negRisk 事件，Gamma API 公开可读，无需鉴权）
16 队全有成交价，事件流动性约 89 万美元，且可脚本化自动刷新。

目标：**把 Polymarket 接入为第二个市场源，与庄家赔率等权合成「市场共识价」，
再与模型融合；市场覆盖从 5/16 提升到 16/16；站点全链路跟进。**

两源在共同覆盖的 5 队上分歧显著（条件概率口径：Team Spirit 庄家 23.7% vs
Polymarket 13.3%，Team Yandex 19.8% vs 31.5%），因此合成方式是实质决定，
不是形式。已确认采用 **log-odds 等权**——分歧大时等权是唯一不需要额外论证的立场。

### 明确不做（YAGNI）

- 不引入流动性/点差加权（bid-ask 点差信息仅存档，不参与计算）。
- 不动 `w_market=0.7`（文献建议 0.6–0.8 的既有论证不受影响）。
- 抄作业 16 格仍用纯模型的瑞士轮分布——Polymarket 也没开分档盘，
  README 对应限制条款保留。
- 不做定时自动抓取；抓取是手动一条命令，赛前可随时重跑。

## 2. 架构与数据流

```
fetch_polymarket.py（新，根目录，与 fetch_pro_all.py 并列）
    ↓ GET https://gamma-api.polymarket.com/events?slug=<冠军盘 slug>
    ↓ 原始返回归档 data/polymarket_raw_<UTC时间戳>.json（data/ 已 gitignore）
    → 解析 + 队名映射 → model/polymarket_odds.json（入库，含出处信息）

model/l2_blend.py（扩展，仍是一条命令）
    第一级  市场共识 = blend_partial(PM 16 队概率, 庄家 5 队赔率, w_market=0.5)
    第二级  最终概率 = blend_logodds(模型概率, 市场共识, w_market=0.7)
    → model/l2_blended.json

site/build_site.py → 全站数字自动重算
site/odds.py       → 市场页改两来源对照
model/freeze.py    → 重新存证
```

**两级融合不写任何新数学。** 第一级恰好是现有 `blend_partial` 的语义：
对有盘口的子集（庄家 5 队）做条件去水与 log-odds 融合、保持子集总质量不变。
把第一参数从「模型」换成「Polymarket 概率」即得到目标语义——庄家赔率只影响
它开过盘的 5 队内部的相对排序，5 队与其余 11 队之间的质量分配由全覆盖的
Polymarket 决定。第二级共识价已全覆盖，直接 `blend_logodds`。两个函数
均有既有测试（`tests/test_market.py`）。

## 3. 口径决定

| 决定 | 取值 | 依据 |
|---|---|---|
| 价格 | `outcomePrices` 的 Yes 价（= bid/ask 中点，已实测验证） | lastTrade 可能陈旧；点差过宽的尾部队用 mid 最中性 |
| 归一化 | 16 队 mid 按比例归一到和为 1 | 实测 mid 和 = 1.176，negRisk 市场同样有溢价 |
| 队名映射 | `{"1w Team": "Iron Wing"}`，其余 15 队精确匹配 | Liquipedia：Tundra 班底转入 1w Team，以 Iron Wing 名义参赛（lp_ti2026.txt 第 43 行及引注 110–111） |
| 占位市场 | "Will A/B/C/another team Win…" 靠映射后不在 16 队名单内自然排除 | 不维护占位黑名单，靠白名单闭合 |
| 源间权重 | 0.5 / 0.5（可用 `--w-book` 覆盖；`w_book` 指庄家一侧权重，0=纯 Polymarket，1=庄家完全决定 5 队内部排序） | 等权最不武断；庄家快照的陈旧性靠标注抓取时间暴露，不靠调权重掩盖 |
| 模型 vs 市场 | `w_market=0.7` 不变 | 00-DESIGN.md §4.2 |

## 4. 组件

### 4.1 `fetch_polymarket.py`（新）

CLI：`--slug`（默认冠军盘 slug）、`--out`（默认 `model/polymarket_odds.json`）。
HTTP 用 `requests`，沿用 `od_sql.py` 的惯例（含 import 前清理本地代理环境变量）。
`requirements.txt` 补列 `requests`（现有 `od_sql.py` 已在用但漏列，顺手修正）。

产出 schema：

```json
{
  "source": "Polymarket Gamma API",
  "event_slug": "the-international-2026-winner-20260629212545745",
  "captured_utc": "2026-08-05T09:00:00Z",
  "event_liquidity": 894751.55,
  "event_volume": 60854.65,
  "prices": {
    "TEAM VISION": {"mid": 0.235, "bid": 0.22, "ask": 0.25, "last": 0.23}
  },
  "name_map_applied": {"1w Team": "Iron Wing"},
  "excluded_markets": ["Will A Win The International 2026?"]
}
```

`prices` 共 16 队；参与计算的只有 `mid`，其余字段为出处存档。

### 4.2 `model/market.py`

只新增约 5 行的 `normalize(probs)`（比例归一化，空输入/非正值报错）。

### 4.3 `model/l2_blend.py`

- 新输入 `--pm`（默认 `model/polymarket_odds.json`）、新参数 `--w-book`（默认 0.5）。
- `build_blend` 扩展为两级：`consensus = blend_partial(normalize(pm_mids), book_odds, w_book)`；
  `blended = blend_logodds(model_p, consensus, w_market)`。
- 输出 `l2_blended.json` 顶层字段 `champion_blended`、`w_market` 保持不变（站点在读），
  追加 `market_consensus`（共识价本身）与 `sources` 元信息块（两源文件的
  captured_utc、覆盖队数、`w_book`）。

### 4.4 `site/odds.py`

市场页改两来源对照表：队 / 庄家小数赔率 / 庄家胜率（去水） / Polymarket 价 /
融合后模型概率，各来源标注抓取时间与出处。「只核实到 5 支队」的覆盖说明改写；
16 队全有行，不再有留空行。文案继续保持「不提供投注建议」声明。

### 4.5 文档与存证

- README：结果概览表重算；「三个可能有复用价值的点」不动；限制条款中
  「抄作业没融合赔率」保留原表述。
- 站内 changelog 加条目（说明接入了什么、数字为什么变了）。
- `model/freeze.py` 重新存证，`frozen/` 留新版本哈希。

## 5. 错误处理（宁可失败不可带病产出）

- 抓取：HTTP 非 200 / JSON 结构不符 → 非零退出，不写任何输出；
  原始归档文件仅在解析成功后保留。
- 映射硬闸：映射后队名集合必须**恰好等于** `l2_predictions.json` 的 16 队
  key 集合，多/少均打印差集并失败。
- 价格哨兵：每个 mid ∈ (0,1)；16 队 mid 之和 ∈ [0.8, 1.5]
  （2026-08-05 实测 1.176；越界说明抓到占位价或 API 语义变了）。
- 融合：沿用「概率和偏离 1 超容差即断言失败」；`--pm` 文件缺失直接报错
  （该文件入库，正常情况下永远存在）。

## 6. 测试

- `tests/test_fetch_polymarket.py`（新）：用裁剪自 `pm.json` 的 fixture，
  不打网。覆盖：映射生效（1w Team → Iron Wing）、占位市场排除、恰好 16 队、
  mid 抽取正确、两个哨兵触发时确实失败。
- `tests/test_market.py` 补：`normalize` 行为；共识价性质——等权对称性
  （仅在庄家覆盖的 5 队条件子问题上成立：两侧条件概率对换、结果不变）、
  `w_book=0/1` 退化为单源、11 支单源队的质量份额保持不变。
- `tests/test_l2_blend.py`：复现性钉子测试更新为新输入组合
  （重跑 == 磁盘上的新 `l2_blended.json`）。
- 站点：现有构建测试通过 + 市场页含两来源列的断言。

## 7. 验收标准

1. `python3 fetch_polymarket.py` 一条命令产出 `model/polymarket_odds.json`，
   失败时无副作用。
2. `python3 model/l2_blend.py` 一条命令完成两级融合，输出向后兼容。
3. 全部测试通过（现有 162 个 + 新增）。
4. `python3 site/build_site.py` 后市场页呈现两来源对照，全站数字与
   `l2_blended.json` 一致。
5. `frozen/` 有新版本存证；changelog 有对应条目。
