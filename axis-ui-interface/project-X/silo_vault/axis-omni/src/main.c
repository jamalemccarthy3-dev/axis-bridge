#include <stdio.h>
#include "../lib/vibe_profiles.h"
#include "../lib/system_registry.h"
#include "../lib/metronome.h"
#include "../lib/post.h"
#include "../lib/pipe.h"
#include "../lib/speech_engine.h"
#include "../lib/aggregator.h"
#include "input_handler.h"

int main(void) {
    /* 1. Initialize the brain */
    system_registry_init();
    speech_engine_init();
    VibeProfile profile;
    if (!load_vibe_profile("bank/performance_modes/standard_neutral.json", &profile) && !load_vibe_profile("../bank/performance_modes/standard_neutral.json", &profile)) {
        profile = (VibeProfile){"neutral", 85, "moderate", "balanced"};
    }

    /* 2. Orchestration loop: it ends at the end of the input (fgets blocks while it waits, so it never spins) */
    while (handle_input()) {
        metronome_tick();
        if (has_message()) {
            Message msg = pop_message();
            aggregator_fetch_all();
            pipe_stream_data(PIPE_A, msg, &profile);
        }
    }
    print_registry_status();
    return 0;
}
