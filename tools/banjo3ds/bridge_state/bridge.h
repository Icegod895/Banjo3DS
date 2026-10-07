#ifndef BANJO_BRIDGE_STATE_H
#define BANJO_BRIDGE_STATE_H
#include "../world_query/segment.h"
/* Isolated static SM contract. Reset only on creation of a fresh map/actor.
 * Actor tick schedules mesh transforms; mesh tick publishes them. Queries
 * between those phases still see the preceding committed vertex geometry. */
#define BRIDGE_REQUIRED_ABILITIES UINT32_C(0x9db1)
typedef struct {
    float offset, elapsed;
    int16_t applied;
    uint8_t pending, completed;
} BridgeMesh;
typedef struct {
    BridgeMesh mesh[3]; /* 497, 498, 499 */
    uint8_t initialized, alive;
} BridgeState;
/* Base is first: only the isolated bridge query build accepts this container.
 * No packet/vertex copy: both packet blocks and state are borrowed. */
typedef struct { BqModel base; const BridgeState *state; } BridgeModel;
void bridge_init(BridgeState *);
void bridge_actor_tick(BridgeState *, uint32_t learned);
void bridge_mesh_tick(BridgeState *, float dt);
int16_t bridge_component(const BqModel *, unsigned vertex, unsigned axis);
int bridge_model_open(BridgeModel *, const uint8_t *, size_t, const BridgeState *);
#endif
