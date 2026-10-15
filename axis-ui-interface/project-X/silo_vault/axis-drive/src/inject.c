#include "inject.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char assembly_buffer[ASSEMBLY_CAP + 2];
static size_t assembly_len = 0;

void inject_reset(void) {
    assembly_len = 0;
    assembly_buffer[0] = '\0';
}

const char *inject_buffer(void) { return assembly_buffer; }
size_t inject_length(void) { return assembly_len; }

int inject_set(const char *data, size_t n) {
    if (n > ASSEMBLY_CAP || (n > 0 && data == NULL)) return 0;
    if (n > 0) memcpy(assembly_buffer, data, n);
    assembly_len = n;
    assembly_buffer[n] = '\0';
    return 1;
}

int inject_load(const char *path) {
    FILE *fp;
    size_t n;
    if (path == NULL || path[0] == '\0') return -1;
    fp = fopen(path, "rb");
    if (fp == NULL) return -1;
    n = fread(assembly_buffer, 1, ASSEMBLY_CAP + 1, fp);   /* one byte more than the cap, to notice a file that does not fit */
    fclose(fp);
    if (n > ASSEMBLY_CAP) {
        inject_reset();
        return -1;
    }
    assembly_len = n;
    assembly_buffer[n] = '\0';
    return (int)n;
}

int inject_logic(void) {
    const char *path = getenv("AXIS_SCHEMATIC");
    int n = inject_load(path);
    if (n < 0) return 0;
    printf("[INJECT] loaded %d bytes from %s\n", n, path);
    return 1;
}

size_t inject_normalize(void) {
    size_t r = 0, w = 0;
    /* CRLF -> LF (a lone CR stays) */
    for (r = 0; r < assembly_len; r++) {
        if (assembly_buffer[r] == '\r' && r + 1 < assembly_len && assembly_buffer[r + 1] == '\n') continue;
        assembly_buffer[w++] = assembly_buffer[r];
    }
    assembly_len = w;
    /* trailing blanks, tabs, newlines and NULs go; then exactly one newline */
    while (assembly_len > 0 && (assembly_buffer[assembly_len - 1] == ' ' || assembly_buffer[assembly_len - 1] == '\t' ||
                                assembly_buffer[assembly_len - 1] == '\n' || assembly_buffer[assembly_len - 1] == '\0'))
        assembly_len--;
    if (assembly_len > 0) assembly_buffer[assembly_len++] = '\n';
    assembly_buffer[assembly_len] = '\0';
    return assembly_len;
}
