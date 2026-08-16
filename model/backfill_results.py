"""把已完赛结果回填进赛前对账表 reports/ti15_matches.csv。

**为什么要有这个脚本**

reports/ti15_matches.csv 是赛前冻结的 120 组两两胜率（model/emit_match_table.py），
对照的是 538 的 `spi_matches.csv`：赛前概率与赛后结果放在同一张表里公开。
它留了 `stage` 和 `result_a_wins` 两列等赛后回填，原设计写的是"人工，或未来的脚本"。
这就是那个脚本——手工回填 59 场系列赛，抄错一格就会污染 Brier，而且事后查不出来。

**只写两列，绝不碰概率**

`p_a_wins_series` 与 `frozen_at` 是赛前对这对队伍的唯一承诺，本脚本一个字节都不改。
（`--check` 模式连这两列都不写，只报告将要回填什么。）

**幂等且拒绝改口**

同一场比赛重复回填没有副作用；但如果表里已有的结果与 results.json 不一致，
直接报错退出——那意味着两边有一处抄错了，静默覆盖等于把错误变成"事实"。

用法：
    python3 -m model.backfill_results            # 回填并打分
    python3 -m model.backfill_results --check    # 只看会填什么，不写盘
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import results as results_mod                      # noqa: E402
from score import MATCH_TABLE_FIELDNAMES, score_report, classify_brier   # noqa: E402

DEFAULT_CSV = os.path.join(ROOT, "reports", "ti15_matches.csv")
DEFAULT_RATING = os.path.join(HERE, "l1_rating.json")


class BackfillError(ValueError):
    """回填对不上。信息里必须写清楚哪一场对不上、两边各是什么。"""


def finished_series(observed, teams):
    """已完赛系列赛 -> [(队A, 队B, 胜者, "swiss_rN"/"advance"), ...]，按赛程排序。

    附加淘汰轮排在瑞士轮之后（赛程本来就是这个顺序），stage 记 "advance"——
    与站点侧 STAGE_CN 的键一致。
    """
    out = []
    for rnd, series in sorted(observed["rounds"].items()):
        for i, j, a_wins, _ in series:
            if a_wins is None:
                continue
            a, b = teams[i], teams[j]
            out.append((a, b, a if a_wins else b, "swiss_r%d" % rnd))
    for i, j, a_wins, _ in observed.get("elim") or []:
        if a_wins is None:
            continue
        a, b = teams[i], teams[j]
        out.append((a, b, a if a_wins else b, "advance"))
    return out


def backfill(rows, observed, teams):
    """把结果写进 rows（原地改 stage / result_a_wins），返回 (改动数, 明细)。

    明细里带上赛前概率与是否命中，供调用方直接打印——避免调用方再查一遍表
    而两边口径不一致。

    **二次相遇**（瑞士轮打过、附加轮又碰上）按 emit_match_table.py 的说明处理：
    同一对队伍的第二场**追加一行**，p_a_wins_series 与 frozen_at 照抄第一行——
    赛前概率是对这对队伍的唯一承诺，不为第二次相遇重新估计。匹配按 stage 区分：
    先找已标了本阶段的行（幂等重跑），再找还空着的行，都没有才追加。
    """
    index = {}
    for r in rows:
        index.setdefault(frozenset((r["team_a"], r["team_b"])), []).append(r)

    changed, detail = 0, []
    for a, b, winner, stage in finished_series(observed, teams):
        key = frozenset((a, b))
        cand = index.get(key)
        if not cand:
            raise BackfillError(
                "对账表里找不到 %s vs %s 这一行——赛前那张表本应覆盖全部 120 组配对，"
                "找不到说明队名对不上或表被改过。" % (a, b))
        row = next((r for r in cand if (r.get("stage") or "") == stage), None)
        if row is None:
            row = next((r for r in cand
                        if not (r.get("result_a_wins") or "").strip()), None)
        if row is None:
            # 这对队伍的所有行都已被别的阶段占用 → 真正的二次相遇，追加一行。
            base = cand[0]
            row = {"stage": "", "team_a": base["team_a"], "team_b": base["team_b"],
                   "p_a_wins_series": base["p_a_wins_series"],
                   "frozen_at": base["frozen_at"], "result_a_wins": ""}
            rows.append(row)
            cand.append(row)
        want = "1" if winner == row["team_a"] else "0"
        have = (row.get("result_a_wins") or "").strip()
        if have and have != want:
            raise BackfillError(
                "%s vs %s（%s）的结果对不上：表里是 result_a_wins=%s，results.json 说赢的是 %s"
                "（应为 %s）。两边有一处抄错了，请先查清楚，不要覆盖。"
                % (a, b, stage, have, winner, want))
        p_a = float(row["p_a_wins_series"])
        detail.append({
            "stage": stage, "team_a": row["team_a"], "team_b": row["team_b"],
            "p_a": p_a, "winner": winner, "result_a_wins": int(want),
            "hit": (p_a > 0.5) == (want == "1"),
            "already": bool(have),
        })
        if have and row.get("stage") == stage:
            continue
        row["stage"] = stage
        row["result_a_wins"] = want
        changed += 1
    return changed, detail


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--check", action="store_true", help="只报告，不写盘")
    args = ap.parse_args(argv)

    teams = list(json.load(open(DEFAULT_RATING))["rating"])
    observed = results_mod.load(teams)
    if not observed:
        print("results.json 未启用——没有可回填的结果。")
        return None

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    changed, detail = backfill(rows, observed, teams)

    print("已完赛系列赛 %d 场，本次回填 %d 行%s\n"
          % (len(detail), changed, "（--check：未写盘）" if args.check else ""))
    print("%-9s %-17s %-17s %8s %-17s %s"
          % ("轮次", "队A", "队B", "赛前P(A)", "实际胜者", "赛前是否看对"))
    print("-" * 88)
    for d in detail:
        print("%-9s %-17s %-17s %7.1f%% %-17s %s"
              % (d["stage"], d["team_a"], d["team_b"], d["p_a"] * 100,
                 d["winner"], "✓" if d["hit"] else "✗"))
    hits = sum(1 for d in detail if d["hit"])
    print("-" * 88)
    print("方向命中 %d/%d = %.1f%%" % (hits, len(detail), 100.0 * hits / len(detail)))

    if args.check:
        return detail

    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MATCH_TABLE_FIELDNAMES)
        w.writeheader()
        w.writerows(rows)
    print("\n→ 写入 %s" % args.csv)

    rep = score_report(args.csv)
    print("\n赛后打分（只算已回填的 %d 场）：" % rep["n_scored"])
    print("  Brier      %.4f   （%s；健康区间 %.2f-%.2f）"
          % (rep["brier"], rep["verdict"], *rep["healthy_range"]))
    print("  LogLoss    %.4f" % rep["log_loss"])
    print("  ⚠️ %d 场样本量太小，这个数只能看方向，不能当结论。" % rep["n_scored"])
    return rep


if __name__ == "__main__":
    main()
