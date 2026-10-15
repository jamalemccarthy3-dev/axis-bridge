# Intake pipeline: Inspect -> Heal -> Gate -> Contribute

Every repository NEXXUS fetches from outside passes through four stages before it is staged for your approval (`nexxus/intake_pipeline.py`, called from `tool_vault.stage`).
Nothing is executed at any point: the stages only read the files (`ast.parse`, `json.loads`, `node --check`).

| Stage | What happens |
|---|---|
| **1. Inspect** | The payload is read into memory (nothing is written). Every file's destination is mapped, each path is checked to stay inside its folder (no `..`, drive letters, Windows device names, case collisions), and the imports are followed so every file's connections are known: relative imports that lead nowhere are "mystery drops", files nothing connects to are listed. |
| **2. Heal** | A file that does not parse is diagnosed from the real parser's message and given a small targeted correction, then checked again, up to 5 rounds: strip a BOM/NUL, replace typographic quotes and dashes, remove a doubled keyword (`import import x`), make mixed tabs consistent, convert a Python 2 `print`, convert a plain `raise Class, message` to `raise Class(message)`, add a missing colon, remove a JSON trailing comma, add a missing `__init__.py`. It keeps working on one file while each correction moves its first failure further on, so a file with many snags still finishes inside the round budget. A fixer refuses to guess: a `raise` with a comment on the line, a tuple value or a traceback part is left alone. A correction is kept only if it clears the file or moves the failure further on. Every one is logged with file, line, the parser's message, before and after. |
| **3. Gate** | Final clearance, uncompromising. Checks: paths stay inside their folder; every file parses; no connection leads nowhere; the asset has an explicit name; every file has an explicit name (conventional ones such as `setup.py`, `__init__.py`, `main.py` are fine); no credential is in the source (the value is never copied into any report); the axis gate itself is available. **One failed check blocks the asset completely**: it is not staged, cannot be approved, and only a report is kept in `staging_vault/_blocked/<id>/`. A notification says so. |
| **4. Contribute** | If anything was corrected, a private note for the original author is written (below). It is saved with the staged asset for you to review. NEXXUS never sends it. |

## What staging keeps
* `source/` is the **corrected** copy, which is what the briefing, the function list and your approval cover. Its file hashes are recomputed, so the usual byte-for-byte approval check still guards exactly what you were shown.
* `upstream/` is the repository **exactly as published**, untouched, kept beside it.
* `pipeline.json` is the full report; `contribution_note.md` is the note. The briefing (`/api/ingest/<id>`, and the Tools drawer) shows the verdict, each stage, each gate check and each correction.
* Approval is refused for an asset whose pipeline record does not say `pass`. Older staged assets with no record still work.

## The note to the original author (Reciprocal Feedback)
Written by `contribution_letter`. It always:
1. says the repository is used **strictly in private**: not published, shared or redistributed, no public critique, and the author's ownership, license and intellectual property remain theirs;
2. says their concept and design are **untouched**: nothing was redesigned, restructured, extended or re-interpreted, and the files they published are kept byte-for-byte. It does not hide that mechanical details were attended to: it lists every one;
3. frames each item as **the route forward**: what stopped the run and the exact route past it, peer to peer, to use whenever they are ready or never, with no pull request unless they ask.
It avoids judgement words (a test checks the tone). A clean repository gets a single line saying nothing needed to change, or no note at all.

Before you send it yourself, the briefing lists what you must be able to say truthfully: that you use the repository only privately, have not published or shared it, and will send the note yourself. NEXXUS cannot know those are true, so it asks rather than assumes.

## Names and Flight Records at every step
The asset is named `<owner>__<repo>` and must pass the explicit-name rule (a stand-in repository name such as `temp` is blocked). Every run is a Flight Record (kind `intake`, Settings > Flight Records) with a checkpoint per stage and its real time; a blocked run is a refused flight, with the failing step and the reason.

## Generated code
Engine builds get the **Heal** stage on what the model writes (same targeted, logged corrections, as `heal` events in the build tracker) before the tests run; their gate is the existing audit, test run and hash-bound approval. Creation mode keeps its own validate-and-repair loop. Both already use explicit names and adoption tags.

## What the gate knows about Python 2 (`nexxus/py2fix.py`)

Three kinds of trouble, handled differently. The rule everywhere: a rewrite is applied only when the Python 3 form is **provably equivalent**; otherwise nothing is touched and the construct is reported.

