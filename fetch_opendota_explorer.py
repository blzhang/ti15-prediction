#!/usr/bin/env python3
"""
TI15 预测项目 — OpenDota /api/explorer SQL 端点抓取器 (proof of concept)

用法:
    python3 fetch_opendota_explorer.py --league 18324 --tag ti14
    python3 fetch_opendota_explorer.py --league 18324,16935,15728 --tag ti_recent

关键环境注意事项:
  1. 本机 HTTP(S)_PROXY=127.0.0.1:7890 会破坏 TLS 握手 -> 脚本内强制清掉代理。
  2. OpenDota 匿名额度: 60 req/min, ~2000 req/day (响应头 x-rate-limit-remaining-*)。
  3. explorer 端点有服务端查询读超时 -> 一律按 leagueid 分片，禁止全表扫描。
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# --- 必须: 清掉会破坏 TLS 的本地代理 ---
for _v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_v, None)
# 强制 urllib 不走任何代理
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)

API = "https://api.opendota.com/api/explorer"
UA = "TI15-Research/1.0 (academic match-prediction research; contact zzznbzzznb@gmail.com)"

# 全局限速状态：OpenDota 匿名 60/min
_MIN_INTERVAL = 1.1  # 秒/请求 -> ~54 req/min，留安全边际
_last_call = [0.0]
RATE = {"minute": None, "day": None}


def run_sql(sql, retries=3, timeout=60):
    """跑一条 SQL，返回 rows(list[dict])。自动限速 + 重试。"""
    for attempt in range(retries):
        wait = _MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        url = API + "?sql=" + urllib.parse.quote(sql)
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Encoding": "identity",   # 见下方 note
        })
        _last_call[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                RATE["minute"] = resp.headers.get("x-rate-limit-remaining-minute")
                RATE["day"] = resp.headers.get("x-rate-limit-remaining-day")
                body = resp.read().decode("utf-8")
            data = json.loads(body)
        except Exception as e:
            sys.stderr.write(f"  [retry {attempt+1}/{retries}] {type(e).__name__}: {e}\n")
            time.sleep(3 * (attempt + 1))
            continue
        if data.get("err"):
            sys.stderr.write(f"  [sql err] {data['err']}\n")
            # 查询超时通常重试也没用，直接抛
            raise RuntimeError(f"OpenDota explorer SQL error: {data['err']}")
        return data.get("rows", [])
    raise RuntimeError("run_sql failed after retries")


def write_csv(path, rows):
    if not rows:
        sys.stderr.write(f"  !! no rows for {path}\n")
        return 0
    cols = list(rows[0].keys())
    # union 所有 key，防止稀疏
    for r in rows[1:]:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return len(rows)


# ---------------------------------------------------------------- 查询定义

Q_MATCHES = """
SELECT m.match_id, m.leagueid, l.name AS league_name, l.tier AS league_tier,
       m.start_time, to_char(to_timestamp(m.start_time),'YYYY-MM-DD') AS match_date,
       m.duration, m.radiant_win,
       m.radiant_team_id, tr.name AS radiant_team_name, tr.tag AS radiant_team_tag,
       m.dire_team_id, td.name AS dire_team_name, td.tag AS dire_team_tag,
       m.radiant_score, m.dire_score,
       m.series_id, m.series_type,
       m.first_blood_time,
       m.tower_status_radiant, m.tower_status_dire,
       m.barracks_status_radiant, m.barracks_status_dire,
       m.radiant_captain, m.dire_captain,
       m.game_mode, m.lobby_type, m.human_players,
       mp.patch
FROM matches m
LEFT JOIN leagues l ON l.leagueid = m.leagueid
LEFT JOIN match_patch mp ON mp.match_id = m.match_id
LEFT JOIN teams tr ON tr.team_id = m.radiant_team_id
LEFT JOIN teams td ON td.team_id = m.dire_team_id
WHERE m.leagueid IN ({leagues})
ORDER BY m.start_time
"""

Q_PLAYER_MATCHES = """
SELECT pm.match_id, m.leagueid,
       to_char(to_timestamp(m.start_time),'YYYY-MM-DD') AS match_date,
       m.start_time,
       pm.account_id, np.name AS player_name, np.country_code, np.fantasy_role,
       pm.player_slot,
       (pm.player_slot < 128) AS is_radiant,
       CASE WHEN pm.player_slot < 128 THEN m.radiant_team_id ELSE m.dire_team_id END AS team_id,
       CASE WHEN pm.player_slot < 128 THEN tr.name ELSE td.name END AS team_name,
       ((pm.player_slot < 128) = m.radiant_win) AS won,
       pm.hero_id, h.localized_name AS hero_name,
       pm.kills, pm.deaths, pm.assists,
       pm.gold_per_min, pm.xp_per_min, pm.net_worth,
       pm.last_hits, pm.denies, pm.level,
       pm.hero_damage, pm.tower_damage, pm.hero_healing,
       pm.damage_taken IS NOT NULL AS has_detailed,
       pm.teamfight_participation,
       pm.lane, pm.lane_role, pm.is_roaming,
       pm.obs_placed, pm.sen_placed, pm.camps_stacked, pm.rune_pickups,
       pm.towers_killed, pm.roshans_killed, pm.firstblood_claimed,
       pm.stuns, pm.gold_spent, pm.leaver_status,
       m.duration
