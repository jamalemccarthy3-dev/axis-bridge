"""marketplace_export.py - turns the published products into a static, indexable storefront: plain HTML pages with clean URLs, meta tags, structured data, a sitemap and robots.txt.

Search engines cannot index a program running on one computer, so this is how the Marketplace becomes discoverable: build the site, then publish the folder yourself (for example to GitHub Pages). Nothing is
uploaded for you. Every page is self-contained: no scripts, no trackers, no external resources. Everything is escaped before it is written, so a product cannot inject markup into a page. A star rating is
written only when real, verified reviews exist; a Free and Open product's code is not hosted here (its page links to its repository, or says it is available inside NEXXUS).
"""
import html
import json
import os
import re

import market_social as social
import marketplace
import seo

CSS = "body{font:16px/1.6 system-ui,sans-serif;max-width:860px;margin:0 auto;padding:16px;background:#0b1220;color:#e2e8f0}a{color:#7dd3fc}h1{margin:.2em 0}.badge{display:inline-block;padding:1px 10px;border-radius:999px;border:1px solid #34d399;color:#86efac;font-size:.8rem}.paid{border-color:#fbbf24;color:#fde68a}.card{border:1px solid #334155;border-radius:12px;padding:12px;margin:10px 0}.muted{color:#94a3b8;font-size:.9rem}pre{background:#05080f;border:1px solid #334155;border-radius:8px;padding:10px;overflow:auto;white-space:pre-wrap}.c{border-left:2px solid #38bdf8;padding-left:10px;margin:8px 0}"


def esc(s):
    return html.escape(str(s), quote=True)


def md(text):
    """A deliberately tiny markdown subset (headings, lists, code blocks, paragraphs, bold, inline code, https links). Everything is escaped FIRST."""
    out, in_code, in_list = [], False, False
    for line in str(text).replace("\r\n", "\n").split("\n"):
        if line.strip().startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(esc(line))
            continue
        e = esc(line)
        e = re.sub(r"`([^`]+)`", r"<code>\1</code>", e)
        e = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", e)
        e = re.sub(r"\[([^\]]+)\]\((https://[^\s)]+)\)", r'<a href="\2" rel="noopener nofollow">\1</a>', e)
        m = re.match(r"^(#{1,3})\s+(.*)", e)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("<h%d>%s</h%d>" % (len(m.group(1)) + 1, m.group(2), len(m.group(1)) + 1))
        elif re.match(r"^\s*[-*]\s+", e):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>%s</li>" % re.sub(r"^\s*[-*]\s+", "", e))
        elif e.strip():
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("<p>%s</p>" % e)
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def _stars(r):
    return ("%.1f of 5 from %d verified review%s" % (r["avg"], r["count"], "" if r["count"] == 1 else "s")) if r["count"] else "No reviews yet"


def _comments(tree):
    out = []
    for c in tree:
        out.append('<div class="c"><b>%s</b> <span class="muted">%s</span><div>%s</div>%s</div>' % (esc(c["who"] or "removed"), esc(__import__("time").strftime("%Y-%m-%d", __import__("time").gmtime(c["t"]))), esc(c["text"]), _comments(c["replies"])))
    return "".join(out)


