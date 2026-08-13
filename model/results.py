"""已打完 / 已排定的瑞士轮系列赛（model/results.json）。

**这个模块解决什么问题**

赛前的预测把 5 轮瑞士轮全部当随机变量模拟。开赛之后，前面几轮已经是事实了，
再当随机变量抽就是在假装不知道自己知道的东西。本模块把「已经发生的结果」和
「已经排定但还没打的对阵」读进来，交给 l2_simulate 逐轮replay：
已知结果照抄（不消耗随机数），已排定未开打的用固定对阵 + 模拟胜负，
其余轮次照旧走配对函数。

**顺带解决了分组**

TI 瑞士轮 R1–R3 只在组内配对、R4 只跨组（见 model/swiss.py 的规则出处）。
所以每多打一轮，「谁跟谁必须同组」的约束就多一层：

    只知道 R1（8 组对阵）→ 8 个必须同组的块，各 2 队 → C(8,4)/2 = 35 种分法
    再知道 R2（8 组对阵）→ 4 个必须同组的块，各 4 队 → C(4,2)/2 =  3 种分法
    再知道 R3          → 2 个块，各 8 队           →            1 种（分组确定）

也就是说**分组不需要猜，打到第三轮它会自己塌缩成唯一解**。在那之前，
本模块只负责把「还剩几种」算出来，由模拟器对剩下的可能性平均——
这跟 2026-08-10 那次「35 种全平均」是同一条原则，只是约束变紧了。

⚠️ R4 是**跨组**轮，它给的是「必须不同组」的约束，绝不能拿去做同组合并。
`_constraints` 严格按轮次区分这两种约束，写反会静默产出一份错的分组。

**校验从严**

与 model/draw.py 同一条原则：填错会静默产出一份看着正常的错预测，
所以所有校验失败一律抛 ResultsError 退出，不做任何"尽力而为"的兜底。
"""
import itertools
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "results.json")

# 轮次语义（rnd 从 1 计，与对外文案一致；模块内部转成从 0 计的索引）
SAME_GROUP_ROUNDS = (1, 2, 3)   # 只在组内配对
DIFF_GROUP_ROUNDS = (4,)        # 只跨组配对
FREE_ROUNDS = (5,)              # 无分组约束
MAX_ROUND = 5

BO3_WIN = 2                     # 全部瑞士轮系列赛都是 BO3


class ResultsError(ValueError):
    """results.json 有问题。信息里必须写清楚哪一项错了、应该怎么改。"""


def _parse_score(score, a, b, where):
    """校验一场 BO3 比分 -> (a_wins, loser_games)；未开打返回 (None, None)。"""
    if score is None:
        return None, None
    if not isinstance(score, list) or len(score) != 2:
        raise ResultsError("%s 的 score 必须是 [A 局数, B 局数] 两个整数，现在是 %r"
                           % (where, score))
    for v in score:
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise ResultsError("%s 的 score 里出现了非自然数：%r" % (where, score))
    hi, lo = max(score), min(score)
    if hi != BO3_WIN or lo not in (0, 1):
        raise ResultsError(
            "%s 的比分 %d-%d 不是一场打完的 BO3（必须是 2-0 或 2-1）。"
            "还没打完的系列赛请把 score 整个删掉，而不是填当前比分——"
            "填进行中的比分会被当成最终结果。" % (where, score[0], score[1]))
    return score[0] == BO3_WIN, lo


def _parse_rounds(cfg, idx):
    """校验 rounds -> {rnd（从 1 计）: [(i, j, a_wins|None, loser_games|None)]}。"""
    raw = cfg.get("rounds", [])
    if not isinstance(raw, list) or not raw:
        raise ResultsError("results.json 的 rounds 必须是非空数组")
    out = {}
    for entry in raw:
        rnd = entry.get("round")
        if rnd not in range(1, MAX_ROUND + 1):
            raise ResultsError("round 只能是 1-%d，现在是 %r" % (MAX_ROUND, rnd))
        if rnd in out:
            raise ResultsError("第 %d 轮出现了两次" % rnd)
        series = entry.get("series", [])
        if not isinstance(series, list) or not series:
            raise ResultsError("第 %d 轮的 series 必须是非空数组" % rnd)
        seen, parsed = set(), []
        for k, s in enumerate(series, start=1):
            where = "第 %d 轮第 %d 场" % (rnd, k)
            a, b = s.get("a"), s.get("b")
            for t in (a, b):
                if t not in idx:
                    raise ResultsError(
                        "%s 里的队名不认识：%r（大小写和空格必须与 l1_rating.json 完全一致）"
                        % (where, t))
            if a == b:
                raise ResultsError("%s 的两侧是同一支队：%s" % (where, a))
            for t in (a, b):
                if t in seen:
                    raise ResultsError(
                        "%s：%s 在第 %d 轮里出现了不止一次——一支队一轮只打一场"
                        % (where, t, rnd))
                seen.add(t)
            a_wins, loser_games = _parse_score(s.get("score"), a, b, where)
            parsed.append((idx[a], idx[b], a_wins, loser_games))
        out[rnd] = parsed

    # 轮次不能跳号：缺了中间某一轮，后面那轮的战绩前提就是错的
    for r in range(1, max(out) + 1):
        if r not in out:
            raise ResultsError(
                "填了第 %d 轮却缺第 %d 轮。中间缺一轮会让后面几轮的战绩前提失真，"
                "请补齐或删掉靠后的轮次。" % (max(out), r))
    return out


