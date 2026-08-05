"""fetch_polymarket.py 解析层测试。全部走 fixture，不打网。

fixture 裁剪自 pm.json（2026-08-01 的 Gamma API 快照）：20 个市场，
16 支真实队 + 4 个占位盘（A/B/C/another team）。pm.json 本体未入库
（被 .gitignore 排除），入库的是它的裁剪版 fixture（tests/fixtures/polymarket_event.json）。
"""
import copy
import json
import os

import pytest

from fetch_polymarket import PM_NAME_MAP, parse_event, validate_prices


def _project_path(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, *parts)


@pytest.fixture
def event():
    with open(_project_path("tests", "fixtures", "polymarket_event.json")) as f:
        return json.load(f)


@pytest.fixture
def teams():
    with open(_project_path("model", "l2_predictions.json")) as f:
        return set(json.load(f)["champion"])


def test_name_map_is_exactly_the_iron_wing_entry():
    """唯一映射条目。依据 Liquipedia（lp_ti2026.txt:43 及引注 110-111）：
    Tundra 班底转入 1w Team，以 Iron Wing 名义参赛；Polymarket 用了组织名。"""
    assert PM_NAME_MAP == {"1w Team": "Iron Wing"}


def test_parse_maps_1w_team_to_iron_wing(event, teams):
    prices, _ = parse_event(event, teams)
    assert "Iron Wing" in prices
    assert "1w Team" not in prices
    # fixture 里 "Will 1w Team Win..." 的 Yes mid 是 0.065
    assert prices["Iron Wing"]["mid"] == pytest.approx(0.065)


def test_parse_excludes_placeholder_markets_and_covers_exactly_16(event, teams):
    prices, excluded = parse_event(event, teams)
    assert set(prices) == teams
    assert len(prices) == 16
    # 4 个占位盘（A/B/C/another team）靠「映射后不在 16 队名单内」自然排除
    assert len(excluded) == 4
    assert any("another team" in q for q in excluded)


def test_parse_extracts_mid_bid_ask_last(event, teams):
    prices, _ = parse_event(event, teams)
    aurora = prices["Aurora Gaming"]
    # fixture: outcomePrices '["0.065", "0.935"]'，bestBid 0.06，bestAsk 0.07，lastTrade 0.09
    assert aurora["mid"] == pytest.approx(0.065)
    assert aurora["bid"] == pytest.approx(0.06)
    assert aurora["ask"] == pytest.approx(0.07)
    assert aurora["last"] == pytest.approx(0.09)


def test_parse_fails_loudly_when_a_team_is_missing(event, teams):
    ev = copy.deepcopy(event)
    ev["markets"] = [m for m in ev["markets"]
                     if m["groupItemTitle"] != "Aurora Gaming"]
    with pytest.raises(ValueError, match="Aurora Gaming"):
        parse_event(ev, teams)


def test_parse_fails_loudly_on_duplicate_team(event, teams):
    ev = copy.deepcopy(event)
    dup = copy.deepcopy(ev["markets"][0])
    ev["markets"].append(dup)
    with pytest.raises(ValueError, match="重复"):
        parse_event(ev, teams)


def test_validate_rejects_mid_outside_unit_interval():
    bad = {"X": {"mid": 0.0, "bid": None, "ask": None, "last": None}}
    with pytest.raises(ValueError):
        validate_prices(bad)


def test_validate_rejects_sum_outside_sentinel_band():
    # 16 队 mid 全 0.03 → 和 0.48，低于哨兵下界 0.8（像是抓到了占位价）
    bad = {"T%d" % i: {"mid": 0.03, "bid": None, "ask": None, "last": None}
           for i in range(16)}
    with pytest.raises(ValueError):
        validate_prices(bad)


def test_validate_accepts_real_snapshot(event, teams):
    # 2026-08-01 快照的 16 队 mid 之和 ≈1.31，应落在 [0.8, 1.5] 哨兵区间内
    prices, _ = parse_event(event, teams)
    validate_prices(prices)


from fetch_polymarket import build_output


def test_build_output_schema_and_provenance(event, teams):
    prices, excluded = parse_event(event, teams)
    out = build_output(event, prices, excluded, "2026-08-05T09:00:00Z")
    assert out["source"] == "Polymarket Gamma API"
    assert out["event_slug"] == event["slug"]
    assert out["captured_utc"] == "2026-08-05T09:00:00Z"
    assert out["event_liquidity"] == event["liquidity"]
    assert out["event_volume"] == event["volume"]
    assert set(out["prices"]) == teams
    assert out["name_map_applied"] == {"1w Team": "Iron Wing"}
    assert len(out["excluded_markets"]) == 4
