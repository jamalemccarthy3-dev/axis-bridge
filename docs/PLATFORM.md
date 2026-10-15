# Platform mode

Platform is a locked operating mode with a two-sided spatial layout. It is chosen from the **Modes** menu in the bottom bar (**Mode: Platform**, shown with a lock until unlocked). Until it is unlocked and selected, NEXXUS stays in the standard desktop view: telemetry, the workstation and the shop.

## What you get when it is on

* **Left wall: your profile hub**, laid out like a professional profile: name, headline, location, about, links, and the links you have shared. Edit it with *Edit profile*.
* **Right wall: your network and friends feed**, showing active posts and shared links from other people.
* **Centre floor:** a fast chat-style feed, with the **command bar fixed at the base** of the floor. Type to post or chat; paste a link and it is shared as a link.
* **Exit Platform** (top right, or the Esc key) collapses the view and returns to the desktop dashboard. On a phone the three areas become Profile / Floor / Network tabs.

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

`GET /api/platform/entitlement`, `POST|DELETE /api/platform/license`, `GET /api/platform/state`, `POST /api/platform/profile`, `POST /api/platform/post`, `DELETE /api/platform/post/<id>`. Everything except the entitlement and license routes returns 402 with the plans until a valid key is present. All of them refuse requests from another web page, another hostname (DNS rebinding) and other machines.
