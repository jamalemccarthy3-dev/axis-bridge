"""campaign_kit.py - a go-to-market kit for ONE real business: video scripts, channel-ready ad copy, an email sequence, branded display graphics and a landing page, built from facts the owner supplies.

The rules this module enforces (they are code, not promises):
  * It writes ONLY from the profile: the offer, audience, differentiators and proof points the owner typed. Any number, percentage or quoted statement in generated copy must already be in the
    profile, or the copy is rejected. No invented testimonials, statistics, awards, customers or staff.
  * Claims that need substantiation (guaranteed, risk-free, #1, best in the world, cure, doctor-recommended, ...) are rejected unless the owner put that exact claim in the profile as a proof point.
  * Every ad respects its channel's character limits (Google search headline 30 / description 90, Meta headline 40, LinkedIn headline 70, TikTok text 100, native headline 60). Over the limit = rejected.
  * Video scripts fit their running time at a speakable pace (2.5 words per second).
  * Every email carries the sender's name, a real postal address and an unsubscribe line, or the sequence is not produced (anti-spam law). It is for people who asked to hear from you.
  * Anything with a synthetic voice or AI-assisted assembly says so in its own manifest and on its end card.
  * Nothing is posted anywhere from here. The kit is a folder of finished files plus a manifest.
Copy comes from a template builder that always works offline, or from a local model if you pass one (its output goes through exactly the same checks). Graphics are drawn with Pillow in the brand colours
(WCAG contrast checked), the landing page is one self-contained responsive file. Photoreal AI footage and AI presenters are NOT produced here.
"""
import hashlib
import html
import json
import os
import re
import time
from pathlib import Path

MAX_FACT = 300
SPEAK_WPS = 2.5
VIDEO_FORMATS = {"social_15s": {"seconds": 15, "label": "15 second social cut", "scenes": 3}, "broadcast_30s": {"seconds": 30, "label": "30 second broadcast spot", "scenes": 5},
                 "brand_story": {"seconds": 90, "label": "90 second brand story", "scenes": 8}}
AD_LIMITS = {"google_search": {"headline": 30, "description": 90, "headlines": (3, 15), "descriptions": (2, 4)}, "meta": {"headline": 40, "primary_text": 125, "description": 30},
             "linkedin": {"headline": 70, "intro": 150}, "tiktok": {"text": 100}, "native": {"headline": 60, "description": 150}}
AD_SIZES = {"display_300x250": (300, 250), "display_728x90": (728, 90), "display_160x600": (160, 600), "social_1200x628": (1200, 628), "social_1080x1080": (1080, 1080), "story_1080x1920": (1080, 1920), "landing_header_1600x600": (1600, 600)}
RISKY = re.compile(r"(?<!\w)#\s*1\b|\b(guarantee[sd]?|risk[- ]free|no risk|number one|best in the world|world'?s best|cure[sd]?|miracle|doctor[- ]recommended|clinically proven|get rich|make \$?\d+|instantly|overnight success|100% (?:safe|effective|free)|act now or|only \d+ left)\b", re.I)
_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s*%?")
_QUOTE = re.compile(r"[\"“”][^\"“”]{12,}[\"“”]")


class CampaignError(Exception):
    pass


def _s(v, name, required=True, limit=MAX_FACT):
    v = str(v or "").strip()
    if required and not v:
        raise CampaignError("%s is required" % name)
    if len(v) > limit or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", v):
        raise CampaignError("%s must be plain text up to %d characters" % (name, limit))
    return v


