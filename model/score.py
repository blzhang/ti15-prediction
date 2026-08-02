"""L5：赛后评分与校准（task-10-brief.md Step 3 起，含控制器指令要求的健全性区间）。

设计文档 §4.5 / §8 验收标准 7：一届 TI 只有 1 个冠军观测，评估不了任何东西。
但 TI15 会打 59 场系列赛 / 约 145 局，场级预测有上百个观测——这是全项目
唯一有统计功效的检验场。调研发现连圈内公信力最高的公开预测者（Noxville）
都不公布事后准确率，整个领域缺公开质量基准；对照标准学 538 的
`spi_matches.csv`——赛前概率与赛后结果放在同一张表公开
（那张表就是 reports/ti15_matches.csv，见 model/emit_match_table.py）。

健全性区间（设计文档 §5，控制器指令要求写进代码注释）：
    Brier **0.21-0.24**，约对应 63-67% 准确率。
    - 高于 0.25 = 比抛硬币还差（抛硬币的 Brier 恒为 0.25）。
    - **低于 0.20 要先怀疑数据泄漏，而不是庆祝**——赛前 Dota2 预测的现实
      准确率上限是 65-70%，做到 85%+ 几乎总意味着特征里混进了赛后信息。
    `classify_brier()` 把这条护栏钉成可执行代码而不是只存在于注释里。

brier / log_loss / calibration_bins 的算法与 task-10-brief.md Step 3 给的
参考实现一致（brier/log_loss 逐字核对无误）；calibration_bins 的分桶索引
在浮点边界上有一处需要修的地方，`calibration_bins` 的 docstring 里写清楚
了复现方式与修法，task-10-report.md 有完整的排查过程。
`score_report` 是 Interfaces 里点名要产出、但 brief 没给参考实现的第 4 个
函数，是本文件把 CSV 接到前三个函数上的那一层。
"""
import csv
import math

EPS = 1e-15                    # 与 sklearn 旧版 log_loss 的裁剪阈值一致

HEALTHY_BRIER_LO = 0.21
HEALTHY_BRIER_HI = 0.24
LEAKAGE_SUSPECT_BELOW = 0.20    # 严格小于——0.20 本身不算“怀疑泄漏”
COINFLIP_BRIER = 0.25           # 严格大于才算“比抛硬币还差”——0.25 本身就是抛硬币

MATCH_TABLE_FIELDNAMES = [
    "stage", "team_a", "team_b", "p_a_wins_series", "frozen_at", "result_a_wins",
]


def _check(probs, outcomes):
    if len(probs) != len(outcomes):
        raise ValueError(
            "probs 与 outcomes 长度必须一致：len(probs)=%d, len(outcomes)=%d"
            % (len(probs), len(outcomes))
        )
    if len(probs) == 0:
        raise ValueError("probs/outcomes 不能为空")


def brier(probs, outcomes):
    """场级 Brier score：均方误差。0=完美，1=完全反向，0.25=对半抛硬币。"""
    _check(probs, outcomes)
    return sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / len(probs)


def log_loss(probs, outcomes):
    """场级对数损失。概率裁到 [EPS, 1-EPS] 防止 log(0) 炸出 -inf。"""
    _check(probs, outcomes)
    total = 0.0
    for p, y in zip(probs, outcomes):
        p = min(max(p, EPS), 1 - EPS)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(probs)


def calibration_bins(probs, outcomes, n_bins=10):
    """按预测概率分桶，报告每桶样本数、桶内平均预测概率、桶内实际发生频率。

    桶 i 覆盖左闭右开区间 [i/n_bins, (i+1)/n_bins)（最后一桶在 p=1.0 处闭合）。

    **实测验证过的一个真实浮点边界问题**：把 `p * n_bins` 直接 `int()` 截断
    做分桶索引，在某些 n_bins 下会因为浮点乘法舍入误差把恰好落在桶边界上的
    p 分进错误的前一个桶。用穷举脚本扫过 n_bins=2..59 的所有精确边界值
    k/n_bins 验证过：
      - n_bins=10（本函数默认值、task-10-brief.md 五条测试全部用的值）下，
        k=1..9 十个边界全部精确，**不受影响**——不能因为下面这条会触发就
        想当然地认为默认配置也有问题，必须实测（tests/test_score.py::
        test_calibration_bins_default_decile_boundaries_are_all_exact 锁住
        这个正面结论）。
      - 但 n_bins=22 时 k=15：15/22 == 0.6818181818181818，乘以 22 算出
        14.999999999999998（不是 15.0），`int()` 截断成 14，样本被错分进
        桶 14（[14/22,15/22)）而不是它该在的桶 15（[15/22,16/22)）。
        n_bins=23(k=13)/26(k=15)/39(k=31) 同样复现。
    既然 n_bins 是调用方可控的参数（不是写死的 10），这是一个真实存在、
    只是默认配置恰好没触发的缺陷，用 `+1e-9` 的极小 epsilon 把浮点噪声推过
    边界修掉：epsilon 比本项目概率保留的 6 位小数精度（1e-6）小三个数量级，
    不会把真正相差 ≥1e-6 的、本该属于下一个桶的值误推上去
    （tests/test_score.py::test_calibration_bins_handles_float_boundary_case
    验证修复生效；task-10-report.md 记录了穷举扫描确认无副作用的过程）。
    """
    _check(probs, outcomes)
    bins = [{"lo": i / n_bins, "hi": (i + 1) / n_bins,
             "n": 0, "predicted": 0.0, "observed": 0.0} for i in range(n_bins)]
    correct_sum = [0.0] * n_bins
    for p, y in zip(probs, outcomes):
        i = min(int(p * n_bins + 1e-9), n_bins - 1)
        bins[i]["n"] += 1
        bins[i]["predicted"] += p
        correct_sum[i] += y
    for i, b in enumerate(bins):
        if b["n"]:
            b["predicted"] /= b["n"]
            b["observed"] = correct_sum[i] / b["n"]
    return bins


