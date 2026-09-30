#include "camera_runtime.h"
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
    const BanjoCameraZoom *zoom,const BanjoCameraTrigger *triggers,size_t count) {
    if(!s || !player || !zoom || !triggers || !count)return false;
    memset(s,0,sizeof(*s));s->status=CAMERA_RUNTIME_INVALID;
    if(bq_open(&s->opa,opa,opa_size)!=1 || bq_open(&s->xlu,xlu,xlu_size)!=1
       || s->opa.role!=0 || s->xlu.role!=1)return false;
    s->zoom=zoom;s->triggers=triggers;s->trigger_count=count;
    if(bq_bridge_init(&s->bridge,0)!=1)return false;
    banjo_camera_math_init(&s->math);
    const MovementActor *a=&player->motion.actor;
    BanjoCameraInput in={{a->x,a->y,a->z},a->y,a->yaw,a->y,0,1,player->motion.grounded};
    const float eye[3]={a->x,a->y+375,a->z-850},rotation[3]={340,180,0};
    /* Explicit B.9 bootstrap seed, not a published floor_getXPosition result. */
    banjo_camera_init(&s->camera,&s->math,&in,eye,rotation);
    if(!cameraRareView(&s->camera,s->view,&s->parity))return false;
    s->initialized=true;s->status=CAMERA_RUNTIME_WAIT;return true;
}
static void candidate(void *context,const float xyz[3]) {
    CameraRuntime *s=context;
    ++s->candidate_calls;
    /* B.9 permits exactly one ordinary callback, before either collision path. */
    assert(s->candidate_calls==1);
    memcpy(s->pre_candidate,xyz,sizeof(s->pre_candidate));
    if(s->candidate_calls!=1 || bq_bridge_candidate(&s->bridge,&s->opa,&s->xlu,xyz,0)!=1)
        s->status=CAMERA_RUNTIME_QUERY_FAILED;
    else s->floor_ready=true;
}
int cameraRuntimeMove(CameraRuntime *s,PlayerRuntime *player,
    float x,float y,float yaw,float dt,int vi,bool jump,bool camera_mode,
    const FloorVertex *vertices,const FloorTriangle *triangles,size_t count) {
    if(!s || !s->initialized || !player || !isfinite(dt) || dt<0 || dt>.05f
       || !isfinite(x) || !isfinite(y) || !isfinite(yaw) || vi<1 || vi>15)return CAMERA_RUNTIME_INVALID;
    s->candidate_calls=0;s->status=CAMERA_RUNTIME_OK;
    if(bq_bridge_begin(&s->bridge)!=1)return s->status=CAMERA_RUNTIME_INVALID;
    playerRuntimeMoveObserved(player,x,y,yaw,dt,jump,camera_mode,vertices,triangles,count,candidate,s);
    assert(s->candidate_calls==(dt>0?1u:0u));
    if(s->candidate_calls!=(dt>0?1u:0u))s->status=CAMERA_RUNTIME_INVALID;
    if((player->events&BANJO_JUMP_RECOVERED) && s->status==CAMERA_RUNTIME_OK) {
        /* B.9 diagnostic relocation event: reinit preserves history and clock.
         * This is not a collision-contact/final-position replay. */
        const float relocated[3]={player->motion.actor.x,player->motion.actor.y,player->motion.actor.z};
        if(bq_bridge_reinit(&s->bridge)!=1 ||
           bq_bridge_candidate(&s->bridge,&s->opa,&s->xlu,relocated,s->bridge.next_ordinal)!=1)
            s->status=CAMERA_RUNTIME_QUERY_FAILED;
    }
    if(bq_bridge_end(&s->bridge)!=1)return s->status=CAMERA_RUNTIME_INVALID;
    if(s->status!=CAMERA_RUNTIME_OK)return s->status;
    if(!s->floor_ready)return s->status=CAMERA_RUNTIME_WAIT;
    float under;
    if(bq_camera_terrain(&s->opa,&s->xlu,s->camera.position,&under)<0)
        return s->status=CAMERA_RUNTIME_QUERY_FAILED;
    const MovementActor *a=&player->motion.actor;
    BanjoCameraInput in={{a->x,a->y,a->z},s->bridge.floor.height,a->yaw,under,dt,vi,player->motion.grounded};
    BanjoCamera next=s->camera;
    if(!banjo_camera_update(&next,&s->math,s->zoom,s->triggers,s->trigger_count,&in))
        return s->status=CAMERA_RUNTIME_UNSUPPORTED;
    if(!cameraRareView(&next,s->view,&s->parity))return s->status=CAMERA_RUNTIME_INVALID;
    s->camera=next;s->view_ready=true;return s->status;
}
