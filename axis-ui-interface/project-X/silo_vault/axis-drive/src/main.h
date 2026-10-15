#ifndef MAIN_H
#define MAIN_H

/* The Master Ignition. drive_run() is the whole run: it loads the Creed (port_init), loads the schematic (the given path, or $AXIS_SCHEMATIC when path is
   NULL), and assembles. Returns 0 when the assembly succeeded, 1 when it failed, 2 when no schematic could be loaded. main() just calls it. */
int drive_run(const char *path);

#endif
