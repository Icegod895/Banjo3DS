#include "movement.h"
#include <math.h>

static const float radians = 0.017453292519943295f;

float movementDelta(uint64_t now, uint64_t previous)
{
    return now < previous ? 0.0f : fminf((now - previous) * 0.001f, 0.05f);
}

void movementNormalize(float x, float y, float out[2])
{
    float radius = sqrtf(x*x + y*y);
    out[0] = out[1] = 0.0f;
    if (radius <= MOVEMENT_DEADZONE) return;
    float strength = fminf((radius - MOVEMENT_DEADZONE) /
                          (MOVEMENT_NOMINAL_MAXIMUM - MOVEMENT_DEADZONE), 1.0f);
    out[0] = x / radius * strength;
    out[1] = y / radius * strength;
}

void movementDirection(float x, float y, float cameraYaw, float out[2])
{
    float c = cosf(cameraYaw * radians), s = sinf(cameraYaw * radians);
    out[0] = c*x - s*y;
    out[1] = s*x + c*y;
}

bool movementFloor(const FloorVertex *vertices, const FloorTriangle *triangles,
                   size_t count, float x, float z, float previousY, float *height)
{
    bool found = false;
    float highest = previousY - MOVEMENT_STEP;
    for (size_t i = 0; i < count; ++i) {
        const FloorTriangle *t = &triangles[i];
        if (t->flags & MOVEMENT_FLOOR_FILTER) continue;
        const FloorVertex *a = &vertices[t->a], *b = &vertices[t->b], *c = &vertices[t->c];
        float ux = b->x-a->x, uy = b->y-a->y, uz = b->z-a->z;
        float vx = c->x-a->x, vy = c->y-a->y, vz = c->z-a->z;
        float nx = uy*vz-uz*vy, ny = uz*vx-ux*vz, nz = ux*vy-uy*vx;
        float length = sqrtf(nx*nx + ny*ny + nz*nz);
        if (length == 0.0f) continue;
        /* Original 0x10000 allows a downward ray to hit the reverse side. */
        float normalY = (t->flags & 0x10000u) ? fabsf(ny) : ny;
        if (normalY < MOVEMENT_MIN_NORMAL_Y * length) continue;
        float det = ux*vz-uz*vx;
        float px = x-a->x, pz = z-a->z;
        float u = (px*vz-pz*vx)/det, v = (ux*pz-uz*px)/det;
        if (u < 0.0f || v < 0.0f || u+v > 1.0f) continue;
        float y = a->y + u*uy + v*vy;
        if (y < previousY-MOVEMENT_STEP || y > previousY+MOVEMENT_STEP) continue;
        if (!found || y > highest) { highest = y; found = true; }
    }
    if (found) *height = highest;
    return found;
}

bool movementUpdate(MovementActor *actor, float padX, float padY, float cameraYaw,
                    float dt, bool cameraMode, const FloorVertex *vertices,
                    const FloorTriangle *triangles, size_t count)
{
    float stick[2], direction[2], floor;
    if (cameraMode || dt <= 0.0f) return false;
    movementNormalize(padX, padY, stick);
    if (stick[0] == 0.0f && stick[1] == 0.0f) return false;
    movementDirection(stick[0], stick[1], cameraYaw, direction);
    dt = fminf(dt, 0.05f);
    float x = actor->x + direction[0]*MOVEMENT_SPEED*dt;
    float z = actor->z + direction[1]*MOVEMENT_SPEED*dt;
    if (!movementFloor(vertices, triangles, count, x, z, actor->y, &floor)) return false;
    /* Commit all position/heading state together, only after a valid floor. */
    actor->x = x; actor->y = floor; actor->z = z;
    actor->yaw = atan2f(direction[0], direction[1]) / radians;
    return true;
}

void movementActorMatrix(const MovementActor *a, float rows[4][4])
{
    float c = cosf(a->yaw*radians), s = sinf(a->yaw*radians);
    float m[4][4] = {{c,0,s,a->x}, {0,1,0,a->y}, {-s,0,c,a->z}, {0,0,0,1}};
    for (int i=0;i<4;i++) for (int j=0;j<4;j++) rows[i][j]=m[i][j];
}
