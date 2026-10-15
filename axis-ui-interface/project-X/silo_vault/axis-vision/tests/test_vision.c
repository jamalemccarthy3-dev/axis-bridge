/* tests/test_vision.c - axis-vision's input and validation logic. */
#include <stdio.h>
#include <string.h>
#include "../src/vision_logic.h"

static int passed = 0, failed = 0;
#define CHECK(name, cond) do { if (cond) { passed++; printf("[PASS] %s\n", name); } else { failed++; printf("[FAIL] %s\n", name); } } while (0)

int main(void) {
    char a[] = "   hello    big   world  ";
    process_input(a);
    CHECK("whitespace is trimmed and collapsed in place", strcmp(a, "hello big world") == 0);
    CHECK("everyday words read as plain", last_complexity_level() == 1);
    char b[] = "orchestration infrastructure serialization";
    process_input(b);
    CHECK("long technical words read as technical", last_complexity_level() == 2);
    char e[] = "";
    process_input(e);
    process_input(NULL);
    CHECK("empty and NULL input do not crash", 1);
    CHECK("balanced structure is valid", validate_structural_integrity("{\"a\": [1, (2)], \"b\": \"}\"}") == 1);
    CHECK("an unclosed bracket is invalid", validate_structural_integrity("{\"a\": [1, 2}") == 0);
    CHECK("a stray closer is invalid", validate_structural_integrity("]") == 0);
    CHECK("an unterminated string is invalid", validate_structural_integrity("{\"a") == 0);
    CHECK("empty and NULL are invalid", validate_structural_integrity("") == 0 && validate_structural_integrity(NULL) == 0);
    printf("\n%d/%d passed\n", passed, passed + failed);
    return failed ? 1 : 0;
}
