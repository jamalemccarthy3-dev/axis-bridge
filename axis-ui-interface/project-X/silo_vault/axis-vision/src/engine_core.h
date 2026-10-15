#ifndef ENGINE_CORE_H
#define ENGINE_CORE_H

#define STATE_DORMANT 0
#define STATE_VIEWPORT 1     /* the 360 viewport exists */
#define STATE_CONNECTED 2    /* a hardware device has shaken hands */
#define MESH_MAX_VERTICES 4096
extern int current_state;

/* Core viewport and hardware interface protocols */

/* Creates the 360-degree viewport: yaw 0, pitch 0, 90-degree field of view. The state becomes STATE_VIEWPORT (or stays STATE_CONNECTED). */
void initialize_360_viewport();
/* Turns the view. Yaw wraps into [0,360); pitch is clamped to [-90,90]. */
void viewport_rotate(float d_yaw, float d_pitch);
float viewport_yaw(void);
float viewport_pitch(void);
/* Where a point in the scene lands on an equirectangular 360 image, as u,v in [0,1] (u = left to right across the full circle, 0.5 = straight ahead
   along +z when yaw is 0 and the view is centred). Returns 0 for the origin, which has no direction. */
int viewport_project(float x, float y, float z, float *u, float *v);

/* Registers a hardware device. The id must be 1..63 characters of letters, digits, '_', '-' or '.'. Returns 1 and moves to STATE_CONNECTED (telling the
   universal port), else 0 and nothing changes. */
int execute_hardware_handshake(char* hardware_id);
const char *hardware_connected_id(void);   /* "" when none */

/* Real-time additive generation: adds a vertex to the mesh. Returns its index, or -1 if a coordinate is not a finite number or the mesh is full. */
int update_geometry_mesh(float x, float y, float z);
int mesh_vertex_count(void);
int mesh_vertex(int index, float out[3]);                 /* 1 if the index exists */
int mesh_bounds(float lo[3], float hi[3]);                /* 1 if the mesh has vertices */
void mesh_clear(void);

/* Reads a binary PGM (P5) or PPM (P6) image and records its size and mean brightness (0..255). Returns 1 on success, 0 if the file is missing or is not
   a well-formed 8-bit P5/P6 image. */
int apply_surface_texture(char* texture_map_path);
int texture_width(void);
int texture_height(void);
float texture_mean_brightness(void);

#endif