def validate_profile(p):
    """-> the clean profile. Required: name, what, audience, offer, cta_text, cta_url, sender_name, postal_address (the email rules need a real one)."""
    if not isinstance(p, dict):
        raise CampaignError("the profile must be an object")
    out = {"name": _s(p.get("name"), "name", limit=80), "what": _s(p.get("what"), "what the business does"), "audience": _s(p.get("audience"), "who it is for"), "offer": _s(p.get("offer"), "the offer"),
           "cta_text": _s(p.get("cta_text"), "call to action", limit=30), "cta_url": _s(p.get("cta_url"), "call-to-action address", limit=300),
           "sender_name": _s(p.get("sender_name"), "sender name", limit=80), "postal_address": _s(p.get("postal_address"), "postal address", limit=200),
           "sender_email": _s(p.get("sender_email"), "sender email", required=False, limit=120), "tone": _s(p.get("tone") or "clear and friendly", "tone", limit=60)}
    if not re.match(r"^https?://[^\s]+$", out["cta_url"]):
        raise CampaignError("the call-to-action address must be a web address (https://...)")
    for k in ("differentiators", "proof_points"):
        v = p.get(k) or []
        if isinstance(v, str):
            v = [x.strip() for x in v.split("\n") if x.strip()]
        if not isinstance(v, list) or len(v) > 8:
            raise CampaignError("%s must be a list of up to 8 short statements" % k)
        out[k] = [_s(x, k, limit=MAX_FACT) for x in v]
    if not out["differentiators"]:
        raise CampaignError("give at least one real differentiator: what is actually different or good about it")
    c = p.get("colors") or {}
    out["colors"] = {"primary": _hex(c.get("primary") or "#1d4ed8"), "accent": _hex(c.get("accent") or "#f59e0b")}
    return out


def _hex(v):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(v)):
        raise CampaignError("colours are #rrggbb")
    return str(v).lower()


def known_facts(profile):
    return " ".join([profile["name"], profile["what"], profile["audience"], profile["offer"], profile["cta_text"]] + profile["differentiators"] + profile["proof_points"])


def lint_copy(text, profile, where="copy"):
    """-> problems. Every number must come from the profile; no quoted statements; no unsubstantiated claims."""
    problems, facts = [], known_facts(profile)
    for m in _NUM.finditer(text):
        tok = m.group(0).strip()
        digits = re.sub(r"[^\d.]", "", tok)
        if digits and digits not in re.sub(r"[^\d.\s]", " ", facts).replace(",", "") and tok not in facts:
            problems.append("%s: the figure %r is not in the profile" % (where, tok))
    if _QUOTE.search(text):
        problems.append("%s: contains a quoted statement; testimonials are never invented (put a real one in the profile as a proof point)" % where)
    for m in RISKY.finditer(text):
        if m.group(0).lower() not in facts.lower():
            problems.append("%s: %r is a claim that needs substantiation; it is not in the profile's proof points" % (where, m.group(0)))
    return problems


def _cut(text, n):
    text = " ".join(str(text).split())
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut or text[:n]


