"""赔率去水与 log-odds 融合。

设计文档 §4.2：
  - 夺冠盘 overround 常在 1.20–1.40，不去水直接当概率会看到「每支队都被高估」的假象
  - 文献共识是融合优于对抗，市场权重建议 60–80%
"""
import math

W_MARKET_DEFAULT = 0.7   # §4.2 建议区间 0.6–0.8 的中点

W_BOOK_DEFAULT = 0.5     # 源间权重（庄家一侧）。2026-08-05 Polymarket 设计文档 §3：等权最不武断


def normalize(probs):
    """概率 dict 按比例归一化到和为 1。

    Polymarket 冠军盘 16 队 mid 价之和实测 ≈1.18——负风险市场同样有溢价，
    当概率用之前必须归一。空输入或任何非正值直接报错，不猜。
    """
    if not probs:
        raise ValueError("probs 不能为空")
    for k, v in probs.items():
        if v is None or v <= 0:
            raise ValueError("概率必须为正：%s=%r" % (k, v))
    s = sum(probs.values())
    return {k: v / s for k, v in probs.items()}


def devig(odds):
    """小数赔率 dict → 去水后概率 dict（比例法 / proportional normalisation）。"""
    if not odds:
        raise ValueError("odds 不能为空")
    for k, v in odds.items():
        if v is None or v <= 0:
            raise ValueError("赔率必须为正：%s=%r" % (k, v))
    raw = {k: 1.0 / v for k, v in odds.items()}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}


def blend_logodds(model_p, market_p, w_market=W_MARKET_DEFAULT):
    """在 log-odds 空间加权平均后重新归一化。

    w_market=0 → 纯模型；w_market=1 → 纯市场。
    """
    if set(model_p) != set(market_p):
        raise ValueError("两侧 key 必须一致")
    if not 0.0 <= w_market <= 1.0:
        raise ValueError("w_market 必须在 [0,1]")

    def logit(p):
        p = min(max(p, 1e-9), 1 - 1e-9)
        return math.log(p / (1 - p))

    z = {k: (1 - w_market) * logit(model_p[k]) + w_market * logit(market_p[k])
         for k in model_p}
    raw = {k: 1.0 / (1.0 + math.exp(-v)) for k, v in z.items()}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}


def blend_partial(model_p, decimal_odds, w_market=W_MARKET_DEFAULT):
    """只有部分队有盘口时的融合。

    做法：对有盘口的子集做条件去水与融合，保持该子集的总概率质量不变；
    无盘口的队保留纯模型概率。这样避免用「假的 null 赔率」污染结果。
    """
    priced = {k: v for k, v in decimal_odds.items() if v}
    if not priced:
        return dict(model_p)
    mass = sum(model_p[k] for k in priced)
    if mass <= 0:
        raise ValueError(
            "有盘口的 %d 支队在模型里的总概率质量 mass=%r（<=0），"
            "无法计算条件份额 model_p[k]/mass" % (len(priced), mass)
        )
    cond_model = {k: model_p[k] / mass for k in priced}
    cond_market = devig(priced)
    blended = blend_logodds(cond_model, cond_market, w_market)
    out = dict(model_p)
    for k in priced:
        out[k] = blended[k] * mass
    s = sum(out.values())
    return {k: v / s for k, v in out.items()}


def round_probs(probs, ndigits=6):
    """把概率 dict 四舍五入到 ndigits 位小数，用于 JSON 输出。

    Global Constraints：概率输出 JSON 一律 float，保 6 位小数。这个函数只做
    四舍五入，不重新归一化——归一化会把小数位又变长，抵消四舍五入的目的。
    n 个值各自四舍五入后，和与 1 的偏差上界约为 n * 0.5 * 10**-ndigits
    （例如 n=16, ndigits=6 时约 8e-6）；调用方应自行校验
    `abs(sum(out.values()) - 1.0) < tolerance`（推荐 tolerance=1e-5），
    不要在四舍五入之后再做归一化修正。
    """
    return {k: round(v, ndigits) for k, v in probs.items()}
