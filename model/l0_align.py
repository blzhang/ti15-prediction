"""L0 实体对齐：用 80 个 account_id 反查各队历史 team_id 血统。

为什么不按队名匹配：TI15 有三支队因 Valve 禁博彩品牌名而改用"参赛名"
(BetBoom→BoomBoys / 1win→Iron Wing / PARIVISION→TEAM VISION)，
另有拼装队 (Vici=Tidebound3+Xtreme2) 和整体转会 (Tundra 阵容→Iron Wing)。
按名字匹配会静默丢历史；按选手反查则自动正确。

判据：某场比赛中若一方阵容含 ≥3 名该队当前首发，则该场归属该队血统。
"""
import csv, json, collections, datetime, os

D = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.dirname(__file__)
import sys; sys.path.insert(0, OUT)
from rosters import ROSTERS, ACCOUNT_TO_TEAM

MIN_SHARED = 3          # 一场比赛里至少几名当前首发同时在场，才算这支队的血统
SINCE = datetime.datetime(2024, 1, 1).timestamp()

teams_dim = {r["team_id"]: r["name"] for r in csv.DictReader(open(f"{D}/pro_dim_teams.csv"))}
leagues = {r["leagueid"]: r.get("name", "") for r in csv.DictReader(open(f"{D}/pro_dim_leagues.csv"))}

# pro_player_matches 没有 team_id 列，只有 player_slot：<128 = 天辉，>=128 = 夜魇。
# 必须回连 pro_matches 取 radiant_team_id / dire_team_id。
mt, m_rad, m_dire = {}, {}, {}
for r in csv.DictReader(open(f"{D}/pro_matches_2020_2026.csv")):
    mt[r["match_id"]] = int(r["start_time"])
    m_rad[r["match_id"]] = r["radiant_team_id"]
    m_dire[r["match_id"]] = r["dire_team_id"]

# 扫选手-比赛表，收集我们关心的 80 个 account 的出场
targets = set(map(str, ACCOUNT_TO_TEAM))
# (match_id, team_id) -> set(account_id)
side = collections.defaultdict(set)
with open(f"{D}/pro_player_matches_2020_2026.csv") as f:
    for r in csv.DictReader(f):
        if r["account_id"] not in targets:
            continue
        mid = r["match_id"]
        slot = r["player_slot"]
        if not slot.isdigit():
            continue
        tid = (m_rad if int(slot) < 128 else m_dire).get(mid, "")
        side[(mid, tid)].add(int(r["account_id"]))

# 对每支队，统计它的当前首发在哪些 team_id 下同时出场
lineage = {t: collections.Counter() for t in ROSTERS}
recent = {t: collections.Counter() for t in ROSTERS}
for (mid, tid), accts in side.items():
    if not tid or tid == "0":
        continue
    by_team = collections.Counter(ACCOUNT_TO_TEAM[a] for a in accts)
    for t, n in by_team.items():
        if n >= MIN_SHARED:
            lineage[t][tid] += 1
            if mt.get(mid, 0) >= SINCE:
                recent[t][tid] += 1

result = {}
print(f"{'TI15 队名':<17}{'血统 team_id':>12}  {'该 id 下场次':>10}  {'2024+ 场次':>9}  数据里的名字")
print("-" * 92)
for t in ROSTERS:
    ids = lineage[t].most_common()
    result[t] = [{"team_id": i, "games": c, "games_since_2024": recent[t][i],
                  "name": teams_dim.get(i, "?")} for i, c in ids if c >= 5]
    if not ids:
        print(f"{t:<17}{'—— 未找到 ——':>12}")
        continue
    for k, (i, c) in enumerate(ids[:4]):
        if c < 5:
            break
        print(f"{t if k==0 else '':<17}{i:>12}  {c:>10}  {recent[t][i]:>9}  {teams_dim.get(i,'?')[:34]}")

json.dump(result, open(f"{OUT}/lineage.json", "w"), indent=1, ensure_ascii=False)
print(f"\n→ 写入 {OUT}/lineage.json")
