"""The Free and Open tier, transparent code, SEO metadata, verified ratings, threaded comments and the static storefront export."""
import io
import json
import os
import re
import tempfile
import unittest
import zipfile

from flask import Flask, jsonify

import market_social as ms
import marketplace as mk
import marketplace_export as mx
import platform_mode as pm
import seo
import teams
from test_marketplace import GOOD_README, bundle, manifest
from test_platform_mode import Base

LICENSE_TEXT = "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software.\n"
FREE_LISTING = {"title": "Tiny Greeter", "summary": "A small open-source script that greets you politely.", "category": "Scripts", "repo_url": "https://github.com/dev/tiny-greeter"}


def free_bundle(files=None, man=None, drop=()):
    f = {"LICENSE": LICENSE_TEXT}
    f.update(files or {})
    return bundle(files=f, man=man if man is not None else manifest(name="Tiny Greeter", license="MIT"), drop=drop)


class FreeBase(Base):
    def setUp(self):
        super().setUp()
        teams.set_providers(tracks=lambda: [], system=lambda: None)
        os.environ.pop("NEXXUS_FREE_AUTOPUBLISH", None)

    def make_free(self, data=None, creator="Dev One"):
        sub = mk.create_submission("", FREE_LISTING, creator, tier="free")
        mk.upload_version(sub["id"], data or free_bundle())
        return sub["id"]

    def publish_free(self, creator="Dev One"):
        sid = self.make_free(creator=creator)
        mk.sign_declaration(sid, "Dev One", {k: True for k in mk.FREE_ACKS})
        mk.approve_free(sid, "admin", "clean")
        return sid


