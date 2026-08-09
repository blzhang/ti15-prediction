"""构建 shadowjacob.shop/dota2 静态站点。

产出 site/dist/，包含 4 个页面 + 数据包。全部从冻结产出物生成，不手抄数字。

用法：
    python3 site/build_site.py            # 构建到 site/dist/
    python3 site/build_site.py --check    # 只校验数据源齐全，不写文件
"""
import argparse
import csv
import datetime
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(HERE, "dist")
BASE = "/dota2"

# 站点要打包的产出物：(源路径, 站内文件名, 人类可读说明, 是否进搜索索引)
ASSETS = [
    ("model/l2_blended.json", "l2_blended.json", "最终夺冠概率（已与市场共识融合：Polymarket ✕ 庄家赔率，市场占七成权重）"),
    ("model/polymarket_odds.json", "polymarket_odds.json", "Polymarket 冠军盘价格快照（16 队，含买卖价与成交价）"),
    ("model/l2_predictions.json", "l2_predictions.json", "模拟的全部结果：夺冠、进前四、晋级、各队小组赛战绩分布、最终名次分布"),
    ("model/l1_rating.json", "l1_rating.json", "16 支队的实力分与误差范围，以及模型在没见过的比赛上的实测成绩"),
    ("model/lineage.json", "lineage.json", "每支队的\"前世今生\"：用现役五人反查出来的历史队名与场次"),
    ("reports/ti15_matches.csv", "ti15_matches.csv", "任意两队交手的赛前胜率，共 120 组，赛后可拿来对账"),
    ("reports/p3_p4_players.json", "p3_p4_players.json", "80 名参赛选手在 15 项数据上的预测值与误差范围"),
    ("reports/p1_fantasy_matrix.json", "p1_fantasy_matrix.json", "梦幻挑战：各队三个位置的分项预期表现"),
    ("reports/p6_draw_sensitivity.json", "p6_draw_sensitivity.json", "分组敏感度实测：知道抽签结果能让预测准多少，含噪声对照组"),
    ("reports/p2_extremes.json", "p2_extremes.json", "谁会打出全场最高纪录，以及各种纪录出现的可能性"),
    ("reports/p5_window_backtest.json", "p5_window_backtest.json", "取数窗口回测：四届 TI 上七种取数起点的逐单元成绩与判定过程"),
]

FULL_DATA = [
    ("pro_matches_2020_2026.csv", "16 MB", "145,974 场比赛级结果"),
    ("pro_player_matches_2020_2026.csv", "182 MB", "1,459,742 条选手-比赛记录"),
    ("pro_picks_bans_2020_2026.csv", "139 MB", "3,436,132 条 BP 记录"),
    ("pro_blob_stats.csv", "1.3 MB", "smoke/tormentor/courier 三项（需解 JSON blob）"),
]

ITEM_LABEL = {
    "kills": "击杀", "deaths": "死亡", "creep_score": "正补+反补", "gpm": "每分钟经济",
    "tower_kills": "推塔", "roshan": "肉山", "teamfight": "参战率", "wards": "眼位",
    "camps_stacked": "堆野", "runes": "神符", "smokes": "烟雾", "tormentor": "百加",
    "first_blood": "一血", "stuns": "眩晕(秒)", "courier": "信使",
}


def patch_layer_facts(rating):
    """把 l1_rating.json 里的整格搜索结果压成方法论页要用的几个数。

    回答一件事：「按版本号打折」这一层到底有没有用。做法是拿同一格搜索里
    **启用版本层的最好一档**（全局最优）比**不启用的最好一档**（γ=1 的最优），
    两边都只看验证期——测试期不参与任何选择。

    curve_r / half_gap 是「这两档其实是同一条衰减曲线」的量化证据：把两条
    权重曲线在训练区间上采样，算相关系数，并各自求权重降到一半的时点。
    没有 hp_search（沿用旧缓存、这轮没重搜）时返回 None，页面整节不渲染。
    """
    log = rating.get("hp_search")
    mass = rating.get("patch_weight_mass")
    if not log or not mass:
        return None

    sys.path.insert(0, ROOT)
    import numpy as np
    from model.patch_weight import patch_weights, GAMMA_OFF

    best = min(log, key=lambda r: r["logloss"])
    off = min((r for r in log if r["patch_gamma"] == GAMMA_OFF),
              key=lambda r: r["logloss"])
    # LogLoss 的标准误按 s/sqrt(n) 估；s 取 0.5（logistic 逐样本损失的典型量级），
    # 这是个保守的数量级参照，不是精确值——页面上也是这么说的。
    se = 0.5 / math.sqrt(best["n"])
    delta = best["logloss"] - off["logloss"]

    # 两条权重曲线：在 L1 的训练区间上均匀采样比形状
    since = datetime.datetime(2022, 1, 1).timestamp()
    now = datetime.datetime(2026, 8, 2).timestamp()
    ts = np.linspace(since, now, 20000)
    day = 86400.0

    def curve(hl, gamma):
        w = 0.5 ** ((now - ts) / (hl * day)) * patch_weights(ts, now, gamma)
        return w

    c_sel = curve(best["half_life_days"], best["patch_gamma"])
    c_off = curve(off["half_life_days"], off["patch_gamma"])
    half_days = lambda c: float((now - ts[int(np.argmin(np.abs(c - 0.5)))]) / day)
    return {
        "val_n": best["n"],
        "n_grid": len(log),
        "delta": delta,
        "delta_abs": abs(delta),
        "se": se,
        "se_ratio": abs(se / delta) if delta else float("inf"),
        "hl_sel": best["half_life_days"], "g_sel": best["patch_gamma"],
        "hl_off": off["half_life_days"],
        "curve_r": float(np.corrcoef(c_sel / c_sel.sum(), c_off / c_off.sum())[0, 1]),
        "half_gap": abs(half_days(c_sel) - half_days(c_off)),
        "cur_share": mass["0"]["weight_share"] * 100,
        "mass": mass,
    }


