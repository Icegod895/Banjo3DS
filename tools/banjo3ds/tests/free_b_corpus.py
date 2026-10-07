"""Deterministic full-update schedules and canonical observer packing.

Original-source oracle only; no production camera/contact implementation.
State seeds are explicit diagnostic initial conditions, never injected contact
results. Every frame still runs original smoothing, queries and postprocessing.
"""
import ctypes as C
import hashlib
import json
import struct
import camera_reference as camera
import contact_corpus as contact

F=C.c_float
class Trace(C.Structure):
    _fields_=[(n,F*3) for n in ('previous','desired','smoothed','corrected','final_position','look')]+[
        ('dot',F),('rollback_executed',C.c_uint32),('rolled_back',C.c_uint32),('free_b',C.c_uint32),('contact',contact.Trace)]

def trace_values(t):
    return [*[x for n,_ in Trace._fields_[:6] for x in getattr(t,n)],t.dot,
            t.rollback_executed,t.rolled_back,t.free_b,*contact.trace_values(t.contact)]

def packed(v,ids,history,counter,t):
    # Camera:22f4i; separate history/counter:fI; boundary:19f3I8I9f.
    return camera.pack(v,ids)+struct.pack('>fI',history,counter)+struct.pack('>19f11I9f',*trace_values(t))

def command(p,**kw):
    return dict(player=list(p),floor=kw.get('floor',p[1]),yaw=kw.get('yaw',0),
                under=kw.get('under',p[1]),dt=kw.get('dt',1/60),vi=kw.get('vi',1),
                stable=kw.get('stable',True),preset=kw.get('preset',2),
                target=kw.get('target',[p[0],p[1]+60,p[2]]))

def schedules():
    result=[]
    for name in camera.CASES:
        p,eye,rot=camera.initial(name)
        cmds=[dict(c,target=[c['player'][0],c['player'][1]+60,c['player'][2]]) for c in camera.commands(name)]
        result.append(dict(name='real-'+name,world='real',zones=True,player=p,eye=eye,rotation=rot,commands=cmds))
    history_entry=dict(next(s for s in result if s['name']=='real-node_to_free'))
    history_entry.update(name='negative-history-across-node32-B',history=-1,counter=3)
    result.append(history_entry)
    # Ordinary uninterrupted wall approach, tangential motion and retreat.
    for world in ('opa','xlu','shared'):
        p=[-400,-375,0];cmds=[]
        for i in range(300):
            cmds.append(command([p[0]-(i*10 if i<150 else (300-i)*10),p[1],i],target=[-400,0,0]))
        result.append(dict(name=world+'-approach-slide-leave',world=world,zones=False,player=p,
                           eye=[100,0,0],rotation=[0,90,0],commands=cmds))
    # Same complete wall trajectory, different explicit collider-center input.
    # This isolates original recovery failure versus miss/reset; no hit is faked.
    wall_schedule=result[-3]
    for name,target in (('failed-recovery',[-20,0,0]),('obstruction-miss',[200,0,0])):
        s=dict(wall_schedule);s['name']=name
        s['commands']=[dict(c,target=target) for c in s['commands']]
        if name=='failed-recovery':
            s['commands']=[dict(c,player=[c['player'][0],c['player'][1],0],yaw=90) for c in s['commands']]
        s['counter']=2 if name=='obstruction-miss' else 0
        result.append(s)
    result.append(dict(name='unchanged-preserves-history-counter',world='opa',zones=False,
        player=[1000,-375,0],eye=[1850,0,0],rotation=[0,90,0],history=-1,counter=3,
        commands=[command([1000,-375,0]) for _ in range(30)]))
    # Known real OPA and XLU walls from the original-primitive corpus. Seed a
    # finite incoming position accumulator, then run uninterrupted updates.
    for name,w,obs,steps in contact.schedules():
        if name not in ('real-opa-wall','real-xlu-wall'):continue
        a,b,target=steps[0];p=[b[0],b[1]-375,b[2]-850]
        result.append(dict(name=name+'-full-chain',world='real',zones=False,player=p,eye=a,
            rotation=[330,0,0],orbit=0,position_step=[(b[i]-a[i])/5 for i in range(3)],
            commands=[command(p,target=target) for _ in range(120)]))
    result.append(dict(name='previous-sphere-pushout',world='opa',zones=False,
        player=[-400,-375,0],eye=[20,0,0],rotation=[0,90,0],
        commands=[command([-400,-375,0],target=[-400,0,0]) for _ in range(40)]))
    return result

def initialize(ref,schedule):
    records,z=camera.setup();records=records if schedule['zones'] else []
    raw=[v for r in records for v in r[1:]]
    ref.ref_setup((C.c_int*len(raw))(*raw),len(records),(F*12)(*z[:12]))
    contact.load(ref,schedule['world'])
    ref.composition_init((F*3)(*schedule['player']),schedule['player'][1],
                         (F*3)(*schedule['eye']),(F*3)(*schedule['rotation']))
    ref.composition_seed(schedule.get('history',0),schedule.get('counter',0))
    if 'orbit' in schedule:F.in_dll(ref,'D_8037DB70').value=schedule['orbit']
    ref.ref_seed((F*3)(*schedule.get('position_step',[0]*3)),(F*3)(*schedule.get('angular_step',[0]*3)))

def step(ref,c):
    ok=ref.composition_step((F*3)(*c['player']),c['floor'],c['yaw'],c['under'],c['dt'],c['vi'],c['stable'],c['preset'],(F*3)(*c['target']))
    if not ok:raise AssertionError(('original query overflow/viewport transition',c))
    v,ids=camera.snapshot(ref);h=F();counter=C.c_uint32();t=Trace()
    ref.composition_state(C.byref(h),C.byref(counter),C.byref(t))
    return v,ids,h.value,counter.value,t

def golden(ref):
    cases={}
    all_frames=[]
    for s in schedules():
        initialize(ref,s);stream=[];events={};counts=dict(changed=0,rollback=0,recovered=0,obstructions=0,
            failed_recovery=0,negative_dot=0,historical_rollback=0,previous_pushout=0)
        for i,c in enumerate(s['commands'],1):
            v,ids,h,counter,t=step(ref,c);stream.append(packed(v,ids,h,counter,t))
            counts['changed']+=t.contact.changed;counts['rollback']+=t.rolled_back
            counts['recovered']+=t.contact.recovered;counts['obstructions']+=t.contact.obstruction_calls
            counts['failed_recovery']+=bool(t.contact.recovery_attempts==11 and not t.contact.recovered)
            counts['negative_dot']+=bool(t.rollback_executed and t.dot<0)
            counts['historical_rollback']+=bool(t.rolled_back and t.dot>=0)
            counts['previous_pushout']+=bool(t.free_b and list(t.previous)!=list(t.contact.pushed_previous))
            if i in (1,2,5,30,60,120,len(s['commands'])) or t.contact.recovery_attempts or (t.rolled_back and t.dot>=0):
                events[str(i)]=dict(camera=v,ids=ids,history=h,counter=counter,trace=trace_values(t))
        cases[s['name']]=dict(frames=len(stream),sha256=hashlib.sha256(b''.join(stream)).hexdigest(),counts=counts,checkpoints=events)
        all_frames.extend(stream)
    return dict(packing='>22f4ifI19f11I9f; camera,history,counter,phase/contact observers',
        input_sha256=hashlib.sha256(json.dumps(schedules(),sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        frames=len(all_frames),sha256=hashlib.sha256(b''.join(all_frames)).hexdigest(),cases=cases)
