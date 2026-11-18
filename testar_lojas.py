"""Testa cada loja sem gravar nada e mostra quantos anúncios foram lidos e quantos são relevantes.

Uso:  .venv\\Scripts\\python.exe testar_lojas.py "rtx 3060 12gb" [loja]
Com PRECOS_DEBUG=1 as páginas baixadas ficam em data\\debug para análise.
"""
import sys
import time

from app import coupons
from app.collector import _one_store
from app.stores.catalog import STORES

for _s in (sys.stdout, sys.stderr):  # o console do Windows (cp1252) não imprime ✓, emojis etc.
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

q =sys.argv[1] if len(sys.argv) > 1 else "rtx 3060 12gb"
only = sys.argv[2:] or None
print(f'Buscando "{q}"\n')
for sid, name, fn, _kind, _note in STORES:
    if only and sid not in only:
        continue
    t0 = time.monotonic()
    r = _one_store(sid, name, fn, q, [])
    print(f"{name:20} {r.status:10} lidos={r.seen:3} relevantes={len(r.offers):3} {time.monotonic() - t0:5.1f}s  {r.error or ''}")
    for o in sorted(r.offers, key=lambda o: o.price)[:3]:
        print(f"    R$ {o.price:10,.2f}  {o.title[:70]}  {o.url[:90]}")
if not only or "cupons" in only:
    print("\nCupons")
    for store in coupons.COUPON_STORES:
        cps, errs = coupons.fetch_store(store)
        print(f"{store:15} {len(cps):3} cupons  {'; '.join(errs)[:150]}")
        for c in cps[:3]:
            print(f"    {c.code or '(sem código)':18} {c.title[:80]}")
