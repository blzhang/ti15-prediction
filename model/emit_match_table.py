"""L5：赛前两两对阵概率表——TI15 的 `spi_matches.csv`（task-10-brief.md Step 5）。

设计文档 §4.5 / §8 验收标准 7：赛前概率与赛后结果放在同一张表公开，
是本项目对照 538 `spi_matches.csv` 的诚实基准；一届 TI 只有 1 个冠军观测，
但这张表能积出上百个场级观测，是全项目唯一有统计功效的检验场。

结构性难点与选择（task-10-report.md 有完整推理，这里只留代码需要的结论）：
    瑞士轮配对是内生的——R2 起，谁打谁取决于前面几轮战绩；R1 虽由赛事方
    指定，但两个分组本身赛前未公布，连 R1 的具体配对都列不出来。主赛事
    的双败种子同样取决于瑞士轮最终排名，赛前也列不出具体对阵。

    可选方案对比：
      A. 只列赛前已知的对阵 → 目前已知对阵数 = 0（分组未公布），表是空的。
      B.（采用）列全部 16x15/2=120 个可能配对的两两 BO3 胜率，赛后按实际
         发生的配对取子集回填评分。
      C. 等分组公布后再生成 → 分组公布得很晚且只解决 R1，R2 起依然内生，
         不能一次性解决问题，还会挤占「赛前冻结」的时间余量。
    选 B：两队的 h2h 胜率只是两队实力的函数，不依赖赛程结构本身，赛前就能
    算全；未实际发生的配对由 model/score.py::score_report 通过
    result_a_wins 留空自动排除，不需要提前知道赛程。

    stage 列在赛前同样无法填「实际」阶段（同一个理由：不知道会不会相遇、
    在哪个阶段相遇），所以赛前统一填占位值 STAGE_PENDING。赛后回填流程
    （人工，或未来的脚本）：找到 team_a/team_b 对应实际发生过的那一行，把
    stage 改成真实阶段字符串（如 "swiss_r3"/"advance"/"playoff_ubqf"/
    "playoff_gf"），result_a_wins 填 1（team_a 赢）或 0。如果同一对队伍
    真的相遇两次（如瑞士轮打过一次、决赛又碰到——双败淘汰赛种子不检查
    是否与瑞士轮对手重复），就追加一行而不是覆盖已有行：p_a_wins_series
    两行都复用同一个赛前冻结值，因为它是"赛前对这对队伍的唯一承诺"，不会
    为第二次相遇重新估计；score_report 逐行独立打分，不关心 team_a/team_b
    是否在别的行里重复出现。

    p_a_wins_series 统一按 BO3 公式计算——59 场系列赛里只有决赛 1 场是
    BO5（BO5 让强队的胜率比 BO3 更极端），赛前又不知道谁能打进决赛，无法
    为「决赛专属配对」单独出一版 BO5 数字。这是明确接受的简化：决赛用
    BO3 数字评分会轻微低估夺冠热门的真实优势，但只影响 59 场里的 1 场
    （约 1.7%），影响范围已在 task-10-report.md 写清楚。

    实力不确定性传播：与 model/l2_simulate.py 的方法论保持一致——L2 算
    夺冠/晋级等概率时，每次模拟都从 N(theta_hat, se) 重抽 theta 再判定
    胜负,不是直接对 theta_hat 点估计取一次 sigmoid。这张表的两两胜率同理，
    用蒙特卡洛对 theta 的后验不确定性积分（`series_win_prob_matrix`），
    而不是简单地对两队的点估计差值取一次 sigmoid——否则这张表会比 L2 的
    其它输出更"自信"，出现方法论内部不一致，对样本少、se 大的队伍尤其
    明显（如 HULIGANI se=0.224 远高于 Team Falcons se=0.119）。

用法：
    python3 model/emit_match_table.py --out reports/ti15_matches.csv
"""
import argparse
import csv
import itertools
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)   # 与 l2_simulate.py/l3_player.py 一致的裸导入 shim

