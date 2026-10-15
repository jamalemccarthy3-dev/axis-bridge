#include "port.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static CreedRules current_creed = {2, 1};   /* private to this file; the defaults */
static char creed_source[260] = "defaults";
static int last_alert = 0;

void port_init(void) {
    const char *path = getenv("AXIS_CREED");
    FILE *fp;
    char line[160];
    current_creed.max_retries = 2;
    current_creed.security_strict = 1;
    strcpy(creed_source, "defaults");
    if (path == NULL || path[0] == '\0') return;
    fp = fopen(path, "r");
    if (fp == NULL) {
        printf("[PORT] cannot read the Creed file %s: keeping the defaults\n", path);
        return;
    }
    while (fgets(line, sizeof line, fp)) {
        char *hash = strchr(line, '#');
        int v;
        if (hash) *hash = '\0';
        if (sscanf(line, " max_retries = %d", &v) == 1) {
            if (v >= 1 && v <= 10) current_creed.max_retries = v;
            else printf("[PORT] max_retries=%d is out of range 1..10: keeping %d\n", v, current_creed.max_retries);
        } else if (sscanf(line, " security_strict = %d", &v) == 1) {
            if (v == 0 || v == 1) current_creed.security_strict = v;
            else printf("[PORT] security_strict=%d is not 0 or 1: keeping %d\n", v, current_creed.security_strict);
        }
    }
    fclose(fp);
    strncpy(creed_source, path, sizeof creed_source - 1);
    creed_source[sizeof creed_source - 1] = '\0';
}

int port_get_max_retries(void) { return current_creed.max_retries; }
int port_is_security_strict(void) { return current_creed.security_strict; }
const char *port_creed_source(void) { return creed_source; }

void trigger_alert(int error_code) {
    last_alert = error_code;
    printf("[ALERT] System threshold breached! (code %d)\n", error_code);
}

int port_last_alert(void) { return last_alert; }
