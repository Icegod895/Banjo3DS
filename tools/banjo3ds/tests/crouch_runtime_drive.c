#include "player_crouch.h"
#include "player_ground.h"
#include <string.h>

static PlayerGroundState ground_state;
static BqFloorBridge ground_clock;
static int ground_ready;

static void observe(void *context, const float xyz[3]) {
    (void)context;
    (void)xyz;
}

void crouch_host_reset(PlayerRuntime *player) {
    playerGroundInit(&ground_state, &player->motion);
    memset(&ground_clock, 0, sizeof ground_clock);
    ground_ready = 1;
}

void crouch_host_set_floor(float height) {
    ground_state.phase.floor_height = height;
}

/* Body resolution is stubbed by the test link. This step still runs the
 * installed crouch hook, horizontal response and the yaw write. */
unsigned crouch_host_step(PlayerRuntime *player, float magnitude, float stick_yaw, float dt,
                          int jump, const FloorVertex *vertices, const FloorTriangle *triangles,
                          size_t count) {
    int status = 0;
    PlayerGroundContext ctx;
    if (!player) return 0;
    if (!ground_ready) crouch_host_reset(player);
    memset(&ctx, 0, sizeof ctx);
    ctx.state = &ground_state;
    ctx.floor = &ground_clock;
    ctx.observe = observe;
    ctx.vertices = vertices;
    ctx.triangles = triangles;
    ctx.count = count;
    ctx.query_status = &status;
    player->horizontal.intent.magnitude = magnitude;
    player->horizontal.intent.desired_yaw = stick_yaw;
    return playerGroundStep(&ctx, &player->motion, &player->horizontal, dt, jump ? true : false, false);
}

int bp_frame_resolve(const BpFrameContext *context, BgFrame *frame, uint32_t identity) {
    (void)context;
    (void)frame;
    (void)identity;
    return 1;
}