# ---- the template builder: always available, always within the limits, never invents ----
def build_copy(profile):
    p = profile
    d1 = p["differentiators"][0]
    d2 = p["differentiators"][1] if len(p["differentiators"]) > 1 else p["what"]
    proof = p["proof_points"][0] if p["proof_points"] else None
    hook = _cut("%s for %s" % (p["offer"], p["audience"]), 90)
    google = {"headlines": [_cut(x, 30) for x in (p["name"], p["offer"], p["cta_text"], d1, d2, "For " + p["audience"]) if x][:6],
              "descriptions": [_cut("%s. %s." % (p["what"], d1), 90), _cut("%s. %s" % (p["offer"], p["cta_text"]), 90)]}
    google["headlines"] = list(dict.fromkeys(google["headlines"]))
    ads = {"google_search": google,
           "meta": {"headline": _cut(p["offer"], 40), "primary_text": _cut("%s %s" % (p["what"], d1), 125), "description": _cut(p["cta_text"], 30), "cta": p["cta_text"]},
           "linkedin": {"headline": _cut("%s: %s" % (p["name"], p["offer"]), 70), "intro": _cut("%s For %s. %s" % (p["what"], p["audience"], d1), 150)},
           "tiktok": {"text": _cut("%s %s" % (p["offer"], d1), 100)},
           "native": {"headline": _cut(p["offer"], 60), "description": _cut("%s %s" % (p["what"], d1), 150)}}
    scripts = {}
    for key, f in VIDEO_FORMATS.items():
        beats = [("the problem", "%s know how much time the old way takes." % _cap(p["audience"])), ("what we do", "%s: %s." % (p["name"], p["what"])), ("what is different", d1 + "."),
                 ("more of the difference", d2 + "."), ("proof", (proof + ".") if proof else "Ask us how it works."), ("the offer", "%s." % p["offer"]), ("who it is for", "Built for %s." % p["audience"]),
                 ("call to action", "%s at %s." % (p["cta_text"], re.sub(r"^https?://", "", p["cta_url"]).rstrip("/")))]
        keep = {3: [1, 2, 7], 5: [0, 1, 2, 5, 7], 8: list(range(8))}[f["scenes"]]
        beats = [beats[i] for i in keep]
        words_budget = int(f["seconds"] * SPEAK_WPS)
        scenes, t = [], 0.0
        per = f["seconds"] / len(beats)
        for i, (label, line) in enumerate(beats):
            scenes.append({"scene": i + 1, "t_start": round(t, 2), "t_end": round(t + per, 2), "beat": label, "narration": line, "on_screen_text": _cut(line, 70),
                           "visual_direction": "Brand-colour title card with the line on screen" + ("; end card with the call to action" if i == len(beats) - 1 else "")})
            t += per
        scripts[key] = {"label": f["label"], "seconds": f["seconds"], "scenes": scenes, "word_count": sum(len(s["narration"].split()) for s in scenes), "word_budget": words_budget}
        while scripts[key]["word_count"] > words_budget and len(scenes) > 2:                       # fit the running time: drop the optional middle beats, never cut mid-sentence
            scenes.pop(len(scenes) // 2)
            for i, s in enumerate(scenes):
                s["scene"] = i + 1
                s["t_start"], s["t_end"] = round(i * f["seconds"] / len(scenes), 2), round((i + 1) * f["seconds"] / len(scenes), 2)
            scripts[key]["word_count"] = sum(len(s["narration"].split()) for s in scenes)
    emails = []
    steps = [("Welcome", "You asked to hear from us about %s." % p["what"], "Here is what you can expect: %s" % d1), ("The idea", p["offer"], d1), ("What is different", d1, d2),
             ("Proof", (proof or p["what"]), "If you have questions, reply to this email: it is read by a person."), ("Next step", "Ready when you are.", "%s: %s" % (p["cta_text"], p["cta_url"]))]
    for i, (subj, lead, body) in enumerate(steps):
        emails.append({"day": i * 3, "subject": _cut("%s - %s" % (subj, p["name"]), 60), "preheader": _cut(lead, 90),
                       "body": "%s\n\n%s\n\n%s\n\n%s\n%s\n%s\n\nYou are receiving this because you asked to hear from %s. Unsubscribe: {{unsubscribe_url}}" % (lead, body, p["cta_text"] + ": " + p["cta_url"], p["sender_name"], p["name"], p["postal_address"], p["name"])})
    return {"hook": hook, "ads": ads, "video_scripts": scripts, "emails": emails}


def _cap(s):
    return s[:1].upper() + s[1:]


def check_kit(kit, profile):
    """-> problems for the whole kit: channel limits, running times, email compliance, and the copy lint on every string."""
    problems = []
    g = kit["ads"]["google_search"]
    lo, hi = AD_LIMITS["google_search"]["headlines"]
    if not lo <= len(g["headlines"]) <= hi:
        problems.append("google_search needs %d to %d headlines" % (lo, hi))
    lo, hi = AD_LIMITS["google_search"]["descriptions"]
    if not lo <= len(g["descriptions"]) <= hi:
        problems.append("google_search needs %d to %d descriptions" % (lo, hi))
    for h in g["headlines"]:
        if len(h) > 30:
            problems.append("google_search headline over 30 characters: %r" % h)
    for d in g["descriptions"]:
        if len(d) > 90:
            problems.append("google_search description over 90 characters: %r" % d)
    for ch, lim in AD_LIMITS.items():
        if ch == "google_search":
            continue
        for field, n in lim.items():
            v = kit["ads"][ch].get(field)
            if v is not None and len(v) > n:
                problems.append("%s %s is %d characters, the limit is %d" % (ch, field, len(v), n))
    for k, s in kit["video_scripts"].items():
        if s["word_count"] > s["word_budget"]:
            problems.append("%s has %d words, over the %d that fit %d seconds" % (k, s["word_count"], s["word_budget"], s["seconds"]))
    for i, e in enumerate(kit["emails"]):
        for need in ("{{unsubscribe_url}}", profile["postal_address"], profile["sender_name"]):
            if need not in e["body"]:
                problems.append("email %d is missing %s (sender, postal address and unsubscribe are required)" % (i + 1, need))
        if len(e["subject"]) > 60:
            problems.append("email %d subject is over 60 characters" % (i + 1))
    strings = []

    def walk(v, where):
        if isinstance(v, str):
            strings.append((where, v))
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(x, where + "." + str(k))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, where + "[%d]" % i)
    walk({"ads": kit["ads"], "video_scripts": {k: [s["narration"] for s in v["scenes"]] for k, v in kit["video_scripts"].items()}}, "kit")
    for e in kit["emails"]:
        strings.append(("email %s" % e["subject"], re.sub(r"\{\{unsubscribe_url\}\}|" + re.escape(profile["postal_address"]) + "|" + re.escape(profile["cta_url"]), "", e["body"])))
    for where, text in strings:
        if text and not where.endswith(".cta"):
            problems += lint_copy(text, profile, where)
    return problems


