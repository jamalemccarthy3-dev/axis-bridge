# Publishing the public facade (PRIVATE notes: this file is not part of the public output)

## Rules that keep the code private
1. **Never make an existing repository public.** Every repo that has ever held code keeps that code in its history, forever. The public repo is a NEW repo whose only commit is the generated facade (`C:\Users\Jamal\Desktop\public_facade`).
2. Keep these private: `nexxus`, `axis-phonetic`, `axis-vantage_point`, `S.A.M.U.E.L.-`, `Triad-protocol-module-`, the axis gate repository and anything else holding source.
3. Rebuild with `python build_facade.py build` (the leak guard must say CLEAN) and never edit the output by hand.
4. Names are the content: the public can see every folder and file NAME. If a name reveals something you want private, add a word from it to `extra_hide_names` in `facade_policy.json` and rebuild.
5. Review `descriptions` in `facade_policy.json`: they are DRAFT labels taken from folder names.

## GitHub settings for the public repo
**Repository name (suggestion):** `nexxus-architecture` (a plain, searchable name beats a clever one)

**Description (under 350 characters):**
> Autonomous Automation AI Infrastructure and Orchestrator: a sovereign, local-first orchestration framework with empty utility skeletons. Infrastructure, not handouts: no plug-and-play code, no cloud crutches. Command your own local AI to build the implementation.

**Topics (GitHub allows 20; lowercase, hyphens):**
`system-design` `software-architecture` `modular-architecture` `reference-architecture` `architecture-diagram` `plugin-architecture` `microservices` `multi-agent-systems` `ai-agents` `local-first` `self-hosted` `python` `design-patterns` `separation-of-concerns` `api-gateway` `human-in-the-loop` `ai-orchestration` `ai-infrastructure` `workflow-automation` `agentic-ai`

**Website field:** leave empty until there is a page to point to.

**Other settings:** turn off Wiki, Projects and Discussions unless you will use them (an empty tab looks abandoned); keep Issues on if you want feedback.
Add a **social preview image** (Settings > General): a clean 1280x640 picture of the diagram from the README.

## Keywords to keep in the README (people search these phrases)
modular architecture, system design, reference architecture, plugin architecture, single gateway, bridge pattern, separation of concerns, local-first AI,
self-hosted AI, multi-agent system, human-in-the-loop, facade pattern. They are already in the README's headings and first paragraph; keep the first 150
characters meaningful, because that is what search results and link previews show.

## What actually drives discoverability (honest list)
- A clear first paragraph and a diagram (done), accurate topics (above), and a stable name.
- Linking to the repo from places people already read (your own site, posts, profiles). No setting makes a repo rank by itself.
- A licence. With none, all rights are reserved and some people will not touch it. For a structure-only repo, CC BY 4.0 or MIT are common choices: your call.
- Do not add claims you cannot defend (such as "nobody has built this"). Technical readers check, and one counter-example costs more trust than the claim earns.

## Go-live record (2026-10-08) and procedure

Pre-flight found two problems that cannot be fixed after publishing, and both were fixed BEFORE anything went public:
1. The bridge side listed wiring and governance file names (mesh, roster, governance, orders, diagnostics, tunnel, watchdog, tests...). The builder now hides them (`BRIDGE_HIDE`) and the leak guard enforces it.
2. The 8 local commits carried the real email address and older file listings. The public repository is ONE fresh commit under the GitHub no-reply address; the old history was discarded.

Procedure when you have created the (empty) public repository:
1. Create it on GitHub as PUBLIC, EMPTY: no README, no licence, no .gitignore (otherwise the first push conflicts). Suggested name: `nexxus-architecture`.
2. `cd C:\Users\Jamal\Desktop\public_facade` then `git remote add origin https://github.com/<you>/<name>.git` then `git push -u origin main`.
3. On GitHub: Add file > Create new file > name it `LICENSE` > pick the Creative Commons Attribution 4.0 template (the README already states CC BY 4.0).
4. Settings: paste the description and topics from this file; upload a social preview image.
5. Archive it for a dated, independent record (Software Heritage or the Internet Archive) and tag a release.
Never push the private repositories to the public one, and never make an existing private repository public.

## Deployment record (2026-10-08)

Created on GitHub with the GitHub CLI (v2.102.0, checksum-verified, signed by GitHub, Inc.), authenticated as the owner through a one-time device code; the token lives in the system keyring, never in a file:
- `nexxus-architecture`: PUBLIC, empty at creation. Description and the 20 topics set; wiki, projects and discussions off; issues on. The public history is ONE commit under the GitHub no-reply address; the official CC BY 4.0 text is its `LICENSE`.
- `picthis`, `theblogguy`: PRIVATE, new.
- `axis-bridge`, `axis-core`, `TheBlogGuyEngine`: already existed (private, each only a one-commit `.gitattributes` scaffold). Nothing was overwritten: `go_live.ps1` fetches the scaffold commit and MERGES it in. No force push, ever.
- Already pushed earlier: `nexxus`, the axis gate repository, `axis-phonetic`, `axis-vantage_point`, `S.A.M.U.E.L.-`, `Triad-protocol-module-`.

Cleanup of the login (do this when you no longer want the CLI to have access):
1. Remove the CLI's access: GitHub > Settings > Applications > Authorized OAuth Apps > "GitHub CLI" > Revoke.
2. The CLI binary lives only in a temporary scratch folder; deleting that folder removes it.
Git itself keeps using your normal stored login for pushes.
