"""从产出物直接生成设计文档 §9.5/§9.6 的表格，杜绝手抄陈旧数字。

背景：最终评审发现 §9.6 的 4-1 分布是 Task 3/4 重跑之前的旧数，
且第 3、4 位次序反转——照文档答官方预测题会答反。
根因是那两张表当初是手抄进文档的，模型重跑后没人同步。

用法：
    python3 model/emit_design_tables.py            # 打印 markdown
    python3 model/emit_design_tables.py --check    # 只校验文档与产出物是否一致，不一致则非零退出
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PRED = os.path.join(HERE, "l2_predictions.json")
BLEND = os.path.join(HERE, "l2_blended.json")
DESIGN = os.path.join(ROOT, "00-DESIGN.md")


def load():
    pred = json.load(open(PRED))
    blended = json.load(open(BLEND))["champion_blended"]
    return pred, blended


def main_table(pred, blended):
    rows = ["| 队 | **夺冠（融合）** | 夺冠（纯模型） | 进淘汰赛 | 瑞士轮前3 | 5-0 | 4-1 |",
            "|---|---|---|---|---|---|---|"]
    for t in sorted(blended, key=lambda x: -blended[x]):
        rows.append("| %s | **%.1f%%** | %.1f%% | %.1f%% | %.1f%% | %.1f%% | %.1f%% |" % (
            t, blended[t] * 100, pred["champion"][t] * 100,
            pred["advance_playoffs"][t] * 100, pred["swiss_top3"][t] * 100,
            pred["record_5_0"][t] * 100, pred["record_4_1"][t] * 100))
    return "\n".join(rows)


def swiss_tables(pred):
    a = ["| 本届 5-0 队数 | 概率 |", "|---|---|"]
    for k in sorted(pred["n_5_0_dist"], key=int):
        a.append("| %s 支 | %.2f%% |" % (k, pred["n_5_0_dist"][k] * 100))
    b = ["| 本届 4-1 队数 | 概率 |", "|---|---|"]
    for k in sorted(pred["n_4_1_dist"], key=int):
        v = pred["n_4_1_dist"][k]
        if v > 0.005:
            b.append("| %s 支 | %.2f%% |" % (k, v * 100))
    return "\n".join(a), "\n".join(b)


def check(pred, blended):
    """校验设计文档里的关键数字与产出物一致。返回不一致清单。"""
    text = open(DESIGN).read()
    bad = []
    # 融合后夺冠概率：每队一行「| 队名 | **x.x%** |」
    for t, v in blended.items():
        want = "| %s | **%.1f%%**" % (t, v * 100)
        if want not in text:
            bad.append("夺冠(融合) %s 应为 %.1f%%" % (t, v * 100))
    for k, v in pred["n_4_1_dist"].items():
        if v > 0.005:
            want = "| %s 支 | %.2f%% |" % (k, v * 100)
            if want not in text:
                bad.append("4-1 分布 %s 支 应为 %.2f%%" % (k, v * 100))
    for k, v in pred["n_5_0_dist"].items():
        want = "| %s 支 | %.2f%% |" % (k, v * 100)
        if want not in text:
            bad.append("5-0 分布 %s 支 应为 %.2f%%" % (k, v * 100))
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    pred, blended = load()
    if args.check:
        bad = check(pred, blended)
        if bad:
            print("设计文档与产出物不一致（%d 处）：" % len(bad))
            for b in bad:
                print("  -", b)
            sys.exit(1)
        print("设计文档与产出物一致 ✓")
    else:
        t50, t41 = swiss_tables(pred)
        print("### 主表\n\n%s\n\n### 5-0\n\n%s\n\n### 4-1\n\n%s" % (main_table(pred, blended), t50, t41))
