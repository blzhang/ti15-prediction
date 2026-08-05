# Polymarket 双源市场融合 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入 Polymarket TI 2026 冠军盘为第二个市场源，与庄家赔率等权合成市场共识价再与模型融合，市场覆盖从 5/16 提升到 16/16，站点全链路跟进。

**Architecture:** 新增 `fetch_polymarket.py`（解析层纯函数可测，HTTP 懒加载）产出 `model/polymarket_odds.json`；`model/l2_blend.py` 改两级融合——第一级 `blend_partial(Polymarket 概率, 庄家赔率, w_book=0.5)` 得共识价，第二级 `blend_logodds(模型, 共识, w_market=0.7)`；站点市场页改两来源对照。融合数学零新增，全部复用 `model/market.py` 既有函数。

**Tech Stack:** Python 3 标准库 + `requests`（仅抓取脚本用，懒加载）；pytest。

**Spec:** `docs/superpowers/specs/2026-08-05-polymarket-integration-design.md`

## Global Constraints

- 概率输出 JSON 一律 float，保 6 位小数（用 `market.round_probs`，四舍五入后不再归一化，只校验 `|sum-1| < 1e-5`）。
- 测试一律不打网；fixture 从仓库里已提交的 `pm.json` 裁剪生成。
- 宁可失败不带病产出：抓取/解析任何一步失败即非零退出，不写任何输出文件。
- 权重常量单一定义：`w_market=0.7` 用 `market.W_MARKET_DEFAULT`，`w_book=0.5` 用 `market.W_BOOK_DEFAULT`，别处不得重复写字面量。
- 队名映射唯一条目 `{"1w Team": "Iron Wing"}`，依据 Liquipedia（`lp_ti2026.txt` 第 43 行及引注 110–111：Tundra 班底转入 1w Team，以 Iron Wing 名义参赛）。
- 测试命令一律在仓库根目录跑 `python3 -m pytest`（pytest.ini 已配 testpaths=tests）。
- 面向读者的站点文案用人话，保留「不提供任何投注建议」声明。

---

### Task 1: `market.py` 共识价基础 —— `normalize` + `W_BOOK_DEFAULT` + 共识性质测试

**Files:**
- Modify: `model/market.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Produces: `normalize(probs: dict[str, float]) -> dict[str, float]`（比例归一化，空/非正值抛 ValueError）；常量 `W_BOOK_DEFAULT = 0.5`。后续 Task 4 从 `market` 导入两者。
- Consumes: 既有 `devig` / `blend_partial`（仅测试引用，不改动）。

- [ ] **Step 1: 写失败测试**

在 `tests/test_market.py` 末尾追加：

```python
from model.market import normalize, W_BOOK_DEFAULT


def test_w_book_default_is_half():
    """源间权重 0.5 的单一定义（设计文档 2026-08-05 §3：等权最不武断）。"""
    assert W_BOOK_DEFAULT == 0.5


def test_normalize_scales_to_unit_sum_preserving_ratios():
    out = normalize({"A": 0.6, "B": 0.6})
    assert abs(sum(out.values()) - 1.0) < 1e-12
    assert out["A"] == pytest.approx(0.5)
    # 已归一的输入 → 原样
    out2 = normalize({"A": 0.5, "B": 0.25, "C": 0.25})
    assert out2 == pytest.approx({"A": 0.5, "B": 0.25, "C": 0.25})


def test_normalize_rejects_empty_and_non_positive():
    with pytest.raises(ValueError):
        normalize({})
    with pytest.raises(ValueError):
        normalize({"A": 0.5, "B": 0.0})
    with pytest.raises(ValueError):
        normalize({"A": 0.5, "B": -0.1})


