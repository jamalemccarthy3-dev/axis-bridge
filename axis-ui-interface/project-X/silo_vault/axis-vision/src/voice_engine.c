#include <stdio.h>
#include <stdbool.h>

// This keeps track if we have voice files or not
static bool voice_is_ready = false;

// This runs once when the engine starts to check for your audio files
void voice_init(void) {
    // In our flat build, it looks for the file right in the project folder
    FILE *file = fopen("audio_male.raw", "r");
   
    if (file) {
        voice_is_ready = true; // Files exist, system is ready to talk
        fclose(file);
    } else {
        voice_is_ready = false; // Files missing, system stays muted/stable
    }
}

// This is the function you call to make the module speak
void voice_speak(const char* text) {
    // Safety check: if no voices exist, just skip it and keep running
    if (!voice_is_ready) {
        return;
    }
   
    // If we have the files, we print the text (or send it to the speaker)
    printf("Speaking: %s\n", text);
}

 