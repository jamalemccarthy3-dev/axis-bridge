# Demo plan: a 90-second video and a README GIF

Goal: let a stranger see, in under two minutes, that NEXXUS is a real, working system with real safeguards. Everything below uses what exists today. Nothing is staged and nothing is simulated.

## Before you record (10 minutes)

- Restart the hub so the latest code is live (`restart_nexxus.bat`), and wait until the Boiler Room shows 21 of 21.
- Hide anything personal: the **Creations** panel (scroll it away or use a clean session), saved sessions, notification pop-ups. Close other browser tabs.
- Do **not** show the admin token. Unlock the padlock off camera, then record from a state where the token is already entered and never shown in a field.
- Set the browser window to 1920x1080 and zoom to 100 percent. Turn on Do Not Disturb.
- Record with Windows Game Bar (`Win+G`, then Record) or OBS. Export an MP4 for the repository's Releases page and a short GIF (under 10 MB) for the README.
- Leave the phone/Tailscale section **out** until the real mobile-data test has passed.

## The 90-second shot list

| Time | On screen | What you say (in your own words) |
|---|---|---|
| 0:00 | The dashboard, Boiler Room in the corner reading 21/21 | One line: what NEXXUS is. "A local-first mesh of 21 independent engines with a dashboard that commands it." |
| 0:10 | Click the Boiler Room to expand it | The engines run headless; the dashboard is the command and aggregation layer, not 21 widgets. |
| 0:25 | Close one engine window (for example `ENGINE axis-vision`). Watch it turn stale in about 24 seconds while the others stay green. Restart it | Isolation: one engine dying does not stop the others, and the dashboard says so within a known time. |
| 0:45 | Open the Perimeter panel. Show the quarantine list, then press **Release All**, then **Confirm?** | Failed packets are kept as inert, redacted copies; bulk release needs two presses and leaves a tamper-evident record. Do this on a **test** perimeter, never your real quarantine. |
| 1:05 | In a terminal: `python engine_checklist.py axis-core` and show the nine PASS lines | Every engine has to pass the same nine-point definition of done, with raw output kept. |
| 1:20 | Open `AUDIT.md` on screen, scroll to "What is proven, and what is not" | Close on honesty: the list of what is not proven yet is public. |

## The README GIF (10 to 15 seconds)

The engine-close moment only: the Boiler Room dots with one going stale and recovering. It is the most convincing single clip. Save it as `docs/images/isolation.gif` and add one line under the screenshot in the README.

## Do not

- Do not show real quarantine contents, keys, tokens or the Creations panel.
- Do not claim phone access, Bluetooth or production readiness. Say "public beta, working, with known limits".
- Do not use the clone-and-run claim until a clean machine has actually been tested.

## Record in the demo sandbox (recommended)

`demo_sandbox.py` makes an isolated copy of the system on port 8100, with its own 21 engines, its own demo-only quarantine items (12 obviously fake packets) and a throwaway admin token, `demo-token`,
that is safe to type on camera. Your real hub, quarantine, logs and secrets are never touched. Record the **whole** video there.

```
python demo_sandbox.py build        (once: copies the system, creates the demo settings and demo items)
python demo_sandbox.py start        (starts the sandbox hub and 21 engines; open http://localhost:8100/ and use the token demo-token)
python demo_sandbox.py reseed       (puts the 12 demo items back before each take of "Release All")
python demo_sandbox.py checklist    (the nine-point checklist for axis-core, run against the sandbox)
python demo_sandbox.py status       (shows the sandbox and your real hub are different servers)
python demo_sandbox.py stop         (stops only the sandbox)
python demo_sandbox.py clean        (stops it and deletes the sandbox folder)
```

Notes: items 3 and 4 of the checklist show NOT RUN unless you add `--stop-test`; that is the engine-close step, which you can do by hand on camera. Item 8 shows BLOCKED while commits are on hold,
so crop it out of the recording (decided by the owner on 2026-10-14). Because the crop leaves out a line, keep the narration accurate: say "these checks pass", not "all nine pass" or "A+".
Run `--stop-test` by hand beforehand so items 3 and 4 are PASS on screen, or crop those two lines as well rather than leaving NOT RUN visible. Tested on 2026-10-14: Release All in the sandbox released 12 of 12 with a verified record while the real quarantine stayed at 497.
