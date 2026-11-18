"""Gera a versão estática do Radar de Preços (para o GitHub Pages): copia a interface e exporta os dados em JSON.

Os JSON são as mesmas respostas da API do servidor local (app/main.py); o arquivo web/static-api.js responde
no navegador às rotas /api/... a partir deles. Nada privado é exportado: nem .env, nem tokens, nem caminhos locais.
"""
import json
import os
import shutil
from pathlib import Path

from . import config, db
from . import main as api

# o site só carrega os próprios arquivos; as fotos dos produtos vêm dos sites das lojas (https)
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' https: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'")
HISTORY_POINTS = int(os.environ.get("PRECOS_SITE_HISTORY", "120"))  # pontos de histórico por oferta no site


def export(out_dir: Path, watch_ids: list[int] | None = None, interval_min: int = 60) -> dict:
    """Gera o site em out_dir. watch_ids limita aos produtos publicados (os de config/produtos.json)."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "data").mkdir(parents=True)

    # interface: os mesmos arquivos do servidor local, com caminhos relativos e a API estática
    for f in ("app.js", "styles.css", "static-api.js"):
        shutil.copy2(config.WEB_DIR / f, out_dir / f)
    html = (config.WEB_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/static/styles.css"', 'href="styles.css"')
    html = html.replace('<script src="/static/app.js"></script>',
                        '<script src="static-api.js"></script>\n<script src="app.js"></script>')
    html = html.replace('<meta charset="utf-8">',
                        f'<meta charset="utf-8">\n  <meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
                        '  <meta name="referrer" content="no-referrer">', 1)
    if "static-api.js" not in html or "Content-Security-Policy" not in html or 'href="styles.css"' not in html:
        raise RuntimeError("web/index.html mudou: não foi possível adaptar a página para a versão estática")
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    keep = set(watch_ids) if watch_ids is not None else None
    published = lambda w: keep is None or w["id"] in keep  # noqa: E731

    watches = [w for w in api.watches() if published(w)]
    details, histories = {}, {}
    for w in watches:
        d = api.watch(w["id"], inactive=False)
        d["running"] = None
        details[str(w["id"])] = d
        for o in d["items"]:
            histories[str(o["id"])] = db.history(o["id"])[-HISTORY_POINTS:]

    dash = api.dashboard()
    dash["watches"] = watches
    dash["hot"] = [o for o in dash["hot"] if published({"id": o["watch_id"]})]
    dash["new"] = [o for o in dash["new"] if published({"id": o["watch_id"]})]
    dash["bugaos"] = sum(1 for o in dash["hot"] if "bugao" in o["flags"])

    generated = db.now()
    status = {"running": False, "watches_running": {}, "coupons_running": False, "auto_update": True,
              "interval_min": interval_min, "scheduler_alive": True, "telegram": False,
              "static": True, "generated_at": generated}
    dash["status"] = status
    coupons = api.list_coupons(None, False)
    coupons["running"] = False
    meta = {"repo": os.environ.get("GITHUB_REPOSITORY", ""), "generated_at": generated, "interval_min": interval_min}

    data = {"generated_at": generated, "meta": meta, "status": status, "dashboard": dash, "watches": watches,
            "details": details, "coupons": coupons, "stores": api.stores()}
    _write(out_dir / "data" / "precos.json", data)
    _write(out_dir / "data" / "historico.json", histories)
    _write(out_dir / "data" / "status.json", {"generated_at": generated})
    return {"watches": len(watches), "offers": sum(len(d["items"]) for d in details.values()),
            "coupons": len(coupons["items"]), "generated_at": generated}


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
