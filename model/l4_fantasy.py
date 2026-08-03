"""L4-P1：Fantasy 分项产出矩阵。

设计文档 §4.3：基础系数服务端下发、静态取不到，因此**不出绝对总分**，
只出「选手 × 计分项」的每局期望，由使用者按自己装的徽记取用。

TI15 Fantasy 选队不选人：Core Duo / Support Duo 是队级（两人取平均），
Mid 是单人。三种口径都要能出。

对 task-7-brief.md Step 3 参考实现的一处修正（详见 task-7-report.md 的
repro 记录，已用 tests/test_l4_fantasy.py 的新增测试锁定，不是"默默改"）：

  `SLOT_POSITIONS["core"]` 原参考实现写的是 `(1, 2)`（carry + mid），
  应为 `(1, 3)`（carry + offlane）。号位编号（`model/rosters.py` 头注、
  `01-ti15-facts.md:270`）是 1=carry / 2=mid / 3=offlane / 4=soft support
  / 5=hard support。TI15 Fantasy 只有 3 槽：Core Duo / Mid / Support Duo，
  历史 Player Card 时代（`06-fantasy-rules.md` §E.2）原文写阵容是
  "2 Core + 1 Mid + 2 Support 共 5 张卡"——5 个号位无重叠无遗漏地分给
  三类，Mid 单独占 1 个号位，Support 占 4、5，Core 因此只能是剩下的
  1、3（carry+offlane），不可能是 (1,2)：若 Core=(1,2)，2 号位会同时被
  Core 和 Mid 计费（重复计分），3 号位（offlane）则完全没有任何槽位
  覆盖——一个理应覆盖全队 5 人产出的 fantasy 系统凭空漏掉一整个位置，
  不合理。`06-fantasy-rules.md` §G.4 的 TI14 真实数据表也把 Team Falcons
  的 Malr1ne（2 号位/中单）标注为 "Mid" 而非 "Core"，印证 OpenDota 自己
  的 `fantasy_role` 字段同样不把 2 号位算进 Core。
"""
SLOT_POSITIONS = {"core": (1, 3), "mid": (2,), "support": (4, 5)}


def player_matrix(rates_by_item, items):
    """{item: {account: {...}}} → {account: {item: rate}}"""
    out = {}
    for item in items:
        for acct, v in rates_by_item[item].items():
            out.setdefault(acct, {})[item] = float(v["rate"])
    return out


def slot_aggregate(matrix, rosters, positions, slot):
    """按槽位把选手矩阵聚合到队级。mid 槽不做平均，直接取该队 2 号位
    （用同一套"除以成员数"公式表达：mid 槽成员数恒为 1，除以 1 就是
    直接取值，不需要单独分支）。

    某队在该槽位对应号位上没有任何选手出现在 matrix 里（比如样本量为 0
    被上游 fit_rate_model 过滤掉）时，该队从结果里跳过，不产出除以 0
    的假平均。

    【Important 缺陷修复】槽位命中的成员里，若只有部分人在 matrix 里有
    某个具体 item（例如该队 2 名核心里，一人该项样本量为 0 被上游过滤掉，
    另一人正常），该 item 的分母必须只算实际持有它的成员数，不能把缺失
    的一方按 0.0 计入总和后仍除以全部成员数——那样会把该队该项的分数
    静默腰斩一半（`sum([500.0, 0.0]) / 2 == 250.0`，而正确答案应该是只由
    真正持有该 item 的成员决定，见
    test_slot_aggregate_excludes_missing_item_from_denominator_not_zero_fills）。
    """
    if slot not in SLOT_POSITIONS:
        raise ValueError("未知槽位 %r" % slot)
    want = SLOT_POSITIONS[slot]
    out = {}
    for team, roster in rosters.items():
        members = [a for a in roster.values()
                   if positions.get(a) in want and a in matrix]
        if not members:
            continue
        # sorted()：Python 字符串哈希每进程随机（PYTHONHASHSEED），裸用
        # set() 的遍历顺序决定输出键序会导致同一份输入连跑两次产出字节不同
        # 的 JSON（值一样、键序不同）——reports/p1_fantasy_matrix.json 因此
        # 无法做哈希存证、git diff 也全是噪声（见
        # .superpowers/sdd/fix-final-report.md【2】，
        # test_slot_aggregate_orders_items_deterministically_not_by_set_hash
        # 锁定）。
        items = sorted(set().union(*(matrix[a].keys() for a in members)))
        team_scores = {}
        for it in items:
            contributing = [matrix[a][it] for a in members if it in matrix[a]]
            team_scores[it] = sum(contributing) / len(contributing)
        out[team] = team_scores
    return out


