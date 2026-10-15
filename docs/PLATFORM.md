# Platform mode

Platform is a locked operating mode with a two-sided spatial layout. It is chosen from the **Modes** menu in the bottom bar (**Mode: Platform**, shown with a lock until unlocked). Until it is unlocked and selected, NEXXUS stays in the standard desktop view: telemetry, the workstation and the shop.

## Beta mode (current state: open to everyone)

Platform is in **open Beta**: no purchase and no license key are needed, for anyone, and a **BETA** badge shows in the Platform header, the Modes menu and the profile hub. This is controlled by `platform_beta.json` (`"beta_open": true`). To bring the paid gate back, set it to `false` (or set the environment variable `NEXXUS_PLATFORM_BETA=0`); anyone in Platform then drops back to the desktop view unless they hold a valid key. The license system described under "The access gate" below stays in place and tested, just switched off.

**What the Beta really contains today:** the spatial layout, your profile, the floor with photo posts, comments and 1-5 star ratings, and live sync between every open viewport. **Not built yet:** other people (friends, direct messages, group chats, audio and video calls), pods, and the guided building paths. Those need a networked server and are not part of this build; the Beta does not pretend otherwise.

## What you get when it is on

* **Left wall: your profile hub**, laid out like a professional profile: name, headline, location, about, links, and the links you have shared. Edit it with *Edit profile*.
* **Right wall: your network and friends feed**, showing active posts and shared links from other people.
* **Centre floor:** a fast chat-style feed, with the **command bar fixed at the base** of the floor. Type to post or chat; paste a link and it is shared as a link.
* **Exit Platform** (top right, or the Esc key) collapses the view and returns to the desktop dashboard. On a phone the three areas become Profile / Floor / Network tabs.

## Photos, comments, ratings and live sync

* **Photos:** attach with the camera button, paste an image into the command bar, or drop one on the floor. JPEG, PNG, GIF or WebP up to 6 MB. Each photo is re-encoded on this computer: it is rotated by its orientation tag, shrunk to 1600 px, and **all metadata (location, camera) is removed**. SVG and anything that is not really a photo is refused. Photos are served with `nosniff` and a sandboxing policy.
* **Comments and ratings:** every post can be rated 1 to 5 stars (click the same star again to clear it) and can hold up to 100 comments of 300 characters.
* **Live sync:** every change (posts, photos, comments, ratings, deletes, profile edits) is pushed at once to every open viewport over a Server-Sent Events stream, with no refresh. The header shows `Live - N viewports`. A viewport that drops reconnects on its own and reloads so nothing missed is lost. "Viewport" means any place that opens this same NEXXUS: another tab or window, or your phone through the dashboard's Tailscale access (changes from another device need the admin token, as everywhere else in the dashboard).
* Limits: 30 posts a minute, 500 posts kept, 20 viewports at once.

## Content standard: PG-13

Photos and messages are welcome and are held to a **PG-13** standard (details in [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)). The command bar carries a short reminder. **Nothing detects explicit images automatically in this build**; photos are validated and stripped of metadata, not judged. While Platform is local to your computer that is yours to keep; before other people can see each other's posts, add reporting, removal and (ideally) automated screening.

## What is real today, and what is not

Everything on the walls and the floor is **real and local**: your own profile, posts and links are saved only on this computer in `nexxus_data/platform/`. **There is no network yet**, so there are no other people: the right wall shows "0 connections" and an empty state, never invented friends or posts. Connecting people (accounts, a feed that other people can post into, moderation) is a server-side feature that does not exist in this build and would need its own privacy and safety design.

## The access gate

| Plan | Price |
|---|---|
| Monthly subscription | **$9.99 / month** |
| Lifetime Access Pass | **$199 one-time** |

NEXXUS never handles payments or card details. The flow is:

1. The owner creates two checkout links with a payment provider (for example two Stripe Payment Links) and sets them before starting the server: `NEXXUS_CHECKOUT_MONTHLY` and `NEXXUS_CHECKOUT_LIFETIME` (https only). A plan with no link shows "Checkout not set up yet".
2. The buyer pays on that page and the owner sends them a **license key**.
3. The buyer pastes the key into the unlock dialog (it opens when Platform is picked while locked). The key is checked **on the buyer's computer** against `license_public_key.pem`, then saved locally. A monthly key stops working on its expiry date and the mode falls back to the desktop view; renewing means a new key. A lifetime key never expires.

### Issuing keys (owner only)

```bash
python tools/issue_license.py keygen             # once: creates .local_config/license_private_key.pem (BACK IT UP) and license_public_key.pem
python tools/issue_license.py issue lifetime     # prints a Lifetime Access Pass key
python tools/issue_license.py issue monthly --days 31
python tools/issue_license.py check <key>
```

The private key never leaves your machine and is gitignored. If it is lost, no new keys can be issued: generate a new pair and ship the new public key in a release (old keys then stop verifying).

### Honest limits of the gate

* It is a **local** gate in source-available software. Someone who edits the code can remove it, and an offline check cannot revoke a key you have already issued (a monthly key just expires). Real enforcement belongs on the server side of any networked Platform feature, which is where the gate should live once one exists.
* Selling access is separate from the project's licence for the public source (PolyForm Noncommercial). Check that your terms for paying customers say what they get.
* Issuing keys is manual today. A webhook that issues a key after payment is a natural next step but needs a small server.

## Routes (local machine only)

`GET /api/platform/entitlement`, `POST|DELETE /api/platform/license`, `GET /api/platform/state`, `GET /api/platform/stream` (live events), `POST /api/platform/profile`, `POST /api/platform/post` (JSON, or multipart with an `image`), `DELETE /api/platform/post/<id>`, `POST /api/platform/post/<id>/rating`, `POST /api/platform/post/<id>/comment`, `DELETE /api/platform/post/<id>/comment/<cid>`, `GET /api/platform/media/<id>`. Outside Beta, everything except the entitlement and license routes returns 402 with the plans until a valid key is present. All of them refuse requests from another web page and another hostname (DNS rebinding); other devices are served only if the dashboard's own network rules admit them, and their changes need the admin token.
