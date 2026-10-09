"""Explicit external schedules; no camera/DroneLook algorithm in this driver."""
import ctypes as C
import hashlib
import struct
from first_person_reference import Camera, Clock, Input, Look, F

def frame(**changes):
    d=dict(dt=1/60,vi=1,gains=[10,10,120,120],internal=[0,2100,-850],rotation=[340,180,0],
           viewport=[10,2105,-845],viewport_rotation=[341,181,0],eye=[0,1900,0],look=[0,180,0])
    d.update(changes);return d

def camera_schedules():
    specs=[]
    for name,gains in [('default',[10,10,120,120]),('apparent-arguments',[10,20,120,200]),('inherited',[6,10,50,120]),('zero',[0,0,0,0])]:
        for vi in (1,2,3,15):
            rows=[]
            for i in range(240):
                d=frame(gains=gains,vi=vi,viewport=[i*.5,2105-i*.125,-845],
                        viewport_rotation=[341,181+i*.3,0],look=[(359+i*.25)%360,(170+i*3)%360,0])
                if i==0:d['state']=1
                if i==140:d['state']=3
                rows.append(d)
            specs.append(dict(name=f'camera-{name}-vi{vi}',layer=1,rows=rows))
    for name,rotation,look in [('plus180',[0,0,0],[0,180,0]),('minus180',[0,180,0],[0,0,0]),
                              ('wrap',[359,359,0],[1,1,0]),('negative',[-360,-721,0],[720,-180,0])]:
        specs.append(dict(name=name,layer=1,rows=[frame(state=1 if i==0 else 2,rotation=rotation,look=look) for i in range(80)]))
    for distance in (39.999996185302734,40,40.000003814697266):
        for state in (1,3):
            d=frame(dt=0,state=state,internal=[distance,0,0],eye=[0,0,0],viewport=[distance,0,0],look=[0,0,0])
            # EXIT at t=0 reads incoming position; initialize timer=1 but use
            # dt=1 for this synthetic endpoint test (API math supports it).
            if state==3:d['dt']=1
            specs.append(dict(name=f'visibility-{state}-{distance}',layer=1,visible=state==1,rows=[d]))
    rows=[]
    for i in range(160):
        d=frame(dt=.03125,vi=2,look=[0,270,0])
        if i in (0,50,100):d['state']=1
        if i in (40,90):d['state']=3
        if i==120:d['reset']=True
        rows.append(d)
    specs.append(dict(name='reenter-reset-pass',layer=1,rows=rows))
    specs.append(dict(name='timer-exact',layer=1,rows=[frame(dt=.03125,vi=2,**({'state':1} if i==0 else {'state':3} if i==64 else {})) for i in range(128)]))
    specs.append(dict(name='never-enter-pass',layer=1,rows=[frame(dt=0 if i%2 else .05) for i in range(16)]))
    return specs

def look_schedules():
    specs=[]
    for exit_button in (1,2,4):
        for context in (1,31,2,3,4):
            rows=[]
            for i in range(240):
                d=frame(player=[i*.01,1800,0],buttons=4 if i<20 else exit_button if 170<=i<220 else 0,
                        context=context,zone=3,stick_x=1 if 65<i<110 else -1 if 110<=i<160 else 0,
                        stick_y=1 if 65<i<115 else -1 if 115<=i<165 else 0)
                rows.append(d)
            specs.append(dict(name=f'look-context{context}-exit{exit_button}',layer=2,rows=rows))
    for name in ('entry-held-A','entry-held-Cup','loss-24','loss-25','loss-26','positive-vy','reenter-exit-denied','fast-zone4','pitch-limits'):
        rows=[]
        for i in range(260):
            d=frame(buttons=4 if i==0 else 0,player=[0,1800,0])
            if name=='entry-held-A':d['buttons']=4 if i==0 else 1 if i<100 else 0
            if name=='entry-held-Cup':d['buttons']=4
            if name.startswith('loss-') and i>=90:
                d.update(stable_flag=0,floor=1800-int(name[5:]))
            if name=='positive-vy' and i>=90:d.update(vy=.01)
            if name=='reenter-exit-denied':d['buttons']=4 if i==0 or (i>=90 and i%2==0) else 0
            if name=='fast-zone4':d.update(context=4,zone=4,buttons=4)
            if name=='pitch-limits':d.update(stick_y=1 if i<155 else -1,stick_x=1)
            rows.append(d)
        specs.append(dict(name=name,layer=2,rows=rows))
    return specs

