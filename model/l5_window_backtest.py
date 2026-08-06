"""L5 窗口回测：选手数据窗口该不该切到当届版本发布日起。

spec：docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md

结构与本仓既有的 l4_* 一致：纯函数在 model/l5_window.py，本模块负责
读真实 CSV、跑四届 holdout、出报告。预测速率直接复用
model.l3_player.fit_rate_model，一行不改——每个臂只是喂不同的时间切片。

**本模块不修改任何产线默认值。** 结论出来之后是否改 l4_* 的 since_ts、
是否重新冻结存证，是另一次任务的事。
"""
import argparse
import datetime
import json
import os

import numpy as np
import pandas as pd

from model.l3_player import (_resolve_item_values, fit_rate_model,
                             MIN_N_FOR_OWN_GAME_VAR)
from model.l5_window import (DAY, window_arms, sliding_arms, derive_positions, coarsen,
                             score_arm, paired_sign_test, patch_boundaries_in)
from model.patches import patch_ts

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

# ---- 以下三个只服务于「探索性分析」小节，不参与任何预注册判定。----
# 等长对照臂：105 天，与四届里最长的那个版本窗口几乎一样长。把版本臂同时
# 对 baseline 和对它比，才分得清亏的是「版本边界」还是「窗口太短」。
CONTROL_ARM = "L105d"

# 读者提的方案是「只用 7.41 起的数据」。7.41 的发布时间在 model/patches.py
# （OpenDota constants/patch 实取），TI15 开赛日见 01-ti15-facts.md（已核实）。
# 天数由这两者算出来，不手抄——版本表一改，报告里的天数跟着变。
PROPOSAL_PATCH = "7.41"
PROPOSAL_EVENT_START_UTC = "2026-08-13T00:00:00Z"

# 渲染阈值：baseline 覆盖到 all 这么大比例时，正文才把这一届称作「几乎重合」。
# 只影响措辞，不影响任何数字，也不参与判定。
NEAR_COINCIDENT_SHARE = 0.90


def _year_rows(pm, year):
    return pm[pm["match_date"].astype(str).str[:4] == str(year)]


def participant_game_counts(pm, year, min_games=MIN_HOLDOUT_GAMES):
    """该届出场 >= min_games 的选手 -> 出场局数。

    局数本身要留着：ROBUSTNESS_MIN_GAMES 的两个门槛到底收不收得动人，
    只能拿这个分布说话，不能凭「门槛更松/更紧」想当然。
    """
    sub = _year_rows(pm, year).dropna(subset=["account_id"])
    counts = sub.groupby(sub["account_id"].astype("int64")).size()
    return {int(a): int(c) for a, c in counts.items() if c >= min_games}


