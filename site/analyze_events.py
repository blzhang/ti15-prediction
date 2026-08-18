"""分析 /dota2 埋点事件日志。

数据源：服务器上的 /var/log/nginx/dota2-events.log（格式不含 IP）。
默认直接 ssh 拉取；也可用 --file 分析本地副本。

用法：
    python3 site/analyze_events.py                 # 从服务器拉并分析
    python3 site/analyze_events.py --file x.log    # 分析本地文件
    python3 site/analyze_events.py --days 3        # 只看最近 N 天
"""
import argparse
import collections
import re
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HOST = "vultr"
REMOTE = "/var/log/nginx/dota2-events.log"
BOT = re.compile(r"bot|spider|crawl|slurp|headless|python-requests|curl/|wget|monitor|uptime",
                 re.I)
PAGE_LABEL = {"index": "结论（首页）", "predictions": "预测详情", "methodology": "方法论",
              "data": "数据与检索", "homework": "作业（预测答案）",
              # 兼容改用自动取名之前的旧事件
              "pred": "预测详情(旧)", "meth": "方法论(旧)",
              "other": "未识别页面", "selftest": "自测（应排除）"}


def fetch(path=None):
    if path:
        return open(path, encoding="utf-8", errors="replace").read().splitlines()
    out = subprocess.run(["ssh", "-o", "ConnectTimeout=25", HOST,
                          # 轮转文件用 -* 而非 -*.gz：logrotate 转出的当天文件要到
                          # 下一轮才压缩，只匹配 .gz 会把它整天的数据漏掉
                          # （2026-08-17 就这么被漏成了"低谷"）。zcat -f 对未压缩文件等于 cat。
                          "cat %s 2>/dev/null; zcat -f %s-* 2>/dev/null || true" % (REMOTE, REMOTE)],
                         capture_output=True, text=True)
    if out.returncode != 0 and not out.stdout:
        raise SystemExit("拉取失败：%s" % out.stderr.strip()[:200])
    return out.stdout.splitlines()


def parse(lines, since=None):
    evs = []
    for ln in lines:
        parts = ln.split("|", 2)
        if len(parts) < 2:
            continue
        ts_s, args = parts[0], parts[1]
        ua = parts[2] if len(parts) > 2 else ""
        if BOT.search(ua):
            continue
        try:
            ts = datetime.fromisoformat(ts_s)
        except ValueError:
            continue
        if since and ts < since:
            continue
        kv = dict(p.split("=", 1) for p in args.split("&") if "=" in p)
        if kv.get("p") == "selftest":
            continue
        kv["_ts"] = ts
        evs.append(kv)
    return evs


def bar(n, mx, width=26):
    return "█" * max(0, round(n / mx * width)) if mx else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--days", type=int)
    args = ap.parse_args()

    since = None
    if args.days:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
    evs = parse(fetch(args.file), since)
    if not evs:
        print("没有可分析的事件（可能埋点刚上线，还没人访问）")
        return

    pv = [e for e in evs if e.get("e") == "pv"]
    sd = [e for e in evs if e.get("e") == "sd"]
    end = [e for e in evs if e.get("e") == "end"]

    lo = min(e["_ts"] for e in evs)
    hi = max(e["_ts"] for e in evs)
    print("=" * 62)
    print("  /dota2 埋点统计")
    print("  窗口：%s ～ %s（UTC）" % (lo.strftime("%m-%d %H:%M"), hi.strftime("%m-%d %H:%M")))
    print("=" * 62)

    print("\n【页面浏览】共 %d 次" % len(pv))
    per = collections.Counter(e.get("p", "?") for e in pv)
    mx = max(per.values()) if per else 1
    for p, c in per.most_common():
        print("  %-14s %4d  %s" % (PAGE_LABEL.get(p, p), c, bar(c, mx)))

    print("\n【来源】")
    ref = collections.Counter(e.get("r", "?") for e in pv)
    for r, c in ref.most_common(8):
        lbl = {"direct": "直接访问 / 无来源", "internal": "站内跳转"}.get(r, r)
        print("  %-26s %4d" % (lbl, c))

    print("\n【视口宽度】")
    W = {"s": "手机 <600", "m": "平板 600-1000", "l": "笔记本 1000-1500", "xl": "大屏 >1500"}
    wc = collections.Counter(e.get("w", "?") for e in pv)
    for w in ("s", "m", "l", "xl"):
        if wc.get(w):
            print("  %-18s %4d" % (W[w], wc[w]))

    # 滚动深度：每次浏览取到达的最大档
    print("\n【滚动深度】按页面，看内容是否被读完")
    reach = collections.defaultdict(dict)     # page -> {vid: maxdepth}
    for e in sd:
        try:
            d = int(e.get("d", 0))
        except ValueError:
            continue
        vid, p = e.get("id"), e.get("p", "?")
        reach[p][vid] = max(reach[p].get(vid, 0), d)
    pv_by_page = collections.Counter(e.get("p", "?") for e in pv)
    for p in sorted(reach, key=lambda x: -pv_by_page.get(x, 0)):
        tot = pv_by_page.get(p, 0) or len(reach[p])
        vals = reach[p]
        line = []
        for m in (25, 50, 75, 100):
            k = sum(1 for v in vals.values() if v >= m)
            line.append("%d%%:%3d(%3.0f%%)" % (m, k, k / tot * 100 if tot else 0))
        print("  %-14s 浏览 %3d → %s" % (PAGE_LABEL.get(p, p), tot, "  ".join(line)))

    # 停留时长
    print("\n【停留时长】按页面（秒）")
    dur = collections.defaultdict(list)
    for e in end:
        try:
            t = int(e.get("t", 0))
        except ValueError:
            continue
        if 0 < t <= 3600:
            dur[e.get("p", "?")].append(t)
    for p in sorted(dur, key=lambda x: -len(dur[x])):
        v = sorted(dur[p])
        med = statistics.median(v)
        p75 = v[int(len(v) * 0.75)] if len(v) > 3 else v[-1]
        over30 = sum(1 for x in v if x >= 30)
        print("  %-14s n=%3d  中位 %4.0f  p75 %4.0f  ≥30秒 %3d (%3.0f%%)"
              % (PAGE_LABEL.get(p, p), len(v), med, p75, over30, over30 / len(v) * 100))

    # 逐小时（北京时间）
    print("\n【逐小时页面浏览（北京时间）】")
    hrs = collections.Counter(((e["_ts"].hour + 8) % 24) for e in pv)
    mx = max(hrs.values()) if hrs else 1
    for h in sorted(hrs):
        print("  %02d:00  %3d  %s" % (h, hrs[h], bar(hrs[h], mx)))

    # 一句话结论
    print("\n" + "=" * 62)
    idx_pv = pv_by_page.get("index", 0)
    deep = sum(1 for v in reach.get("index", {}).values() if v >= 75)
    if idx_pv:
        print("  首页读到 75%% 以上的比例：%.0f%%（%d/%d）" % (deep / idx_pv * 100, deep, idx_pv))
    all_dur = [t for v in dur.values() for t in v]
    if all_dur:
        print("  全站停留中位数：%.0f 秒" % statistics.median(all_dur))
    print("=" * 62)


if __name__ == "__main__":
    main()
