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

  var API = {
    BIT_STAGE: BIT_STAGE, N_BITS: N_BITS, N_BRACKETS: N_BRACKETS,
    derive: derive, expand: expand, score: score,
    bestGiven: bestGiven, resolve: resolve
  };

  // 浏览器里挂 window，node 里（跨语言对照测试）走 module.exports
  root.BracketEditor = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : this);
