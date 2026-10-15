#include <ctype.h>
#include <stdio.h>
#include <string.h>
#include "vision_logic.h"
#include "universal_port.h" // Only INCLUDE, do not DEFINE port logic here

// This file ONLY contains vision-specific logic.
// All Port logic is safely handled by universal_port.c

static int last_level = 1;

int last_complexity_level(void) { return last_level; }

void process_input(char* input_data) {
    if (!input_data) return;
    char* w = input_data;
    int in_space = 1, words = 0, letters = 0;
    for (const char* r = input_data; *r; r++) {
        if (isspace((unsigned char)*r)) {
            in_space = 1;
        } else {
            if (in_space && w != input_data) *w++ = ' ';
            if (in_space) words++;
            in_space = 0;
            *w++ = *r;
            letters++;
        }
    }
    *w = '\0';
    // long words on average read as technical wording
    last_level = (words > 0 && letters / words >= 7) ? 2 : 1;
}

int validate_structural_integrity(void* build_data) {
    const char* s = (const char*)build_data;
    if (!s || !*s) return 0;
    char stack[64];
    int depth = 0, in_string = 0;
    for (; *s; s++) {
        if (in_string) {
            if (*s == '\\' && s[1]) s++;
            else if (*s == '"') in_string = 0;
            continue;
        }
        if (*s == '"') { in_string = 1; continue; }
        if (*s == '{' || *s == '[' || *s == '(') {
            if (depth == (int)sizeof stack) return 0;
            stack[depth++] = *s;
        } else if (*s == '}' || *s == ']' || *s == ')') {
            if (depth == 0) return 0;
            char open = stack[--depth];
            if ((*s == '}' && open != '{') || (*s == ']' && open != '[') || (*s == ')' && open != '(')) return 0;
        }
    }
    return depth == 0 && !in_string;
}

void provide_user_feedback(int complexity_level) {
    if (complexity_level >= 2) printf("[Vision] Technical view: full detail, exact terms.\n");
    else printf("[Vision] Plain view: short sentences, everyday words.\n");
}

void process_visual_input(char* input_data) {
    process_input(input_data);
    provide_user_feedback(last_level);
}

void render_sovereign_view(void) {
    printf("[Vision] Sovereign view rendered (text mode).\n");
}
