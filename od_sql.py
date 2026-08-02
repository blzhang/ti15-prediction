#!/usr/bin/env python3
"""
OpenDota /api/explorer 通用 SQL 执行器（可 import，可 CLI 单跑）。

用法:
    python3 od_sql.py "SELECT count(*) FROM matches"
    python3 od_sql.py --file q.sql

环境铁律（实测，见 02-data-sources.md §0）:
  1. 本机 HTTP(S)_PROXY=127.0.0.1:7890 破坏 TLS -> 进程内强制清掉。
  2. 必须允许 gzip（requests 默认带；urllib 需显式），否则长响应被截断成非法 JSON。
  3. explorer 有服务端读超时 -> 查询必须窄（按 leagueid / 时间窗分片）。
"""
import json
import os
import sys
import time

# --- 必须: 清掉会破坏 TLS 的本地代理（在 import requests 之前） ---
for _v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy", "REQUESTS_CA_BUNDLE"):
    os.environ.pop(_v, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

import requests  # noqa: E402

API = "https://api.opendota.com/api/explorer"
UA = ("TI15-Research/1.0 (academic esports match-prediction research; "
      "contact zzznbzzznb@gmail.com)")

_SESSION = requests.Session()
_SESSION.trust_env = False          # 彻底忽略环境代理
_SESSION.headers.update({"User-Agent": UA, "Accept": "application/json"})

RATE = {"minute": None, "day": None}
_MIN_INTERVAL = 1.1                 # ~54 req/min，OpenDota 匿名限 60/min
_last_call = [0.0]


def run_sql(sql, retries=3, timeout=300, quiet=False):
    """跑一条 SQL -> rows(list[dict])。自适应限速 + 指数退避重试。"""
    sql = " ".join(sql.split())
    last_err = None
    for attempt in range(retries):
        # 限速：固定最小间隔 + 读响应头自适应
        wait = _MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        if RATE["minute"] is not None and int(RATE["minute"]) <= 3:
            if not quiet:
                sys.stderr.write("  [rate] minute quota low, sleeping 20s\n")
            time.sleep(20)
        _last_call[0] = time.time()
        try:
            r = _SESSION.get(API, params={"sql": sql}, timeout=timeout)
            RATE["minute"] = r.headers.get("x-rate-limit-remaining-minute", RATE["minute"])
            RATE["day"] = r.headers.get("x-rate-limit-remaining-day", RATE["day"])
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
        except Exception as e:                       # noqa: BLE001
            last_err = e
            if not quiet:
                sys.stderr.write(f"  [retry {attempt+1}/{retries}] "
                                 f"{type(e).__name__}: {str(e)[:180]}\n")
            time.sleep(4 * (2 ** attempt))           # 4s, 8s, 16s
            continue
        if data.get("err"):
            # 服务端查询错误（含 read timeout）：重试无益，直接抛
            raise RuntimeError(f"explorer SQL error: {data['err']}")
        return data.get("rows", [])
    raise RuntimeError(f"run_sql failed after {retries} retries: {last_err}")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    if args[0] == "--file":
        sql = open(args[1], encoding="utf-8").read()
    else:
        sql = args[0]
    t0 = time.time()
    rows = run_sql(sql)
    dt = time.time() - t0
    sys.stderr.write(f"[ok] {len(rows)} rows in {dt:.1f}s "
                     f"(quota min={RATE['minute']} day={RATE['day']})\n")
    print(json.dumps(rows, ensure_ascii=False, indent=1, default=str)[:20000])


if __name__ == "__main__":
    main()
