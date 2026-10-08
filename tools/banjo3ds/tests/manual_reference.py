"""Independent manual-camera oracle compiled from original decomp functions.

Extends the original-only zone/contact oracle; no production manual imports.
Inputs are dry normal Banjo, explicit collider target, dt/VI, held buttons and
bainput enable bits. Audio has no camera-state effect and is observed as no-op.
"""
import ctypes as C
import functools
from pathlib import Path
import subprocess
import tempfile
import camera_reference as camera
import free_b_reference as free
import zones_reference as zones
import horizontal_reference
F=C.c_float
ROOT=camera.ROOT
FIELDS=(camera.FIELDS + 'r_radius r_target r_orbit r_velocity c_target c_orbit c_step c_radius c_radius_step zoom_timer viewport_offset_x viewport_offset_y viewport_offset_z viewport_offset_pitch viewport_offset_yaw viewport_offset_roll viewport_remaining viewport_duration viewport_x viewport_y viewport_z viewport_pitch viewport_yaw viewport_roll profile_radius profile_height position_gain position_response rotation_gain rotation_response rollback_dot'.split())
IDS='mode state node preset group local profile last_zoom focus_mode c_complete viewport_state obstruction_counter buttons'.split()

@functools.lru_cache(None)
def library(opt):
    base=zones.library(opt);tmp=tempfile.TemporaryDirectory(prefix='manual-original-');p=Path(tmp.name)
    code=(Path(base.temporary.name)/'reference.c').read_text()
    replacements={'batimer_decrement':'bool batimer_decrement(int n);','func_80290F14':'void func_80290F14(void);',
      'func_8029105C':'int func_8029105C(int n);','bakey_held':'u32 bakey_held(int n);',
      'func_802911E0':'void func_802911E0(void);','func_80291268':'void func_80291268(void);'}
    for n,v in replacements.items():
        code=code.replace('void '+n+'(void){}',v) if n=='func_80291268' else free.transform(code,n,lambda _,v=v:v)
    code=free.transform(code,'ncDynamicCamera_setState',lambda _:'''void ncDynamicCam13_init(void);
void ncDynamicCamera_setState(int n){if(n==dynamic_state)return;
 if(n==11)ncDynamicCamB_init();else if(n==17)ncDynamicCam11_init();else if(n==19)ncDynamicCam13_init();
 dynamic_state=n;}
''')
    # Real manual routines replace the former hard-disabled input adapters.
    extra='''
float D_8037DBA0,D_8037DBA4,D_8037DBA8,D_8037DBAC;
float D_80365DA0,D_80365DA4,D_80365DA8,D_80365DAC=100,D_80365DB4;u8 D_80365DB0;
unsigned manual_buttons,manual_edges,manual_enabled;float viewport_pos[3],viewport_rot[3];
struct {float value[8],last[8];} s_batimer;
#define manual_timer s_batimer.value[7]
int balookat_getState(void){return 0;}
#define BSGROUP_4_LOOK 4
#define SFX_12E_CAMERA_ZOOM_MEDIUM 0
#define SFX_12D_CAMERA_ZOOM_CLOSEST 1
void basfx_80299D2C(int a,float b,int c){}
void basfx_debug(void){}
#define BUTTON_C_LEFT 2
#define BUTTON_C_RIGHT 4
#define BUTTON_C_DOWN 8
#define bainput_enableMask manual_enabled
struct {u32 pressed_count[16];} bakey;
#define INCREMENT_OR_CLEAR_IF(dst, test) dst = (test) ? ((dst) + 1) : (0)
int func_802C0190(void){return focus_mode;}
void func_802C095C(void);
'''
    extra+=camera.original('src/core2/bakey.c','bakey_pressed')
    # camera.original's extractor excludes the u32 return type; preserve body.
    raw=(ROOT/'src/core2/bakey.c').read_text();a=raw.index('u32 bakey_held(');b=raw.index('\n}',a)+2
    extra+=raw[a:b]+'\n'
    for n in ('bainput_isEnabled','bainput_should_rotate_camera_left','bainput_should_rotate_camera_right','bainput_should_zoom_out_camera'):
        extra+=camera.original('src/core2/bainput.c',n)
    for n in ('batimer_get','batimer_set','batimer_decrement'):
        extra+=camera.original('src/core2/batimer.c',n)
    for n in ('ml_mapAbsRange_f','func_802589E4'):
        extra+=camera.original('src/core1/ml.c',n)
    extra+=camera.original('src/core2/code_3B2C0.c','func_802C2264')
    for n in ('func_802BDB30','func_802BDCE0','func_802BDE88','func_802BCE0C'):
        extra+=camera.original('src/core2/nc/dynamicCamera.c',n)
    for n in ('func_802C0640','func_802C069C','ncDynamicCam13_init','func_802C0780','ncDynamicCam13_update','func_802C095C'):
        extra+=camera.original('src/core2/nc/dynamicCam13.c',n)
    for n in ('ncDynamicCamA_func_802C1DB0','ncDynamicCamA_func_802C1EE0','ncDynamicCamA_func_802C1EEC','ncDynamicCamA_update'):
        extra+=camera.original('src/core2/nc/dynamicCamA.c',n)
    for n in ('func_80290F14','func_8029103C','func_8029105C','func_802911E0','func_80291268'):
        extra+=camera.original('src/core2/code_9BD0.c',n)
    extra+='''
void manual_init(const float *p,float floor,const float *eye,const float *rot){
 composition_init(p,floor,eye,rot);memset(&bakey,0,sizeof(bakey));manual_buttons=manual_edges=0;manual_enabled=35;manual_timer=.5f;
 D_8037DBA0=D_8037DBA4=D_8037DBA8=D_8037DBAC=0;
 D_80365DA0=D_80365DA4=D_80365DA8=D_80365DB4=0;D_80365DAC=100;D_80365DB0=0;
 memset(s_position,0,12);memset(s_rotation,0,12);s_time_remaining_s=s_duration=0;
 memcpy(viewport_pos,eye,12);memcpy(viewport_rot,rot,12);
}
int manual_step(const float *p,float floor,float yaw,float under,float dt,int vi,int on_ground,unsigned buttons,unsigned enabled,const float *target){
 memset(&trace,0,sizeof(trace));memset(&observed,0,sizeof(observed));overflow=0;
 memcpy(explicit_target,target,12);memcpy(player,p,12);floor_height=floor;yaw_deg=yaw;
 D_8037D9A0=under;current_dt=dt;vi_frames=vi;stable=on_ground;
 for(int bit=1;bit<=8;bit*=2){INCREMENT_OR_CLEAR_IF(bakey.pressed_count[bit],buttons&bit);}
 manual_edges=buttons&~manual_buttons;manual_buttons=buttons;manual_enabled=enabled;
 cameraMode_update();memcpy(D_8037D948,cameraPosition,12);func_802BCA58();
 switch(dynamic_state){case 11:ncDynamicCamB_update();break;case 17:ncDynamicCam11_update();break;
 case 19:ncDynamicCam13_update();break;case 10:ncDynamicCamA_update();break;default:return 0;}
 memcpy(viewport_pos,cameraPosition,12);memcpy(viewport_rot,cameraRotation,12);func_802C22C0(viewport_pos,viewport_rot);
 return !overflow;
}
int manual_obstruction(unsigned variant,float *camera,float *target,State *state,Trace *out){
 memset(&trace,0,sizeof(trace));overflow=0;memcpy(cameraPosition,camera,12);memcpy(explicit_target,target,12);
 D_8037D9F6=state->counter;memcpy(D_8037D9E0,state->position_step,12);memcpy(D_8037D9C8,state->angular_step,12);
 int result=func_802BC84C(variant);memcpy(camera,cameraPosition,12);state->counter=D_8037D9F6;
 memcpy(state->position_step,D_8037D9E0,12);memcpy(state->angular_step,D_8037D9C8,12);*out=trace;
 return overflow?-1:result;
}
void manual_snapshot(float *o,int *ids,Trace *t){
 ref_snapshot(o,ids);int k=22;
 float more[]={D_8037DBA0,D_8037DBA4,D_8037DBA8,D_8037DBAC,D_80365DA0,D_80365DA4,D_80365DA8,D_80365DAC,D_80365DB4,manual_timer};
 memcpy(o+k,more,sizeof(more));k+=10;memcpy(o+k,s_position,12);k+=3;memcpy(o+k,s_rotation,12);k+=3;
 o[k++]=s_time_remaining_s;o[k++]=s_duration;memcpy(o+k,viewport_pos,12);k+=3;memcpy(o+k,viewport_rot,12);k+=3;
 o[k++]=profile_r;o[k++]=profile_h;o[k++]=D_8037D9EC;o[k++]=D_8037D9F0;o[k++]=D_8037D9D4;o[k++]=D_8037D9D8;o[k++]=original_rollback_history;
 ids[4]=D_8037C010;ids[5]=D_8037C014;ids[6]=selected_profile;ids[7]=last_configured;
 ids[8]=focus_mode;ids[9]=D_80365DB0;ids[10]=s_state;ids[11]=D_8037D9F6;ids[12]=manual_buttons;*t=trace;
}
'''
    code+=extra;(p/'reference.c').write_text(code)
    trig=Path(horizontal_reference.library(opt).temporary.name)
    subprocess.run(['cc',*camera.FLAGS,opt,'-shared','-fPIC',str(p/'reference.c'),str(trig/'sinf.c'),str(trig/'cosf.c'),'-lm','-o',str(p/'reference.so')],check=True)
    lib=C.CDLL(str(p/'reference.so'));lib.temporary=tmp
    fp=C.POINTER(F)
    lib.zone_setup.argtypes=base.zone_setup.argtypes;lib.zone_reorder.argtypes=base.zone_reorder.argtypes
    lib.ref_load.argtypes=base.ref_load.argtypes
    lib.manual_init.argtypes=[fp,F,fp,fp];lib.manual_init.restype=None
    lib.manual_step.argtypes=[fp,F,F,F,F,C.c_int,C.c_int,C.c_uint,C.c_uint,fp];lib.manual_step.restype=C.c_int
    lib.manual_snapshot.argtypes=[fp,C.POINTER(C.c_int),C.c_void_p];lib.manual_snapshot.restype=None
    lib.manual_obstruction.argtypes=[C.c_uint,fp,fp,C.c_void_p,C.c_void_p];lib.manual_obstruction.restype=C.c_int
    return lib
