"""factory_platform.py - the platform generator: a branded website or storefront from a brand, your copy and live assets.

Input: a validated platform_factory configuration and an asset resolver (creation id -> files in the Creations hub). Output: a real multi-page site in the instance's own folder
(index, about, products, contact, one stylesheet, the assets copied beside it). Nothing is stubbed:
  * every piece of text is HTML-escaped; the page uses no external file, font, script or URL,
  * a product that names an asset the hub does not hold FAILS the build (it is never silently skipped),
  * after the build, check() reads the files back and proves it: every page parses, every link and asset resolves, the brand is in every title, every product is on the products page.
Orders and messages go to the instance's local inbox (a route in the server). No payment is taken: a storefront here is a catalogue and an order request, and says so on the page.
"""
import hashlib
import html
import html.parser
import json
import os
import re
import shutil
from pathlib import Path

IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
VID_EXT = (".mp4", ".webm")
MAX_PRODUCTS = 100
_E = html.escape


class PlatformError(Exception):
    pass


def _products(config):
    kind, raw = config.get("kind"), config.get("products") or []
    if kind == "site" and raw:
        raise PlatformError("a site has no products: choose the storefront kind, or remove them")
    if kind == "storefront" and not raw:
        raise PlatformError("a storefront needs at least one product")
    if not isinstance(raw, list) or len(raw) > MAX_PRODUCTS:
        raise PlatformError("products must be a list of up to %d" % MAX_PRODUCTS)
    out = []
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            raise PlatformError("product %d must be an object" % (i + 1))
        name, desc = str(p.get("name") or "").strip(), str(p.get("description") or "").strip()
        price = p.get("price")
        if not name or len(name) > 80:
            raise PlatformError("product %d needs a name of up to 80 characters" % (i + 1))
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0 or price != price or price == float("inf"):
            raise PlatformError("product %r needs a price (a number, 0 or more)" % name)
        if len(desc) > 400:
            raise PlatformError("product %r: the description is over 400 characters" % name)
        out.append({"name": name, "price": float(price), "currency": str(p.get("currency") or "").strip().upper()[:3], "description": desc, "asset": str(p.get("asset") or "").strip() or None})
    return out


def _asset_files(resolver, cid):
    files = resolver(cid) if resolver else None
    if not files:
        raise PlatformError("the asset %r is not in the Creations hub" % cid)
    pick = next((f for f in files if f[0].lower().endswith(IMG_EXT + VID_EXT)), None)
    if pick is None:
        raise PlatformError("the asset %r has no image or video file to show" % cid)
    return pick


def _page(brand, title, body, active, pages, accent_script=""):
    nav = "".join('<a href="%s"%s>%s</a>' % (h, ' class="on"' if h == active else "", _E(t)) for h, t in pages)
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>%s</title><link rel="stylesheet" href="style.css"></head>\n'
            '<body><header><a class="brand" href="index.html">%s</a><nav>%s</nav></header><main>\n%s\n</main><footer>%s</footer>%s</body></html>\n') % (
        _E("%s - %s" % (title, brand)), _E(brand), nav, body, _E(brand), accent_script)


_CSS = """:root { --accent: %(accent)s; --bg: #0b1020; --fg: #e8ecf5; --muted: #9aa6bf; --card: #131a30; }
@media (prefers-color-scheme: light) { :root { --bg: #f6f7fb; --fg: #151a2c; --muted: #5a6480; --card: #ffffff; } }
* { box-sizing: border-box; } body { margin: 0; font: 16px/1.55 system-ui, sans-serif; background: var(--bg); color: var(--fg); }
header { display: flex; align-items: center; gap: 24px; padding: 14px 24px; border-bottom: 1px solid color-mix(in srgb, var(--fg) 15%%, transparent); flex-wrap: wrap; }
.brand { font-weight: 800; letter-spacing: .04em; color: var(--accent); text-decoration: none; font-size: 1.2rem; } nav { display: flex; gap: 16px; margin-left: auto; }
nav a { color: var(--muted); text-decoration: none; padding: 4px 2px; border-bottom: 2px solid transparent; } nav a.on, nav a:hover { color: var(--fg); border-bottom-color: var(--accent); }
main { max-width: 1040px; margin: 0 auto; padding: 32px 24px; } h1 { font-size: 2rem; margin: 0 0 8px; } .tag { color: var(--muted); margin: 0 0 24px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 18px; } .card { background: var(--card); border-radius: 12px; padding: 16px; border: 1px solid color-mix(in srgb, var(--fg) 12%%, transparent); display: flex; flex-direction: column; gap: 8px; }
.card img, .card video { width: 100%%; border-radius: 8px; background: #000; max-height: 220px; object-fit: contain; } .price { color: var(--accent); font-weight: 700; }
button, input, textarea, select { font: inherit; padding: 8px 10px; border-radius: 8px; border: 1px solid color-mix(in srgb, var(--fg) 25%%, transparent); background: var(--card); color: var(--fg); }
button { background: var(--accent); color: #fff; border: 0; cursor: pointer; font-weight: 600; } form { display: grid; gap: 12px; max-width: 520px; } footer { padding: 24px; text-align: center; color: var(--muted); }
.note { color: var(--muted); font-size: .9rem; } .ok { color: #34d399; } .bad { color: #f87171; }
"""


