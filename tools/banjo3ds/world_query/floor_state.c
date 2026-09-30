#include "floor_state.h"
#include <math.h>
#include <string.h>

typedef struct {float y;BqHit hit;int found;} Query;
typedef struct {const BqModel *opa,*xlu;int error;} Context;
static void mode(BqFloorState *s,unsigned value) {
    if(value==1)s->countdown=5;
    if(value==4)s->grace=1;
    s->mode=(uint8_t)value;
}
void bq_floor_init(BqFloorState *s) {
    memset(s,0,sizeof(*s));s->normal[1]=1;s->height=-9000;s->special_height=-10000;s->upper=56;
    for(int i=0;i<3;i++)s->floor_ref[i]=s->special_ref[i]=-1;
    mode(s,1);
}
void bq_floor_reinit(BqFloorState *s) {mode(s,1);}
static Query segment(Context *c,const float p[3],float a,float b,uint32_t filter) {
    Query q;memset(&q,0,sizeof(q));float start[3]={p[0],p[1]+a,p[2]},end[3]={p[0],p[1]+b,p[2]};
    q.found=bq_segment(c->opa,c->xlu,start,end,filter,&q.hit);
    if(q.found<0){c->error=1;q.found=0;}
    q.y=end[1];return q;
}
static Query query(Context *c,const float p[3],float a,float b,uint32_t filter) {
    if(fabsf(b-a)>500.f) {
        float stop=a<b?a+500.f:a-500.f;
        Query q=segment(c,p,a,stop,filter);
        if(!q.found)q=segment(c,p,a<b?a+500.f-1.f:a-500.f+1.f,b,filter);
        return q;
    }
    return segment(c,p,a,b,filter);
}
static void copy_triangle(BqFloorTriangle *t,int32_t ref[3],const BqHit *h) {
    for(int i=0;i<3;i++)t->vertex[i]=(int16_t)h->indices[i];
    t->surface=(int16_t)h->surface;t->flags=h->flags;
    ref[0]=h->role;ref[1]=h->occurrence;ref[2]=h->cell;
}
static void floor_hit(BqFloorState *s,const Query *q) {
    copy_triangle(&s->floor_triangle,s->floor_ref,&q->hit);
    s->valid=1;s->flags=q->hit.flags;s->surface=(int16_t)q->hit.surface;s->height=q->y;
    s->model=(uint32_t)(q->hit.role+1);memcpy(s->normal,q->hit.normal,12);
}
static void no_floor(BqFloorState *s) {
    s->valid=1;s->flags=0;s->surface=0;s->height=-9000;s->model=0;
    s->normal[0]=s->normal[2]=0;s->normal[1]=1;
}
static void special_hit(BqFloorState *s,const Query *q) {
    copy_triangle(&s->special_triangle,s->special_ref,&q->hit);
    s->special_valid=1;s->special_height=q->y;
}
static void no_special(BqFloorState *s) {s->special_valid=1;s->special_height=-10000;}
static unsigned classify(const BqFloorState *s) {
    if(!s->special_valid)return 2;
    if(!s->valid)return 4;
    if(s->special_height<s->candidate[1])return 2;
    float d=s->special_height-s->height;
    if(d < -20.f)return 2;
    if(d > 100.f)return 4;
    return 3;
}
static void state2(BqFloorState *s,Context *c) {
    float delta=s->previous[1]-s->candidate[1];
    float upper=(delta>150.f?delta:150.f)+10.f;
    Query q=query(c,s->candidate,upper,-5.f,0xf800ff0f);int special=q.found;
    if(special)special_hit(s,&q);
    upper=s->upper;q=query(c,s->candidate,upper,-1300.f,s->filter);
    if(!q.found) {
        no_floor(s);
        if(!special)no_special(s);
        else if(s->candidate[1]<s->special_height)mode(s,3);
    }else if(q.hit.flags&0x1e0000) {
        special_hit(s,&q);
        if(s->height<s->special_height && s->candidate[1]<s->special_height)mode(s,3);
        q=query(c,s->candidate,upper,-450.f,s->filter|0x1e0000);
        if(!q.found)no_floor(s);
        else if(q.hit.normal[1]>=0)floor_hit(s,&q);
    }else if(q.hit.normal[1]<0 && !(q.hit.flags&0x10000)) {
        upper=q.y-s->candidate[1];
        q=query(c,s->candidate,upper-1.f,upper-1300.f,s->filter|0x1e0000);
        if(q.found)floor_hit(s,&q);else no_floor(s);
    }else {
        floor_hit(s,&q);
        if(special)mode(s,3);else no_special(s);
    }
}
static void state3(BqFloorState *s,Context *c) {
    Query q=query(c,s->candidate,100.f,-1300.f,s->filter|0x1e0000);
    if(q.found && q.hit.normal[1]>=0)floor_hit(s,&q);
    float offset=s->special_height-s->candidate[1];
    q=query(c,s->candidate,offset+50.f,offset-50.f,0xf800ff0f);
    if(q.found)special_hit(s,&q);
    unsigned next=classify(s);if(next!=3)mode(s,next);
}
static void state4(BqFloorState *s,Context *c,unsigned parity) {
    int high=s->candidate[1]-s->height>120.0;
    if(!high || parity) {
        s->special_valid=s->old_special_valid;
        Query q=query(c,s->candidate,60.f,-390.f,s->filter|0x1e0000);
        if(q.found){if(q.hit.normal[1]>=0)floor_hit(s,&q);}else no_floor(s);
    }
    if(!high || !parity) {
        s->valid=s->old_valid;
        float offset=s->special_height-s->candidate[1];
        Query q=query(c,s->candidate,offset+70.f,offset-70.f,0xf800ff0f);
        if(q.found){special_hit(s,&q);s->grace=1;}
        else if(s->grace){s->grace=0;s->special_valid=1;}
    }
    unsigned next=classify(s);if(next!=4)mode(s,next);
}
int bq_floor_update(BqFloorState *s,const BqModel *opa,const BqModel *xlu,
                    const float candidate[3],float upper,uint32_t filter,unsigned parity) {
    if(!s || !candidate || !isfinite(upper) || fabsf(upper)>10000 || parity>1 || s->mode<1 || s->mode>5)return -1;
    for(int i=0;i<3;i++)if(!isfinite(candidate[i]) || fabsf(candidate[i])>20000)return -1;
    BqFloorState next=*s;Context c={opa,xlu,0};
    memcpy(next.candidate,candidate,12);next.upper=upper;next.filter=filter;
    next.old_valid=next.valid;next.old_special_valid=next.special_valid;next.valid=next.special_valid=0;
    if(next.mode==1 || next.countdown) {
        --next.countdown;
        Query q=segment(&c,next.candidate,-100.f,7000.f,0xf800ff0f);
        if(q.found)special_hit(&next,&q);
        mode(&next,q.found?3:2);
    }
    switch(next.mode) {
        case 2:state2(&next,&c);break;
        case 3:state3(&next,&c);break;
        case 4:state4(&next,&c,parity);break;
        default:break;
    }
    memcpy(next.previous,next.candidate,12);
    if(c.error)return -1;
    *s=next;return 1;
}
