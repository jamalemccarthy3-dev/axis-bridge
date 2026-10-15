#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "core.h"
#include "inject.h"
#include "manifest.h"
#include "port.h"
#include "tip.h"

static int failures = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)

static void write_file(const char *p, const char *s) { FILE *f = fopen(p, "wb"); fputs(s, f); fclose(f); }

int main(int argc, char **argv) {
    const char *dir = argc > 1 ? argv[1] : ".";
    char p[512], q[512];
    char buf[64];
    BuildManifest m, m2;

    /* defaults */
    port_init();
    CHECK(port_get_max_retries() == 2 && port_is_security_strict() == 1);

    /* creed file */
    snprintf(p, sizeof p, "%s/creed.txt", dir);
    write_file(p, "# creed\nmax_retries = 4\nsecurity_strict=0 # lax\n");
#ifdef _WIN32
    _putenv_s("AXIS_CREED", p);
#else
    setenv("AXIS_CREED", p, 1);
#endif
    port_init();
    CHECK(port_get_max_retries() == 4 && port_is_security_strict() == 0);
    CHECK(strcmp(port_creed_source(), p) == 0);
    write_file(p, "max_retries=99\nsecurity_strict=7\n");
    port_init();
    CHECK(port_get_max_retries() == 2 && port_is_security_strict() == 1);   /* out-of-range values refused */

    /* inject */
    snprintf(q, sizeof q, "%s/s.txt", dir);
    write_file(q, "a b\r\nc  \r\n\r\n");
    CHECK(inject_load(q) == 12);
    CHECK(inject_normalize() == 6 && strcmp(inject_buffer(), "a b\nc\n") == 0);
    CHECK(inject_load("no/such/file") == -1);
    CHECK(inject_set("xyz", 3) == 1 && inject_length() == 3);
    CHECK(inject_set("x", ASSEMBLY_CAP + 1) == 0);

    /* calibrate */
    inject_set("", 0);              CHECK(calibrate_fit() == 0);
    inject_set("ok text\n", 8);     CHECK(calibrate_fit() == 1);
    inject_set("bad\x01", 4);       CHECK(calibrate_fit() == 0);
    port_init();                    /* strict */
    inject_set("caf\xc3\xa9", 5);   CHECK(calibrate_fit() == 0);

    /* manifest: same schematic -> same id */
    snprintf(p, sizeof p, "%s/m.json", dir);
    inject_set("same", 4); CHECK(generate_manifest(&m, p) == 1);
    inject_set("same", 4); CHECK(generate_manifest(&m2, p) == 1);
    CHECK(strcmp(m.build_id, m2.build_id) == 0 && strlen(m.build_id) == 16);
    inject_set("diff", 4); generate_manifest(&m2, p);
    CHECK(strcmp(m.build_id, m2.build_id) != 0);
    inject_reset(); CHECK(generate_manifest(&m, p) == 0);

    /* tip */
    snprintf(p, sizeof p, "%s/tip.log", dir);
    remove(p);
#ifdef _WIN32
    _putenv_s("AXIS_TIP_LOG", p);
#else
    setenv("AXIS_TIP_LOG", p, 1);
#endif
    CHECK(log_build_event("one") == 1 && log_build_event("") == 0);
    { FILE *f = fopen(p, "r"); CHECK(f != NULL); if (f) { fgets(buf, sizeof buf, f); CHECK(strstr(buf, "TIP RECORD: one")); fclose(f); } }

    /* assembly: success and failure with alert 404 */
    inject_set("fine\n", 5);
    CHECK(run_core_assembly() == 1);
    inject_set("bad\x01", 4);
    CHECK(run_core_assembly() == 0 && port_last_alert() == 404);

    printf(failures ? "drive: %d FAILED\n" : "drive: all passed\n", failures);
    return failures ? 1 : 0;
}
