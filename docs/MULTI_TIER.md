# Two tiers: your command center and the user sandbox

NEXXUS runs as two separate tiers that never share a trust boundary.

| Tier | Where | What it is | Who can reach it |
|---|---|---|---|
| **Command center** | Your desktop | The full NEXXUS dashboard, server, engines, keys, capture and operator tools | Loopback only (plus Tailscale or LAN if you switch it on). Never the open internet. |
| **User sandbox** | Each user's own phone or browser | The public PWA on GitHub Pages: a static page with no access to your desktop, your files or your keys | Anyone, but it can only talk to the relay below |

## How sandbox telemetry reaches your desktop

```
user's device (opt-in)  --HTTPS POST /e-->  relay (Cloudflare Worker + KV queue)
                                                      ^
your desktop  --HTTPS GET /pull, POST /ack (outbound only)--+
```

* **Your desktop never accepts a connection from the internet.** It calls out to the relay on a timer (every 5 minutes) or on demand, fetches queued events and deletes them from the relay once stored.
* **Off by default, opt-in only.** Until a relay address is put in `config.js` the privacy card is hidden and the page can send nothing. Once configured, a visitor must tick the box. Unticking, or "Delete my ID and turn off", deletes the random ID and stops sending.
* **Fixed, tiny schema.** An event is: name (`page_view`, `install_clicked`, `app_installed`, `section_opened`, `feedback_opened`, `review_link_clicked`, `error`), time, a random install ID, app version, installed-as-app yes/no, a screen class (small, medium, large) and an optional short tag. No text, names, IP addresses (the relay does not store them), or browser details.
* **Checked three times.** The page, the relay and the desktop each enforce the same schema; `test_telemetry_hub.py` fails if they ever disagree. The desktop does not trust the relay.

## Setting it up

1. Deploy the relay (needs a free Cloudflare account):
   ```bash
   cd relay
   npx wrangler kv namespace create EVENTS_KV     # paste the id into wrangler.toml
   npx wrangler secret put PULL_KEY               # choose a long random key
   npx wrangler deploy                            # prints the relay's https address
   ```
2. Put that address in `config.js` (`window.NEXXUS_RELAY_URL = "https://..."`) and push, so the Pages site picks it up.
3. On the desktop, before starting NEXXUS: `set NEXXUS_RELAY_URL=https://...` and `set NEXXUS_RELAY_KEY=<the PULL_KEY>`. Put them in `nexxus_env.bat`, which is gitignored. Never commit them.
4. Watch it: `python telemetry_hub.py summary`, or `GET http://127.0.0.1:8000/api/sandbox-telemetry/summary?days=7` (local machine only). `POST /api/sandbox-telemetry/pull` collects immediately.

Raw events are stored in `nexxus_data/telemetry/` (gitignored). The summary returns counts only (events by name and day, distinct installs, versions); it never returns install IDs.

## What this does not do

* It does not monitor the desktop app, only the public sandbox page.
* It cannot identify anyone: the ID is random and local to one browser, and clearing site data or opting out resets it.
* Relay rate limiting is not built in. Add a Cloudflare rate-limiting rule on `/e` if the relay is ever abused.