import numpy as np

TI15_Q_THREE_GAME = 0.4386   # BO3 打满三局的比例（TI14 实测 25/57）
TI14_PER_GAME_SD = 4.72      # 单局 fantasy 分标准差（06-fantasy-rules.md）


def _best_series(rng, mu, sd, n_series):
    """模拟 n_series 个系列赛，每个取最高两局的均值，返回其中最好的那个。

    不能用解析近似：取最大值是顺序统计量，随 n 增长极慢。
    早期用 `1 + ln(n)` 近似，实测相对误差 43%→130% 且随 n 放大
    （真实 2→9 场只涨约 17.3%，该近似涨约 89%），会系统性高估深跑收益，
    直接污染 A/B 分支对比——这是本任务杠杆最大的一条护栏，两条锁定测试
    （test_max_order_statistic_grows_slowly_not_logarithmically_in_scale、
    test_calibrates_to_ti14_measured_distribution）不许放松。

    这里用的 BO3 打满三局比例是 TI14 全局实测的固定常数 0.4386，跟
    `model/bracket.py::loser_games_prob` 现在用的"随实力差变化"公式不是
    同一件事，也不应该改成那个公式：`loser_games_prob` 要求知道具体对手
    是谁才能算出让分小局概率，而这里的 `n_series` 来自 `series_dist`——
    一个已经对"未知的、随赛程变化的对手"边际化过的期望系列赛数，本来
    就不含"这一场具体对谁"的信息，用全局平均常数是这个抽象层级上唯一
    自洽的选择。
    """
    n_series = int(n_series)
    if n_series <= 0:
        return 0.0
    best = -np.inf
    for _ in range(n_series):
        n_games = 2 + int(rng.random() < TI15_Q_THREE_GAME)
        g = np.sort(rng.normal(mu, sd, size=n_games))[::-1][:2]
        best = max(best, float(g.mean()))
    return best


def expected_slot_score(matrix, series_dist, branch,
                        per_game_sd=TI14_PER_GAME_SD, n_sim=4000, seed=20260802):
    """把每局速率与「打多少系列赛」合成一个期望分。

    branch A：全程只取最好的一个系列赛 —— 多打只是多抽几次，边际递减
    branch B：分阶段计分、缺席阶段记 0 —— 缺席直接损失整段
    两个分支的量化对比见设计文档 §4.3。

    series_dist 的值可以是小数（模拟出来的期望系列赛数），
    按概率取上下整（无偏随机取整，E[draw(v)]==v），避免直接截断丢掉
    半场的信息。matrix 里有但 series_dist 里没有的 key 按 0 场处理
    （没有系列赛数据 = 预测不出这支队/这个槽打了多少场，期望分退化为 0，
    不报错）。

    `matrix` 的每个 team/slot 条目应当是「单个已经过某种系数换算成
    同一量纲的每局综合分」（`mu = sum(items.values())`），不是
    `slot_aggregate` 直接产出的多项原始分项（那些量纲互不可比，例如
    GPM 和 Kills 不能直接相加）——`model/l4_fantasy_report.py` 里对
    A/B 分支的编排调用会用 DPC 代理系数把多项先合成单一分再传进来，
    并清楚标注这是代理值、不是 TI15 真实分数（§4.3 的系数缺口）。
    """
    if branch not in ("A", "B"):
        raise ValueError("branch 必须是 'A' 或 'B'")

    rng = np.random.default_rng(seed)
    out = {}
    for key, items in matrix.items():
        mu = float(sum(items.values()))
        stages = series_dist.get(key, {})
        total = 0.0
        for _ in range(n_sim):
            def draw(v):
                lo = int(np.floor(v))
                return lo + int(rng.random() < (v - lo))
            if branch == "A":
                total += _best_series(rng, mu, per_game_sd,
                                      draw(sum(stages.values())))
            else:
                total += sum(_best_series(rng, mu, per_game_sd, draw(v))
                             for v in stages.values())
        out[key] = total / n_sim
    return out
