# Platform mode

**Platform mode is a digital academy.** It is built as a self-contained school and training ground: a structured curriculum where people learn how to build, operate and run real systems using exact prompts, teaching tools and command blueprints, earn badges as proof of what they learned and did, and then take on leadership by guiding others through the same path. Everything below (profile, floor, vault, public wall, ranks) supports that loop. It is open to everyone in Beta.

## The Academy (the front door)

* **Tracks, modules and steps.** Four tracks ship: **Operate NEXXUS** (the control room itself, using only things that really exist in it), and three business tracks, **YouTube channel profile**, **Digital storefront** and **Content pipeline**. Each step says why it matters, what to do, gives exact **prompts** and **commands** (with a Copy button), tips, a click-to-load **video** slot, and how you know you are done. See `academy/README.md` for how content is written and how to attach a video you have the right to use.
* **Start here:** onboarding quests (accept the Code of Conduct, fill in your profile, post an introduction, share a public post, choose a path). The ones NEXXUS can check itself are checked against what you really did, so they cannot be faked. Quests that need other people are shown and clearly marked "not available yet".
* **Solo Build or Group Build.** Solo is independent work through a track. Group asks you to follow a **trust protocol** (introduce yourself, help others, collaborate, be vouched for) before entering a team pod. Most of those steps need other people and pods, which are not built, so they stay open and nothing is faked; pod entry shows as locked.
* **Badges are proof.** Finish a module for a module badge, a whole track for a track badge. Each badge shows how it was proved: **verified by NEXXUS**, **self-reported** (the step asks you to write what you did) or part of each. The criteria for all 14 badges are on the shelf. Your badge ledger is append-only.
* **The leadership loop.** Finishing any whole track earns **Mentor-ready**: you can now guide others through it. Mentoring itself (matching you with a learner and reviewing their work) needs other people on the platform and is not built yet; the badge says so.
* **Badges and ranks are separate.** Badges come only from learning and doing. Ranks come only from public contributions (the ledger below).
* **Open Beta:** every track is open from day one, with no payment and no prerequisites.

**Honestly not built yet:** other people (friends, direct messages, group chats), pods, and live audio/video rooms. Those need a networked server, accounts and moderation. The Academy, profile, vault, public wall, ranks and GitHub audit trail work today.

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

## The profile wall (what visitors see)

The centre column has three views: **Floor**, **Profile wall** and **Image vault**. The profile wall is a LinkedIn-style page for visitors: a banner and your profile photo, name, headline and location, then **About**, **Experience** (a timeline of roles), **Projects** (cards with links), **Skills** (chips), **Featured** (up to 3 of your floor posts or photos) and **Links**. Each section has its own *Visible to visitors* switch and its own editor, and your profile photo is chosen from your image vault.

* **Privacy first:** location and links start **hidden**; the other sections start visible. Visitors always see name and headline, and nothing else unless you leave it on.
* **View as visitor:** shows the page exactly as a visitor sees it, built by the same server code (`GET /api/platform/profile/public`) that a future network will use to serve real visitors. Hidden sections do not appear at all. Featured posts show only their text, link and photo, never comments, ratings or your other posts.
* There are **no visitors yet**, because there is no network. The wall is complete and ready; it is the preview you can check today.

## The image vault

Every photo you add or post is kept in your **image vault**, private to you: a grid you can open full size, add to (button or drag-and-drop), post from, use as your profile photo, or delete (click twice). Deleting a post leaves its photo in the vault; deleting from the vault removes the file once no post and no profile photo use it. Up to 300 photos; all are cleaned of location and camera data when stored.

## The welcome manifest

The first time anyone enters Platform they see a welcome briefing (and any time from **What is this?** in the header): what the platform is (a sovereign digital academy, collaborative workspace and company-building ground), the **Beta** notice (everything that exists is open to everyone, free, with no locked tiers; if paid tiers are ever introduced you will see exactly what each includes before you pay, and nobody is charged during Beta), what works today, and what is **not available yet** with what each item needs. It never advertises something that does not exist, and `test_teams.py` fails if a planned feature is described as available.

## Talk to NEXXUS and Post & Publish

The command bar at the base of the floor has two modes, always labelled so you know where your words go:

* **Talk to NEXXUS** (blue): a private line to the NEXXUS on this computer for questions, debugging and guidance. It goes only to NEXXUS; it is never posted, never public, never sent to GitHub and never counted for ranks (`nexxus_talk` is a private kind in `privacy.py`). It is the same NEXXUS as on your desktop dashboard. Builds are still chosen deliberately: exit Platform and pick a build mode.
* **Post & Publish**: **Private note** (grey: a scratchpad saved only for you) or **Shared post** (green: goes on the public wall; publishing it to GitHub is a separate, confirmed step on the Public wall).

