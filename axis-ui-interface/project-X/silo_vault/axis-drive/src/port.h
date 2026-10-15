#ifndef PORT_H
#define PORT_H

typedef struct {
    int max_retries;
    int security_strict;
} CreedRules;

/* The Creed: the rules the drive runs under. port_init() loads them from the file named by AXIS_CREED (lines  max_retries=N  and  security_strict=0|1;
   '#' starts a comment); without that variable, or for a line it does not understand, the defaults (2 retries, strict) stand and port_creed_source()
   says so. A value outside 1..10 retries or not 0/1 for strict is refused and the default kept. */
void port_init(void);
int port_get_max_retries(void);
int port_is_security_strict(void);
const char *port_creed_source(void);   /* "defaults", or the file the Creed was loaded from */
void trigger_alert(int error_code);    /* records the alert (see port_last_alert) and prints it */
int port_last_alert(void);             /* the last error code raised, 0 if none */

#endif