def classify_brier(b):
    """把一个场级 Brier score 归类为设计文档 §5 健全性护栏的四档之一。

    边界语义严格照护栏原文的用词理解：
      「低于 0.20」→ suspect_leakage（b < LEAKAGE_SUSPECT_BELOW，严格小于，
          0.20 本身不算“低于”）
      「0.21-0.24」→ healthy（闭区间，两端都健康）
      「高于 0.25」→ worse_than_coinflip（b > COINFLIP_BRIER，严格大于，
          0.25 本身就是抛硬币，不算“比抛硬币还差”）
      其余两段灰区 [0.20,0.21) 和 (0.24,0.25] → borderline
    """
    if b < LEAKAGE_SUSPECT_BELOW:
        return "suspect_leakage"
    if b > COINFLIP_BRIER:
        return "worse_than_coinflip"
    if HEALTHY_BRIER_LO <= b <= HEALTHY_BRIER_HI:
        return "healthy"
    return "borderline"


def _read_scored_rows(csv_path):
    """读 match table CSV，返回 (总行数, [(p, outcome), ...] 已回填结果的子集)。

    只有非空的 result_a_wins 才算“已回填”；空字符串（赛前默认值、或某些
    配对赛后也确实没发生）一律跳过，不计入 n_scored，也不参与打分。
    """
    scored = []
    total = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):   # 表头占第 1 行
            total += 1
            raw = (row.get("result_a_wins") or "").strip()
            if raw == "":
                continue
            if raw not in ("0", "1"):
                raise ValueError(
                    "第 %d 行 result_a_wins=%r 不是合法值（必须是空字符串、"
                    "'0' 或 '1'）：%s vs %s"
                    % (row_num, raw, row.get("team_a"), row.get("team_b"))
                )
            try:
                p = float(row["p_a_wins_series"])
            except (TypeError, ValueError):
                raise ValueError(
                    "第 %d 行 p_a_wins_series=%r 不是合法浮点数（%s vs %s 已标记"
                    "有结果，但概率字段缺失或损坏）"
                    % (row_num, row.get("p_a_wins_series"), row.get("team_a"), row.get("team_b"))
                )
            scored.append((p, int(raw)))
    return total, scored


def score_report(csv_path):
    """读 reports/ti15_matches.csv 风格的对阵概率表，只对已回填结果的行打分。

    赛前生成时全部 result_a_wins 留空：此时 n_scored=0，brier/log_loss 为
    None、verdict="no_data_yet"——这不是错误，是「赛事还没打完/还没回填」的
    正常状态。赛事进行中可以随时重新调用：只会对已经回填的子集打分，
    尚未发生的配对（result_a_wins 仍留空）被正确忽略，不会污染分数。
    """
    n_total, scored = _read_scored_rows(csv_path)
    out = {
        "n_total": n_total,
        "n_scored": len(scored),
        "brier": None,
        "log_loss": None,
        "calibration_bins": [],
        "healthy_range": [HEALTHY_BRIER_LO, HEALTHY_BRIER_HI],
        "verdict": "no_data_yet",
    }
    if not scored:
        return out

    probs = [p for p, _ in scored]
    outcomes = [y for _, y in scored]
    b = brier(probs, outcomes)
    out["brier"] = b
    out["log_loss"] = log_loss(probs, outcomes)
    out["calibration_bins"] = calibration_bins(probs, outcomes)
    out["verdict"] = classify_brier(b)
    return out