def need(rel):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        raise SystemExit("缺少数据源：%s" % rel)
    return p


def load_all():
    blended = json.load(open(need("model/l2_blended.json")))["champion_blended"]
    pred = json.load(open(need("model/l2_predictions.json")))
    rating = json.load(open(need("model/l1_rating.json")))
    players = json.load(open(need("reports/p3_p4_players.json")))
    for rel, _, _ in ASSETS:
        need(rel)
    return blended, pred, rating, players


def build_search_index(players, rating):
    """压缩成客户端搜索用的扁平索引。"""
    rows = []
    for item, entries in players.get("rankings_by_item", {}).items():
        for e in entries:
            rows.append({
                "n": e["name"], "t": e["team"], "p": e["position"], "i": item,
                "r": round(e["rate"], 4), "lo": round(e["lo"], 4), "hi": round(e["hi"], 4),
                "g": e["n_games"], "rk": e.get("rank"),
            })
    return {"items": sorted({r["i"] for r in rows}),
            "item_label": ITEM_LABEL,
            "teams": sorted(rating["rating"]),
            "rows": rows}


def team_table(blended, pred, rating):
    out = []
    for t in sorted(blended, key=lambda x: -blended[x]):
        out.append({
            "team": t,
            "champ_blended": blended[t],
            "champ_model": pred["champion"][t],
            "top4": pred["top4"][t],
            "advance": pred["advance_playoffs"][t],
            "swiss_top3": pred["swiss_top3"][t],
            "r40": pred["record_4_0"][t],
            "r41": pred["record_4_1"][t],
            "elim_survive": pred["elim_round_survive"][t],
            "elim_out": pred["elim_round_out"][t],
            "theta": rating["rating"][t],
            "se": rating["rating_se"][t],
            "games": rating["games"][t],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    blended, pred, rating, players = load_all()
    if args.check:
        print("数据源齐全 ✓（%d 份产出物）" % len(ASSETS))
        return

    if os.path.isdir(DIST):
        shutil.rmtree(DIST)
    os.makedirs(os.path.join(DIST, "data"), exist_ok=True)
    os.makedirs(os.path.join(DIST, "assets"), exist_ok=True)

    # 1. 拷贝下载物
    manifest = []
    for rel, name, desc in ASSETS:
        src = os.path.join(ROOT, rel)
        shutil.copyfile(src, os.path.join(DIST, "data", name))
        manifest.append({"file": name, "desc": desc,
                         "bytes": os.path.getsize(src), "src": rel})

    # 2. 站点数据包
    payload = {
        "generated_utc": pred.get("generated_utc", ""),
        "n_sim": pred.get("n_sim"),
        "teams": team_table(blended, pred, rating),
        
        "oos": rating.get("oos_test", {}),
        "half_life_days": rating.get("half_life_days"),
        "patch_gamma": rating.get("patch_gamma"),
        "patch_layer": patch_layer_facts(rating),
        # 市场快照日期：长图/卡片上的「赛前已存证 · 日期」要跟这一版实际用的
        # 市场价同源，不能各写各的（make_cards.py 只读 site.json）
        "market_captured": json.load(open(need("model/polymarket_odds.json")))
                               .get("captured_utc", "")[:10],
        "ridge": rating.get("ridge"),
        "cross_region": rating.get("cross_region", {}),
        "homework": (lambda: (lambda hw: {
            "answer": {k: [[t, round(v, 6)] for t, v in vs] for k, vs in hw["answer"].items()},
            "expected": round(hw["expected_correct"], 4),
            "random": round(hw["random_baseline"], 4),
            "elim": {k: round(v, 4) for k, v in hw["elim"].items()},
        })(__import__("homework").compute(pred, rating["rating"])))(),
        "raw_pred": pred,
        "raw_fantasy": json.load(open(need("reports/p1_fantasy_matrix.json"))),
        "raw_market": json.load(open(need("model/market_odds.json"))),
        "raw_pm": json.load(open(need("model/polymarket_odds.json"))),
        "raw_window": json.load(open(need("reports/p5_window_backtest.json"))),
        # 分组敏感度实测（model/draw_sensitivity.py 产出）。抄作业页和更新日志页
        # 都要引用这几个数，走 payload 才能追溯到某一次真实运行，而不是手抄。
        "raw_draw_sens": json.load(open(need("reports/p6_draw_sensitivity.json"))),
        "manifest": manifest,
        "full_data": [{"file": f, "size": s, "desc": d} for f, s, d in FULL_DATA],
    }
    json.dump({k: v for k, v in payload.items() if k not in ("raw_pred", "raw_fantasy", "raw_market", "raw_pm", "raw_window", "raw_draw_sens")},
              open(os.path.join(DIST, "data", "site.json"), "w"),
              ensure_ascii=False, separators=(",", ":"))
    json.dump(build_search_index(players, rating),
              open(os.path.join(DIST, "data", "search_index.json"), "w"),
              ensure_ascii=False, separators=(",", ":"))

    # 3. 页面与静态资源由 pages.py 写出
    sys.path.insert(0, HERE)
    import pages
    pages.write_all(DIST, BASE, payload)

    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(DIST) for f in fs)
    print("构建完成：%s" % DIST)
    print("  文件数 %d，合计 %.1f MB" % (
        sum(len(fs) for _, _, fs in os.walk(DIST)), total / 1048576))


if __name__ == "__main__":
    main()
