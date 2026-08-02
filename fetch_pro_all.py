#!/usr/bin/env python3
"""
TI15 预测项目 — 全量职业比赛抓取器（2020-01-01 ~ 至今），断点续跑。

设计要点（全部基于实测，见 02-data-sources.md）:
  * 分片：按时间窗（年/月）切，每片一个 CSV，写完立刻落盘 + 记 state。
  * 续跑：state 文件记录已完成分片 key；重跑自动跳过。
  * 无 JOIN 原则：match 级不做 LEFT JOIN（teams/leagues/match_patch 单独整表 dump，
    本地再拼）。实测同样 3 万行，带 4 个 JOIN 要 300s+，不带 JOIN 只要 11.5s。
  * 限速：od_sql 内置 1.1s 最小间隔 + 读 x-rate-limit-remaining-* 头自适应。

用法:
  python3 fetch_pro_all.py dims                    # leagues / teams 维表
  python3 fetch_pro_all.py matches                 # 全量 match 级（按年分片）
  python3 fetch_pro_all.py patch                   # match_patch（按年分片）
  python3 fetch_pro_all.py player_matches --leagues-file tier1_leagues.txt
  python3 fetch_pro_all.py picks_bans   --leagues-file tier1_leagues.txt
  python3 fetch_pro_all.py merge <task>            # 合并分片
  python3 fetch_pro_all.py status
"""
import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from od_sql import run_sql, RATE  # noqa: E402

DATA = os.path.join(HERE, "data")
PARTS = os.path.join(DATA, "pro_parts")
STATE_PATH = os.path.join(DATA, "pro_fetch_state.json")
LOG_PATH = os.path.join(DATA, "pro_fetch.log")

TIER_FILTER = "l.tier IN ('premium','professional')"
START_2020 = 1577836800          # 2020-01-01T00:00:00Z
NOW_TS = int(time.time())


# ------------------------------------------------------------------ 基础设施
def log(msg):
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}"
    sys.stderr.write(line + "\n")
    os.makedirs(DATA, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"done": {}, "rowcounts": {}}


def save_state(st):
    os.makedirs(DATA, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1, sort_keys=True)
    os.replace(tmp, STATE_PATH)


def write_csv(path, rows):
    if not rows:
        # 空分片也要落一个带表头的空文件？不落，但 state 记 0，避免重复跑
        return 0
    cols = list(rows[0].keys())
    for r in rows[1:]:
        for k in r:
            if k not in cols:
                cols.append(k)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    os.replace(tmp, path)
    return len(rows)


def year_windows(t_start=START_2020, t_end=NOW_TS):
    """按自然年切片 -> [(key, lo, hi), ...]"""
    out = []
    y0 = datetime.fromtimestamp(t_start, timezone.utc).year
    y1 = datetime.fromtimestamp(t_end, timezone.utc).year
    for y in range(y0, y1 + 1):
        lo = int(datetime(y, 1, 1, tzinfo=timezone.utc).timestamp())
        hi = int(datetime(y + 1, 1, 1, tzinfo=timezone.utc).timestamp())
        out.append((str(y), max(lo, t_start), min(hi, t_end + 1)))
    return out


def month_windows(t_start=START_2020, t_end=NOW_TS):
    out = []
    y = datetime.fromtimestamp(t_start, timezone.utc).year
    m = datetime.fromtimestamp(t_start, timezone.utc).month
    while True:
        lo = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp())
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        hi = int(datetime(ny, nm, 1, tzinfo=timezone.utc).timestamp())
        if lo > t_end:
            break
        out.append((f"{y}-{m:02d}", max(lo, t_start), hi))
        y, m = ny, nm
    return out