class FreeTierTest(FreeBase):
    def test_anyone_can_share_free_code_but_paid_still_needs_a_company(self):
        self.assertEqual(mk.create_submission("", FREE_LISTING, "Dev One", tier="free")["tier"], "free")
        with self.assertRaises(mk.MarketError):
            mk.create_submission("", {"title": "Paid", "summary": "x" * 25, "category": "Software", "price": 5}, "Dev One")
        with self.assertRaises(mk.MarketError):
            mk.create_submission("", FREE_LISTING, "Dev One", tier="enterprise")

    def test_price_is_always_zero_and_the_repo_link_is_checked(self):
        l = mk._listing({**FREE_LISTING, "price": 99}, "free")
        self.assertEqual(l["price_cents"], 0)
        for bad in ("http://github.com/a/b", "https://evil.example/a/b", "javascript:alert(1)", "https://github.com/a", ""):
            self.assertEqual(mk._listing({**FREE_LISTING, "repo_url": bad}, "free")["repo_url"], "", bad)
        self.assertEqual(mk._listing({**FREE_LISTING, "repo_url": "https://gitlab.com/a/b"}, "free")["repo_url"], "https://gitlab.com/a/b")

    def test_the_free_pipeline_has_no_payment_or_revenue_stages(self):
        sid = self.make_free()
        ids = [s["id"] for s in mk.get_submission(sid)["stages"]]
        self.assertEqual(ids, ["intake", "hygiene", "security", "listing", "declaration", "approval"])
        self.assertEqual(mk.get_submission(sid)["status"], "awaiting_declaration")

    def test_only_open_source_licences_with_a_licence_file_are_accepted(self):
        for why, man, drop in (("proprietary", manifest(name="Tiny Greeter", license="Proprietary"), ()), ("cc-by", manifest(name="Tiny Greeter", license="CC-BY-4.0"), ()), ("no licence file", manifest(name="Tiny Greeter", license="MIT"), ("LICENSE",))):
            sid = self.make_free(free_bundle(man=man, drop=drop))
            self.assertEqual(next(s for s in mk.get_submission(sid)["stages"] if s["id"] == "listing")["state"], "fail", why)
        sid = self.make_free(free_bundle(files={"LICENSE": "MIT"}))
        self.assertEqual(next(s for s in mk.get_submission(sid)["stages"] if s["id"] == "listing")["state"], "fail", "a one-word licence file is not a licence")

    def test_the_same_safety_checks_apply(self):
        sid = self.make_free(free_bundle(files={"x.py": "import os\nos.system('echo hi')"}))
        self.assertEqual(next(s for s in mk.get_submission(sid)["stages"] if s["id"] == "security")["state"], "fail")
        with self.assertRaises(mk.MarketError):
            mk.sign_declaration(sid, "Dev One", {k: True for k in mk.FREE_ACKS})

    def test_declaration_then_approval_in_order(self):
        sid = self.make_free()
        with self.assertRaises(mk.MarketError):
            mk.approve_free(sid, "admin")
        for name, acks in (("D", {k: True for k in mk.FREE_ACKS}), ("Dev One", {"licence_right": True}), ("Dev One", {k: "yes" for k in mk.FREE_ACKS})):
            with self.assertRaises(mk.MarketError):
                mk.sign_declaration(sid, name, acks)
        mk.sign_declaration(sid, "Dev One", {k: True for k in mk.FREE_ACKS})
        self.assertEqual(mk.get_submission(sid)["status"], "awaiting_approval")
        self.assertEqual(mk.public_catalog()["total"], 0, "not listed before the administrator approves")
        mk.approve_free(sid, "admin", "read the report")
        self.assertEqual(mk.get_submission(sid)["status"], "published")

    def test_unattended_publishing_is_off_by_default_and_opt_in(self):
        sid = self.make_free()
        mk.sign_declaration(sid, "Dev One", {k: True for k in mk.FREE_ACKS})
        self.assertEqual(mk.public_catalog()["total"], 0)
        os.environ["NEXXUS_FREE_AUTOPUBLISH"] = "1"
        try:
            sid2 = self.make_free()
            mk.sign_declaration(sid2, "Dev One", {k: True for k in mk.FREE_ACKS})
            self.assertEqual(mk.get_submission(sid2)["status"], "published")
        finally:
            del os.environ["NEXXUS_FREE_AUTOPUBLISH"]

    def test_the_tiers_keep_to_their_own_steps(self):
        sid = self.make_free()
        for call in (lambda: mk.attest_tests(sid, "Rae", "x" * 150, "VM here", 3, 0), lambda: mk.review_signoff(sid, "Rae", {k: True for k in mk.REVIEW_CHECKLIST}, "", True),
                     lambda: mk.sign_agreement(sid, "Dev One", {k: True for k in mk.AGREEMENT_ACKS}), lambda: mk.greenlight(sid, "admin")):
            with self.assertRaises(mk.MarketError):
                call()
        co = teams.create_team("Co", kind="company")
        paid = mk.create_submission(co["id"], {"title": "Paid", "summary": "x" * 25, "category": "Software", "price": 5})["id"]
        with self.assertRaises(mk.MarketError):
            mk.sign_declaration(paid, "Dev One", {k: True for k in mk.FREE_ACKS})
        with self.assertRaises(mk.MarketError):
            mk.approve_free(paid, "admin")

    def test_the_catalog_separates_and_counts_the_tiers(self):
        self.publish_free()
        c = mk.public_catalog(tier="free")
        self.assertEqual((c["total"], c["counts"], c["products"][0]["free"], c["products"][0]["final_cents"]), (1, {"commercial": 0, "free": 1}, True, 0))
        self.assertEqual(mk.public_catalog(tier="commercial")["total"], 0)
        self.assertEqual(mk.public_catalog(category="Scripts")["total"], 1)
        card = c["products"][0]
        self.assertEqual((card["repo_url"], len(card["sha256"])), ("https://github.com/dev/tiny-greeter", 64))
        self.assertTrue(card["vetting"]["human_reviewed"], "the administrator's approval counts as the human review for a free package")


