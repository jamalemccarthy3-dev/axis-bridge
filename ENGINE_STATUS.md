# Engine status (python engine_audit.py regenerates the table; the notes are written by hand)

The flat import probe cannot tell the silos' own lib/ and config/ folders apart, so for axis-SandM, axis-video_creator, axis-logic and axis-integrity read each engine's own health_report.py instead of the 'Import problems' column. C engines: `python c_engine_check.py`.

| Engine | Files | Code lines | Stubs | Import problems (flat probe) | Notes |
|---|---:|---:|---:|---:|---|
| S.A.M.U.E.L.- | 9 | 383 | 0 | 0 | Six .logic rule files (specification, nothing executes them yet); honest file check; own repo. |
| axis-SandM | 179 | 2043 | 4 | 41 | Operational: 7/7 agents start, every utility imports. All 42 former placeholder tools now do real work on local data (data/ folder, inbox drop folders), covered by test_governor.py and test_silos.py. Outside feeds (social, competitor, sales) are read from data/inbox/, never invented. |
| axis-cloud | 29 | 1209 | 0 | 0 | Imports clean. Not examined in depth. |
| axis-core | 11 | 340 | 0 | 1 | Operational: the C SDK (named pipes, security lock, guarded purge) compiles and passes a real pipe loopback test (test_c_core.py). A report-only purge replaced one that deleted files on a plain call. The MinGW in bin/ has no cc1 (cannot compile). |
| axis-curator | 56 | 1095 | 2 | 1 | Operational: QC reviewer on the orchestrator bus; tools do real work. |
| axis-diagnostic | 71 | 867 | 0 | 0 | Operational: every module imports and every tool can be created (test_operational.py). |
| axis-drive | 11 | 408 | 0 | 0 | C engine; compiles with warnings on and passes tests/test_drive.c (test_c_core.py): the Creed loads from AXIS_CREED, the schematic from a file or AXIS_SCHEMATIC, retries reload it, the manifest id is a hash of the build, the TIP ledger appends to AXIS_TIP_LOG. Its prebuilt .exe is untouched and untracked. |
| axis-integrity | 126 | 1076 | 37 | 15 | Operational: every layer imports, tamper-evident Auditor, registry matches disk. |
| axis-link | 18 | 483 | 0 | 0 | Imports clean after a class-name alias fix. |
| axis-llm | 46 | 3104 | 0 | 0 | Imports clean after a class-name alias fix. |
| axis-logic | 200 | 3810 | 40 | 23 | Operational: calibrated-probability pipeline; real sports, stocks, ecom and logs engines; 27 + 26 tests. gaming_video tests still call methods the physics engines never had. |
| axis-omni | 16 | 638 | 0 | 2 | Python voice works; the C core was rewritten coherently (message queue, tempo, mode loader, speech plan, routing): it compiles, links and passes 22 C checks. An input handler that ran `rmdir` through the shell no longer deletes anything. |
| axis-phonetic | 14 | 401 | 0 | 0 | C engine; compiles and links (main.c was a copy of Omni's with headers that do not exist here; rewritten for this engine). Own repo. |
| axis-port | 11 | 405 | 0 | 0 | C engine; compiles and links (actuator file names and includes fixed). |
| axis-search_engine | 52 | 3149 | 0 | 0 | Operational offline: every component loads; search queries are URL-encoded; 6 tests. |
| axis-sweep | 12 | 412 | 0 | 0 | Operational: JavaScript engine rewritten with real lineage/purge/scheduler/throttler logic; 15 node tests. |
| axis-triage | 30 | 970 | 0 | 1 | Operational: gate, sanitiser, sync, packet delivery, controller; 8 tests. |
| axis-validator | 77 | 2176 | 0 | 21 | Operational: all 60 src modules import; tests. |
| axis-vantage_point | 14 | 462 | 0 | 0 | C console messenger; compiles and links; packets are sealed with real ChaCha20-Poly1305 (RFC 8439 test vectors pass in tests/test_vantage.c), the key is AXIS_VANTAGE_KEY and with no key nothing is sent. The hub is an in-process relay (no socket transport), identities are random identifiers (no key exchange yet). The prebuilt .exe predates the sources and must be rebuilt. Own repo. |
| axis-video_creator | 220 | 1592 | 31 | 35 | Operational: builds timed storyboards for NEXXUS orders; some modules are marked stubs. |
| axis-vision | 12 | 406 | 0 | 0 | C engine; compiles and links; the three declared functions (process_input, validate_structural_integrity, provide_user_feedback) are implemented and tested. |
| triad-protocol-module- | 21 | 768 | 0 | 0 | Imports clean. Own repo. |
