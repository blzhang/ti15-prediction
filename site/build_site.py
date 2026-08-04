"""构建 shadowjacob.shop/dota2 静态站点。

产出 site/dist/，包含 4 个页面 + 数据包。全部从冻结产出物生成，不手抄数字。

用法：
    python3 site/build_site.py            # 构建到 site/dist/
    python3 site/build_site.py --check    # 只校验数据源齐全，不写文件
"""
import argparse
import csv
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(HERE, "dist")
BASE = "/dota2"

# 站点要打包的产出物：(源路径, 站内文件名, 人类可读说明, 是否进搜索索引)
ASSETS = [
    ("model/l2_blended.json", "l2_blended.json", "最终夺冠概率（已参考博彩赔率，市场占七成权重）"),
    ("model/l2_predictions.json", "l2_predictions.json", "模拟的全部结果：夺冠、进前四、晋级、各队小组赛战绩分布、最终名次分布"),
    ("model/l1_rating.json", "l1_rating.json", "16 支队的实力分与误差范围，以及模型在没见过的比赛上的实测成绩"),
    ("model/lineage.json", "lineage.json", "每支队的\"前世今生\"：用现役五人反查出来的历史队名与场次"),
    ("reports/ti15_matches.csv", "ti15_matches.csv", "任意两队交手的赛前胜率，共 120 组，赛后可拿来对账"),
    ("reports/p3_p4_players.json", "p3_p4_players.json", "80 名参赛选手在 15 项数据上的预测值与误差范围"),
    ("reports/p1_fantasy_matrix.json", "p1_fantasy_matrix.json", "梦幻挑战：各队三个位置的分项预期表现"),
    ("reports/p2_extremes.json", "p2_extremes.json", "谁会打出全场最高纪录，以及各种纪录出现的可能性"),
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
        "manifest": manifest,
        "full_data": [{"file": f, "size": s, "desc": d} for f, s, d in FULL_DATA],
    }
    json.dump({k: v for k, v in payload.items() if k not in ("raw_pred", "raw_fantasy", "raw_market")},
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
