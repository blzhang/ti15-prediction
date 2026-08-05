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