**1. Syntax that no longer parses** (error-driven, tokenizer-based, so multi-line statements and strings are handled correctly)
* `print` in every form: `print a, b`, `print "x" % y`, `print >>f, x`, trailing comma (`end=" "`), after `if x:` on one line
* `raise E, msg`, `raise E, msg, tb` (`.with_traceback`), `raise E, (a, b)`, with a trailing comment kept
* `exec code in g, l`; `lambda (k, v): body` (one flat tuple; the body is found by bracket depth, multi-line included)
* backticks, `<>`, octal `0755`, long `10L`, lone carriage-return line endings, `async` / `await` used as names (renamed in every file so definitions and callers stay in step; declined if a file uses real coroutines)
* typographic quotes, doubled keywords, mixed tabs, missing colons; JSON trailing commas and comments
* Files are decoded like Python reads them (BOM and `# coding:` honoured, re-encoded the same way). A file that is not valid in its declared encoding is **refused, never guessed**.

**2. Behaviour that parses but means something else on Python 3** (found with the AST; every edit is position-exact, repeated until nothing more changes)
* `except X, e:` (3.14 parses it as a tuple of exception types), `print >>f, x` (valid syntax, a `TypeError` at run time), a lone `print`
* `xrange raw_input unicode unichr basestring long StandardError`, `reduce` (import added), `apply(f, a, k)`, `execfile`, `cmp` (simple arguments only), `file()`, `reload`, `intern`
* `.iteritems() .itervalues() .iterkeys()` (only where the result is just iterated), `d.has_key(k)`, `sys.maxint`, `os.getcwdu()`
* the module renames: `StringIO cStringIO cPickle ConfigParser Queue Tkinter httplib HTMLParser SocketServer BaseHTTPServer Cookie cookielib xmlrpclib urlparse commands thread ...` (written as `import new as old`, so every existing use keeps working), `urllib2` split into `urllib.request` / `urllib.error`, `urllib.urlopen/urlencode/quote ...`, `sets.Set`, `itertools.izip/imap/ifilter`, `types.StringType ...`, `string.letters / maketrans / join / lower ...`
* `__nonzero__ -> __bool__`, `__div__ -> __truediv__`, implicit relative imports inside a package
* Names are resolved **by scope** like Python does (a parameter called `string` does not stop a local `import string` from being recognised), and a name the program defines itself is never touched.

**3. Leftovers that will fail on Python 3 and have no exact rewrite** (reported with the line and the route; the gate **blocks** the asset): `md5`, `sha`, `buffer`, `coerce`, `sets` used other ways, `urllib2` passed around as a module, `dict.iteritems()` whose result is kept, and so on.
Compatibility code is recognised and left alone: `try: import urllib2 / except ImportError:`, `try: unicode / except NameError: unicode = str`, anything under a `sys.version_info` check. A broad `try:` or bare `except:` around ordinary code is **not** treated as a shim.

**Heads-up notes (never blocking):** `__metaclass__`, `next()` instead of `__next__`, `__cmp__`, integer literals divided with `/`, and names that are read but never defined (upstream's own latent problems, such as a typo, are left exactly as published and listed).

## What "pass" means, and does not mean, said plainly
A pass means: every file parses, the paths are safe, nothing leads nowhere, nothing credential-shaped is in the source, names are explicit, and **no known Python 2 only code remains**. It does **not** mean the program works. Nothing is ever run, so logic, `str` versus `bytes` handling, dictionary ordering, integer division on variables, and missing third-party packages are not checked; the briefing's own risk review and your approval still stand between a pass and a tool.
Real code the gate correctly refuses: `voidfiles/lark` has `def ClientSchema(collander.MappingSchema):` (a `def` where a `class` was meant), which no tool should "repair". Real code it now clears: `hncrawl` (48 corrections including a vendored BeautifulSoup), `evolutionary-circuits` (96), `amazonaccess` (60), `Drapache` (35), `oauth2lib`, `skypipe`.
Other limits: `ur"..."` literals, tuple parameters in `def` (as opposed to `lambda`) and `raise "string"` are not rewritten; Python 3.14 accepts `except A, B:` as a tuple, which is why the behaviour pass looks for it.

Routes (admin token): `GET /api/ingest/<id>` (briefing with `pipeline`), `GET /api/ingest/<id>/contribution`. Tests: `nexxus/test_intake_pipeline.py`, `nexxus/test_intake_staging.py`, `test_intake_routes.py`.
