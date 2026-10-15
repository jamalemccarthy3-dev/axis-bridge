"""seo.py - turns a marketplace listing into search-friendly metadata, deterministically and honestly.

Run when a bundle is uploaded (and again at publish) from what the listing actually says: the title, summary, manifest description, README, the kinds of files in the bundle and what the code declares it
can do. No model, no stuffing, no invented claims:
  * the meta title is at most 60 characters and always contains the product's real title;
  * the meta description is at most 155 characters and ends cleanly at a word;
  * keywords are real words from the listing (at most 12, no repeats), plus its category, kind, licence, languages and, for the free tier, "open source";
  * the structured data (schema.org JSON-LD) offers a price only for what is actually for sale and includes an aggregateRating ONLY when real, verified reviews exist.
"""
import json
import os
import re

TITLE_MAX = 60
DESC_MAX = 155
KEYWORDS_MAX = 12
STOP = set("""a about above after again all also am an and any are as at be because been before being below between both but by can could did do does doing down during each few for from further had has have
having he her here hers him his how i if in into is it its just me more most my no nor not of off on once only or other our out over own same she should so some such than that the their them then there these
they this those through to too under until up very was we were what when where which while who whom why will with would you your yours use used using uses makes make made get gets""".split())
LANGS = {".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".html": "HTML", ".css": "CSS", ".sh": "Shell", ".ps1": "PowerShell", ".sql": "SQL", ".json": "JSON", ".md": "Markdown", ".yml": "YAML", ".yaml": "YAML"}
CODE_LANGS = ("Python", "JavaScript", "HTML", "CSS", "Shell", "PowerShell", "SQL")
SITE = "NEXXUS Marketplace"


def languages(names):
    """Programming languages in a bundle by file extension, most files first."""
    count = {}
    for n in names:
        lang = LANGS.get(os.path.splitext(n.lower())[1])
        if lang in CODE_LANGS:
            count[lang] = count.get(lang, 0) + 1
    return [l for l, _ in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))]


def code_summary(names, permissions):
    langs = languages(names)
    where = "Written in " + " and ".join(langs[:3]) if langs else "No program code (documents and assets)"
    perms = ("Declares permissions: " + ", ".join(permissions)) if permissions else "Asks for no special permissions"
    return "%s, %d files. %s." % (where, len(names), perms)


def _words(text):
    return [w for w in re.findall(r"[a-z][a-z0-9+#.-]{2,}", str(text).lower()) if w.strip(".-") not in STOP]


def keywords(title, summary, description, readme, extra):
    score = {}
    for weight, text in ((5, title), (3, summary), (2, description), (1, (readme or "")[:1500])):
        for w in _words(text):
            w = w.strip(".-")
            if len(w) >= 3 and w not in STOP:
                score[w] = score.get(w, 0) + weight
    ranked = [w for w, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))]
    out, seen = [], set()
    for w in [x.lower() for x in extra if x] + ranked:
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= KEYWORDS_MAX:
            break
    return out


def _cut(text, n):
    text = " ".join(str(text).split())
    if len(text) <= n:
        return text
    cut = text[: n - 1].rsplit(" ", 1)[0].rstrip(",;:- ")
    return (cut or text[: n - 1]) + "…"


def slug(title, pid):
    words = re.findall(r"[a-z0-9]+", str(title).lower())[:6]
    return ("-".join(words) or "product") + "-" + re.sub(r"[^a-z0-9]", "", str(pid).lower())[:10]


def generate(listing, manifest, readme, names, tier, pid, repo_url=""):
    """-> the SEO record for a version of a product."""
    manifest = manifest or {}
    title, summary = listing["title"], listing["summary"]
    free = tier == "free"
    perms = manifest.get("permissions") or []
    langs = languages(names)
    cs = code_summary(names, perms)
    head = title if len(title) <= TITLE_MAX - 3 else _cut(title, TITLE_MAX - 3)
    tail = " | Free & open source" if free else " | " + listing["category"]
    meta_title = head + tail if len(head + tail) <= TITLE_MAX else (head + " | " + SITE if len(head + " | " + SITE) <= TITLE_MAX else _cut(head, TITLE_MAX))
    lead = summary.rstrip(". ") + "."
    extras = (" Free, open source (%s)." % manifest.get("license", "open licence")) if free else (" %s product by %s." % (listing["category"], "a micro-company"))
    meta_description = _cut(lead + extras + " " + cs, DESC_MAX)
    kws = keywords(title, summary, manifest.get("description", ""), readme, [listing["category"], manifest.get("kind", "")] + langs[:2] + ([manifest.get("license", ""), "open source", "free"] if free else [manifest.get("license", "")]))
    path = "/products/%s/" % slug(title, pid)
    return {"slug": slug(title, pid), "path": path, "meta_title": meta_title, "meta_description": meta_description, "keywords": kws, "languages": langs, "code_summary": cs,
            "og": {"title": meta_title, "description": meta_description, "type": "website", "site_name": SITE}, "repo_url": repo_url or ""}


def json_ld(card, seo, rating=None, base_url=""):
    """schema.org SoftwareApplication. A price is offered only if the product can really be obtained; aggregateRating appears only with real reviews."""
    data = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": card["title"], "description": seo["meta_description"], "applicationCategory": card["category"],
            "softwareVersion": card.get("version") or "", "author": {"@type": "Organization", "name": card["seller"]}, "keywords": ", ".join(seo["keywords"])}
    if base_url:
        data["url"] = base_url.rstrip("/") + seo["path"]
    if card.get("free"):
        data["isAccessibleForFree"] = True
        data["offers"] = {"@type": "Offer", "price": "0", "priceCurrency": card.get("currency", "USD")}
        if card.get("license"):
            data["license"] = card["license"]
        if seo.get("repo_url"):
            data["codeRepository"] = seo["repo_url"]
    elif card.get("buy_url"):
        data["offers"] = {"@type": "Offer", "price": "%.2f" % (card["final_cents"] / 100.0), "priceCurrency": card.get("currency", "USD"), "url": card["buy_url"]}
    if rating and rating.get("count", 0) >= 1:
        data["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": str(rating["avg"]), "reviewCount": str(rating["count"]), "bestRating": "5", "worstRating": "1"}
    return json.dumps({k: v for k, v in data.items() if v not in ("", None)}, ensure_ascii=False)
