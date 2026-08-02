"""赔率去水与 log-odds 融合。

设计文档 §4.2：
  - 夺冠盘 overround 常在 1.20–1.40，不去水直接当概率会看到「每支队都被高估」的假象
  - 文献共识是融合优于对抗，市场权重建议 60–80%
"""
import math

W_MARKET_DEFAULT = 0.7   # §4.2 建议区间 0.6–0.8 的中点


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
    cond_model = {k: model_p[k] / mass for k in priced}
    cond_market = devig(priced)
    blended = blend_logodds(cond_model, cond_market, w_market)
    out = dict(model_p)
    for k in priced:
        out[k] = blended[k] * mass
    s = sum(out.values())
    return {k: v / s for k, v in out.items()}
