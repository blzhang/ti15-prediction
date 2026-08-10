"""赛事方公布的瑞士轮分组与首轮对阵（model/draw.json）。

**为什么需要这个模块**

瑞士轮前三轮只在组内配对、第四轮才跨组，所以「谁跟谁一组」直接决定前三轮的
对手。这不是运气，是主办方定的。但抽签在开赛前才公布，所以模拟器在未公布期间
只能每次随机抽一组分法，把所有可能性平均掉——
    16 队分两组 8 人：C(16,8)/2 = 6,435 种
    每组 8 队首轮配 4 对：7!! = 105 种，两组 105² = 11,025 种
    合计约 7,100 万种抽签结果
已发布的概率就是对这 7,100 万种情况求的平均。抽签一公布，它塌缩成 1 种。

**契约：未公布时必须零影响**

load() 在 announced=false（或文件缺失）时返回 None，调用方走原来的随机分支，
一次 rng 调用都不多不少——所以本模块存在与否，不改变任何已发布的数字。
tests/test_draw.py::test_unannounced_is_bit_identical 锁住这条。

**校验从严**

填错分组会静默产出一份错的预测并直接发布出去，这比崩掉严重得多。所以所有
校验失败一律抛 DrawError 退出，不做任何"尽力而为"的兜底。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "draw.json")


class DrawError(ValueError):
    """分组配置有问题。信息里必须写清楚哪一项错了、应该怎么改。"""


# 分组这件事的出处。首轮对阵可以有两个独立来源、当事实用，分组却可能是
# 我们自己从转播分流之类的旁证推出来的——两者的可信度差着一整级，混在一个
# announced=true 里发出去，读者只会读成「官方公布了」。
# 所以出处是结构化字段，一路带进 l2_predictions.json 和站点，不靠注释。
GROUPING_OFFICIAL = "official"   # 赛事方公布
GROUPING_INFERRED = "inferred"   # 我们从旁证推的，可能是错的
GROUPING_UNKNOWN = "unknown"     # 不知道，也不猜——交给模拟器平均掉
GROUPING_VALUES = (GROUPING_OFFICIAL, GROUPING_INFERRED, GROUPING_UNKNOWN)


def _need_list(cfg, key):
    v = cfg.get(key, [])
    if not isinstance(v, list):
        raise DrawError("draw.json 的 %s 必须是数组，现在是 %s" % (key, type(v).__name__))
    return v


def _parse_round1(r1, idx, group_vec):
    """校验并解析 round1 -> [(i, j), ...]。

    group_vec 为 None 表示分组未知，跳过「必须同组」那一条——分组本身待定，
    没有可比对的组别。其余校验（8 组、格式、队名、不重不漏）一视同仁。
    """
    if len(r1) != 8:
        raise DrawError("round1 要么留空，要么正好 8 组对阵，现在有 %d 组" % len(r1))
    flat = []
    for k, pair in enumerate(r1):
        if not isinstance(pair, list) or len(pair) != 2:
            raise DrawError("round1 第 %d 组必须是 [队A, 队B] 两个队名" % (k + 1))
        for t in pair:
            if t not in idx:
                raise DrawError("round1 第 %d 组里的队名不认识：%s" % (k + 1, t))
        if group_vec is not None and group_vec[idx[pair[0]]] != group_vec[idx[pair[1]]]:
            raise DrawError(
                "round1 第 %d 组是跨组对阵（%s vs %s）——首轮只在组内打，"
                "请核对分组或对阵是否填反了" % (k + 1, pair[0], pair[1]))
        flat += pair
    if len(set(flat)) != 16:
        dup = sorted({t for t in flat if flat.count(t) > 1})
        raise DrawError("round1 里这些队出现了不止一次：%s" % "、".join(dup))
    return [(idx[x], idx[y]) for x, y in r1]


def load(teams, path=None):
    """读取并校验分组配置。

    teams: 队名列表，顺序即模拟器里的队伍索引（model/l1_rating.json 的顺序）。

    返回 None 表示"未公布，按原样随机化"；否则返回
        {"group_vec": [0/1]*16,          # 按 teams 顺序的分组标记
         "r1_pairs": [(i, j), ...] 或 None,  # 首轮对阵，队伍索引
         "grouping": "official"|"inferred",  # 分组是官方公布的还是我们推的
         "source": "..."}                # 出处，写进产物供追溯
    """
    p = path or PATH
    if not os.path.exists(p):
        return None
    with open(p) as fh:
        cfg = json.load(fh)
    if not cfg.get("announced"):
        return None

    # 出处先校验：写错一个字（"infered"）如果被静默当成 official，
    # 正好把「推测」悄悄升级成「事实」，是这个字段最该防住的那种失败。
    grouping = cfg.get("grouping", GROUPING_OFFICIAL)
    if grouping not in GROUPING_VALUES:
        raise DrawError(
            "grouping 只能是 %s 之一，现在是 %r。"
            "官方公布的填 %r；自己从旁证推出来的填 %r——推的东西不能标成公布的。"
            % ("、".join(map(repr, GROUPING_VALUES)), grouping,
               GROUPING_OFFICIAL, GROUPING_INFERRED))

    idx = {t: i for i, t in enumerate(teams)}
    a, b = _need_list(cfg, "group_a"), _need_list(cfg, "group_b")
    r1_raw = _need_list(cfg, "round1")

    # 0. 「只锁首轮、分组未知」模式：两组都留空、round1 填齐。
    #    2026-08-10 的真实处境正是这样——首轮对阵有两个独立来源可以当事实，
    #    A/B 分组官方从没公布过。此前一版从转播分流「推」了一个分组填进来，
    #    那等于在 35 种同样自洽的切法里挑了一种当事实，凭空多一个自由度。
    #    留空才是诚实的写法：模拟器每次抽一种与首轮自洽的切法，把 35 种平均掉。
    if not a and not b:
        if not r1_raw:
            raise DrawError(
                "group_a / group_b / round1 三个都是空的，announced 却是 true——"
                "这份配置什么信息都没有。要么填分组，要么至少填 round1，"
                "要么把 announced 改回 false。")
        if grouping != GROUPING_UNKNOWN:
            raise DrawError(
                "分组留空时 grouping 必须是 %r，现在是 %r。"
                "两组都没填却声称分组是 %s，是自相矛盾的配置。"
                % (GROUPING_UNKNOWN, grouping, grouping))
        r1_pairs = _parse_round1(r1_raw, idx, group_vec=None)
        return {"group_vec": None, "r1_pairs": r1_pairs,
                "grouping": GROUPING_UNKNOWN, "source": cfg.get("source", "")}

    if grouping == GROUPING_UNKNOWN:
        raise DrawError(
            "grouping 是 %r 却填了分组名单——想声明「分组未知」就把 group_a / "
            "group_b 都留空；想用这份分组就把 grouping 改成 %r 或 %r。"
            % (GROUPING_UNKNOWN, GROUPING_OFFICIAL, GROUPING_INFERRED))

    # 1. 每组恰好 8 队 —— 瑞士轮的 1/2/5/5/2/1 分档恒等式依赖两组等分，
    #    一旦不等分，整个分档结构就不成立了，不能放过。
    for name, g in (("group_a", a), ("group_b", b)):
        if len(g) != 8:
            raise DrawError("%s 必须正好 8 支队，现在有 %d 支" % (name, len(g)))

    # 2. 队名必须精确匹配（大小写、空格都算）
    unknown = [t for t in a + b if t not in idx]
    if unknown:
        raise DrawError(
            "这些队名在 l1_rating.json 里找不到（大小写和空格必须完全一致）：%s\n"
            "合法队名：%s" % ("、".join(unknown), "、".join(teams)))

    # 3. 16 支队不重不漏
    both = a + b
    if len(set(both)) != 16:
        dup = sorted({t for t in both if both.count(t) > 1})
        raise DrawError("有队伍被填了多次：%s" % "、".join(dup))
    missing = [t for t in teams if t not in set(both)]
    if missing:
        raise DrawError("这些队没被分到任何一组：%s" % "、".join(missing))

    group_vec = [0] * len(teams)
    for t in b:
        group_vec[idx[t]] = 1

    # 4. 首轮：8 场，覆盖全部 16 队，且每场必须同组
    #    （跨组会让两组胜者数不确定，破坏后续分档结构——见 swiss.pair_round）
    r1_pairs = _parse_round1(r1_raw, idx, group_vec) if r1_raw else None

    return {"group_vec": group_vec, "r1_pairs": r1_pairs,
            "grouping": grouping, "source": cfg.get("source", "")}


def describe(drawn, teams):
    """给人看的一行摘要，跑重算脚本时打印出来供肉眼复核。

    第一行会被打进重算日志、也会被人直接抄进对外文案，所以分组是推的时候
    这里绝不能出现「分组已公布」——那是我们没有的东西。
    """
    if not drawn:
        return "分组未公布 —— 模拟器按原样随机化分组与首轮对阵"
    src = " · 来源：%s" % drawn["source"] if drawn["source"] else ""
    if drawn["group_vec"] is None:
        return ("首轮对阵已锁定，分组未知 —— 模拟器对 35 种与首轮自洽的分法平均" + src
                + "\n  首轮：" + "；".join("%s vs %s" % (teams[i], teams[j])
                                            for i, j in drawn["r1_pairs"]))
    ga = [t for t, g in zip(teams, drawn["group_vec"]) if g == 0]
    gb = [t for t, g in zip(teams, drawn["group_vec"]) if g == 1]
    head = ("分组已公布" if drawn["grouping"] == GROUPING_OFFICIAL
            else "⚠️ 分组为推测（官方未公布），首轮对阵已证实")
    out = [head + src,
           "  A 组：" + "、".join(ga),
           "  B 组：" + "、".join(gb)]
    if drawn["r1_pairs"]:
        out.append("  首轮：" + "；".join("%s vs %s" % (teams[i], teams[j])
                                          for i, j in drawn["r1_pairs"]))
    else:
        out.append("  首轮对阵未公布 —— 组内随机")
    return "\n".join(out)