FROM player_matches pm
JOIN matches m ON m.match_id = pm.match_id
LEFT JOIN notable_players np ON np.account_id = pm.account_id
LEFT JOIN heroes h ON h.id = pm.hero_id
LEFT JOIN teams tr ON tr.team_id = m.radiant_team_id
LEFT JOIN teams td ON td.team_id = m.dire_team_id
WHERE m.leagueid IN ({leagues})
ORDER BY m.start_time, pm.match_id, pm.player_slot
"""

Q_PICKS_BANS = """
SELECT pb.match_id, m.leagueid,
       to_char(to_timestamp(m.start_time),'YYYY-MM-DD') AS match_date,
       pb.ord, pb.is_pick, pb.team,
       CASE WHEN pb.team = 0 THEN m.radiant_team_id ELSE m.dire_team_id END AS team_id,
       pb.hero_id, h.localized_name AS hero_name
FROM picks_bans pb
JOIN matches m ON m.match_id = pb.match_id
LEFT JOIN heroes h ON h.id = pb.hero_id
WHERE m.leagueid IN ({leagues})
ORDER BY pb.match_id, pb.ord
"""

# 派生名单：解决「选手-队伍时间对齐」
Q_ROSTER = """
SELECT pm.account_id, np.name AS player_name,
       CASE WHEN pm.player_slot < 128 THEN m.radiant_team_id ELSE m.dire_team_id END AS team_id,
       CASE WHEN pm.player_slot < 128 THEN tr.name ELSE td.name END AS team_name,
       count(*) AS games,
       to_char(to_timestamp(min(m.start_time)),'YYYY-MM-DD') AS first_game,
       to_char(to_timestamp(max(m.start_time)),'YYYY-MM-DD') AS last_game,
       min(m.start_time) AS first_ts, max(m.start_time) AS last_ts
FROM matches m
JOIN player_matches pm ON pm.match_id = m.match_id
LEFT JOIN notable_players np ON np.account_id = pm.account_id
LEFT JOIN teams tr ON tr.team_id = m.radiant_team_id
LEFT JOIN teams td ON td.team_id = m.dire_team_id
WHERE m.leagueid IN ({leagues})
GROUP BY 1,2,3,4
ORDER BY team_id, games DESC
"""

TASKS = [
    ("matches", Q_MATCHES),
    ("player_matches", Q_PLAYER_MATCHES),
    ("picks_bans", Q_PICKS_BANS),
    ("roster_derived", Q_ROSTER),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True, help="逗号分隔的 leagueid")
    ap.add_argument("--tag", required=True, help="输出文件名前缀")
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    args = ap.parse_args()

    leagues = ",".join(str(int(x)) for x in args.league.split(","))
    os.makedirs(args.outdir, exist_ok=True)

    summary = []
    for name, tmpl in TASKS:
        sql = tmpl.format(leagues=leagues).strip().replace("\n", " ")
        sys.stderr.write(f"[{name}] querying leagues={leagues} ...\n")
        t0 = time.time()
        rows = run_sql(sql)
        dt = time.time() - t0
        path = os.path.join(args.outdir, f"{args.tag}_{name}.csv")
        n = write_csv(path, rows)
        sys.stderr.write(f"[{name}] {n} rows in {dt:.1f}s -> {path} "
                         f"(quota min={RATE['minute']} day={RATE['day']})\n")
        summary.append((name, n, round(dt, 1), path))

    print("\n=== SUMMARY ===")
    for name, n, dt, path in summary:
        print(f"{name:<18} {n:>7} rows  {dt:>5}s  {path}")
    print(f"rate limit remaining: minute={RATE['minute']} day={RATE['day']}")


if __name__ == "__main__":
    main()