def build(workdir, config, resolver=None, instance_id=None):
    """Write the site into <workdir>/site. -> the manifest check() proves. Raises PlatformError for anything that cannot be built honestly."""
    products = _products(config)
    brand, tagline, about = config["brand"], config.get("tagline", ""), config.get("about", "")
    storefront = config["kind"] == "storefront"
    site = Path(workdir) / "site"
    if site.exists():
        shutil.rmtree(site)
    (site / "assets").mkdir(parents=True)
    pages = [("index.html", "Home"), ("about.html", "About")] + ([("products.html", "Products")] if storefront else []) + [("contact.html", "Order" if storefront else "Contact")]
    assets, cards = {}, []
    for p in products:
        media = ""
        if p["asset"]:
            if p["asset"] not in assets:
                fname, data = _asset_files(resolver, p["asset"])[:2]
                safe = re.sub(r"[^A-Za-z0-9._-]", "_", fname)
                rel = "assets/%s-%s" % (hashlib.sha256(data).hexdigest()[:8], safe)
                (site / rel).write_bytes(data)
                assets[p["asset"]] = rel
            rel = assets[p["asset"]]
            media = ('<video src="%s" controls preload="metadata"></video>' % rel) if rel.lower().endswith(VID_EXT) else ('<img src="%s" alt="%s">' % (rel, _E(p["name"])))
        price = ("%s %.2f" % (p["currency"], p["price"])).strip()
        cards.append('<article class="card">%s<h3>%s</h3><p>%s</p><p class="price">%s</p></article>' % (media, _E(p["name"]), _E(p["description"]), _E(price)))
    feat = '<section class="grid">%s</section>' % "".join(cards[:3]) if cards else ""
    (site / "style.css").write_text(_CSS % {"accent": config.get("accent", "#38bdf8")}, encoding="utf-8")
    (site / "index.html").write_text(_page(brand, "Home", '<h1>%s</h1><p class="tag">%s</p>%s' % (_E(brand), _E(tagline), feat), "index.html", pages), encoding="utf-8")
    (site / "about.html").write_text(_page(brand, "About", "<h1>About %s</h1><p>%s</p>" % (_E(brand), _E(about or "No description has been written yet.")), "about.html", pages), encoding="utf-8")
    if storefront:
        (site / "products.html").write_text(_page(brand, "Products", '<h1>Products</h1><section class="grid">%s</section>' % "".join(cards), "products.html", pages), encoding="utf-8")
    items = "".join('<option value="%s">%s</option>' % (_E(p["name"]), _E(p["name"])) for p in products)
    form = ('<h1>%s</h1><form id="f"><input name="name" placeholder="Your name" required maxlength="80">%s<input name="email" type="email" placeholder="Your email" required maxlength="120">'
            '<textarea name="message" rows="4" placeholder="%s" required maxlength="1000"></textarea><button>Send</button><p id="r" class="note"></p></form>'
            '<p class="note">%s</p>') % ("Place an order request" if storefront else "Contact us",
                                          ('<select name="item" required>%s</select><input name="quantity" type="number" min="1" max="999" value="1" required>' % items) if storefront else "",
                                          "Delivery details" if storefront else "Your message",
                                          "This sends an order REQUEST to the owner. No payment is taken on this site." if storefront else "Your message is stored for the owner.")
    script = ('<script>document.getElementById("f").addEventListener("submit",async e=>{e.preventDefault();const r=document.getElementById("r"),d=Object.fromEntries(new FormData(e.target));'
              'try{const x=await fetch("/api/factory/%s/inbox",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(d)});const j=await x.json();'
              'r.className=x.ok?"note ok":"note bad";r.textContent=x.ok?"Received.":(j.message||"Not sent")}catch(err){r.className="note bad";r.textContent="Not sent: "+err.message}});</script>') % (instance_id or "preview")
    (site / "contact.html").write_text(_page(brand, "Order" if storefront else "Contact", form, "contact.html", pages, script), encoding="utf-8")
    return check(site, config, products, assets)


class _Scan(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs, self.stack, self.title, self._in_title, self.text = [], [], "", False, []
        self.void = {"meta", "link", "img", "input", "br", "hr", "source"}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("href", "src", "action"):
            if a.get(k):
                self.refs.append(a[k])
        if tag == "title":
            self._in_title = True
        if tag not in self.void:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        self.text.append(data)


def check(site, config, products=None, assets=None):
    """Read the built site back and prove it. Raises PlatformError listing everything wrong. -> the manifest."""
    site = Path(site)
    problems, files, text_by_page = [], [], {}
    for f in sorted(site.rglob("*")):
        if f.is_file():
            files.append({"path": f.relative_to(site).as_posix(), "bytes": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    names = {x["path"] for x in files}
    for f in sorted(site.glob("*.html")):
        s = _Scan()
        raw = f.read_text(encoding="utf-8")
        s.feed(raw)
        s.close()
        if s.stack:
            problems.append("%s has unclosed tags: %s" % (f.name, ", ".join(sorted(set(s.stack)))))
        if config["brand"] not in html.unescape(s.title):
            problems.append("%s: the brand is not in the title" % f.name)
        for ref in s.refs:
            if re.match(r"^(https?:)?//", ref, re.I):
                problems.append("%s links to an external address: %s" % (f.name, ref))
            elif ref.startswith("/api/"):
                continue
            elif ref.split("#")[0] and ref.split("#")[0] not in names:
                problems.append("%s links to %s, which does not exist" % (f.name, ref))
        text_by_page[f.name] = " ".join(s.text)
    for ref_file in ("index.html", "about.html", "contact.html"):
        if ref_file not in names:
            problems.append("%s was not built" % ref_file)
    prods = products if products is not None else _products(config)
    if config["kind"] == "storefront":
        page = html.unescape(text_by_page.get("products.html", ""))
        for p in prods:
            if p["name"] not in page:
                problems.append("the product %r is not on the products page" % p["name"])
    if problems:
        raise PlatformError("the built site failed its own checks: " + "; ".join(problems[:10]))
    return {"pages": sorted(n for n in names if n.endswith(".html")), "files": files, "products": len(prods), "assets": len(assets or {}), "bytes": sum(x["bytes"] for x in files)}
