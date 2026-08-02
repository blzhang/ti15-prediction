"""L4-P3/P4 编排脚本：把 fantasy_stats / l3_player / l4_players 串起来，
落盘成 `reports/p3_p4_players.md`（task-8-brief.md Step 5 的人工抽查对象）
+ 同名 `.json`（完整数据，供下游程序化消费，6 位小数）。

P3 选手实力排名：15 个可得计分项里，除 deaths 外的 14 项都是"更高更好"，
    按位置分层排序（`rank_players`）；deaths 越低越好，不适合塞进
    "排名=更强"的框架，只出现在 P4 里（预测其场均值，不隐含名次即优劣）。
P4 个人数据预测：全部 15 个可得项，逐人逐项给 (均值, lo, hi)（`predict_player_stats`）。

两者共享同一份 `rates_by_item`（`fit_rate_model` 对每个 item_key 独立拟合的
输出），跟 Task 7 的 P1 报告用的是同一层 L3 读出、同一个 since_ts 窗口——
两份报告因此互相可比对（同一个 df/rates_by_item，只是消费方式不同：
P1 把速率合成到队级 Fantasy 槽，P3/P4 直接读选手层排名与区间）。

复用 `model/l4_fantasy_report.py` 已经写好并跑通的 `load_blob_joined_df`
（smokes/tormentor/courier 三项按 match_id+account_id 左连 blob 表）和
`_round`（JSON 输出统一 6 位小数），不重复实现同一段逻辑——`l4_fantasy_report`
是纯函数+`if __name__=="__main__"`门禁的模块，`import` 它不会触发任何
副作用（不会重新跑一遍它的 main）。

用法：
  python3 model/l4_players_report.py --out reports/p3_p4_players.md
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rosters import ROSTERS, POSITIONS, ACCOUNT_TO_TEAM, ACCOUNT_TO_NAME
from fantasy_stats import available_items
from l3_player import fit_rate_model
from l4_players import rank_players, predict_player_stats
from l4_fantasy_report import load_blob_joined_df, _round

DEFAULT_CSV = os.path.join(HERE, "..", "data", "pro_player_matches_2020_2026.csv")
DEFAULT_BLOB = os.path.join(HERE, "..", "data", "pro_blob_stats.csv")
SINCE_2024_01_01 = 1704067200   # 与 Task 6/7 真实数据校验脚本同一个窗口起点

# 中文展示名，纯排版用，不影响 item_key 本身
ITEM_LABEL = {
    "kills": "击杀", "deaths": "死亡", "creep_score": "补刀(LH+D)", "gpm": "GPM",
    "tower_kills": "推塔", "roshan": "肉山", "teamfight": "参团率",
    "wards": "眼位", "camps_stacked": "叠野", "runes": "神符",
    "first_blood": "一血", "stuns": "眩晕时长", "smokes": "烟雾",
    "tormentor": "小boss", "courier": "信使击杀",
}

# P3 排名只用"更高=更好"的 14 项；deaths 越低越好，排进同一张"谁在前列更强"
# 的榜单会传递错误的价值判断，只在 P4 个人数据预测里作为普通预测量出现。
NOT_A_STRENGTH_RANKING = {"deaths"}

HEADLINE_ITEMS = ("gpm", "kills", "creep_score")     # Step 5 抽查用的头部指标
BOX_SCORE_ITEMS = ("gpm", "kills", "creep_score", "deaths")  # P4 摘要表用


def _fmt_ci(mean, lo, hi):
    return f"{mean:.2f} [{lo:.2f}–{hi:.2f}]"


def build_rates(csv_path=DEFAULT_CSV, blob_path=DEFAULT_BLOB, since_ts=SINCE_2024_01_01):
    """跑一遍 L3，返回 (pos, meta, item_keys, rates_by_item, n_rows_used)。"""
    pos = {aid: POSITIONS[t][p] for t, r in ROSTERS.items() for p, aid in r.items()}
    df = load_blob_joined_df(csv_path, blob_path, set(ACCOUNT_TO_TEAM), since_ts)

    items = available_items(include_blob=True)          # 15/18 可得项
    item_keys = [i["key"] for i in items]
    rates_by_item = {k: fit_rate_model(df, k, pos) for k in item_keys}

    meta = {aid: (ACCOUNT_TO_NAME.get(aid, str(aid)), ACCOUNT_TO_TEAM.get(aid, "?"))
            for aid in pos}
    return pos, meta, item_keys, rates_by_item, int(len(df))


def yatoro_spot_check(rankings_by_item, headline_items=HEADLINE_ITEMS):
    """Step 5 抽查 1：Yatoro（Team Spirit 1 号位）应在 1 号位榜前列。"""
    yatoro_id = ROSTERS["Team Spirit"]["Yatoro"]
    assert POSITIONS["Team Spirit"]["Yatoro"] == 1, "Yatoro 在花名册里不是 1 号位，先查 rosters.py"
    out = {}
    for item in headline_items:
        pos1 = [r for r in rankings_by_item[item] if r["position"] == 1]
        row = next((r for r in pos1 if r["account_id"] == yatoro_id), None)
        out[item] = {
            "found": row is not None,
            "rank": row["rank"] if row else None,
            "of_n_position1_players": len(pos1),
            "rate": row["rate"] if row else None,
            "lo": row["lo"] if row else None,
            "hi": row["hi"] if row else None,
            "n_games": row["n_games"] if row else None,
        }
    return out


def huligani_vs_liquid_widths(rankings_by_item, item_keys):
    """Step 5 抽查 2：HULIGANI（109 场量级）区间宽度应明显宽于 Team Liquid
    （1041 场量级）。逐项（除 deaths 外全部 14 项）都算，不挑一个好看的。"""

    def team_rows(item, team):
        rows = {r["account_id"]: r for r in rankings_by_item[item]}
        ids = list(ROSTERS[team].values())
        return [rows[a] for a in ids if a in rows]

    out = {}
    for item in item_keys:
        hul = team_rows(item, "HULIGANI")
        liq = team_rows(item, "Team Liquid")
        if not hul or not liq:
            continue
        hul_w = [r["hi"] - r["lo"] for r in hul]
        liq_w = [r["hi"] - r["lo"] for r in liq]
        out[item] = {
            "huligani_avg_width": sum(hul_w) / len(hul_w),
            "huligani_avg_n_games": sum(r["n_games"] for r in hul) / len(hul),
            "team_liquid_avg_width": sum(liq_w) / len(liq_w),
            "team_liquid_avg_n_games": sum(r["n_games"] for r in liq) / len(liq),
            "width_ratio_huligani_over_liquid":
                (sum(hul_w) / len(hul_w)) / (sum(liq_w) / len(liq_w))
                if sum(liq_w) > 0 else None,
        }
    return out


def build_report(csv_path=DEFAULT_CSV, blob_path=DEFAULT_BLOB, since_ts=SINCE_2024_01_01):
    pos, meta, item_keys, rates_by_item, n_rows_used = build_rates(csv_path, blob_path, since_ts)

    rankings_by_item = {item: rank_players(rates_by_item[item], meta, by_position=True)
                        for item in item_keys}
    predictions = predict_player_stats(rates_by_item, item_keys)

    sanity = {
        "yatoro_position1_headline_rank": yatoro_spot_check(rankings_by_item),
        "huligani_vs_team_liquid_interval_width": huligani_vs_liquid_widths(rankings_by_item, item_keys),
    }

    notes = [
        "P3/P4 都是 L3 后验的直接读出（00-DESIGN.md §3-L4），本报告不重新建模、"
        "不重新估计——rank_players/predict_player_stats 只做排序和区间打包。",

        "P3 排名只用 kills/creep_score/gpm/tower_kills/roshan/teamfight/wards/"
        "camps_stacked/runes/first_blood/stuns/smokes/tormentor/courier 共 14 项"
        "（deaths 越低越好，排进'排名=更强'的框架会传递错误的价值判断，"
        "只在 P4 个人数据预测里作为普通预测量出现，不含任何名次）。",

        "区间下界在 0 处截断：全部 15 项在物理意义上都不可能为负（计数或计数类"
        "比例），对称正态区间在均值本身接近 0 且样本量小时下界可能算出负数——"
        "已在 model/l4_players.py::_interval 里修正（详见该模块 docstring 与 "
        "task-8-report.md）。上界不做类似处理，仍可能出现，是已知限制。",

        "数据窗口与 Task 6/7 一致：since=2024-01-01 起、80 名花名册选手、"
        f"过滤后 {n_rows_used} 条选手-比赛行。smokes/tormentor/courier 按 "
        "match_id+account_id 左连 data/pro_blob_stats.csv（06-fantasy-rules.md §F.5）。",

        "蓝色徽记池 Watcher/Lotus 完全没有字段、madstone 只有语义不同的代理量——"
        "这三项不在 available_items() 范围内，P3/P4 都不覆盖（跟 Task 7 P1 报告"
        "同一条已知缺口，见 00-DESIGN.md R4）。",

        "as-of 对齐：号位来自 model/rosters.py 的花名册（策展数据，按 ROSTERS "
        "里每队选手的书写顺序赋 1-5 号位），选手的历史比赛不区分当时所属队伍——"
        "只要 account_id 本身在窗口内有比赛就计入，转会不影响个人数据统计"
        "（跟 L1 队伍层的 as-of join 是两回事，见 00-PLAN.md Task 6 Step 5 相关讨论）。",

        "重要澄清（task-8-report.md 有完整 repro）：下方检查 2 的 HULIGANI/Team "
        "Liquid 区间宽度比值实测在 1.17x-1.56x 之间，量级上明显小于 task-8-brief.md "
        "引用的'109 场 vs 1041 场'（约 9.5x）——这不是 se 传递出错，是两个不同的"
        "样本量：00-DESIGN.md §9.4 的 109/1041 是 L1 的**队伍级**样本（按 team_id、"
        "经 L0 实体对齐、2022-01-01 起），这里的 n_games 是 L3 的**选手级**样本"
        "（按 account_id、2024-01-01 起，不做实体对齐——account_id 本身跨转会稳定，"
        "不需要对齐；一名选手可能在多支队伍打过球，个人账号历史天然比某一个 "
        "team_id 身份的历史长）。实测 HULIGANI 5 名选手 2024 年以来场次均值 464.6，"
        "并不小，只是持续小于 Team Liquid 的 769.2；逐位置核验：n_games 差距最小的"
        "5 号位（659 vs 730）区间宽度差距也最小（2.81 vs 2.70），n_games 差距最大的"
        "4 号位（304 vs 787）区间宽度差距也最大（4.08 vs 2.52）——se 与 n_games 严格"
        "同向变化，排除了'se 没被正确传递'这个假设。",
    ]

    return {
        "notes": notes,
        "coverage": {
            "available_items": item_keys,
            "ranked_items": [k for k in item_keys if k not in NOT_A_STRENGTH_RANKING],
            "not_a_strength_ranking": sorted(NOT_A_STRENGTH_RANKING),
            "n_players_with_any_rate": len({a for item in item_keys for a in rates_by_item[item]}),
        },
        "sanity_checks": sanity,
        "rankings_by_item": {item: rankings_by_item[item] for item in item_keys},
        "predictions": {str(acct): {item: list(v) for item, v in items_.items()}
                        for acct, items_ in predictions.items()},
        "since_ts": since_ts,
        "n_rows_used": n_rows_used,
    }


def _render_markdown(report):
    pos1_n = report["coverage"].get("n_players_with_any_rate", 80)
    lines = []
    lines.append("# L4-P3/P4：选手实力排名与个人数据预测\n")
    lines.append(f"数据窗口起点 since_ts={report['since_ts']}，"
                 f"过滤后 {report['n_rows_used']} 条选手-比赛行，"
                 f"覆盖 {pos1_n} 名花名册选手。\n")

    lines.append("## 方法论与已知限制\n")
    for n in report["notes"]:
        lines.append(f"- {n}")
    lines.append("")

    lines.append("## Step 5 健全性检查\n")

    lines.append("### 检查 1：Yatoro（Team Spirit，1 号位）在 1 号位榜的位置\n")
    lines.append("| 计分项 | 名次 | 1号位共几人 | 场均值 | 95% 区间 | 样本局数 |")
    lines.append("|---|---|---|---|---|---|")
    for item, v in report["sanity_checks"]["yatoro_position1_headline_rank"].items():
        label = ITEM_LABEL.get(item, item)
        if not v["found"]:
            lines.append(f"| {label} | 未找到 | {v['of_n_position1_players']} | - | - | - |")
            continue
        lines.append(f"| {label} | {v['rank']} | {v['of_n_position1_players']} | "
                     f"{v['rate']:.2f} | [{v['lo']:.2f}–{v['hi']:.2f}] | {v['n_games']} |")
    lines.append("")

    lines.append("### 检查 2：HULIGANI（小样本）vs Team Liquid（大样本）区间宽度\n")
    lines.append("HULIGANI 选手的 as-of 样本量小于 Team Liquid，逐项区间宽度均值应明显更宽——"
                 "如果比值接近 1，说明 se 没有正确从 L3 传递到这一层。\n")
    lines.append("**比值量级说明**：下表比值在 1.17x-1.56x 之间，明显小于 brief 引用的"
                 "队伍级 109 vs 1041 场（≈9.5x）——这是预期之内的，不是 bug。109/1041 是 "
                 "00-DESIGN.md §9.4 的 **L1 队伍级**样本（按 team_id、经实体对齐、"
                 "2022-01-01 起）；下表是 **L3 选手级**样本（按 account_id、"
                 "2024-01-01 起，个人账号历史天然比某一个 team_id 身份的历史长）。"
                 "详见上方'方法论与已知限制'最后一条、task-8-report.md 的完整 repro。\n")
    lines.append("| 计分项 | HULIGANI 均宽 | HULIGANI 均场次 | Team Liquid 均宽 | "
                 "Team Liquid 均场次 | 宽度比(HULIGANI/Liquid) |")
    lines.append("|---|---|---|---|---|---|")
    for item, v in report["sanity_checks"]["huligani_vs_team_liquid_interval_width"].items():
        label = ITEM_LABEL.get(item, item)
        ratio = v["width_ratio_huligani_over_liquid"]
        ratio_s = f"{ratio:.2f}x" if ratio is not None else "-"
        lines.append(f"| {label} | {v['huligani_avg_width']:.2f} | "
                     f"{v['huligani_avg_n_games']:.1f} | {v['team_liquid_avg_width']:.2f} | "
                     f"{v['team_liquid_avg_n_games']:.1f} | {ratio_s} |")
    lines.append("")

    lines.append("## P3 选手实力排名（分位置，按 GPM 排序，附击杀/补刀对照）\n")
    for p in range(1, 6):
        lines.append(f"### {p} 号位\n")
        lines.append("| 排名(GPM) | 选手 | 战队 | GPM | 击杀 | 补刀(LH+D) | 样本局数 |")
        lines.append("|---|---|---|---|---|---|---|")
        gpm_rows = [r for r in report["rankings_by_item"]["gpm"] if r["position"] == p]
        kills_by_acct = {r["account_id"]: r for r in report["rankings_by_item"]["kills"]}
        cs_by_acct = {r["account_id"]: r for r in report["rankings_by_item"]["creep_score"]}
        for r in gpm_rows:
            k = kills_by_acct.get(r["account_id"])
            c = cs_by_acct.get(r["account_id"])
            k_s = _fmt_ci(k["rate"], k["lo"], k["hi"]) if k else "-"
            c_s = _fmt_ci(c["rate"], c["lo"], c["hi"]) if c else "-"
            lines.append(f"| {r['rank']} | {r['name']} | {r['team']} | "
                         f"{_fmt_ci(r['rate'], r['lo'], r['hi'])} | {k_s} | {c_s} | {r['n_games']} |")
        lines.append("")

    lines.append("## P4 个人数据预测（box score 摘要：GPM / 击杀 / 补刀 / 死亡）\n")
    lines.append("完整 15 项 × 80 人的预测见同名 `.json`；这里只摘要 4 项经典个人数据"
                 "（呼应设计文档 §2.2 P4 的 'KDA/GPM/LH 等' 提法——本项目没有 assists 字段，"
                 "不产出真正的 KDA 比值，用 kills/deaths 分列代替）。\n")
    for p in range(1, 6):
        lines.append(f"### {p} 号位\n")
        lines.append("| 选手 | 战队 | GPM | 击杀 | 补刀(LH+D) | 死亡 | 样本局数 |")
        lines.append("|---|---|---|---|---|---|---|")
        rows = [r for r in report["rankings_by_item"]["gpm"] if r["position"] == p]
        deaths_by_acct = {r["account_id"]: r for r in report["rankings_by_item"].get("deaths", [])}
        # deaths 不参与"排名"表，但要用同一份 rank_players 输出取 rate/lo/hi——
        # 这里额外单独跑一遍 deaths 的 by_position 排名只是为了拿到 lo/hi，
        # 展示时特意不显示它的 rank 列（deaths 越低越好，不该暗示"排名靠前=更强"）。
        kills_by_acct = {r["account_id"]: r for r in report["rankings_by_item"]["kills"]}
        cs_by_acct = {r["account_id"]: r for r in report["rankings_by_item"]["creep_score"]}
        for r in rows:
            k = kills_by_acct.get(r["account_id"])
            c = cs_by_acct.get(r["account_id"])
            d = deaths_by_acct.get(r["account_id"])
            k_s = _fmt_ci(k["rate"], k["lo"], k["hi"]) if k else "-"
            c_s = _fmt_ci(c["rate"], c["lo"], c["hi"]) if c else "-"
            d_s = _fmt_ci(d["rate"], d["lo"], d["hi"]) if d else "-"
            lines.append(f"| {r['name']} | {r['team']} | "
                         f"{_fmt_ci(r['rate'], r['lo'], r['hi'])} | {k_s} | {c_s} | {d_s} | {r['n_games']} |")
        lines.append("")

    lines.append("## 完整数据\n")
    lines.append("全部 15 个可得计分项 × 80 名选手的完整排名（`rankings_by_item`）与"
                 "个人数据预测（`predictions`，值为 [均值, lo, hi]，6 位小数）见同名 `.json`。\n")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "reports", "p3_p4_players.md"))
    ap.add_argument("--json-out", default=None,
                    help="默认与 --out 同名、扩展名换成 .json")
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--blob", default=DEFAULT_BLOB)
    ap.add_argument("--since-ts", type=int, default=SINCE_2024_01_01)
    args = ap.parse_args()

    report = build_report(csv_path=args.csv, blob_path=args.blob, since_ts=args.since_ts)

    md = _render_markdown(report)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(md)

    json_out = args.json_out
    if json_out is None:
        base, _ = os.path.splitext(args.out)
        json_out = base + ".json"
    with open(json_out, "w") as f:
        json.dump(_round(report), f, indent=1, ensure_ascii=False)

    yatoro = report["sanity_checks"]["yatoro_position1_headline_rank"]
    print(f"选手覆盖：{report['coverage']['n_players_with_any_rate']} 名，"
          f"{len(report['coverage']['available_items'])} 项可得计分项")
    print(f"已写入 {args.out}")
    print(f"已写入 {json_out}")
    print()
    print("[Step 5 抽查 1] Yatoro 1号位排名:")
    for item, v in yatoro.items():
        print(f"  {item}: rank={v['rank']}/{v['of_n_position1_players']} "
              f"rate={v['rate']} n_games={v['n_games']}")
    print()
    print("[Step 5 抽查 2] HULIGANI vs Team Liquid 区间宽度比值（若接近 1 需停下来查 se 传递）:")
    for item, v in report["sanity_checks"]["huligani_vs_team_liquid_interval_width"].items():
        print(f"  {item}: HULIGANI 均宽={v['huligani_avg_width']:.3f} "
              f"(n_games均={v['huligani_avg_n_games']:.1f}) vs "
              f"Team Liquid 均宽={v['team_liquid_avg_width']:.3f} "
              f"(n_games均={v['team_liquid_avg_n_games']:.1f}) "
              f"比值={v['width_ratio_huligani_over_liquid']:.2f}x")


if __name__ == "__main__":
    main()
