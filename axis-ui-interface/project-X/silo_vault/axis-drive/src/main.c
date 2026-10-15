#include <stdio.h>
#include "main.h"
#include "core.h"
#include "inject.h"
#include "port.h"

int drive_run(const char *path) {
    int ok;
    port_init();
    printf("Creed: max_retries=%d security_strict=%d (from %s)\n", port_get_max_retries(), port_is_security_strict(), port_creed_source());
    if (path != NULL) {
        if (inject_load(path) < 0) {
            printf("cannot load the schematic %s\n", path);
            return 2;
        }
    } else if (!inject_logic()) {
        printf("no schematic: give a file as argument 1 or set AXIS_SCHEMATIC\n");
        return 2;
    }
    ok = run_core_assembly();
    printf(ok ? "Assembly succeeded.\n" : "Assembly FAILED.\n");
    return ok ? 0 : 1;
}

/* axis-drive: argument 1 (or $AXIS_SCHEMATIC) is the schematic. Exit code 0 only if the assembly succeeded. */
int main(int argc, char **argv) {
    return drive_run(argc > 1 ? argv[1] : NULL);
}
