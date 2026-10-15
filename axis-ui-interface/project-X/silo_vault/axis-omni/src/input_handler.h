/* input_handler.h - the interface map */
#ifndef HANDLER_H
#define HANDLER_H

/* State enumerator so other modules know the system status */
typedef enum { SANDBOX_MODE, FACTORY_MODE } SystemState;

/* External access to the current state */
extern SystemState current_state;

/* Reads one line from stdin and dispatches it. Returns 1 while there is input, 0 at end of input. */
int handle_input(void);
void process_user_input(const char* input);
int nexus_execute_audit(const char* input);
void execute_engine_build(const char* input);
void execute_config_live(const char* input);
/* Deleting a project folder is NEVER done from a typed command: this only reports that it needs a person. */
void execute_purge_folder(const char* input);

#endif
