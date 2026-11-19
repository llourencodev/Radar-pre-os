/* Radar de Preços — interface (JavaScript puro, sem build). Mesmo visual do Radar Inteligente de Notícias. */
(() => {
  "use strict";

  // ------------------------------------------------------------ ícones (SVG inline)
  const P = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
  const ICONS = {
    home: P('<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>'),
    tag: P('<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.5"/>'),
    ticket: P('<path d="M3 8a2 2 0 002-2h14a2 2 0 002 2v2a2 2 0 000 4v2a2 2 0 00-2 2H5a2 2 0 00-2-2v-2a2 2 0 000-4z"/><path d="M13 6v12" stroke-dasharray="2 2"/>'),
    bolt: P('<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>'),
    box: P('<path d="M21 8l-9-5-9 5 9 5 9-5z"/><path d="M3 8v8l9 5 9-5V8M12 13v8"/>'),
    radio: P('<circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 010 8.4M7.8 16.2a6 6 0 010-8.4M19 5a10 10 0 010 14M5 19A10 10 0 015 5"/>'),
    search: P('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
    refresh: P('<path d="M20 11a8 8 0 10-2.3 5.7"/><path d="M20 4v7h-7"/>'),
    theme: P('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
    menu: P('<path d="M4 6h16M4 12h16M4 18h16"/>'),
    external: P('<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5"/>'),
    close: P('<path d="M6 6l12 12M18 6L6 18"/>'),
    trend: P('<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>'),
  };
  const icon = (n) => `<span class="ico">${ICONS[n] || ""}</span>`;
  const hydrateIcons = (root = document) => root.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = ICONS[el.dataset.icon] || ""; });

  // ------------------------------------------------------------ utilidades
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* sem armazenamento */ } },
  };
  const STATIC = !!window.PRECOS_API; // versão publicada (GitHub Pages): dados em JSON, sem servidor
  async function api(path, opts = {}) {
    if (STATIC) return window.PRECOS_API(path, opts);
    const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || `Erro ${r.status}`);
    return data;
  }
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 3500);
  }
  const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const brl = (v) => (v == null ? "—" : BRL.format(v));
  const fmtDT = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  function rel(iso) {
    if (!iso) return "—";
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return "agora";
    if (s < 3600) return `há ${Math.floor(s / 60)} min`;
    if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
    const d = Math.floor(s / 86400);
    return d === 1 ? "ontem" : `há ${d} dias`;
  }
  const fmtLocal = (iso) => (iso ? fmtDT.format(new Date(iso)) : "—");

  const FLAGS = {
    bugao: ["BUGÃO", "Desconto de 50% ou mais sobre o preço de referência (mediana das lojas brasileiras). Corra, mas confira o vendedor."],
    bug: ["Possível bug de preço", "Preço muito abaixo do preço de referência (mediana das lojas). Confira antes que corrijam."],
    alvo: ["Preço alvo atingido", "Igual ou abaixo do preço alvo que você definiu"],
    suspeito: ["Suspeito", "Barato demais: pode ser acessório, peça usada ou anúncio falso. Verifique o vendedor."],
    abaixo: ["Abaixo da média", "Mais barato que a maioria das lojas"],
    nova: ["Nova oferta", "Apareceu nas últimas horas"],
    queda: ["Preço caiu", "O preço caiu desde a última coleta"],
    desconto_alto: ["Desconto alto", "A loja mostra um preço 'de' muito maior"],
    usado: ["Usado", "Anúncio de produto usado"],
    encerrada: ["Encerrada", "A comunidade marcou esta promoção como encerrada"],
    antiga: ["Postagem antiga", "Promoção postada há mais de 7 dias: o preço provavelmente já mudou"],
    sem_data: ["Data não informada", "A comunidade não informou quando a promoção foi postada; confira no link"],
  };
  const flagLabel = (o, f) => {
    if (f === "bugao") return o.ratio ? `BUGÃO -${Math.round((1 - o.ratio) * 100)}%` : "BUGÃO";
    if (f === "suspeito" && o.flags.includes("bugao")) return "Suspeito: confira o vendedor";
    return FLAGS[f]?.[0] || f;
  };
  const flagBadges = (o) => (o.flags || []).map((f) => `<span class="badge f-${f}" title="${esc(FLAGS[f]?.[1] || "")}">${esc(flagLabel(o, f))}</span>`).join("");
  const ST = { ok: "OK", vazio: "Sem resultado", bloqueado: "Bloqueou", erro: "Erro", pending: "Buscando…" };

  // ------------------------------------------------------------ estado
  const S = { watches: [], status: null, dash: null };

  // ------------------------------------------------------------ componentes
  function vsRef(o) {
    if (!o.ratio) return "";
    const pct = Math.round((1 - o.ratio) * 100);
    if (pct >= 1) return `<span class="vs down" title="Comparado ao preço de referência ${brl(o.ref_price)}">${pct}% abaixo da referência</span>`;
    if (pct <= -1) return `<span class="vs up" title="Comparado ao preço de referência ${brl(o.ref_price)}">${-pct}% acima</span>`;
    return `<span class="vs up">na média</span>`;
  }
  function offerCard(o, showQuery = false) {
    const img = o.image ? `<img src="${esc(safeUrl(o.image))}" alt="" loading="lazy" referrerpolicy="no-referrer" data-fallback="1">` : noImg(o);
    const promo = o.kind === "promo" ? `<span class="badge f-promo" title="Postado por uma comunidade de promoções">Promoção ${esc(o.store)}</span>` : "";
    return `<article class="card ${o.flags?.includes("bugao") ? "is-bugao" : o.flags?.includes("bug") ? "is-bug" : ""}">
      <div class="thumb product">${img}</div>
      <div class="card-body">
        <div class="badges"><span class="badge store">${esc(o.kind === "promo" ? (o.via || "Loja não informada") : o.store)}</span>${promo}${flagBadges(o)}</div>
        <div class="price-row"><span class="price">${brl(o.price)}</span>${o.old_price ? `<span class="old">${brl(o.old_price)}</span>` : ""}${vsRef(o)}</div>
        <h3><a href="${esc(safeUrl(o.url))}" target="_blank" rel="noopener noreferrer">${esc(o.title)}</a></h3>
        <div class="meta">${showQuery ? `<span class="outlet">${esc(o.query)}</span>` : ""}${o.seller ? `<span>Vendedor: ${esc(o.seller)}</span>` : ""}${o.kind === "promo" && o.posted_at ? `<span>Postada ${rel(o.posted_at)}</span>` : `<span title="Primeira vez que o radar viu esta oferta: ${esc(fmtLocal(o.first_seen))}">Conferido ${rel(o.last_seen || o.first_seen)}</span>`}${o.min_price && o.min_price < o.price ? `<span>Menor já visto: ${brl(o.min_price)}</span>` : ""}</div>
        ${o.coupon ? `<div>Cupom: <button class="coupon-code" data-copy="${esc(o.coupon)}">${esc(o.coupon)}</button></div>` : ""}
        ${o.installments ? `<div class="note">${esc(o.installments)}</div>` : ""}
        ${o.note ? `<div class="note">${esc(o.note)}</div>` : ""}
      </div>
      <div class="card-foot">
        ${o.id > 0 ? `<button class="linkbtn" data-hist="${o.id}" data-title="${esc(o.title)}">Histórico de preço</button>` : "<span></span>"}
        <a href="${esc(safeUrl(o.url))}" target="_blank" rel="noopener noreferrer">${o.kind === "promo" ? "Ver promoção" : "Ver na loja"} ${icon("external")}</a>
      </div>
    </article>`;
  }
  function noImg(o) {
    return `<div class="noimg" style="--c:#0b5cad">${icon("tag")}<span class="outlet">${esc(o.store)}</span><span class="note">Sem imagem</span></div>`;
  }
  function couponCard(c) {
    const off = c.pct ? `${c.pct}% OFF` : c.amount ? `${brl(c.amount)} OFF` : "Desconto";
    return `<article class="card"><div class="coupon">
      <div class="badges"><span class="badge store">${esc(c.store)}</span><span class="badge f-abaixo">${esc(off)}</span>${c.min_value ? `<span class="badge">Mínimo ${brl(c.min_value)}</span>` : ""}</div>
      <p class="title">${esc(c.title)}</p>
      <div class="price-row">${c.code ? `<button class="coupon-code" data-copy="${esc(c.code)}" title="Clique para copiar">${esc(c.code)}</button>` : `<span class="hint">Desconto ativado pelo link, sem código</span>`}
      ${c.saving ? `<span class="save">economia estimada ${brl(c.saving)}</span>` : ""}</div>
      <div class="meta"><span>Fonte: ${esc(c.source)}</span><span>Visto ${rel(c.last_seen)}</span>${c.expires ? `<span>Validade: ${esc(String(c.expires).slice(0, 10))}</span>` : ""}</div>
    </div><div class="card-foot"><span class="hint">Confirme no carrinho</span><a href="${esc(safeUrl(c.url))}" target="_blank" rel="noopener noreferrer">Ver regras ${icon("external")}</a></div></article>`;
  }
  function sparkline(points) {
    if (!points || points.length < 2) return `<p class="hint">O gráfico aparece a partir do segundo dia de monitoramento.</p>`;
    const W = 600, H = 64, ps = points.map((p) => p.price);
    const min = Math.min(...ps), max = Math.max(...ps), span = max - min || 1;
    const xy = points.map((p, i) => [(i / (points.length - 1)) * W, H - 6 - ((p.price - min) / span) * (H - 12)]);
    const d = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
    return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Menor preço por dia"><path class="area" d="${d}L${W},${H}L0,${H}Z"/><path class="line" d="${d}"/></svg>
      <div class="meta"><span>${esc(points[0].day.split("-").reverse().join("/"))}: ${brl(points[0].price)}</span><span>Mín. ${brl(min)}</span><span>Máx. ${brl(max)}</span><span>Hoje: ${brl(ps[ps.length - 1])}</span></div>`;
  }
  function storeDots(stores, running) {
    const st = (running && running.stores) || {};
    const names = new Set([...(stores || []).map((s) => s.store), ...Object.keys(st)]);
    if (!names.size && !running) return "";
    return `<div class="store-dots">${[...names].sort().map((n) => {
      const s = (stores || []).find((x) => x.store === n) || {};
      const status = running && !st[n] ? "pending" : (st[n] || s.status || "vazio");
      return `<span class="store-dot" title="${esc(s.error || "")}"><span class="dot ${status}"></span>${esc(n)}${s.matched != null && !running ? ` · ${s.matched}` : ""}</span>`;
    }).join("")}${running ? `<span class="store-dot"><span class="dot pending"></span>${running.done}/${running.total} lojas consultadas</span>` : ""}</div>`;
  }
  function fixImages(root) {
    root.querySelectorAll("img[data-fallback]").forEach((img) => img.addEventListener("error", () => {
      img.closest(".thumb")?.insertAdjacentHTML("beforeend", `<div class="noimg" style="--c:#0b5cad">${icon("tag")}<span class="note">Imagem indisponível</span></div>`);
      img.remove();
    }, { once: true }));
  }
  function bindCommon(root) {
    fixImages(root);
    root.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); toast(`Cupom ${b.dataset.copy} copiado.`); } catch { toast(b.dataset.copy); }
    }));
    root.querySelectorAll("[data-hist]").forEach((b) => b.addEventListener("click", () => openHistory(b.dataset.hist, b.dataset.title)));
  }

  // ------------------------------------------------------------ navegação
  function renderNav() {
    const items = [`<a class="nav-item" href="#/" data-route="dashboard">${icon("home")}<span>Painel</span></a>`,
      `<a class="nav-item" href="#/cupons" data-route="cupons" style="--c:#22c55e">${icon("ticket")}<span>Cupons</span><span class="count">${S.dash ? S.dash.coupons_total : ""}</span></a>`,
      `<div class="nav-label">Produtos monitorados</div>`];
    if (!S.watches.length) items.push(`<div class="nav-item" style="opacity:.7">${icon("search")}<span>Busque um produto acima</span></div>`);
    S.watches.forEach((w) => {
      const c = w.bugs ? "#f87171" : w.new ? "#38bdf8" : "#94a3b8";
      items.push(`<a class="nav-item" href="#/p/${w.id}" data-route="p/${w.id}" style="--c:${c}">${icon(w.bugs ? "bolt" : "tag")}<span>${esc(w.query)}</span><span class="count">${w.best ? brl(w.best.price).replace(/,\d\d$/, "") : ""}</span></a>`);
    });
    $("#nav").innerHTML = items.join("");
    markActive();
  }
  function markActive() {
    const r = location.hash.replace(/^#\/?/, "").split("?")[0] || "dashboard";
    document.querySelectorAll(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.route === r));
  }
  async function router() {
    const h = location.hash.replace(/^#\/?/, "");
    const [path, qs] = h.split("?");
    const params = new URLSearchParams(qs || "");
    const view = $("#view");
    markActive();
    closeMenu();
    try {
      if (!path) await viewDashboard(view);
      else if (path.startsWith("p/")) await viewWatch(view, +path.slice(2), params);
      else if (path === "cupons") await viewCoupons(view, params);
      else if (path === "lojas") await viewStores(view);
      else if (path === "busca") await viewBusca(view, params);
      else location.hash = "#/";
    } catch (e) {
      view.innerHTML = `<div class="empty">Não foi possível carregar: ${esc(e.message)}</div>`;
    }
    hydrateIcons(view);
  }

  // ------------------------------------------------------------ painel
  async function viewDashboard(view) {
    if (!S.dash) view.innerHTML = `<div class="skeleton"></div>`;
    const d = S.dash = await api("/api/dashboard");
    S.watches = d.watches; renderNav();
    const bugaos = d.hot.filter((o) => o.flags.includes("bugao")), hotRest = d.hot.filter((o) => !o.flags.includes("bugao"));
    const bugs = d.watches.reduce((a, w) => a + w.bugs, 0), news = d.watches.reduce((a, w) => a + w.new, 0);
    const total = d.watches.reduce((a, w) => a + w.offers, 0);
    const rowsW = d.watches.map((w) => `<tr class="watch-row"><td><a href="#/p/${w.id}">${esc(w.query)}</a></td>
      <td class="mono"><strong>${brl(w.best?.price)}</strong>${w.best ? `<div class="hint">${esc(w.best.store)}</div>` : ""}</td>
      <td class="mono">${brl(w.ref_price)}</td><td class="mono">${w.target_price ? brl(w.target_price) : "—"}</td>
      <td>${w.offers}</td><td>${w.bugs ? `<span class="badge f-bug">${w.bugs}</span>` : "0"}</td><td>${w.new}</td><td>${rel(w.last_run)}</td></tr>`).join("");
    view.innerHTML = `
      <div class="page-head"><div><div class="eyebrow">Visão geral</div><h1>Painel de preços</h1>
        <p>Menores preços, possíveis bugs de preço e cupons das lojas que você acompanha.</p></div></div>
      <div class="kpis">
        <div class="kpi"><div class="label">Produtos monitorados</div><div class="value">${d.watches.length}</div><div class="sub">Atualiza a cada ${S.status?.interval_min ?? 30} min</div></div>
        <div class="kpi"><div class="label">Ofertas ativas</div><div class="value">${total}</div><div class="sub">Em ${new Set(d.watches.flatMap((w) => w.stores.filter((s) => s.matched).map((s) => s.store))).size} lojas</div></div>
        <div class="kpi"><div class="label">Possíveis bugs de preço</div><div class="value" style="color:${bugs ? "var(--bad)" : "inherit"}">${bugs}</div><div class="sub">Abaixo de 70% da referência${bugaos.length ? ` · ${d.bugaos ?? bugaos.length} bugão(ões)` : ""}</div></div>
        <div class="kpi"><div class="label">Ofertas novas</div><div class="value">${news}</div><div class="sub">Últimas 24 horas</div></div>
      </div>
      ${!d.watches.length ? `<div class="empty"><h3>Comece buscando um produto</h3><p>Digite na barra de busca, por exemplo <button class="chip" data-q="RTX 3060 12GB">RTX 3060 12GB</button>. O radar consulta as lojas e passa a monitorar o preço.</p></div>` : ""}
      ${bugaos.length ? `<section class="section bugao-section"><div class="section-head"><h2>BUGÕES</h2><span class="sub">50% ou mais abaixo da referência</span></div><div class="grid">${bugaos.map((o) => offerCard(o, true)).join("")}</div></section>` : ""}
      ${hotRest.length ? `<section class="section"><div class="section-head"><h2>Bugs de preço e ofertas quentes</h2></div><div class="grid">${hotRest.map((o) => offerCard(o, true)).join("")}</div></section>` : ""}
      ${d.watches.length ? `<section class="section"><div class="section-head"><h2>Seus produtos</h2></div><div class="table-wrap"><table>
        <thead><tr><th>Produto</th><th>Menor preço</th><th>Referência</th><th>Preço alvo</th><th>Ofertas</th><th>Bugs</th><th>Novas</th><th>Atualizado</th></tr></thead>
        <tbody>${rowsW}</tbody></table></div></section>` : ""}
      ${d.new.length ? `<section class="section"><div class="section-head"><h2>Acabaram de sair</h2></div><div class="grid">${d.new.slice(0, 12).map((o) => offerCard(o, true)).join("")}</div></section>` : ""}
      <section class="section"><div class="section-head"><h2>Melhores cupons</h2><a href="#/cupons">Ver todos</a></div>
        ${d.coupons.length ? `<div class="grid">${d.coupons.map(couponCard).join("")}</div>` : `<div class="empty">${S.status?.coupons_running ? "Buscando cupons…" : "Nenhum cupom com código encontrado ainda."}</div>`}</section>`;
    view.querySelectorAll(".chip[data-q]").forEach((b) => b.addEventListener("click", () => doSearch(b.dataset.q)));
    bindCommon(view);
  }

  // ------------------------------------------------------------ produto
  async function viewWatch(view, id, params) {
    const F = { store: params.get("loja") || "", flag: params.get("f") || "", usados: params.get("usados") === "1", promo: params.get("promo") !== "0", sort: params.get("ord") || "preco" };
    if (view.dataset.wid !== String(id)) view.innerHTML = `<div class="skeleton"></div>`;
    view.dataset.wid = id;
    const w = await api(`/api/watches/${id}`);
    let items = w.items.filter((o) => (!F.store || o.store === F.store || o.via === F.store) && (F.usados || o.condition !== "usado") && (F.promo || o.kind !== "promo"));
    if (F.flag) items = items.filter((o) => o.flags.includes(F.flag));
    if (F.sort === "novas") items.sort((a, b) => b.first_seen.localeCompare(a.first_seen));
    else if (F.sort === "desconto") items.sort((a, b) => (a.ratio || 9) - (b.ratio || 9));
    // todas as lojas consultadas, mesmo sem oferta ou bloqueadas: "Mercado Livre (bloqueado)", "Magalu (0)"
    const offerCount = (s) => w.items.filter((o) => o.store === s || o.via === s).length;
    const runs = Object.fromEntries((w.stores || []).map((s) => [s.store, s]));
    const stores = [...new Set([...(w.stores || []).map((s) => s.store), ...w.items.map((o) => o.store)])].sort((a, b) => a.localeCompare(b, "pt-BR"));
    const storeLabel = (s) => {
      const r = runs[s], n = offerCount(s);
      return r && (r.status === "bloqueado" || r.status === "erro") && !n ? `${s} (${r.status})` : `${s} (${n})`;
    };
    const count = (f) => w.items.filter((o) => o.flags.includes(f)).length;
    const link = (patch) => { const p = new URLSearchParams(params); Object.entries(patch).forEach(([k, v]) => (v === "" || v == null ? p.delete(k) : p.set(k, v))); return `#/p/${id}${p.toString() ? "?" + p : ""}`; };
    const chip = (f, label) => `<a class="period ${F.flag === f ? "on" : ""}" href="${link({ f })}"><span>${label}</span></a>`;
    const best = w.best;
    view.innerHTML = `
      <div class="page-head"><div><div class="eyebrow">Produto monitorado</div><h1>${esc(w.query)}</h1>
        <p>Última busca ${w.last_run ? `${fmtLocal(w.last_run)} (${rel(w.last_run)})` : "em andamento"} · atualiza sozinho a cada ${S.status?.interval_min ?? 30} min</p></div>
        ${STATIC ? "" : `<div style="display:flex;gap:8px"><button class="btn" id="cfgBtn">Preço alvo e filtros</button><button class="btn btn-primary" id="refBtn" ${w.running ? "disabled" : ""}>${icon("refresh")}<span>${w.running ? "Buscando…" : "Buscar agora"}</span></button></div>`}</div>
      ${storeDots(w.stores, w.running)}
      <div class="hero-price">
        <div class="kpi"><div class="label">Menor preço agora</div><div class="value small">${brl(best?.price)}</div><div class="sub">${best ? `${esc(best.store)} · <a href="${esc(safeUrl(best.url))}" target="_blank" rel="noopener">ver oferta</a>` : "—"}</div></div>
        <div class="kpi"><div class="label">Preço de referência</div><div class="value small">${brl(w.ref_price)}</div><div class="sub">Mediana das lojas (novos)</div></div>
        <div class="kpi"><div class="label">Possíveis bugs</div><div class="value small" style="color:${w.bugs ? "var(--bad)" : "inherit"}">${w.bugs}</div><div class="sub">${w.new} oferta(s) nova(s) em 24 h</div></div>
        <div class="kpi"><div class="label">Menor preço por dia</div>${sparkline(w.history)}</div>
      </div>
      <div class="filters">
        <div class="periods"><span class="periods-label">Mostrar</span>${chip("", `Todas (${w.items.length})`)}${count("bugao") ? chip("bugao", `Bugões (${count("bugao")})`) : ""}${chip("bug", `Bugs de preço (${count("bug")})`)}${chip("abaixo", `Abaixo da média (${count("abaixo")})`)}${chip("nova", `Novas (${count("nova")})`)}${chip("queda", `Preço caiu (${count("queda")})`)}${w.target_price ? chip("alvo", `No preço alvo (${count("alvo")})`) : ""}${chip("suspeito", `Suspeitas (${count("suspeito")})`)}</div>
        <select id="fStore"><option value="">Todas as lojas</option>${stores.map((s) => `<option value="${esc(s)}" ${s === F.store ? "selected" : ""}>${esc(storeLabel(s))}</option>`).join("")}</select>
        <select id="fSort"><option value="preco">Menor preço</option><option value="desconto" ${F.sort === "desconto" ? "selected" : ""}>Maior desconto vs. referência</option><option value="novas" ${F.sort === "novas" ? "selected" : ""}>Mais recentes</option></select>
        <label class="check"><input type="checkbox" id="fUsados" ${F.usados ? "checked" : ""}> Incluir usados</label>
        <label class="check"><input type="checkbox" id="fPromo" ${F.promo ? "checked" : ""}> Incluir comunidades (Pelando, Promobit)</label>
      </div>
      <p class="results-info">${items.length} oferta(s)${w.running ? " · a busca continua e a lista se atualiza sozinha" : ""}</p>
      ${items.length ? `<div class="grid">${items.map((o) => offerCard(o)).join("")}</div>` : `<div class="empty">${w.running ? "Consultando as lojas… as ofertas aparecem em alguns segundos." : "Nenhuma oferta com esses filtros."}</div>`}
      ${w.coupons.length ? `<section class="section" style="margin-top:28px"><div class="section-head"><h2>Cupons para as lojas com melhor preço</h2><a href="#/cupons">Todos os cupons</a></div><div class="grid">${w.coupons.map(couponCard).join("")}</div></section>` : ""}`;
    const go = (patch) => { location.hash = link(patch); };
    $("#fStore").addEventListener("change", (e) => go({ loja: e.target.value }));
    $("#fSort").addEventListener("change", (e) => go({ ord: e.target.value === "preco" ? "" : e.target.value }));
    $("#fUsados").addEventListener("change", (e) => go({ usados: e.target.checked ? "1" : "" }));
    $("#fPromo").addEventListener("change", (e) => go({ promo: e.target.checked ? "" : "0" }));
    $("#refBtn")?.addEventListener("click", async () => { await api(`/api/watches/${id}/refresh`, { method: "POST" }); toast("Buscando nas lojas…"); pollStatus(true); });
    $("#cfgBtn")?.addEventListener("click", () => openConfig(w));
    bindCommon(view);
  }

  function openConfig(w) {
    $("#modalBody").innerHTML = `<div class="inner"><button class="icon-btn close" id="mClose" aria-label="Fechar">${icon("close")}</button>
      <h2>${esc(w.query)}</h2>
      <form id="cfgForm" class="inline-form" style="margin-top:12px">
        <label>Preço alvo (R$)<input name="target" type="number" step="0.01" min="0" value="${w.target_price ?? ""}" placeholder="ex.: 1800"></label>
        <label style="flex:1">Excluir anúncios com estas palavras (separe por vírgula)<input name="exclude" value="${esc(w.exclude || "")}" placeholder="ex.: ti, 8gb, usado, lhr"></label>
        <button class="btn btn-primary" type="submit">Salvar</button>
      </form>
      <p class="hint">Com preço alvo definido, ofertas iguais ou abaixo dele ganham destaque e, se o Telegram estiver configurado no arquivo .env, você recebe um aviso.</p>
      <div style="display:flex;justify-content:space-between;gap:10px;margin-top:18px"><button class="btn" id="pauseBtn">${w.enabled ? "Pausar monitoramento" : "Retomar monitoramento"}</button><button class="btn btn-danger" id="delBtn">Remover produto</button></div></div>`;
    hydrateIcons($("#modalBody"));
    $("#modal").showModal();
    $("#mClose").onclick = () => $("#modal").close();
    $("#cfgForm").onsubmit = async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      await api(`/api/watches/${w.id}`, { method: "PATCH", body: JSON.stringify({ target_price: f.get("target") ? +f.get("target") : null, exclude: f.get("exclude") }) });
      await api(`/api/watches/${w.id}/refresh`, { method: "POST" });
      $("#modal").close(); toast("Salvo. Buscando de novo com os novos filtros…"); pollStatus(true); router();
    };
    $("#pauseBtn").onclick = async () => { await api(`/api/watches/${w.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !w.enabled }) }); $("#modal").close(); router(); };
    $("#delBtn").onclick = async () => { await api(`/api/watches/${w.id}`, { method: "DELETE" }); $("#modal").close(); await loadWatches(); location.hash = "#/"; };
  }

  async function openHistory(id, title) {
    const h = await api(`/api/offers/${id}/history`);
    const pts = h.map((x) => ({ day: x.seen_at.slice(0, 10), price: x.price }));
    $("#modalBody").innerHTML = `<div class="inner"><button class="icon-btn close" id="mClose" aria-label="Fechar">${icon("close")}</button>
      <h2>${esc(title)}</h2><h4>Histórico de preço</h4>${sparkline(pts)}
      <div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>Quando</th><th>Preço</th></tr></thead><tbody>
      ${h.slice().reverse().map((x) => `<tr><td>${fmtLocal(x.seen_at)}</td><td class="mono">${brl(x.price)}</td></tr>`).join("")}</tbody></table></div></div>`;
    hydrateIcons($("#modalBody"));
    $("#modal").showModal();
    $("#mClose").onclick = () => $("#modal").close();
  }

  // ------------------------------------------------------------ cupons
  async function viewCoupons(view, params) {
    const lojaSel = params.get("loja") || "", codes = params.get("codigo") === "1";
    const d = await api(`/api/coupons?${new URLSearchParams({ ...(lojaSel ? { store: lojaSel } : {}), only_codes: codes })}`);
    const items = d.items.slice().sort((a, b) => b.saving - a.saving);
    view.innerHTML = `
      <div class="page-head"><div><div class="eyebrow">Descontos</div><h1>Cupons</h1>
        <p>Cupons coletados de Pelando, Cuponomia e Méliuz para as lojas monitoradas, ordenados pela economia estimada numa compra de R$ 1.000.</p></div>
        ${STATIC ? "" : `<button class="btn btn-primary" id="cpRefresh" ${d.running ? "disabled" : ""}>${icon("refresh")}<span>${d.running ? "Atualizando…" : "Atualizar cupons"}</span></button>`}</div>
      <div class="filters">
        <select id="cpStore"><option value="">Todas as lojas</option>${d.stores.map((s) => `<option ${s === lojaSel ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
        <label class="check"><input type="checkbox" id="cpCodes" ${codes ? "checked" : ""}> Só cupons com código</label>
        <span class="grow"></span><span class="hint">${d.runs.length ? `Última atualização ${rel(d.runs.map((r) => r.at).sort().pop())}` : ""}</span>
      </div>
      ${items.length ? `<div class="grid">${items.map(couponCard).join("")}</div>` : `<div class="empty">${d.running ? "Buscando cupons…" : (STATIC ? "Nenhum cupom encontrado na última coleta." : "Nenhum cupom encontrado. Clique em Atualizar cupons.")}</div>`}
      ${d.runs.some((r) => r.status !== "ok") ? `<section class="section" style="margin-top:24px"><div class="section-head"><h2>Situação das fontes de cupons</h2></div><div class="table-wrap"><table><thead><tr><th>Loja</th><th>Situação</th><th>Cupons</th><th>Detalhe</th></tr></thead><tbody>
        ${d.runs.map((r) => `<tr><td>${esc(r.store)}</td><td class="st ${r.status}">${esc(r.status)}</td><td>${r.found}</td><td class="err">${esc(r.error || "")}</td></tr>`).join("")}</tbody></table></div></section>` : ""}`;
    const go = (k, v) => { const p = new URLSearchParams(params); v ? p.set(k, v) : p.delete(k); location.hash = `#/cupons${p.toString() ? "?" + p : ""}`; };
    $("#cpStore").addEventListener("change", (e) => go("loja", e.target.value));
    $("#cpCodes").addEventListener("change", (e) => go("codigo", e.target.checked ? "1" : ""));
    $("#cpRefresh")?.addEventListener("click", async () => { await api("/api/coupons/refresh", { method: "POST" }); toast("Atualizando cupons…"); pollStatus(true); router(); });
    bindCommon(view);
  }

  // ------------------------------------------------------------ lojas
  async function viewStores(view) {
    const st = await api("/api/stores");
    view.innerHTML = `
      <div class="page-head"><div><div class="eyebrow">Diagnóstico</div><h1>Lojas e coleta</h1>
        <p>Resultado da última consulta em cada loja. ${STATIC ? "Nesta versão publicada a coleta roda nos servidores do GitHub, que algumas lojas bloqueiam mais do que um computador de casa." : "Lojas com bloqueio anti-robô podem falhar; desligue-as no arquivo .env (PRECOS_DISABLED_STORES)."}</p></div></div>
      <div class="table-wrap"><table><thead><tr><th>Loja</th><th>Tipo</th><th>Última consulta</th><th>Situação</th><th>Lidos / relevantes</th><th>Sucesso</th><th>Detalhe</th></tr></thead><tbody>
      ${st.map((s) => `<tr><td><strong>${esc(s.name)}</strong>${s.note ? `<div class="hint">${esc(s.note)}</div>` : ""}</td><td>${esc(s.kind)}</td>
        <td>${s.last ? `${rel(s.last.at)}<div class="hint">${esc(s.last.query)}</div>` : "—"}</td>
        <td class="st ${s.last?.status || ""}">${s.enabled ? esc(ST[s.last?.status] || "Aguardando") : "Desligada"}</td>
        <td class="mono">${s.last ? `${s.last.seen} / ${s.last.matched}` : "—"}</td><td>${s.runs ? `${s.ok}/${s.runs}` : "—"}</td><td class="err">${esc(s.last?.error || "")}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="hint" style="margin-top:12px">"Lidos" são os anúncios que a loja devolveu; "relevantes" são os que têm todos os termos da busca e não parecem acessório ou outra variante.</p>`;
  }

  // ------------------------------------------------------------ busca e situação
  async function doSearch(q) {
    q = (q || "").trim();
    if (q.length < 2) { $("#searchInput").focus(); return; }
    let r;
    try {
      r = await api("/api/search", { method: "POST", body: JSON.stringify({ q }) });
    } catch (e) {
      if (!e.notFound) throw e;
      $("#searchInput").value = "";
      location.hash = `#/busca?${new URLSearchParams({ q })}`;
      return;
    }
    $("#searchInput").value = "";
    if (STATIC) { location.hash = `#/p/${r.id}`; return; }
    toast(`Buscando "${q}" nas lojas…`);
    await loadWatches();
    location.hash = `#/p/${r.id}`;
    pollStatus(true);
  }
  // ------------------------------------------------------------ busca de produto novo no site publicado
  // O site é estático: um produto novo é pedido por uma issue no GitHub ("Buscar: produto"), que dispara
  // a coleta (.github/workflows/busca.yml). Enquanto isso, links para olhar direto nas lojas.
  const PENDING = "busca-pendente", PENDING_MAX = 10 * 60 * 1000;
  const normQ = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
  const slugQ = (q) => normQ(q).replace(/ /g, "-");
  function storeLinks(q) {
    const e = encodeURIComponent(q);
    return [
      ["KaBuM!", `https://www.kabum.com.br/busca/${slugQ(q)}`],
      ["Pichau", `https://www.pichau.com.br/search?q=${e}`],
      ["Terabyte", `https://www.terabyteshop.com.br/busca?str=${e}`],
      ["Mercado Livre", `https://lista.mercadolivre.com.br/${slugQ(q)}`],
      ["Amazon", `https://www.amazon.com.br/s?k=${e}`],
      ["Magalu", `https://www.magazineluiza.com.br/busca/${e}/`],
      ["Zoom", `https://www.zoom.com.br/search?q=${e}`],
      ["Google Shopping", `https://www.google.com/search?tbm=shop&q=${e}`],
    ];
  }
  function issueUrl(q, repo) {
    const body = `Pedido feito pelo site do Radar de Preços.\n\nAo criar esta issue, o GitHub Actions passa a monitorar "${q}", consulta as lojas, publica o site de novo (uns 5 minutos) e responde aqui com o menor preço.`;
    return `https://github.com/${repo}/issues/new?${new URLSearchParams({ title: `Buscar: ${q}`, labels: "busca", body })}`;
  }
  // ------------------------------------------------------------ busca instantânea (qualquer produto, na hora)
  const BUSCA = new Map();   // resultados já recebidos nesta aba (trocar filtros não busca de novo)
  async function fetchBusca(base, q) {
    if (BUSCA.has(q)) return BUSCA.get(q);
    const ctrl = new AbortController(), t = setTimeout(() => ctrl.abort(), 90000);
    try {
      const r = await fetch(`${base}/api/buscar?${new URLSearchParams({ q })}`, { signal: ctrl.signal, cache: "no-store" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || `Erro ${r.status}`);
      BUSCA.set(q, data);
      return data;
    } catch (e) {
      throw new Error(e.name === "AbortError" ? "O servidor de busca não respondeu a tempo." : e.message === "Failed to fetch" ? "O servidor de busca não está disponível." : e.message);
    } finally { clearTimeout(t); }
  }
  function storeLinksHtml(q) {
    return `<div class="store-links">${storeLinks(q).map(([n, u]) => `<a class="btn btn-sm" href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(n)} ${icon("external")}</a>`).join("")}</div>`;
  }
  function askMonitor(q, repo) {
    if (!STATIC) {
      return api("/api/search", { method: "POST", body: JSON.stringify({ q }) }).then(async (r) => {
        toast(`"${q}" agora é monitorado.`); await loadWatches(); location.hash = `#/p/${r.id}`; pollStatus(true);
      });
    }
    window.open(issueUrl(q, repo), "_blank", "noopener");
    store.set(PENDING, JSON.stringify({ q, at: Date.now() }));
    toast("Na aba do GitHub, clique em Create. O produto entra no site em uns 5 minutos.");
    watchPending();
  }
  async function viewBusca(view, params) {
    const q = (params.get("q") || "").replace(/[^\p{L}\p{N} \-.+/]/gu, " ").replace(/\s+/g, " ").trim().slice(0, 80);
    if (q.length < 2) { location.hash = "#/"; return; }
    const F = { store: params.get("loja") || "", flag: params.get("f") || "" };
    const meta = STATIC ? await api("/api/meta") : { api_url: "", repo: "" };
    const base = STATIC ? meta.api_url : "";
    const n = (viewBusca._n = (viewBusca._n || 0) + 1);
    const head = (sub, extra = "") => `<div class="page-head"><div><div class="eyebrow">Busca instantânea</div><h1>${esc(q)}</h1><p>${sub}</p></div>${extra}</div>`;
    const monitorBtn = STATIC && !meta.repo ? "" : `<button class="btn" id="monBtn">${icon("bolt")}<span>Monitorar este produto (histórico e alertas)</span></button>`;
    if (STATIC && !base) return buscaFallback(view, q, meta.repo, "A busca instantânea ainda não foi configurada neste site.", head, monitorBtn);
    if (!BUSCA.has(q)) {
      view.innerHTML = head("Consultando as lojas agora") + `<div class="empty"><div class="skeleton" style="height:6px;margin-bottom:14px"></div>
        <p><strong>Buscando nas lojas…</strong> ${STATIC ? "a primeira busca do dia pode levar até 1 minuto (o servidor gratuito acorda)." : "leva até 30 segundos."}</p>
        <p class="hint" style="margin-top:10px">Enquanto isso, olhe direto nas lojas:</p>${storeLinksHtml(q)}</div>`;
      hydrateIcons(view);
    }
    let d;
    try {
      d = await fetchBusca(base, q);
    } catch (e) {
      if (n === viewBusca._n) buscaFallback(view, q, meta.repo, e.message, head, monitorBtn);
      return;
    }
    if (n !== viewBusca._n) return;   // o usuário já foi para outra página
    let items = d.items.filter((o) => !F.store || o.store === F.store || o.via === F.store);
    if (F.flag) items = items.filter((o) => o.flags.includes(F.flag));
    const count = (f) => d.items.filter((o) => o.flags.includes(f)).length;
    const link = (patch) => { const p = new URLSearchParams(params); Object.entries(patch).forEach(([k, v]) => (v === "" || v == null ? p.delete(k) : p.set(k, v))); return `#/busca?${p}`; };
    const chip = (f, label) => `<a class="period ${F.flag === f ? "on" : ""}" href="${link({ f })}"><span>${label}</span></a>`;
    const runs = Object.fromEntries(d.stores.map((s) => [s.store, s]));
    const stores = d.stores.map((s) => s.store).sort((a, b) => a.localeCompare(b, "pt-BR"));
    const label = (s) => { const r = runs[s], c = d.items.filter((o) => o.store === s || o.via === s).length; return !c && r && r.status !== "ok" && r.status !== "vazio" ? `${s} (${r.status})` : `${s} (${c})`; };
    const best = d.best;
    view.innerHTML = head(`Consultado ${rel(d.generated_at)} em ${d.stores.length} lojas${d.seconds ? ` (${String(d.seconds).replace(".", ",")} s)` : ""}. Os preços não ficam guardados: para ter histórico e alertas, monitore o produto.`,
      monitorBtn ? `<div style="display:flex;gap:8px">${monitorBtn}</div>` : "") + `
      ${storeDots(d.stores)}
      <div class="hero-price">
        <div class="kpi"><div class="label">Menor preço agora</div><div class="value small">${brl(best?.price)}</div><div class="sub">${best ? `${esc(best.store)} · <a href="${esc(safeUrl(best.url))}" target="_blank" rel="noopener">ver oferta</a>` : "—"}</div></div>
        <div class="kpi"><div class="label">Preço de referência</div><div class="value small">${brl(d.ref_price)}</div><div class="sub">Mediana das lojas (novos)</div></div>
        <div class="kpi"><div class="label">Possíveis bugs</div><div class="value small" style="color:${d.bugs ? "var(--bad)" : "inherit"}">${d.bugs}</div><div class="sub">${d.bugaos ? `${d.bugaos} bugão(ões)` : "Abaixo de 70% da referência"}</div></div>
      </div>
      <div class="filters">
        <div class="periods"><span class="periods-label">Mostrar</span>${chip("", `Todas (${d.items.length})`)}${count("bugao") ? chip("bugao", `Bugões (${count("bugao")})`) : ""}${chip("bug", `Bugs de preço (${count("bug")})`)}${chip("abaixo", `Abaixo da média (${count("abaixo")})`)}${chip("suspeito", `Suspeitas (${count("suspeito")})`)}</div>
        <select id="fStore"><option value="">Todas as lojas</option>${stores.map((s) => `<option value="${esc(s)}" ${s === F.store ? "selected" : ""}>${esc(label(s))}</option>`).join("")}</select>
      </div>
      <p class="results-info">${items.length} oferta(s)</p>
      ${items.length ? `<div class="grid">${items.map((o) => offerCard(o)).join("")}</div>` : `<div class="empty">Nenhuma oferta encontrada${F.store || F.flag ? " com esses filtros" : ""}. Olhe direto nas lojas:${storeLinksHtml(q)}</div>`}
      ${d.coupons?.length ? `<section class="section" style="margin-top:28px"><div class="section-head"><h2>Cupons para estas lojas</h2><a href="#/cupons">Todos os cupons</a></div><div class="grid">${d.coupons.map(couponCard).join("")}</div></section>` : ""}`;
    $("#fStore").addEventListener("change", (e) => { location.hash = link({ loja: e.target.value }); });
    $("#monBtn")?.addEventListener("click", () => askMonitor(q, meta.repo));
    bindCommon(view);
  }
  function buscaFallback(view, q, repo, reason, head, monitorBtn) {
    view.innerHTML = head("A busca na hora não funcionou desta vez", monitorBtn ? `<div style="display:flex;gap:8px">${monitorBtn}</div>` : "") + `
      <div class="empty"><p>${esc(reason)}</p>
      <p style="margin-top:10px">Olhe direto nas lojas, com a busca já preenchida:</p>${storeLinksHtml(q)}
      ${monitorBtn ? `<p class="hint" style="margin-top:14px">Ou clique em <strong>Monitorar este produto</strong>: o radar passa a buscá-lo de hora em hora e guarda o histórico.</p>` : ""}</div>`;
    hydrateIcons(view);
    $("#monBtn")?.addEventListener("click", () => askMonitor(q, repo));
  }
  function pendingSearch() {
    try {
      const p = JSON.parse(store.get(PENDING, "null"));
      if (p && p.q && Date.now() - p.at < PENDING_MAX) return p;
    } catch { /* ignorado */ }
    store.set(PENDING, "");
    return null;
  }
  function pendingBar(text) {
    let bar = $("#pendingBar");
    if (!text) { bar?.remove(); return; }
    if (!bar) { bar = document.createElement("div"); bar.id = "pendingBar"; bar.className = "pending-bar"; document.body.appendChild(bar); }
    bar.textContent = text;
  }
  async function watchPending() {
    clearTimeout(watchPending._t);
    const p = pendingSearch();
    if (!p) { pendingBar(""); return; }
    try {
      await api("/api/status");   // recarrega os dados se saiu uma publicação nova
      await loadWatches();
    } catch { /* tenta de novo no próximo ciclo */ }
    const hit = S.watches.find((w) => normQ(w.query) === normQ(p.q));
    if (hit) {
      store.set(PENDING, "");
      pendingBar("");
      if ($("#modal").open) $("#modal").close();
      toast(`"${hit.query}" chegou: abrindo a página do produto.`);
      location.hash = `#/p/${hit.id}`;
      return;
    }
    if (Date.now() - p.at >= PENDING_MAX) {
      store.set(PENDING, "");
      pendingBar("");
      toast(`"${p.q}" ainda não apareceu. A issue no GitHub mostra o andamento; o site atualiza sozinho.`);
      return;
    }
    pendingBar(`Buscando "${p.q}" nas lojas, o site atualiza sozinho…`);
    watchPending._t = setTimeout(watchPending, 60000);
  }
  async function loadWatches() { S.watches = await api("/api/watches"); renderNav(); }

  let pollTimer = null, wasRunning = false;
  async function pollStatus(force = false) {
    clearTimeout(pollTimer);
    try {
      const st = S.status = await api("/api/status");
      const dot = $("#statusDot"), txt = $("#statusText");
      dot.className = "dot " + (st.running ? "running" : st.scheduler_alive ? "ok" : "parado");
      const n = Object.keys(st.watches_running).length;
      txt.textContent = st.static ? `Atualizado ${rel(st.generated_at)}` : st.running ? (n ? `Buscando ${n} produto(s)…` : "Atualizando cupons…") : `${st.auto_update ? "Monitorando" : "Monitoramento automático desligado"}${st.last_update ? ` · atualizado ${rel(st.last_update)}` : ""}`;
      $("#statusBox").title = st.last_update ? `Última coleta: ${fmtLocal(st.last_update)}` : "Situação da coleta";
      // coleta automática que terminou entre duas consultas: a página também precisa recarregar
      const changed = !st.static && pollStatus._last !== undefined && st.last_update !== pollStatus._last;
      pollStatus._last = st.last_update;
      if (st.running || wasRunning || force || changed) {
        await loadWatches();
        if (!$("#modal").open) router();
      }
      if ((wasRunning || changed) && !st.running) toast("Preços atualizados.");
      wasRunning = st.running;
      if (st.static && st.generated_at !== pollStatus._gen) { pollStatus._gen = st.generated_at; if (!force) { await loadWatches(); if (!$("#modal").open) router(); } }
      pollTimer = setTimeout(pollStatus, st.static ? 300000 : st.running ? 2500 : 30000);
    } catch {
      $("#statusDot").className = "dot parado"; $("#statusText").textContent = STATIC ? "Sem conexão" : "Servidor parado";
      pollTimer = setTimeout(pollStatus, 10000);
    }
  }

  function applyTheme(t) { if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; }
  function closeMenu() { $("#sidebar").classList.remove("open"); $("#scrim").classList.remove("show"); }

  async function init() {
    applyTheme(store.get("theme", ""));
    hydrateIcons();
    $("#themeBtn").addEventListener("click", () => {
      const dark = document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
      const t = dark ? "light" : "dark"; store.set("theme", t); applyTheme(t);
    });
    $("#menuBtn").addEventListener("click", () => { $("#sidebar").classList.add("open"); $("#scrim").classList.add("show"); });
    $("#scrim").addEventListener("click", closeMenu);
    $("#statusBox").addEventListener("click", () => { location.hash = "#/lojas"; });
    $("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); doSearch($("#searchInput").value).catch((err) => toast(err.message)); });
    $("#searchBtn").addEventListener("click", () => doSearch($("#searchInput").value).catch((err) => toast(err.message)));
    $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("#modal").close(); });
    window.addEventListener("hashchange", router);
    await loadWatches().catch(() => {});
    if (STATIC) watchPending();
    await pollStatus();
    router();
  }
  init();
})();
