# =====================================================================
# REVIEW SNIPPET  (optional - paste into any engine that should act as a PEER REVIEWER)
# When NEXXUS reviews staged files before they are committed, every engine that
# declares a utility named "review" is asked to look at them too, and its findings
# are added to the report (tagged with this engine's name).
#
# WHERE IT GOES: in the engine's entry file, BELOW the mesh snippet's `utility`
# decorator definition and ABOVE its `if "--mesh" in sys.argv:` block (the same
# place as any other @utility - the mesh answers and exits at that block).
# After adding it, run mesh discovery once so NEXXUS learns the engine has a reviewer.
#
# WHAT IT RETURNS: {"findings": [{"severity": "critical"|"warning"|"info",
#                                 "file": "name", "line": 12, "message": "what is wrong"}]}
# A "critical" finding HOLDS the commit until you release it, so only mark a finding
# critical when it really should stop a build. Anything that is not one of those three
# severities is treated as "info". Return {"findings": []} when you find nothing.
# =====================================================================
@utility("review", "Peer-review staged files and report findings", params={"files": "dict of file name -> text"})
def review(files):
    findings = []
    for name, text in (files or {}).items():
        for number, line in enumerate(str(text).splitlines(), 1):
            # TODO: replace this example check with what THIS engine is good at
            # (e.g. axis-logic: check that probabilities sum to 1; axis-validator: schema checks).
            if "FIXME" in line:
                findings.append({"severity": "warning", "file": name, "line": number,
                                 "message": "FIXME left in the file"})
    return {"findings": findings}