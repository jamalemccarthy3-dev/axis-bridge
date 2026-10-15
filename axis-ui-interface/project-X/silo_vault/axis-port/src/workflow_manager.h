#ifndef WORKFLOW_MANAGER_H
#define WORKFLOW_MANAGER_H

typedef enum {
    STATE_IDLE,
    STATE_CONFIG_LOAD,
    STATE_EXECUTE_BUILD,
    STATE_SAFETY_CHECK,
    STATE_PURGE_CLEANUP,
    STATE_ERROR_RESET
} SystemState;

extern SystemState current_state;

void run_workflow(void);

#endif

 
