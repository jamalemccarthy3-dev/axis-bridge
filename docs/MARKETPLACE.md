# Marketplace

The Marketplace is a tab inside Platform. It has two sides and two tiers.

| | **Commercial** (paid) | **Free & Open** |
|---|---|---|
| Who can submit | a micro-company (a company workspace) | anyone |
| Price | set by the seller, with optional administrator discounts | free, always |
| Licence | seller's choice from a list | an open-source licence, with the full text in a `LICENSE` file |
| Vetting | the full gauntlet below | the same automatic safety checks, a contribution declaration and an administrator's approval |
| Agreement | partnership agreement with a **5% platform revenue share** | a short contribution declaration; no payments, no revenue share |
| Code visible to buyers | no (they buy it) | yes: read every file, check the SHA-256, download the exact vetted package |

## Two views

* **Buyer (default, and what any visitor sees):** a storefront with the tier switch (All / Commercial / Free & Open), search, categories, sorting and discounts. Each thumbnail shows its **price or FREE / Open source badge, star rating, review count and comment count**. Open a card for the full product page. If there are no products the page says so; nothing is invented.
* **Seller portal:** share free code (no company needed), or, with a company workspace, submit a paid product and follow it through the gauntlet stage by stage. Admin tools appear only for the administrator.

## The paid gauntlet (strict order, nothing can be skipped)

1. **Intake and manifest** (automatic): a safe `.zip` with a `marketplace.json` manifest. The AXIS intake standards apply: nothing is executed, paths stay inside the bundle, every file parses, explicit names.
2. **File hygiene and secrets** (automatic): no executables or nested archives, no oversized files, no credentials or private paths. Findings never print the secret.
3. **Static security** (automatic): dangerous constructs are blocked (`eval`, `exec`, shell commands, `pickle`, `ctypes`...) and what the code can *do* (network, files, subprocess, environment) must match the permissions the manifest declares.
4. **Honest listing** (automatic): README, a recognised licence, no income or safety guarantees.
5. **Functional and stress tests** (a person, in isolation): see "Why NEXXUS does not run the code" below.
6. **Reviewer sign-off** (administrator): a seven-point checklist; every item must be ticked to approve.
7. **Partnership agreement** (seller): typed full name and three acknowledgements; the exact text is recorded by hash.
8. **Greenlight** (administrator): publishes it and sets the checkout link and any discount.

A failed stage stops everything after it. An update to a published product runs the whole gauntlet again; buyers keep the previously vetted version meanwhile.

## Why NEXXUS does not run the code

Running a stranger's code on your computer is how machines get compromised, and this machine has no real sandbox (no network, no filesystem access, resource limits). So stages 1-4 only **read** the bundle, and "stress testing" is done by a person in a disposable environment who attests the result with a written report. The storefront says which checks were automatic and which a person did. Static analysis cannot prove safety, and the product pages say so.

## The Free & Open tier

Same automatic safety checks, an open-source licence rule, then the seller's **contribution declaration** (the code is theirs to share, it contains no malware, they accept the Code of Conduct) and an **administrator's approval**. The administrator can turn on unattended publishing with `NEXXUS_FREE_AUTOPUBLISH=1`; it is off by default because code from strangers should meet a person first.

**Transparent code:** a published free package can be inspected file by file, its SHA-256 is shown, and the download is the exact vetted bundle (it is refused if the stored file no longer matches its recorded checksum). A listing can link its GitHub/GitLab/Codeberg repository for collaboration (issues, pull requests). Paid code is never exposed.

## Ratings and comments

* **Ratings are real or absent.** A review needs a **verified interaction**: a recorded download for a free package, or a purchase the administrator has attested for a paid one (NEXXUS cannot see payments itself). One review per person (a second replaces the first), 1-5 stars, never your own product. With no reviews there is no rating, and the search metadata carries no `aggregateRating`.
* **Comments** are open to anyone who can see the product, threaded three levels deep, limited in length and rate, and removable by their author, the product's creator or the administrator (a "[removed]" marker keeps the thread readable). Keep it PG-13.
* In a single-user install every product is yours, so you cannot review any of them; ratings and the review form come alive when other people can reach the same Marketplace.

## SEO and the static storefront

When a bundle is uploaded NEXXUS generates, deterministically from the listing, README and bundle: a meta title (60 characters or fewer), meta description (155 or fewer), up to 12 real keywords, a code summary ("Written in Python, 4 files. Asks for no special permissions."), a clean page address (`/products/<name>-<id>/`) and schema.org structured data. A price is offered only for something that can really be obtained.

A program running on one computer cannot be indexed by search engines, so the administrator can **export a static site** (Admin queue, "Export the storefront"): `index.html`, one page per product, `sitemap.xml` and `robots.txt`, written to `nexxus_data/marketplace/site/`. Pages have no scripts (apart from the structured-data block), no trackers and a strict content policy; everything is escaped, so a product cannot inject markup. **You publish the folder yourself** (for example to GitHub Pages); nothing is uploaded for you.

## What is not here: payments

NEXXUS never handles payment details. The **Buy** button opens a hosted checkout link that the administrator adds (for example a payment provider's checkout), after an "you are leaving NEXXUS" confirmation. The 5% revenue share is **recorded in the agreement but cannot be enforced by software**: payouts, tax and refunds need a payment provider that can split and settle funds, and a lawyer-reviewed agreement. The agreement text is a **draft template**. Do not take real money until both are in place, and check the rules where you and your buyers live.

## Reports, takedowns and the audit trail

Anyone can report a listing. The administrator sees reports, can take a product down (it leaves the storefront at once; buyers keep what they bought) or reject a submission, and every state change is written to an append-only audit trail.

## Routes

Catalog, product page, social and downloads: `GET /api/platform/marketplace/catalog?tier=&category=&q=&sort=`, `GET .../product/<id>/page`, `POST .../product/<id>/review|comment`, `DELETE .../comment/<id>`, `GET .../free/<id>/files|file?name=|download`, `POST .../report`. Seller: `GET .../mine`, `POST .../submission`, `POST .../submission/<id>/upload|agreement|declaration|withdraw`. Administrator (needs the admin token): `GET .../admin/queue`, `POST .../submission/<id>/attest|review|greenlight|approve|checkout|reject|unpublish`, `POST .../product/<id>/verify-purchase`, `POST .../export`.
