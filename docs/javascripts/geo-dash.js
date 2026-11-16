/* Geo-AI WG talk browser: list (table | cards) + subtle side figures. Tags filter everything. Data: feeds/catalog.json */
(function () {
  const DIMS = [["year", "Year"], ["theme", "Theme"], ["sector", "Sector"], ["category", "AI category"], ["skill", "Skill level"]];
  const TAGS = ["theme", "sector", "category", "skill"];
  const SKILL_ORDER = ["Basic", "Intermediate", "Advanced", "Bleeding Edge", "Unspecified"];
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const yt = (id) => `https://www.youtube.com/watch?v=${id}&list=PLKlxghiZuIM59XVSjuye43qcHXRZLwQNN`;

  function mount(host, rows, view) {
    const state = { q: "" };
    DIMS.forEach(([k]) => (state[k] = ""));
    host.classList.add("gd");
    host.innerHTML = `
      <div class="gd-main">
        <div class="gd-bar">
          <input class="gd-search" type="search" placeholder="Search title or speaker…" aria-label="Search talks">
          <div class="gd-active"></div>
          <span class="gd-count"></span>
        </div>
        <div class="gd-list"></div>
      </div>
      <aside class="gd-side" aria-label="Talk metrics"></aside>`;
    const $ = (s) => host.querySelector(s);
    $(".gd-search").addEventListener("input", (e) => { state.q = e.target.value.toLowerCase(); render(); });
    host.addEventListener("click", (e) => {
      const t = e.target.closest("[data-k]");
      if (!t) return;
      e.preventDefault();
      const k = t.dataset.k, v = t.dataset.v;
      state[k] = state[k] === v ? "" : v;
      render();
      if (t.closest(".gd-list")) host.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    const match = (r, skip) => DIMS.every(([k]) => k === skip || !state[k] || String(r[k]) === state[k]) &&
      (!state.q || (r.title + " " + r.speaker).toLowerCase().includes(state.q));

    const tag = (k, v) => v && v !== "Unspecified"
      ? `<button class="gd-tag t-${k}${state[k] === v ? " on" : ""}" data-k="${k}" data-v="${esc(v)}" title="Filter by ${k}: ${esc(v)}">${esc(v)}</button>` : "";

    function fig(k, label, rowsFor) {
      const cnt = {};
      rowsFor.forEach((r) => (cnt[r[k]] = (cnt[r[k]] || 0) + 1));
      let keys = Object.keys(cnt).filter((x) => x && x !== "Unspecified" && x !== "Undated");
      keys = k === "year" ? keys.sort() : k === "skill" ? SKILL_ORDER.filter((s) => cnt[s]) : keys.sort((a, b) => cnt[b] - cnt[a]);
      const max = Math.max(1, ...keys.map((x) => cnt[x]));
      const untagged = (cnt.Unspecified || 0) + (cnt.Undated || 0);
      const unspec = untagged ? `<span class="gd-unspec">+${untagged} untagged</span>` : "";
      if (k === "year") {
        return `<figure class="gd-fig"><figcaption>${label} ${unspec}</figcaption><div class="gd-spark">` +
          keys.map((x) => `<button data-k="year" data-v="${x}" class="${state.year === x ? "on" : ""}" title="${x}: ${cnt[x]} talks"><i style="height:${(cnt[x] / max) * 100}%"></i><span>'${x.slice(2)}</span></button>`).join("") +
          `</div></figure>`;
      }
      return `<figure class="gd-fig"><figcaption>${label} ${unspec}</figcaption>` +
        keys.map((x) => `<button class="gd-row${state[k] === x ? " on" : ""}" data-k="${k}" data-v="${esc(x)}" title="${esc(x)}: ${cnt[x]}">
          <span class="l">${esc(x)}</span><span class="b"><i style="width:${(cnt[x] / max) * 100}%"></i></span><span class="n">${cnt[x]}</span></button>`).join("") +
        `</figure>`;
    }

    function item(r) {
      const tags = TAGS.map((k) => tag(k, r[k])).join("");
      const href = r.video ? yt(r.video) : r.link;
      const title = href ? `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title);
      if (view === "cards") {
        return `<article class="gd-card-talk">
          ${r.video ? `<a class="thumb" href="${yt(r.video)}" target="_blank" rel="noopener" aria-label="Watch ${esc(r.title)}"><img loading="lazy" src="https://i.ytimg.com/vi/${r.video}/mqdefault.jpg" alt=""></a>` : `<div class="thumb none">No recording</div>`}
          <div class="body"><div class="t">${title}</div><div class="m">${esc(r.speaker)}${r.date ? " · " + r.date : ""}</div><div class="tags">${tags}</div></div></article>`;
      }
      return `<tr><td class="d">${r.date || "—"}</td><td><div class="t">${title}${r.video ? ' <span class="yt" title="Recording on YouTube">▶</span>' : ""}</div><div class="m">${esc(r.speaker)}</div><div class="tags">${tags}</div></td></tr>`;
    }

    function render() {
      const f = rows.filter((r) => match(r));
      $(".gd-active").innerHTML = DIMS.filter(([k]) => state[k])
        .map(([k, l]) => `<button class="gd-chip" data-k="${k}" data-v="${esc(state[k])}" title="Remove filter">${l}: ${esc(state[k])} ✕</button>`).join("");
      $(".gd-count").textContent = `${f.length} of ${rows.length} talks`;
      $(".gd-list").innerHTML = !f.length ? `<p class="gd-empty">No talks match these filters.</p>` :
        view === "cards" ? `<div class="gd-cards">${f.map(item).join("")}</div>`
          : `<table class="gd-table"><thead><tr><th>Date</th><th>Talk</th></tr></thead><tbody>${f.map(item).join("")}</tbody></table>`;
      const speakers = new Set(f.map((r) => r.speaker).filter(Boolean)).size;
      const recorded = f.filter((r) => r.video).length;
      // each figure counts rows matching every OTHER active filter
      $(".gd-side").innerHTML =
        `<div class="gd-kpi"><b>${f.length}</b> talks · <b>${speakers}</b> speakers · <b>${recorded}</b> recorded</div>` +
        DIMS.map(([k, l]) => fig(k, l, rows.filter((r) => match(r, k)))).join("");
    }
    render();
  }

  function init() {
    document.querySelectorAll("[data-geo-dash]").forEach(async (host) => {
      if (host.dataset.done) return;
      host.dataset.done = 1;
      try {
        const j = await (await fetch(host.dataset.src)).json();
        const cards = host.dataset.geoDash === "cards";
        mount(host, cards ? j.talks.filter((r) => r.video) : j.talks, cards ? "cards" : "table");
      } catch (e) {
        host.innerHTML = `<p>Could not load talks (${esc(e)}).</p>`;
      }
    });
  }
  if (window.document$) document$.subscribe(init); else document.addEventListener("DOMContentLoaded", init);
})();