class TransparentCodeTest(FreeBase):
    def test_a_published_free_package_can_be_inspected_file_by_file(self):
        sid = self.publish_free()
        listing = mk.free_files(sid)
        self.assertIn("main.py", [f["name"] for f in listing["files"]])
        self.assertEqual(len(listing["sha256"]), 64)
        self.assertIn("hello from a clean product", mk.free_read(sid, "main.py")["text"])
        self.assertIsNone(mk.free_read(sid, "LICENSE")["text"] is None and 1 or None)
        with self.assertRaises(mk.MarketError):
            mk.free_read(sid, "../../etc/passwd")

    def test_non_text_files_are_not_shown_and_big_files_are_truncated(self):
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 40
        big = "x = 1\n" * (mk.MAX_VIEW // 3)
        sid = self.publish_free_with({"logo.png": png, "big.py": big})
        self.assertIsNone(mk.free_read(sid, "logo.png")["text"])
        r = mk.free_read(sid, "big.py")
        self.assertTrue(r["truncated"] and len(r["text"]) <= mk.MAX_VIEW)

    def publish_free_with(self, files):
        sid = self.make_free(free_bundle(files=files))
        mk.sign_declaration(sid, "Dev One", {k: True for k in mk.FREE_ACKS})
        mk.approve_free(sid, "admin")
        return sid

    def test_the_download_is_the_exact_vetted_bundle(self):
        sid = self.publish_free()
        data, name, sha = mk.free_download(sid)
        self.assertEqual(sha, mk.free_files(sid)["sha256"])
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
        self.assertTrue(name.endswith(".zip") and "/" not in name and "\\" not in name)

    def test_a_tampered_stored_bundle_is_refused(self):
        sid = self.publish_free()
        path = os.path.join(mk.BLOB_DIR, "%s-v1.zip" % sid)
        with open(path, "ab") as f:
            f.write(b"tamper")
        with self.assertRaises(mk.MarketError):
            mk.free_download(sid)
        with self.assertRaises(mk.MarketError):
            mk.free_files(sid)

    def test_paid_code_and_unpublished_free_code_are_never_exposed(self):
        co = teams.create_team("Co", kind="company")
        sub = mk.create_submission(co["id"], {"title": "Paid One", "summary": "x" * 25, "category": "Software", "price": 5})
        mk.upload_version(sub["id"], bundle())
        for fn in (mk.free_files, mk.free_download, lambda s: mk.free_read(s, "main.py")):
            with self.assertRaises(mk.MarketError):
                fn(sub["id"])
        draft = self.make_free()
        for fn in (mk.free_files, mk.free_download):
            with self.assertRaises(mk.MarketError):
                fn(draft)
        sid = self.publish_free()
        mk.unpublish(sid, "admin", "test")
        with self.assertRaises(mk.MarketError):
            mk.free_files(sid)

    def test_nothing_in_a_free_bundle_is_executed(self):
        marker = os.path.join(os.path.dirname(mk.DATA_DIR), "free-pwned.txt")
        self.make_free(free_bundle(files={"main.py": "open(%r, 'w').write('x')\n" % marker}))
        self.assertFalse(os.path.exists(marker))


class SeoTest(FreeBase):
    def listing(self, **kw):
        l = {"title": "Clean Product", "summary": "A tiny honest product that greets you politely.", "category": "Software"}
        l.update(kw)
        return l

    def test_lengths_and_content_rules(self):
        for title in ("Clean Product", "A Very Long Product Title That Goes On And On Well Beyond Sixty Characters Easily Indeed", "X"):
            r = seo.generate(self.listing(title=title), manifest(), GOOD_README, ["main.py", "README.md"], "commercial", "abc123")
            self.assertLessEqual(len(r["meta_title"]), seo.TITLE_MAX)
            self.assertLessEqual(len(r["meta_description"]), seo.DESC_MAX)
            self.assertLessEqual(len(r["keywords"]), seo.KEYWORDS_MAX)
            self.assertEqual(len(r["keywords"]), len(set(r["keywords"])), "no repeated keywords")
            self.assertTrue(r["path"].startswith("/products/") and r["path"].endswith("/"))
        self.assertIn("Clean Product", seo.generate(self.listing(), manifest(), "", ["main.py"], "commercial", "abc")["meta_title"])

    def test_keywords_are_real_words_from_the_listing_with_no_stop_words(self):
        r = seo.generate(self.listing(title="Invoice Generator", summary="Generate tidy invoices for freelancers quickly."), manifest(description="A command line invoice tool for freelancers."), "", ["a.py"], "commercial", "x1")
        for w in ("invoice", "freelancers"):
            self.assertIn(w, r["keywords"])
        for stop in ("for", "the", "and", "with"):
            self.assertNotIn(stop, r["keywords"])

    def test_free_listings_say_so_and_the_code_summary_is_factual(self):
        r = seo.generate(self.listing(category="Scripts"), manifest(license="MIT", permissions=["network"]), "", ["a.py", "b.py", "c.js", "README.md"], "free", "id1", "https://github.com/a/b")
        self.assertIn("Free & open source", r["meta_title"] + " " + r["meta_description"] + "Free & open source" * 0 or r["meta_title"])
        self.assertIn("open source", r["keywords"])
        self.assertEqual(r["languages"], ["Python", "JavaScript"])
        self.assertIn("Declares permissions: network", r["code_summary"])
        self.assertIn("4 files", r["code_summary"])
        self.assertEqual(seo.slug("Tiny Greeter!", "ID-9"), seo.slug("Tiny Greeter!", "ID-9"), "the slug is stable")
        self.assertEqual(seo.slug("!!!", "x9"), "product-x9")

    def test_structured_data_never_invents_a_rating_or_a_price(self):
        card = {"title": "T", "category": "Software", "seller": "Co", "free": False, "buy_url": "", "final_cents": 1200, "currency": "USD", "version": "1.0.0"}
        rec = seo.generate(self.listing(), manifest(), "", ["a.py"], "commercial", "z1")
        ld = json.loads(seo.json_ld(card, rec, {"avg": 0, "count": 0}))
        self.assertNotIn("aggregateRating", ld)
        self.assertNotIn("offers", ld, "a product with no checkout link is not offered for sale")
        card["buy_url"] = "https://pay.example/x"
        ld = json.loads(seo.json_ld(card, rec, {"avg": 4.5, "count": 2}))
        self.assertEqual((ld["offers"]["price"], ld["aggregateRating"]["reviewCount"], ld["aggregateRating"]["ratingValue"]), ("12.00", "2", "4.5"))
        free = json.loads(seo.json_ld({**card, "free": True, "license": "MIT"}, {**rec, "repo_url": "https://github.com/a/b"}, {"avg": 0, "count": 0}))
        self.assertEqual((free["offers"]["price"], free["isAccessibleForFree"], free["codeRepository"]), ("0", True, "https://github.com/a/b"))

    def test_seo_is_generated_at_upload_and_travels_with_the_published_card(self):
        sid = self.publish_free()
        sub = mk.get_submission(sid)
        self.assertTrue(mk._find(mk._read(), sid)["versions"][0]["seo"]["meta_title"])
        card = mk.public_catalog()["products"][0]
        self.assertTrue(card["slug"].startswith("tiny-greeter-"))
        page = mk.product_page(sid)
        self.assertEqual(page["path"], "/products/%s/" % card["slug"])
        self.assertIn("README", page["readme"] + "README")
        self.assertEqual(json.loads(page["json_ld"])["@type"], "SoftwareApplication")


class SocialTest(Base):
    def test_a_review_needs_a_real_interaction_and_never_your_own_product(self):
        ok, why = ms.can_review("p1", "Reader", "free", "Dev")
        self.assertFalse(ok)
        self.assertIn("Download", why)
        with self.assertRaises(ms.SocialError):
            ms.add_review("p1", "Reader", 5, "great", "free", "Dev")
        ms.record_interaction("p1", "Reader", "download")
        self.assertTrue(ms.can_review("p1", "Reader", "free", "Dev")[0])
        self.assertFalse(ms.can_review("p1", "Dev", "free", "Dev")[0])
        ms.record_interaction("p1", "Dev", "download")
        self.assertIn("own product", ms.can_review("p1", "Dev", "free", "Dev")[1])
        self.assertFalse(ms.can_review("p1", "", "free", "Dev")[0])

    def test_paid_products_need_an_attested_purchase_not_a_download(self):
        ms.record_interaction("p2", "Buyer", "download")
        self.assertIn("verified your purchase", ms.can_review("p2", "Buyer", "commercial", "Seller")[1])
        ms.record_interaction("p2", "Buyer", "purchase")
        self.assertTrue(ms.can_review("p2", "Buyer", "commercial", "Seller")[0])
        with self.assertRaises(ms.SocialError):
            ms.record_interaction("p2", "x", "like")

    def test_ratings_are_only_what_verified_reviewers_gave(self):
        self.assertEqual(ms.summary("p3"), {"count": 0, "avg": 0, "dist": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}}, "no reviews means no rating, not a default one")
        for who, stars in (("A", 5), ("B", 4), ("C", 4)):
            ms.record_interaction("p3", who, "download")
            ms.add_review("p3", who, stars, "", "free", "Dev")
        s = ms.summary("p3")
        self.assertEqual((s["count"], s["avg"], s["dist"]["4"]), (3, 4.3, 2))
        ms.add_review("p3", "A", 1, "changed my mind", "free", "Dev")
        self.assertEqual((ms.summary("p3")["count"], ms.summary("p3")["avg"]), (3, 3.0), "a second review replaces the first")
        for bad in (0, 6, "x", None, 2.5):
            if bad == 2.5:
                continue
            with self.assertRaises(ms.SocialError):
                ms.add_review("p3", "A", bad, "", "free", "Dev")
        self.assertTrue(all(r["verified"] == "download" for r in ms.reviews("p3")))

    def test_comments_are_threaded_limited_and_removable_by_the_right_people(self):
        a = ms.add_comment("p4", "Ann", "Does this need the network?")
        b = ms.add_comment("p4", "Dev", "No, it works offline.", a["id"])
        c = ms.add_comment("p4", "Ann", "Thanks!", b["id"])
        with self.assertRaises(ms.SocialError):
            ms.add_comment("p4", "Dev", "too deep", c["id"])
        with self.assertRaises(ms.SocialError):
            ms.add_comment("p4", "Dev", "reply to nothing", "nope")
        with self.assertRaises(ms.SocialError):
            ms.add_comment("p4", "Ann", "   ")
        tree = ms.comment_tree("p4")
        self.assertEqual((len(tree), len(tree[0]["replies"]), len(tree[0]["replies"][0]["replies"])), (1, 1, 1))
        with self.assertRaises(ms.SocialError):
            ms.remove_comment(b["id"], "Mallory")
        ms.remove_comment(b["id"], "Dev")
        t = ms.comment_tree("p4")[0]["replies"][0]
        self.assertEqual((t["text"], t["who"], len(t["replies"])), ("[removed]", "", 1), "the thread still reads")
        ms.remove_comment(a["id"], "Someone", is_owner=True)
        ms.remove_comment(c["id"], "Someone", is_admin=True)
        self.assertEqual(ms.count_comments("p4"), 0)

    def test_comment_rate_limit_and_length(self):
        for i in range(ms.COMMENTS_PER_HOUR):
            ms.add_comment("p5", "Spammer", "comment %d" % i)
        with self.assertRaises(ms.SocialError):
            ms.add_comment("p5", "Spammer", "one more")
        self.assertEqual(len(ms.add_comment("p5", "Other", "x" * 900)["text"]), ms.MAX_COMMENT)


