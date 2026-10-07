#ifndef BANJO_MOVEMENT_H
#define BANJO_MOVEMENT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct { int16_t x, y, z; } FloorVertex;
typedef struct { uint16_t a, b, c; int16_t surface; uint32_t flags; } FloorTriangle;
typedef struct { float x, y, z, yaw; } MovementActor;

/* Optional sparse source-derived Y overlay. Borrows published world state;
 * no vertex buffer copy, lifecycle or physics state is owned here.
 * Binding rows sorted by movement index: {movement, source, mesh slot}. */
typedef struct {
    const uint16_t (*binding)[3];
    size_t count;
    const void *state;
    int16_t (*offset)(const void *state, unsigned slot);
} MovementOverlay;
static inline FloorVertex movementVertex(const FloorVertex *base, unsigned index,
                                         const MovementOverlay *overlay) {
    FloorVertex v=base[index];
    if(overlay && overlay->count && index>=overlay->binding[0][0] &&
       index<=overlay->binding[overlay->count-1][0]) {
        for(size_t i=0;i<overlay->count;i++)if(overlay->binding[i][0]==index) {
            v.y=(int16_t)(uint16_t)((int32_t)v.y+
                (uint16_t)overlay->offset(overlay->state,overlay->binding[i][2]));
            break;
        }
    }
    return v;
}

/* Diagnostic tuning, not guaranteed Circle Pad hardware limits. */
#define MOVEMENT_DEADZONE 20.0f
#define MOVEMENT_NOMINAL_MAXIMUM 156.0f
#define MOVEMENT_SPEED 150.0f
#define MOVEMENT_STEP 30.0f
#define MOVEMENT_MIN_NORMAL_Y 0.432f
#define MOVEMENT_FLOOR_FILTER 0x005E0000u

void movementNormalize(float x, float y, float out[2]);
void movementDirection(float x, float y, float cameraYaw, float out[2]);
float movementDelta(uint64_t now, uint64_t previous);
bool movementFloor(const FloorVertex *vertices, const FloorTriangle *triangles,
                   size_t count, float x, float z, float previousY, float *height);
/* Ground-only point-floor following from a previously confirmed position.
 * Ordered segments preserve movementFloor's +/-30/highest-valid semantics.
 * The whole candidate is rejected on any failed query; height is untouched.
 * No actor, velocity, yaw or collision data is mutated. Endpoint sampling is
 * not a continuous ground sweep and does not add wall/volume collision. */
bool movementFollowFloor(const FloorVertex *vertices, const FloorTriangle *triangles,
                         size_t count, float startX, float startY, float startZ,
                         float endX, float endZ, float *height);
bool movementUpdate(MovementActor *actor, float padX, float padY, float cameraYaw,
                    float dt, bool cameraMode, const FloorVertex *vertices,
                    const FloorTriangle *triangles, size_t count);
/* Row-major T(position) * Ry(yaw), yaw 0 faces +Z, +90 faces +X. */
void movementActorMatrix(const MovementActor *actor, float rows[4][4]);
/* Same algorithms, with the optional coordinate-read overlay. NULL is the
 * immutable legacy path; all original entry points remain available. */
bool movementFloorOverlay(const FloorVertex *,const FloorTriangle *,size_t,
    float,float,float,float *,const MovementOverlay *);
bool movementFollowFloorOverlay(const FloorVertex *,const FloorTriangle *,size_t,
    float,float,float,float,float,float *,const MovementOverlay *);
bool movementUpdateOverlay(MovementActor *,float,float,float,float,bool,
    const FloorVertex *,const FloorTriangle *,size_t,const MovementOverlay *);
#endif
