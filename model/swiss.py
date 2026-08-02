"""瑞士轮配对与排名。

规则来源 01-ti15-facts.md §1.3（TI14 原文，TI15 页面此节为空，按惯例沿用）：
  排名判据：胜场 → 负场 → 小局胜率 → Buchholz（对手总胜场）
            → 对手平均小局胜率 → 掷硬币
  配对：同战绩配对 / 尽量避免重赛 / 尽量最小化排名距离
  分轮修正：R1 分两组由赛事方指定；R2/R3 只组内；R4 只跨组；R5 无修正
"""


class SwissState(object):
    def __init__(self, n=16):
        self.n = n
        self.wins = [0] * n
        self.losses = [0] * n
        self.game_wins = [0] * n
        self.game_losses = [0] * n
        self.played = [set() for _ in range(n)]
        self.opponents = [[] for _ in range(n)]
        self.group = [0] * (n // 2) + [1] * (n - n // 2)

    def record(self, a, b, a_wins, loser_games):
        """记一场 BO3 结果。loser_games = 输方拿到的小局数（0 或 1）。"""
        w, l = (a, b) if a_wins else (b, a)
        self.wins[w] += 1
        self.losses[l] += 1
        self.game_wins[w] += 2
        self.game_losses[w] += loser_games
        self.game_wins[l] += loser_games
        self.game_losses[l] += 2
        self.played[a].add(b)
        self.played[b].add(a)
        self.opponents[a].append(b)
        self.opponents[b].append(a)

    def game_rate(self, t):
        d = self.game_wins[t] + self.game_losses[t]
        return self.game_wins[t] / d if d else 0.0

    def buchholz(self, t):
        return sum(self.wins[o] for o in self.opponents[t])

    def opp_game_rate(self, t):
        if not self.opponents[t]:
            return 0.0
        return sum(self.game_rate(o) for o in self.opponents[t]) / len(self.opponents[t])


def rank_teams(state, rng):
    return sorted(
        range(state.n),
        key=lambda t: (-state.wins[t], state.losses[t], -state.game_rate(t),
                       -state.buchholz(t), -state.opp_game_rate(t), rng.random()),
    )


def _bipartite_perfect_matching(top, bot, edge_ok):
    """增广路径（Kuhn 算法）：在 top×bot 间找一个完美匹配，`edge_ok(a, b)`
    判断该边是否可用。返回 None 表示在给定约束下无解；否则返回按 top 顺序
    排列的 [(a, b), ...]。

    比贪心（按 top 顺序逐个抢最靠前的可行对手）更可靠：贪心会在明明存在
    可行完美匹配时，因为抢占顺序不利而漏掉（见 test_no_rematch_within_five_rounds
    debug 记录：贪心把某队的下浮唯一候选提前用掉，导致本可避免的重赛）。
    """
    adj = {a: [b for b in bot if edge_ok(a, b)] for a in top}
    match_b_to_a = {}

    def augment(a, visited):
        for b in adj[a]:
            if b in visited:
                continue
            visited.add(b)
            if b not in match_b_to_a or augment(match_b_to_a[b], visited):
                match_b_to_a[b] = a
                return True
        return False

    for a in top:
        if not augment(a, set()):
            return None
    match_a_to_b = {a: b for b, a in match_b_to_a.items()}
    return [(a, match_a_to_b[a]) for a in top]


def _edge_ok(state, must_differ_group, level):
    """三级回退的边可行性判据：
      0. 满足分组约束（若给定）且不重赛
      1. 放弃分组约束，只要求不重赛
      2. 两者都放弃（任意匹配）
    """
    def f(a, b):
        if level == 0:
            if must_differ_group is not None and (state.group[a] != state.group[b]) != must_differ_group:
                return False
            return b not in state.played[a]
        if level == 1:
            return b not in state.played[a]
        return True
    return f


def _pair_pool(pool, state, must_differ_group=None):
    """在一个候选池内配对：上半区对下半区，用完美匹配三级回退替代贪心。"""
    half = len(pool) // 2
    top, bot = pool[:half], pool[half:]
    for level in (0, 1, 2):
        m = _bipartite_perfect_matching(top, bot, _edge_ok(state, must_differ_group, level))
        if m is not None:
            return m
    return list(zip(top, bot))     # 兜底；level=2 图完全连通，理论上到不了这里


def pair_round(state, rnd, rng):
    """rnd 从 0 计。返回 [(a,b), ...]。"""
    order = rank_teams(state, rng)

    if rnd == 0:                       # R1：跨组，赛事方指定，用同组内随机近似
        g0 = [t for t in order if state.group[t] == 0]
        g1 = [t for t in order if state.group[t] == 1]
        rng.shuffle(g0)
        rng.shuffle(g1)
        return list(zip(g0, g1))

    if rnd in (1, 2):                  # R2/R3：只在组内
        pairs = []
        for g in (0, 1):
            pool = [t for t in order if state.group[t] == g]
            pairs += _pair_by_score(pool, state, None)
        return pairs

    if rnd == 3:                       # R4：只跨组
        return _pair_by_score(order, state, must_differ_group=True)

    return _pair_by_score(order, state, None)      # R5：无修正


def _pair_by_score(pool, state, must_differ_group):
    """按战绩分组，组内完美匹配，奇数组下浮一队。"""
    remaining = list(pool)
    pairs = []
    while remaining:
        s = state.wins[remaining[0]]
        grp = [t for t in remaining if state.wins[t] == s]
        if len(grp) % 2 == 1:
            rest = [t for t in remaining if state.wins[t] != s]
            if rest:
                grp.append(_pick_downfloat(grp, rest, state, must_differ_group))
        pairs += _pair_pool(grp, state, must_differ_group)
        for t in grp:
            if t in remaining:
                remaining.remove(t)
    return pairs


def _pick_downfloat(grp, rest, state, must_differ_group):
    """奇数组下浮对象：不能盲取 rest[0]（战绩紧邻的最高排位队）——它可能恰好
    已经和 grp 里的队打过，导致 _pair_pool 在这个局部池里无解可选、被迫重赛，
    即便 rest 里其实还有没打过的候选（真实复现见 test_no_rematch_within_five_rounds
    debug：seed=4 时 rest[0]=11 号已和 3 号打过，但 8/9/12 号都没打过、本有解）。
    依次按「组约束+不重赛」「只要求不重赛」两级，优先选一个使 grp+[候选]
    能配出完美匹配的候选；两级都无解时才退回 rest[0]（交给 _pair_pool 兜底重赛）。
    """
    for level in (0, 1):
        edge_ok = _edge_ok(state, must_differ_group, level)
        for cand in rest:
            trial = grp + [cand]
            half = len(trial) // 2
            if _bipartite_perfect_matching(trial[:half], trial[half:], edge_ok) is not None:
                return cand
    return rest[0]
