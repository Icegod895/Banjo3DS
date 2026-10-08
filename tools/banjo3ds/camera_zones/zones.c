#include "zones.h"
#include <math.h>
#include <string.h>
void bz_init(BzState *s) {
    memset(s,0,sizeof(*s));s->group=s->local=s->last_zoom=-1;
    memset(s->enabled,1,sizeof(s->enabled));
}
bool bz_enable(BzState *s,int32_t node,bool enabled) {
    if(!s || node<0 || node>=80)return false;
    s->enabled[node]=enabled;return true;
}
static bool hit(const BanjoCameraTrigger *t,const int32_t p[3]) {
    int32_t x=p[0]-t->position[0],z=p[2]-t->position[2];
    return (t->mask&1) && p[1]+150>=t->position[1] && p[1]-150<t->position[1]
        && x*x+z*z<t->radius*t->radius;
}
static int local(const BzState *s,const BzData *d,int g,int old,const int32_t p[3]) {
    const BzGroup *group=&d->groups[g];
    if(!s->enabled[group->node])return -1;
    if(old>=0 && old<group->count && hit(d->triggers+group->first+old,p))return old;
    for(int i=0;i<group->count;i++)if(hit(d->triggers+group->first+i,p))return i;
    return -1;
}
int32_t bz_select(BzState *s,const BzData *d,const float position[3]) {
    int32_t p[3];for(int i=0;i<3;i++)p[i]=(int32_t)position[i];
    if(s->group>=0 && (size_t)s->group<d->group_count) {
        int l=local(s,d,s->group,s->local<0?0:s->local,p);
        if(l>=0){s->local=l;return d->groups[s->group].node;}
    }
    for(size_t g=0;g<d->group_count;g++) {
        int l=local(s,d,(int)g,0,p);
        if(l>=0){s->group=(int)g;s->local=l;return d->groups[g].node;}
    }
    s->group=s->local=-1;return -1;
}
bool bz_update(BzState *s,BanjoCamera *camera,BcFreeBState *post,const BanjoCameraMath *math,
    const BzData *data,const BanjoCameraInput *in,bool force,
    const BqModel *opa,const BqModel *xlu,const float target[3],BcScratch *scratch,BcFreeBTrace *trace) {
    if(!s || !camera || !post || !math || !data || !in || !data->nodes || !data->groups
       || !data->triggers || !isfinite(in->dt) || in->dt<0 || in->dt>.05f
       || in->vi_frames<1 || in->vi_frames>15 || camera->preset<1 || camera->preset>3
       || !isfinite(in->floor_height) || !isfinite(in->floor_under_camera)
       || !isfinite(in->visible_yaw) || fabsf(in->visible_yaw)>36000)return false;
    for(int i=0;i<3;i++)if(!isfinite(in->player[i]) || fabsf(in->player[i])>20000)return false;
    BzState next=*s;BanjoCamera cam=*camera;
    if(in->stable || force)memcpy(cam.stable_position,in->player,12);
    int node=bz_select(&next,data,cam.stable_position);bool zoom=false;
    if(node<0)next.profile=0;
    else {
        if((size_t)node>=data->node_count)return false;
        const BzNode *n=data->nodes+node;
        if(n->type==3){next.last_zoom=node;zoom=true;}
        else if(n->type==4 && n->profile==1)next.profile=1;
        else return false;
    }
    /* Profile survives while a zoom node is selected, exactly as 90D48. */
    static const float radii[2][3]={{550,850,1100},{800,950,1100}};
    static const float heights[2][3]={{175,375,675},{375,525,675}};
    BanjoCameraZoom empty={0};
    const BanjoCameraZoom *z=next.last_zoom<0?&empty:&data->nodes[next.last_zoom].zoom;
    BanjoCameraPhase phase;
    if(!banjo_camera_prepare_selected(&phase,&cam,math,z,in,node,zoom,
        radii[next.profile][cam.preset-1],heights[next.profile][cam.preset-1]))return false;
    if(!bc_free_b_finish_phase(&cam,post,math,z,in,&phase,opa,xlu,target,scratch,trace))return false;
    *s=next;*camera=cam;return true;
}
