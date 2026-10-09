"""Independent original-decomp oracle, never imports production FP code.

Original ncba1p, dronelook, eligibility, stand/walk selection, eye provider,
angle/easing/smoothing functions are extracted verbatim. External gameplay is
an explicit dry/safe normal-Banjo environment. Events observe called services;
physics, next-state init, animation playback, audio, zones are not simulated.
"""
import ctypes as C
import functools
from pathlib import Path
import re
import subprocess
import tempfile
from camera_reference import original
from horizontal_reference import ROOT, FLAGS, library as trig_library
F=C.c_float
FP=C.POINTER(F)
class Camera(C.Structure):
    _fields_=[(n,F*3) for n in ('position','rotation','eye','look','source','source_rotation')]+[('timer',F),('state',C.c_int32)]
class Clock(C.Structure):
    _fields_=[('dt',F),('gains',F*4),('vi',C.c_int32)]
class Input(C.Structure):
    _fields_=[('player',F*3)]+[(n,F) for n in ('yaw','floor','vy','speed','target_speed','stick_x','stick_y')]+[('buttons',C.c_uint32)]+[(n,C.c_int32) for n in ('stable_flag','zone','context','fall','slide','can_claw','can_roll','map_blocks')]
class Look(C.Structure):
    _fields_=[('velocity',F*3)]+[(n,F) for n in ('target_speed','ideal_yaw','animation_duration')]+[('buttons',C.c_uint32)]+[(n,C.c_int32) for n in ('active','flag','animation','animation_starts','entries','exits')]+[('update_types',C.c_int32*4)]+[(n,C.c_int32) for n in ('sound','requested','event_count')]+[('events',C.c_int32*16)]

def enum(name):
    text=(ROOT/'include/enums.h').read_text()
    return re.search(r'enum '+name+r'\s*\{.*?\};',text,re.S)[0]+'\n'

def enum_function(path, name):
    text=(ROOT/path).read_text()
    m=re.search(r'(?m)^enum \w+\s+'+name+r'\([^;]*?\)\s*\{',text)
    end=m.end();depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[m.start():end]+'\n'

def raw_file(path):
    return re.sub(r'^#include.*$', '', (ROOT/path).read_text(),flags=re.M)

