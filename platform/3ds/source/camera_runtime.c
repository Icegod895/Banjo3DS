#include "camera_runtime.h"
#include "../../../tools/banjo3ds/bridge_state/movement_overlay.h"
#include <assert.h>
#include <math.h>
#include <string.h>

bool cameraRareView(const BanjoCamera *s,float out[4][4],RendererWindingParity *parity) {
    if(!s || !out || !parity)return false;
    for(int i=0;i<3;i++)if(!isfinite(s->position[i]) || !isfinite(s->rotation[i]) || !isfinite(s->focus[i]))return false;
    float y=s->rotation[1]*0.017453292519943295f,p=s->rotation[0]*0.017453292519943295f;
    float sy=sinf(y),cy=cosf(y),sp=sinf(p),cp=cosf(p);
    /* Original RH inverse yaw/pitch followed by diag(1,1,-1,1).
     * This reflection and REVERSED parity must remain one boundary. */
    float v[4][4]={{cy,0,-sy,0},{sp*sy,cp,sp*cy,0},
                  {-cp*sy,sp,-cp*cy,0},{0,0,0,1}};
    for(int i=0;i<3;i++)v[i][3]=-(v[i][0]*s->position[0]+v[i][1]*s->position[1]+v[i][2]*s->position[2]);
    for(int i=0;i<4;i++)for(int j=0;j<4;j++)if(!isfinite(v[i][j]))return false;
    memcpy(out,v,sizeof(v));*parity=RENDERER_WINDING_REVERSED;return true;
}
float cameraMovementYaw(const BanjoCamera *s) {
    /* Existing movementDirection expects debug yaw: forward=(-sin(y),cos(y)).
     * Rare RH camera forward in world XZ is (-sin(y),-cos(y)). */
    return 180.0f-s->rotation[1];
}
void cameraMovementInput(const BanjoCamera *s,bool debug,float debug_yaw,
    float pad_x,float pad_y,float input[3]) {
    /* 180-yaw matches Rare forward but negates Rare right=(cos(yaw),-sin(yaw)).
     * Reflect the input basis here, not the view, physics or hardware calibration. */
    input[0]=debug?pad_x:-pad_x;
    input[1]=pad_y;
    input[2]=debug?debug_yaw:cameraMovementYaw(s);
}
int cameraViFrames(uint32_t current,uint32_t previous) {
    uint32_t elapsed=current-previous;
    return elapsed<1?1:elapsed>15?15:(int)elapsed;
}
bool cameraRuntimeInit(CameraRuntime *s,const PlayerRuntime *player,
    const uint8_t *opa,size_t opa_size,const uint8_t *xlu,size_t xlu_size,
    const BzData *zones) {
    if(!s || !player || !zones || !zones->triggers || !zones->groups || !zones->nodes
       || zones->group_count!=27 || zones->node_count!=43)return false;
    memset(s,0,sizeof(*s));s->status=CAMERA_RUNTIME_INVALID;
    bridge_init(&s->world_bridge);
    playerGroundInit(&s->player_ground,&player->motion);
    if(bridge_model_open(&s->opa,opa,opa_size,&s->world_bridge)!=1 ||
       bridge_model_open(&s->xlu,xlu,xlu_size,&s->world_bridge)!=1 ||
       s->opa.base.role!=0 || s->xlu.base.role!=1)return false;
    s->zone_data=zones;s->manual_enabled=0x23;
    if(bq_bridge_init(&s->bridge,0)!=1)return false;
    banjo_camera_math_init(&s->math);
    const MovementActor *a=&player->motion.actor;
    BanjoCameraInput in={{a->x,a->y,a->z},a->y,a->yaw,a->y,0,1,player->motion.grounded};
    const float eye[3]={a->x,a->y+375,a->z-850},rotation[3]={340,180,0};
    /* Explicit B.9 bootstrap seed, not a published floor_getXPosition result. */
    bm_init(&s->manual,&s->math,&in,eye,rotation);
    if(!cameraRareView(&s->manual.camera,s->view,&s->parity))return false;
    s->initialized=true;s->status=CAMERA_RUNTIME_WAIT;return true;
}
static void candidate(void *context,const float xyz[3]) {
    CameraRuntime *s=context;
    ++s->candidate_calls;
    /* One physics candidate. E.2 owns the subsequent 1..5 floor queries. */
    assert(s->candidate_calls==1);
    memcpy(s->pre_candidate,xyz,sizeof(s->pre_candidate));
    if(s->candidate_calls!=1)s->status=CAMERA_RUNTIME_INVALID;
}
static int cameraRuntimeMoveQueries(CameraRuntime *s,PlayerRuntime *player,
    float x,float y,float yaw,float dt,int vi,bool jump,bool camera_mode,
    const FloorVertex *vertices,const FloorTriangle *triangles,size_t count) {
    if(!s || !s->initialized || !player || !isfinite(dt) || dt<0 || dt>.05f
       || !isfinite(x) || !isfinite(y) || !isfinite(yaw) || vi<1 || vi>15)return CAMERA_RUNTIME_INVALID;
    s->candidate_calls=0;s->status=CAMERA_RUNTIME_OK;
    if(bq_bridge_begin(&s->bridge)!=1)return s->status=CAMERA_RUNTIME_INVALID;
    /* Borrow committed geometry before mesh publication, exactly like B3Q1.
     * No alternate BridgeState, copied collision buffer or final-position call. */
    const MovementOverlay overlay=bridge_movement_overlay(&s->world_bridge);
    PlayerGroundContext ground={&s->player_ground,&s->bridge,candidate,s,
        vertices,triangles,count,&overlay,&s->status,&s->body,
        &s->query_scratch.player,&s->opa,&s->xlu,&s->math};
    playerRuntimeMoveStepped(player,x,y,yaw,dt,jump,camera_mode,vertices,triangles,count,
        candidate,s,&overlay,playerGroundStep,&ground);
    assert(s->candidate_calls==(dt>0?1u:0u));
    if(s->candidate_calls!=(dt>0?1u:0u))s->status=CAMERA_RUNTIME_INVALID;
    if(dt>0 && s->status==CAMERA_RUNTIME_OK) {
        assert(s->bridge.next_ordinal>=1 && s->bridge.next_ordinal<=5);
        if(s->bridge.next_ordinal<1 || s->bridge.next_ordinal>5)s->status=CAMERA_RUNTIME_INVALID;
        else s->floor_ready=true;
    }
    if((player->events&BANJO_JUMP_RECOVERED) && s->status==CAMERA_RUNTIME_OK) {
        /* B.9 diagnostic relocation event: reinit preserves history and clock.
         * This is not a collision-contact/final-position replay. */
        const float relocated[3]={player->motion.actor.x,player->motion.actor.y,player->motion.actor.z};
        if(bq_bridge_reinit(&s->bridge)!=1 ||
           bridge_cadence_candidate(&s->bridge,&s->opa.base,&s->xlu.base,relocated,s->bridge.next_ordinal)!=1)
            s->status=CAMERA_RUNTIME_QUERY_FAILED;
        if(s->status==CAMERA_RUNTIME_OK) {
            memcpy(s->player_ground.phase.position,relocated,sizeof(relocated));
            s->player_ground.phase.floor_height=s->bridge.floor.height;
            s->player_ground.phase.vertical_velocity=player->motion.verticalVelocity;
            s->player_ground.phase.grounded=player->motion.grounded;
        }
    }
    if(bq_bridge_end(&s->bridge)!=1)return s->status=CAMERA_RUNTIME_INVALID;
    if(s->status!=CAMERA_RUNTIME_OK)return s->status;
    if(!s->floor_ready)return s->status=CAMERA_RUNTIME_WAIT;
    float under;
    if(bridge_camera_terrain(&s->opa.base,&s->xlu.base,s->manual.camera.position,&under)<0)
        return s->status=CAMERA_RUNTIME_QUERY_FAILED;
    const MovementActor *a=&player->motion.actor;
    BanjoCameraInput in={{a->x,a->y,a->z},s->bridge.floor.height,a->yaw,under,dt,vi,player->motion.grounded};
    /* Original code_7060.c:430 -> code_C4B0.c:248/260: normal Banjo's
     * collider center is +80Y. Stand/gaits/ordinary jump do not change it.
     * This is not camera focus/lead and does not add player-volume physics. */
    const float target[3]={a->x,a->y+80.0f,a->z};
    return cameraRuntimeUpdateView(s,&in,target);
}
void cameraRuntimeSetLearnedAbilities(CameraRuntime *s,uint32_t bits) {
    if(s)s->learned_abilities=bits;
}
int cameraRuntimeMove(CameraRuntime *s,PlayerRuntime *player,
    float x,float y,float yaw,float dt,int vi,bool jump,bool camera_mode,
    const FloorVertex *vertices,const FloorTriangle *triangles,size_t count) {
    if(!s || !s->initialized || !player || !isfinite(dt) || dt<0 || dt>.05f
       || !isfinite(x) || !isfinite(y) || !isfinite(yaw) || vi<1 || vi>15)return CAMERA_RUNTIME_INVALID;
    /* Original actor -> player/camera queries -> mesh publication ordering.
     * Even a bounded unsupported camera zone does not cancel the world tick. */
    bridge_actor_tick(&s->world_bridge,s->learned_abilities);
    int status=cameraRuntimeMoveQueries(s,player,x,y,yaw,dt,vi,jump,camera_mode,vertices,triangles,count);
    bridge_mesh_tick(&s->world_bridge,dt);
    return status;
}
int cameraRuntimeUpdateView(CameraRuntime *s,const BanjoCameraInput *in,const float target[3]) {
    if(!s || !s->initialized || !in || !target)return CAMERA_RUNTIME_INVALID;
    BmState next=s->manual;
    BmTrace trace;
    if(!bm_update(&next,&s->math,s->zone_data,in,s->manual_buttons,s->manual_enabled,
                  &s->opa.base,&s->xlu.base,target,&s->query_scratch.camera,&trace)) {
        /* Classify unsupported data without running another camera/contact update.
         * Ordinary misses remain successful world-query results. */
        const float *probe=in->stable?in->player:s->manual.camera.stable_position;
        for(int i=0;i<3;i++)if(!isfinite(probe[i]) || fabsf(probe[i])>20000)
            return s->status=CAMERA_RUNTIME_INVALID;
        BzState lookup=s->manual.zones;
        int n=bz_select(&lookup,s->zone_data,probe);
        if(n>=0) {
            if((size_t)n>=s->zone_data->node_count)return s->status=CAMERA_RUNTIME_UNSUPPORTED;
            const BzNode *node=s->zone_data->nodes+n;
            if(!((node->type==3 && !(node->zoom.flags&1)) ||
                 (node->type==4 && node->profile==1)))return s->status=CAMERA_RUNTIME_UNSUPPORTED;
        }
        return s->status=CAMERA_RUNTIME_QUERY_FAILED;
    }
    float view[4][4];RendererWindingParity parity;
    /* Render and SORT use the viewport, not the potentially ahead-of-transition
     * internal camera. Keep RH->LH/parity conversion at the existing boundary. */
    BanjoCamera visible=next.camera;
    memcpy(visible.position,next.viewport_position,sizeof(visible.position));
    memcpy(visible.rotation,next.viewport_rotation,sizeof(visible.rotation));
    if(!cameraRareView(&visible,view,&parity))return s->status=CAMERA_RUNTIME_INVALID;
    s->manual=next;memcpy(s->view,view,sizeof(view));s->parity=parity;
    s->view_ready=true;return s->status=CAMERA_RUNTIME_OK;
}

void cameraRuntimeManualInput(CameraRuntime *s,uint32_t buttons,uint32_t enabled) {
    if(s){s->manual_buttons=buttons;s->manual_enabled=enabled;}
}
void cameraRuntimeMovementInput(const CameraRuntime *s,bool debug,float debug_yaw,
    float pad_x,float pad_y,float input[3]) {
    BanjoCamera visible={0};
    memcpy(visible.rotation,s->manual.viewport_rotation,sizeof(visible.rotation));
    cameraMovementInput(&visible,debug,debug_yaw,pad_x,pad_y,input);
}
