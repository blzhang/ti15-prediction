"""抓取 Polymarket 的 TI15 淘汰赛**单场盘** → model/polymarket_matches.json。

与 fetch_polymarket.py 的关系
-----------------------------
fetch_polymarket.py 抓的是**冠军盘**（16 队谁夺冠）。这个脚本抓的是**单场盘**
（某一场 BO3 谁赢）。两者是不同的市场、不同的交易者、不同的流动性，
**而且实测会互相矛盾**——这正是要分开抓、分开存的理由。

为什么这份数据重要：冠军盘只能告诉你「谁最后举盾」，要从它推出「这一场谁赢」，
必须反解一组隐含实力再让赛制展开（见 model/l6_playoffs.py）。而反解会把市场
「因为赛制之外的理由给某队定价」的那部分强行翻译成实力。单场盘是**直接价格**，
不需要翻译。2026-08-17 实测：从冠军盘反解出的 VISION vs BoomBoys 是 65.4%，
而单场盘直接报 **80.5%**；Nigma vs Falcons 反解 41.1%，单场盘 **34.5%**。
两个方向都错，且都不小——所以单场盘必须单独接进来。

代理方向：与 fetch_polymarket.py 一致，**尊重用户 shell 里的 HTTP(S)_PROXY**
（gamma-api 直连会被 SSL EOF 掐断，见那个脚本的说明）。不要照搬 od_sql.py
的清代理块。

用法：
    python3 fetch_polymarket_matches.py
    python3 fetch_polymarket_matches.py --out model/polymarket_matches.json
"""
import argparse
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
GAMMA_API = "https://gamma-api.polymarket.com/events"
DEFAULT_OUT = os.path.join(HERE, "model", "polymarket_matches.json")
RAW_DIR = os.path.join(HERE, "data")

# 八强四场的事件 slug（Polymarket 自己的命名，用 public-search 找出来的）。
# 顺序与 model/results.json 的 playoffs.ubqf 一致（Liquipedia R1M1–R1M4 槽位序）。
# ⚠️ slug 里的日期是 Polymarket 按 UTC 起的名，与 CST 赛程差一天属正常
# （Iron Wing 那场 slug 写 08-19，实际是 8/20 10:00 CST）。
MATCH_SLUGS = [
    ("UBQF1", "dota2-ironwi-ts8-2026-08-19", "Iron Wing", "Team Spirit"),
    ("UBQF2", "dota2-vsn2-boombo-2026-08-20", "TEAM VISION", "BoomBoys"),
    ("UBQF3", "dota2-liquid-ty-2026-08-20", "Team Liquid", "Team Yandex"),
    ("UBQF4", "dota2-ngx-flc-2026-08-20", "Nigma Galaxy", "Team Falcons"),
]

# 队名映射：Polymarket 单场盘用的名字与 l1_rating.json 的正式名对齐。
# 目前实测完全一致（冠军盘那边要映射 "1w Team"→"Iron Wing"，单场盘直接写
# "Iron Wing"），留这个表是为了后面几轮出现别名时有地方改。
PM_NAME_MAP = {"1w Team": "Iron Wing"}


def pick_series_market(event):
    """从一个事件的十几个盘里挑出「整场 BO3 谁赢」那一个。

    一个事件里混着：整场 BO3、逐小局（Game 1/2/3 Winner）、让分、大小分、
    以及一堆「本局有没有人 Rampage」的花活。我们要的是**整场**——它的 question
    与事件标题同名，且是唯一一个 outcomes 为两支队名、question 里不含
    "Game N" / "Handicap" / "Total" 的盘。

    挑错盘不会报错，只会安静地把「第一小局胜率」当成「整场胜率」用，
    而这两个数差得不小（BO3 会放大强队优势）。所以这里逐条排除、并在最后
    断言恰好命中一个。
    """
    cands = []
    for m in event["markets"]:
        q = m.get("question") or ""
        if "Game " in q or "Handicap" in q or "Total" in q:
            continue
        outs = json.loads(m.get("outcomes") or "[]")
        if len(outs) != 2:
            continue
        cands.append(m)
    if len(cands) != 1:
        raise ValueError(
            "事件 %r 里能当「整场 BO3」的盘有 %d 个（应恰好 1 个）：%s"
            % (event.get("slug"), len(cands), [c.get("question") for c in cands]))
    return cands[0]


