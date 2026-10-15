#ifndef VISION_LOGIC_H
#define VISION_LOGIC_H

// Adaptive Linguistics and Constraint protocols
void process_input(char* input_data);              // trims and collapses whitespace IN PLACE and measures how technical the wording is
int validate_structural_integrity(void* build_data); // build_data is a NUL-terminated text; 1 when brackets and quotes are balanced and it is not empty, else 0
void provide_user_feedback(int complexity_level);  // 1 = Layman, 2 = Tech: prints the matching explanation level
int last_complexity_level(void);                   // what process_input decided (1 = Layman, 2 = Tech)

void process_visual_input(char* input_data);
void render_sovereign_view(void);

#endif
