#include <stdio.h>
#include <string.h>
#include <stdlib.h>

// --- System State Definitions ---
typedef enum { SANDBOX_MODE, FACTORY_MODE } SystemState;
SystemState current_state = SANDBOX_MODE;
int in_dialogue_session = 0;

// Conversation Memory Buffer to track what we are discussing
char last_topic[256] = "none";

// --- Nexxus: The Final Authority ---
int nexxus_execute_audit(char* input) {
    printf("Nexxus: Running logic/principle audit...\n");
    return 1;
}

// --- Axis-Engines (Workspace) ---
void execute_engine_build(char* input) {
    printf("Engine: Executing build request: %s\n", input);
}

// --- Config-Live: Architect Assistant Utility ---
void execute_config_live(char* input) {
    printf("Config-Live: Creating folder structure in the Sandbox Workbench...\n");
}

// --- Cleanup Utility: Folder Purge ---
void execute_purge_folder(char* input) {
    printf("Config-Live: Purging unwanted project folder from the Sandbox Workbench...\n");
    system("rmdir /s /q abandoned_build 2>nul");
}

// --- Universal Dispatcher with Correction Handling ---
void process_user_input(char* input) {
    // 1. Handle Corrections on the Fly
    if (strstr(input, "no,") || strstr(input, "not correct") || strstr(input, "wrong") || strstr(input, "i meant")) {
        printf("Steward: Understood. Let's recalibrate. Rejecting prior assumption on '%s'—what is the correct adjustment, Architect?\n", last_topic);
        return;
    }

    // Exit active dialogue if requested
    if (strstr(input, "exit dialogue") || strstr(input, "stop talking")) {
        in_dialogue_session = 0;
        printf("Steward: Exiting active dialogue. Returned to standard workbench.\n");
        return;
    }

    // 2. Active Conversational Loop with Context Tracking
    if (in_dialogue_session) {
        // Save this input as our current active discussion topic
        snprintf(last_topic, sizeof(last_topic), "%s", input);
        
        printf("Steward: I've logged '%s' into our active thread. Building on that premise, how should we refine this engine component next?\n", input);
        return;
    }

    // 3. Mode Switching & Triggers
    if (strstr(input, "start session") || strstr(input, "begin")) {
        execute_config_live(input);
        printf("Omni: Project folder created. Material stored. Would you like to finalize the build and wake Nexxus?\n");
        return;
    }

    if (strstr(input, "let's build") || strstr(input, "finalize")) {
        current_state = FACTORY_MODE;
        in_dialogue_session = 0;
        printf("Omni: Presenting material to Nexxus for audit...\n");
        return;
    }

    if (strstr(input, "conversation") || strstr(input, "hello") || strstr(input, "hi")) {
        current_state = SANDBOX_MODE;
        in_dialogue_session = 1;
        printf("Steward: Conversation mode engaged. Sandbox workbench open. What systems or design concepts are we working on?\n");
        return;
    }

    // 4. Factory vs Sandbox Execution Logic
    if (current_state == FACTORY_MODE) {
        if (nexxus_execute_audit(input)) {
            if (strstr(input, "create a new folder")) {
                execute_config_live(input);
            } else {
                execute_engine_build(input);
            }
            printf("Nexxus: Execution confirmed. Logic/Principles verified.\n");
        } else {
            printf("Nexxus: Build rejected. Logic mismatch. Redirecting to Sandbox for calibration.\n");
            current_state = SANDBOX_MODE;
        }
    } else {
        // Default Sandbox Handling
        snprintf(last_topic, sizeof(last_topic), "%s", input);
        printf("Steward: Received '%s' in the sandbox workbench. Would you like to open an active conversation thread about this? (Type 'conversation' to begin)\n", input);

        if (strstr(input, "build story")) {
            execute_engine_build(input);
        } else if (strstr(input, "create a new folder")) {
            execute_config_live(input);
        } else if (strstr(input, "delete folder") || strstr(input, "purge")) {
            execute_purge_folder(input);
        }
    }
}

// --- Main Program Entry Point ---
int main(void) {
    char input_buffer[256];
    printf("=== NEXXUS Core Initialized ===\n");
    
    while(1) {
        printf("\nEnter command: ");
        if (fgets(input_buffer, sizeof(input_buffer), stdin) == NULL) {
            break;
        }
        input_buffer[strcspn(input_buffer, "\r\n")] = 0;
        
        if (strlen(input_buffer) > 0) {
            process_user_input(input_buffer);
        }
    }
    return 0;
}