#ifndef BANJO_CAMERA_MANUAL_H
#define BANJO_CAMERA_MANUAL_H
#include "../camera_zones/zones.h"
/* Host-only NORMAL dry Banjo. Held logical N64 inputs, NOT a 3DS mapping. */
enum { BM_R=1, BM_LEFT=2, BM_RIGHT=4, BM_DOWN=8 };
typedef struct {
    BanjoCamera camera;
    BzState zones;
    BcFreeBState post;
    float r_radius,r_target,r_orbit,r_velocity;
    float c_target,c_orbit,c_step,c_radius,c_radius_step;
    float zoom_timer;
    float viewport_offset[3],viewport_angles[3],viewport_remaining,viewport_duration;
    float viewport_position[3],viewport_rotation[3];
    float radius,height,position_gain,position_response,rotation_gain,rotation_response;
    uint32_t focus_mode,c_complete,viewport_state,buttons;
} BmState;
typedef struct { BcFreeBTrace free_b; BcTrace contact; } BmTrace;
void bm_init(BmState *,const BanjoCameraMath *,const BanjoCameraInput *,const float eye[3],const float rotation[3]);
/* enabled uses original bainput bits 0,1,5; R is unaffected. Caller supplies
 * one immutable static-map view and one frame dt/VI. Atomic on query failure.
 * Snapshot internal camera and visible viewport separately. No heap. */
bool bm_update(BmState *,const BanjoCameraMath *,const BzData *,const BanjoCameraInput *,
    uint32_t buttons,uint32_t enabled,const BqModel *,const BqModel *,const float target[3],BcScratch *,BmTrace *);
/* Manual gate and recovery variants use the SAME proven primitive geometry. */
int bm_gate(const BqModel *,const BqModel *,const float from[3],const float to[3],BcScratch *,BcTrace *);
int bm_obstruction(const BqModel *,const BqModel *,float camera[3],const float target[3],
    unsigned variant,BcState *,BcScratch *,BcTrace *);
#endif
