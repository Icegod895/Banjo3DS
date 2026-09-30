#include "floor_bridge.h"
#include <string.h>
int bq_bridge_init(BqFloorBridge *s,unsigned initial_parity) {
    if(!s || initial_parity>1)return -1;
    memset(s,0,sizeof(*s));bq_floor_init(&s->floor);
    s->initial_parity=(uint8_t)initial_parity;s->initialized=1;return 1;
}
unsigned bq_bridge_parity(const BqFloorBridge *s) {
    return (s->frame+s->initial_parity)&1u;
}
int bq_bridge_begin(BqFloorBridge *s) {
    if(!s || !s->initialized || s->active)return -1;
    s->active=1;s->next_ordinal=0;return 1;
}
int bq_bridge_reinit(BqFloorBridge *s) {
    if(!s || !s->initialized)return -1;
    bq_floor_reinit(&s->floor);return 1;
}
int bq_bridge_candidate(BqFloorBridge *s,const BqModel *opa,const BqModel *xlu,
                        const float xyz[3],uint32_t ordinal) {
    if(!s || !s->initialized || !s->active || ordinal!=s->next_ordinal || ordinal==UINT32_MAX)return -1;
    int result=bq_floor_update(&s->floor,opa,xlu,xyz,56.f,0x400000u,bq_bridge_parity(s));
    if(result==1)++s->next_ordinal;
    return result;
}
int bq_bridge_end(BqFloorBridge *s) {
    if(!s || !s->initialized || !s->active)return -1;
    s->active=0;++s->frame;return 1;
}
