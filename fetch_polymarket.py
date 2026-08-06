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

    # requests 放到函数内懒加载，纯解析测试不需要装它。不做代理清理：
    # od_sql.py 清代理是因为本地代理会破坏 OpenDota 的 TLS；gamma-api.polymarket.com
    # 正相反——在需要代理出网的环境里，直连会被 SSL EOF 掐断（curl 用同样的
    # HTTP(S)_PROXY 能通，实测验证过），所以这里尊重用户 shell 里已有的
    # HTTP_PROXY/HTTPS_PROXY，让 requests 按其默认行为自动使用。
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