def page(prod, base_url):
    card, rec = prod["product"], prod["seo"]
    rating = social.summary(card["id"])
    badge = '<span class="badge">FREE / Open source</span>' if card["free"] else '<span class="badge paid">%s</span>' % esc(("$%.2f" % (card["final_cents"] / 100.0)) if card["final_cents"] else "Free")
    canonical = (base_url.rstrip("/") + rec["path"]) if base_url else rec["path"]
    if card["free"]:
        action = '<p><a href="%s" rel="noopener">View the source repository</a></p>' % esc(card["repo_url"]) if card.get("repo_url") else '<p class="muted">This open-source package is available inside NEXXUS Platform, where its code can be inspected and its checksum verified.</p>'
    else:
        action = '<p><a href="%s" rel="noopener nofollow">Buy now</a></p>' % esc(card["buy_url"]) if card.get("buy_url") else '<p class="muted">Checkout is not set up for this product yet.</p>'
    ld = seo.json_ld(card, rec, rating, base_url).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")      # inside JSON these are exactly the same text, and they can never be read as markup
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>%(title)s</title><meta name="description" content="%(desc)s"><meta name="keywords" content="%(kw)s"><link rel="canonical" href="%(canon)s">
<meta property="og:title" content="%(title)s"><meta property="og:description" content="%(desc)s"><meta property="og:type" content="website"><meta property="og:site_name" content="%(site)s"><meta property="og:url" content="%(canon)s">
<meta name="twitter:card" content="summary"><script type="application/ld+json">%(ld)s</script><style>%(css)s</style></head>
<body><p><a href="../../">&larr; %(site)s</a></p><h1>%(h1)s</h1><p>%(badge)s <span class="muted">by %(seller)s &middot; v%(ver)s &middot; %(cat)s &middot; %(lic)s</span></p>
<p><strong>%(stars)s</strong></p><p>%(summary)s</p><div class="card">%(vet)s</div>%(action)s
<h2>About this product</h2>%(readme)s<h2>Code summary</h2><p>%(cs)s</p><h2>Comments</h2>%(comments)s
<p class="muted">Ratings come only from people who downloaded the package or whose purchase was verified. Keep comments PG-13.</p></body></html>
""" % {"title": esc(rec["meta_title"]), "desc": esc(rec["meta_description"]), "kw": esc(", ".join(rec["keywords"])), "canon": esc(canonical), "site": esc(seo.SITE), "ld": ld, "css": CSS, "h1": esc(card["title"]),
       "badge": badge, "seller": esc(card["seller"]), "ver": esc(card.get("version") or "?"), "cat": esc(card["category"]), "lic": esc(card.get("license") or ""), "stars": esc(_stars(rating)), "summary": esc(card["summary"]),
       "vet": "Automatic safety checks passed: %s.%s" % (esc(", ".join(card["vetting"]["automatic"])), " Tested and reviewed by a person." if card["vetting"]["human_reviewed"] else " Approved by the administrator."),
       "action": action, "readme": md(prod["readme"]), "cs": esc(rec.get("code_summary", "")), "comments": _comments(social.comment_tree(card["id"])) or '<p class="muted">No comments yet.</p>'}


def build_site(out_dir, base_url=""):
    """Write the static storefront. -> the list of files written. Nothing outside out_dir is touched."""
    base_url = base_url.strip()
    if base_url and not re.match(r"^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~/-]*)?$", base_url):
        raise marketplace.MarketError("The site address must be an https URL.")
    cat = marketplace.public_catalog()
    written, rows = [], []
    for card in cat["products"]:
        prod = marketplace.product_page(card["id"], base_url)
        if not prod["seo"]:
            continue
        d = os.path.join(out_dir, "products", prod["seo"]["slug"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(page(prod, base_url))
        written.append(os.path.join("products", prod["seo"]["slug"], "index.html"))
        rows.append((prod, card))
    items = "".join('<div class="card"><h2><a href="products/%s/">%s</a></h2><p>%s</p><p><span class="badge%s">%s</span> <span class="muted">%s &middot; %s</span></p></div>' % (
        esc(p["seo"]["slug"]), esc(c["title"]), esc(c["summary"]), "" if c["free"] else " paid", "FREE / Open source" if c["free"] else esc("$%.2f" % (c["final_cents"] / 100.0)), esc(c["category"]), esc(_stars(social.summary(c["id"])))) for p, c in rows)
    index = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
             '<title>%s</title><meta name="description" content="Vetted community software, scripts and assets, paid and free open source."><style>%s</style></head><body><h1>%s</h1>%s</body></html>' % (
                 esc(seo.SITE), CSS, esc(seo.SITE), items or '<p class="muted">No products are published yet.</p>'))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index)
    written.append("index.html")
    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\n" + (("Sitemap: %s/sitemap.xml\n" % base_url.rstrip("/")) if base_url else ""))
    written.append("robots.txt")
    urls = ["<url><loc>%s</loc></url>" % esc((base_url.rstrip("/") if base_url else "") + p["seo"]["path"]) for p, c in rows]
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % "".join(urls))
    written.append("sitemap.xml")
    return written
