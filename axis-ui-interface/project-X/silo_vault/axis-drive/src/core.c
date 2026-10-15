#include "core.h"
#include "inject.h"
#include "manifest.h"
#include "port.h"
#include "tip.h"
#include <stdio.h>

int calibrate_fit(void) {
    size_t i, n;
    const char *b;
    inject_normalize();
    n = inject_length();
    b = inject_buffer();
    if (n == 0) return 0;                                   /* nothing to assemble */
    for (i = 0; i < n; i++) {
        unsigned char c = (unsigned char)b[i];
        if (c == '\n' || c == '\t') continue;
        if (c < 0x20 || c == 0x7f) return 0;                /* a control character or NUL: not a text schematic */
        if (port_is_security_strict() && c > 0x7e) return 0; /* strict: printable ASCII only */
    }
    return 1;
}

int run_core_assembly(void) {
    int attempts = 0, max = port_get_max_retries();
    BuildManifest m;
    while (attempts < max) {
        if (attempts > 0) inject_logic();                   /* a retry reloads the schematic: the file may have been corrected */
        if (calibrate_fit()) {
            if (generate_manifest(&m, "build_manifest.json")) {
                log_build_event("assembly succeeded");
                return 1;
            }
            log_build_event("assembly fitted but the manifest could not be written");
            trigger_alert(500);
            return 0;
        }
        attempts++;
    }
    log_build_event("assembly failed: the schematic did not fit");
    trigger_alert(404);
    return 0;
}
