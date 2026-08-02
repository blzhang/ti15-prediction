import numpy as np
import pandas as pd
import pytest
from model.fantasy_stats import SCORING_ITEMS, available_items, load_player_games


# ---- brief 给定的 4 条测试（Step 1，原样使用） ----

def test_eighteen_items_declared_with_pools():
    assert len(SCORING_ITEMS) == 18
    pools = {i["pool"] for i in SCORING_ITEMS}
    assert pools == {"red", "blue", "green"}
    assert sum(1 for i in SCORING_ITEMS if i["pool"] == "red") == 6
    assert sum(1 for i in SCORING_ITEMS if i["pool"] == "blue") == 6
    assert sum(1 for i in SCORING_ITEMS if i["pool"] == "green") == 6


def test_watcher_and_lotus_marked_unavailable():
    unavailable = {i["key"] for i in SCORING_ITEMS if not i["available"]}
    assert "watchers" in unavailable
    assert "lotuses" in unavailable


def test_blue_pool_coverage_is_four_of_six():
    """06-fantasy-rules.md 的结构性缺口：蓝池只有 4/6，Support 槽因此偏弱。"""
    blue = [i for i in SCORING_ITEMS if i["pool"] == "blue"]
    assert sum(1 for i in blue if i["available"]) == 4


def test_load_player_games_filters_and_types(tmp_path):
    csv = tmp_path / "pm.csv"
    csv.write_text(
        "match_id,account_id,player_slot,hero_id,kills,deaths,assists,gold_per_min,"
        "xp_per_min,net_worth,last_hits,denies,level,hero_damage,tower_damage,"
        "hero_healing,teamfight_participation,lane,lane_role,is_roaming,obs_placed,"
        "sen_placed,camps_stacked,rune_pickups,towers_killed,roshans_killed,"
        "firstblood_claimed,stuns,gold_spent,leaver_status,leagueid,start_time\n"
        "1,100,0,5,10,2,8,600,700,20000,300,20,25,40000,3000,0,0.5,2,1,,3,2,4,9,1,0,1,3.5,18000,0,99,1700000000\n"
        "1,200,128,7,1,9,3,250,300,5000,20,1,15,8000,100,500,0.4,3,4,,12,10,0,2,0,0,0,7.25,4500,0,99,1700000000\n"
        "2,100,1,5,4,4,4,500,550,15000,200,10,22,30000,1000,0,0.45,2,1,,2,1,3,5,0,1,0,2.0,14000,0,99,1600000000\n"
    )
    df = load_player_games(str(csv), account_ids={100}, since_ts=1650000000)
    assert list(df["account_id"].unique()) == [100]
    assert len(df) == 1, "1600000000 早于 since_ts，应被过滤"
    assert df["kills"].dtype.kind in "iu"
    assert "is_roaming" in df.columns
    assert df["is_roaming"].isna().sum() == 0, "语义空必须 fillna(False)，不可 dropna"


# ---- 补充测试：锁定对 brief Step 3 参考实现的两处修正 ----
#
# 1) idx 被 brief 参考实现按「池子分块后的数组下标」重新编了号，
#    与 06-fantasy-rules.md §F.1 / 客户端 helpstat_0..17 的真实编号对不上
#    （例如 brief 把 idx=16 分给了 first_blood，但客户端 helpstat_16 实际是
#    Tormentor Kills；idx=4 被分给 madstone，实际 helpstat_4 是 Tower Kills）。
#    聚合计数类断言（18/6-6-6、蓝池 4/6）在错误编号下也能通过，测不出这个问题，
#    所以单独锁定几个跨池边界的锚点。
#
# 2) Creep Score（idx 2）的服务端公式是
#    "+{f:helpstat_2} per last hit or deny"（06-fantasy-rules.md §A.6），
#    last_hits 和 denies 等价计分。brief 参考实现的 column 只填了
#    "last_hits"，denies 因此从未进入 usecols，被静默漏抽了一半原始信号。