def holdout_participants(pm, year, min_games=MIN_HOLDOUT_GAMES):
    """该届出场 >= min_games 的选手集合（不分计分项）。"""
    return set(participant_game_counts(pm, year, min_games))


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

    每段的跳过原因与 run_holdout / run_robustness 一样要留住：滑动窗口越往前
    越可能整组算不出来，只报 mean_spearman 会让「这一段没那么多单元」看不见。
    """
    out = []
    for arm, (since, until) in sliding_arms(event_start_ts).items():
        rhos, skipped = [], []
        for item in ITEMS:
            actual = holdout_actuals(pm, holdout["year"], item)
            rates = fit_arm(train, since, until, item, positions)
            kept = {a: v for a, v in rates.items() if a in actual}
            scores, skips = score_arm(kept, actual, positions)
            rhos += list(scores.values())
            for pos, reason in skips.items():
                skipped.append({"holdout": holdout["year"], "arm": arm,
                                "item": item, "position": pos, "reason": reason})
        out.append({"holdout": holdout["year"], "arm": arm,
                    "since_ts": since, "until_ts": until,
                    "n_scored_units": len(rhos),
                    "mean_spearman": float(np.mean(rhos)) if rhos else None,
                    "patch_boundaries": patch_boundaries_in(since, until),
                    "n_skipped_units": len(skipped), "skipped": skipped})
    return out


# ---- 探索性分解（不参与预注册判定，见 render_markdown 里的整段告诫）--------


def arm_diff_units(units, arm, baseline=BASELINE_ARM):
    """把 units 重算成「arm − baseline」的配对差，形状与主判定用的 units 一致。

    任何一侧缺值（该臂在该单元被跳过）时 diff 记 None，绝不记 0——
    把「算不出来」混进「没有差异」会直接污染符号检验。
    """
    out = []
    for u in units:
        a = u["spearman"].get(arm)
        b = u["spearman"].get(baseline)
        out.append({"holdout": u["holdout"], "item": u["item"],
                    "position": u["position"],
                    "diff": None if (a is None or b is None) else float(a - b)})
    return out


def compare_arms_to_baseline(units, baseline=BASELINE_ARM):
    """每个非 baseline 臂各自对 baseline 跑一遍 decide() -> {臂: decide 结果}。

    **这是探索性的**：预注册的对照只有 patch vs baseline 一组，事后对七个臂
    逐个跑同一套规则会抬高假阳性率。之所以还是要算，是因为不算的话报告里
    五个臂一个数字都没有，读者只看得到 treatment 输了、看不到别的臂赢了多少，
    结论就会被读成「窗口长度这件事已经查过了」。
    """
    arms = []
    for u in units:
        for a in u["spearman"]:
            if a not in arms:
                arms.append(a)
    return {a: decide(arm_diff_units(units, a, baseline))
            for a in arms if a != baseline}


def median_diff_by_holdout(units, arm_a, arm_b):
    """{届: median(arm_a − arm_b)}，任意两臂。"""
    out = {}
    for h in sorted({u["holdout"] for u in units}):
        d = [u["spearman"][arm_a] - u["spearman"][arm_b] for u in units
             if u["holdout"] == h
             and u["spearman"].get(arm_a) is not None
             and u["spearman"].get(arm_b) is not None]
        if d:
            out[h] = float(np.median(d))
    return out


def identical_units_by_holdout(units, arm_a, arm_b):
    """{届: {n_units, n_identical, median_diff}}，两臂逐单元完全相同的计数。

    spec §3 的已知弱点（训练数据下限 2020-01，最早那届的 baseline 几乎盖满
    了 all）需要用数字讲，「几乎重合」四个字本身不是证据。
    """
    out = {}
    for h in sorted({u["holdout"] for u in units}):
        pairs = [(u["spearman"].get(arm_a), u["spearman"].get(arm_b))
                 for u in units if u["holdout"] == h]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        if pairs:
            out[h] = {"n_units": len(pairs),
                      "n_identical": sum(1 for x, y in pairs if x == y),
                      "median_diff": float(np.median([x - y for x, y in pairs]))}
    return out


def window_sample_profile(train, window, n_players_total):
    """一个时间窗内「每名选手有多少局」的画像。

    只统计窗内**确实有数据**的选手：窗内一局都没有的人根本进不了该臂的预测，
    也就进不了臂间交集，把他们按 0 局混进中位数会把「样本稀薄」和「人直接
    消失」两件事搅在一起。两个数分开报。

    pct_below_min_n 用的是 l3_player.MIN_N_FOR_OWN_GAME_VAR：低于它的选手拿
    不到自身局内方差估计，只能退回号位先验——这是短窗口真正的代价。
    """
    since, until = window
    ts = train["start_time"].astype("int64")
    sub = train[(ts >= int(since)) & (ts < int(until))]
    counts = (sub.groupby(sub["account_id"].astype("int64")).size()
              if not sub.empty else pd.Series(dtype="int64"))
    n_present = int(len(counts))
    return {
        "window_days": int(round((int(until) - int(since)) / DAY)),
        "n_players_total": int(n_players_total),
        "n_players_in_window": n_present,
        "n_players_absent_from_window": int(n_players_total) - n_present,
        "median_games_in_window": float(counts.median()) if n_present else None,
        "min_n_for_own_game_var": MIN_N_FOR_OWN_GAME_VAR,
        "pct_below_min_n": (float((counts < MIN_N_FOR_OWN_GAME_VAR).mean() * 100)
                            if n_present else None),
    }


def baseline_overlap(train, arms, baseline=BASELINE_ARM):
    """baseline 窗口覆盖了 all 窗口多少行——spec §3 已知弱点的分子分母。"""
    a_s, a_u = arms["all"]
    b_s, b_u = arms[baseline]
    ts = train["start_time"].astype("int64")
    n_all = int(((ts >= int(a_s)) & (ts < int(a_u))).sum())
    n_base = int(((ts >= int(b_s)) & (ts < int(b_u))).sum())
    return {"n_rows_all": n_all, "n_rows_baseline": n_base,
            "baseline_since_ts": int(b_s),
            "baseline_share_of_all": (n_base / n_all) if n_all else None}


def proposal_window_days():
    """读者提议的窗口（PROPOSAL_PATCH 发布日 -> TI15 开赛日）有多少天。

    与 holdout_meta 里的 window_days 用同一套四舍五入，两边才能直接比。
    """
    e = int(datetime.datetime.strptime(PROPOSAL_EVENT_START_UTC, "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=datetime.timezone.utc).timestamp())
    return int(round((e - patch_ts(PROPOSAL_PATCH)) / DAY))


def build_exploratory(units, holdout_meta):
    """探索性小节要用的全部数字，一次算齐（渲染层只负责排版，不再算数）。"""
    lengths = [m["patch_window"]["window_days"] for m in holdout_meta
               if m.get("patch_window")]
    return {
        "preregistered": False,
        "control_arm": CONTROL_ARM,
        "arm_vs_baseline": compare_arms_to_baseline(units),
        "median_diff_vs_control_by_holdout":
            median_diff_by_holdout(units, TREATMENT_ARM, CONTROL_ARM),
        "treatment_vs_control_by_holdout":
            identical_units_by_holdout(units, TREATMENT_ARM, CONTROL_ARM),
        "all_vs_baseline_by_holdout":
            identical_units_by_holdout(units, "all", BASELINE_ARM),
        "proposal": {"patch": PROPOSAL_PATCH,
                     "event_start_utc": PROPOSAL_EVENT_START_UTC,
                     "window_days": proposal_window_days()},
        "historical_patch_window_days": ({"min": min(lengths), "max": max(lengths)}
                                         if lengths else None),
    }


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
        game_counts = participant_game_counts(pm, year)
        per_holdout_meta.append({
            "holdout": year, "patch": h["patch"], "event_start_ts": event_start,
            "n_participants": len(participants),
            "n_with_position": len(positions),
            "n_participants_without_pre_event_history": len(participants) - len(positions),
            "arms": {a: {"since_ts": s, "until_ts": u} for a, (s, u) in arms.items()},
            # 门槛敏感性到底空不空，看这个数：参赛者里出场最少的人打了几局。
            "min_games_among_participants": (min(game_counts.values())
                                             if game_counts else None),
            "patch_window": window_sample_profile(train, arms[TREATMENT_ARM],
                                                  len(positions)),
            "control_window": window_sample_profile(train, arms[CONTROL_ARM],
                                                    len(positions)),
            "baseline_overlap": baseline_overlap(train, arms),
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
        "exploratory": build_exploratory(units, per_holdout_meta),
    }


def _render_skip_reasons(lines, skipped, indent=""):
    """把跳过原因按出现次数降序渲染成条目列表，主路径与稳健性变体共用一套。"""
    reasons = {}
    for s in skipped:
        reasons[s["reason"]] = reasons.get(s["reason"], 0) + 1
    for r, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        lines.append("%s- %s：%d" % (indent, r, n))


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
    n_skipped = len(report["skipped"])
    # 零跳过时不要留一个吊在半空的冒号：后面什么都没有。
    L.append("跳过的单元 **%d** 个%s" % (n_skipped, "，按原因：" if n_skipped else "。"))
    _render_skip_reasons(L, report["skipped"])
    L.append("\n## 滑动窗口台阶检验\n")
    L.append("等长 105 天、起点逐段往前滑。曲线平滑下降 = 单纯的近期性；"
             "版本边界处掉档 = 版本效应。\n")
    L.append("| 届 | 段 | 平均 Spearman | 跳过单元 | 段内跨越的版本 |")
    L.append("|---|---|---|---|---|")
    for s in report["sliding"]:
        ms = "—" if s["mean_spearman"] is None else "%.4f" % s["mean_spearman"]
        L.append("| TI%s | %s | %s | %d | %s |"
                 % (s["holdout"], s["arm"], ms,
                    s.get("n_skipped_units", len(s.get("skipped") or [])),
                    "、".join(s["patch_boundaries"]) or "无"))
    _render_robustness(L, report)
    _render_exploratory(L, report)
    return "\n".join(L) + "\n"


def _sign(x):
    return (x > 0) - (x < 0)


def _same_direction(a, b):
    """两个中位差是否同向。

    比的是**符号**，不是两个 supported 布尔值——"不支持"有好几种理由，
    两边都 False 就会把一个中位差强烈为正、只是届数不够的变体渲染成
    「同向」，而那恰恰是最需要被看见的反例。
    """
    return "是" if _sign(a) == _sign(b) else "否"


def _render_robustness(L, report):
    rb = report.get("robustness") or {}
    if not rb:
        return
    d = report["decision"]
    t = d["sign_test"]
    L.append("\n## 稳健性变体\n")
    L.append("不参与主判定，只用来看结论是不是靠某一个口径撑起来的。"
             "变体只跑 treatment 与 baseline 两个臂。"
             "末列比的是**中位差的符号**是否与主结果同向（不是两个 supported "
             "布尔值——那样任何一种「不支持」都会被算成同向）。\n")
    L.append("| 变体 | 配对单元 | 正/负 | 中位差 | p | 中位差同向？ |")
    L.append("|---|---|---|---|---|---|")
    for name, dv in rb.items():
        tv = dv["sign_test"]
        L.append("| %s | %d | %d/%d | %+.4f | %.4f | %s |"
                 % (name, dv["n_units_compared"], tv["n_pos"], tv["n_neg"],
                    tv["median"], tv["p"],
                    _same_direction(tv["median"], t["median"])))
    alpha = report.get("alpha", ALPHA)
    against = [(n, dv) for n, dv in rb.items()
               if dv["sign_test"]["p"] < alpha and dv["sign_test"]["median"] < 0]
    for name, dv in against:
        tv = dv["sign_test"]
        L.append("\n`%s` 在 α=%.2f 下**显著**，而且中位差为负（%+.4f，p=%.4f，"
                 "正/负 %d/%d）：在这个口径下 treatment 显著地**更差**。"
                 "这是全表最扎眼的一个数字——它加强而不是削弱上面的负面结论，"
                 "方向上也跟主判定一致。"
                 % (name, alpha, tv["median"], tv["p"], tv["n_pos"], tv["n_neg"]))
    _render_threshold_vacuity(L, report, rb)
    L.append("\n各变体跳过的单元：")
    for name, dv in rb.items():
        skipped = dv.get("skipped") or []
        L.append("- **%s**：跳过 %d 个" % (name, len(skipped)))
        if skipped:
            _render_skip_reasons(L, skipped, "  ")


def _render_threshold_vacuity(L, report, rb):
    """门槛敏感性是不是空检验，用数字说，不摆成"通过了的检查"。"""
    d = report["decision"]
    vacuous = [n for n, dv in rb.items()
               if n.startswith("min_games=")
               and dv["sign_test"] == d["sign_test"]
               and dv["n_units_compared"] == d["n_units_compared"]]
    if not vacuous:
        return
    mins = [m.get("min_games_among_participants") for m in report.get("holdout_meta", [])]
    mins = [m for m in mins if m is not None]
    line = ("\n**门槛敏感性是空检验。** %s 的符号检验与主结果逐位相同"
            "（配对单元、正/负、中位差、p 全部一致）。原因有两层："
            "一是 `build_report` 交给变体的 positions 与 train 已经在 "
            "`MIN_HOLDOUT_GAMES=%d` 上冻结过，把门槛放宽到 3 在**构造上**不可能"
            "再收进任何选手；" % ("、".join("`%s`" % v for v in vacuous),
                                  MIN_HOLDOUT_GAMES))
    if mins:
        line += ("二是各届参赛者的最少出场局数是 %s，收紧到 8 也收不掉人。"
                 % "/".join(str(m) for m in mins))
    else:
        line += "二是各届参赛者的出场局数本来就都在这两个门槛之上。"
    line += "所以三个变体里真正有信息量的只有 `coarse_position`。"
    L.append(line)


def _fmt(v, spec="%.4f", none="—"):
    return none if v is None else spec % v


def _render_exploratory(L, report):
    """探索性分解（复审整改）。

    放在最后、整段带告诫：预注册结论是头条，本节不许改变它的地位。但也
    不能不写——原报告七个臂里只有 treatment 的数字到得了读者眼前，读者会
    据此以为「窗口长度这件事已经查过了」，而本次自己产出的数据说的恰恰相反。
    """
    ex = report.get("exploratory")
    if not ex:
        return
    metas = report.get("holdout_meta") or []
    L.append("\n## 探索性分析（非预注册）\n")
    L.append("> **本节全部是探索性的，不属于预注册分析。** 预注册的对照只有一组"
             "（`%s` vs `%s`，见开头的〈结论〉）；本节把七个臂逐个摆开、并把版本臂"
             "的亏损按窗口长度拆开，都是在看过主结果之后才做的：多重比较**没有**"
             "做任何校正，分析单元之间也**不独立**（同一届 12 个计分项用的是同一批"
             "选手，符号检验会高估显著性）。\n"
             % (report["treatment_arm"], report["baseline_arm"]))
    L.append("> **本节任何一行都不构成改产线 `since_ts` 的依据。** 要真的动窗口，"
             "必须另立一次预注册检验：先写死候选臂与判据、再跑数据。"
             "上面那条预注册结论不因本节而改变。\n")

    L.append("### 七个臂各自对 baseline\n")
    L.append("对每个臂套用与主判定**完全相同**的 `decide()`：配对符号检验 "
             "p<%.2f 且中位差>0，并且至少 %d 届届内中位差为正。"
             "「同一规则下成立？」那一列只是这把尺子的读数，不是推荐。\n"
             % (report["alpha"], report["min_holdouts_positive"]))
    L.append("| 臂 | 正/负/零 | 中位差 | p | 届内为正 | 同一规则下成立？ |")
    L.append("|---|---|---|---|---|---|")
    ranked = sorted((ex.get("arm_vs_baseline") or {}).items(),
                    key=lambda kv: -kv[1]["sign_test"]["median"])
    for arm, dd in ranked:
        tv = dd["sign_test"]
        label = "`%s`%s" % (arm, "（treatment）" if arm == report["treatment_arm"] else "")
        # p 用五位小数：几个短窗口臂的 p 都在 1e-3 量级，四位会把它们压成同一个数。
        L.append("| %s | %d/%d/%d | %+.4f | %.5f | %d/%d | %s |"
                 % (label, tv["n_pos"], tv["n_neg"], tv["n_zero"],
                    tv["median"], tv["p"], dd["n_holdouts_positive"],
                    len(dd["median_diff_by_holdout"]),
                    "是" if dd["supported"] else "否"))

    L.append("\n### 版本边界 vs 窗口长度\n")
    L.append("版本臂到底亏在「版本边界」还是「窗口太短」，看这张表：窗口越短，"
             "低于 `l3_player.MIN_N_FOR_OWN_GAME_VAR` 的选手越多——这些人拿不到"
             "自身局内方差估计，只能退回号位先验。倒数第二列是版本臂对**等长日历"
             "窗口** `%s` 的届内中位差（不是对 baseline），末列是两臂逐单元 Spearman "
             "完全相同的个数。\n" % ex.get("control_arm"))
    L.append("| 届 | 版本 | 版本窗口 | 窗内有数据的选手 | 每人局数中位 | 低于门槛的比例 | 中位差 vs `%s` | 两臂完全相同的单元 |"
             % ex.get("control_arm"))
    L.append("|---|---|---|---|---|---|---|---|")
    ctl = ex.get("median_diff_vs_control_by_holdout") or {}
    tvc = ex.get("treatment_vs_control_by_holdout") or {}
    for m in metas:
        w = m.get("patch_window") or {}
        u = tvc.get(m["holdout"]) or {}
        L.append("| TI%s | %s | %s 天 | %s/%s | %s | %s | %s | %s |"
                 % (m["holdout"], m.get("patch", "?"),
                    _fmt(w.get("window_days"), "%d"),
                    _fmt(w.get("n_players_in_window"), "%d"),
                    _fmt(w.get("n_players_total"), "%d"),
                    _fmt(w.get("median_games_in_window"), "%.0f"),
                    _fmt(w.get("pct_below_min_n"), "%.1f%%"),
                    _fmt(ctl.get(m["holdout"]), "%+.4f"),
                    ("%d/%d" % (u["n_identical"], u["n_units"])) if u else "—"))
    thr = next((m["patch_window"].get("min_n_for_own_game_var") for m in metas
                if m.get("patch_window")), None)
    if thr is not None:
        L.append("\n（「低于门槛」= 窗内局数 < `MIN_N_FOR_OWN_GAME_VAR` = %d。"
                 "窗内一局都没有的选手不计入中位数与比例，单列在「窗内有数据的选手」，"
                 "他们根本进不了该臂的预测、也就进不了臂间交集。）" % thr)

    ranked_meta = sorted((m for m in metas if m.get("patch_window")),
                         key=lambda m: m["patch_window"]["window_days"])
    if ranked_meta:
        longest = ranked_meta[-1]
        others = ranked_meta[:-1]
        u = tvc.get(longest["holdout"]) or {}
        para = ("\n**（a）版本边界本身：窗口长度一对齐，边界就不花钱了。** "
                "TI%s 的版本窗口 %d 天，与等长日历窗口 `%s` 基本同长；这一届上"
                "「从版本发布日切」相对「从等长日历窗口切」的届内中位差是 %s"
                % (longest["holdout"], longest["patch_window"]["window_days"],
                   ex.get("control_arm"), _fmt(ctl.get(longest["holdout"]), "%+.4f")))
        if u:
            para += ("（%d 个单元里 %d 个两臂完全相同，其余 %d 个有差异但正负相抵）"
                     % (u["n_units"], u["n_identical"],
                        u["n_units"] - u["n_identical"]))
        para += ("。这一届是**特意造出来的对照**——spec §3 设 `%s` 就是为了跟它"
                 "几乎重合，用来把「近期性」和「版本」分开。它能证明的是"
                 "「版本边界只通过它圈进来的那批数据起作用，边界本身不额外携带"
                 "信息」，**不是**「版本边界在任何窗口长度下都无害」。"
                 % ex.get("control_arm"))
        vals = [ctl.get(m["holdout"]) for m in others]
        vals = [v for v in vals if v is not None]
        if others and vals:
            lens = [m["patch_window"]["window_days"] for m in others]
            para += ("其余 %d 届的版本窗口只有 %d–%d 天，同一个对照下的届内中位差是 %s%s"
                     % (len(others), min(lens), max(lens),
                        "、".join("%+.4f" % v for v in vals),
                        "——全部为负。差距出现在窗口短的那几届，不出现在长度对齐的那一届。"
                        if all(v < 0 for v in vals) else "。"))
        L.append(para + "\n")

    beaten = [(a, dd) for a, dd in (ex.get("arm_vs_baseline") or {}).items()
              if dd["supported"]]
    beaten.sort(key=lambda kv: -kv[1]["sign_test"]["median"])
    if beaten:
        L.append("**（b）窗口长度本身是有效应的，而且现行的 `%s` 被更短的窗口打败。** "
                 "同一套规则下，有 %d 个臂对 baseline 同时满足两条判定：%s。"
                 "**这不是可以直接照做的结论**——见本节开头的告诫；它只说明"
                 "「窗口长度」这个维度还没有被认真查过。\n"
                 % (report["baseline_arm"], len(beaten),
                    "、".join("`%s`（中位差 %+.4f，p=%.5f，%d/%d 届为正）"
                              % (a, dd["sign_test"]["median"], dd["sign_test"]["p"],
                                 dd["n_holdouts_positive"],
                                 len(dd["median_diff_by_holdout"]))
                              for a, dd in beaten)))
    else:
        L.append("**（b）** 同一套规则下没有任何一个臂对 baseline 同时满足两条判定。\n")

    prop = ex.get("proposal") or {}
    hist = ex.get("historical_patch_window_days") or {}
    if prop and hist:
        L.append("**（c）本次回测没有测到读者真正提的那个窗口。** 四届 holdout 的版本"
                 "窗口是 %d–%d 天，而 `%s` 到 TI15 开赛（%s）有 **%d 天**——比历史上"
                 "任何一届的版本窗口都长，落在上表那些日历窗口的量级里，而不是落在"
                 "被测的版本窗口的量级里。所以「只用 %s 起的数据」这个提议，本次回测"
                 "既没有证伪也没有证实：它测的是 %d–%d 天的版本窗口，不是 %d 天的。"
                 % (hist["min"], hist["max"], prop.get("patch"),
                    prop.get("event_start_utc"), prop.get("window_days"),
                    prop.get("patch"), hist["min"], hist["max"],
                    prop.get("window_days")))

    ov = ex.get("all_vs_baseline_by_holdout") or {}
    if ov:
        L.append("\n### 已知弱点：`all` 与 baseline 的重合度（spec §3）\n")
        L.append("训练数据下限是 **2020-01**，而 baseline 是「开赛前 955 天」——"
                 "holdout 越早，baseline 的起点越贴近数据下限，`all` 与 baseline "
                 "就越像。这不影响主判据（`%s` vs `%s`），但「`all` vs baseline」"
                 "这一组对照在早期届上几乎没有信息量——读七臂表里 `all` 那一行时"
                 "要记住这一点。\n"
                 % (report["treatment_arm"], report["baseline_arm"]))
        L.append("| 届 | baseline 覆盖 `all` 的行数比例 | 两臂完全相同的单元 | 届内中位差 |")
        L.append("|---|---|---|---|")
        for m in metas:
            o = m.get("baseline_overlap") or {}
            u = ov.get(m["holdout"]) or {}
            share = o.get("baseline_share_of_all")
            L.append("| TI%s | %s | %s | %s |"
                     % (m["holdout"],
                        _fmt(None if share is None else share * 100, "%.1f%%"),
                        ("%d/%d" % (u["n_identical"], u["n_units"])) if u else "—",
                        _fmt(u.get("median_diff"), "%+.4f")))
        near = [m["holdout"] for m in metas
                if (m.get("baseline_overlap") or {}).get("baseline_share_of_all")
                is not None
                and m["baseline_overlap"]["baseline_share_of_all"] >= NEAR_COINCIDENT_SHARE]
        L.append("\n达到「几乎重合」（baseline 覆盖 `all` 的 %.0f%% 以上）的是 %s。"
                 "spec §3 把最早两届一并写成对这组对照「基本没有信息量」，"
                 "实测只有上表里过线的那几届到这个程度——**以表为准**。\n"
                 % (NEAR_COINCIDENT_SHARE * 100,
                    "、".join("TI" + h for h in near) if near else "（没有）"))


def run_robustness(train, pm, holdout, positions, arms):
    """稳健性变体（spec §4），只跑 treatment 与 baseline 两个臂。

      coarse_position —— 号位换成 core(1-3)/support(4-5)。这个划分在 TI15 的
                         80 名人工策展选手上与净资产排名 100% 吻合，是最不
                         依赖号位推导准确性的口径。
      min_games=3     —— 名义上是放宽门槛，**实际上收不进任何人**：build_report
                         传进来的 positions 与 train 已经在 MIN_HOLDOUT_GAMES
                         上冻结过，只打了 3 局的选手连预测都拿不到，放宽下游
                         门槛在构造上不可能把他们捞回来。
      min_games=8     —— 门槛收紧，名义上只留打得深的队。真实数据上四届参赛者
                         的最少出场局数都不低于 8，所以它同样收不掉人。

    换句话说，这两个门槛变体在本次数据上都是**空检验**，报告会拿
    holdout_meta.min_games_among_participants 和「与主结果逐位相同」照实写明，
    不能摆成"通过了的稳健性检查"。真正有信息量的只有 coarse_position。

    三个变体都不参与主判定，作用是暴露"结论是不是靠某一个口径撑起来的"。
    只跑两个臂：另外五个臂对交叉验证没有增量信息，跑全套是三倍成本。

    三个变体各自换了号位分组或入选门槛，skip 模式互不相同、也推不出彼此——
    每个变体的 skipped 都要带上 "variant" 字段原样返回，不能只留 units
    （不许悄悄丢数据）。
    """
    pair = {a: w for a, w in arms.items() if a in (BASELINE_ARM, TREATMENT_ARM)}

    def _run(variant, res):
        return {"variant": variant, "units": res["units"],
                "skipped": [dict(s, variant=variant) for s in res["skipped"]]}

    out = [_run("coarse_position",
                run_holdout(train, pm, holdout, coarsen(positions), pair))]
    for mg in ROBUSTNESS_MIN_GAMES:
        out.append(_run("min_games=%d" % mg,
                        run_holdout(train, pm, holdout, positions, pair,
                                    min_games=mg)))
    return out


def aggregate_robustness(all_variant_runs):
    """把各届的变体结果按变体名合并，各自跑一遍 decide。

    skipped 同样按变体合并，塞进对应变体那个 decide() 结果 dict 里的
    "skipped" 键——decide() 本身不产出这个键，不会撞车。三个变体的口径
    互不相同，各自的跳过原因不能互相推导，必须各自带着走到报告里。

    units 也一样要带走。只留 decide() 的汇总，coarse_position 那个 p 值就
    没法像主结论一样被独立复核——主结论之所以可复核，正是因为 240 个单元
    原样进了 JSON。同一条「不许悄悄丢数据」的规矩，对变体一视同仁。
    """
    units_by_variant = {}
    skipped_by_variant = {}
    for run in all_variant_runs:
        units_by_variant.setdefault(run["variant"], []).extend(run["units"])
        skipped_by_variant.setdefault(run["variant"], []).extend(run.get("skipped", []))
    out = {}
    for v, units in units_by_variant.items():
        d = decide(units)
        d["skipped"] = skipped_by_variant.get(v, [])
        d["units"] = units
        out[v] = d
    return out


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
