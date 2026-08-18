/* 抄作业页主赛事对阵表的编辑器：在图上直接点，钉住的格子保持不动，其余重搜最优。

   位定义（一份自洽填法 = 一个 14 位整数，0 表示「上面那个候选」）与
   model/l6_playoffs.py 的 expand() 完全一致。完整的表在
   docs/superpowers/specs/2026-08-18-bracket-editor-design.md 决定一。

   ⚠️ 改这里必须同步改 model/l6_playoffs.py——tests/test_bracket_bits.py 会用 node
   跑本文件的 expand，与 Python 版逐位比对全部 16384 种展开。两边漂移不会崩溃，
   只会让页面静静印出一个跟模型对不上的期望答对数，所以那条测试是必须的。

   纯前端：无后端、无 cookie，填法编进 URL 的 #hash。 */
(function (root) {
  "use strict";

  var BIT_STAGE = ["UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2",
                   "LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "UBF",
                   "LBF", "GF"];
  var N_BITS = BIT_STAGE.length;
  var N_BRACKETS = 1 << N_BITS;          // 16384

  /* ---------- 路径规则 ---------- */

  /* 把 14 位整数展开成一份自洽填法，并顺带给出每一格的两位候选。

     pairs[阶段][side] 就是该位取 side 时选中的那一方——这个顺序与
     site/bracket_svg.py 的 _layout() 画上下两行的顺序一致（有测试钉住），
     所以「点上面那一行」= side 0，不需要任何额外映射。 */
  function derive(qf, bits) {
    var b = [], k;
    for (k = 0; k < N_BITS; k++) b.push((bits >> k) & 1);
    var w = [], l = [];
    for (k = 0; k < 4; k++) { w.push(qf[k][b[k]]); l.push(qf[k][1 - b[k]]); }
    var e = b[4], f = b[5];
    var sfW = [w[e], w[2 + f]];            // E / F 的胜者
    var sfL = [w[1 - e], w[3 - f]];        // E / F 的败者
    var lb1 = [l[b[6]], l[2 + b[7]]];      // 败1上 / 败1下的胜者
    // 败者组交叉：败2上 = 败1上胜者 vs F 的败者；败2下 = 败1下胜者 vs E 的败者
    var q1 = [lb1[0], sfL[1]], q2 = [lb1[1], sfL[0]];
    var lb2 = [q1[b[8]], q2[b[9]]];
    var lb3 = lb2[b[10]];
    var ubfW = sfW[b[11]], ubfL = sfW[1 - b[11]];
    var lbfOpts = [lb3, ubfL], lbf = lbfOpts[b[12]];
    var gfOpts = [ubfW, lbf], champ = gfOpts[b[13]];

    var vals = [w[0], w[1], w[2], w[3], sfW[0], sfW[1],
                lb1[0], lb1[1], lb2[0], lb2[1], lb3, ubfW, lbf, champ];
    var picks = {};
    for (k = 0; k < N_BITS; k++) picks[BIT_STAGE[k]] = vals[k];

    return {
      picks: picks,
      pairs: {
        "UBQF1": qf[0], "UBQF2": qf[1], "UBQF3": qf[2], "UBQF4": qf[3],
        "UBSF1": [w[0], w[1]], "UBSF2": [w[2], w[3]],
        "LBR1-1": [l[0], l[1]], "LBR1-2": [l[2], l[3]],
        "LBQF-1": q1, "LBQF-2": q2,
        "LBSF": lb2, "UBF": sfW, "LBF": lbfOpts, "GF": gfOpts
      }
    };
  }

  function expand(qf, bits) { return derive(qf, bits).picks; }

  /* 期望答对数。winP[阶段][队] 是**边缘**概率——某队真的赢下某一场，
     与你在别的格子填了什么无关。所以算分永远是查表，不需要重跑任何模拟。 */
  function score(winP, picks) {
    var s = 0;
    for (var i = 0; i < N_BITS; i++) {
      var st = BIT_STAGE[i];
      s += winP[st][picks[st]] || 0;
    }
    return s;
  }

  /* 在满足 pinned 的自洽填法里搜期望最高的一份。无解返回 -1。
     16384 × 14 次查表，实测毫秒级，不需要任何剪枝。 */
  function bestGiven(qf, winP, pinned) {
    var bestBits = -1, bestSc = -1, st;
    for (var bits = 0; bits < N_BRACKETS; bits++) {
      var picks = expand(qf, bits), ok = true;
      for (st in pinned) {
        if (pinned.hasOwnProperty(st) && picks[st] !== pinned[st]) { ok = false; break; }
      }
      if (!ok) continue;
      var sc = score(winP, picks);
      if (sc > bestSc) { bestSc = sc; bestBits = bits; }
    }
    return bestBits;
  }

  /* 钉住集合可能互相矛盾：改了 A 格之后，E 格钉的那支队可能已经被淘汰了。

     规则（设计文档决定二）：从最老的钉开始逐个丢，直到有解。
     pins 数组的最后一个是本次点击，所以「丢最老的」天然跳过它——
     这正是要的行为：你最近点的那一下永远生效。

     通过 UI 点出来的钉一定有解（点的就是当前填法下的候选），
     所以循环最多丢到只剩本次点击。全丢光的兜底只服务于手改 URL 的情形。 */
  function resolve(qf, winP, pins) {
    var p = pins.slice();
    while (p.length) {
      var pinned = {};
      for (var i = 0; i < p.length; i++) pinned[p[i].stage] = p[i].team;
      var bits = bestGiven(qf, winP, pinned);
      if (bits >= 0) return { bits: bits, pins: p };
      p.shift();
    }
    return { bits: bestGiven(qf, winP, {}), pins: [] };
  }

  /* ---------- 状态 ---------- */
  var D = null;          // bracket_data() 给的那个对象
  var bits = 0;          // 当前填法
  var pins = [];         // [{stage, team}]，按点击时间从老到新
  var editable = false;  // 窄屏只读（见 Task 7）

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function $(id) { return document.getElementById(id); }

  function pinnedMap() {
    var m = {};
    for (var i = 0; i < pins.length; i++) m[pins[i].stage] = pins[i].team;
    return m;
  }

  /* ---------- 渲染：SVG ---------- */

  /* 只改文本与属性，不重建 SVG。连线、坐标、列头都不随填法变，重建它们是白费；
     而且构建时 Python 输出的那一份正好当无 JS 回退。 */
  function paintSvg(picks, pairs, pinMap) {
    for (var i = 0; i < N_BITS; i++) {
      var st = BIT_STAGE[i], pair = pairs[st], isPinned = pinMap[st] !== undefined;
      for (var side = 0; side < 2; side++) {
        var nm = $("bk-" + st + "-" + side + "-nm");
        if (!nm) continue;                       // 非交互版渲染，什么都不做
        var dot = $("bk-" + st + "-" + side + "-dot");
        var pv = $("bk-" + st + "-" + side + "-p");
        var team = pair[side], on = team === picks[st];
        nm.textContent = D.short[team] || team;
        nm.setAttribute("class", on ? "tm on" : "tm");
        dot.setAttribute("fill", on ? "var(--s1)" : "none");
        dot.setAttribute("stroke", on ? "var(--s1)" : "var(--ink-muted)");
        // 钉住的那一格描粗一圈，与「它替我算的」区分开
        dot.setAttribute("stroke-width", on && isPinned ? "3.2" : "1.4");
        pv.textContent = on ? (D.win_p[st][team] * 100).toFixed(0) + "%" : "";
      }
    }
  }

  /* ---------- 渲染：逐场卡片 ---------- */

  /* 「这一格还可能出现」列的是与填法无关的全表 top——它是卡片相对于图的增量信息。
     八强那四场对阵固定，其余队概率为 0，这一段自然不显示。 */
  function alsoPossible(st, pair) {
    var rows = [], t;
    for (t in D.win_p[st]) {
      if (D.win_p[st].hasOwnProperty(t) && pair.indexOf(t) < 0 && D.win_p[st][t] > 0.005) {
        rows.push([t, D.win_p[st][t]]);
      }
    }
    rows.sort(function (a, b) { return b[1] - a[1]; });
    return rows.slice(0, 3);
  }

  function cardHtml(st, picks, pairs, pinMap) {
    var pair = pairs[st], pick = picks[st];
    var other = pair[0] === pick ? pair[1] : pair[0];
    var meta = D.meta[st];
    var also = alsoPossible(st, pair);
    var alsoHtml = also.length
      ? '<div class="picksub">这一格还可能出现</div>' + also.map(function (r) {
          return '<div class="pick"><span class="t">' + esc(r[0]) +
                 '</span><span class="p">' + (r[1] * 100).toFixed(0) + "%</span></div>";
        }).join("")
      : "";
    return '<div class="hwcard' + (pinMap[st] !== undefined ? " pinned" : "") + '">' +
           '<div class="hwhead"><b>' + esc(meta.panel) + "</b><span>" +
           esc(meta.cn) + " · " + esc(meta.time) +
           (pinMap[st] !== undefined ? ' · <i class="pinlab">你钉的</i>' : "") +
           "</span></div>" +
           '<div class="pickbig">' + esc(pick) + "</div>" +
           '<div class="picksub">这一场它赢的概率 ' +
           (D.win_p[st][pick] * 100).toFixed(1) + "%　｜　另一个候选</div>" +
           '<div class="pick"><span class="t">' + esc(other) + '</span><span class="p">' +
           (D.win_p[st][other] * 100).toFixed(1) + "%</span></div>" + alsoHtml + "</div>";
  }

  /* ⚠️ 分组标题与 site/homework.py:bracket_section 里那三个 <h3> 是重复的一份：
     JS 覆盖 #bkcards 的全部内容，所以两处都要写。改一处必须改另一处，
     否则读者在 JS 加载前后会看到两套不同的小标题。 */
  function paintCards(picks, pairs, pinMap) {
    var wrap = $("bkcards");
    if (!wrap) return;
    var groups = [
      ["胜者组（4 + 2 + 1 场）", ["UBQF1", "UBQF2", "UBQF3", "UBQF4", "UBSF1", "UBSF2", "UBF"]],
      ["败者组（2 + 2 + 1 + 1 场）", ["LBR1-1", "LBR1-2", "LBQF-1", "LBQF-2", "LBSF", "LBF"]],
      ["总决赛", ["GF"]]
    ];
    var html = "";
    for (var g = 0; g < groups.length; g++) {
      html += "<h3>" + groups[g][0] + '</h3><div class="hwgrid">';
      for (var i = 0; i < groups[g][1].length; i++) {
        html += cardHtml(groups[g][1][i], picks, pairs, pinMap);
      }
      html += "</div>";
    }
    wrap.innerHTML = html;
  }

  /* ---------- 渲染：分数条 ---------- */
  function paintStats(picks) {
    // best 与 mine 现在同源：都是查 D.win_p 表算出来的，不再有一个来自 Python
    // 一个来自 JS 的两条独立路径——D.bits 是模型给的、无任何钉住的原始推荐，
    // 从没被本文件改写过，恒等于「模型最优那份填法」。
    var mine = score(D.win_p, picks), best = score(D.win_p, expand(D.qf, D.bits));
    var set = function (id, txt) { var el = $(id); if (el) el.textContent = txt; };
    set("bk-exp", mine.toFixed(2));
    set("bk-best", best.toFixed(2));
    set("bk-delta", (mine - D.stats.random).toFixed(2));
    var bar = $("bk-bar");
    if (bar) bar.style.width = Math.max(0, Math.min(100, mine / N_BITS * 100)).toFixed(1) + "%";
    var st = $("bk-status");
    if (!st) return;
    if (!pins.length) {
      st.textContent = "这是模型算出来的最优填法";
      st.className = "pkstat ok";
    } else if (mine >= best - 1e-9) {
      st.textContent = "钉了 " + pins.length + " 格，仍然是最优填法";
      st.className = "pkstat ok";
    } else {
      st.textContent = "钉了 " + pins.length + " 格，期望少了 " +
                       (best - mine).toFixed(2) + " 场";
      st.className = "pkstat warn";
    }
  }

  function paint() {
    var d = derive(D.qf, bits), pinMap = pinnedMap();
    paintSvg(d.picks, d.pairs, pinMap);
    paintCards(d.picks, d.pairs, pinMap);
    paintStats(d.picks);
  }

  /* ---------- 分享链接 ---------- */

  /* 编码 = 14 位填法 + 14 位钉住掩码，各 3 个 base36 字符（36^3 = 46656 > 16384）。

     钉住掩码必须一起编：只编填法的话，别人打开你的链接看到的是一份「全部由模型
     算出来的」填法，分不出哪几格是你自己的判断——而那恰恰是你想分享的东西。

     顺序不编码。pins 的先后只在冲突解钉时起作用，而接收方拿到的状态本身是自洽的，
     他继续点时按位序恢复的顺序照样能工作。为 6 个字符再加一段顺序编码不划算。 */
  function pad3(n) {
    var s = n.toString(36);
    return "000".slice(s.length) + s;
  }

  function encode() {
    var mask = 0, pinMap = pinnedMap();
    for (var i = 0; i < N_BITS; i++) {
      if (pinMap[BIT_STAGE[i]] !== undefined) mask |= (1 << i);
    }
    return pad3(bits) + pad3(mask);
  }

  function readHash() {
    var m = /(?:^|[#&])b=([0-9a-z]{6})(?:&|$)/.exec(location.hash || "");
    if (!m) return false;
    var v = parseInt(m[1].slice(0, 3), 36), mask = parseInt(m[1].slice(3), 36);
    if (isNaN(v) || isNaN(mask) || v < 0 || v >= N_BRACKETS || mask < 0 ||
        mask >= N_BRACKETS) return false;
    var picks = expand(D.qf, v), p = [];
    for (var i = 0; i < N_BITS; i++) {
      if (mask & (1 << i)) p.push({ stage: BIT_STAGE[i], team: picks[BIT_STAGE[i]] });
    }
    // 走一遍 resolve 而不是直接采信：链接可以被手改，非法的钉在这里被丢掉，
    // 页面退回到一份合法填法，而不是渲染出一张自相矛盾的表。
    var r = resolve(D.qf, D.win_p, p);
    bits = r.bits;
    pins = r.pins;
    return true;
  }

  function writeHash() {
    try { history.replaceState(null, "", "#b=" + encode()); } catch (e) {}
  }

  function share(btn) {
    var url = location.origin + location.pathname + "#b=" + encode();
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "已复制链接 ✓";
      setTimeout(function () { btn.textContent = old; }, 1800);
    };
    // 文档失焦、权限被拒都会让 writeText 走拒绝分支——那时候剪贴板里其实还是
    // 旧内容，不能照样显示「已复制」，得落回 prompt 让读者自己复制。
    var fallback = function () { window.prompt("复制这个链接分享给别人：", url); };
    if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, fallback);
    else fallback();
  }

  /* ---------- 交互 ---------- */

  /* 点某格的某一侧 = 钉住「这支队赢下这一格」。

     钉的是**队伍**不是位置：位置（「上面那一行」）的含义随前面的选择变化，
     钉位置会让读者看到「我明明钉了这一格，怎么队伍自己变了」。 */
  function pick(stage, side) {
    if (!editable) return;
    var team = derive(D.qf, bits).pairs[stage][side];
    var kept = [];
    for (var i = 0; i < pins.length; i++) {
      if (pins[i].stage !== stage) kept.push(pins[i]);
    }
    kept.push({ stage: stage, team: team });      // 本次点击永远排在最后
    var r = resolve(D.qf, D.win_p, kept);
    bits = r.bits;
    pins = r.pins;
    paint();
    writeHash();
  }

  function reset() {
    pins = [];
    bits = D.bits;
    paint();
    writeHash();
  }

  /* 窄屏只读（设计文档决定五）。

     每行热区在窄屏约 159×21 CSS px，且要横向滚动才能找到格子——在手机上这是个
     **会点错**的功能，不是个不好用的功能：任何一次点击都产生一份合法填法，
     点错不报错。所以窄屏干脆不绑。

     断点复用 style.css 里 SVG 开始横滚的那一个（940px），不引入第二个阈值。
     用 change 事件跟随窗口变化，而不是只在加载时判一次——否则读者把窗口拉宽后
     会发现还是点不动。 */
  function watchWidth() {
    var mq = window.matchMedia("(min-width: 940px)");
    var apply = function () {
      editable = mq.matches;
      var wrap = $("bkwrap");
      if (wrap) wrap.className = "bkwrap" + (editable ? " editable" : "");
    };
    apply();
    if (mq.addEventListener) mq.addEventListener("change", apply);
    else if (mq.addListener) mq.addListener(apply);      // Safari < 14
  }

  /* ---------- 入口 ---------- */
  function init(data) {
    D = data;
    bits = data.bits;
    pins = [];
    watchWidth();
    if (!readHash()) { bits = data.bits; pins = []; }
    paint();

    document.addEventListener("click", function (ev) {
      var hit = ev.target.closest && ev.target.closest(".bkhit");
      if (hit) { pick(hit.getAttribute("data-stage"), +hit.getAttribute("data-side")); return; }
      // 用 closest() 而不是 ev.target.id：按钮里将来加个图标或 <span>，
      // 点在子元素上不该静默失效。share() 要拿到按钮本身（它要改按钮文字），
      // 所以传 closest() 找到的那个元素，不是 ev.target。
      var resetBtn = ev.target.closest && ev.target.closest("#bk-reset");
      if (resetBtn) { reset(); return; }
      var shareBtn = ev.target.closest && ev.target.closest("#bk-share");
      if (shareBtn) { share(shareBtn); return; }
    });

    window.addEventListener("hashchange", function () { if (readHash()) paint(); });
  }

  var API = {
    BIT_STAGE: BIT_STAGE, N_BITS: N_BITS, N_BRACKETS: N_BRACKETS,
    derive: derive, expand: expand, score: score,
    bestGiven: bestGiven, resolve: resolve, init: init
  };

  // 浏览器里挂 window，node 里（跨语言对照测试）走 module.exports
  root.BracketEditor = API;
  root.initBracket = init;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : this);
