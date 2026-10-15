#include "engine_core.h"
#include "universal_port.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int current_state = STATE_DORMANT;

static float view_yaw = 0.0f, view_pitch = 0.0f;
static char hardware_id_stored[64] = "";
static float vertices[MESH_MAX_VERTICES][3];
static int vertex_count = 0;
static int tex_w = 0, tex_h = 0;
static float tex_mean = 0.0f;

static int finite_number(float v) { return isfinite(v); }

/* ---- viewport ---- */
void initialize_360_viewport() {
    view_yaw = 0.0f;
    view_pitch = 0.0f;
    if (current_state == STATE_DORMANT) current_state = STATE_VIEWPORT;
}

void viewport_rotate(float d_yaw, float d_pitch) {
    if (!finite_number(d_yaw) || !finite_number(d_pitch)) return;
    view_yaw = fmodf(view_yaw + d_yaw, 360.0f);
    if (view_yaw < 0.0f) view_yaw += 360.0f;
    view_pitch += d_pitch;
    if (view_pitch > 90.0f) view_pitch = 90.0f;
    if (view_pitch < -90.0f) view_pitch = -90.0f;
}

float viewport_yaw(void) { return view_yaw; }
float viewport_pitch(void) { return view_pitch; }

int viewport_project(float x, float y, float z, float *u, float *v) {
    const float pi = 3.14159265358979f;
    float len = sqrtf(x * x + y * y + z * z), az, el;
    if (!finite_number(len) || len == 0.0f) return 0;
    az = atan2f(x, z) * 180.0f / pi - view_yaw;        /* degrees to the right of the line of sight */
    el = asinf(y / len) * 180.0f / pi - view_pitch;
    az = fmodf(az, 360.0f);
    if (az > 180.0f) az -= 360.0f;
    if (az < -180.0f) az += 360.0f;
    if (el > 90.0f) el = 90.0f;
    if (el < -90.0f) el = -90.0f;
    if (u) *u = 0.5f + az / 360.0f;
    if (v) *v = 0.5f - el / 180.0f;
    return 1;
}

/* ---- hardware ---- */
int execute_hardware_handshake(char* hardware_id) {
    size_t i, n;
    if (hardware_id == NULL) return 0;
    n = strlen(hardware_id);
    if (n == 0 || n > 63) return 0;
    for (i = 0; i < n; i++) {
        char c = hardware_id[i];
        int ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.';
        if (!ok) return 0;
    }
    memcpy(hardware_id_stored, hardware_id, n + 1);
    current_state = STATE_CONNECTED;
    UMP_notify_connection(true);
    return 1;
}

const char *hardware_connected_id(void) { return hardware_id_stored; }

/* ---- mesh ---- */
int update_geometry_mesh(float x, float y, float z) {
    if (!finite_number(x) || !finite_number(y) || !finite_number(z) || vertex_count >= MESH_MAX_VERTICES) return -1;
    vertices[vertex_count][0] = x;
    vertices[vertex_count][1] = y;
    vertices[vertex_count][2] = z;
    return vertex_count++;
}

int mesh_vertex_count(void) { return vertex_count; }

int mesh_vertex(int index, float out[3]) {
    if (index < 0 || index >= vertex_count) return 0;
    memcpy(out, vertices[index], sizeof vertices[index]);
    return 1;
}

int mesh_bounds(float lo[3], float hi[3]) {
    int i, k;
    if (vertex_count == 0) return 0;
    for (k = 0; k < 3; k++) lo[k] = hi[k] = vertices[0][k];
    for (i = 1; i < vertex_count; i++)
        for (k = 0; k < 3; k++) {
            if (vertices[i][k] < lo[k]) lo[k] = vertices[i][k];
            if (vertices[i][k] > hi[k]) hi[k] = vertices[i][k];
        }
    return 1;
}

void mesh_clear(void) { vertex_count = 0; }

/* ---- texture ---- */
static int read_header_int(FILE *fp, int *out) {
    int c, v = 0, digits = 0;
    for (;;) {                                           /* skip blanks and # comments */
        c = fgetc(fp);
        if (c == '#') { while (c != '\n' && c != EOF) c = fgetc(fp); continue; }
        if (c == ' ' || c == '\t' || c == '\n' || c == '\r') continue;
        break;
    }
    while (c >= '0' && c <= '9') {
        v = v * 10 + (c - '0');
        if (v > 100000) return 0;
        digits++;
        c = fgetc(fp);
    }
    if (digits == 0) return 0;                           /* the one whitespace byte after the number has been consumed */
    *out = v;
    return 1;
}

int apply_surface_texture(char* texture_map_path) {
    FILE *fp;
    int w, h, maxv, channels;
    char magic[3] = {0};
    unsigned long long sum = 0, count, i;
    if (texture_map_path == NULL) return 0;
    fp = fopen(texture_map_path, "rb");
    if (fp == NULL) return 0;
    if (fread(magic, 1, 2, fp) != 2 || magic[0] != 'P' || (magic[1] != '5' && magic[1] != '6')) { fclose(fp); return 0; }
    channels = magic[1] == '6' ? 3 : 1;
    if (!read_header_int(fp, &w) || !read_header_int(fp, &h) || !read_header_int(fp, &maxv) || w <= 0 || h <= 0 || maxv != 255) { fclose(fp); return 0; }
    count = (unsigned long long)w * (unsigned long long)h * (unsigned long long)channels;
    for (i = 0; i < count; i++) {
        int c = fgetc(fp);
        if (c == EOF) { fclose(fp); return 0; }          /* the pixel data is shorter than the header promises */
        sum += (unsigned)c;
    }
    fclose(fp);
    tex_w = w;
    tex_h = h;
    tex_mean = (float)((double)sum / (double)count);
    return 1;
}

int texture_width(void) { return tex_w; }
int texture_height(void) { return tex_h; }
float texture_mean_brightness(void) { return tex_mean; }
