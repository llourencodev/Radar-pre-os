/* Radar de Preços — API estática (GitHub Pages).
   Responde no navegador às mesmas rotas /api/... do servidor local, a partir de data/precos.json,
   gerado a cada coleta pelo GitHub Actions. As rotas de escrita não existem aqui: os produtos
   monitorados ficam em config/produtos.json no repositório. */
(() => {
  "use strict";
  const D = { loaded: null, data: null, hist: null };

  async function getJSON(path) {
    const r = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(`Não foi possível ler ${path} (erro ${r.status})`);
    return r.json();
  }
  const ready = () => (D.loaded ||= getJSON("data/precos.json").then((d) => { D.data = d; }).catch((e) => { D.loaded = null; throw e; }));

  class ApiError extends Error {
    constructor(msg, extra) { super(msg); Object.assign(this, extra || {}); }
  }
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const norm = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();

  async function route(path, opts = {}) {
    const method = (opts.method || "GET").toUpperCase();
    const url = new URL(path, location.href);
    const p = url.pathname.replace(/^.*?\/api\//, "/api/");
    await ready();
    const d = D.data;

    if (method !== "GET") {
      if (p === "/api/search") {
        // busca entre os produtos já monitorados; produto novo se cadastra no GitHub
        const q = norm(JSON.parse(opts.body || "{}").q);
        const hit = d.watches.find((w) => norm(w.query) === q) || d.watches.find((w) => norm(w.query).includes(q) || q.includes(norm(w.query)));
        if (hit) return { id: hit.id };
        throw new ApiError("Para monitorar um produto novo, adicione-o em config/produtos.json", { notFound: true, repo: d.meta.repo });
      }
      throw new ApiError("Nesta versão publicada a coleta é automática (GitHub Actions); não há servidor para esta ação.");
    }

    if (p === "/api/status") {
      // a cada consulta, confere se já existe uma publicação mais nova
      try {
        const s = await getJSON("data/status.json");
        if (s.generated_at && s.generated_at !== d.generated_at) { D.loaded = null; D.hist = null; await ready(); }
      } catch { /* mantém os dados atuais */ }
      return clone(D.data.status);
    }
    if (p === "/api/dashboard") return clone(d.dashboard);
    if (p === "/api/watches") return clone(d.watches);
    let m = p.match(/^\/api\/watches\/(\d+)$/);
    if (m) {
      const w = d.details[m[1]];
      if (!w) throw new ApiError("Produto não encontrado");
      return clone(w);
    }
    m = p.match(/^\/api\/offers\/(\d+)\/history$/);
    if (m) {
      D.hist ||= await getJSON("data/historico.json");
      return clone(D.hist[m[1]] || []);
    }
    if (p === "/api/coupons") {
      const store = url.searchParams.get("store"), codes = url.searchParams.get("only_codes") === "true";
      const c = clone(d.coupons);
      c.items = c.items.filter((x) => (!store || x.store === store) && (!codes || x.code));
      return c;
    }
    if (p === "/api/stores") return clone(d.stores);
    throw new ApiError(`Rota não disponível na versão publicada: ${p}`);
  }

  window.PRECOS_API = route;
})();
