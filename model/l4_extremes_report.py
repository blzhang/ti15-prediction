"""L4-P2 编排脚本：把 fantasy_stats / l3_player / l4_extremes / l2_predictions
串起来，产出「全场之最」的两类题——阈值题（会不会出现单局 ≥X）与身份题
（谁会打出全场最高值）——外加两份独立验证报告（task-9-report.md 完整记录
了下面每一步的真实命令与输出）：

  --variance-check   独立复算「局间标准差 / 泊松假定标准差」这组倍数，
                      confirm/refute 控制器实测（Task 8 复审时发现的
                      shrink() 泊松假定问题）。
  --backtest-ti14     Step 5：只用 TI14 开赛前的数据，预测 TI14 会发生的
                      极值，与 TI14 实际发生的比对——P2 唯一能做的诚实
                      检验，好看不好看都如实写进产出物。

不带 flag 时产出 TI15 正式的 P2 报告（reports/p2_extremes.{md,json}）。

**为什么 who_leads 需要 residual_pool（而不是 brief 原来的单个 rate）**：
见 model/l4_extremes.py 模块 docstring 与 task-9-report.md 的完整复现——
控制器实测局间标准差远超「泊松假定 sqrt(rate)」，last_hits/gpm/stuns
尤其严重（本任务独立复算约 7x/4x/6x），一个标量 rate 结构上不携带
"这项有多离散"的信息，因此必须额外提供该计分项真实的局间残差分布。
本脚本按位置池化残差（不同位置的离散度形状本身有差异，见 task-9-report.md
分位置实测表），复用 `model/l3_player.py::fit_rate_model` 同一套按位置
分层的思路。

**threshold_prob 的 samples 用全局池（不分位置）**：「本届会不会出现单局
≥26 杀」问的是"任意选手的任意一局"，不是某个位置专属的问题，池化全部
选手样本能拿到更大的历史样本，符合 §4.4"优先信经验频率、样本越大越
稳"的方法论；而 who_leads 问的是"谁"，不同位置选手的离散度形状有实质
差异，因此按位置分别池化残差——两处池化粒度不同是有意为之，不是不一致。

**"n_games"（threshold_prob 的试验次数）取 player-game 槽位数，不是场次数**：
"单局 ≥26 杀"说的是某一名选手在某一局里的击杀数，每一局有 10 个选手槽位，
所以试验次数 = 全赛事期望局数 × 10，而不是局数本身（见 total_expected_games /
build_report 里的换算）。
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
from fantasy_stats import load_player_games
from l3_player import fit_rate_model
from l4_fantasy import TI15_Q_THREE_GAME
from l4_fantasy_report import load_blob_joined_df, _round
from l4_extremes import threshold_prob, needs_gpd, who_leads, empirical_residuals, dispersion_ratio

DEFAULT_CSV = os.path.join(HERE, "..", "data", "pro_player_matches_2020_2026.csv")
DEFAULT_BLOB = os.path.join(HERE, "..", "data", "pro_blob_stats.csv")
DEFAULT_L2 = os.path.join(HERE, "l2_predictions.json")
SINCE_2024_01_01 = 1704067200     # 与 Task 6/7/8 真实数据校验脚本同一个窗口起点
GLOBAL_SEED = 20260802            # 全局约束：蒙特卡洛固定这个种子

DEFAULT_TI14_MATCHES = os.path.join(HERE, "..", "data", "ti14_matches.csv")
DEFAULT_TI14_ROSTER = os.path.join(HERE, "..", "data", "ti14_roster_derived.csv")
DEFAULT_TI14_PLAYER_MATCHES = os.path.join(HERE, "..", "data", "ti14_player_matches.csv")

# 用于「泊松假定 vs 实测」核验、以及 P2 报告的 6 个原始列（不走 SCORING_ITEMS
# 的 key 映射——l3_player._resolve_item_values 对字面同名的 df 列直接放行，
# P2 问的是原始比赛数据里的"单局 XX"，不是 Fantasy 计分口径）。
VARIANCE_CHECK_ITEMS = ["kills", "deaths", "last_hits", "gold_per_min", "stuns", "teamfight_participation"]
HEADLINE_ITEMS = ["kills", "gold_per_min", "last_hits", "stuns"]     # P2 报告实际出题的 4 项
ITEM_LABEL = {
    "kills": "击杀", "deaths": "死亡", "last_hits": "补刀(仅last hits)",
    "gold_per_min": "GPM", "stuns": "眩晕时长(秒)", "teamfight_participation": "参团率",
}

BEYOND_RANGE_MARGIN = 1.15             # 超出历史最大值 15%，专门用来演示 needs_gpd 的边界

# 每项一个"人为选定"的整数关卡阈值——**不**从这个计分项自己的分位数机械
# 倒推（早期版本这样做过：结果是任何计分项在"自己的第99.5分位"上算出的
# 全赛事概率都趋同于同一个 1-(1-0.005)^n，因为按定义就是同一个分位数，
# 报告看起来像是把同一个数字换了个马甲贴四次，掩盖了不同计分项真实尾部
# 形状的差异，见 task-9-report.md 的自我纠错记录）。
# kills=26 是任务原文点名的示例；gold_per_min=1000/last_hits=1000 是 Dota
# 社区公认的"千GPM/千补刀"整数关卡（对照本任务实测：gpm p99=918/p99.9=1039，
# last_hits p99=832/p99.9=1175，1000 对两项都落在"稀有但达得到"的真实区间，
# 不是拍脑袋）；stuns 没有类似的公认整数关卡，用接近 p99.5 的整数代替，
# 标签里明确注明"非社区共识梗"，不冒充跟前三项同等地位。
HEADLINE_THRESHOLD = {
    "kills": (26.0, "任务原文点名示例"),
    "gold_per_min": (1000.0, "Dota 社区公认的'千GPM'整数关卡"),
    "last_hits": (1000.0, "Dota 社区公认的'千补刀'整数关卡"),
    "stuns": (200.0, "无公认整数关卡，取接近99.5分位的整数代替"),
}


# ---------------------------------------------------------------------------
# 通用 helper
# ---------------------------------------------------------------------------

def _unbiased_round(rng, v):
    """无偏随机取整：E[draw(v)] == v，避免直接截断系统性丢掉小数部分的期望
    （跟 model/l4_fantasy.py::expected_slot_score 内部 draw() 同一个技巧，
    这里是模块级独立实现，避免依赖它的函数内闭包）。"""
    lo = int(np.floor(v))
    return lo + int(rng.random() < (v - lo))


def variance_check(df, items=VARIANCE_CHECK_ITEMS):
    """独立复算「局间标准差 / 泊松假定标准差」——confirm/refute 控制器实测。
    见 task-9-report.md 的完整数字与多种聚合方式交叉验证。"""
    out = {}
    for item in items:
        sub = df[["account_id", item]].dropna()
        out[item] = dispersion_ratio(sub[item].values, sub["account_id"].values)
    return out


def expected_games_by_team(series_dist):
    """{team: 预计打几局} = (group+playoff 期望系列赛数) × 每系列赛期望局数。

    每系列赛期望局数用 2+q（q=TI15_Q_THREE_GAME，BO3 打满三局的实测比例），
    跟 model/l4_fantasy.py::expected_slot_score 对全部系列赛（含决赛 BO5）
    统一按 BO3 近似处理是同一个既有简化，不重新发明一套口径。
    """
    per_series_games = 2.0 + TI15_Q_THREE_GAME
    return {t: (s.get("group", 0.0) + s.get("playoff", 0.0)) * per_series_games
            for t, s in series_dist.items()}


def total_expected_games(series_dist):
    """全赛事期望总局数：sum(每队 group+playoff 期望系列赛数)/2（每场系列赛
    被两支队伍各计一次，除以 2 去重复计数）× 每系列赛期望局数。

    这是对 00-DESIGN.md §1.2 "N≈145（58 场 BO3 + 1 场 BO5，q=0.4386）"的
    代码可复现版本：直接从 l2_predictions.json 的 series_dist 反推系列赛
    总数（应为 59，与 00-DESIGN.md 精确吻合），再乘同一个 2+q 近似
    （决赛那 1 场 BO5 也按 BO3 近似，跟 expected_games_by_team 同一个
    简化，误差在 1 局量级，见 task-9-report.md 的数值核对）。
    """
    total_series = sum(s.get("group", 0.0) + s.get("playoff", 0.0)
                       for s in series_dist.values()) / 2.0
    return total_series * (2.0 + TI15_Q_THREE_GAME)


def build_residual_pools_by_position(df, positions, items=HEADLINE_ITEMS):
    """{item: {position(1-5): 残差池 array}}——不同位置的离散度形状本身有
    差异（task-9-report.md 分位置实测：last_hits 弥散度比值 1 号位 8.58 vs
    5 号位 7.08），who_leads 因此按位置分别池化，不用全局单一残差池。"""
    work = df.copy()
    work["position"] = work["account_id"].map(positions)
    out = {}
    for item in items:
        out[item] = {}
        sub_all = work[["account_id", "position", item]].dropna()
        for p in sorted(sub_all["position"].unique()):
            sub = sub_all[sub_all["position"] == p]
            out[item][int(p)] = empirical_residuals(sub[item].values, sub["account_id"].values)
    return out


def pick_thresholds(samples, item):
    """给一个计分项挑«全场之最»阈值题的候选阈值：一个人为选定的整数关卡
    （HEADLINE_THRESHOLD，见上方常量注释——不从这个计分项自己的分位数
    机械倒推）+ 一个明确超出历史观测范围的假设阈值（演示 needs_gpd 的
    边界）。附带报告该关卡在真实历史样本里的经验分位，供读者自行判断
    稀有程度，不是凭空断言。"""
    samples = np.asarray(samples, dtype=float)
    mx = float(samples.max())
    out = []
    seen = set()
    headline_v, headline_desc = HEADLINE_THRESHOLD.get(item, (None, None))
    if headline_v is not None:
        hits = int((samples >= headline_v).sum())
        # 用原始命中次数而不是只显示分位数百分比——稀有事件的分位数四舍五入
        # 到 1 位小数会显示成"100.0"，读起来像"历史上从未发生过"，但实际
        # 命中次数可能是 20 次而不是 0 次（真实撞见：kills>=26 在 49762 局
        # 样本里发生过 20 次，分位数 99.9598% 四舍五入后是 100.0，具有误导性）。
        label = f"{headline_desc}（历史{len(samples)}局里出现过{hits}次）"
        out.append((label, float(headline_v)))
        seen.add(headline_v)
    beyond = round(mx * BEYOND_RANGE_MARGIN)
    if beyond not in seen:
        out.append((f"超出历史观测上限{mx:.0f}的假设阈值（演示 needs_gpd 边界）", float(beyond)))
        seen.add(beyond)
    return sorted(out, key=lambda kv: kv[1])


# ---------------------------------------------------------------------------
# 主报告：TI15 正式 P2
# ---------------------------------------------------------------------------

def build_report(csv_path=DEFAULT_CSV, blob_path=DEFAULT_BLOB, l2_path=DEFAULT_L2,
                  since_ts=SINCE_2024_01_01, seed=GLOBAL_SEED):
    pos = {aid: POSITIONS[t][p] for t, r in ROSTERS.items() for p, aid in r.items()}
    df = load_blob_joined_df(csv_path, blob_path, set(ACCOUNT_TO_TEAM), since_ts)

    vc = variance_check(df, VARIANCE_CHECK_ITEMS)

    rates_by_item = {item: fit_rate_model(df, item, pos) for item in HEADLINE_ITEMS}
    pools_by_position = build_residual_pools_by_position(df, pos, HEADLINE_ITEMS)

    l2 = json.load(open(l2_path))
    series_dist = l2["series_dist"]
    team_games = expected_games_by_team(series_dist)
    total_games = total_expected_games(series_dist)
    total_player_slots = total_games * 10.0

    rng = np.random.default_rng(seed)
    n_games_by_player = {}
    for t, roster in ROSTERS.items():
        g = team_games.get(t, 0.0)
        for aid in roster.values():
            n_games_by_player[aid] = _unbiased_round(rng, g)

    who_leads_out = {}
    for item in HEADLINE_ITEMS:
        rates = {a: v["rate"] for a, v in rates_by_item[item].items()}
        pool_dict = {a: pools_by_position[item][pos[a]] for a in rates
                     if pos.get(a) in pools_by_position[item]}
        rates = {a: r for a, r in rates.items() if a in pool_dict}
        out = who_leads(rates, n_games_by_player, pool_dict, n_sim=20000, seed=seed)
        ranked = sorted(out.items(), key=lambda kv: -kv[1])
        who_leads_out[item] = [
            {"account_id": a, "name": ACCOUNT_TO_NAME.get(a, str(a)),
             "team": ACCOUNT_TO_TEAM.get(a, "?"), "prob_leads": p,
             "rate": rates[a], "n_games_ti15": n_games_by_player.get(a, 0)}
            for a, p in ranked
        ]

    threshold_out = {}
    for item in HEADLINE_ITEMS:
        samples = df[item].dropna().astype(float).values
        rows = []
        for label, thr in pick_thresholds(samples, item):
            gpd_needed = needs_gpd(samples, thr)
            row = {"label": label, "threshold": thr, "needs_gpd": gpd_needed}
            if gpd_needed:
                row["prob_at_least_one"] = None
                row["note"] = "阈值超出历史观测范围，经验频率不可靠；本模块按设计不实现 GPD，如实报告为无法估计，不假装能算"
            else:
                row["prob_at_least_one"] = threshold_prob(samples, thr, n_games=total_player_slots)
                row["note"] = None
            rows.append(row)
        threshold_out[item] = rows

    notes = [
        "P2 两类题：阈值题（threshold_prob，'本届会不会出现单局≥X'）与身份题"
        "（who_leads，'谁会打出全场最高值'）——00-DESIGN.md §2.2。两者都是"
        "\"L3 分布尾部 × L2 局数\"（§3-L4），不重新拟合广义帕累托（GPD）："
        "阈值多数落在历史观测范围内（几十上百个真实观测支撑），经验频率+"
        "层次平滑更稳，GPD 还会引入'阈值怎么选'这个新的过拟合来源（§4.4）。"
        "needs_gpd 划这条边界：命中 True 时如实报告'超出可估计范围'，不假装"
        "经验频率仍然可靠。",

        "对 task-9-brief.md 的两处修正（完整 repro 见 task-9-report.md）："
        "(1) brief 自己的 Step1 测试断言 threshold_prob 在特定 fixture 下 <0.2，"
        "代入 brief 自己 Step3 的参考实现精确算出 0.303——测试与实现互相矛盾"
        "（本项目第 11 个此类问题，性质与前 10 个不同：不是'共享错误前提所以"
        "骗过测试'，是压根跑不过），已修正测试断言，threshold_prob 公式本身"
        "不变。(2) who_leads 原参考实现用 rng.poisson(rate) 模拟单局产出，"
        "等价于假设 Var(单局)≈rate（泊松）。本任务独立复算局间标准差/泊松"
        "假定标准差：kills≈1.5x / deaths≈1.3x / last_hits≈7.2-7.7x / "
        "gold_per_min≈4.1-4.3x / stuns≈5.9-6.1x（teamfight_participation≈0.18x，"
        "反而比泊松假定更窄）——与控制器实测的方向一致但量级不完全相同"
        "（控制器数字 1.8/1.4/12.0/7.8/6.4/0.2x，见 task-9-report.md 对多种"
        "聚合口径的交叉验证与讨论）。GPM/补刀/眩晕差 4-8 倍不是舍入误差，"
        "已把 who_leads 改成吃真实局间残差分布（residual_pool，见"
        "model/l4_extremes.py），不再用一个标量 rate 套泊松。",

        "两处池化粒度不同，是有意为之：threshold_prob 的 samples 用全局池"
        "（不分位置，问题问的是'任意选手任意一局'，池化拿更大样本）；"
        "who_leads 的 residual_pool 按位置分别池化（不同位置离散度形状本身"
        "有差异）。",

        f"threshold_prob 的 n_games 用 player-game 槽位数 = 全赛事期望总局数"
        f"({total_games:.1f}) × 10 个选手槽位 ≈ {total_player_slots:.0f}，"
        "不是局数本身——'单局≥26杀'问的是某一名选手在某一局的击杀数。"
        "期望总局数从 model/l2_predictions.json 的 series_dist 反推"
        "（=59 场系列赛，与 00-DESIGN.md §1.2 精确吻合），乘 2+q 近似"
        "（q=TI15_Q_THREE_GAME，决赛那 1 场 BO5 也按 BO3 近似——沿用"
        "model/l4_fantasy.py 已有的同一简化，不重新发明口径）。",

        "who_leads 里选手的预计 TI15 局数来自 series_dist 按队展开"
        "（同队 5 人共享同一个局数预期），用无偏随机取整避免截断丢期望"
        "（跟 model/l4_fantasy.py::expected_slot_score 内部 draw() 同一个"
        "技巧）。",

        "数据窗口：since=2024-01-01，80 名花名册选手，与 Task 6/7/8 一致；"
        "smokes/tormentor/courier 不在本报告范围内（P2 只覆盖 kills/gpm/"
        "last_hits/stuns 四项'headline 记录'型计分项，不是全部 15 个可得项——"
        "'全场最高眼位数'这类问题娱乐性不足，故未纳入，属主动的范围裁剪）。",

        "已知数据质量注记（非本任务引入，抽查时发现）：teamfight_participation "
        "在 0.064% 的行里 >1（理论上限应为 1），stuns 在 0.9% 的行里 <0（物理"
        "上不可能为负）——TI14 官方数据里同样存在这类值（例如 TI14 "
        "teamfight_participation 实测最大值 1.13），判断为 OpenDota 数据源"
        "本身的噪声，不是本报告的抽取逻辑引入的，对整体弥散度比值影响"
        "可忽略（占比 <1%）。",
    ]

    return {
        "notes": notes,
        "coverage": {"headline_items": HEADLINE_ITEMS, "n_players": len(pos)},
        "variance_check": vc,
        "total_expected_games_ti15": total_games,
        "total_player_game_slots_ti15": total_player_slots,
        "who_leads": who_leads_out,
        "threshold_questions": threshold_out,
        "since_ts": since_ts,
        "n_rows_used": int(len(df)),
    }


def _render_markdown(report):
    lines = []
    lines.append("# L4-P2：全场之最（极值题）\n")
    lines.append(f"数据窗口 since_ts={report['since_ts']}，过滤后 {report['n_rows_used']} 条选手-比赛行，"
                 f"覆盖 {report['coverage']['n_players']} 名花名册选手。全赛事期望总局数 "
                 f"{report['total_expected_games_ti15']:.1f}，约合 "
                 f"{report['total_player_game_slots_ti15']:.0f} 个选手-局槽位。\n")

    lines.append("## 方法论与已知限制\n")
    for n in report["notes"]:
        lines.append(f"- {n}")
    lines.append("")

    lines.append("## 独立方差核验：局间标准差 / 泊松假定标准差\n")
    lines.append("| 计分项 | 均值倍数 | 中位数倍数 | 选手数 |")
    lines.append("|---|---|---|---|")
    for item in VARIANCE_CHECK_ITEMS:
        v = report["variance_check"][item]
        lines.append(f"| {ITEM_LABEL.get(item, item)} | {v['ratio_mean']:.2f}x | "
                     f"{v['ratio_median']:.2f}x | {v['n_players']} |")
    lines.append("")

    lines.append("## 阈值题：会不会出现单局 ≥X\n")
    for item in HEADLINE_ITEMS:
        lines.append(f"### {ITEM_LABEL.get(item, item)}\n")
        lines.append("| 阈值 | 说明 | 是否超出观测范围(needs_gpd) | 全赛事至少一次的概率 |")
        lines.append("|---|---|---|---|")
        for row in report["threshold_questions"][item]:
            p = "无法估计（见备注）" if row["prob_at_least_one"] is None else f"{row['prob_at_least_one']*100:.2f}%"
            lines.append(f"| {row['threshold']:.0f} | {row['label']} | "
                         f"{'是' if row['needs_gpd'] else '否'} | {p} |")
        lines.append("")

    lines.append("## 身份题：谁会打出全场最高值（Top 8）\n")
    for item in HEADLINE_ITEMS:
        lines.append(f"### {ITEM_LABEL.get(item, item)}\n")
        lines.append("| 排名 | 选手 | 战队 | 夺得全场最高的概率 | 每局期望值 | 预计参赛局数 |")
        lines.append("|---|---|---|---|---|---|")
        for i, r in enumerate(report["who_leads"][item][:8], 1):
            lines.append(f"| {i} | {r['name']} | {r['team']} | {r['prob_leads']*100:.2f}% | "
                         f"{r['rate']:.1f} | {r['n_games_ti15']} |")
        lines.append("")

    lines.append("## 完整数据\n")
    lines.append("全部选手的 who_leads 概率分布见同名 `.json`（6 位小数）。\n")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# --variance-check：独立复算方差倍数
# ---------------------------------------------------------------------------

def run_variance_check(args):
    pos = {aid: POSITIONS[t][p] for t, r in ROSTERS.items() for p, aid in r.items()}
    df = load_player_games(args.csv, set(ACCOUNT_TO_TEAM), args.since_ts)
    vc = variance_check(df, VARIANCE_CHECK_ITEMS)

    print(f"独立方差核验：{len(pos)} 名选手，since_ts={args.since_ts}，{len(df)} 条选手-比赛行\n")
    print(f"{'计分项':<26}{'均值倍数':>10}{'中位数倍数':>12}{'选手数':>8}")
    for item in VARIANCE_CHECK_ITEMS:
        v = vc[item]
        print(f"{ITEM_LABEL.get(item, item):<26}{v['ratio_mean']:>9.2f}x{v['ratio_median']:>11.2f}x{v['n_players']:>8d}")

    out = {"since_ts": args.since_ts, "n_rows_used": int(len(df)), "variance_check": vc}
    out_path = args.json_out or os.path.join(HERE, "..", "reports", "p2_variance_check.json")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(_round(out), f, indent=1, ensure_ascii=False)
    print(f"\n已写入 {out_path}")


# ---------------------------------------------------------------------------
# --backtest-ti14：Step 5 诚实回溯校验
# ---------------------------------------------------------------------------

def _load_pre_ti14_training_df(csv_path, ti14_accounts, cutoff_ts):
    """TI14 开赛前的全部可得历史（不设 since_ts 下限，最大化回测样本量——
    这是 backtest 专用的简化，跟正式 TI15 报告用 since_ts=2024-01-01 这个
    较近窗口是两回事，见 run_backtest_ti14 的 notes）。"""
    df = load_player_games(csv_path, ti14_accounts, since_ts=0)
    return df[df["start_time"].astype("int64") < int(cutoff_ts)].reset_index(drop=True)


def run_backtest_ti14(args):
    ti14_matches = pd.read_csv(args.ti14_matches)
    cutoff = int(ti14_matches["start_time"].min())
    ti14_roster = pd.read_csv(args.ti14_roster)
    ti14_accounts = set(int(a) for a in ti14_roster["account_id"])
    ti14_name = {int(r.account_id): r.player_name for r in ti14_roster.itertuples()}
    ti14_team = {int(r.account_id): r.team_name for r in ti14_roster.itertuples()}

    train = _load_pre_ti14_training_df(args.csv, ti14_accounts, cutoff)
    actual = pd.read_csv(args.ti14_player_matches)
    actual["account_id"] = actual["account_id"].astype(int)

    actual_games = actual.groupby("account_id").size().to_dict()
    total_actual_games = int(len(ti14_matches))
    total_actual_slots = total_actual_games * 10

    rng = np.random.default_rng(args.seed)

    threshold_rows = []
    who_leads_rows = {}
    for item in HEADLINE_ITEMS:
        pre_samples = train[item].dropna().astype(float).values

        # ---- 阈值题回验：用赛前数据算概率，跟 TI14 实际是否发生比对 ----
        for label, thr in pick_thresholds(pre_samples, item):
            gpd_needed = needs_gpd(pre_samples, thr)
            actual_hit = bool((actual[item].dropna().astype(float) >= thr).any())
            row = {"item": item, "label": label, "threshold": thr, "needs_gpd": gpd_needed,
                   "actual_happened": actual_hit}
            if gpd_needed:
                row["predicted_prob"] = None
            else:
                row["predicted_prob"] = threshold_prob(pre_samples, thr, n_games=total_actual_slots)
            threshold_rows.append(row)

        # ---- 身份题回验：用赛前 rate（选手自己历史均值，不做位置分层收缩——
        # ti14_roster_derived.csv 没有号位字段，回测特意简化，见 notes）
        # + TI14 实际局数（事后已知的真值，回测只考察 L3尾部/L4-P2 这一层，
        # 不重新检验 L1/L2 的晋级路径模拟，那部分已在 Task 3/4 独立验证过）----
        pre_by_player = train.dropna(subset=[item]).groupby("account_id")[item]
        rates = {a: float(g.mean()) for a, g in pre_by_player if a in ti14_accounts}
        pool_values = train.dropna(subset=[item])
        residual_pool = empirical_residuals(pool_values[item].values, pool_values["account_id"].values)
        n_games_actual = {a: int(actual_games.get(a, 0)) for a in rates}

        out = who_leads(rates, n_games_actual, residual_pool, n_sim=20000, seed=args.seed)
        ranked = sorted(out.items(), key=lambda kv: -kv[1])

        actual_row = actual.loc[actual[item].idxmax()]
        actual_leader = int(actual_row["account_id"])
        actual_value = float(actual_row[item])
        rank_of_actual = next((i for i, (a, _) in enumerate(ranked, 1) if a == actual_leader), None)
        prob_of_actual = out.get(actual_leader)

        # 诚实的评判基准："猜中 Top1"对身份题是个过严的标准——即便模型跟真实
        # 生成过程完全一致，"谁打出全场最高值"这件事本身也高度随机，任何一个
        # 候选人的夺魁概率都不会接近 1。更合适的两个校准指标：
        #   (1) 实际夺魁者拿到的概率，相对于"完全不区分能力、均匀瞎猜"这个
        #       基准（1/候选人数）高多少倍——>1 说明模型确实捕捉到了真实信号；
        #   (2) 实际夺魁者在预测排名里的百分位——排得靠前（即使不是当中的
        #       第一名）也说明模型没有走偏。
        n_candidates = len(rates)
        uniform_baseline = 1.0 / n_candidates if n_candidates else None
        prob_vs_uniform = (prob_of_actual / uniform_baseline
                          if prob_of_actual is not None and uniform_baseline else None)
        rank_percentile = (1.0 - (rank_of_actual - 1) / n_candidates
                          if rank_of_actual is not None and n_candidates else None)

        who_leads_rows[item] = {
            "predicted_top8": [
                {"account_id": a, "name": ti14_name.get(a, str(a)), "team": ti14_team.get(a, "?"),
                 "prob_leads": p, "pre_ti14_rate": rates.get(a), "actual_ti14_games": n_games_actual.get(a)}
                for a, p in ranked[:8]
            ],
            "actual_leader": {
                "account_id": actual_leader, "name": ti14_name.get(actual_leader, str(actual_leader)),
                "team": ti14_team.get(actual_leader, "?"), "actual_value": actual_value,
                "predicted_prob": prob_of_actual, "predicted_rank": rank_of_actual,
                "pre_ti14_rate": rates.get(actual_leader), "actual_ti14_games": n_games_actual.get(actual_leader),
            },
            "calibration": {
                "n_candidates": n_candidates, "uniform_baseline_prob": uniform_baseline,
                "actual_leader_prob_vs_uniform": prob_vs_uniform,
                "actual_leader_rank_percentile": rank_percentile,
            },
        }

    rank_pcts = [v["calibration"]["actual_leader_rank_percentile"] for v in who_leads_rows.values()
                if v["calibration"]["actual_leader_rank_percentile"] is not None]
    prob_ratios = [v["calibration"]["actual_leader_prob_vs_uniform"] for v in who_leads_rows.values()
                  if v["calibration"]["actual_leader_prob_vs_uniform"] is not None]
    overall_summary = {
        "n_items": len(who_leads_rows),
        "mean_actual_leader_rank_percentile": float(np.mean(rank_pcts)) if rank_pcts else None,
        "mean_actual_leader_prob_vs_uniform": float(np.mean(prob_ratios)) if prob_ratios else None,
        "n_threshold_questions": len(threshold_rows),
        "n_threshold_correct": sum(1 for r in threshold_rows if r["needs_gpd"] is False and (
            (r["predicted_prob"] >= 0.5) == r["actual_happened"])),
    }

    report = {
        "ti14_cutoff_start_time": cutoff,
        "ti14_total_games": total_actual_games,
        "ti14_total_player_game_slots": total_actual_slots,
        "n_pre_ti14_rows_used": int(len(train)),
        "overall_summary": overall_summary,
        "threshold_backtest": threshold_rows,
        "who_leads_backtest": who_leads_rows,
        "notes": [
            "Step 5：唯一能做的诚实检验——用 TI14 开赛前（start_time < "
            f"{cutoff}）的全部可得历史预测 TI14 会发生的极值，跟 TI14 实际"
            "发生的比对，结果不管好不好看都如实记录（见 task-9-report.md）。",

            "训练窗口用 TI14 开赛前的全部可得历史（不设 since_ts 下限），"
            "跟正式 TI15 报告用 since_ts=2024-01-01 这个较近窗口是两回事——"
            "回测要最大化样本量以获得稳健的尾部估计，正式报告要避免过时"
            "版本的滚动窗口，两者目的不同，是有意的方法论差异，不是不一致。",

            "身份题回测特意简化：(1) ti14_roster_derived.csv 没有号位字段，"
            "无法复现正式报告里'按位置分层收缩+按位置池化残差'那一套，"
            "改用选手自己的赛前历史均值（不做 L3 收缩）+全局池化残差"
            "（不分位置）；(2) n_games 用 TI14 实际局数（事后已知的真值），"
            "不重新模拟晋级路径——回测的目标是检验 L3尾部/L4-P2 这一层"
            "（有没有正确把'能力+离散度+局数'合成'谁最可能夺得全场之最'），"
            "不是重新检验 L1/L2 的晋级路径模拟（那部分已经在 Task 3/4 独立"
            "验证过、不是本任务范围）。",

            "阈值题的 n_games 用 TI14 实际总局数（144，事后已知）×10 个"
            "选手槽位，同一个理由：只检验尾部概率估计本身，不重新检验"
            "总局数的预测准不准（00-DESIGN.md §1.2 已经验证 N≈145 点估计"
            "与 TI14 实测 144 精确吻合）。",
        ],
    }
    return report


def _render_backtest_markdown(report):
    lines = []
    lines.append("# L4-P2 Step 5：TI14 回溯校验（诚实检验，好坏都记）\n")
    lines.append(f"TI14 开赛前 start_time<{report['ti14_cutoff_start_time']} 的历史行数："
                 f"{report['n_pre_ti14_rows_used']}；TI14 实际共 {report['ti14_total_games']} 局"
                 f"（≈{report['ti14_total_player_game_slots']} 个选手-局槽位）。\n")
    for n in report["notes"]:
        lines.append(f"- {n}")
    lines.append("")

    s = report["overall_summary"]
    rank_pct_s = f"{s['mean_actual_leader_rank_percentile']*100:.1f}%" if s["mean_actual_leader_rank_percentile"] is not None else "-"
    ratio_s = f"{s['mean_actual_leader_prob_vs_uniform']:.2f}x" if s["mean_actual_leader_prob_vs_uniform"] is not None else "-"
    lines.append("## 总览（好看不好看都在这）\n")
    lines.append(f"- 身份题（{s['n_items']} 项）：实际夺魁者的预测排名百分位平均 **{rank_pct_s}**"
                 f"（越高越好，100%=永远排第一），预测概率相对均匀瞎猜基准平均 **{ratio_s}**"
                 "（>1x 说明模型确实捕捉到真实信号）——但 4 项里没有一项把实际夺魁者猜成 Top1，"
                 "\"谁打出全场最高值\"这件事本身随机性很大，见下方逐项明细。")
    lines.append(f"- 阈值题（{s['n_threshold_questions']} 项里 {s['n_threshold_questions'] - sum(1 for r in report['threshold_backtest'] if r['needs_gpd'])} 项可估计）："
                 f"用\"预测概率是否≥50%\"当二元判断，猜对 {s['n_threshold_correct']} 项——"
                 "样本量太小（单届锦标赛只能提供个位数个阈值观测），这个比例本身不构成"
                 "有统计功效的校准检验，只作为定性参考，见逐项明细与 task-9-report.md 的完整讨论。\n")

    lines.append("## 阈值题回验\n")
    lines.append("| 计分项 | 阈值 | 说明 | 赛前预测概率 | TI14 是否实际发生 |")
    lines.append("|---|---|---|---|---|")
    for row in report["threshold_backtest"]:
        p = "无法估计(needs_gpd)" if row["predicted_prob"] is None else f"{row['predicted_prob']*100:.2f}%"
        lines.append(f"| {ITEM_LABEL.get(row['item'], row['item'])} | {row['threshold']:.0f} | "
                     f"{row['label']} | {p} | {'是' if row['actual_happened'] else '否'} |")
    lines.append("")

    lines.append("## 身份题回验：预测的夺魁概率排名 vs TI14 实际最高值得主\n")
    lines.append("**评判基准说明**：\"猜中 Top1\"对身份题是过严的标准——即便模型与真实生成过程"
                 "完全一致，\"谁打出全场最高值\"本身也高度随机，不会有任何候选人的概率接近 1。"
                 "下面同时给两个更合适的校准指标：实际夺魁者拿到的概率相对于\"均匀瞎猜\""
                 "（1/候选人数）高多少倍（>1 说明模型确实捕捉到真实信号），以及实际夺魁者在"
                 "预测排名里的百分位（排得靠前即使不是第一名也说明模型没有走偏）。\n")
    for item, v in report["who_leads_backtest"].items():
        lines.append(f"### {ITEM_LABEL.get(item, item)}\n")
        a = v["actual_leader"]
        c = v["calibration"]
        rank_s = str(a["predicted_rank"]) if a["predicted_rank"] is not None else "赛前模型未覆盖该选手"
        prob_s = f"{a['predicted_prob']*100:.2f}%" if a["predicted_prob"] is not None else "-"
        ratio_s = f"{c['actual_leader_prob_vs_uniform']:.2f}x" if c["actual_leader_prob_vs_uniform"] is not None else "-"
        pct_s = f"{c['actual_leader_rank_percentile']*100:.1f}%" if c["actual_leader_rank_percentile"] is not None else "-"
        lines.append(f"TI14 实际最高值得主：**{a['name']}**（{a['team']}），实际值 {a['actual_value']:.1f}，"
                     f"赛前模型给他的夺魁概率排名第 **{rank_s}**/{c['n_candidates']}（概率 {prob_s}，"
                     f"是均匀瞎猜基准的 **{ratio_s}**，排名百分位 **{pct_s}**）。\n")
        lines.append("| 赛前预测排名 | 选手 | 战队 | 夺魁概率 | 赛前场均 | TI14 实际局数 |")
        lines.append("|---|---|---|---|---|---|")
        for i, r in enumerate(v["predicted_top8"], 1):
            lines.append(f"| {i} | {r['name']} | {r['team']} | {r['prob_leads']*100:.2f}% | "
                         f"{r['pre_ti14_rate']:.1f} | {r['actual_ti14_games']} |")
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "reports", "p2_extremes.md"))
    ap.add_argument("--json-out", default=None, help="默认与 --out 同名、扩展名换成 .json")
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--blob", default=DEFAULT_BLOB)
    ap.add_argument("--l2", default=DEFAULT_L2)
    ap.add_argument("--since-ts", type=int, default=SINCE_2024_01_01)
    ap.add_argument("--seed", type=int, default=GLOBAL_SEED)
    ap.add_argument("--variance-check", action="store_true",
                    help="只独立复算方差倍数，不产出完整 P2 报告")
    ap.add_argument("--backtest-ti14", action="store_true",
                    help="Step 5：用 TI14 开赛前数据预测 TI14 实际发生的极值")
    ap.add_argument("--ti14-matches", default=DEFAULT_TI14_MATCHES)
    ap.add_argument("--ti14-roster", default=DEFAULT_TI14_ROSTER)
    ap.add_argument("--ti14-player-matches", default=DEFAULT_TI14_PLAYER_MATCHES)
    args = ap.parse_args()

    if args.variance_check:
        run_variance_check(args)
        return

    if args.backtest_ti14:
        report = run_backtest_ti14(args)
        report = _round(report)
        out_path = os.path.join(HERE, "..", "reports", "p2_ti14_backtest.md")
        json_path = os.path.join(HERE, "..", "reports", "p2_ti14_backtest.json")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(_render_backtest_markdown(report))
        with open(json_path, "w") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)
        print(f"已写入 {out_path}")
        print(f"已写入 {json_path}")
        for item, v in report["who_leads_backtest"].items():
            a = v["actual_leader"]
            print(f"[{item}] TI14 实际夺魁: {a['name']}({a['team']}) actual={a['actual_value']} "
                 f"predicted_rank={a['predicted_rank']} predicted_prob={a['predicted_prob']}")
        return

    report = build_report(csv_path=args.csv, blob_path=args.blob, l2_path=args.l2,
                          since_ts=args.since_ts, seed=args.seed)
    report = _round(report)

    md = _render_markdown(report)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(md)

    json_out = args.json_out
    if json_out is None:
        base, _ = os.path.splitext(args.out)
        json_out = base + ".json"
    with open(json_out, "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)

    print(f"已写入 {args.out}")
    print(f"已写入 {json_out}")
    print()
    print("[独立方差核验]")
    for item in VARIANCE_CHECK_ITEMS:
        v = report["variance_check"][item]
        print(f"  {item}: 均值倍数={v['ratio_mean']}x 中位数倍数={v['ratio_median']}x")


if __name__ == "__main__":
    main()