def test_consensus_equal_weight_is_symmetric_on_priced_subset():
    """等权对称性（设计文档 §6）：在庄家覆盖的子集上把两侧条件概率对换，
    共识价不变。blend_partial(主向量, 赔率, 0.5) 内部是 log-odds 等权，
    等权融合对两个输入对称——这条测试把「0.5 的含义就是两源地位对等」钉死。"""
    pm = {"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1}
    odds = {"A": 2.0, "B": 3.0, "C": None, "D": None}
    fwd = blend_partial(pm, odds, w_market=0.5)

    # 反向：主向量位置放庄家条件概率（乘回质量 0.7），赔率位置放 pm 条件概率的倒数
    book_p = devig({"A": 2.0, "B": 3.0})
    swapped_main = {"A": book_p["A"] * 0.7, "B": book_p["B"] * 0.7, "C": 0.2, "D": 0.1}
    swapped_odds = {"A": 1 / (0.4 / 0.7), "B": 1 / (0.3 / 0.7), "C": None, "D": None}
    rev = blend_partial(swapped_main, swapped_odds, w_market=0.5)

    for t in "ABCD":
        assert rev[t] == pytest.approx(fwd[t]), t


def test_consensus_w_book_extremes_reduce_to_single_source():
    """w_book=0 → 纯 Polymarket；w_book=1 → 庄家完全决定其 5 队内部排序，
    但质量分配仍由 Polymarket 决定（设计文档 §2）。"""
    pm = {"A": 0.4, "B": 0.3, "C": 0.3}
    odds = {"A": 3.0, "B": 2.0, "C": None}
    out0 = blend_partial(pm, odds, w_market=0.0)
    for t in pm:
        assert out0[t] == pytest.approx(pm[t]), t
    out1 = blend_partial(pm, odds, w_market=1.0)
    book_p = devig({"A": 3.0, "B": 2.0})
    assert out1["A"] / out1["B"] == pytest.approx(book_p["A"] / book_p["B"])
    assert out1["C"] == pytest.approx(pm["C"])


def test_consensus_preserves_mass_share_of_pm_only_teams():
    """庄家没开盘的队，其共识概率精确等于 Polymarket 概率（质量份额保持）。"""
    pm = {"A": 0.4, "B": 0.3, "C": 0.2, "D": 0.1}
    odds = {"A": 1.5, "B": 6.0, "C": None, "D": None}
    out = blend_partial(pm, odds, w_market=0.5)
    assert out["C"] == pytest.approx(0.2)
    assert out["D"] == pytest.approx(0.1)
    assert out["A"] + out["B"] == pytest.approx(0.7)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_market.py -v -k "normalize or w_book or consensus"`
Expected: ImportError（`normalize`/`W_BOOK_DEFAULT` 不存在）

- [ ] **Step 3: 最小实现**

在 `model/market.py` 中，`W_MARKET_DEFAULT = 0.7 ...` 行之后加：

```python
W_BOOK_DEFAULT = 0.5     # 源间权重（庄家一侧）。2026-08-05 Polymarket 设计文档 §3：等权最不武断


def normalize(probs):
    """概率 dict 按比例归一化到和为 1。

    Polymarket 冠军盘 16 队 mid 价之和实测 ≈1.18——负风险市场同样有溢价，
    当概率用之前必须归一。空输入或任何非正值直接报错，不猜。
    """
    if not probs:
        raise ValueError("probs 不能为空")
    for k, v in probs.items():
        if v is None or v <= 0:
            raise ValueError("概率必须为正：%s=%r" % (k, v))
    s = sum(probs.values())
    return {k: v / s for k, v in probs.items()}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_market.py -v`
Expected: 全部 PASS（新增 6 条 + 既有全绿）

- [ ] **Step 5: Commit**

```bash
git add model/market.py tests/test_market.py
git commit -m "feat: market.py 加 normalize 与 W_BOOK_DEFAULT，钉死共识价三条性质"
```

---

### Task 2: `fetch_polymarket.py` 解析层（纯函数，不打网）+ fixture

**Files:**
- Create: `fetch_polymarket.py`（本任务只写解析层，`main()` 在 Task 3）
- Create: `tests/fixtures/polymarket_event.json`（从已提交的 `pm.json` 裁剪）
- Test: `tests/test_fetch_polymarket.py`

**Interfaces:**
- Produces:
  - `PM_NAME_MAP: dict[str, str]`（`{"1w Team": "Iron Wing"}`）
  - `parse_event(event: dict, teams: set[str]) -> tuple[dict, list[str]]`——返回 `(prices, excluded_questions)`；`prices[队名] = {"mid": float, "bid": float|None, "ask": float|None, "last": float|None}`；队伍缺失/重复抛 ValueError
  - `validate_prices(prices: dict, lo=0.8, hi=1.5) -> None`——mid ∉ (0,1) 或 mid 之和越界抛 ValueError
- Consumes: fixture 的结构 = Gamma API 事件 dict 的子集（`slug`/`liquidity`/`volume`/`markets[].{question, groupItemTitle, outcomePrices, bestBid, bestAsk, lastTradePrice}`）。

- [ ] **Step 1: 生成 fixture（从 pm.json 裁剪，20 个市场全保留——16 队 + 4 个占位）**

```bash
mkdir -p tests/fixtures && python3 - <<'EOF'
import json
ev = json.load(open("pm.json"))[0]
slim = {
    "slug": ev["slug"], "liquidity": ev["liquidity"], "volume": ev["volume"],
    "markets": [{k: m[k] for k in ("question", "groupItemTitle", "outcomePrices",
                                   "bestBid", "bestAsk", "lastTradePrice") if k in m}
                for m in ev["markets"]],
}
json.dump(slim, open("tests/fixtures/polymarket_event.json", "w"),
          ensure_ascii=False, indent=1)
print("markets:", len(slim["markets"]))
EOF
```

Expected 输出：`markets: 20`

- [ ] **Step 2: 写失败测试**

创建 `tests/test_fetch_polymarket.py`：

```python
"""fetch_polymarket.py 解析层测试。全部走 fixture，不打网。

fixture 是 pm.json（2026-08-01 的 Gamma API 快照，已入库）裁剪出的 20 个市场：
16 支真实队 + 4 个占位盘（A/B/C/another team）。
"""
import copy
import json
import os

import pytest

from fetch_polymarket import PM_NAME_MAP, parse_event, validate_prices


def _project_path(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, *parts)


@pytest.fixture
def event():
    with open(_project_path("tests", "fixtures", "polymarket_event.json")) as f:
        return json.load(f)


@pytest.fixture
def teams():
    with open(_project_path("model", "l2_predictions.json")) as f:
        return set(json.load(f)["champion"])


def test_name_map_is_exactly_the_iron_wing_entry():
    """唯一映射条目。依据 Liquipedia（lp_ti2026.txt:43 及引注 110-111）：
    Tundra 班底转入 1w Team，以 Iron Wing 名义参赛；Polymarket 用了组织名。"""
    assert PM_NAME_MAP == {"1w Team": "Iron Wing"}


def test_parse_maps_1w_team_to_iron_wing(event, teams):
    prices, _ = parse_event(event, teams)
    assert "Iron Wing" in prices
    assert "1w Team" not in prices
    # fixture 里 "Will 1w Team Win..." 的 Yes mid 是 0.065
    assert prices["Iron Wing"]["mid"] == pytest.approx(0.065)


def test_parse_excludes_placeholder_markets_and_covers_exactly_16(event, teams):
    prices, excluded = parse_event(event, teams)
    assert set(prices) == teams
    assert len(prices) == 16
    # 4 个占位盘（A/B/C/another team）靠「映射后不在 16 队名单内」自然排除
    assert len(excluded) == 4
    assert any("another team" in q for q in excluded)


def test_parse_extracts_mid_bid_ask_last(event, teams):
    prices, _ = parse_event(event, teams)
    aurora = prices["Aurora Gaming"]
    # fixture: outcomePrices '["0.065", "0.935"]'，bestBid 0.06，bestAsk 0.07，lastTrade 0.09
    assert aurora["mid"] == pytest.approx(0.065)
    assert aurora["bid"] == pytest.approx(0.06)
    assert aurora["ask"] == pytest.approx(0.07)
    assert aurora["last"] == pytest.approx(0.09)


def test_parse_fails_loudly_when_a_team_is_missing(event, teams):
    ev = copy.deepcopy(event)
    ev["markets"] = [m for m in ev["markets"]
                     if m["groupItemTitle"] != "Aurora Gaming"]
    with pytest.raises(ValueError, match="Aurora Gaming"):
        parse_event(ev, teams)


def test_parse_fails_loudly_on_duplicate_team(event, teams):
    ev = copy.deepcopy(event)
    dup = copy.deepcopy(ev["markets"][0])
    ev["markets"].append(dup)
    with pytest.raises(ValueError, match="重复"):
        parse_event(ev, teams)


def test_validate_rejects_mid_outside_unit_interval():
    bad = {"X": {"mid": 0.0, "bid": None, "ask": None, "last": None}}
    with pytest.raises(ValueError):
        validate_prices(bad)


def test_validate_rejects_sum_outside_sentinel_band():
    # 16 队 mid 全 0.03 → 和 0.48，低于哨兵下界 0.8（像是抓到了占位价）
    bad = {"T%d" % i: {"mid": 0.03, "bid": None, "ask": None, "last": None}
           for i in range(16)}
    with pytest.raises(ValueError):
        validate_prices(bad)


def test_validate_accepts_real_snapshot(event, teams):
    # 2026-08-01 快照的 16 队 mid 之和 ≈1.31，应落在 [0.8, 1.5] 哨兵区间内
    prices, _ = parse_event(event, teams)
    validate_prices(prices)
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python3 -m pytest tests/test_fetch_polymarket.py -v`
Expected: FAIL / ERROR（`fetch_polymarket` 模块不存在）

- [ ] **Step 4: 最小实现**

创建 `fetch_polymarket.py`（仓库根目录）：

```python
"""抓取 Polymarket 的 TI 2026 冠军盘 → model/polymarket_odds.json。

Gamma API 公开可读，无需鉴权：
    GET https://gamma-api.polymarket.com/events?slug=<冠军盘 slug>

设计文档 docs/superpowers/specs/2026-08-05-polymarket-integration-design.md：
  - 价格取 outcomePrices 的 Yes 价（= bid/ask 中点）；bid/ask/lastTrade 仅存档
  - 队名映射唯一条目 1w Team → Iron Wing（Liquipedia：Tundra 班底转入 1w Team，
    以 Iron Wing 名义参赛；lp_ti2026.txt:43 及引注 110-111）
  - 占位盘（"Will A/B/C/another team Win..."）靠映射后不在 16 队名单内自然排除
  - 宁可失败不带病产出：解析成功前不落任何文件

用法：
    python3 fetch_polymarket.py            # 抓默认冠军盘，写 model/polymarket_odds.json
    python3 fetch_polymarket.py --slug ... --out ...
"""
import argparse
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
GAMMA_API = "https://gamma-api.polymarket.com/events"
DEFAULT_SLUG = "the-international-2026-winner-20260629212545745"
DEFAULT_OUT = os.path.join(HERE, "model", "polymarket_odds.json")
DEFAULT_L2 = os.path.join(HERE, "model", "l2_predictions.json")
RAW_DIR = os.path.join(HERE, "data")

PM_NAME_MAP = {
    "1w Team": "Iron Wing",
}


def parse_event(event, teams):
    """Gamma API 事件 dict → (prices, excluded_questions)。

    prices[模型队名] = {"mid", "bid", "ask", "last"}；excluded 记录被排除的
    市场标题（占位盘等）。映射后集合必须恰好等于 teams，多/少/重复都报错。
    """
    prices, excluded = {}, []
    for m in event["markets"]:
        name = PM_NAME_MAP.get(m["groupItemTitle"], m["groupItemTitle"])
        if name not in teams:
            excluded.append(m["question"])
            continue
        if name in prices:
            raise ValueError("队伍在冠军盘里重复出现：%r" % name)
        prices[name] = {
            "mid": float(json.loads(m["outcomePrices"])[0]),
            "bid": m.get("bestBid"),
            "ask": m.get("bestAsk"),
            "last": m.get("lastTradePrice"),
        }
    missing = sorted(set(teams) - set(prices))
    if missing:
        raise ValueError(
            "这些队在 Polymarket 冠军盘里找不到（改名了？缺映射？）：%s" % missing)
    return prices, excluded


def validate_prices(prices, lo=0.8, hi=1.5):
    """价格哨兵：mid ∈ (0,1)；mid 之和 ∈ [lo, hi]（2026-08-05 实测 1.18）。"""
    for team, rec in prices.items():
        if not 0.0 < rec["mid"] < 1.0:
            raise ValueError("%s 的 mid=%r 不在 (0,1) 内" % (team, rec["mid"]))
    total = sum(rec["mid"] for rec in prices.values())
    if not lo <= total <= hi:
        raise ValueError(
            "mid 之和 %.4f 超出哨兵区间 [%s, %s]——像是抓到了占位价，"
            "或者 API 的价格语义变了" % (total, lo, hi))
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m pytest tests/test_fetch_polymarket.py -v`
Expected: 全部 PASS（9 条）

- [ ] **Step 6: Commit**

```bash
git add fetch_polymarket.py tests/fixtures/polymarket_event.json tests/test_fetch_polymarket.py
git commit -m "feat: Polymarket 冠军盘解析层——队名映射、占位盘排除、双哨兵，全走 fixture 不打网"
```

---

### Task 3: `fetch_polymarket.py` 组装层 + CLI + 真实抓取产出快照

**Files:**
- Modify: `fetch_polymarket.py`（追加 `build_output` 与 `main`）
- Modify: `requirements.txt`
- Create: `model/polymarket_odds.json`（真实抓取产出，入库）
- Test: `tests/test_fetch_polymarket.py`（追加 build_output 测试）

**Interfaces:**
- Consumes: Task 2 的 `parse_event` / `validate_prices` / `PM_NAME_MAP`。
- Produces: `build_output(event, prices, excluded, captured_utc) -> dict`（产出文件的完整 schema，见下）；`main(argv=None)`；磁盘上的 `model/polymarket_odds.json`——Task 4 融合、Task 5 站点都读它。

- [ ] **Step 1: 写失败测试**

在 `tests/test_fetch_polymarket.py` 末尾追加：

```python
from fetch_polymarket import build_output


def test_build_output_schema_and_provenance(event, teams):
    prices, excluded = parse_event(event, teams)
    out = build_output(event, prices, excluded, "2026-08-05T09:00:00Z")
    assert out["source"] == "Polymarket Gamma API"
    assert out["event_slug"] == event["slug"]
    assert out["captured_utc"] == "2026-08-05T09:00:00Z"
    assert out["event_liquidity"] == event["liquidity"]
    assert out["event_volume"] == event["volume"]
    assert set(out["prices"]) == teams
    assert out["name_map_applied"] == {"1w Team": "Iron Wing"}
    assert len(out["excluded_markets"]) == 4
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_fetch_polymarket.py -v -k build_output`
Expected: ImportError（`build_output` 不存在）

- [ ] **Step 3: 实现 `build_output` 与 `main`**

在 `fetch_polymarket.py` 末尾追加：

```python
def build_output(event, prices, excluded, captured_utc):
    """组装 model/polymarket_odds.json 的内容。参与计算的只有 prices[*]["mid"]，
    其余字段全部是出处存档。"""
    return {
        "source": "Polymarket Gamma API",
        "event_slug": event["slug"],
        "captured_utc": captured_utc,
        "event_liquidity": event.get("liquidity"),
        "event_volume": event.get("volume"),
        "prices": prices,
        "name_map_applied": dict(PM_NAME_MAP),
        "excluded_markets": excluded,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", default=DEFAULT_SLUG, help="Gamma API 事件 slug")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出路径")
    args = ap.parse_args(argv)

    # 清掉会破坏 TLS 的本地代理（od_sql.py 的既有惯例），然后才 import requests。
    # requests 放到函数内懒加载，纯解析测试不需要装它。
    for _v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
               "ALL_PROXY", "all_proxy", "REQUESTS_CA_BUNDLE"):
        os.environ.pop(_v, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    import requests

    resp = requests.get(GAMMA_API, params={"slug": args.slug}, timeout=30)
    resp.raise_for_status()
    events = resp.json()
    if not isinstance(events, list) or len(events) != 1:
        raise SystemExit("slug %r 应恰好命中 1 个事件，实际返回 %r 个"
                         % (args.slug, len(events) if isinstance(events, list) else type(events)))
    event = events[0]

    captured_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(DEFAULT_L2) as f:
        teams = set(json.load(f)["champion"])
    prices, excluded = parse_event(event, teams)
    validate_prices(prices)

    # 解析+哨兵全过之后才落盘（宁可失败不带病产出）
    os.makedirs(RAW_DIR, exist_ok=True)
    raw_path = os.path.join(
        RAW_DIR, "polymarket_raw_%s.json"
        % captured_utc.replace("-", "").replace(":", ""))
    with open(raw_path, "w") as f:
        json.dump(events, f, ensure_ascii=False)

    out = build_output(event, prices, excluded, captured_utc)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("Polymarket 冠军盘 %s" % event["slug"])
    print("抓取于 %s · 事件流动性 $%.0f · 累计成交 $%.0f"
          % (captured_utc, event.get("liquidity") or 0, event.get("volume") or 0))
    print("%-17s %8s %8s %8s" % ("队", "mid", "bid", "ask"))
    for team in sorted(prices, key=lambda t: -prices[t]["mid"]):
        rec = prices[team]
        print("%-17s %8.4f %8s %8s" % (team, rec["mid"], rec["bid"], rec["ask"]))
    print("\nmid 合计 %.4f（溢价在融合层做归一化）"
          % sum(rec["mid"] for rec in prices.values()))
    print("排除 %d 个占位盘：%s" % (len(excluded), "；".join(excluded)))
    print("→ 原始归档 %s（不入库）" % raw_path)
    print("→ 写入 %s" % args.out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_fetch_polymarket.py -v`
Expected: 全部 PASS（10 条）

- [ ] **Step 5: `requirements.txt` 补列 requests**

`requirements.txt` 末尾追加一行：

```
requests>=2.28   # 仅数据抓取脚本用（fetch_pro_all.py / fetch_polymarket.py）；只建站不需要
```

- [ ] **Step 6: 真实抓取一次，产出快照**

Run: `python3 fetch_polymarket.py`
Expected: 打印 16 队价格表 + `mid 合计 ≈1.1x` + `排除 4 个占位盘` + `→ 写入 .../model/polymarket_odds.json`

校验产出：

```bash
python3 -c "
import json
d = json.load(open('model/polymarket_odds.json'))
assert len(d['prices']) == 16 and 'Iron Wing' in d['prices']
print('OK:', d['captured_utc'], '| 流动性', d['event_liquidity'])"
```

Expected: `OK: 2026-08-05T...Z | 流动性 89xxxx...`

- [ ] **Step 7: Commit**

```bash
git add fetch_polymarket.py tests/test_fetch_polymarket.py requirements.txt model/polymarket_odds.json
git commit -m "feat: Polymarket 抓取 CLI 与首份入库快照（16 队全覆盖，含出处存档）"
```

---

### Task 4: `l2_blend.py` 两级融合 + 重新产出 `l2_blended.json`

**Files:**
- Modify: `model/l2_blend.py`
- Modify: `model/l2_blended.json`（重新产出）
- Test: `tests/test_l2_blend.py`

**Interfaces:**
- Consumes: `market.normalize` / `market.W_BOOK_DEFAULT`（Task 1）、`model/polymarket_odds.json`（Task 3）、既有 `blend_partial` / `blend_logodds` / `round_probs` / `W_MARKET_DEFAULT`。
- Produces: `build_blend(l2_path=..., odds_path=..., pm_path=..., w_book=W_BOOK_DEFAULT, w_market=W_MARKET_DEFAULT) -> dict`，返回 `{"champion_blended", "w_market", "market_consensus", "sources"}`；`DEFAULT_PM` 常量；CLI 新增 `--pm` / `--w-book`。站点只读 `champion_blended`（顶层字段名不变）。

- [ ] **Step 1: 改写测试（旧签名的 4 条测试同步更新）**

`tests/test_l2_blend.py` 整体替换为：

```python
"""对 model/l2_blend.py 的测试（两级融合版）。

第一级：市场共识 = blend_partial(Polymarket 16 队概率, 庄家 5 队赔率, w_book)
第二级：最终概率 = blend_logodds(模型, 共识, w_market)

复现性钉子测试的立场不变：以后任何人改了三个输入文件
（l2_predictions / market_odds / polymarket_odds）却忘了重跑
model/l2_blend.py，这条测试直接变红，不让产出物静默漂移。
"""
import json

import pytest

from model.l2_blend import build_blend, main, DEFAULT_OUT
from model.market import (
    blend_logodds, blend_partial, normalize, round_probs,
    W_BOOK_DEFAULT, W_MARKET_DEFAULT,
)


def test_build_blend_reproduces_committed_l2_blended_json():
    """核心不变量：用磁盘上的三个真实输入文件（默认参数）重新融合，
    结果必须与已冻结的 model/l2_blended.json 完全相等（含 market_consensus
    与 sources 元信息块）。"""
    result = build_blend()
    with open(DEFAULT_OUT) as f:
        on_disk = json.load(f)
    assert result == on_disk


def test_build_blend_defaults_come_from_markets_shared_constants():
    """0.7 与 0.5 都必须来自 market.py 的单一定义，本脚本不得另写字面量。"""
    assert W_MARKET_DEFAULT == 0.7
    assert W_BOOK_DEFAULT == 0.5
    result = build_blend()
    assert result["w_market"] == W_MARKET_DEFAULT
    assert result["sources"]["w_book"] == W_BOOK_DEFAULT


def test_build_blend_toy_example_is_a_thin_wrapper_not_a_reimplementation(tmp_path):
    """最小合成输入验证 build_blend 只是 market.py 公开函数的两级薄封装：
    期望值手动调 normalize → blend_partial → blend_logodds → round_probs 算出，
    不是硬编码数字。"""
    l2_path = tmp_path / "toy_l2.json"
    odds_path = tmp_path / "toy_odds.json"
    pm_path = tmp_path / "toy_pm.json"
    model = {"A": 0.5, "B": 0.3, "C": 0.2}
    odds = {"A": 2.0, "B": None, "C": 5.0}
    pm_mids = {"A": 0.5, "B": 0.4, "C": 0.3}
    l2_path.write_text(json.dumps({"champion": model}))
    odds_path.write_text(json.dumps(
        {"decimal_odds": odds, "captured_utc": "2026-08-01"}))
    pm_path.write_text(json.dumps(
        {"prices": {t: {"mid": v, "bid": None, "ask": None, "last": None}
                    for t, v in pm_mids.items()},
         "captured_utc": "2026-08-05T00:00:00Z", "event_slug": "toy"}))

    result = build_blend(l2_path=str(l2_path), odds_path=str(odds_path),
                         pm_path=str(pm_path), w_book=0.5, w_market=0.5)

    consensus = blend_partial(normalize(pm_mids), odds, w_market=0.5)
    expected = round_probs(blend_logodds(model, consensus, 0.5), 6)
    assert result["champion_blended"] == expected
    assert result["market_consensus"] == round_probs(consensus, 6)
    # B 庄家无盘口 → 共识里 B 精确等于归一化后的 Polymarket 概率（质量份额保持）
    assert result["market_consensus"]["B"] == round(normalize(pm_mids)["B"], 6)


def test_build_blend_rejects_pm_team_set_mismatch(tmp_path):
    """Polymarket 与模型的队伍集合不一致必须报错，不能静默丢队。"""
    l2_path = tmp_path / "toy_l2.json"
    odds_path = tmp_path / "toy_odds.json"
    pm_path = tmp_path / "toy_pm.json"
    l2_path.write_text(json.dumps({"champion": {"A": 0.6, "B": 0.4}}))
    odds_path.write_text(json.dumps({"decimal_odds": {"A": 2.0, "B": None}}))
    pm_path.write_text(json.dumps(
        {"prices": {"A": {"mid": 0.5, "bid": None, "ask": None, "last": None}}}))
    with pytest.raises(ValueError, match="B"):
        build_blend(l2_path=str(l2_path), odds_path=str(odds_path),
                    pm_path=str(pm_path))


def test_main_cli_writes_file_matching_build_blend_return_value(tmp_path):
    """CLI 真实入口（真实数据，--out 指向临时文件）：写盘内容与 build_blend()
    返回值一致，16 队、和在容差内、元信息块齐全。"""
    out = str(tmp_path / "l2_blended.json")
    result = main(["--out", out])

    with open(out) as f:
        on_disk = json.load(f)
    assert on_disk == result
    assert on_disk["w_market"] == 0.7
    assert len(on_disk["champion_blended"]) == 16
    assert len(on_disk["market_consensus"]) == 16
    assert on_disk["sources"]["polymarket"]["teams_priced"] == 16
    assert on_disk["sources"]["book"]["teams_priced"] == 5
    assert abs(sum(on_disk["champion_blended"].values()) - 1.0) < 1e-5
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_l2_blend.py -v`
Expected: FAIL（`build_blend` 无 `pm_path` 参数 / 返回缺 `market_consensus`）

- [ ] **Step 3: 改写 `model/l2_blend.py`**

模块 docstring 里「本脚本把这条链路固化成一条命令」之后的段落追加一段（其余 docstring 保留）：

```
2026-08-05 起改为两级融合（docs/superpowers/specs/2026-08-05-polymarket-
integration-design.md）：第一级 blend_partial(Polymarket 16 队概率,
庄家 5 队赔率, w_book=0.5) 得市场共识价——庄家只影响它开过盘的 5 队内部
排序，5 队与其余 11 队的质量分配由全覆盖的 Polymarket 决定；第二级
blend_logodds(模型, 共识, w_market=0.7)。融合数学仍全部来自 market.py。
```

import 行与常量改为：

```python
from market import (
    blend_logodds, blend_partial, normalize, round_probs,
    W_BOOK_DEFAULT, W_MARKET_DEFAULT,
)

DEFAULT_L2 = os.path.join(HERE, "l2_predictions.json")
DEFAULT_ODDS = os.path.join(HERE, "market_odds.json")
DEFAULT_PM = os.path.join(HERE, "polymarket_odds.json")
DEFAULT_OUT = os.path.join(HERE, "l2_blended.json")
```

`build_blend` 整体替换为：

```python
def build_blend(l2_path=DEFAULT_L2, odds_path=DEFAULT_ODDS, pm_path=DEFAULT_PM,
                w_book=W_BOOK_DEFAULT, w_market=W_MARKET_DEFAULT):
    """两级融合，纯函数不写盘（写盘是 main() 的职责）。

    第一级：市场共识 = blend_partial(Polymarket 概率, 庄家赔率, w_book)
    第二级：最终概率 = blend_logodds(模型概率, 共识, w_market)

    返回 {"champion_blended", "w_market", "market_consensus", "sources"}；
    前两个字段与旧版结构一致（站点在读），后两个是本次新增的出处块。
    """
    model = json.load(open(l2_path))["champion"]
    book = json.load(open(odds_path))
    pm = json.load(open(pm_path))

    pm_probs = normalize({t: rec["mid"] for t, rec in pm["prices"].items()})
    if set(pm_probs) != set(model):
        raise ValueError(
            "Polymarket 与模型的队伍集合不一致，只在一侧出现：%s"
            % sorted(set(pm_probs) ^ set(model)))

    consensus = blend_partial(pm_probs, book["decimal_odds"], w_market=w_book)
    blended = blend_logodds(model, consensus, w_market)
    rounded = round_probs(blended, 6)

    # 口径不变：四舍五入后不重新归一化，只校验偏差在文档化容差内
    deviation = abs(sum(rounded.values()) - 1.0)
    assert deviation < 1e-5, (
        "四舍五入后概率和偏离 1 超出文档化容差：deviation=%r" % deviation)
    return {
        "champion_blended": rounded,
        "w_market": w_market,
        "market_consensus": round_probs(consensus, 6),
        "sources": {
            "book": {
                "file": os.path.basename(str(odds_path)),
                "captured_utc": book.get("captured_utc"),
                "teams_priced": sum(1 for v in book["decimal_odds"].values() if v),
            },
            "polymarket": {
                "file": os.path.basename(str(pm_path)),
                "captured_utc": pm.get("captured_utc"),
                "event_slug": pm.get("event_slug"),
                "teams_priced": len(pm_probs),
            },
            "w_book": w_book,
        },
    }
```

`main` 里参数与调用同步改（打印逻辑保留，首行改为报三个输入）：

```python
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--l2", default=DEFAULT_L2, help="model/l2_predictions.json 路径")
    ap.add_argument("--odds", default=DEFAULT_ODDS, help="model/market_odds.json 路径")
    ap.add_argument("--pm", default=DEFAULT_PM, help="model/polymarket_odds.json 路径")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出路径")
    ap.add_argument("--w-book", type=float, default=W_BOOK_DEFAULT,
                    help="共识价里庄家一侧的权重，默认 0.5（0=纯 Polymarket）")
    ap.add_argument("--w-market", type=float, default=W_MARKET_DEFAULT,
                    help="市场共识对模型的权重，默认 0.7")
    args = ap.parse_args(argv)

    result = build_blend(l2_path=args.l2, odds_path=args.odds, pm_path=args.pm,
                         w_book=args.w_book, w_market=args.w_market)
    champ = result["champion_blended"]

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)

    print("两级融合：w_book=%s，w_market=%s" % (args.w_book, args.w_market))
    print("输入：%s + %s + %s" % (args.l2, args.odds, args.pm))
    print("%-17s%12s%14s" % ("队", "市场共识", "融合后夺冠概率"))
    cons = result["market_consensus"]
    for team in sorted(champ, key=lambda t: -champ[t]):
        print("%-17s%11.1f%%%13.1f%%" % (team, cons[team] * 100, champ[team] * 100))
    total = sum(champ.values())
    print("\n合计：%.10f（偏差 |sum-1|=%.2e，应 < 1e-5）" % (total, abs(total - 1.0)))
    print("\n→ 写入 %s" % args.out)
    return result
```

- [ ] **Step 4: 重新产出 `l2_blended.json`**

Run: `python3 model/l2_blend.py`
Expected: 打印 16 队「市场共识 / 融合后」两列表格 + `→ 写入 .../model/l2_blended.json`

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m pytest tests/test_l2_blend.py tests/test_market.py -v`
Expected: 全部 PASS（test_market.py 里两条读 `l2_blended.json` 的回归测试也要绿——6 位小数与和容差的口径没变）

- [ ] **Step 6: Commit**

```bash
git add model/l2_blend.py model/l2_blended.json tests/test_l2_blend.py
git commit -m "feat: 两级融合——Polymarket×庄家等权共识价再与模型融合，市场覆盖 5/16 → 16/16"
```

---

### Task 5: 站点 —— 市场页两来源对照 + 数据打包

**Files:**
- Modify: `site/odds.py`（`render` 加 `pm` 参数，表格改两来源）
- Modify: `site/pages.py:470-473`（`odds.html` 的 render 调用传入 `payload["raw_pm"]`）
- Modify: `site/build_site.py`（ASSETS 加一条、payload 加 `raw_pm`、site.json 排除表加 `"raw_pm"`）
- Test: `tests/test_site_odds.py`（新）

**Interfaces:**
- Consumes: `model/polymarket_odds.json`（Task 3 schema：`prices[队]{mid,...}`、`captured_utc`、`event_liquidity`）。
- Produces: `odds.render(base, pred, blended, market, pm) -> str`（新签名，5 参数）。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_site_odds.py`：

```python
"""site/odds.py 市场页渲染测试：两来源对照、留空规则、按融合概率排序。"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site"))
import odds  # noqa: E402


def _render(blended, decimal_odds, pm_mids):
    market = {"decimal_odds": decimal_odds, "captured_utc": "2026-08-01"}
    pm = {"prices": {t: {"mid": v, "bid": None, "ask": None, "last": None}
                     for t, v in pm_mids.items()},
          "captured_utc": "2026-08-05T09:00:00Z",
          "event_liquidity": 890000.0}
    return odds.render("/dota2", {}, blended, market, pm)


def test_render_shows_both_sources_and_dashes_for_unpriced_bookmaker():
    html = _render({"A": 0.5, "B": 0.3, "C": 0.2},
                   {"A": 2.0, "B": None, "C": None},
                   {"A": 0.6, "B": 0.3, "C": 0.3})
    assert "Polymarket" in html
    assert "2.00" in html                    # A 的庄家小数赔率
    assert "—" in html                       # B/C 的庄家两列留空
    assert "25.0%" in html                   # B 的 Polymarket 胜率 = 0.3/1.2
    assert "2026-08-01" in html              # 庄家抓取时间
    assert "2026-08-05T09:00:00Z" in html    # Polymarket 抓取时间
    assert "不提供任何投注建议" in html


def test_render_orders_rows_by_blended_probability_desc():
    html = _render({"A": 0.2, "B": 0.5, "C": 0.3},
                   {"A": None, "B": None, "C": None},
                   {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})
    assert html.index(">B<") < html.index(">C<") < html.index(">A<")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_site_odds.py -v`
Expected: FAIL（`render()` 只收 4 个参数）

- [ ] **Step 3: 改写 `site/odds.py`**

整个文件替换为：

```python
"""生成「市场怎么看」页：庄家赔率 ✕ Polymarket ✕ 模型，三方对照。

庄家赔率来自 model/market_odds.json（人工核实录入）；Polymarket 价来自
model/polymarket_odds.json（fetch_polymarket.py 抓取）。都带抓取时间。
庄家查不到的队留空——不编造。
"""
import json
import os


def _devig(odds):
    """去掉抽水：把小数赔率换成和为 1 的概率。"""
    raw = {k: 1.0 / v for k, v in odds.items() if v}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}, s


def render(base, pred, blended, market, pm):
    import html as _h

    def esc(s):
        return _h.escape(str(s), quote=True)

    od = market["decimal_odds"]
    priced = {k: v for k, v in od.items() if v}
    imp, overround = _devig(priced)
    mass = sum(blended[t] for t in priced)

    mids = {t: rec["mid"] for t, rec in pm["prices"].items()}
    pm_sum = sum(mids.values())
    pm_p = {t: v / pm_sum for t, v in mids.items()}

    def book_cells(t):
        if od.get(t):
            return ("<td class=num>%.2f</td><td class=num>%.1f%%</td>"
                    % (od[t], imp[t] * mass * 100))
        return "<td class=num>—</td><td class=num>—</td>"

    rows = "".join(
        "<tr><td>%s</td>%s<td class=num>%.1f%%</td><td class='num hi'>%.1f%%</td></tr>"
        % (esc(t), book_cells(t), pm_p[t] * 100, blended[t] * 100)
        for t in sorted(blended, key=lambda x: -blended[x]))

    return """
<h1>市场怎么看</h1>
<p class="lede">两个公开市场对 TI15 各队夺冠的定价——传统博彩网站的赔率，和
Polymarket 预测市场的合约价——换算成胜率之后，与我们模型的结果放在一起对比。</p>
<p class="meta">庄家赔率抓取于 %s · Polymarket 抓取于 %s · 仅供参考，本站不提供任何投注建议</p>

<div class="note"><b>覆盖范围。</b>
庄家的夺冠盘只核实到 <b>%d 支队</b>，查不到的留空——不做估算、不编数字。<br>
Polymarket 的冠军盘 <b>16 支队全有价</b>（盘内资金约 <b>%.0f 万美元</b>），
这也是把它接进来的主要原因。</div>

<h2>怎么读这两种价</h2>
<p>博彩网站给的是「小数赔率」，比如 <b>4.50</b> 意思是押 1 块钱赢了拿回 4.5 块。
把它倒过来（1 ÷ 4.50 = 22.2%%）就是市场认为的大致胜率。</p>
<div class="note"><b>但直接倒过来算是不准的，因为里面含着庄家的抽水。</b><br>
把所有队的倒数加起来，公平市场应该正好等于 1，实际这次是 <b>%.2f</b>——
多出来的就是庄家留给自己的利润空间。下表「庄家胜率」一列已经把抽水去掉。<br>
夺冠这种多路盘的抽水通常比单场比赛高得多，<b>不去抽水直接看，会觉得每支队都被高估了。</b></div>
<p>Polymarket 上买的是「某队夺冠」的合约：比如某队的合约卖 0.24 美元，
真夺冠了每份兑 1 美元——所以<b>价格本身就是市场估的概率</b>。
不过 16 份合约的价格加起来是 <b>%.2f</b>，同样带着溢价，
下表「Polymarket 胜率」也是按比例归一之后的数字。</p>

<h2>市场 vs 模型</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>队伍</th><th>庄家赔率</th><th>庄家胜率</th><th>Polymarket 胜率</th><th>本站预测</th></tr></thead>
<tbody>%s</tbody></table></div>
<p class="hint">「本站预测」已经融合了市场信息：两个市场源先<b>等权</b>合成一个「市场共识价」
（庄家只开了 5 支队的盘，所以它只影响这 5 队内部的排序），
共识价再占<b>七成</b>权重与纯模型融合。所以最后一列和前面两列不会差太多——
这是有意的，不是巧合。</p>

<h2>一个反直觉的历史事实</h2>
<p>很多人觉得「跟着赔率买最稳」或者反过来「赔率总是错的」。两种说法都不太对。</p>
<p>我们查了 TI9 到 TI14 六届：<b>赛前赔率排第一的队，只夺冠过 1 次</b>；
冠军在赛前赔率里的排名，中位数是<b>第 4.5 名</b>。</p>
<div class="note"><b>但这不能说明赔率算错了。</b><br>
16 支队的比赛里，最被看好的那支大概也就两成半的夺冠机会。
那么六届里只赢一届，本来就是最正常不过的结果——概率上比抛硬币还平常。<br>
换句话说：<b>赔率其实挺准的，只是 TI 本来就没有稳的。</b>指望靠「反着买冷门」赚钱，
历史数据不支持这个想法。</div>

<h2>为什么我们的预测要参考市场</h2>
<p>做这套模型时查过学术文献，结论挺一致的：<b>想靠统计模型系统性打赢博彩公司，非常难。</b>
包含大量变量的模型在对比开盘者时并没有占到便宜，少数成功案例也都是很窄的口径，
而且有作者提到账号很快就被限制了。</p>
<p>所以我们的做法不是「跟市场对着干」，而是<b>把市场当成一个很强的参考</b>，
只在有明确理由的地方才偏离它——比如某支队换了人、而市场好像还没反应过来。</p>

<div class="note good"><b>想自己核对？</b>庄家赔率可以去公开博彩网站查证，
Polymarket 的价格在它官网的冠军盘页面就能看到，本站的快照文件也在
「数据与检索」页提供下载。价格是会变的，我们标了抓取时间；
到了开赛前如果有明显变化，我会更新这一页。</div>
""" % (esc(market.get("captured_utc", "—")), esc(pm.get("captured_utc", "—")),
       len(priced), (pm.get("event_liquidity") or 0) / 1e4,
       overround, pm_sum, rows)
```

- [ ] **Step 4: 接线 `site/pages.py` 与 `site/build_site.py`**

`site/pages.py` 的 odds.html 条目改为（多传一个参数）：

```python
        "odds.html": shell(base, "odds.html", "市场怎么看",
                           _odds.render(base, payload["raw_pred"],
                                        {r["team"]: r["champ_blended"] for r in payload["teams"]},
                                        payload["raw_market"], payload["raw_pm"])),
```

`site/build_site.py` 三处：

ASSETS 列表 `("model/l2_blended.json", ...)` 那行之后加：

```python
    ("model/polymarket_odds.json", "polymarket_odds.json", "Polymarket 冠军盘价格快照（16 队，含买卖价与成交价）"),
```

payload 里 `"raw_market": ...` 行之后加：

```python
        "raw_pm": json.load(open(need("model/polymarket_odds.json"))),
```

site.json 的排除元组 `("raw_pred", "raw_fantasy", "raw_market")` 改为：

```python
    json.dump({k: v for k, v in payload.items() if k not in ("raw_pred", "raw_fantasy", "raw_market", "raw_pm")},
```

- [ ] **Step 5: 跑测试 + 真实构建**

Run: `python3 -m pytest tests/test_site_odds.py -v`
Expected: 2 条 PASS

Run: `python3 site/build_site.py`
Expected: `构建完成：.../site/dist`，无异常

抽查产物：

```bash
grep -c "Polymarket 胜率" site/dist/odds.html && grep -c "<tr><td>" site/dist/odds.html
```

Expected: 第一个 ≥1；第二个 ≥16（16 队全有行）

- [ ] **Step 6: Commit**

```bash
git add site/odds.py site/pages.py site/build_site.py tests/test_site_odds.py
git commit -m "feat: 市场页改两来源对照（庄家×Polymarket×模型），快照进数据下载页"
```

---

### Task 6: 文档、更新日志、存证、全量验证

**Files:**
- Modify: `site/changelog.py`（entries 列表最上方加一条）
- Modify: `README.md`（结果概览、复现命令、市场描述）
- Create: `frozen/frozen_v7-blended-polymarket.json` 等 4 个存证文件
- Test: 全量 `python3 -m pytest`

**Interfaces:**
- Consumes: Task 4 的 `model/l2_blended.json`（README 表格数字来源）、Task 3 的 `model/polymarket_odds.json`、`payload["raw_pm"]["event_liquidity"]`（changelog 动态数字）。

- [ ] **Step 1: changelog 加条目**

`site/changelog.py` 的 `entries = [` 之后、第一个 `_entry("2026-08-04", ...)` 之前插入：

```python
        _entry("2026-08-05", "接入 Polymarket：市场侧从 5 队单源变成 16 队双源", [
            ("改了什么",
             "夺冠概率的市场参考原来只有 5 支队的庄家赔率，另外 11 支完全没有市场信息。"
             "现在接入了 Polymarket 的 TI 冠军盘（16 支队全有成交价），"
             "与庄家赔率<b>等权</b>合成「市场共识价」后再与模型融合，市场仍占七成权重。"),
            ("为什么",
             "Polymarket 是真金白银的预测市场，这个盘的资金深度足够"
             "（约 <b>%.0f 万美元</b>流动性），且 16 队全覆盖——庄家只开了 5 队的盘。"
             % (payload["raw_pm"]["event_liquidity"] / 1e4)),
            ("影响到什么",
             "全部 16 队的夺冠概率都重算了；「市场怎么看」页现在是两个来源并排对照，"
             "各自标了抓取时间。<b>抄作业 16 格不受影响</b>——"
             "分档没有盘口可参照，仍是纯模型。"),
            ("怎么核对",
             "Polymarket 快照原文件在「数据与检索」页可下载；两支队名对不上的问题"
             "（Polymarket 叫 1w Team、本站叫 Iron Wing）在快照文件的 name_map_applied "
             "字段里有记录，依据是 Liquipedia 的转会公告。"),
        ]),
```

- [ ] **Step 2: README 更新（三处）**

第一处，结果概览引言行：

```markdown
夺冠概率（已与博彩赔率融合，市场权重 0.7）：
```

改为：

```markdown
夺冠概率（已与市场融合：Polymarket ✕ 庄家赔率等权合成共识价，市场权重 0.7）：
```

第二处，用新数字重写概览表。先跑：

```bash
python3 -c "
import json
champ = json.load(open('model/l2_blended.json'))['champion_blended']
for t in sorted(champ, key=lambda x: -champ[x])[:6]:
    print('| %s | %.1f%% |' % (t, champ[t] * 100))"
```

把输出的 6 行替换 README 里概览表的 6 个数据行（表头 `| 队 | 夺冠 |` 不动），并核对表格下方「头名只有 18.2%」那段的数字与新头名概率一致（不一致就改成新值）。

第三处，「从零重跑整条链路」代码块中 `python3 -m model.l2_simulate` 与 `python3 -m model.l2_blend` 之间插一行，并更新 l2_blend 的注释：

```bash
python3 fetch_polymarket.py           # 抓 Polymarket 冠军盘   → model/polymarket_odds.json
python3 -m model.l2_blend             # 两级融合：Polymarket×庄家共识 + 模型 → model/l2_blended.json
```

- [ ] **Step 3: 重建站点（changelog/README 改动生效）**

Run: `python3 site/build_site.py`
Expected: `构建完成`，且 `grep -c "Polymarket" site/dist/changelog.html` ≥1

- [ ] **Step 4: 存证**

```bash
python3 -c "
from model.freeze import freeze_predictions
freeze_predictions('model/l2_blended.json', 'frozen', 'v7-blended-polymarket')
freeze_predictions('model/polymarket_odds.json', 'frozen', 'v7-polymarket-odds')
print('frozen v7 OK')"
```

Expected: `frozen v7 OK`，`frozen/` 下新增 4 个文件（frozen_/freeze_ × 两个 label）

- [ ] **Step 5: 全量测试**

Run: `python3 -m pytest`
Expected: 全部通过（162 + 新增 ≈ 180 条，0 failed）

- [ ] **Step 6: Commit**

```bash
git add site/changelog.py README.md frozen/
git commit -m "docs: 更新日志与 README 跟进 Polymarket 双源融合；冻结 v7 存证"
```

---

## 收尾（不在本计划内、由用户决定）

- 线上部署：`site/deploy.sh` 是发布到 shadowjacob.shop 的动作，属对外发布，由用户手动执行。
- 赛前刷新：开赛前重跑 `python3 fetch_polymarket.py && python3 model/l2_blend.py && python3 site/build_site.py`，并用新 label（如 v8）重新存证即可，无需改代码。
