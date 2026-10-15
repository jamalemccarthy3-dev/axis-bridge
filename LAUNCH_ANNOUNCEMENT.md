# NEXXUS Public Beta

**My time is money, but my product is free.**

I'm Jamale McCarthy. NEXXUS is my formal introduction to the industry and my portfolio statement: not a starter kit, not a box of parts, not a blueprint you have to finish yourself.
It is a completed, engineered, local-first AI infrastructure: a 21-node headless mesh, a gate that verifies what it runs, and a dashboard that commands it. You download it, install it and run it.

Today it enters **Public Beta**.

---

## What you are getting

- **A 21-node mesh that runs on your own machine.** Twenty-one independent engines (data pipelines, validators, builders, media and 3D, a vault container, diagnostics and more) signed into one hub. Each has its own key and a real health check, and keeps running if a neighbour fails.
- **A dashboard that commands, not decorates.** Telemetry, the rolled-up engine cluster, perimeter controls (Hard Lock, Quarantine, tamper-evident bulk release) and the operator's overrides. The engines run headless; the dashboard stays focused.
- **axis gate.** Signed manifests, replay protection and drift detection. Inbound files and builds stay staged until the owner signs them off.
- **Your own sandboxed silos.** Each installation is its own instance, on your own computer, with its own private memory. Nothing is shared with me or with other users' installs.
- **An audit you can read.** [AUDIT.md](AUDIT.md) is the record of an adversarial architectural review: what was attacked, what broke, what was fixed, with measurements. It also lists what is *not* proven yet.

## The terms, in plain words

| | |
|---|---|
| **Free** | Reading, running, studying, learning from, and building personal, educational and other **noncommercial** projects. This is not a trial. It stays free. |
| **Commercial use** | Building a paid product or service on NEXXUS, or selling, hosting or bundling it, needs a **one-time commercial license: $199**. Contact: **[CONTACT EMAIL]**. |
| **The core** | **The core architecture is closed to modification; build alongside it through the documented interfaces.** I maintain the core myself and do not take changes to it. |
| **License** | [PolyForm Noncommercial 1.0.0](LICENSE), with the scope of the work spelled out. This is source-available, not open source. |

The core is protected by design: the axis gate seals it with signed manifests and tells you when anything drifts. Build your own silos and tools next to it, not inside it.

## Why a beta, and what I'm asking for

It's a beta because I'd rather say so than claim more than I've proven. I want your honest feedback: **good, bad or broken.** If it fails on your machine, if a doc is wrong, if something is
confusing or slow, tell me. That is how this gets better, and every report helps. Open an issue on the repository.

## Honest limits (today)

- **Windows 10/11, one machine.** Local-first means one computer, not a cluster.
- **Resources.** The local model runs on CPU through Ollama. On a modest machine (mine has 8 GB of RAM) replies are slow, and that's hardware, not a bug.
- **Phone access** over Tailscale is built and locked down, but my real-world test over mobile data is not finished. I'll update this line when it passes.
- **Bluetooth** is not verified: the machine I develop on has no radio.
- **Support.** I'm one operator. I read every report; I can't promise response times.
- Some third-party tools (Python packages, ffmpeg, Ollama, the InstantMesh model) are installed separately under their own licenses. See section 5 of [LICENSE](LICENSE).

## Get started

```
git clone <repository URL>
cd axis-bridge
pip install -r requirements.txt
START_NEXXUS.bat
```

Then open `http://localhost:8000/`. Full instructions are in [README.md](README.md).

## Who this is for

Developers who want to **study a complete, working, audited multi-engine system** and run it for themselves. Builders who want a reliable base to put their own silos next to. Anyone who
would rather read a finished piece of engineering than assemble one.

---

*Jamale McCarthy · jamalemccarthy3-dev · Commercial licensing: [CONTACT EMAIL]*

<!-- PERSONAL PHILOSOPHY goes in the README; link to it here if you want it in the announcement. -->