FIELDNAMES = ["stage", "team_a", "team_b", "p_a_wins_series", "frozen_at", "result_a_wins"]
STAGE_PENDING = "pending"       # 赛前占位值：真实阶段要等对阵实际发生才知道
DEFAULT_N_SIM = 200000          # 与 model/l2_simulate.py 的 N_SIM 保持一致
MC_SEED = 20260802              # Global Constraints：蒙特卡洛固定该种子


def series_win_prob_matrix(theta, se, rng, n_sim=DEFAULT_N_SIM, batch=10000):
    """蒙特卡洛估计 P[i, j] = P(队伍 i 赢队伍 j 的一场 BO3)。

    每次抽样都从 theta_i ~ N(theta_hat_i, se_i) 重抽全部队伍的实力
    （与 model/l2_simulate.py::run_one 顶部算 p1/p3 的公式完全一致），
    在同一批抽样上同时算出 [i,j] 和 [j,i] 两个方向，而不是分别独立抽样
    再估计——这保证了 P[i,j] + P[j,i] 对每一次抽样都精确等于 1（BO3 公式
    本身的代数恒等式 p3(q)+p3(1-q)==1），不会出现两个方向独立抽样凑不齐
    1 的自洽问题（对应设计文档 §8 验收标准 3「概率自洽」）。

    分批累加而不是一次性生成 (n_sim, n, n) 的完整张量：16 队、
    n_sim=200000 时一次性生成约需 410MB，分批（默认每批 1 万次）能把峰值
    内存压到几十 MB，对内存有限的机器更友好。
    """
    theta = np.asarray(theta, dtype=float)
    se = np.asarray(se, dtype=float)
    n = len(theta)
    acc = np.zeros((n, n))
    done = 0
    while done < n_sim:
        b = min(batch, n_sim - done)
        draws = theta[None, :] + se[None, :] * rng.standard_normal((b, n))
        diff = draws[:, :, None] - draws[:, None, :]          # diff[s,i,j] = theta_i - theta_j
        p1 = 1.0 / (1.0 + np.exp(-diff))                       # 单局胜率
        p3 = p1 ** 2 * (3 - 2 * p1)                            # BO3 胜率
        acc += p3.sum(axis=0)
        done += b
    return acc / n_sim


def build_match_rows(teams, theta, se, rng, n_sim=DEFAULT_N_SIM, frozen_at=None, batch=10000):
    """产出 C(len(teams), 2) 行：team_a/team_b 按队名字典序排列、去重、
    只保留一个方向。team_a/team_b 的顺序只是"字典序在前"，不代表主场、
    种子、实力强弱或任何别的语义——纯粹是避免同一对队伍出现两行
    （一行 A vs B，一行 B vs A）的去重手段。
    """
    if frozen_at is None:
        frozen_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    P = series_win_prob_matrix(theta, se, rng, n_sim=n_sim, batch=batch)
    idx = {t: i for i, t in enumerate(teams)}
    rows = []
    for a, b in itertools.combinations(sorted(teams), 2):
        rows.append({
            "stage": STAGE_PENDING,
            "team_a": a,
            "team_b": b,
            "p_a_wins_series": round(float(P[idx[a], idx[b]]), 6),
            "frozen_at": frozen_at,
            "result_a_wins": "",
        })
    return rows


def write_match_csv(rows, out_path):
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "reports", "ti15_matches.csv"))
    ap.add_argument("--n-sim", type=int, default=DEFAULT_N_SIM)
    args = ap.parse_args(argv)

    rating = json.load(open(os.path.join(HERE, "l1_rating.json")))
    teams = list(rating["rating"])
    theta = [rating["rating"][t] for t in teams]
    se = [rating["rating_se"][t] for t in teams]
    rng = np.random.default_rng(MC_SEED)

    rows = build_match_rows(teams, theta, se, rng, n_sim=args.n_sim)
    write_match_csv(rows, args.out)
    print("→ 写入 %s（%d 队两两组合，%d 行，n_sim=%d）"
          % (args.out, len(teams), len(rows), args.n_sim))
    return rows


if __name__ == "__main__":
    main()
