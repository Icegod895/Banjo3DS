#include "bridge.h"
#include <string.h>
#include <math.h>
void bridge_init(BridgeState *s) { memset(s,0,sizeof(*s));s->alive=1; }
static void set(BridgeState *s,int i,float y) {
    s->mesh[i].offset=y;s->mesh[i].elapsed=0;
    s->mesh[i].pending=1;s->mesh[i].completed=0;
}
void bridge_actor_tick(BridgeState *s,uint32_t learned) {
    if(!s->alive)return;
    int all=(learned&BRIDGE_REQUIRED_ABILITIES)==BRIDGE_REQUIRED_ABILITIES;
    if(!s->initialized) {
        if(!all){set(s,2,-5000);set(s,1,0);}
        else {set(s,0,-5000);s->alive=0;}
        s->initialized=1;
    }
    /* Original despawn is deferred; the second condition still executes. */
    if(all){set(s,1,-5000);set(s,2,0);set(s,0,-5000);s->alive=0;}
}
void bridge_mesh_tick(BridgeState *s,float dt) {
    /* Host API domain: original nonnegative, finite simulation delta. */
    if(!isfinite(dt)||dt<0)return;
    for(int i=0;i<3;i++) {
        BridgeMesh *m=&s->mesh[i];if(!m->pending)continue;
        m->elapsed+=dt;if(0.00001f<m->elapsed)m->elapsed=0.00001f;
        /* C62B0: both endpoints equal; retain original float order/cast. */
        m->applied=(int16_t)(uint16_t)(int32_t)(m->offset+
            ((m->elapsed/0.00001f)*(m->offset-m->offset)));
        if(0.00001f<=m->elapsed){m->pending=0;m->completed=1;}
    }
}
int16_t bridge_component(const BqModel *base,unsigned vertex,unsigned axis) {
    const BridgeModel *view=(const BridgeModel *)base;
    const uint8_t *p=base->vertices+24+16*vertex+2*axis;
    int16_t original=(int16_t)((unsigned)p[0]*256+p[1]);
    if(base->role!=1||axis!=1||!view->state)return original;
    /* Membership from 14D0's actual mesh list; independently frozen in tests. */
    int mesh=vertex>=134&&vertex<=137?0:vertex>=150&&vertex<=165?1:
             vertex>=138&&vertex<=149?2:-1;
    if(mesh<0)return original;
    return (int16_t)(uint16_t)((int32_t)original+(uint16_t)view->state->mesh[mesh].applied);
}
int bridge_model_open(BridgeModel *m,const uint8_t *packet,size_t size,const BridgeState *s) {
    if(!m||!bq_open(&m->base,packet,size))return 0;
    m->state=s;return 1;
}