@functools.lru_cache(None)
def library(opt):
    tmp=tempfile.TemporaryDirectory(prefix='fp-original-');p=Path(tmp.name)
    trig=Path(trig_library(opt).temporary.name)
    code=r'''
#include <math.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
typedef float f32;typedef int32_t s32;typedef uint8_t u8;typedef uint32_t u32;
#define TRUE 1
#define FALSE 0
#define VER_SELECT(a,b,c,d) a
#define BAD_PI 3.141592654
#define sinf ref_sinf
float ref_sinf(float);
#define TUPLE_COPY(a,b) (a)[0]=(b)[0];(a)[1]=(b)[1];(a)[2]=(b)[2];
#define TUPLE_DIFF_COPY(a,b,c) (a)[0]=(b)[0]-(c)[0];(a)[1]=(b)[1]-(c)[1];(a)[2]=(b)[2]-(c)[2];
#define LENGTH_VEC3F(a) sqrtf((a)[0]*(a)[0]+(a)[1]*(a)[1]+(a)[2]*(a)[2])
typedef struct {float position[3],rotation[3],eye[3],look[3],source[3],source_rotation[3],timer;int state;} Camera;
typedef struct {float dt,gains[4];int vi;} Clock;
typedef struct {float player[3],yaw,floor,vy,speed,target_speed,stick_x,stick_y;unsigned buttons;int stable_flag,zone,context,fall,slide,can_claw,can_roll,map_blocks;} Input;
typedef struct {float velocity[3],target_speed,ideal_yaw,animation_duration;unsigned buttons;int active,flag,animation,animation_starts,entries,exits,update_types[4],sound,requested,event_count,events[16];} Look;
static Clock clock_in;static Input input;static Look obs;
static float internal_p[3],internal_r[3];static int visible,visibility_event;
float D_8037D984,D_8037D988,D_8037D98C,D_8037D990;
float time_getDelta(void){return clock_in.dt;}
int time_getDeltaReal_frames(void){return clock_in.vi;}
void ncDynamicCamera_getPosition(float *p){memcpy(p,internal_p,12);}
void ncDynamicCamera_getRotation(float *r){memcpy(r,internal_r,12);}
bool func_8028F150(void){return visible!=0;}
void player_setModelVisible(bool v){visible=v;visibility_event=v?2:1;}
static void event(int e){obs.events[obs.event_count++]=e;}
/* Original unused parameters are intentional: smoothing uses global gains. */
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-variable"
'''
    for n in ('nc_first_person_state','bs_e','asset_e','transformation_e'):
        code+=enum(n)
    for n in ('ml_vec3f_clear','ml_vec3f_copy','ml_vec3f_distance','mlNormalizeAngle','mlDiffDegF','ml_map_f','func_802575BC','func_80257658','ml_mapFunction_f','func_80257CF8','ml_sub_delta_time','ml_clamp_abs_f','ml_max_f','ml_min_f'):
        code+=original('src/core1/ml.c',n)
    for n in ('func_802BD610','func_802BD780'):
        code+=original('src/core2/nc/dynamicCamera.c',n)
    code+=raw_file('src/core2/nc/ba/1p.c')
    code+=r'''
void load_camera(const Camera *s){memcpy(D_8037DC60.position,s->position,72);D_8037DC60.transistion_timer=s->timer;D_8037DC60.state=s->state;}
void save_camera(Camera *s){memcpy(s->position,D_8037DC60.position,72);s->timer=D_8037DC60.transistion_timer;s->state=D_8037DC60.state;}
void ref_reset(Camera *s){load_camera(s);ncba1p_reset();save_camera(s);}
void ref_state(Camera *s,int n,const float *p,const float *r){load_camera(s);memcpy(internal_p,p,12);memcpy(internal_r,r,12);ncba1p_setState(n);save_camera(s);}
void ref_target(Camera *s,float *p,float *r){load_camera(s);ncba1p_setZoomedOutPosition(p);ncba1p_setZoomedOutRotation(r);save_camera(s);}
int ref_view(Camera *s,const Clock *c,float *p,float *r,int *v){
 load_camera(s);clock_in=*c;D_8037D984=c->gains[0];D_8037D988=c->gains[1];D_8037D98C=c->gains[2];D_8037D990=c->gains[3];
 visible=*v;visibility_event=0;ncba1p_getPositionAndRotation(p,r);*v=visible;save_camera(s);return visibility_event;
}
#define BUTTON_A 1
#define BUTTON_B 2
#define BUTTON_C_UP 4
#define BUTTON_Z 8
#define MAP_27_FP_FREEZEEZY_PEAK 39
#define MAP_1B_MMM_MAD_MONSTER_MANSION 27
#define YAW_STATE_1_DEFAULT 1
#define BA_PHYSICS_NORMAL 2
#define BA_FLAG_17_FIRST_PERSON_VIEW 17
#define BSWATERGROUP_0_NONE 0
#define SFX_12D_CAMERA_ZOOM_CLOSEST 0x12d
#define SFX_12E_CAMERA_ZOOM_MEDIUM 0x12e
struct {int pressed_count[16];} bakey;
static void button_counts(unsigned previous){
 for(int b=1;b<=8;b*=2)bakey.pressed_count[b]=(input.buttons&b)?((previous&b)?2:1):0;
} /* Counts >1 are equivalent for pressed(); no repeat simulation needed. */
unsigned bakey_held(int b){return input.buttons&b;}
int gsworld_getMap(void){return input.map_blocks?39:1;}
int mapSpecificFlags_get(int n){return input.map_blocks;}
bool player_inWater(void){return false;}
#define D_8037BF60 input.stable_flag
float baphysics_get_vertical_velocity(void){return input.vy;}
float playerPosition_getY(void){return input.player[1];}
float func_80294438(void){return input.floor;}
void playerPosition_get(float *p){memcpy(p,input.player,12);}
void player_getPosition(float *p){playerPosition_get(p);}
int bsStoredState_getTransformation(void){return TRANSFORM_1_BANJO;}
/* Unused eye-provider branches, outside normal-Banjo case 5. */
void baModel_getPosition(float *p){playerPosition_get(p);}
void baModel_802924E8(float *p){playerPosition_get(p);}
void baModel_8029223C(float *p){playerPosition_get(p);}
void baModel_80292260(float *p){playerPosition_get(p);}
'''
    code+=original('src/core2/bakey.c','bakey_pressed')
    for n in ('player_isStable','can_view_first_person','func_8028B254'):
        code+=original('src/core2/playerutils.c',n)
    code+=original('src/core2/bainput.c','bainput_should_look_first_person_camera')
    code+=original('src/core2/code_7060.c','func_8028E9C4')
    # Source-derived dry normal table entries: do not ask production for values.
    tables=(ROOT/'src/core2/code_14420.c').read_text()
    code+='typedef struct {int state_id;enum asset_e anim_id;float anim_duration;} Entry;\n'
    m=re.search(r'Struct_core2_13FC0 D_803647A0\[14\] = (\{.*?\});',tables,re.S)
    code+='Entry D_803647A0[14] = '+m[1]+';\n'
    code+=re.search(r's16 D_80364624\[14\] = \{.*?\};',tables,re.S)[0].replace('s16','int')+'\n'
    code+='int func_8029BAF0(void){return 6;}\n'
    code+=original('src/core2/code_14420.c','func_8029BCF8')
    code+=enum_function('src/core2/code_14420.c','func_8029BDBC')
    code+=r'''
void bsDroneLook_end(void);
void basfx_80299D2C(int a,float b,int c){obs.sound=a;event(1);}
void baanim_playForDuration_loopSmooth(enum asset_e a,float d){obs.animation=a;obs.animation_duration=d;obs.animation_starts++;event(2);}
void code_14420_setUpdateTypes(int a,int b,int c,int d){obs.update_types[0]=a;obs.update_types[1]=b;obs.update_types[2]=c;obs.update_types[3]=d;event(3);}
void baphysics_set_target_horizontal_velocity(float v){obs.target_speed=v;event(4);}
void baphysics_set_velocity(float *v){if(v)memcpy(obs.velocity,v,12);else memset(obs.velocity,0,12);event(5);}
void ncDynamicCamera_enterFirstPerson(void){ncba1p_setState(FIRSTPERSON_STATE_1_ENTER);ncba1p_setZoomedOutPosition(internal_p);ncba1p_setZoomedOutRotation(internal_r);event(6);}
void ncDynamicCamera_exitFirstPerson(void){ncba1p_setState(FIRSTPERSON_STATE_3_EXIT);event(11);}
void player_getRotation(float *r){r[0]=r[2]=0;r[1]=input.yaw;}
void baflag_set(int f){obs.flag=1;event(9);}
void baflag_clear(int f){obs.flag=0;event(12);}
float bastick_getX(void){return input.stick_x;}
float bastick_getY(void){return input.stick_y;}
void yaw_setIdeal(float v){obs.ideal_yaw=mlNormalizeAngle(v);event(10);}
int player_getTransformation(void){return TRANSFORM_1_BANJO;}
int player_getWaterState(void){return 0;}
int balookat_getState(void){return 0;}
void bs_setState(int n){obs.requested=n;if(obs.active && n){bsDroneLook_end();obs.active=0;obs.exits++;}}
/* Observe target setter calls without changing the original bodies. */
static void eye_event(float *p){ncba1p_setZoomedOutPosition(p);event(7);}
static void rotation_event(float *p){ncba1p_setZoomedOutRotation(p);event(8);}
#define ncba1p_setZoomedOutPosition eye_event
#define ncba1p_setZoomedOutRotation rotation_event
'''
    code+=raw_file('src/core2/bs/dronelook.c')
    code+='\n#undef ncba1p_setZoomedOutPosition\n#undef ncba1p_setZoomedOutRotation\n'
    code+=r'''
int bastick_getZone(void){return input.zone;}
float bastick_distance(void){return input.zone?1.f:0.f;}
float yaw_get(void){return input.yaw;}
bool baphysics_is_slower_than(float v){return input.speed<v;}
float baphysics_get_horizontal_velocity(void){return input.speed;}
float baphysics_get_target_horizontal_velocity(void){return input.target_speed;}
bool player_isOnDangerousGround(void){return false;}
bool func_8028B4C4(void){return false;}
bool player_shouldFall(void){return input.fall!=0;}
bool player_isSliding(void){return input.slide!=0;}
bool can_claw(void){return input.can_claw!=0;}
bool can_roll(void){return input.can_roll!=0;}
int badrone_look(void){return BS_98_WALK_DRONE;}
#define BA_FLAG_2_ON_SPRING_PAD 2
#define BA_FLAG_1_ON_FLIGHT_PAD 1
bool baflag_isTrue(int n){return false;}
bool can_flap_flip(void){return true;} /* explicit eligibility environment */
int func_8029CA94(int n){return n;} /* no scripted/transform override */
void func_802B6E44(void){} /* animation-rate side effects outside selector */
void func_8029AD28(float x,int y){}
void func_802B6D00(void){} /* target speed supplied, not re-evaluated */
void func_802B6EBC(void){}
int func_802B6EF4(void){return 1;} /* gait phase gate supplied open */
void func_80299594(int n,float v){}
float bsWalkSlowWalkWalkVelocityThreshold=150,bsWalkWalkFastWalkVelocityThreshold=225,bsWalkSkidVelocity=125;
'''
    code+=enum_function('src/core2/code_14420.c','bs_getTypeOfJump')
    code+=original('src/core2/bs/stand.c','func_802B488C')
    for n in ('func_802B6F20','bswalk_creep_update','bswalk_slow_upate','bswalk_update','bswalk_fast_update'):
        code+=original('src/core2/bs/walk.c',n)
    code+=r'''
int select_original(void){
 if(input.context==1)return func_802B488C(0);
 switch(input.context){case 31:bswalk_creep_update();break;case 2:bswalk_slow_upate();break;case 3:bswalk_update();break;case 4:bswalk_fast_update();break;}
 return obs.requested;
}
int ref_eligible(Camera *s,Input *in){load_camera(s);input=*in;return can_view_first_person();}
int ref_select(Camera *s,Input *in,unsigned pressed){load_camera(s);input=*in;button_counts(in->buttons&~pressed);memset(&obs,0,sizeof(obs));return select_original();}
void ref_look(Look *s,Camera *c,const Clock *time,const Input *in,const float *p,const float *r){
 load_camera(c);clock_in=*time;input=*in;memcpy(internal_p,p,12);memcpy(internal_r,r,12);obs=*s;
 button_counts(obs.buttons);obs.buttons=in->buttons;obs.requested=0;obs.event_count=0;memset(obs.events,0,sizeof(obs.events));
 if(obs.active)bsDroneLook_update();else {
  /* Selection's non-look animation/velocity side effects are deliberately
   * outside this boundary. Only the selected request is consumed. */
  Look before=obs;int request=select_original();obs=before;obs.requested=request;
  if(request==BS_98_WALK_DRONE){obs.active=1;obs.entries++;bsDroneLook_init();}
 }
 *s=obs;save_camera(c);
}
'''
    (p/'reference.c').write_text(code)
    result=subprocess.run(['cc',*FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',str(p/'reference.c'),str(trig/'sinf.c'),'-lm','-o',str(p/'reference.so')],capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr)
    lib=C.CDLL(str(p/'reference.so'));lib.temporary=tmp;lib.compiler_output=result.stderr
    configure(lib,'ref_');return lib

def configure(lib,prefix):
    cp=C.POINTER(Camera);clock=C.POINTER(Clock);ip=C.POINTER(Input)
    for name,args,rest in (
        ('reset',[cp],None),('state',[cp,C.c_int,FP,FP],None),('target',[cp,FP,FP],None),
        ('view',[cp,clock,FP,FP,C.POINTER(C.c_int32)],C.c_int),
        ('eligible',[cp,ip],C.c_int),('select',[cp,ip,C.c_uint],C.c_int),
        ('look' if prefix=='ref_' else 'look_update',[C.POINTER(Look),cp,clock,ip,FP,FP],None)):
        f=getattr(lib,prefix+name);f.argtypes=args;f.restype=rest
