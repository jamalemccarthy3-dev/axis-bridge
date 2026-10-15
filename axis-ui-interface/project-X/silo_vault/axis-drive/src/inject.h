#ifndef INJECT_H
#define INJECT_H

#include <stddef.h>

#define ASSEMBLY_CAP 65536   /* the assembly buffer holds at most this many bytes */

/* Reads the raw schematic file and maps it into the assembly buffer.
   inject_load(path)   -> bytes loaded (0..ASSEMBLY_CAP), or -1 if the file cannot be read or is larger than the buffer
   inject_logic()      -> 1 if the schematic named by the AXIS_SCHEMATIC environment variable was loaded, 0 if not (no variable, no file, too big)
   inject_set(d, n)    -> puts bytes straight into the buffer (for callers that already have them); returns 1, or 0 if n > ASSEMBLY_CAP
   inject_normalize()  -> tidies the buffer: CRLF -> LF, trailing blanks and NULs removed, one final newline; returns the new length
   inject_buffer() / inject_length() / inject_reset()  read the buffer, its length, and empty it */
int inject_load(const char *path);
int inject_logic(void);
int inject_set(const char *data, size_t n);
size_t inject_normalize(void);
const char *inject_buffer(void);
size_t inject_length(void);
void inject_reset(void);

#endif
