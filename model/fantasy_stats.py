"""L3 数据层：Fantasy 18 项计分项的抽取与可得性声明。

来源 06-fantasy-rules.md §F（客户端本地化文件一手核实）。
基础系数是服务端下发的 {f:helpstat_0..17}，静态提取不到 ——
因此本项目交付「分项产出矩阵」而非绝对总分（设计文档 §4.3）。

`idx` 对应客户端文案里的 helpstat_N 编号本身（06-fantasy-rules.md §F.1 的表格
就是按这个编号写的，只是为了可读性按颜色分块展示）—— 它是这一项在服务端
18 个系数里的身份编号，不是数组下标。下面按 idx 升序排列。
"""
import pandas as pd

# pool: red=核心向 / blue=辅助向 / green=节奏向（对应徽记颜色，06-fantasy-rules.md §F.1/§F.3）
# column=None 表示本地 CSV 无直接列（需 OpenDota JSON blob，或完全没有字段）；
# column 为二元组表示该项由多列相加构成——目前只有 Creep Score
# （客户端文案 "+{f:helpstat_2} per last hit or deny"，last_hits 与 denies 等价计分）。
# available=False 表示：完全没有任何字段（Watcher/Lotus），
#   或者只有语义不同的代理量——Madstone 的 item_uses->>'madstone_bundle'
#   量的是「用了疯石袋」，不是「采到疯石」，代理量不能冒充真值
#   （06-fantasy-rules.md §F.1 的 ⚠️ 行，§F.2 单独统计，不计入「确定性缺口」）。
SCORING_ITEMS = [
    {"idx": 0,  "key": "kills",         "pool": "red",   "column": "kills",                   "available": True},
    {"idx": 1,  "key": "deaths",        "pool": "red",   "column": "deaths",                  "available": True},
    {"idx": 2,  "key": "creep_score",   "pool": "red",   "column": ("last_hits", "denies"),   "available": True},
    {"idx": 3,  "key": "gpm",           "pool": "red",   "column": "gold_per_min",            "available": True},
    {"idx": 4,  "key": "tower_kills",   "pool": "red",   "column": "towers_killed",           "available": True},
    {"idx": 5,  "key": "roshan",        "pool": "green", "column": "roshans_killed",          "available": True},
    {"idx": 6,  "key": "teamfight",     "pool": "green", "column": "teamfight_participation", "available": True},
    {"idx": 7,  "key": "wards",         "pool": "blue",  "column": "obs_placed",              "available": True},
    {"idx": 8,  "key": "camps_stacked", "pool": "blue",  "column": "camps_stacked",           "available": True},
    {"idx": 9,  "key": "runes",         "pool": "blue",  "column": "rune_pickups",            "available": True},
    {"idx": 10, "key": "first_blood",   "pool": "green", "column": "firstblood_claimed",      "available": True},
    {"idx": 11, "key": "stuns",         "pool": "green", "column": "stuns",                   "available": True},
    {"idx": 12, "key": "smokes",        "pool": "blue",  "column": None,                      "available": True},
    {"idx": 13, "key": "madstone",      "pool": "red",   "column": None,                      "available": False},
    {"idx": 14, "key": "watchers",      "pool": "blue",  "column": None,                      "available": False},
    {"idx": 15, "key": "lotuses",       "pool": "blue",  "column": None,                      "available": False},
    {"idx": 16, "key": "tormentor",     "pool": "green", "column": None,                      "available": True},
    {"idx": 17, "key": "courier",       "pool": "green", "column": None,                      "available": True},
]

