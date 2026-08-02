"""8 队双败淘汰赛。

结构来源 01-ti15-facts.md §1.2（Liquipedia 逐槽位点数）：
  UB: QF 4 场 → SF 2 场 → UBF 1 场 = 7 场
  LB: R1 2 场 → QF 2 场 → SF 1 场 → LBF 1 场 = 6 场
  决赛 BO5，其余全 BO3，**无 bracket reset**
名次：1 冠 / 2 亚 / 3 = LBF 负 / 4 = LB SF 负 / 5-6 = LB QF 负 / 7-8 = LB R1 负
"""


def loser_games_prob(p_game):
    """BO3 中，在赢方获胜的条件下，输方拿到 1 小局的概率。

    收紧假设 A5：原实现用固定常数 0.4386（TI14 全局实测），
    但强弱悬殊时更可能 2-0、势均力敌时更可能 2-1，应随实力差变化。
    赢方 2-1 概率 = 2p²(1-p)；赢方总胜率 = p²(3-2p)。
    条件概率 = 2p²(1-p) / [p²(3-2p)]，p² 完全约去 = 2(1-p) / (3-2p)。
    """
    p = min(max(float(p_game), 1e-9), 1 - 1e-9)
    return 2 * (1 - p) / (3 - 2 * p)


def run_playoffs(seeds, p3, p5, rng):
    """seeds 为长度 8 的队伍索引列表，seeds[0] 为 1 号种子。返回 {队伍索引: 名次}。"""
    place = {}

    def m3(a, b):
        return a if rng.random() < p3[a, b] else b

    # UB QF：1v8 4v5 2v7 3v6
    qf = [(seeds[0], seeds[7]), (seeds[3], seeds[4]),
          (seeds[1], seeds[6]), (seeds[2], seeds[5])]
    ubw, ubl = [], []
    for a, b in qf:
        w = m3(a, b)
        ubw.append(w)
        ubl.append(b if w == a else a)

    sfw, sfl = [], []
    for a, b in ((ubw[0], ubw[1]), (ubw[2], ubw[3])):
        w = m3(a, b)
        sfw.append(w)
        sfl.append(b if w == a else a)

    ubf_w = m3(sfw[0], sfw[1])
    ubf_l = sfw[1] if ubf_w == sfw[0] else sfw[0]

    lb1w = []
    for a, b in ((ubl[0], ubl[1]), (ubl[2], ubl[3])):
        w = m3(a, b)
        lb1w.append(w)
        place[b if w == a else a] = 7

    lb2w = []
    for a, b in ((lb1w[0], sfl[1]), (lb1w[1], sfl[0])):
        w = m3(a, b)
        lb2w.append(w)
        place[b if w == a else a] = 5

    lbsf_w = m3(lb2w[0], lb2w[1])
    place[lb2w[1] if lbsf_w == lb2w[0] else lb2w[0]] = 4

    lbf_w = m3(lbsf_w, ubf_l)
    place[ubf_l if lbf_w == lbsf_w else lbsf_w] = 3

    champ = ubf_w if rng.random() < p5[ubf_w, lbf_w] else lbf_w   # 无 bracket reset
    place[champ] = 1
    place[lbf_w if champ == ubf_w else ubf_w] = 2
    return place
