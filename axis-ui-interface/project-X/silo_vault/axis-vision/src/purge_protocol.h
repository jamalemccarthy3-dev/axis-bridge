
#ifndef PURGE_PROTOCOL_H
#define PURGE_PROTOCOL_H

#define STATE_DORMANT 0

// Function declarations - MUST match purge_protocol.c exactly
void purge_volatile_memory(void);
void save_persistent_data(const char* file_path);
void execute_cleanup_routine(void);
void send_copy_to_user(const char* filepath);

#endif