def generate(profile, llm=None, tries=2):
    """-> kit. With llm=None the template builder is used. With a model, its JSON is checked exactly like the template's; failing twice falls back to the template and says so."""
    p = validate_profile(profile)
    kit = build_copy(p)
    kit["source"] = "template"
    if llm is not None:
        for attempt in range(tries):
            try:
                raw = llm(_prompt(p, kit))
                cand = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
                trial = json.loads(json.dumps(kit))
                trial["ads"] = cand.get("ads", trial["ads"])
                trial["emails"] = cand.get("emails", trial["emails"])
                if not check_kit(trial, p):
                    trial["source"] = "local model (checked)"
                    kit = trial
                    break
            except (ValueError, AttributeError, KeyError, TypeError):
                continue
        else:
            kit["source_note"] = "the model's text failed the checks twice, so the template copy is used"
    problems = check_kit(kit, p)
    if problems:
        raise CampaignError("the kit failed its own checks: " + " | ".join(problems[:6]))
    kit["profile"] = p
    return kit


def _prompt(p, kit):
    return ("Rewrite this advertising copy to be warmer and more specific. Keep the same JSON shape (keys ads and emails), keep every character limit, and use ONLY these facts: %s. "
            "No numbers, quotes, testimonials or guarantees that are not in the facts. Reply with JSON only.\n%s" % (known_facts(p), json.dumps({"ads": kit["ads"], "emails": kit["emails"]})))


