#ifndef UNIVERSAL_PORT_H
#define UNIVERSAL_PORT_H

#include <stdbool.h>

// This defines the type of function the module will call when connected
typedef void (*connection_callback_t)(void);

// The core UMP interface
typedef struct {
    bool is_connected;
    connection_callback_t on_connect;
    connection_callback_t on_disconnect;
} UMP_Interface;

// Functions to register and trigger the "awareness"
void UMP_init(connection_callback_t connect_fn, connection_callback_t disconnect_fn);
void UMP_notify_connection(bool connected);
bool UMP_is_active(void);

#endif