def make_input(d):
    v=Input();v.player[:]=d.get('player',[0,1800,0]);v.yaw=d.get('yaw',0);v.floor=d.get('floor',1800)
    v.vy=d.get('vy',-1);v.speed=d.get('speed',100);v.target_speed=d.get('target_speed',150)
    v.stick_x=d.get('stick_x',0);v.stick_y=d.get('stick_y',0);v.buttons=d.get('buttons',0)
    for n,default in [('stable_flag',1),('zone',0),('context',1),('fall',0),('slide',0),('can_claw',1),('can_roll',1),('map_blocks',0)]:setattr(v,n,d.get(n,default))
    return v

def pack(camera,visible,p,r,event,look):
    floats=[]
    for n in ('position','rotation','eye','look','source','source_rotation'):floats+=list(getattr(camera,n))
    floats+=[camera.timer]
    result=struct.pack('>19f2i6fi',*floats,camera.state,visible,*p,*r,event)
    result+=struct.pack('>6f',*look.velocity,look.target_speed,look.ideal_yaw,look.animation_duration)
    ints=[look.buttons,look.active,look.flag,look.animation,look.animation_starts,look.entries,look.exits,
          *look.update_types,look.sound,look.requested,look.event_count,*look.events]
    return result+struct.pack('>'+str(len(ints))+'i',*ints)

class Driver:
    def __init__(self,lib,reference,spec):
        self.lib=lib;self.prefix='ref_' if reference else 'fp_';self.spec=spec
        self.camera=Camera();self.look=Look();self.look.velocity[:]=[12,-1,500];self.look.target_speed=500;self.look.ideal_yaw=17
        self.visible=C.c_int32(spec.get('visible',1))
    def step(self,d):
        cam=self.camera;clock=Clock(d['dt'],(F*4)(*d['gains']),d['vi'])
        p=(F*3)(*d['internal']);r=(F*3)(*d['rotation']);under=bytes(p)+bytes(r)
        if self.spec['layer']==2:
            n='look' if self.prefix=='ref_' else 'look_update'
            getattr(self.lib,self.prefix+n)(C.byref(self.look),C.byref(cam),C.byref(clock),C.byref(make_input(d)),p,r)
        else:
            if d.get('reset'):getattr(self.lib,self.prefix+'reset')(C.byref(cam))
            if 'state' in d:getattr(self.lib,self.prefix+'state')(C.byref(cam),d['state'],p,r)
            getattr(self.lib,self.prefix+'target')(C.byref(cam),(F*3)(*d['eye']),(F*3)(*d['look']))
        assert under==bytes(p)+bytes(r),'underlying internal camera mutated'
        vp=(F*3)(*d['viewport']);vr=(F*3)(*d['viewport_rotation'])
        event=getattr(self.lib,self.prefix+'view')(C.byref(cam),C.byref(clock),vp,vr,C.byref(self.visible))
        return pack(cam,self.visible.value,vp,vr,event,self.look)

def golden(lib):
    result={}
    for spec in camera_schedules()+look_schedules():
        driver=Driver(lib,True,spec);rows=[driver.step(d) for d in spec['rows']]
        result[spec['name']]={'frames':len(rows),'sha256':hashlib.sha256(b''.join(rows)).hexdigest()}
    return result