def parse_event(event, stage, a, b):
    """事件 dict → 一条单场盘记录。队名与预期不符直接报错，不猜。"""
    m = pick_series_market(event)
    outs = [PM_NAME_MAP.get(o, o) for o in json.loads(m["outcomes"])]
    prices = [float(x) for x in json.loads(m["outcomePrices"])]
    if set(outs) != {a, b}:
        raise ValueError(
            "%s 的盘口队名是 %s，与预期的 %s 对不上——slug 抄错了或对阵变了"
            % (stage, outs, [a, b]))
    p = dict(zip(outs, prices))
    total = p[a] + p[b]
    if not 0.97 <= total <= 1.03:
        raise ValueError(
            "%s 两侧中间价之和 %.4f 偏离 1 太多——二元盘不该有这么大溢价，"
            "多半是抓到了未开盘的占位价" % (stage, total))
    for t in (a, b):
        if not 0.0 < p[t] < 1.0:
            raise ValueError("%s 的 %s 中间价 %r 不在 (0,1) 内" % (stage, t, p[t]))
    return {
        "stage": stage, "a": a, "b": b,
        "slug": event["slug"],
        "question": m["question"],
        # 参与计算的只有 p_a（归一化后 a 队赢整场 BO3 的概率）
        "p_a": p[a] / total,
        "mid": {a: p[a], b: p[b]},
        "best_bid": m.get("bestBid"), "best_ask": m.get("bestAsk"),
        "last": m.get("lastTradePrice"),
        "volume": float(m.get("volumeNum") or 0),
        "event_liquidity": float(event.get("liquidity") or 0),
        "event_volume": float(event.get("volume") or 0),
        "end_date": event.get("endDate"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--min-volume", type=float, default=1000.0,
                    help="单场盘成交额低于此值时警告（不阻断，只提示信息量有限）")
    args = ap.parse_args(argv)

    import requests   # 懒加载，纯解析测试不需要装它

    captured = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw, out = [], []
    for stage, slug, a, b in MATCH_SLUGS:
        resp = requests.get(GAMMA_API, params={"slug": slug}, timeout=30)
        resp.raise_for_status()
        events = resp.json()
        if not isinstance(events, list) or len(events) != 1:
            raise SystemExit("slug %r 应恰好命中 1 个事件，实际 %r"
                             % (slug, len(events) if isinstance(events, list) else type(events)))
        raw.append(events[0])
        out.append(parse_event(events[0], stage, a, b))

    # 全部解析成功才落盘（宁可失败不带病产出，与 fetch_polymarket.py 同一条纪律）
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(os.path.join(RAW_DIR, "polymarket_matches_raw_%s.json"
                           % captured.replace("-", "").replace(":", "")), "w") as f:
        json.dump(raw, f, ensure_ascii=False)

    doc = {
        "source": "Polymarket Gamma API（单场盘，与冠军盘是两个独立市场）",
        "captured_utc": captured,
        "matches": out,
        "name_map_applied": dict(PM_NAME_MAP),
    }
    with open(args.out, "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    print("Polymarket 八强单场盘 · 抓取于 %s" % captured)
    print("%-7s %-34s %8s %8s %10s" % ("场次", "对阵", "先手胜率", "买/卖", "成交额"))
    for r in out:
        print("%-7s %-34s %7.1f%% %4s/%-4s %10s"
              % (r["stage"], "%s vs %s" % (r["a"], r["b"]), r["p_a"] * 100,
                 r["best_bid"], r["best_ask"], "{:,.0f}".format(r["volume"])))
        if r["volume"] < args.min_volume:
            print("        ⚠️ 成交额不足 %.0f，这条价格的信息量有限" % args.min_volume)
    print("→ 写入 %s" % args.out)


if __name__ == "__main__":
    main()
