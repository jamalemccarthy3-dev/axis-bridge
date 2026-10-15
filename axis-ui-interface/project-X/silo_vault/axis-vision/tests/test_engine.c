/* tests/test_engine.c - axis-vision's viewport, hardware handshake, mesh, texture reader and research engine. Run with the folder for scratch files as argument 1. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "../src/engine_core.h"
#include "../src/research_engine.h"
#include "../src/universal_port.h"

static int passed = 0, failed = 0;
#define CHECK(name, cond) do { if (cond) { passed++; } else { failed++; printf("[FAIL] %s\n", name); } } while (0)

static void write_bytes(const char *path, const char *data, size_t n) { FILE *f = fopen(path, "wb"); fwrite(data, 1, n, f); fclose(f); }
static int near(float a, float b) { return fabsf(a - b) < 0.001f; }

static int connected_calls = 0;
static void on_connect(void) { connected_calls++; }

int main(int argc, char **argv) {
    const char *dir = argc > 1 ? argv[1] : ".";
    char path[512];
    float u, v, p3[3], lo[3], hi[3];

    /* viewport */
    CHECK("starts dormant", current_state == STATE_DORMANT);
    initialize_360_viewport();
    CHECK("viewport state", current_state == STATE_VIEWPORT && near(viewport_yaw(), 0) && near(viewport_pitch(), 0));
    viewport_rotate(370.0f, 120.0f);
    CHECK("yaw wraps, pitch clamps", near(viewport_yaw(), 10.0f) && near(viewport_pitch(), 90.0f));
    viewport_rotate(-20.0f, -200.0f);
    CHECK("negative yaw wraps up", near(viewport_yaw(), 350.0f) && near(viewport_pitch(), -90.0f));
    viewport_rotate(NAN, 0);
    CHECK("NaN rotation ignored", near(viewport_yaw(), 350.0f));
    initialize_360_viewport();
    CHECK("straight ahead is the centre", viewport_project(0, 0, 5, &u, &v) && near(u, 0.5f) && near(v, 0.5f));
    CHECK("right of centre", viewport_project(5, 0, 0, &u, &v) && near(u, 0.75f));
    CHECK("above centre", viewport_project(0, 5, 0, &u, &v) && near(v, 0.0f));
    viewport_rotate(90.0f, 0);
    CHECK("turning right brings the right-hand point to the centre", viewport_project(5, 0, 0, &u, &v) && near(u, 0.5f));
    CHECK("origin has no direction", viewport_project(0, 0, 0, &u, &v) == 0);

    /* hardware */
    UMP_init(on_connect, NULL);
    CHECK("bad ids refused", execute_hardware_handshake("") == 0 && execute_hardware_handshake("a b") == 0 && execute_hardware_handshake(NULL) == 0 &&
          execute_hardware_handshake("../etc") == 0 && current_state == STATE_VIEWPORT && !UMP_is_active());
    CHECK("good id accepted", execute_hardware_handshake("lidar-01.A") == 1 && current_state == STATE_CONNECTED && strcmp(hardware_connected_id(), "lidar-01.A") == 0);
    CHECK("the universal port was told", UMP_is_active() && connected_calls == 1);

    /* mesh */
    CHECK("empty mesh has no bounds", mesh_vertex_count() == 0 && mesh_bounds(lo, hi) == 0);
    CHECK("vertices get indexes", update_geometry_mesh(1, 2, 3) == 0 && update_geometry_mesh(-1, 5, 0) == 1);
    CHECK("bad numbers refused", update_geometry_mesh(NAN, 0, 0) == -1 && update_geometry_mesh(0, INFINITY, 0) == -1 && mesh_vertex_count() == 2);
    CHECK("vertex read back", mesh_vertex(1, p3) && near(p3[0], -1) && near(p3[1], 5) && !mesh_vertex(2, p3) && !mesh_vertex(-1, p3));
    CHECK("bounds", mesh_bounds(lo, hi) && near(lo[0], -1) && near(hi[0], 1) && near(lo[2], 0) && near(hi[1], 5));
    mesh_clear();
    CHECK("mesh capacity", mesh_vertex_count() == 0);
    {
        int i, last = 0;
        for (i = 0; i < MESH_MAX_VERTICES; i++) last = update_geometry_mesh((float)i, 0, 0);
        CHECK("full mesh refuses more", last == MESH_MAX_VERTICES - 1 && update_geometry_mesh(0, 0, 0) == -1);
        mesh_clear();
    }

    /* texture */
    snprintf(path, sizeof path, "%s/a.ppm", dir);
    {
        const char img[] = "P6\n# a comment\n2 1\n255\n\x00\x00\x00\xff\xff\xff";
        write_bytes(path, img, sizeof img - 1);
        CHECK("ppm read", apply_surface_texture(path) == 1 && texture_width() == 2 && texture_height() == 1 && near(texture_mean_brightness(), 127.5f));
        snprintf(path, sizeof path, "%s/b.pgm", dir);
        write_bytes(path, "P5\n2 2\n255\n\x0a\x14\x1e\x28", 15);
        CHECK("pgm read", apply_surface_texture(path) == 1 && texture_width() == 2 && texture_height() == 2 && near(texture_mean_brightness(), 25.0f));
        write_bytes(path, "P5\n2 2\n255\n\x0a\x14", 13);
        CHECK("short pixel data refused", apply_surface_texture(path) == 0 && texture_width() == 2);   /* the earlier texture stays */
        write_bytes(path, "P3\n1 1\n255\n0 0 0\n", 17);
        CHECK("text ppm refused", apply_surface_texture(path) == 0);
        CHECK("missing file refused", apply_surface_texture("no/such.ppm") == 0 && apply_surface_texture(NULL) == 0);
    }

    /* research */
    {
        ResearchHit hits[4];
        int n;
        research_init();
        CHECK("empty index", research_count() == 0 && research_search("anything", hits, 4) == 0);
        CHECK("add", research_add("tides", "The tide rises and the tide falls twice a day.") && research_add("orbit", "Satellites orbit the earth.") && research_count() == 2);
        CHECK("bad adds", !research_add("", "x") && !research_add("x", "") && !research_add(NULL, "x"));
        n = research_search("TIDE?", hits, 4);
        CHECK("case and punctuation ignored", n == 1 && strcmp(hits[0].doc_id, "tides") == 0 && hits[0].score == 2);
        research_add("tide-notes", "tide tables");
        n = research_search("tide", hits, 4);
        CHECK("best first", n == 2 && strcmp(hits[0].doc_id, "tides") == 0 && strcmp(hits[1].doc_id, "tide-notes") == 0 && hits[1].score == 2);   /* text 1 + id 1 */
        CHECK("no match", research_search("volcano", hits, 4) == 0);
        CHECK("max_hits respected", research_search("tide", hits, 1) == 1);
        research_add("orbit", "Satellites orbit the moon too.");
        CHECK("same id replaces", research_count() == 3 && research_search("moon", hits, 4) == 1);
        research_query("orbit");
    }

    printf("%d/%d passed\n", passed, passed + failed);
    return failed ? 1 : 0;
}
