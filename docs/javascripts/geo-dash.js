/* Geo-AI WG lecture analytics + talk filters. Data: feeds/history.json (public-safe, no emails). */
(function () {
  const LIGHT = ["#0054de", "#7a9a26", "#8b68b5", "#c25a48", "#4a36b0", "#a3b833"]; // validated (dataviz validator)
  const DARK = ["#3d7bff", "#7f9f2a", "#9575c4", "#c9634f", "#6a56d6", "#8c9a1c"];
  const GRAY = { light: "#9aa0a6", dark: "#6b7280" };
  const SKILL_ORDER = ["Basic", "Intermediate", "Advanced", "Bleeding Edge", "Unspecified"];
  const DIMS = [["year", "Year", "years"], ["sector", "Sector", "sectors"], ["theme", "Theme", "themes"], ["category", "AI category", "AI categories"], ["skill", "Skill level", "skill levels"]];
  const isDark = () => document.body.getAttribute("data-md-color-scheme") === "slate";
  const ink = () => (isDark() ? { text: "#e6e6e6", muted: "#a0a4ab", grid: "rgba(255,255,255,.08)" } : { text: "#1f2328", muted: "#5f6670", grid: "rgba(0,0,0,.06)" });

  const count = (rows, k) => rows.reduce((m, r) => ((m[r[k]] = (m[r[k]] || 0) + 1), m), {});
  const uniq = (rows, k) => [...new Set(rows.map((r) => r[k]))].sort((a, b) => (k === "skill" ? SKILL_ORDER.indexOf(a) - SKILL_ORDER.indexOf(b) : String(a).localeCompare(String(b))));

  function filtersUI(host, rows, state, onChange) {
    const bar = document.createElement("div");
    bar.className = "gd-filters";
    DIMS.forEach(([k, label, plural]) => {
      const sel = document.createElement("select");
      sel.setAttribute("aria-label", label);
      sel.dataset.k = k;
      sel.innerHTML = `<option value="">All ${plural}</option>` + uniq(rows, k).map((v) => `<option>${v}</option>`).join("");
      sel.onchange = () => { state[k] = sel.value; onChange(); };
      bar.appendChild(sel);
    });
    const reset = document.createElement("button");
    reset.className = "md-button gd-reset"; reset.textContent = "Reset";
    reset.onclick = () => { Object.keys(state).forEach((k) => (state[k] = "")); bar.querySelectorAll("select").forEach((s) => (s.value = "")); onChange(); };
    bar.appendChild(reset);
    host.appendChild(bar);
    return (k, v) => { state[k] = state[k] === String(v) ? "" : String(v); bar.querySelector(`select[data-k=${k}]`).value = state[k]; onChange(); };
  }
  const apply = (rows, state) => rows.filter((r) => DIMS.every(([k]) => !state[k] || String(r[k]) === state[k]));

  /* ---------- lectures dashboard ---------- */
  function lectures(host, rows) {
    const state = {}; const charts = {};
    const sectors = uniq(rows, "sector").filter((s) => s !== "Unspecified").concat(rows.some((r) => r.sector === "Unspecified") ? ["Unspecified"] : []);
    const colorOf = (s, i) => (s === "Unspecified" ? GRAY[isDark() ? "dark" : "light"] : (isDark() ? DARK : LIGHT)[sectors.indexOf(s) % 6]);
    const set = filtersUI(host, rows, state, render);
    host.insertAdjacentHTML("beforeend", `
      <div class="gd-kpis"></div>
      <div class="gd-grid">
        <figure class="gd-card gd-wide"><figcaption>Lectures per year, by sector</figcaption><div class="gd-canvas"><canvas id="c-year"></canvas></div></figure>
        <figure class="gd-card"><figcaption>Sector</figcaption><div class="gd-canvas"><canvas id="c-sector"></canvas></div></figure>
        <figure class="gd-card"><figcaption>Theme</figcaption><div class="gd-canvas"><canvas id="c-theme"></canvas></div></figure>
        <figure class="gd-card"><figcaption>AI category</figcaption><div class="gd-canvas"><canvas id="c-category"></canvas></div></figure>
        <figure class="gd-card"><figcaption>Skill level</figcaption><div class="gd-canvas"><canvas id="c-skill"></canvas></div></figure>
      </div>
      <p class="gd-hint">Tip: click any bar to filter. Source: lecture tracking sheet (all years).</p>
      <details class="gd-table"><summary>Show table</summary><div class="gd-tbl"></div></details>`);

    function base(onClickKey, labels) {
      const c = ink();
      return {
        responsive: true, maintainAspectRatio: false, animation: { duration: 250 },
        plugins: { legend: { display: false }, tooltip: { backgroundColor: isDark() ? "#2a2e37" : "#fff", titleColor: c.text, bodyColor: c.text, borderColor: c.grid, borderWidth: 1 } },
        scales: { x: { ticks: { color: c.muted }, grid: { display: false } }, y: { ticks: { color: c.muted, precision: 0 }, grid: { color: c.grid } } },
        onClick: (e, els) => { if (els.length && onClickKey) set(onClickKey, labels[els[0].index]); },
        onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
      };
    }
    function hbar(id, key, rowsF) {
      const cnt = count(rowsF, key);
      const labels = (key === "skill" ? SKILL_ORDER.filter((s) => cnt[s]) : Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a]));
      const opt = base(key, labels); opt.indexAxis = key === "skill" || key === "category" ? "x" : "y";
      if (opt.indexAxis === "y") { [opt.scales.x, opt.scales.y] = [opt.scales.y, opt.scales.x]; }
      const brand = isDark() ? DARK[0] : LIGHT[0];
      const data = { labels, datasets: [{ data: labels.map((l) => cnt[l]),
        backgroundColor: key === "sector" ? labels.map(colorOf) : labels.map((l) => (state[key] && state[key] !== l ? brand + "55" : brand)),
        borderRadius: 4, borderSkipped: false, maxBarThickness: 26, categoryPercentage: 0.8 }] };
      charts[id]?.destroy(); charts[id] = new Chart(document.getElementById(id), { type: "bar", data, options: opt });
    }
    function render() {
      const f = apply(rows, state); const c = ink();
      const kp = host.querySelector(".gd-kpis");
      kp.innerHTML = [["Lectures", f.length], ["Speakers", new Set(f.map((r) => r.speaker)).size], ["Years", new Set(f.map((r) => r.year)).size], ["Themes", new Set(f.map((r) => r.theme)).size]]
        .map(([l, v]) => `<div><span class="num">${v}</span><span class="lbl">${l}</span></div>`).join("");
      // stacked by sector
      const years = uniq(rows, "year");
      const opt = base("year", years); opt.scales.x.stacked = opt.scales.y.stacked = true;
      opt.plugins.legend = { display: true, position: "bottom", labels: { color: c.text, boxWidth: 10, boxHeight: 10, usePointStyle: true } };
      const ds = sectors.filter((s) => f.some((r) => r.sector === s)).map((s) => ({ label: s, data: years.map((y) => f.filter((r) => r.year == y && r.sector === s).length),
        backgroundColor: colorOf(s), borderColor: isDark() ? "#1e2129" : "#fff", borderWidth: { top: 2 }, borderRadius: 4, borderSkipped: false, maxBarThickness: 48 }));
      charts.year?.destroy(); charts.year = new Chart(document.getElementById("c-year"), { type: "bar", data: { labels: years, datasets: ds }, options: opt });
      hbar("c-sector", "sector", f); hbar("c-theme", "theme", f); hbar("c-category", "category", f); hbar("c-skill", "skill", f);
      host.querySelector(".gd-tbl").innerHTML = `<table><thead><tr><th>Date</th><th>Speaker</th><th>Title</th><th>Theme</th><th>Sector</th><th>Category</th><th>Skill</th></tr></thead><tbody>` +
        f.slice().reverse().map((r) => `<tr><td>${r.date}</td><td>${r.speaker}</td><td>${r.media ? `<a href="${r.media}" target="_blank" rel="noopener">${r.title}</a>` : r.title}</td><td>${r.theme}</td><td>${r.sector}</td><td>${r.category}</td><td>${r.skill}</td></tr>`).join("") + `</tbody></table>`;
    }
    render();
    new MutationObserver(render).observe(document.body, { attributes: true, attributeFilter: ["data-md-color-scheme"] });
  }

  /* ---------- talk archive filters ---------- */
  function talks(host) {
    const cards = [...document.querySelectorAll(".talk-card[data-year]")];
    const rows = cards.map((el) => ({ el, ...el.dataset }));
    const state = {};
    filtersUI(host, rows, state, render);
    const out = document.createElement("p"); out.className = "gd-hint"; host.appendChild(out);
    function render() {
      const keep = new Set(apply(rows, state).map((r) => r.el));
      cards.forEach((el) => (el.hidden = !keep.has(el)));
      document.querySelectorAll(".talk-year").forEach((sec) => { const g = sec.nextElementSibling; sec.hidden = g && ![...g.querySelectorAll(".talk-card")].some((c) => !c.hidden); if (g) g.hidden = sec.hidden; });
      out.textContent = `Showing ${keep.size} of ${cards.length} talks. Sector/theme/category/skill tags come from the lecture tracking sheet; untagged talks show as "Unspecified".`;
    }
    render();
  }

  function init() {
    document.querySelectorAll("[data-geo-dash]").forEach(async (host) => {
      if (host.dataset.done) return; host.dataset.done = 1;
      if (host.dataset.geoDash === "talks") return talks(host);
      try {
        const res = await fetch(host.dataset.src); const j = await res.json();
        lectures(host, j.talks.map((t) => ({ ...t, year: String(t.year) })));
      } catch (e) { host.innerHTML = `<p>Could not load lecture data (${e}).</p>`; }
    });
  }
  if (window.document$) document$.subscribe(init); else document.addEventListener("DOMContentLoaded", init);
})();