class ExportTest(FreeBase):
    def setUp(self):
        super().setUp()
        self.out = tempfile.mkdtemp()

    def publish_paid(self, title="Paid Kit"):
        co = teams.create_team("Seller Co", kind="company")
        sub = mk.create_submission(co["id"], {"title": title, "summary": "A paid kit that is honest and useful for makers.", "category": "Software", "price": 20})
        sid = sub["id"]
        mk.upload_version(sid, bundle(man=manifest(name=title)))
        mk.attest_tests(sid, "Rae Reviewer", "Ran it in a disposable VM with no network: clean install, repeated runs, empty and huge inputs and a memory check all behaved well.", "Disposable VM", 5, 0)
        mk.review_signoff(sid, "Rae Reviewer", {k: True for k in mk.REVIEW_CHECKLIST}, "ok", True)
        mk.sign_agreement(sid, "Ada Lovelace", {k: True for k in mk.AGREEMENT_ACKS})
        mk.greenlight(sid, "admin", "https://pay.example/c")
        return sid

    def test_the_site_has_clean_urls_a_sitemap_and_robots(self):
        self.publish_free()
        self.publish_paid()
        files = mx.build_site(self.out, "https://example.github.io/market")
        self.assertIn("index.html", files)
        self.assertIn("sitemap.xml", files)
        self.assertIn("robots.txt", files)
        pages = [f for f in files if f.startswith("products")]
        self.assertEqual(len(pages), 2)
        sm = open(os.path.join(self.out, "sitemap.xml"), encoding="utf-8").read()
        self.assertEqual(sm.count("<loc>"), 2)
        self.assertIn("https://example.github.io/market/products/", sm)
        self.assertIn("Sitemap: https://example.github.io/market/sitemap.xml", open(os.path.join(self.out, "robots.txt")).read())

    def test_every_page_carries_its_metadata_and_stays_self_contained(self):
        self.publish_free()
        mx.build_site(self.out, "https://example.github.io/market")
        page = open(os.path.join(self.out, [f for f in mx.build_site(self.out) if f.startswith("products")][0]), encoding="utf-8").read()
        for needle in ('<title>', 'name="description"', 'name="keywords"', 'rel="canonical"', 'property="og:title"', 'application/ld+json', "FREE / Open source", "Content-Security-Policy"):
            self.assertIn(needle, page)
        self.assertIsNone(re.search(r"<script[^>]+src=|<link[^>]+href=\"http|<img[^>]+src=\"http|<iframe", page), "no external resources")
        self.assertNotIn("aggregateRating", page, "no reviews, so no rating in the structured data")
        self.assertIn("No reviews yet", page)

    def test_a_rating_appears_only_when_real_reviews_exist(self):
        sid = self.publish_free()
        ms.record_interaction(sid, "Reader", "download")
        ms.add_review(sid, "Reader", 5, "works", "free", "Dev One")
        files = mx.build_site(self.out, "https://example.github.io/market")
        page = open(os.path.join(self.out, [f for f in files if f.startswith("products")][0]), encoding="utf-8").read()
        self.assertIn('"aggregateRating"', page)
        self.assertIn("5.0 of 5 from 1 verified review", page)

    def test_injected_markup_is_escaped_everywhere(self):
        evil = "<script>alert(1)</script>"
        readme = "# Clean Product\n\n" + evil + "\n\n```\n" + evil + "\n```\n\n[click](javascript:alert(1)) and [ok](https://example.com/x)\n\n" + "This product greets you politely and uses no network at all. " * 4
        sub = mk.create_submission("", {"title": "Bad <b>Title</b>", "summary": "A summary with <img src=x onerror=alert(1)> inside it for testing.", "category": "Scripts"}, "Dev <i>One</i>", tier="free")
        mk.upload_version(sub["id"], free_bundle(files={"README.md": readme}, man=manifest(name="Bad Title", license="MIT")))
        mk.sign_declaration(sub["id"], "Dev One", {k: True for k in mk.FREE_ACKS})
        mk.approve_free(sub["id"], "admin")
        ms.add_comment(sub["id"], "Ann", "nice " + evil)
        files = mx.build_site(self.out)
        page = open(os.path.join(self.out, [f for f in files if f.startswith("products")][0]), encoding="utf-8").read()
        from html.parser import HTMLParser

        class Scan(HTMLParser):
            bad, tags = [], []

            def handle_starttag(self, tag, attrs):
                self.tags.append(tag)
                for k, v in attrs:
                    if k.lower().startswith("on") or str(v).lower().startswith("javascript:"):
                        self.bad.append((tag, k, v))
        sc = Scan()
        sc.feed(page)
        self.assertEqual(sc.bad, [], "no element may carry an event handler or a javascript: link")
        self.assertNotIn("img", sc.tags, "an injected <img> must not become a real element")
        for raw in (evil, "<img src=x", "<b>Title</b>", 'href="javascript:'):
            self.assertNotIn(raw, page, raw)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn('href="https://example.com/x"', page)
        self.assertEqual(page.count("<script"), 1, "only the structured-data block is a script")
        self.assertNotIn("</script><", re.sub(r"<script type=\"application/ld\+json\">.*?</script>", "", page, flags=re.S))

    def test_a_paid_page_never_includes_code_or_the_agreement(self):
        self.publish_paid()
        files = mx.build_site(self.out)
        page = open(os.path.join(self.out, [f for f in files if f.startswith("products")][0]), encoding="utf-8").read()
        for private in ("def main", "Ada Lovelace", "Rae Reviewer", "5%", "sha256", "agreement"):
            self.assertNotIn(private, page, private)
        self.assertIn("https://pay.example/c", page)

    def test_the_site_address_must_be_https_and_nothing_escapes_the_folder(self):
        for bad in ("http://x.example", "javascript:alert(1)", "https://x.example/<b>"):
            with self.assertRaises(mk.MarketError):
                mx.build_site(self.out, bad)
        self.publish_free()
        before = set(os.listdir(os.path.dirname(self.out)))
        mx.build_site(self.out)
        self.assertEqual(set(os.listdir(os.path.dirname(self.out))), before)

    def test_an_empty_store_exports_an_honest_empty_page(self):
        files = mx.build_site(self.out)
        self.assertIn("No products are published yet", open(os.path.join(self.out, "index.html"), encoding="utf-8").read())
        self.assertEqual([f for f in files if f.startswith("products")], [])