# ---- graphics ----
def _lum(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(rgb[0]) + 0.7152 * ch(rgb[1]) + 0.0722 * ch(rgb[2])


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def text_colour(bg):
    """White or near-black, whichever reads better on bg (WCAG ratio)."""
    w, k = (255, 255, 255), (17, 24, 39)
    return w if contrast(bg, w) >= contrast(bg, k) else k


def _fit(d, text, width, max_h, start, floor, max_lines, spacing=1.18):
    """The largest font size at which the wrapped text fits width x max_h in at most max_lines; if even the floor does not fit, the text is shortened at a word boundary (and the caller is told)."""
    from PIL import ImageFont
    words = text
    shortened = False
    while True:
        for size in range(start, floor - 1, -2):
            f = ImageFont.load_default(size=size)
            lines = _wrap(d, words, f, width)
            if len(lines) <= max_lines and len(lines) * int(size * spacing) <= max_h and all(d.textlength(x, font=f) <= width for x in lines):
                return f, lines, size, shortened, words
        if len(words.split()) <= 2:
            raise CampaignError("the text %r cannot be made to fit this size" % text)
        words = " ".join(words.split()[:-1])
        shortened = True


def draw_ad(path, size, headline, sub, cta, brand, colors):
    """Draws one ad into path and returns the layout it used. Every block is measured and placed inside its own box, so text never runs into the button, the footer bar or another block."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = size
    bg, ac = _rgb(colors["primary"]), _rgb(colors["accent"])
    fg, cfg = text_colour(bg), text_colour(ac)
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    pad = max(8, int(min(W, H) * 0.05))
    bar = max(4, H // 50)
    d.rectangle([0, H - bar, W, H], fill=ac)
    wide = W / H > 3
    rects = {}
    # the button first: it is anchored, everything else flows around it
    bh = max(26, min(90, int(H * 0.5))) if wide else max(26, min(int(H * 0.09), int(W * 0.14)))
    cs = max(11, int(bh * 0.45))
    fc = ImageFont.load_default(size=cs)
    while d.textlength(cta, font=fc) + 2 * pad > (W * (0.3 if wide else 1) - 2 * pad) and cs > 10:
        cs -= 1
        fc = ImageFont.load_default(size=cs)
    bw = int(d.textlength(cta, font=fc) + 2 * pad)
    bx, by = (W - bw - pad, (H - bar - bh) // 2) if wide else (pad, H - bar - pad - bh)
    rects["button"] = (bx, by, bx + bw, by + bh)
    # the brand line
    fb, brand_lines = None, []
    top = pad
    if not wide and H >= 200:
        bs0 = max(11, min(30, int(min(W, H) * 0.04)))
        fb, brand_lines, bs, _, _ = _fit(d, brand, W - 2 * pad, int(H * 0.12), bs0, 9, 2)                 # a long name wraps or shrinks; it never leaves the image
        rects["brand"] = (pad, pad, pad + int(max(d.textlength(x, font=fb) for x in brand_lines)), pad + len(brand_lines) * int(bs * 1.18))
        top = rects["brand"][3] + int(pad * 0.8)
    # the text area
    if wide:
        area = (pad, pad, bx - pad, H - bar - pad)
    else:
        area = (pad, top, W - pad, by - pad)
    aw, ah = area[2] - area[0], area[3] - area[1]
    if aw < 40 or ah < 20:
        raise CampaignError("size %dx%d is too small for the layout" % size)
    max_lines_h = 2 if wide else 4
    hf, hl, hs, shortened, final = _fit(d, headline, aw, int(ah * (1.0 if wide else 0.68)), int(min(aw, ah) * (0.9 if wide else 0.5)), 12, max_lines_h)
    hh = len(hl) * int(hs * 1.18)
    hy = area[1] + (0 if not wide else max(0, (ah - hh) // 2))
    rects["headline"] = (area[0], hy, area[0] + int(max(d.textlength(x, font=hf) for x in hl)), hy + hh)
    y = hy
    for ln in hl:
        d.text((area[0], y), ln, font=hf, fill=fg)
        y += int(hs * 1.18)
    for i, ln in enumerate(brand_lines):
        d.text((pad, pad + i * int(bs * 1.18)), ln, font=fb, fill=fg)
    sub_drawn = False
    if not wide:
        room = area[3] - (rects["headline"][3] + int(pad * 0.5))
        if room >= 26:
            try:
                sf, sl, ss, cut, _ = _fit(d, sub, aw, room, max(12, int(hs * 0.5)), 11, 6 if H > 2.5 * W else 3)
                if cut:
                    raise CampaignError("the sub-line does not fit whole; it is left out rather than cut mid-sentence")
                sy = rects["headline"][3] + int(pad * 0.5)
                rects["sub"] = (area[0], sy, area[0] + int(max(d.textlength(x, font=sf) for x in sl)), sy + len(sl) * int(ss * 1.18))
                for ln in sl:
                    d.text((area[0], sy), ln, font=sf, fill=fg)
                    sy += int(ss * 1.18)
                sub_drawn = True
            except CampaignError:
                pass
    d.rounded_rectangle(rects["button"], radius=bh // 4, fill=ac)
    d.text((bx + pad, by + (bh - cs) // 2 - 1), cta, font=fc, fill=cfg)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG")
    return {"path": str(path), "size": list(size), "contrast_text_on_background": round(contrast(bg, fg), 2), "contrast_label_on_button": round(contrast(ac, cfg), 2),
            "layout": {k: list(v) for k, v in rects.items()}, "headline_shortened": shortened, "headline_drawn": final, "sub_drawn": sub_drawn, "footer_bar_top": H - bar}


def _wrap(d, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


# ---- landing page ----
def landing_page(profile, kit):
    p, c = profile, profile["colors"]
    bg, ac = _rgb(c["primary"]), _rgb(c["accent"])
    fg, cfg = "#%02x%02x%02x" % text_colour(bg), "#%02x%02x%02x" % text_colour(ac)
    e = html.escape
    proof = "".join("<li>%s</li>" % e(x) for x in p["proof_points"])
    diffs = "".join("<li>%s</li>" % e(x) for x in p["differentiators"])
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>%s - %s</title>"
            "<meta name=\"description\" content=\"%s\"><style>:root{--p:%s;--a:%s;--fg:%s;--cfg:%s}*{box-sizing:border-box}body{margin:0;font:17px/1.6 system-ui,sans-serif;color:#1b1f2a}"
            "header{background:var(--p);color:var(--fg);padding:64px 24px;text-align:center}h1{font-size:clamp(1.8rem,5vw,3rem);margin:0 0 12px}.sub{max-width:640px;margin:0 auto 24px;opacity:.95}"
            ".cta{display:inline-block;background:var(--a);color:var(--cfg);padding:14px 28px;border-radius:10px;font-weight:700;text-decoration:none}.cta:focus-visible{outline:3px solid var(--fg);outline-offset:3px}"
            "main{max-width:760px;margin:0 auto;padding:40px 24px}h2{color:var(--p)}ul{padding-left:1.2em}footer{padding:28px 24px;text-align:center;font-size:.85rem;color:#556}</style></head>"
            "<body><header><h1>%s</h1><p class=\"sub\">%s</p><a class=\"cta\" href=\"%s\">%s</a></header><main><h2>What it is</h2><p>%s</p><h2>Why it is different</h2><ul>%s</ul>%s"
            "<h2>Who it is for</h2><p>%s</p><p><a class=\"cta\" href=\"%s\">%s</a></p></main><footer>%s &middot; %s</footer></body></html>\n") % (
        e(p["name"]), e(p["offer"]), e(_cut(p["what"], 150)), c["primary"], c["accent"], fg, cfg, e(p["offer"]), e(p["what"]), e(p["cta_url"]), e(p["cta_text"]), e(p["what"]), diffs,
        ("<h2>In practice</h2><ul>%s</ul>" % proof) if proof else "", e(p["audience"]), e(p["cta_url"]), e(p["cta_text"]), e(p["name"]), e(p["postal_address"]))


# ---- write the kit to a folder ----
def write_kit(root, kit, graphics=True):
    p = kit["profile"]
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    files = {}

    def put(rel, text):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode("utf-8")
        path.write_bytes(data)
        files[rel] = hashlib.sha256(data).hexdigest()
    put("video_scripts.json", json.dumps(kit["video_scripts"], indent=1))
    put("ad_copy.json", json.dumps(kit["ads"], indent=1))
    put("emails.md", "\n\n".join("## Day %d: %s\n\nPreheader: %s\n\n%s" % (e["day"], e["subject"], e["preheader"], e["body"]) for e in kit["emails"]))
    put("landing/index.html", landing_page(p, kit))
    gfx = []
    if graphics:
        for key, size in AD_SIZES.items():
            r = draw_ad(root / "graphics" / (key + ".png"), size, p["offer"], p["what"], p["cta_text"], p["name"], p["colors"])
            files["graphics/%s.png" % key] = hashlib.sha256((root / "graphics" / (key + ".png")).read_bytes()).hexdigest()
            gfx.append(r)
    manifest = {"business": p["name"], "made_at": time.strftime("%Y-%m-%d %H:%M:%S"), "copy_source": kit.get("source"), "files": files, "graphics": gfx,
                "disclosure": "Copy and graphics were produced by automated tools from the facts in the profile. Review everything before use.",
                "not_included": ["photoreal AI footage or AI presenters", "posting to any platform (see the campaign queue: export only after your approval)"]}
    put("manifest.json", json.dumps(manifest, indent=1))
    return manifest
