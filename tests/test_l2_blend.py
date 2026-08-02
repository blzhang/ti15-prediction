"""对 model/l2_blend.py 的测试。

设计文档 §8 验收标准 1「可复现：从原始 CSV 到最终概率，一条命令跑通，
无手工步骤」——`model/l2_blended.json` 最初（Task 2）是靠报告里一段内联
`python -c` 手打出来的，`model/` 下没有对应脚本；之后 Task 3（瑞士轮分轮
配对修正）、Task 4（双败结构+动态让分）都重新生成过 `model/l2_predictions.json`，
`l2_blended.json` 却从未跟着重新融合，两者从 Task 2 起就已经不同步。
task-23-report.md 记录了本次补脚本、补测试、重新产出并冻结的完整过程。

本项目已有 6 次"测试写了但测不到它声称要测的东西"的教训（历次
task-N-report.md 的评审记录），所以下面
`test_build_blend_reproduces_committed_l2_blended_json` 落地时做过变异
验证：临时改动磁盘上 model/l2_blended.json 里的一个数字，确认这条测试
真的会变红，再恢复——过程记录在 task-23-report.md，不在这里重复。
"""
import json

import pytest

from model.l2_blend import build_blend, main, DEFAULT_OUT
from model.market import blend_partial, round_probs, W_MARKET_DEFAULT


def test_build_blend_reproduces_committed_l2_blended_json():
    """核心不变量，本任务最重要的一条测试：用当前磁盘上的
    model/l2_predictions.json + model/market_odds.json（默认参数，真实
    文件、非合成数据）重新跑一遍融合，结果必须与磁盘上已经冻结的
    model/l2_blended.json 逐队精确相等（champion_blended 与 w_market
    都要对上）。

    这条测试锁定的不是"融合数学对不对"（那是 tests/test_market.py 的
    职责，devig/blend_logodds/blend_partial 本身的正确性已经在那边单独
    测过），而是"产出物是不是用当前的上游输入重新产出的"——以后任何人
    改了 model/l2_predictions.json 或 model/market_odds.json 却忘了重新
    跑 model/l2_blend.py，这条测试会直接变红，不会让两者继续静默漂移。
    """
    result = build_blend()
    with open(DEFAULT_OUT) as f:
        on_disk = json.load(f)

    assert result["w_market"] == on_disk["w_market"]
    assert result["champion_blended"] == on_disk["champion_blended"]


def test_build_blend_default_w_market_is_markets_shared_constant():
    """融合权重必须来自 market.py::W_MARKET_DEFAULT 这一份共享定义（0.7，
    设计文档 §4.2 建议区间 0.6-0.8 的中点），本脚本不应该另外重复写一份
    独立的 0.7 常量——否则以后 market.py 的默认值一改，这里会悄悄不再
    同步。"""
    assert W_MARKET_DEFAULT == 0.7
    result = build_blend()
    assert result["w_market"] == W_MARKET_DEFAULT


def test_build_blend_toy_example_is_a_thin_wrapper_not_a_reimplementation(tmp_path):
    """用不依赖真实 16 队数据的最小合成输入验证：build_blend() 只是
    market.py::blend_partial + round_probs 的薄封装，而不是重新实现了
    一遍融合数学（任务要求"复用...不要重写这些函数"）。期望值直接调用
    market.py 的公开函数手算，不是拍脑袋硬编码的数字。"""
    l2_path = tmp_path / "toy_l2.json"
    odds_path = tmp_path / "toy_odds.json"
    model = {"A": 0.5, "B": 0.3, "C": 0.2}
    odds = {"A": 2.0, "B": None, "C": 5.0}
    l2_path.write_text(json.dumps({"champion": model}))
    odds_path.write_text(json.dumps({"decimal_odds": odds}))

    result = build_blend(l2_path=str(l2_path), odds_path=str(odds_path), w_market=0.5)

    expected = round_probs(blend_partial(model, odds, w_market=0.5), 6)
    assert result == {"champion_blended": expected, "w_market": 0.5}
    # B 无盘口 → 必须精确保留纯模型概率，不能被市场信息污染
    assert result["champion_blended"]["B"] == pytest.approx(model["B"])


def test_main_cli_writes_file_matching_build_blend_return_value(tmp_path):
    """走 main()/CLI 这条真实入口（真实 16 队数据，`--out` 指向临时文件，
    不触碰仓库里已冻结的 model/l2_blended.json），验证"一条命令跑通"这条
    验收标准：写盘内容必须与直接调用 build_blend() 的返回值一致。"""
    out = str(tmp_path / "l2_blended.json")
    result = main(["--out", out])

    with open(out) as f:
        on_disk = json.load(f)
    assert on_disk == result
    assert on_disk["w_market"] == 0.7
    assert len(on_disk["champion_blended"]) == 16
    assert abs(sum(on_disk["champion_blended"].values()) - 1.0) < 1e-5
