#ifndef CORE_H
#define CORE_H

/* The core: auto-calibrates the injected schematic and assembles.
   calibrate_fit()      -> 1 if the assembly buffer holds a schematic that fits, 0 if not. It tidies the buffer (inject_normalize) and then checks it:
                           not empty, no NUL or control characters other than tab/newline, and in strict mode (the Creed) only printable ASCII.
   run_core_assembly()  -> 1 on success; 0 after the Creed's max_retries failed attempts (each retry reloads the schematic), having raised alert 404.
                           On success it writes the build manifest and a TIP record. */
int calibrate_fit(void);
int run_core_assembly(void);

#endif
