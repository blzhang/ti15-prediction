/* 轻量埋点：零后端、零 cookie、零本地存储、零第三方。
 *
 * 原理：向 /dota2/px 发一个带查询串的信标，nginx 直接返回 204 并把查询串
 * 写进独立日志（日志格式不含 IP，见 deploy/nginx-dota2-px.conf）。
 * 没有数据库、没有服务端代码，分析由 site/analyze_events.py 离线跑。
 *
 * 采集什么：
 *   pv  页面浏览（含来源域名、视口宽度档）
 *   sd  滚动深度里程碑（25/50/75/100%，每档只发一次）
 *   end 离开页面时的停留秒数
 *
 * 不采集什么：
 *   - 不设 cookie / localStorage，刷新即换 ID，**无法跨页或跨次追踪个人**
 *   - 来源只取域名，不取完整 URL（完整 URL 可能带搜索词等个人信息）
 *   - 视口宽度只分 4 档，不取精确分辨率（避免指纹）
 *   - 不采集鼠标轨迹、点击坐标、输入内容
 *
 * 尊重 Do Not Track 与 Global Privacy Control：置位则完全不发。
 */
(function () {
  "use strict";
  try {
    var nav = navigator;
    if (nav.doNotTrack === "1" || window.doNotTrack === "1" ||
        nav.msDoNotTrack === "1" || nav.globalPrivacyControl) return;

    var BASE = "/dota2/px";
    // 每次页面浏览一个随机 ID，仅用于把 sd/end 事件join回同一次浏览。
    // 不落盘到客户端，页面一关就没了。
    var vid = Math.random().toString(36).slice(2, 10);
    var t0 = Date.now();
    var sent = {};

    // 从文件名自动取页面标识，不用写死的映射表——
    // 初版用固定映射，结果新加的 homework.html 全部掉进 "other"，
    // 18 次浏览被归成"未知页面"。新增页面不该需要改埋点。
    var page = (function () {
      var p = location.pathname.replace(/^\/dota2\/?/, "").replace(/\.html$/, "");
      if (!p || p === "index") return "index";
      // 只保留安全字符，截断，避免日志被畸形路径污染
      return p.replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 24) || "other";
    })();

    var ref = (function () {
      if (!document.referrer) return "direct";
      try {
        var h = new URL(document.referrer).hostname;
        return h === location.hostname ? "internal" : h;
      } catch (e) { return "unknown"; }
    })();

    // 视口尺寸拿不到时报 "?" 而不是猜一个档位——
    // 误报成 "手机" 会让统计得出"移动端占比很高"的假结论。
    var wbucket = (function () {
      var w = window.innerWidth || 0;
      if (!w) return "?";
      return w < 600 ? "s" : w < 1000 ? "m" : w < 1500 ? "l" : "xl";
    })();

    function send(params) {
      params.id = vid;
      params.p = page;
      var qs = Object.keys(params)
        .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]); })
        .join("&");
      var url = BASE + "?" + qs;
      if (nav.sendBeacon) { nav.sendBeacon(url); return; }
      var i = new Image(); i.src = url;   // 老浏览器回退
    }

    send({ e: "pv", r: ref, w: wbucket });

    // 滚动深度：每档只发一次
    // 返回 null 表示"测不出来"。视口高度为 0（无头环境、异常 UA）时
    // 若照算，会把深度算成一个偏低的假值，进而得出"没人往下读"的错误结论。
    // 宁可不发，也不发错的。
    function depth() {
      var vh = window.innerHeight || 0;
      if (!vh) return null;
      var doc = document.documentElement;
      var h = Math.max(doc.scrollHeight, document.body.scrollHeight, 1);
      var seen = (window.scrollY || doc.scrollTop || 0) + vh;
      return h <= vh ? 100 : Math.min(100, Math.round(seen / h * 100));
    }
    var ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        ticking = false;
        var d = depth();
        if (d === null) return;
        [25, 50, 75, 100].forEach(function (m) {
          if (d >= m && !sent["d" + m]) { sent["d" + m] = 1; send({ e: "sd", d: m }); }
        });
      });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();   // 短页面一进来就是 100%

    // 停留时长：页面隐藏或卸载时发一次
    var ended = false;
    function end() {
      if (ended) return;
      ended = true;
      send({ e: "end", t: Math.min(3600, Math.round((Date.now() - t0) / 1000)) });
    }
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") end();
    });
    window.addEventListener("pagehide", end);
  } catch (e) { /* 埋点永不影响页面本身 */ }
})();
