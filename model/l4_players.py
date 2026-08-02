"""L4-P3/P4：选手实力排名与个人数据预测。

两者都是 L3 后验的直接读出（00-DESIGN.md §3-L4："P3 排名 = L3 速率参数
直接排序"、"P4 个人数据 = L3 后验均值"）——本模块不重新建模、不重新估计
任何东西，只做排序与区间打包。关键是把不确定区间带出来：HULIGANI 只有
109 场样本，Team Liquid 有 1041 场，两队选手的区间宽度必须能看出明显
差别，否则说明 se 没有正确地一路从 L3 传递到这一层。

对 task-8-brief.md Step 3 参考实现的一处修正（详见 task-8-report.md 的
repro 记录与理由，已用 tests/test_l4_players.py 的新增测试锁定，不是
"默默改"）：

  `_interval` 原参考实现对 `rate ± Z95*se` 不做任何边界处理。本模块能读到
  的 15 个可得计分项（kills/deaths/creep_score/gpm/tower_kills/roshan/
  teamfight/wards/camps_stacked/runes/first_blood/stuns/smokes/tormentor/
  courier）全部是「每局计数」或「每局计数类比例」，物理意义上不可能为
  负——但当某项的后验均值本身接近 0（低频事件，例如某些位置的 Roshan
  参与、部分选手的 First Blood）且 se 相对偏大（小样本，典型如 HULIGANI
  这种只有 109 场的队伍）时，对称正态区间的下界会算出负数，报出一个
  "选手场均 Roshan 击杀 [-0.3, 0.5]"这种不可能存在的下界，对 Step 5 的
  人工抽查是明显的误导。brief 给的 4 条测试的 toy RATES（rate 只有
  4.0/8.0/9.0，se 最大 2.5）从未让下界跌破 3，结构上不可能暴露这个问题——
  跟 Task 5/6/7 report 记录的"toy 数据凑巧躲开了错误分支"是同一类空白。

  改为下界在 0 处截断（`max(0.0, lo)`）。**只单侧处理下界，不处理上界**：
  15 个可得项里 teamfight_participation / first_blood 概念上算"比例"、
  有 <=1 的上界，但 kills / gpm / creep_score 等大多数项是无上界的计数，
  而 `_interval` 本身不掌握"调用者传的是哪个 item"这个信息，不能不分
  青红皂白地给全部项都加上界=1 的截断。这是已知限制，不是漏改——
  task-8-report.md 会明确记录。
"""
Z95 = 1.959964   # 双侧 95% 正态临界值


def _interval(rate, se):
    """`rate ± Z95·se` 的正态近似区间，下界在 0 处截断。

    上游 L3（`model/l3_player.py::shrink`）产出的后验本身就是高斯共轭
    近似，这里直接复用同一个分布族出对称区间，不重新建模。但可得的
    15 个计分项全部是计数或计数类比例，不可能为负，下界因此必须 >= 0；
    上界不做类似处理（原因见模块 docstring）。
    """
    lo = rate - Z95 * se
    hi = rate + Z95 * se
    return max(0.0, lo), hi


def rank_players(rates, meta, by_position=True):
    """把 L3 单个计分项的 `{account_id: {"rate","se","position",...}}`
    输出，转成带排名和 95% 区间的行列表。

    rates: fit_rate_model() 对某一个 item_key 的输出。
    meta: {account_id: (name, team)}。缺失时回退为 (str(account_id), "?")。
    by_position=True：分位置分别排序（1 号位只跟 1 号位比，不跨位置）——
        "80 名参赛选手分位置排序"（00-DESIGN.md §2.2 P3）的字面要求，
        不同位置的同一计分项分布形状本来就不是一回事，直接混排没有意义。
    by_position=False：忽略位置，出一张全局总榜。
    """
    rows = []
    for acct, v in rates.items():
        name, team = meta.get(acct, (str(acct), "?"))
        lo, hi = _interval(v["rate"], v["se"])
        rows.append({"account_id": acct, "name": name, "team": team,
                     "position": v["position"], "rate": v["rate"],
                     "se": v["se"], "lo": lo, "hi": hi,
                     "n_games": v.get("n_games", 0),
                     "raw_rate": v.get("raw_rate")})
    if by_position:
        out = []
        for pos in sorted({r["position"] for r in rows}):
            grp = sorted([r for r in rows if r["position"] == pos],
                         key=lambda r: -r["rate"])
            for i, r in enumerate(grp, 1):
                r["rank"] = i
            out += grp
        return out
    rows.sort(key=lambda r: -r["rate"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def predict_player_stats(rates_by_item, items):
    """{item: L3 该项输出} × items 列表 → {account_id: {item: (均值, lo, hi)}}。

    单纯的读出+区间打包，不做跨 item 的任何合成或加权——每个 item 各自
    独立来自 L3 对该 item_key 单独拟合的速率模型。account 在某个 item 里
    不存在（例如样本量为 0 被上游过滤掉）时，该 (account, item) 组合
    静默跳过，不产出占位值，也不报错（跟 `model/l4_fantasy.py::player_matrix`
    对同类缺失的处理方式一致）。
    """
    out = {}
    for item in items:
        for acct, v in rates_by_item[item].items():
            lo, hi = _interval(v["rate"], v["se"])
            out.setdefault(acct, {})[item] = (v["rate"], lo, hi)
    return out
