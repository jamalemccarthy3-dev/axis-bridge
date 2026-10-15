"""test_ui_state.py - the dashboard page (silo_vault/render/babylon_preview.html): its script still parses, and the two front-end fixes are in place.

  1. Drawers and modals: opening the (i) cheat sheet used to scroll the body sideways (a fixed drawer parked off-screen widened the body, which has a CSS
     perspective, and focusing inside the sliding drawer scrolled it), which dragged the Tool briefing drawer into view next to it and left both stuck.
     The body is now overflow:clip, focus does not scroll, one drawer is open at a time, and x / Escape / a press outside / the modal backdrop close things.
  2. A refresh restores the screen (conversation, notes, cube face, drawer, unsent text) from localStorage.

These are checks of the source plus a syntax check of the script (node, when it is installed). The behaviour itself was exercised in a real browser
against the running server; see ENGINE_STATUS.md. Run: python test_ui_state.py"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(ROOT, "axis-ui-interface", "project-X", "silo_vault", "render", "babylon_preview.html")
with open(PAGE, encoding="utf-8") as _f:
    HTML = _f.read()


def scripts():
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", HTML, flags=re.S)


class PageSource(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_every_inline_script_parses(self):
        for i, code in enumerate(scripts()):
            path = os.path.join(tempfile.mkdtemp(prefix="ui_js_"), "s%d.js" % i)
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            r = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, "script %d: %s" % (i, r.stderr[-600:]))

    def test_the_body_cannot_be_scrolled_sideways(self):
        self.assertRegex(HTML, r"body\s*\{\s*overflow:\s*clip;\s*\}")
        self.assertRegex(HTML, r"body, html \{[^}]*overflow:\s*hidden")      # html stays hidden so the body's clip is not handed to the viewport

    def test_focusing_the_filter_does_not_scroll(self):
        self.assertIn("f.focus({ preventScroll: true })", HTML)
        self.assertNotIn("getElementById('cmdSheetFilter').focus()", HTML)

    def test_drawer_guard_covers_close_paths(self):
        self.assertIn("function initDrawerGuard", HTML)
        for needle in ("e.key === 'Escape'", "'pointerdown'", "#closeCmdSheetBtn, #closeToolBriefBtn", "modal-overlay", "nxCloseDrawers(m.target.id)"):
            self.assertIn(needle, HTML, needle)
        guard = HTML.index("initDrawerGuard();")
        self.assertLess(guard, HTML.index("function initCmdSheet"), "the guard must be set up before (and independently of) the panel inits")

    def test_every_drawer_is_known_to_the_guard(self):
        listed = set(re.findall(r"'(\w+Drawer)'", re.search(r"const NX_DRAWERS = \[(.*?)\];", HTML).group(1)))
        in_page = set(re.findall(r'<div id="(\w+Drawer)" class="archive-drawer', HTML))
        self.assertEqual(listed, in_page)

    def test_screen_state_is_saved_and_restored(self):
        for needle in ("NX_SCREEN_KEY", "function nxScreenCapture", "function nxScreenRestore", "'pagehide'", "'beforeunload'", "fresh=1", "nxScreen.ready"):
            self.assertIn(needle, HTML, needle)
        self.assertIn("if (!nxScreen.ready) return false;", HTML)             # the saved screen is never overwritten before it was put back
        self.assertIn("nxCleanHtml(f.files[k])", HTML)                        # restored notes HTML is cleaned first
        self.assertIn("nxScreen.briefId = id;", HTML)

    def test_engine_build_telemetry_and_prompt_vault_pieces_are_in_the_page(self):
        for needle in ('<option value="engine_build"', 'id="engineStandalone"', 'id="engineTrackerBtn"', 'id="engineTrackerDrawer"', 'id="engTree"', 'id="engApprove"',
                       'id="promptVaultBtn"', 'id="promptVaultDrawer"', 'id="engineLedStrip"', 'id="telTable"', 'id="telBeep"', 'engine_build:  { chip'):
            self.assertIn(needle, HTML, needle)
        # the [P] button sits in the header right beside the (i) button, and is placed with it
        self.assertLess(HTML.index('id="cmdInfoBtn"'), HTML.index('id="promptVaultBtn"'))
        self.assertLess(HTML.index('id="promptVaultBtn"') - HTML.index('id="cmdInfoBtn"'), 400)
        self.assertIn("document.getElementById('promptVaultBtn'); if (pb) pb.style.left", HTML)
        # approval goes through the admin helper and carries the hash that was shown; nothing deploys from the page without it
        self.assertIn("briefing_sha256: eng.brief.sha256", HTML)
        self.assertIn("crAdmin(`api/engine/builds/", HTML)
        # the tracker must not close on an outside click (you watch a build while you work); the vault may
        peek_line = re.search(r"const NX_PEEK_DRAWERS = (\[[^\]]*\])", HTML).group(1)
        self.assertNotIn("engineTrackerDrawer", peek_line)
        self.assertIn("promptVaultDrawer", peek_line)
        # sound only after a user gesture, and it can be muted
        self.assertIn("pointerdown', () => { if (tel.beepOn) telAudio(); }", HTML)
        self.assertIn("nexxusTelemetryPrefs", HTML)
        # the hidden attribute must really hide the engine controls in other modes
        self.assertIn("#engineSwitchWrap[hidden], #engineTrackerBtn[hidden] { display:none !important; }", HTML)

    def test_boiler_room_pieces_are_in_the_page(self):
        for needle in ('<option value="diagnostic"', 'id="boilerWidget"', 'id="boilerRoomPanel"', 'id="brBody"', 'id="closeBoilerBtn"', 'id="bwLock"', 'id="brLock"',
                       "diagnostic:    { chip: 'DIAGNOSTIC'", "api/diagnostics/overview", "api/diagnostics/engine/", "function brShowEngine", "function brOpen"):
            self.assertIn(needle, HTML, needle)
        # the widget is the first thing in the left sidebar; the panel is a top-level sibling of the drawers (fixed to the window, not to the 3D cube)
        aside = HTML.index('<aside class="left-sidebar"')
        self.assertLess(aside, HTML.index('id="boilerWidget"'))
        self.assertLess(HTML.index('id="boilerWidget"') - aside, 120)
        self.assertGreater(HTML.index('id="boilerRoomPanel"'), HTML.index('id="toolBriefDrawer"'))
        # it must NOT be treated as a drawer: Escape and outside clicks must not close the monitor you are working beside
        self.assertNotIn("boilerRoomPanel", re.search(r"const NX_DRAWERS = \[[^\]]*\]", HTML).group(0))
        self.assertNotIn("boilerRoomPanel", re.search(r"const NX_PEEK_DRAWERS = \[[^\]]*\]", HTML).group(0))
        # a response for a view you have already left is dropped, and a click during a refresh is not lost
        self.assertIn("if (view !== br.view) { br.again = true; return; }", HTML)
        self.assertIn("if (br.busy) { br.again = true; return; }", HTML)
        # the panel is remembered across a refresh like the other screen state
        self.assertIn("boiler: !!(typeof br !== 'undefined' && br.open)", HTML)
        self.assertIn("step('boiler'", HTML)

    def test_no_mock_data_or_invented_telemetry_is_left_in_the_page(self):
        # the purge: nothing in the page states a figure or a status that nothing measures
        for fake in ("NASDAQ Index", "S&P 500 Ticker", "Premier League Scores", "ARS 2 - 1 MCI", "Armor Mesh Rig", "Destructibility Physics", "512 MB (Local", "22 Nodes Synchronized", "NEXXUS-V2-STABLE",
                     "pulse=60Hz", "sync_interval=30s", "SAMPLE DATA", "initWaveCanvas", "wave-canvas", "Registered Utilities & Parameters"):
            self.assertNotIn(fake, HTML, fake)
        self.assertNotRegex(HTML, r"telemetry-val\" style=\"color: #34d399;\">(ENGAGED|PASSING)<")              # the old always-green claims
        self.assertIn("let dashboardHubsList = [];", HTML)                                                    # only real dashboards, from the server
        self.assertNotIn("ptInput(", HTML)                                                                    # no calculator input starts pre-filled with an example number
        for needle in ("function settingsLiveFill", "function liveUtilitiesHtml", "function ptNoData", "function ptGate", "None declared. Nothing is assumed.", "Nothing is shown here until real data is loaded."):
            self.assertIn(needle, HTML, needle)
        # every static engine entry keeps its name and description but declares no invented utilities
        reg = HTML[HTML.index("const diagnosticsState = {"):HTML.index("\n};\n", HTML.index("const diagnosticsState = {"))]
        self.assertNotRegex(reg, r"utilities: \[\s*\{")

    def test_axis_link_pieces_are_in_the_page(self):
        for needle in ('<option value="link"', 'Mode: Link', 'id="transmissionHub"', 'TRANSMISSION', 'id="linkFlyout"', 'id="lkVoice"', 'id="qLights"', 'id="lkSettingsCard"',
                       "link:          { chip: 'LINK'", "api/link/log", "api/link/txn/", "api/link/analyze", "api/link/hypothesis", "api/input/queue", "function lkSync", "function lkPlay", "lkQueueRejected"):
            self.assertIn(needle, HTML, needle)
        # both panels are top-level and fixed between the header and the footer on the same axis, so the mode selector underneath is never covered
        self.assertGreater(HTML.index('id="transmissionHub"'), HTML.index('id="toolBriefDrawer"'))
        self.assertIn(".tx-hub, .lk-fly { position:fixed; top:60px; bottom:60px;", HTML)
        # the engine hub on the right exists only in Link mode, and the two left panels never show together
        self.assertIn("f.classList.toggle('open', !!open && lk.on)", HTML)
        self.assertIn("if (typeof brOpen === 'function') brOpen(false);", HTML)
        for needle in ('id="axisDock"', 'id="dockBuildBtn"', 'id="dockPerimBtn"', 'id="dockHomeBtn"', 'id="dockBuild"', 'id="dockPerim"', 'id="breachBanner"', 'id="tokDialog"',
                       "function nxAskToken", "function dockBuildOpen", "function pmGoToCommand", "api/perimeter/triad", "api/auth/check", "a.type === 'open_perimeter'"):
            self.assertIn(needle, HTML, needle)
        # the stuck key sequence: no admin-token path may use the blocking window.prompt any more
        self.assertNotIn("window.prompt('Admin token", HTML)
        self.assertGreater(HTML.index('id="dockPerim"'), HTML.index('id="dockBuild"'))
        for needle in ('id="flightRecords"', 'id="frList"', 'id="frTrace"', "function frSelect", "function frTrace", "g.diagnosis" if False else "d.diagnosis", "STALLED"):
            self.assertIn(needle, HTML, needle)
        # Flight Records sit at the base of the Settings face: after the Tools card, before the next face
        self.assertGreater(HTML.index('id="flightRecords"'), HTML.index('id="toolsList"'))
        self.assertLess(HTML.index('id="flightRecords"'), HTML.index('id="face-diagnostics"'))
        # the dock reads Home -> Link -> Build, with Perimeter staying at the far end
        order = [HTML.index('id="%s"' % i) for i in ("dockHomeBtn", "dockLinkBtn", "dockBuildBtn", "dockPerimBtn")]
        self.assertEqual(order, sorted(order))
        # the four portals sit in front of Home: Sports -> Markets -> Logistics -> Economics -> Home (test_portals.py checks the rest of that strip)
        order = [HTML.index('id="%s"' % i) for i in ("dockPt_sports", "dockPt_markets", "dockPt_logistics", "dockPt_economics", "dockHomeBtn")]
        self.assertEqual(order, sorted(order))
        # the engine status panels must not flicker: the header strip, the Settings table, the Link flyout's Engines tab and the engine dock are patched in place, and a flash is
        # played AFTER the render (the old code flashed the LEDs and then threw them away)
        for needle in ("function telSetSt", "pendingFlash.forEach(e => { telFlash(e.engine)", "lk.dockKey", "lk.engSig", "body.replaceChildren(frag); body.scrollTop = keep; lk.engSig = sig"):
            self.assertIn(needle, HTML, needle)
        self.assertNotIn("strip.textContent = '';\n        tel.engines.slice(0, 8).forEach(e => {", HTML)          # the old rebuild-every-poll strip
        self.assertNotIn("body.appendChild(nxEl('div', 'lk-note', 'Reading the engines...'))", HTML)               # the collapse-to-one-line placeholder
        # the Perimeter panel must not flicker or snap shut (it used to flash red forever and rebuild itself empty-then-full every few seconds)
        self.assertNotRegex(HTML, r"body\.breach-on #dockPerim \{[^}]*animation")                 # the PANEL has no flashing animation; only the button pulses, a finite number of times
        self.assertRegex(HTML, r"body\.breach-on #dockPerimBtn \{[^}]*animation:breachFlash 0\.9s ease-in-out 3;")
        for needle in ("async function pmGather", "function pmSig", "function pmApplyLive", "body.replaceChildren(frag)", "dk.pmPinned", "id=\"dockPerimPin\"", "pmLs('nxPerimOpen'"):
            self.assertIn(needle, HTML, needle)
        self.assertNotIn("body.textContent = '';\n        // upper: the perimeter gate", HTML)             # the old empty-then-refill rebuild is gone
        self.assertIn("if (!dk.pmPinned) pmOpen(false);", HTML)                                     # Build and HOME only close it when it is unpinned
        self.assertIn('id="lkEngineDock"', HTML)
        self.assertIn("lkFly(true, 'engines'); lkDock();", HTML)
        # home-room isolation: rotateCube() itself sets body[data-face], and CSS hides every home-only element in any other room (hidden, never closed: their state and polling carry on)
        self.assertIn('<body data-face="home">', HTML)
        self.assertRegex(HTML, r"function rotateCube\(face\) \{\s+const cube = document\.getElementById\('cubeWorld'\);\s+if \(!cube\) return;\s+if \(/\^\(nexxus\|nexus\|search\|settings\|diagnostics\|dashboards\)\$/\.test\(face\)\) nxFaceGate\(face\);")
        self.assertIn('body:not([data-face="home"]) .home-only { visibility: hidden !important; pointer-events: none !important; }', HTML)
        for el in ("axisDock", "dockBuild", "dockPerim", "dockPortal", "dockDesk", "linkFlyout", "lkEngineDock", "transmissionHub"):
            self.assertIn("'%s'" % el, HTML[HTML.index("const NX_HOME_ONLY"):HTML.index("function nxHomeOnlyInit")], el)
        # Link > Engines: an explicit tab open forgets the Engines tab's last drawing, or coming back from the Hypothesis desk is skipped as "unchanged"
        self.assertRegex(HTML, r"function lkRenderFly\(\) \{\s+stopPlay\(\);\s+lk\.engSig = '';")
        # the response card header is NEXXUS-branded: no window dots, no "HTML" label (the FRONTEND / BACKEND callers fill the small sub-tag instead)
        head = HTML[HTML.index("function buildMessageControlHeader()"):HTML.index("// Builds a NEXXUS response card")]
        self.assertIn('class="nx-brand-tag">NEXXUS<', head)
        for gone in ("window-dot", "window-controls", "artifact-language", ">HTML<"):
            self.assertNotIn(gone, head, gone)
        self.assertIn("frontendCard.querySelector('.nx-brand-sub')", HTML)
        self.assertIn("backendCard.querySelector('.nx-brand-sub')", HTML)
        # the status pill is hidden when idle and only shown while NEXXUS works: every outcome of a send goes through finalize(), which ends the thinking state once
        self.assertRegex(HTML, r"\.q-lights \{[^}]*display:none;")
        self.assertIn(".q-lights.processing, .q-lights.full, .q-lights.maxed, .q-lights.thinking { display: flex; }", HTML)
        self.assertIn("nxThinking(true);\n    let thinkDone = false;", HTML)
        self.assertIn("function finalize(replyText, question, job, modeRequired, creationJob) {\n        thinkEnd();", HTML)
        # the mode menu: our own list, appended to <body> (outside the 3D cube), never rebuilt while open, closed only by a pick, Esc, a press elsewhere or leaving the room
        self.assertIn("function modeMenuInit()", HTML)
        self.assertIn("document.body.appendChild(list);", HTML)
        self.assertIn('id="renderModeSelect"', HTML)                                     # the native select stays in the page as the source of truth the rest of the code reads
        sync = HTML[HTML.index("function modeMenuSync()"):HTML.index("function modeMenuHi(i)")]
        self.assertNotIn("replaceChildren", sync)                                        # syncing only changes labels and marks, so a background poll can never disturb an open list
        self.assertIn("if (typeof modeMenuSync === 'function') modeMenuSync();", HTML)
        for panel in ("transmissionHub", "linkFlyout"):
            self.assertNotIn(panel, re.search(r"const NX_DRAWERS = \[[^\]]*\]", HTML).group(0))


if __name__ == "__main__":
    unittest.main(verbosity=1)