def run_chunks(task, chunks, sql_fn, state, timeout=300):
    """通用分片执行：逐片跑、逐片落盘、逐片记 state。"""
    done = state["done"].setdefault(task, [])
    todo = [c for c in chunks if c[0] not in done]
    log(f"[{task}] {len(chunks)} chunks total, {len(todo)} to run")
    for i, chunk in enumerate(todo, 1):
        key = chunk[0]
        path = os.path.join(PARTS, f"{task}_{key}.csv")
        t0 = time.time()
        try:
            rows = run_sql(sql_fn(*chunk), timeout=timeout)
        except Exception as e:                        # noqa: BLE001
            log(f"[{task}] chunk {key} FAILED: {str(e)[:200]}")
            continue
        n = write_csv(path, rows)
        done.append(key)
        state["rowcounts"][f"{task}_{key}"] = n
        save_state(state)
        log(f"[{task}] {i}/{len(todo)} key={key} {n} rows in {time.time()-t0:.1f}s "
            f"(quota min={RATE['minute']} day={RATE['day']})")


# ------------------------------------------------------------------ 各任务
def task_dims(state):
    """维表：leagues / teams。整表小，一次性拉。"""
    for name, sql in [
        ("leagues", "SELECT leagueid, name, tier FROM leagues ORDER BY leagueid"),
        ("teams", "SELECT team_id, name, tag FROM teams ORDER BY team_id"),
    ]:
        if name in state["done"].get("dims", []):
            log(f"[dims] {name} already done, skip")
            continue
        t0 = time.time()
        rows = run_sql(sql, timeout=300)
        n = write_csv(os.path.join(DATA, f"pro_dim_{name}.csv"), rows)
        state["done"].setdefault("dims", []).append(name)
        state["rowcounts"][f"dims_{name}"] = n
        save_state(state)
        log(f"[dims] {name} {n} rows in {time.time()-t0:.1f}s")


M_COLS = """m.match_id, m.leagueid, m.start_time, m.duration, m.radiant_win,
            m.radiant_team_id, m.dire_team_id, m.radiant_score, m.dire_score,
            m.series_id, m.series_type, m.game_mode, m.lobby_type, m.human_players,
            m.first_blood_time, m.tower_status_radiant, m.tower_status_dire,
            m.barracks_status_radiant, m.barracks_status_dire,
            m.radiant_captain, m.dire_captain, m.version"""


def task_matches(state):
    def sql(key, lo, hi):
        return f"""SELECT {M_COLS}
                   FROM matches m JOIN leagues l ON l.leagueid = m.leagueid
                   WHERE {TIER_FILTER} AND m.start_time >= {lo} AND m.start_time < {hi}
                   ORDER BY m.start_time"""
    run_chunks("matches", year_windows(), sql, state)


def task_patch(state):
    def sql(key, lo, hi):
        return f"""SELECT mp.match_id, mp.patch
                   FROM match_patch mp
                   JOIN matches m ON m.match_id = mp.match_id
                   JOIN leagues l ON l.leagueid = m.leagueid
                   WHERE {TIER_FILTER} AND m.start_time >= {lo} AND m.start_time < {hi}"""
    run_chunks("patch", year_windows(), sql, state)


PM_COLS = """pm.match_id, pm.account_id, pm.player_slot, pm.hero_id,
             pm.kills, pm.deaths, pm.assists,
             pm.gold_per_min, pm.xp_per_min, pm.net_worth,
             pm.last_hits, pm.denies, pm.level,
             pm.hero_damage, pm.tower_damage, pm.hero_healing,
             pm.teamfight_participation, pm.lane, pm.lane_role, pm.is_roaming,
             pm.obs_placed, pm.sen_placed, pm.camps_stacked, pm.rune_pickups,
             pm.towers_killed, pm.roshans_killed, pm.firstblood_claimed,
             pm.stuns, pm.gold_spent, pm.leaver_status"""


