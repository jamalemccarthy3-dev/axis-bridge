#ifndef MANIFEST_H
#define MANIFEST_H

typedef struct {
    char build_id[17];   /* 16 hex digits: an FNV-1a hash of the assembled schematic, so the same schematic always gets the same id */
    int version;
} BuildManifest;

/* Wraps the build with its metadata: fills *out (if given) and writes {"build_id", "version", "bytes"} as JSON to `path`.
   Returns 1 on success, 0 if there is nothing assembled or the file cannot be written. */
int generate_manifest(BuildManifest *out, const char *path);

#endif