# smokes / tormentor / courier 需从 OpenDota 的 JSON blob 解出，本地 CSV 无列。
# 对应 explorer SQL：item_uses->>'smoke_of_deceit'、killed->>'npc_dota_miniboss'、
# killed->>'npc_dota_courier'（06-fantasy-rules.md §F.5 实跑验证，roshan=342 交叉校验通过）。
#
# 已按此口径抽取并落盘 data/pro_blob_stats.csv（80 名花名册选手、2024-01-01 起，
# 11810 场、49762 条 match_id×account_id 行，列为 match_id,account_id,smokes,
# tormentor,courier）。data/ 整体 gitignore（见仓库 .gitignore「可用 fetch_pro_all.py
# 重新拉取」的既有约定），此文件同理不进 git，需要时按 task-5-report.md 里的
# 查询重新跑一遍即可。本模块目前不读它——load_player_games 只吃单一 csv_path，
# 按 idx/key 把这三项接进选手-比赛表是下游任务（按 match_id+account_id 左连接）
# 的事，这里先把「能抽出来」这件事做完并验证。
NEEDS_BLOB = {"smokes", "tormentor", "courier"}


def _raw_columns(item):
    """把 SCORING_ITEMS 里的 column 字段（None / str / tuple）展开成列名列表。"""
    col = item["column"]
    if col is None:
        return ()
    if isinstance(col, (list, tuple)):
        return tuple(col)
    return (col,)


DIRECT_COLUMNS = sorted({c for i in SCORING_ITEMS if i["available"] for c in _raw_columns(i)})


def available_items(include_blob=True):
    out = [i for i in SCORING_ITEMS if i["available"]]
    if not include_blob:
        out = [i for i in out if i["key"] not in NEEDS_BLOB]
    return out


def load_player_games(csv_path, account_ids, since_ts):
    """读选手-比赛表，过滤到目标选手与时间窗，做类型与空值处理。

    只做「抽取可得原始列」，不做跨列合成（例如 Creep Score 的
    last_hits + denies 求和）：SCORING_ITEMS[i]["column"] 已经声明了每项
    对应哪些原始列，具体怎么合成留给下游（L3 速率模型）按 item 处理。

    同理不产出 position / duration_min：号位来自 model/rosters.py 的花名册
    （策展数据，这张表本身推不出可靠号位），局长要另 JOIN matches 表——
    两者都是下游任务按需拼接的责任，00-PLAN.md Task 6 Step 5 的真实用法
    就是 `df['position'] = df['account_id'].map(pos)`，并不依赖这里先造好。
    """
    usecols = ["match_id", "account_id", "player_slot", "hero_id", "start_time",
               "leagueid", "lane_role", "is_roaming"] + DIRECT_COLUMNS
    df = pd.read_csv(csv_path, usecols=lambda c: c in set(usecols), low_memory=False)
    df = df[df["account_id"].isin(set(account_ids))]
    df = df[df["start_time"].astype("int64") >= int(since_ts)]
    # is_roaming 63.6% 空是语义空（不是缺失），必须 fillna(False)（02-data-sources.md）。
    # 先转 pandas 可空 "boolean" 再 fillna，避免 object/float64 列直接 fillna(False)
    # 触发 pandas 2.x 的隐式 downcast FutureWarning（未来版本行为会变，这条 fillna
    # 恰恰是本函数最核心的正确性保证，不能留一个会被未来 pandas 版本悄悄改行为的写法）。
    if "is_roaming" in df.columns:
        df["is_roaming"] = df["is_roaming"].astype("boolean").fillna(False).astype(bool)
    for c in ("kills", "deaths", "assists", "last_hits", "denies", "obs_placed", "sen_placed",
              "camps_stacked", "rune_pickups", "towers_killed", "roshans_killed",
              "firstblood_claimed", "gold_per_min"):
        # gold_per_min 是整数型的每分钟经济，源数据缺失时应 fillna(0) 而不是
        # 留着 NaN——teamfight_participation/stuns 是小数计分项，不能同样
        # 转 int64，因此不在这个白名单里（见
        # test_load_player_games_casts_gold_per_min_and_fills_missing_with_zero）。
        if c in df.columns:
            df[c] = df[c].fillna(0).astype("int64")
    return df.reset_index(drop=True)
