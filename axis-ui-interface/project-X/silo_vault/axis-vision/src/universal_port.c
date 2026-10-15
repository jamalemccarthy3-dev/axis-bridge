#include "universal_port.h"
#include <stddef.h>

// This keeps track of the connection state internally.
// It remains dormant and inactive until a connection signal hits it.
static UMP_Interface ump = {
    .is_connected = false,
    .on_connect = NULL,
    .on_disconnect = NULL
};

// Initializes the port with your specific connection/disconnection actions
void UMP_init(connection_callback_t connect_fn, connection_callback_t disconnect_fn) {
    ump.on_connect = connect_fn;
    ump.on_disconnect = disconnect_fn;
}

// This is the "aware" function. It triggers automatically when
// the module detects it has been plugged into a hardware target.
void UMP_notify_connection(bool connected) {
    if (connected && !ump.is_connected) {
        ump.is_connected = true;
        if (ump.on_connect) {
            ump.on_connect(); // Wake up and bond!
        }
    } else if (!connected && ump.is_connected) {
        ump.is_connected = false;
        if (ump.on_disconnect) {
            ump.on_disconnect(); // Return to standalone/sovereign state
        }
    }
}

// Checks if the port is currently live
bool UMP_is_active(void) {
    return ump.is_connected;
}
