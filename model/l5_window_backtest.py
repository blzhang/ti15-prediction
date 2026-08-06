"""L5 窗口回测：选手数据窗口该不该切到当届版本发布日起。

spec：docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md

结构与本仓既有的 l4_* 一致：纯函数在 model/l5_window.py，本模块负责
读真实 CSV、跑四届 holdout、出报告。预测速率直接复用
model.l3_player.fit_rate_model，一行不改——每个臂只是喂不同的时间切片。

**本模块不修改任何产线默认值。** 结论出来之后是否改 l4_* 的 since_ts、
是否重新冻结存证，是另一次任务的事。
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

from model.l3_player import _resolve_item_values, fit_rate_model
from model.l5_window import (window_arms, sliding_arms, derive_positions, coarsen,
                             score_arm, paired_sign_test, patch_boundaries_in)

DEFAULT_CSV = os.path.join("data", "pro_player_matches_2020_2026.csv")
DEFAULT_TI_PM = os.path.join("data", "ti_2021_2025_player_matches.csv")
DEFAULT_OUT = os.path.join("reports", "p5_window_backtest")

# 训练侧只读这些列：全表 32 列 × 约 146 万行读进来没必要，而且号位推导
# 需要每场十个人都在（不能预先按选手过滤），所以列上省一点是值得的。
TRAIN_COLUMNS = ["match_id", "account_id", "player_slot", "start_time", "net_worth",
                 "kills", "deaths", "last_hits", "denies", "gold_per_min",
                 "towers_killed", "roshans_killed", "teamfight_participation",
                 "obs_placed", "camps_stacked", "rune_pickups",
                 "firstblood_claimed", "stuns"]

# ---- 预注册的判定规则（spec §2）。跑完再改这几个常量就等于事后挑指标。----
ALPHA = 0.05
MIN_HOLDOUTS_POSITIVE = 3
BASELINE_ARM = "L955d"     # 现行产线策略：开赛前 955 天
TREATMENT_ARM = "patch"    # 当届版本发布日起

HOLDOUTS = [
    {"year": "2022", "patch": "7.32"},
    {"year": "2023", "patch": "7.34"},
    {"year": "2024", "patch": "7.37"},
    {"year": "2025", "patch": "7.39"},
]
# TI2021 排除：训练侧只有 2020-01 起半年多数据，all 与所有短臂差别过小，
# 没有对照价值（spec §4）。

# 12 个 CSV 直取计分项。blob 三项 smokes/tormentor/courier 需解 OpenDota
# JSON blob，data/pro_blob_stats.csv 只覆盖 TI15 的 80 名选手、2024-01-01 起，
# 历史届取不到，明确排除（报告须写明覆盖 12/15 项）。
ITEMS = ["kills", "deaths", "creep_score", "gpm", "tower_kills", "roshan",
         "teamfight", "wards", "camps_stacked", "runes", "first_blood", "stuns"]

MIN_HOLDOUT_GAMES = 4

# 稳健性变体的入选门槛（spec §4「敏感性另跑 3 和 8」）。主判据仍用
# MIN_HOLDOUT_GAMES = 4，这两个只用来交叉验证结论对门槛是否敏感。
ROBUSTNESS_MIN_GAMES = (3, 8)


def _year_rows(pm, year):
    return pm[pm["match_date"].astype(str).str[:4] == str(year)]


def holdout_participants(pm, year, min_games=MIN_HOLDOUT_GAMES):
    """该届出场 >= min_games 的选手集合（不分计分项）。"""
    sub = _year_rows(pm, year).dropna(subset=["account_id"])
    counts = sub.groupby(sub["account_id"].astype("int64")).size()
    return {int(a) for a, c in counts.items() if c >= min_games}


def holdout_actuals(pm, year, item, min_games=MIN_HOLDOUT_GAMES):
    """该届每名选手该项的每局均值 -> {account_id: mean}。

    item 走 l3_player._resolve_item_values 同一套解析（creep_score =
    last_hits + denies 等）——预测侧和实际侧用不同的列合成方式是这类
    回测最容易出、也最难发现的错。

    n 按该项的**非空**观测计：teamfight_participation / stuns 在真实数据
    里有 NaN，口径必须与 fit_rate_model 一致。
    """
    sub = _year_rows(pm, year).copy()
    sub["_value"] = _resolve_item_values(sub, item)
    sub = sub.dropna(subset=["_value", "account_id"])
    if sub.empty:
        return {}
    stats = sub.groupby(sub["account_id"].astype("int64"))["_value"].agg(["mean", "count"])
    return {int(a): float(r["mean"]) for a, r in stats.iterrows()
            if r["count"] >= min_games}


def intersect_players(rates_by_arm):
    """所有臂都给出了预测的选手交集。

    臂之间人群不同就不是配对比较：短窗口会漏掉赛前歇了几个月的人，
    不取交集等于拿"全历史臂上的 18 人"跟"patch 臂上的 12 人"比。
    """
    sets = [set(r) for r in rates_by_arm.values()]
    return set.intersection(*sets) if sets else set()


def fit_arm(train, since, until, item, positions):
    """在时间切片 [since, until) 上跑 fit_rate_model -> {account_id: rate}。

    区间是左闭右开：until 等于开赛时间，开赛当天那一行必须排除，
    否则是数据泄漏。
    """
    ts = train["start_time"].astype("int64")
    sub = train[(ts >= int(since)) & (ts < int(until))]
    if sub.empty:
        return {}
    fitted = fit_rate_model(sub, item, positions)
    return {int(a): float(v["rate"]) for a, v in fitted.items()}


def run_holdout(train, pm, holdout, positions, arms, min_games=MIN_HOLDOUT_GAMES):
    """跑一届 holdout 的全部臂 × 全部计分项。

    positions 与 min_games 都由调用方传入，不在内部推导——Task 9 的稳健性
    检查要用同一个函数换口径重跑（换 core/support 分组、换入选门槛）。

    返回 {"units": [...], "coverage": [...], "skipped": [...]}：
      units    —— 每个 (item, position) 单元下各臂的 Spearman
      coverage —— 每个 item 的臂间交集前后人数（不许悄悄丢数据）
      skipped  —— 每个被跳过的单元及原因
    """
    year = holdout["year"]
    units, coverage, skipped = [], [], []
    for item in ITEMS:
        actual = holdout_actuals(pm, year, item, min_games)
        rates_by_arm = {arm: fit_arm(train, since, until, item, positions)
                        for arm, (since, until) in arms.items()}
        union = set().union(*[set(r) for r in rates_by_arm.values()]) if rates_by_arm else set()
        keep = intersect_players(rates_by_arm) & set(actual)
        coverage.append({"holdout": year, "item": item,
                         "n_union": len(union), "n_intersection": len(keep),
                         "n_dropped_by_intersection": len(union) - len(keep)})
        scores_by_arm = {}
        for arm, rates in rates_by_arm.items():
            kept = {a: v for a, v in rates.items() if a in keep}
            scores, skips = score_arm(kept, actual, positions)
            scores_by_arm[arm] = scores
            for pos, reason in skips.items():
                skipped.append({"holdout": year, "item": item, "arm": arm,
                                "position": pos, "reason": reason})
        all_pos = sorted({p for s in scores_by_arm.values() for p in s}, key=str)
        for pos in all_pos:
            row = {"holdout": year, "item": item, "position": pos,
                   "spearman": {arm: s.get(pos) for arm, s in scores_by_arm.items()}}
            t, b = row["spearman"].get(TREATMENT_ARM), row["spearman"].get(BASELINE_ARM)
            row["diff"] = None if (t is None or b is None) else float(t - b)
            units.append(row)
    return {"units": units, "coverage": coverage, "skipped": skipped}


def decide(units):
    """预注册的两条判定（spec §2），两条都满足才算"支持切窗口"。

    第 1 条（配对符号检验）单独用不行：同一届的 12 个计分项用的是同一批
    选手，单元之间不独立，符号检验会高估显著性。第 2 条（四届中至少 3 届
    同向）是按届聚类的一致性检查，挡住"某一届的特殊情况撑起了全局显著"。
    第 2 条单独用也不行：四届最多给到 p = 0.0625，永远够不到 0.05。
    """
    diffs = [u["diff"] for u in units if u.get("diff") is not None]
    test = paired_sign_test(diffs)
    by_holdout = {}
    for h in sorted({u["holdout"] for u in units}):
        d = [u["diff"] for u in units if u["holdout"] == h and u.get("diff") is not None]
        if d:
            by_holdout[h] = float(np.median(d))
    n_pos = sum(1 for v in by_holdout.values() if v > 0)
    supported = bool(test["p"] < ALPHA and test["median"] > 0
                     and n_pos >= MIN_HOLDOUTS_POSITIVE)
    return {"sign_test": test, "median_diff_by_holdout": by_holdout,
            "n_holdouts_positive": n_pos, "n_units_compared": len(diffs),
            "supported": supported}


def run_sliding(train, pm, holdout, positions, event_start_ts):
    """等长滑动窗口的台阶检验（spec §3）。

    每段长度相同，只有起点离开赛日的距离不同——长度一变，Spearman 的
    差异就分不清是"窗口更短"还是"离开赛更远"造成的。每段标注跨了哪些
    版本边界：曲线平滑下降 = 单纯的近期性；边界处掉档 = 版本效应。
    """
    out = []
    for arm, (since, until) in sliding_arms(event_start_ts).items():
        rhos = []
        for item in ITEMS:
            actual = holdout_actuals(pm, holdout["year"], item)
            rates = fit_arm(train, since, until, item, positions)
            kept = {a: v for a, v in rates.items() if a in actual}
            scores, _ = score_arm(kept, actual, positions)
            rhos += list(scores.values())
        out.append({"holdout": holdout["year"], "arm": arm,
                    "since_ts": since, "until_ts": until,
                    "n_scored_units": len(rhos),
                    "mean_spearman": float(np.mean(rhos)) if rhos else None,
                    "patch_boundaries": patch_boundaries_in(since, until)})
    return out


def build_report(csv_path=DEFAULT_CSV, ti_pm_path=DEFAULT_TI_PM):
    """跑完四届 × 12 项 × 7 臂，外加滑动窗口，返回完整报告 dict。"""
    train_all = pd.read_csv(csv_path, usecols=lambda c: c in set(TRAIN_COLUMNS),
                            low_memory=False)
    pm = pd.read_csv(ti_pm_path, low_memory=False)

    units, coverage, skipped, sliding, robustness_runs = [], [], [], [], []
    per_holdout_meta = []
    for h in HOLDOUTS:
        year = h["year"]
        event_start = int(_year_rows(pm, year)["start_time"].astype("int64").min())
        participants = holdout_participants(pm, year)
        pre = train_all[train_all["start_time"].astype("int64") < event_start]
        # 号位在**全部赛前历史**上算一次，跨臂固定——每臂各算会让各臂
        # 连分组都不同，那就不是配对比较了（spec §4）。
        positions_all = derive_positions(pre)
        positions = {a: p for a, p in positions_all.items() if a in participants}
        train = pre[pre["account_id"].isin(set(positions))].reset_index(drop=True)

        arms = window_arms(event_start, h["patch"])
        res = run_holdout(train, pm, h, positions, arms)
        units += res["units"]
        coverage += res["coverage"]
        skipped += res["skipped"]
        sliding += run_sliding(train, pm, h, positions, event_start)
        robustness_runs += run_robustness(train, pm, h, positions, arms)
        per_holdout_meta.append({
            "holdout": year, "patch": h["patch"], "event_start_ts": event_start,
            "n_participants": len(participants),
            "n_with_position": len(positions),
            "n_participants_without_pre_event_history": len(participants) - len(positions),
            "arms": {a: {"since_ts": s, "until_ts": u} for a, (s, u) in arms.items()},
        })

    return {
        "generated_by": "model/l5_window_backtest.py",
        "spec": "docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md",
        "baseline_arm": BASELINE_ARM, "treatment_arm": TREATMENT_ARM,
        "alpha": ALPHA, "min_holdouts_positive": MIN_HOLDOUTS_POSITIVE,
        "items_covered": "%d/15" % len(ITEMS),
        "excluded_items": ["smokes", "tormentor", "courier"],
        "holdouts": [h["year"] for h in HOLDOUTS],
        "holdout_meta": per_holdout_meta,
        "decision": decide(units),
        "units": units, "coverage": coverage, "skipped": skipped, "sliding": sliding,
        "robustness": aggregate_robustness(robustness_runs),
    }


def render_markdown(report):
    """人读版报告。

    措辞纪律（spec §8）：判不出显著时只能写"没有证据支持"，不能写成
    "证明了两者一样"——后者是本次样本量给不出的结论。
    """
    d = report["decision"]
    t = d["sign_test"]
    L = []
    L.append("# 选手数据窗口是否该切到当前版本 · 回测报告\n")
    L.append("产出：`%s` ｜ 设计：`%s`\n" % (report["generated_by"], report["spec"]))
    L.append("## 结论\n")
    if d["supported"]:
        L.append("**支持把窗口切到当届版本发布日起。**"
                 "配对符号检验 p=%.4f（<%.2f），中位差 %+.4f，"
                 "四届中 %d 届届内中位差为正（>=%d）。两条预注册判定均满足。\n"
                 % (t["p"], report["alpha"], t["median"],
                    d["n_holdouts_positive"], report["min_holdouts_positive"]))
    else:
        L.append("**没有证据支持把窗口切到当届版本发布日起。**"
                 "配对符号检验 p=%.4f，中位差 %+.4f，"
                 "四届中 %d 届届内中位差为正（需要 >=%d）。\n"
                 % (t["p"], t["median"], d["n_holdouts_positive"],
                    report["min_holdouts_positive"]))
        L.append("> 「没有证据支持」不等于「两者已被证明等价」。"
                 "单届单号位的候选人只有十几人，Spearman 的标准误约 0.25，"
                 "本次样本量下的检验力本来就有限，给不出等价性结论。\n")
    L.append("对照：treatment = `%s`，baseline = `%s`（现行产线策略）。"
             "参与配对的单元 %d 个（正 %d / 负 %d / 零 %d）。\n"
             % (report["treatment_arm"], report["baseline_arm"],
                d["n_units_compared"], t["n_pos"], t["n_neg"], t["n_zero"]))
    L.append("## 各届届内中位差\n")
    L.append("| 届 | 版本 | 中位差（patch − baseline） |")
    L.append("|---|---|---|")
    patch_of = {m["holdout"]: m["patch"] for m in report["holdout_meta"]}
    for h, v in d["median_diff_by_holdout"].items():
        L.append("| TI%s | %s | %+.4f |" % (h, patch_of.get(h, "?"), v))
    L.append("\n## 覆盖与丢弃\n")
    L.append("计分项覆盖 **%s**，排除 %s（需解 OpenDota JSON blob，"
             "`data/pro_blob_stats.csv` 只覆盖 TI15 的 80 名选手、2024-01-01 起，"
             "历史届取不到）。\n"
             % (report["items_covered"], "/".join(report["excluded_items"])))
    dropped = sum(c["n_dropped_by_intersection"] for c in report["coverage"])
    L.append("臂间取交集共丢弃 **%d** 人次（短窗口下没有数据的选手；"
             "不取交集就不是配对比较）。\n" % dropped)
    L.append("跳过的单元 **%d** 个，按原因：" % len(report["skipped"]))
    reasons = {}
    for s in report["skipped"]:
        reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
    for r, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        L.append("- %s：%d" % (r, n))
    L.append("\n## 滑动窗口台阶检验\n")
    L.append("等长 105 天、起点逐段往前滑。曲线平滑下降 = 单纯的近期性；"
             "版本边界处掉档 = 版本效应。\n")
    L.append("| 届 | 段 | 平均 Spearman | 段内跨越的版本 |")
    L.append("|---|---|---|---|")
    for s in report["sliding"]:
        ms = "—" if s["mean_spearman"] is None else "%.4f" % s["mean_spearman"]
        L.append("| TI%s | %s | %s | %s |"
                 % (s["holdout"], s["arm"], ms,
                    "、".join(s["patch_boundaries"]) or "无"))
    rb = report.get("robustness") or {}
    if rb:
        L.append("\n## 稳健性变体\n")
        L.append("不参与主判定，只用来看结论是不是靠某一个口径撑起来的。"
                 "变体只跑 treatment 与 baseline 两个臂。\n")
        L.append("| 变体 | 配对单元 | 正/负 | 中位差 | p | 结论同向？ |")
        L.append("|---|---|---|---|---|---|")
        for name, dv in rb.items():
            tv = dv["sign_test"]
            L.append("| %s | %d | %d/%d | %+.4f | %.4f | %s |"
                     % (name, dv["n_units_compared"], tv["n_pos"], tv["n_neg"],
                        tv["median"], tv["p"],
                        "是" if dv["supported"] == d["supported"] else "否"))
    return "\n".join(L) + "\n"


def run_robustness(train, pm, holdout, positions, arms):
    """稳健性变体（spec §4），只跑 treatment 与 baseline 两个臂。

      coarse_position —— 号位换成 core(1-3)/support(4-5)。这个划分在 TI15 的
                         80 名人工策展选手上与净资产排名 100% 吻合，是最不
                         依赖号位推导准确性的口径。
      min_games=3     —— 门槛放宽，多收小组赛就出局的队。
      min_games=8     —— 门槛收紧，只留打得深的队。

    三个变体都不参与主判定，作用是暴露"结论是不是靠某一个口径撑起来的"。
    只跑两个臂：另外五个臂对交叉验证没有增量信息，跑全套是三倍成本。
    """
    pair = {a: w for a, w in arms.items() if a in (BASELINE_ARM, TREATMENT_ARM)}
    out = [{"variant": "coarse_position",
            "units": run_holdout(train, pm, holdout, coarsen(positions), pair)["units"]}]
    for mg in ROBUSTNESS_MIN_GAMES:
        out.append({"variant": "min_games=%d" % mg,
                    "units": run_holdout(train, pm, holdout, positions, pair,
                                         min_games=mg)["units"]})
    return out


def aggregate_robustness(all_variant_runs):
    """把各届的变体结果按变体名合并，各自跑一遍 decide。"""
    by_variant = {}
    for run in all_variant_runs:
        by_variant.setdefault(run["variant"], []).extend(run["units"])
    return {v: decide(u) for v, u in by_variant.items()}


def main():
    ap = argparse.ArgumentParser(description="选手数据窗口版本切换回测（不改产线）")
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--ti-pm", default=DEFAULT_TI_PM)
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="输出前缀，会写 <out>.json 与 <out>.md")
    args = ap.parse_args()
    report = build_report(csv_path=args.csv, ti_pm_path=args.ti_pm)
    with open(args.out + ".json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(args.out + ".md", "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    print("写出 %s.json 与 %s.md" % (args.out, args.out))
    print("结论：%s" % ("支持切窗口" if report["decision"]["supported"]
                        else "没有证据支持切窗口"))


if __name__ == "__main__":
    main()
