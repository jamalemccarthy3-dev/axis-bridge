#include "manifest.h"
#include "inject.h"
#include <stdio.h>

static unsigned long long fnv1a(const char *b, size_t n) {
    unsigned long long h = 1469598103934665603ULL;
    size_t i;
    for (i = 0; i < n; i++) {
        h ^= (unsigned char)b[i];
        h *= 1099511628211ULL;
    }
    return h;
}

int generate_manifest(BuildManifest *out, const char *path) {
    BuildManifest m;
    FILE *fp;
    if (inject_length() == 0 || path == NULL) return 0;
    snprintf(m.build_id, sizeof m.build_id, "%016llx", fnv1a(inject_buffer(), inject_length()));
    m.version = 1;
    fp = fopen(path, "w");
    if (fp == NULL) return 0;
    fprintf(fp, "{\"build_id\": \"%s\", \"version\": %d, \"bytes\": %lu}\n", m.build_id, m.version, (unsigned long)inject_length());
    if (fclose(fp) != 0) return 0;
    if (out) *out = m;
    return 1;
}
