#include "actuator_interface.h"
#include "../lib/actuator.h"            // the builder
#include "../lib/memory_purger.h"       // the purger
#include "../lib/stability_watchdog.h"  // the safety/reset tool

void execute_build_command(void) {
    // SRC calls the LIB builder
    perform_manifestation();
}

void execute_purge_command(void) {
    // SRC calls the LIB purger
    purge_buffers();
}

void execute_safety_reset(void) {
    // SRC calls the LIB safety/reset tool
    trigger_reset();
}