def task_player_matches(state, leagues=None, windows=None):
    """player_matches 体量 ~ match 数 x10，按月分片；可用 leagues 白名单收窄。"""
    lf = f" AND m.leagueid IN ({leagues})" if leagues else ""

    def sql(key, lo, hi):
        return f"""SELECT {PM_COLS}, m.leagueid, m.start_time
                   FROM player_matches pm
                   JOIN matches m ON m.match_id = pm.match_id
                   JOIN leagues l ON l.leagueid = m.leagueid
                   WHERE {TIER_FILTER}{lf}
                     AND m.start_time >= {lo} AND m.start_time < {hi}"""
    run_chunks("player_matches", windows or month_windows(), sql, state, timeout=600)


def task_picks_bans(state, leagues=None, windows=None):
    lf = f" AND m.leagueid IN ({leagues})" if leagues else ""

    def sql(key, lo, hi):
        return f"""SELECT pb.match_id, pb.ord, pb.is_pick, pb.team, pb.hero_id,
                          m.leagueid, m.start_time
                   FROM picks_bans pb
                   JOIN matches m ON m.match_id = pb.match_id
                   JOIN leagues l ON l.leagueid = m.leagueid
                   WHERE {TIER_FILTER}{lf}
                     AND m.start_time >= {lo} AND m.start_time < {hi}"""
    run_chunks("picks_bans", windows or month_windows(), sql, state, timeout=600)


def task_merge(name):
    """合并分片 -> data/pro_<name>_2020_2026.csv（表头以第一个分片为准）。"""
    files = sorted(f for f in os.listdir(PARTS) if f.startswith(name + "_") and f.endswith(".csv"))
    if not files:
        log(f"[merge] no parts for {name}")
        return
    out = os.path.join(DATA, f"pro_{name}_2020_2026.csv")
    total, header = 0, None
    with open(out, "w", newline="", encoding="utf-8") as fo:
        w = None
        for fn in files:
            with open(os.path.join(PARTS, fn), newline="", encoding="utf-8") as fi:
                r = csv.DictReader(fi)
                if header is None:
                    header = r.fieldnames
                    w = csv.DictWriter(fo, fieldnames=header, extrasaction="ignore")
                    w.writeheader()
                for row in r:
                    w.writerow(row)
                    total += 1
    log(f"[merge] {name}: {len(files)} parts -> {total} rows -> {out}")


def task_status(state):
    print(json.dumps({k: len(v) for k, v in state["done"].items()}, indent=1))
    tot = {}
    for k, v in state["rowcounts"].items():
        tot[k.rsplit("_", 1)[0] if "_" in k else k] = None
    agg = {}
    for k, v in state["rowcounts"].items():
        task = k.split("_")[0] if not k.startswith(("player_matches", "picks_bans")) else \
            ("player_matches" if k.startswith("player_matches") else "picks_bans")
        agg[task] = agg.get(task, 0) + v
    print(json.dumps(agg, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--leagues", help="逗号分隔 leagueid 白名单")
    ap.add_argument("--leagues-file", help="每行一个 leagueid 的文件")
    ap.add_argument("--years", help="限定年份，如 2024,2025,2026")
    a = ap.parse_args()

    os.makedirs(PARTS, exist_ok=True)
    st = load_state()
    leagues = a.leagues
    if a.leagues_file:
        with open(a.leagues_file, encoding="utf-8") as f:
            ids = [ln.split("#")[0].strip() for ln in f]
        leagues = ",".join(x for x in ids if x.isdigit())

    wins = None
    if a.years:
        keep = set(a.years.split(","))
        wins = [w for w in month_windows() if w[0][:4] in keep]

    if a.task == "dims":
        task_dims(st)
    elif a.task == "matches":
        task_matches(st)
    elif a.task == "patch":
        task_patch(st)
    elif a.task == "player_matches":
        task_player_matches(st, leagues, wins)
    elif a.task == "picks_bans":
        task_picks_bans(st, leagues, wins)
    elif a.task == "merge":
        task_merge(a.arg)
    elif a.task == "status":
        task_status(st)
    else:
        ap.error(f"unknown task {a.task}")


if __name__ == "__main__":
    main()
