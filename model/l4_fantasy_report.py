"""L4-P1 编排脚本：把 fantasy_stats / l3_player / l4_fantasy / l2_predictions
串起来，落盘成 reports/p1_fantasy_matrix.json（task-7-brief.md Step 6）。

产出三张表 + A/B 双分支：
  - player_matrix   选手 × 15 个可得计分项 的每局期望（不出绝对总分，§4.3）
  - slot_core / slot_mid / slot_support   按队聚合到三个 Fantasy 槽
  - branch_a / branch_b   A/B 两种计分口径下的期望分（§4.3，两个都算）

A/B 分支的期望分需要一个"跟量纲无关的单一每局综合分"喂给
`expected_slot_score`（否则 GPM~600 和 Kills~7 直接相加毫无意义）。
这里用 06-fantasy-rules.md §E.1 的 DPC 时代 12 项系数当代理——跟该文档
§G 统计 TI14 真实分布用的是同一套代理系数、同样的"非 TI15 真实分数"
免责声明。`proxy_score_by_slot` 字段单独暴露这个中间量，避免使用者
误把 branch_a/branch_b 的绝对数值当成 TI15 官方分数。

用法：
  python3 model/l4_fantasy_report.py --out reports/p1_fantasy_matrix.json
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rosters import ROSTERS, POSITIONS, ACCOUNT_TO_TEAM, ACCOUNT_TO_NAME
from fantasy_stats import available_items, load_player_games, SCORING_ITEMS
from l3_player import fit_rate_model
from l4_fantasy import player_matrix, slot_aggregate, expected_slot_score, SLOT_POSITIONS

DEFAULT_CSV = os.path.join(HERE, "..", "data", "pro_player_matches_2020_2026.csv")
DEFAULT_BLOB = os.path.join(HERE, "..", "data", "pro_blob_stats.csv")
DEFAULT_L2 = os.path.join(HERE, "l2_predictions.json")
SINCE_2024_01_01 = 1704067200   # 与 Task 6 Step 5 真实数据校验脚本同一个窗口起点

# DPC 时代 12 项系数（06-fantasy-rules.md §E.1）。只作 A/B 分支对比用的
# 代理综合分，不是 TI15 真实系数（真实系数服务端下发、拿不到，§4.3）。
# smokes/tormentor/courier 三项 2026 才有、DPC 时代没有对应系数，
# 不计入这个代理分——跟 06-fantasy-rules.md §G 统计 TI14 真实分布的
# 方法论（"缺失的 6 项未计入"）一致。
DPC_PROXY_LINEAR = {
    "kills": 0.3, "creep_score": 0.003, "gpm": 0.002, "tower_kills": 1.0,
    "roshan": 1.0, "wards": 0.5, "camps_stacked": 0.5, "runes": 0.25, "stuns": 0.05,
}
DPC_DEATH_BASE, DPC_DEATH_COEF = 3.0, 0.3
DPC_TEAMFIGHT_COEF = 3.0
DPC_FIRST_BLOOD_COEF = 4.0

BLUE_POOL_GAP_NOTE = "蓝池 6 项中 Watcher/Lotus 取不到，Support 槽预测结构性偏弱"


def dpc_proxy_score(item_rates):
    """{item_key: 每局期望} → 一个单一的"类 fantasy 综合评分"代理值。

    只是为了让 A/B 分支对比这一步"有意义地相加"，不是 TI15 真实分数。
    """
    score = DPC_DEATH_BASE - DPC_DEATH_COEF * item_rates.get("deaths", 0.0)
    score += DPC_TEAMFIGHT_COEF * item_rates.get("teamfight", 0.0)
    score += DPC_FIRST_BLOOD_COEF * item_rates.get("first_blood", 0.0)
    for key, coef in DPC_PROXY_LINEAR.items():
        score += coef * item_rates.get(key, 0.0)
    return score


def _round(x, nd=6):
    """递归四舍五入到 nd 位小数（项目全局约束：概率/期望输出 JSON 一律保
    6 位小数）。字符串/None/布尔原样透传——这份报告里 notes、name、team
    这些字段都是字符串，不能被 float() 强转。"""
    if isinstance(x, dict):
        return {k: _round(v, nd) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v, nd) for v in x]
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, (int, np.integer)):
        return int(x)
    return round(float(x), nd)


def load_blob_joined_df(csv_path, blob_path, account_ids, since_ts):
    """smokes / tormentor / courier 三项 `column=None`，不会出现在
    `load_player_games` 的返回值里（06-fantasy-rules.md §F.5：需从
    OpenDota JSON blob 另外解出）。这里按 match_id + account_id 左连接
    `data/pro_blob_stats.csv`（Task 5 已抽取好的产出，见
    `model/fantasy_stats.py` 模块 docstring）——左连接是因为主表覆盖的
    选手-比赛行不保证每一行都在 blob 表里有对应记录，缺失值按"这三项
    实际发生 0 次"处理（fillna(0)），不能因为没连上就整行丢弃。
    """
    df = load_player_games(csv_path, account_ids, since_ts)
    if not os.path.exists(blob_path):
        print(f"[警告] 找不到 {blob_path}，smokes/tormentor/courier 三项将无法计算"
              f"（需要先按 06-fantasy-rules.md §F.5 的查询重新跑一遍）", file=sys.stderr)
        for c in ("smokes", "tormentor", "courier"):
            df[c] = 0
        return df
    blob = pd.read_csv(blob_path)
    df = df.merge(blob, on=["match_id", "account_id"], how="left")
    for c in ("smokes", "tormentor", "courier"):
        df[c] = df[c].fillna(0).astype("int64")
    return df


def build_report(csv_path=DEFAULT_CSV, blob_path=DEFAULT_BLOB, l2_path=DEFAULT_L2,
                  since_ts=SINCE_2024_01_01):
    pos = {aid: POSITIONS[t][p] for t, r in ROSTERS.items() for p, aid in r.items()}
    df = load_blob_joined_df(csv_path, blob_path, set(ACCOUNT_TO_TEAM), since_ts)

    items = available_items(include_blob=True)          # 15/18 可得项
    item_keys = [i["key"] for i in items]
    rates_by_item = {i["key"]: fit_rate_model(df, i["key"], pos) for i in items}

    matrix = player_matrix(rates_by_item, items=item_keys)

    slot_core = slot_aggregate(matrix, ROSTERS, pos, slot="core")
    slot_mid = slot_aggregate(matrix, ROSTERS, pos, slot="mid")
    slot_support = slot_aggregate(matrix, ROSTERS, pos, slot="support")

    l2 = json.load(open(l2_path))
    series_dist = l2["series_dist"]

    branch_a, branch_b, proxy_score = {}, {}, {}
    for slot_name, agg in (("core", slot_core), ("mid", slot_mid), ("support", slot_support)):
        # 固定按 ROSTERS 字面顺序遍历（agg 本身就是 slot_aggregate 按这个
        # 顺序建的 dict），确保 expected_slot_score 内部按同一个 rng 流
        # 依次消费每队的模拟——同一份输入每次重跑都逐位可复现。
        proxy = {team: dpc_proxy_score(item_rates) for team, item_rates in agg.items()}
        proxy_matrix = {team: {"proxy": v} for team, v in proxy.items()}
        proxy_score[slot_name] = proxy
        branch_a[slot_name] = expected_slot_score(proxy_matrix, series_dist, branch="A")
        branch_b[slot_name] = expected_slot_score(proxy_matrix, series_dist, branch="B")

    player_matrix_out = {}
    for acct, item_rates in matrix.items():
        player_matrix_out[str(acct)] = {
            "name": ACCOUNT_TO_NAME.get(acct, str(acct)),
            "team": ACCOUNT_TO_TEAM.get(acct, "?"),
            "position": pos.get(acct),
            "n_games": {k: rates_by_item[k].get(acct, {}).get("n_games", 0) for k in item_rates},
            "items": item_rates,
        }

    missing_items = [i["key"] for i in SCORING_ITEMS if not i["available"]]

    notes = [
        "不出绝对总分：Fantasy 18 项基础系数是服务端运行时插值 {f:helpstat_0..17}，"
        "静态提取不到（设计文档 §4.3）。本表只交付「选手/队伍 × 计分项」的"
        "每局期望矩阵，由使用者按自己装的徽记（Emblem）自行取用对应分项。",

        BLUE_POOL_GAP_NOTE + "（设计文档 §6 R4，06-fantasy-rules.md §F.3：蓝色徽记池"
        "6 项里 Watchers Taken / Lotuses Grabbed 完全没有任何数据字段，Support Duo"
        "槽的战旗全是蓝色徽记，这不是可以后补的缺口）。",

        "A/B 两个计分分支的口径未定（§4.3/§6 R3），本报告两个分支都出："
        "branch_a=全程只取最好的一个系列赛（能力压倒深度）、"
        "branch_b=三阶段分别计分缺席记 0（深度压倒能力）。",

        "branch_a/branch_b/proxy_score_by_slot 里的分数是用 06-fantasy-rules.md §E.1"
        "的 DPC 时代 12 项系数把分项矩阵合成的单一代理分，仅用于展示两个分支"
        "「能力 vs 深度」的相对形状——不是 TI15 真实分数（TI15 真实系数拿不到，"
        "同上），量级不能直接当作 TI15 官方 Fantasy 分数使用。",

        "smokes / tormentor / courier 三项来自 data/pro_blob_stats.csv 按 "
        "match_id+account_id 左连接（06-fantasy-rules.md §F.5）；madstone 只有"
        "使用疯石袋的代理量（语义不等于采集疯石）、watchers/lotuses 完全没有"
        "字段，这三项（连同 madstone）不在 player_matrix 的覆盖范围内，"
        "18 项里能出的是 15 项。",

        "series_dist 来自 model/l2_predictions.json（model/l2_simulate.py 产出，"
        "200,000 次蒙特卡洛的期望系列赛数），group=瑞士轮+附加轮、"
        "playoff=主赛事双败淘汰赛；Fantasy 官方的 period 边界具体怎么划分未查到"
        "（06-fantasy-rules.md §H #5），这里用 2 段简化，不是 3 段。",
    ]

    return {
        "notes": notes,
        "coverage": {
            "available_items": item_keys,
            "missing_items": missing_items,
            "pool_coverage": {"red": "5(+1 代理 madstone)/6", "blue": "4/6", "green": "6/6"},
            "n_players_with_rates": len(matrix),
        },
        "slot_positions": {k: list(v) for k, v in SLOT_POSITIONS.items()},
        "player_matrix": player_matrix_out,
        "slot_core": slot_core,
        "slot_mid": slot_mid,
        "slot_support": slot_support,
        "proxy_score_by_slot": proxy_score,
        "branch_a": branch_a,
        "branch_b": branch_b,
        "since_ts": since_ts,
        "n_rows_used": int(len(df)),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "reports", "p1_fantasy_matrix.json"))
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--blob", default=DEFAULT_BLOB)
    ap.add_argument("--l2", default=DEFAULT_L2)
    ap.add_argument("--since-ts", type=int, default=SINCE_2024_01_01)
    args = ap.parse_args()

    report = build_report(csv_path=args.csv, blob_path=args.blob, l2_path=args.l2,
                          since_ts=args.since_ts)
    report = _round(report)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)

    print(f"选手矩阵：{report['coverage']['n_players_with_rates']} 名选手 × "
          f"{len(report['coverage']['available_items'])} 项")
    print(f"Core/Mid/Support 队级槽：{len(report['slot_core'])}/"
          f"{len(report['slot_mid'])}/{len(report['slot_support'])} 队")
    print(f"已写入 {args.out}")
    print()
    print("[必须声明] " + BLUE_POOL_GAP_NOTE)


if __name__ == "__main__":
    main()
