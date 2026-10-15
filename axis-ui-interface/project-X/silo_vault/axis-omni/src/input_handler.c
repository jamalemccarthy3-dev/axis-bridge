#include <stdio.h>
#include <string.h>
#include "input_handler.h"

SystemState current_state = SANDBOX_MODE;

/* Nexus: the final authority. The audit refuses empty input; a real logic/principle audit belongs to NEXXUS itself. */
int nexus_execute_audit(const char* input) {
    printf("Nexus: running the input audit...\n");
    return input != NULL && input[0] != '\0';
}

/* Axis-engines (workspace): work proposed by S.A.M.U.E.L. or any engine in the silo */
void execute_engine_build(const char* input) {
    printf("Engine: build request noted: %s\n", input);
}

/* Config-live: architect assistant */
void execute_config_live(const char* input) {
    (void)input;
    printf("Config-Live: a session folder would be created in the Sandbox Workbench.\n");
}

void execute_purge_folder(const char* input) {
    (void)input;
    printf("Config-Live: removing a project folder needs a person to confirm it; nothing was deleted.\n");
}

/* Universal dispatcher */
void process_user_input(const char* input) {
    if (!nexus_execute_audit(input)) {
        printf("Omni: empty input ignored.\n");
        return;
    }
    if (strstr(input, "start session") || strstr(input, "begin")) {
        execute_config_live(input);
        printf("Omni: session ready. Would you like to finalize the build and wake Nexus?\n");
    }
    if (strstr(input, "let's build") || strstr(input, "finalize")) {
        current_state = FACTORY_MODE;
        execute_engine_build(input);
    }
    if (strstr(input, "purge")) {
        execute_purge_folder(input);
    }
}

int handle_input(void) {
    char line[256];
    if (!fgets(line, sizeof line, stdin)) return 0;
    line[strcspn(line, "\r\n")] = '\0';
    process_user_input(line);
    return 1;
}
