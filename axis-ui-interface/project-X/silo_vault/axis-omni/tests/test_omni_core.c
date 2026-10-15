/* tests/test_omni_core.c - checks Omni's C core. Built and run by test_c_core.py; exit code 0 only when every check passes. */
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "../lib/post.h"
#include "../lib/metronome.h"
#include "../lib/pace_controller.h"
#include "../lib/vibe_profiles.h"
#include "../lib/speech_engine.h"
#include "../lib/generator.h"
#include "../lib/pipe.h"
#include "../lib/system_registry.h"
#include "../src/input_handler.h"

static int passed = 0, failed = 0;
#define CHECK(name, cond) do { if (cond) { passed++; printf("[PASS] %s\n", name); } else { failed++; printf("[FAIL] %s\n", name); } } while (0)

int main(void) {
    /* the message queue */
    Message m = {1, "hello"};
    CHECK("an empty queue has no message", !has_message());
    CHECK("an empty queue pops type -1", pop_message().type == -1);
    CHECK("a message is queued", post_message(m) == 1 && has_message());
    Message back = pop_message();
    CHECK("the same message comes back", back.type == 1 && strcmp(back.data, "hello") == 0);
    int queued = 0;
    for (int i = 0; i < POST_CAPACITY + 5; i++) queued += post_message(m);
    CHECK("a full queue refuses instead of overwriting", queued == POST_CAPACITY);
    post_clear();
    CHECK("clearing empties the queue", !has_message());

    /* tempo and pace */
    set_tempo(100.0f);
    CHECK("tempo is clamped to 4.0", get_tempo() == 4.0f);
    set_pace(0.0f);
    CHECK("pace is clamped to 0.25", fabs(get_current_pace() - 0.25) < 1e-6);
    set_pace(2.0f);
    CHECK("a normal pace is kept", get_current_pace() == 2.0f);
    unsigned long t0 = metronome_ticks();
    metronome_tick();
    CHECK("the metronome counts", metronome_ticks() == t0 + 1);

    /* mode files */
    VibeProfile p;
    CHECK("a real mode file loads", load_vibe_profile("bank/performance_modes/rap.json", &p) && strcmp(p.mode_name, "rap") == 0 && p.tempo == 95);
    CHECK("a missing file is refused", !load_vibe_profile("bank/performance_modes/nope.json", &p));
    CHECK("a file without a mode is refused", !load_vibe_profile("bank/performance_modes/corporate.json", &p));

    /* the speech plan matches voice.py: rate = (bpm - 85) / 6 */
    VibeProfile rap = {"rap", 95, "", ""}, poetry = {"poetry", 55, "", ""};
    SpeechPlan a = make_speech_plan("one two three four five six", &rap), b = make_speech_plan("one two three four five six", &poetry);
    CHECK("words are counted", a.words == 6);
    CHECK("rap rate is +1 and poetry rate is -5", a.rate == 1 && b.rate == -5);
    CHECK("slow poetry takes longer than rap", b.seconds > a.seconds);

    /* routing */
    system_registry_init();
    Message speech = {1, "say this"};
    CHECK("pipe A hands a message to the speech engine and records a hit", pipe_stream_data(PIPE_A, speech, &rap) == 1 && registry_success_count() == 1);
    CHECK("pipe B only updates the registry", pipe_stream_data(PIPE_B, speech, &rap) == 1 && registry_success_count() == 1);

    /* the generator */
    char out[64];
    CHECK("a commercial hook is built", generate_content("Fresh ideas", "commercial", out, sizeof out) > 0 && strcmp(out, "[HOOK]: Fresh ideas") == 0);
    CHECK("an unknown genre is refused", generate_content("x", "opera", out, sizeof out) == 0);
    CHECK("a too-small buffer is refused, not overrun", generate_content("a very long brief indeed", "psa", out, 8) == 0);

    /* the input handler never deletes anything */
    process_user_input("let's build the thing");
    CHECK("'let's build' enters factory mode", current_state == FACTORY_MODE);
    process_user_input("");

    printf("\n%d/%d passed\n", passed, passed + failed);
    return failed ? 1 : 0;
}