def test_idx_matches_client_helpstat_identity():
    """idx 必须是 06-fantasy-rules.md §F.1 表格里的 helpstat_N 身份编号，
    不是数组下标。挑选跨池、原 brief 编号刚好会错位的几个点做回归锚点。"""
    by_key = {i["key"]: i["idx"] for i in SCORING_ITEMS}
    assert by_key["kills"] == 0
    assert by_key["deaths"] == 1
    assert by_key["creep_score"] == 2
    assert by_key["gpm"] == 3
    assert by_key["tower_kills"] == 4
    assert by_key["roshan"] == 5
    assert by_key["teamfight"] == 6
    assert by_key["wards"] == 7
    assert by_key["camps_stacked"] == 8
    assert by_key["runes"] == 9
    assert by_key["first_blood"] == 10
    assert by_key["stuns"] == 11
    assert by_key["smokes"] == 12
    assert by_key["madstone"] == 13
    assert by_key["watchers"] == 14
    assert by_key["lotuses"] == 15
    assert by_key["tormentor"] == 16
    assert by_key["courier"] == 17
    # idx 是身份编号：两两不同且覆盖 0..17
    assert sorted(by_key.values()) == list(range(18))


def test_red_pool_coverage_is_five_of_six_with_madstone_the_gap():
    """06-fantasy-rules.md §F.3：红池的唯一缺口是 Madstone
    （item_uses->>'madstone_bundle' 只是「用了疯石袋」，不等于「采到疯石」，
    仅代理量不算真值），其余 5 项直接可得。"""
    red = [i for i in SCORING_ITEMS if i["pool"] == "red"]
    assert sum(1 for i in red if i["available"]) == 5
    assert {i["key"] for i in red if not i["available"]} == {"madstone"}


def test_green_pool_is_fully_available():
    """06-fantasy-rules.md §F.3：绿池 6/6 全部可得
    （含需解 JSON blob 的 Tormentor Kills / Courier Kills）。"""
    green = [i for i in SCORING_ITEMS if i["pool"] == "green"]
    assert all(i["available"] for i in green)


def test_available_items_can_exclude_blob_derived():
    """available_items(include_blob=False) 应只剩本地 CSV 直接可用的 12 项；
    include_blob=True 再加上 smokes/tormentor/courier 共 15 项
    （18 - madstone - watchers - lotuses）。"""
    all_available = available_items(include_blob=True)
    direct_only = available_items(include_blob=False)
    assert len(all_available) == 15
    assert len(direct_only) == 12
    assert {i["key"] for i in all_available} - {i["key"] for i in direct_only} == {
        "smokes", "tormentor", "courier",
    }


def test_creep_score_pulls_in_denies_not_just_last_hits(tmp_path):
    """06-fantasy-rules.md: Creep Score 的服务端公式是
    "+{f:helpstat_2} per last hit or deny" —— last_hits 和 denies 等价计分，
    只抽 last_hits 会漏掉一半的原始信号。"""
    item = next(i for i in SCORING_ITEMS if i["key"] == "creep_score")
    assert item["available"] is True
    cols = item["column"] if isinstance(item["column"], (tuple, list)) else (item["column"],)
    assert "last_hits" in cols and "denies" in cols

    csv = tmp_path / "pm.csv"
    csv.write_text(
        "match_id,account_id,player_slot,hero_id,kills,deaths,assists,gold_per_min,"
        "xp_per_min,net_worth,last_hits,denies,level,hero_damage,tower_damage,"
        "hero_healing,teamfight_participation,lane,lane_role,is_roaming,obs_placed,"
        "sen_placed,camps_stacked,rune_pickups,towers_killed,roshans_killed,"
        "firstblood_claimed,stuns,gold_spent,leaver_status,leagueid,start_time\n"
        "1,100,0,5,10,2,8,600,700,20000,300,20,25,40000,3000,0,0.5,2,1,,3,2,4,9,1,0,1,3.5,18000,0,99,1700000000\n"
    )
    df = load_player_games(str(csv), account_ids={100}, since_ts=1650000000)
    assert "denies" in df.columns, "creep_score = last_hits + denies，denies 不能被漏抽"
    assert int(df.loc[0, "denies"]) == 20
