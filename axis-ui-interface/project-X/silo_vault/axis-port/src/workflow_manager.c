
#include <stdio.h>
#include "workflow_manager.h"

SystemState current_state;

void run_workflow(void) {
    current_state = STATE_IDLE;
    printf("Workflow: System returned to IDLE state.\n");
}