Each destination keeps **its own draft**: switching between Talk, Private and Shared never wipes what you were typing (drafts also survive a reload in the same tab). Leaving the Talk view by any tab puts the bar back to posting, so the label is never wrong.

## Team workspaces (Teams tab)

A **team**, **pod** or **company** workspace has a mission, a **task board** (to do / doing / done, due dates, overdue flagged), **blueprints** (attach Academy tracks and see progress), an activity log and a leader's **control center**: workflow health, overdue work, blueprint progress and **real system telemetry** read from this NEXXUS (hub CPU, memory and uptime, and the status of every engine). Workspaces are private to you.

**Honest limits:** a workspace has one member, you: inviting teammates needs the network, which does not exist yet. Live team rooms, team chat and a **company phone line** are shown as **Not available yet** with the reason (a real phone line needs a telephony provider account, a number, identity checks and legal registration, which NEXXUS cannot provide or fake). Storefront connections and team-specific automation bots are not built; the Academy's storefront track teaches the path and NEXXUS's own engines are the automation layer you can see live.

## Private conversations stay private

Direct messages, group chats and live rooms are **private**. They are never collected, never scraped, never shown on the public wall, never sent to GitHub and never counted toward ranks. This is enforced in code, not just promised: `privacy.py` defines the two classes of data, every public path (public wall, GitHub sync, ranking) accepts only items that pass `require_public()`, private stores live in `nexxus_data/private/` (gitignored, never read by any public module), and `test_privacy.py` fails if a public module ever references a private store or the telemetry schema gains a content field. The platform has no direct messages or group chats yet; this is the rule they must follow when they are built.

## The public wall, ranks and GitHub

* **Public wall:** every post on the floor starts **private**. Press *private* under a post to make it public; it then appears on the **Public wall** view with its comments. Nothing is public unless you choose.
* **GitHub audit trail:** from the Public wall you can **publish** a public post as a Discussion in this repository (category "Show and tell"). You see the exact text first, tick that you understand it becomes public and cannot be taken back from here, and confirm; nothing is ever sent automatically. **Pull GitHub comments** brings other people's comments back onto the post (with their GitHub login and a link), and a comment of yours can be posted to the Discussion with its own confirmation. Photos are not uploaded. Setup: start NEXXUS with `NEXXUS_GITHUB_TOKEN` set (for example from `gh auth token`) and Discussions enabled on the repository; the token is read from the environment each time and is never saved, logged or returned. Optional: `NEXXUS_GITHUB_REPO`, `NEXXUS_DISCUSSION_CATEGORY`.
* **Ranks (Newcomer, Apprentice, Builder, Craftsman, Master):** your rank comes from one **ledger** you can read in full (*How ranks work* on the left wall): +2 for each public post (up to 5 a day) and +1 for each comment another person leaves on your public post (up to 10 a day). Comments on your own posts earn nothing, one award per item, nothing is measured besides the ledger, and a post made private again loses its points. Pod tasks and "helpful" marks are listed in the table but earn nothing yet because they need parts that are not built.
* **Honest limits:** with no network yet, the only other people who can take part are those who comment on your GitHub Discussions. A mirrored post cannot be made private from here (delete the Discussion on GitHub; GitHub may keep cached copies). The GitHub calls are tested against a fake GitHub; the first real publish is the first live test, so try it once with a harmless post.

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

`GET /api/platform/entitlement`, `POST|DELETE /api/platform/license`, `GET|POST /api/platform/teams`, `GET|DELETE /api/platform/teams/<id>`, `POST /api/platform/teams/<id>/task`, `POST|DELETE /api/platform/teams/<id>/task/<id>`, `POST /api/platform/teams/<id>/blueprint`, `POST /api/platform/academy/welcome`, `GET /api/platform/academy`, `GET /api/platform/academy/track/<id>`, `POST /api/platform/academy/path|conduct|step`, `GET /api/platform/state`, `GET /api/platform/stream` (live events), `POST /api/platform/profile` (merges the fields sent), `GET /api/platform/profile/public`, `POST /api/platform/post/<id>/public`, `GET /api/platform/public`, `GET /api/platform/ranks`, `GET /api/platform/github/plan`, `POST /api/platform/github/publish|pull`, `POST /api/platform/post/<id>/comment/<cid>/github`, `GET|POST /api/platform/vault`, `DELETE /api/platform/vault/<id>`, `POST /api/platform/vault/<id>/post`, `POST /api/platform/post` (JSON, or multipart with an `image`), `DELETE /api/platform/post/<id>`, `POST /api/platform/post/<id>/rating`, `POST /api/platform/post/<id>/comment`, `DELETE /api/platform/post/<id>/comment/<cid>`, `GET /api/platform/media/<id>`. Outside Beta, everything except the entitlement and license routes returns 402 with the plans until a valid key is present. All of them refuse requests from another web page and another hostname (DNS rebinding); other devices are served only if the dashboard's own network rules admit them, and their changes need the admin token.
