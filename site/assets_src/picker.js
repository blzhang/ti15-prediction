/* 作业页的互动选择器：自己挑，实时看期望答对数，生成可分享链接。
   纯前端，无后端、无 cookie。选择编码进 URL 的 #hash，别人打开链接就能看到你的填法。 */
(function () {
  var D = null, sel = {}, fsel = {};

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  function init(data) {
    D = data;
    if (!parseHash()) applyPreset("model", true);
    render();
    window.addEventListener("hashchange", function () { if (parseHash()) render(); });
  }

  /* ---------- 选择状态 ---------- */
  function usedBy(team) {
    for (var b in sel) if (sel[b].indexOf(team) >= 0) return b;
    return null;
  }

  function pick(bucket, team) {
    var cap = D.buckets[bucket].cap;
    var cur = sel[bucket] || (sel[bucket] = []);
    var at = cur.indexOf(team);
    if (at >= 0) { cur.splice(at, 1); render(); return; }
    var owner = usedBy(team);
    if (owner) sel[owner].splice(sel[owner].indexOf(team), 1);   // 一支队只能占一格
    if (cur.length >= cap) cur.shift();                          // 满了就顶掉最早选的
    cur.push(team);
    render();
  }

  function applyPreset(which, silent) {
    sel = {};
    for (var b in D.buckets) sel[b] = D.buckets[b].preset.slice();
    fsel = {};
    for (var k in D.fantasy) fsel[k] = D.fantasy[k].rows[0].team;
    if (!silent) render();
  }

  function clearAll() {
    sel = {}; for (var b in D.buckets) sel[b] = [];
    fsel = {}; render();
  }

  /* ---------- 期望答对数 ---------- */
  function expected() {
    var e = 0;
    for (var b in sel) {
      var probs = D.buckets[b].p;
      for (var i = 0; i < sel[b].length; i++) e += probs[sel[b][i]] || 0;
    }
    return e;
  }

  function filled() {
    var n = 0;
    for (var b in sel) n += sel[b].length;
    return n;
  }

  /* ---------- URL 编码 ---------- */
  function encode() {
    var idx = {};
    D.teams.forEach(function (t, i) { idx[t] = i; });
    var parts = [];
    D.order.forEach(function (b) {
      parts.push((sel[b] || []).map(function (t) { return idx[t].toString(36); }).join(""));
    });
    var f = ["core", "mid", "support"].map(function (k) {
      return fsel[k] === undefined ? "-" : idx[fsel[k]].toString(36);
    }).join("");
    return parts.join(".") + "~" + f;
  }

  function parseHash() {
    var h = (location.hash || "").replace(/^#/, "");
    if (!h) return false;
    try {
      var bits = h.split("~"), parts = bits[0].split(".");
      if (parts.length !== D.order.length) return false;
      var s = {};
      D.order.forEach(function (b, i) {
        s[b] = parts[i].split("").map(function (c) { return D.teams[parseInt(c, 36)]; })
                       .filter(Boolean);
      });
      sel = s;
      fsel = {};
      if (bits[1]) {
        ["core", "mid", "support"].forEach(function (k, i) {
          var c = bits[1][i];
          if (c && c !== "-") fsel[k] = D.teams[parseInt(c, 36)];
        });
      }
      return true;
    } catch (e) { return false; }
  }

  /* ---------- 渲染 ---------- */
  function render() {
    var wrap = $("picker");
    if (!wrap) return;
    var html = "";
    D.order.forEach(function (b) {
      var info = D.buckets[b], chosen = sel[b] || [];
      var cands = D.teams.slice().sort(function (x, y) {
        return (info.p[y] || 0) - (info.p[x] || 0);
      });
      var best = info.p[cands[0]] || 1;
      html += '<div class="pkbucket"><div class="pkhead"><b>' + esc(b) + "</b>" +
              '<span>' + esc(info.desc) + " · 选 " + info.cap + " 支 " +
              '<i class="' + (chosen.length === info.cap ? "ok" : "warn") + '">' +
              chosen.length + "/" + info.cap + "</i></span></div><div class=pkopts>";
      cands.forEach(function (t) {
        var p = info.p[t] || 0;
        var on = chosen.indexOf(t) >= 0;
        var owner = usedBy(t);
        var taken = owner && owner !== b;
        html += '<button class="pkopt' + (on ? " on" : "") + (taken ? " taken" : "") +
                '" data-b="' + esc(b) + '" data-t="' + esc(t) + '"' +
                (taken ? ' title="已选在「' + esc(owner) + '」"' : "") + ">" +
                '<span class="bar" style="width:' + (p / best * 100).toFixed(1) + '%"></span>' +
                '<span class="nm">' + esc(t) + "</span>" +
                '<span class="pv">' + (p * 100).toFixed(1) + "%</span></button>";
      });
      html += "</div></div>";
    });
    wrap.innerHTML = html;

    // 梦幻三格
    var fw = $("fpicker");
    if (fw) {
      var fh = "";
      ["core", "mid", "support"].forEach(function (k) {
        var d = D.fantasy[k], best = d.rows[0].total;
        fh += '<div class="pkbucket"><div class="pkhead"><b>' + esc(d.cn) + "</b>" +
              "<span>" + esc(d.desc) + "</span></div><div class=pkopts>";
        d.rows.forEach(function (r) {
          fh += '<button class="pkopt' + (fsel[k] === r.team ? " on" : "") +
                '" data-f="' + k + '" data-t="' + esc(r.team) + '">' +
                '<span class="bar" style="width:' + (r.total / best * 100).toFixed(1) + '%"></span>' +
                '<span class="nm">' + esc(r.team) + "</span>" +
                '<span class="pv">' + (r.gap >= 0 ? "最佳" : (r.gap * 100).toFixed(1) + "%") +
                "</span></button>";
        });
        fh += "</div></div>";
      });
      fw.innerHTML = fh;
    }

    var e = expected(), n = filled();
    $("exp").textContent = e.toFixed(2);
    $("cnt").textContent = n + "/16";
    $("delta").textContent = (e - D.random).toFixed(2);
    $("expbar").style.width = Math.max(0, Math.min(100, e / 8 * 100)).toFixed(1) + "%";
    var st = $("status");
    if (n < 16) { st.textContent = "还差 " + (16 - n) + " 格没填"; st.className = "pkstat warn"; }
    else { st.textContent = "16 格已填满"; st.className = "pkstat ok"; }
    try { history.replaceState(null, "", "#" + encode()); } catch (err) {}
  }

  /* ---------- 事件 ---------- */
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest(".pkopt");
    if (b) {
      if (b.dataset.f) { fsel[b.dataset.f] = b.dataset.t; render(); }
      else pick(b.dataset.b, b.dataset.t);
      return;
    }
    if (ev.target.id === "btn-model") applyPreset("model");
    if (ev.target.id === "btn-clear") clearAll();
    if (ev.target.id === "btn-share") {
      var url = location.origin + location.pathname + "#" + encode();
      var done = function () {
        var el = ev.target; var old = el.textContent;
        el.textContent = "已复制链接 ✓";
        setTimeout(function () { el.textContent = old; }, 1800);
      };
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, done);
      else { prompt("复制这个链接分享给别人：", url); }
    }
  });

  window.initPicker = init;
})();