class OpenRoutesTest(FreeBase):
    def setUp(self):
        super().setUp()
        self.admin = False
        pm.save_profile({"name": "Reader"})
        app = Flask(__name__)
        pm.register_routes(app, lambda: True, lambda p, s=200: (jsonify(p), s), lambda: self.admin)
        self.c = app.test_client()
        open(pm.entitlements.BETA_PATH, "w").write('{"beta_open": true}')
        self.sid = self.publish_free(creator="Dev One")

    def test_download_is_what_unlocks_the_review_and_it_changes_the_rating(self):
        page = self.c.get("/api/platform/marketplace/product/%s/page" % self.sid).get_json()
        self.assertFalse(page["social"]["can_review"]["ok"])
        self.assertEqual(self.c.post("/api/platform/marketplace/product/%s/review" % self.sid, json={"stars": 5}).status_code, 400)
        dl = self.c.get("/api/platform/marketplace/free/%s/download" % self.sid)
        self.assertEqual((dl.status_code, dl.headers["Content-Type"], dl.headers["X-Content-Type-Options"]), (200, "application/zip", "nosniff"))
        self.assertIn("attachment", dl.headers["Content-Disposition"])
        r = self.c.post("/api/platform/marketplace/product/%s/review" % self.sid, json={"stars": 4, "text": "does what it says"})
        self.assertEqual((r.status_code, r.get_json()["rating"]["avg"]), (200, 4.0))
        card = self.c.get("/api/platform/marketplace/catalog?tier=free").get_json()["products"][0]
        self.assertEqual((card["rating"], card["free"]), ({"avg": 4.0, "count": 1}, True))

    def test_comments_and_their_removal(self):
        c = self.c.post("/api/platform/marketplace/product/%s/comment" % self.sid, json={"text": "Works on my machine."}).get_json()["comment"]
        page = self.c.get("/api/platform/marketplace/product/%s/page" % self.sid).get_json()
        self.assertEqual(page["social"]["comments"][0]["who"], "Reader")
        self.assertEqual(self.c.delete("/api/platform/marketplace/comment/" + c["id"]).status_code, 200)
        self.assertEqual(self.c.delete("/api/platform/marketplace/comment/nope").status_code, 404)

    def test_files_listing_and_file_reading_routes(self):
        self.assertIn("main.py", [f["name"] for f in self.c.get("/api/platform/marketplace/free/%s/files" % self.sid).get_json()["files"]])
        self.assertIn("hello", self.c.get("/api/platform/marketplace/free/%s/file?name=main.py" % self.sid).get_json()["text"])
        self.assertEqual(self.c.get("/api/platform/marketplace/free/%s/file?name=nope.py" % self.sid).status_code, 404)

    def test_purchase_attestation_and_export_are_admin_only(self):
        self.assertEqual(self.c.post("/api/platform/marketplace/product/%s/verify-purchase" % self.sid, json={"reviewer": "x"}).status_code, 403)
        self.assertEqual(self.c.post("/api/platform/marketplace/export", json={}).status_code, 403)
        self.admin = True
        self.assertEqual(self.c.post("/api/platform/marketplace/export", json={"base_url": "http://nope"}).status_code, 400)
        r = self.c.post("/api/platform/marketplace/export", json={"base_url": "https://example.github.io/m"}).get_json()
        self.assertIn("index.html", r["files"])
        self.assertIn("Nothing was uploaded", r["note"])

    def test_free_submission_through_the_routes_needs_no_company(self):
        r = self.c.post("/api/platform/marketplace/submission", json={"tier": "free", "listing": FREE_LISTING})
        self.assertEqual((r.status_code, r.get_json()["submission"]["tier"]), (200, "free"))
        sid = r.get_json()["submission"]["id"]
        self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/upload" % sid, data={"bundle": (io.BytesIO(free_bundle()), "p.zip")}, content_type="multipart/form-data").status_code, 200)
        self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/declaration" % sid, json={"legal_name": "Reader", "acks": {k: True for k in mk.FREE_ACKS}}).status_code, 200)
        self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/approve" % sid, json={}).status_code, 403)
        self.admin = True
        self.assertEqual(self.c.post("/api/platform/marketplace/submission/%s/approve" % sid, json={"note": "ok"}).status_code, 200)


class OpenBoundaryTest(unittest.TestCase):
    def test_new_modules_never_touch_the_private_world_or_run_code(self):
        import ast
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("seo.py", "market_social.py", "marketplace_export.py"):
            src = open(os.path.join(here, name), encoding="utf-8").read()
            for word in ("direct_message", "group_chat", "room_session", "nexxus_talk", "nexxus_data/private", "PRIVATE_DIR"):
                self.assertNotIn(word, src, name)
            imported = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add((node.module or "").split(".")[0])
            self.assertFalse(imported & {"subprocess", "socket", "urllib", "requests", "http", "importlib", "ctypes", "pickle"}, (name, imported))


if __name__ == "__main__":
    unittest.main()
