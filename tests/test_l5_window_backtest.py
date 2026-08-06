"""对 model/l5_window_backtest.py 编排层的单元测试（全部走内联 fixture，
不读真实 CSV、不打网）。"""
import pandas as pd
import pytest

from model.l5_window_backtest import (HOLDOUTS, ITEMS, BASELINE_ARM, TREATMENT_ARM,
                                      ALPHA, MIN_HOLDOUTS_POSITIVE,
                                      holdout_participants, holdout_actuals,
                                      intersect_players)


def test_preregistered_decision_constants_are_what_the_spec_says():
    """判定规则是预注册的（spec §2）：跑完再改这几个常量就等于事后挑指标。
    这条测试的作用是让任何改动都必须显式地改到测试，而不是悄悄改掉。"""
    assert ALPHA == 0.05
    assert MIN_HOLDOUTS_POSITIVE == 3
    assert BASELINE_ARM == "L955d"
    assert TREATMENT_ARM == "patch"


def test_holdouts_are_the_four_preregistered_ti_events():
    assert [(h["year"], h["patch"]) for h in HOLDOUTS] == [
        ("2022", "7.32"), ("2023", "7.34"), ("2024", "7.37"), ("2025", "7.39")]


def test_items_are_the_twelve_csv_direct_scoring_items():
    """blob 三项 smokes/tormentor/courier 历史届取不到（pro_blob_stats.csv
    只覆盖 TI15 的 80 名选手、2024-01-01 起），必须排除。"""
    assert ITEMS == ["kills", "deaths", "creep_score", "gpm", "tower_kills",
                     "roshan", "teamfight", "wards", "camps_stacked", "runes",
                     "first_blood", "stuns"]
    assert "smokes" not in ITEMS and "tormentor" not in ITEMS and "courier" not in ITEMS


def _pm(rows):
    return pd.DataFrame(rows)


def test_holdout_participants_requires_min_games_in_that_event():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 5}] * 4
            + [{"match_date": "2025-09-05", "account_id": 2, "kills": 5}] * 2
            + [{"match_date": "2024-09-05", "account_id": 3, "kills": 5}] * 9)
    out = holdout_participants(_pm(rows), "2025", min_games=4)
    assert out == {1}


def test_holdout_actuals_averages_per_game_for_the_requested_year_only():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 10}] * 2
            + [{"match_date": "2025-09-06", "account_id": 1, "kills": 20}] * 2
            + [{"match_date": "2024-09-05", "account_id": 1, "kills": 999}] * 5)
    out = holdout_actuals(_pm(rows), "2025", "kills", min_games=4)
    assert out == {1: pytest.approx(15.0)}


def test_holdout_actuals_resolves_creep_score_as_last_hits_plus_denies():
    """预测侧和实际侧必须走同一套列合成（l3_player._resolve_item_values）。
    两边用不同的合成方式是这类回测最容易出、也最难发现的错。"""
    rows = [{"match_date": "2025-09-05", "account_id": 1,
             "last_hits": 300, "denies": 20}] * 4
    out = holdout_actuals(_pm(rows), "2025", "creep_score", min_games=4)
    assert out == {1: pytest.approx(320.0)}


def test_holdout_actuals_drops_players_below_min_games():
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "kills": 5}] * 4
            + [{"match_date": "2025-09-05", "account_id": 2, "kills": 5}] * 3)
    out = holdout_actuals(_pm(rows), "2025", "kills", min_games=4)
    assert set(out) == {1}


def test_holdout_actuals_counts_only_non_null_rows_toward_min_games():
    """teamfight_participation / stuns 在真实数据里有 NaN。口径必须与
    fit_rate_model 一致：n 按非空计，NaN 行不算出场。"""
    rows = ([{"match_date": "2025-09-05", "account_id": 1, "stuns": 3.0}] * 3
            + [{"match_date": "2025-09-05", "account_id": 1, "stuns": None}] * 5)
    out = holdout_actuals(_pm(rows), "2025", "stuns", min_games=4)
    assert out == {}


def test_intersect_players_keeps_only_players_predicted_by_every_arm():
    """臂之间人群不同就不是配对比较：短窗口会漏掉赛前歇了几个月的人，
    不取交集等于拿"全历史臂上的 18 人"跟"patch 臂上的 12 人"比。"""
    rates_by_arm = {"all": {1: 0.1, 2: 0.2, 3: 0.3},
                    "patch": {1: 0.1, 3: 0.3},
                    "L955d": {1: 0.1, 2: 0.2, 3: 0.3}}
    assert intersect_players(rates_by_arm) == {1, 3}


def test_intersect_players_on_empty_input_is_empty():
    assert intersect_players({}) == set()