def _constraints(rounds):
    """按轮次语义拆出「必须同组」与「必须不同组」两组约束。

    R1–R3 组内配对 → 同组；R4 跨组配对 → 不同组；R5 无约束。
    把 R4 误当同组会直接推出一个错的分组，所以这里按轮次显式区分，
    不做「所有对阵都同组」的省事写法。
    """
    same, diff = [], []
    for rnd, series in rounds.items():
        for i, j, _, _ in series:
            if rnd in SAME_GROUP_ROUNDS:
                same.append((i, j))
            elif rnd in DIFF_GROUP_ROUNDS:
                diff.append((i, j))
    return same, diff


def _blocks(same, n):
    """并查集：把「必须同组」的队伍合并成块。返回按最小成员排序的块列表。"""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in same:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    groups = {}
    for t in range(n):
        groups.setdefault(find(t), []).append(t)
    return sorted((sorted(v) for v in groups.values()), key=lambda b: b[0])


def consistent_splits(blocks, diff, n):
    """枚举全部与约束自洽的分组：每组恰好 n//2 队，块不可拆，diff 两端必须异组。

    返回 [[0/1]*n, ...]，已按「0 号队恒在 0 组」规范化去重（两组互换算同一种）。
    没有任何自洽分法时抛错——那意味着输入的对阵自相矛盾，绝不能静默放过。
    """
    half = n // 2
    out, seen = [], set()
    for k in range(len(blocks) + 1):
        for combo in itertools.combinations(range(len(blocks)), k):
            if sum(len(blocks[b]) for b in combo) != half:
                continue
            gv = [1] * n
            for b in combo:
                for t in blocks[b]:
                    gv[t] = 0
            if gv[0] == 1:                       # 规范化：0 号队恒在 0 组
                gv = [1 - g for g in gv]
            key = tuple(gv)
            if key in seen:
                continue
            if any(gv[i] == gv[j] for i, j in diff):
                continue                          # 违反「必须跨组」
            seen.add(key)
            out.append(gv)
    if not out:
        raise ResultsError(
            "没有任何分组能同时满足已填的对阵约束——说明 results.json 里的对阵"
            "自相矛盾（例如把跨组轮填成了组内轮，或某一轮的对阵抄错了）。")
    return out


def load(teams, path=None):
    """读取并校验已完赛结果。

    teams: 队名列表，顺序即模拟器里的队伍索引（model/l1_rating.json 的顺序）。

    返回 None 表示「还没有任何已完赛信息，按赛前那样全程模拟」；否则返回
        {"rounds": {rnd（从 1 计）: [(i, j, a_wins|None, loser_games|None)]},
         "blocks": [[队伍索引, ...], ...],   # 必须同组的块
         "splits": [[0/1]*16, ...],          # 与全部已知对阵自洽的分组，可能不止一种
         "n_done": 已打完系列赛数, "n_scheduled": 已排定未开打系列赛数,
         "as_of_utc": ..., "source": ...}
    """
    p = path or PATH
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        cfg = json.load(fh)
    if not cfg.get("active"):
        return None

    idx = {t: i for i, t in enumerate(teams)}
    rounds = _parse_rounds(cfg, idx)
    same, diff = _constraints(rounds)
    blocks = _blocks(same, len(teams))
    splits = consistent_splits(blocks, diff, len(teams))

    n_done = sum(1 for s in rounds.values() for r in s if r[2] is not None)
    n_sched = sum(1 for s in rounds.values() for r in s if r[2] is None)
    if not n_done and not n_sched:
        raise ResultsError("rounds 里一场系列赛都没有，active 却是 true")
    return {
        "rounds": rounds,
        "blocks": blocks,
        "splits": splits,
        "n_done": n_done,
        "n_scheduled": n_sched,
        "as_of_utc": cfg.get("as_of_utc", ""),
        "source": cfg.get("source", ""),
    }


def records(observed, teams):
    """从已完赛结果算每队当前战绩 {队名: (胜, 负)}——供站点与复盘页使用，
    不参与模拟（模拟走 SwissState，自己会记）。"""
    w = {t: 0 for t in teams}
    l = {t: 0 for t in teams}
    for series in observed["rounds"].values():
        for i, j, a_wins, _ in series:
            if a_wins is None:
                continue
            win, lose = (i, j) if a_wins else (j, i)
            w[teams[win]] += 1
            l[teams[lose]] += 1
    return {t: (w[t], l[t]) for t in teams}


def describe(observed, teams):
    """给人看的摘要，跑重算脚本时打印出来供肉眼复核。

    分组还没塌缩成唯一解时，这里绝不能说「分组已确定」——与 draw.describe
    同一条纪律：我们没有的东西不能写成我们有。
    """
    if not observed:
        return "无已完赛结果 —— 全程按赛前模拟"
    n = len(observed["splits"])
    head = ("已完赛 %d 场系列赛、已排定未开打 %d 场（截至 %s）"
            % (observed["n_done"], observed["n_scheduled"], observed["as_of_utc"]))
    if n == 1:
        ga = [teams[i] for i, g in enumerate(observed["splits"][0]) if g == 0]
        gb = [teams[i] for i, g in enumerate(observed["splits"][0]) if g == 1]
        grp = ("  分组已由对阵唯一确定（不是猜的，是打出来的）：\n"
               "    一组：" + "、".join(ga) + "\n    另一组：" + "、".join(gb))
    else:
        grp = ("  分组仍未唯一确定：与已知对阵自洽的分法还剩 %d 种，模拟器对这 %d 种平均。\n"
               "    必须同组的块：%s"
               % (n, n, "；".join("{" + "、".join(teams[t] for t in b) + "}"
                                  for b in observed["blocks"])))
    src = "  来源：%s" % observed["source"] if observed["source"] else ""
    return "\n".join([head, grp, src])
