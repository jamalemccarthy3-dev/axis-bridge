#include "tip.h"
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

int log_build_event(const char *message) {
    const char *path = getenv("AXIS_TIP_LOG");
    FILE *fp;
    time_t now;
    if (message == NULL || message[0] == '\0') return 0;
    fp = fopen((path && path[0]) ? path : "build_history.log", "a");
    if (fp == NULL) return 0;
    now = time(NULL);
    fprintf(fp, "[%ld] TIP RECORD: %s\n", (long)now, message);
    return fclose(fp) == 0;
}
