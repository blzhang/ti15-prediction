"""Dota 2 版本发布时间表。

来源：OpenDota `GET https://api.opendota.com/api/constants/patch`，
2026-08-06 取数。上游同一份数据也可在 odota/dotaconstants 的
build/patch.json 核对。

本仓既有约定是「跑的时候不打网」，所以取到的常量落盘并注明来源与取数日期，
不在运行时请求 API。只收录本次回测用得到的区间（7.31 起）。

缺项一律抛 KeyError，不静默回退——回退会让某届的 patch 臂悄悄退化成
全历史臂，而报告里看不出任何异常。
"""
import datetime

FETCHED_AT = "2026-08-06"

# 版本名 -> 发布时间（UTC，ISO 8601）。原样抄自 OpenDota constants/patch 的
# date 字段，只截掉毫秒（本仓所有时间窗都按秒比较）。
PATCH_RELEASE_UTC = {
    "7.31": "2022-02-23T23:46:14Z",
    "7.32": "2022-08-24T02:16:32Z",
    "7.33": "2023-04-21T01:22:56Z",
    "7.34": "2023-08-09T00:11:15Z",
    "7.35": "2023-12-14T16:07:43Z",
    "7.36": "2024-05-23T05:26:05Z",
    "7.37": "2024-08-01T07:30:27Z",
    "7.38": "2025-02-19T13:48:29Z",
    "7.39": "2025-05-22T23:36:01Z",
    "7.40": "2025-12-16T00:50:40Z",
    "7.41": "2026-03-24T00:50:59Z",
}


def patch_ts(name):
    """版本名 -> Unix 秒。查不到直接 KeyError（见模块 docstring）。"""
    if name not in PATCH_RELEASE_UTC:
        raise KeyError(
            "patches.py 里没有版本 %r；已收录 %s。不静默回退——回退会让该届的 "
            "patch 臂悄悄变成全历史臂。" % (name, sorted(PATCH_RELEASE_UTC)))
    dt = datetime.datetime.strptime(PATCH_RELEASE_UTC[name], "%Y-%m-%dT%H:%M:%SZ")
    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())


def previous_patch(name):
    """按发布时间排序取上一个版本名。最早的版本没有上一个 -> KeyError。"""
    patch_ts(name)   # 未知版本在这里统一抛 KeyError
    order = sorted(PATCH_RELEASE_UTC, key=patch_ts)
    i = order.index(name)
    if i == 0:
        raise KeyError("%r 是表里最早的版本，没有上一个版本" % name)
    return order[i - 1]
