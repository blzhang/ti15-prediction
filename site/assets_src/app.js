/* 主题切换 + 数据页的搜索/统计。无外部依赖。 */
(function () {
  var KEY = "ti15-theme";
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  window.toggleTheme = function () {
    var cur = document.documentElement.getAttribute("data-theme");
    if (!cur) {
      cur = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    var next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem(KEY, next); } catch (e) {}
  };
})();

function pct(x, d) { return (x * 100).toFixed(d === undefined ? 1 : d) + "%"; }
function num(x, d) { return Number(x).toFixed(d === undefined ? 2 : d); }

/* ---------- 数据页：选手检索与统计 ---------- */
function initExplorer(base) {
  var elQ = document.getElementById("q");
  var elItem = document.getElementById("item");
  var elTeam = document.getElementById("team");
  var elPos = document.getElementById("pos");
  var elBody = document.getElementById("rows");
  var elStat = document.getElementById("stat");
  var elCount = document.getElementById("count");
  if (!elBody) return;

  var IDX = null, sortKey = "r", sortDir = -1;

  fetch(base + "/data/search_index.json").then(function (r) { return r.json(); }).then(function (d) {
    IDX = d;
    d.items.forEach(function (it) {
      var o = document.createElement("option");
      o.value = it; o.textContent = (d.item_label[it] || it) + "（" + it + "）";
      elItem.appendChild(o);
    });
    d.teams.forEach(function (t) {
      var o = document.createElement("option"); o.value = t; o.textContent = t; elTeam.appendChild(o);
    });
    elItem.value = "gpm";
    render();
  }).catch(function (e) {
    elBody.innerHTML = '<tr><td colspan="8">数据加载失败：' + e + "</td></tr>";
  });

  function filtered() {
    var q = (elQ.value || "").trim().toLowerCase();
    var item = elItem.value, team = elTeam.value, pos = elPos.value;
    return IDX.rows.filter(function (r) {
      if (item && r.i !== item) return false;
      if (team && r.t !== team) return false;
      if (pos && String(r.p) !== pos) return false;
      if (q && r.n.toLowerCase().indexOf(q) < 0 && r.t.toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
  }

  function render() {
    if (!IDX) return;
    var rows = filtered();
    rows.sort(function (a, b) {
      var x = a[sortKey], y = b[sortKey];
      if (typeof x === "string") return sortDir * x.localeCompare(y);
      return sortDir * (x - y);
    });
    elCount.textContent = rows.length + " 条";

    if (!rows.length) {
      elBody.innerHTML = '<tr><td colspan="8">无匹配结果</td></tr>';
      elStat.innerHTML = "";
      return;
    }
    var vals = rows.map(function (r) { return r.r; }).sort(function (a, b) { return a - b; });
    var sum = vals.reduce(function (a, b) { return a + b; }, 0);
    var mean = sum / vals.length;
    var med = vals.length % 2 ? vals[(vals.length - 1) / 2]
                              : (vals[vals.length / 2 - 1] + vals[vals.length / 2]) / 2;
    var sd = Math.sqrt(vals.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / Math.max(vals.length - 1, 1));
    var lbl = IDX.item_label[elItem.value] || elItem.value;
    elStat.innerHTML =
      tile("样本", rows.length + " 名选手", lbl) +
      tile("均值", num(mean), "每局") +
      tile("中位数", num(med), "每局") +
      tile("标准差", num(sd), "选手之间") +
      tile("区间", num(vals[0]) + " – " + num(vals[vals.length - 1]), "最低 / 最高");

    var max = Math.max.apply(null, rows.map(function (r) { return r.hi; })) || 1;
    elBody.innerHTML = rows.map(function (r) {
      var w = Math.max(1, (r.r / max) * 100);
      return "<tr>" +
        "<td>" + esc(r.n) + "</td>" +
        "<td>" + esc(r.t) + "</td>" +
        "<td class=num>" + r.p + "</td>" +
        "<td class='num hi'>" + num(r.r) + "</td>" +
        "<td class=num>" + num(r.lo) + " – " + num(r.hi) + "</td>" +
        "<td class=num>" + r.g + "</td>" +
        "<td style='width:150px'><div class=bar-track style='height:10px'>" +
          "<div class=bar-fill style='width:" + w.toFixed(1) + "%'></div></div></td>" +
        "</tr>";
    }).join("");
  }

  function tile(k, v, s) {
    return '<div class=tile><div class=k>' + esc(k) + '</div><div class=v>' + esc(v) +
           '</div><div class=s>' + esc(s) + "</div></div>";
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  [elQ, elItem, elTeam, elPos].forEach(function (el) {
    el.addEventListener("input", render);
    el.addEventListener("change", render);
  });
  Array.prototype.forEach.call(document.querySelectorAll("th[data-k]"), function (th) {
    th.style.cursor = "pointer";
    th.addEventListener("click", function () {
      var k = th.getAttribute("data-k");
      if (sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = -1; }
      render();
    });
  });
}
