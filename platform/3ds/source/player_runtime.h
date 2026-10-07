#ifndef BANJO_PLAYER_RUNTIME_H
#define BANJO_PLAYER_RUNTIME_H
#include "jump.h"
#include "jump_animation.h"
#include "gait_motion.h"
/* Thin integration of the proven movement/gait/jump modules, no new physics.
 * Separate controller storage makes both handoffs explicit, without aliasing. */
typedef struct {
    BanjoJumpMotion motion;
    BanjoGaitState gait;
    BanjoJumpAnimation jump;
    unsigned events;
    float speed;
    bool accepted, jumpActive;
    BanjoHorizontal horizontal;
    BanjoHorizontalMetrics metrics;
    BanjoGaitMotion locomotion;
    bool horizontalInitialized;
} PlayerRuntime;
/* Initialize motion.actor and motion.grounded; zero all remaining fields. */
void playerRuntimeMove(PlayerRuntime *s, float x, float y, float cameraYaw, float dt,
                       bool jumpPressed, bool cameraMode, const FloorVertex *vertices,
                       const FloorTriangle *triangles, size_t count);
void playerRuntimeMoveObserved(PlayerRuntime *s, float x, float y, float cameraYaw, float dt,
                       bool jumpPressed, bool cameraMode, const FloorVertex *vertices,
                       const FloorTriangle *triangles, size_t count,
                       BanjoCandidateObserver observe, void *context);
bool playerRuntimeAnimate(PlayerRuntime *s, const uint8_t *packet, size_t size, float dt);
void playerRuntimeMoveOverlay(PlayerRuntime *,float,float,float,float,bool,bool,
    const FloorVertex *,const FloorTriangle *,size_t,BanjoCandidateObserver,void *,
    const MovementOverlay *);
/* Explicit motion phase supplied by the world runtime. The legacy entry points
 * remain historical host contracts; the live camera runtime supplies E.1. */
typedef unsigned (*PlayerMotionStep)(void *,BanjoJumpMotion *,BanjoHorizontal *,float,bool,bool);
void playerRuntimeMoveStepped(PlayerRuntime *,float,float,float,float,bool,bool,
    const FloorVertex *,const FloorTriangle *,size_t,BanjoCandidateObserver,void *,
    const MovementOverlay *,PlayerMotionStep,void *);
/* Caller waits for GPU completion, then flushes the actor range afterwards. */
bool playerRuntimeWriteVertices(const PlayerRuntime *s, const uint8_t *packet, void *vertices,
                                size_t total, size_t first, size_t count, size_t stride);
#endif
