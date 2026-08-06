"""L5 窗口回测：选手数据窗口该不该切到当届版本发布日起。

spec：docs/superpowers/specs/2026-08-06-fantasy-patch-window-design.md

结构与本仓既有的 l4_* 一致：纯函数在 model/l5_window.py，本模块负责
读真实 CSV、跑四届 holdout、出报告。预测速率直接复用
model.l3_player.fit_rate_model，一行不改——每个臂只是喂不同的时间切片。

**本模块不修改任何产线默认值。** 结论出来之后是否改 l4_* 的 since_ts、
是否重新冻结存证，是另一次任务的事。
"""
import numpy as np
import pandas as pd

from model.l3_player import _resolve_item_values

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
