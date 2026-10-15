# The NEXXUS source feed

Every copy of NEXXUS can receive real results from the **original** NEXXUS. It is one-way: the original publishes a signed file, each copy downloads it and checks the signature. Nothing about the user is sent
anywhere, and nothing connects into the original, so a copy can never reach the original's data, keys or quarantine.

## What it carries (real data only)

| Section | Content |
|---|---|
| `system` | How many engines the original runs, how many are live and mesh-ready, hub uptime |
| `audit` | The original's dashboard audit result and the engine-cluster rollup |
| `tests` | The latest full test run: suites passed, failed, and whether it was ALL GREEN, with the date |
| `version` | The short commit id the results came from |
| `outputs` | Results the owner chose to publish. Each one must name its **source** and **method**, and carries a notice that it is not advice or a guarantee. Empty until the owner adds real ones |
| `notice` | A plain statement that these are one system's results, offered for information |

Nothing else goes in. The publisher checks the bundle and **stops** if any text looks like a file path, a private address, a key or a credential. No sample or invented data is ever published: if there is nothing
real to say in `outputs`, it says so.

## How a copy trusts it

- The bundle is signed with the owner's Ed25519 key. The matching public key ships with the app (`feed_public_key.pem`). The private key stays on the owner's PC (`.local_config/`, git-ignored).
- A copy refuses a feed whose signature does not match, that is too large, in an unknown format, dated in the future, or **not newer than the one it already has** (replay).
- A feed past its validity window is still shown, but marked stale.
- The saved copy is re-verified every time it is read, so an edited file is caught and not shown.
- Offline or a wrong address gives a plain message and keeps the last verified copy.

## For the owner: publishing (free)

```
python feed_publish.py keygen            once; then BACK UP .local_config/feed_signing_key.pem somewhere private
python feed_publish.py build             collects real results from the running hub, signs them, writes feed_out/
```

Upload the `feed_out/` folder to any static host. The simplest free one is **GitHub Pages** on a small public repository dedicated to the feed (for example `nexxus-feed`): put the folder's files at the repository root, then
turn on Pages in its settings. The feed address is then `https://<your-user>.github.io/nexxus-feed/latest.json`. Put real outputs in `feed_outputs/*.json` before building (each needs `title`, `summary`, `source`,
`method`, `generated_at`, and optionally `data`). Nothing is uploaded by these commands: you upload `feed_out/` yourself.

## For a copy: receiving

Set `NEXXUS_FEED_URL` to the published address once, then `python feed_client.py fetch`, or `POST /api/feed/refresh` with the admin token. The dashboard's API shows the last verified feed at `GET /api/feed/latest`.

## License numbers

`python feed_publish.py license 4821 "Buyer Name"` prints a signed token for the number you put on the download page. A copy can check it offline with the public key. A license signature can never be used as a feed
signature or the other way round. Nothing is sent or tracked.

## Honest limits

- Until the feed address is set and a feed is published, copies show "not set up yet". Nothing is invented in its place.
- Outputs are one system's results, with the source and method stated. Their real-world accuracy has not been measured, so none is claimed.
- This is a trust-the-publisher design: copies trust the owner's key. If that key is lost or stolen, a new public key must ship with a new release.
