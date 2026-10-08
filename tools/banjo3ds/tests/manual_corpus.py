"""Independent manual input histories and packed original-decomp goldens.
No production parser/model imported. World/zone asset readers are original-only.
"""
import ctypes as C
import hashlib
import json
import struct
import manual_reference as ref
import zones_reference
import contact_corpus as contact
F=C.c_float
I=C.c_int
def snapshot(lib):
    f=(F*len(ref.FIELDS))();i=(I*len(ref.IDS))();t=contact.Trace();lib.manual_snapshot(f,i,C.byref(t))
    return list(f),list(i),contact.trace_values(t)
def packed(row):
    f,i,t=row
    return struct.pack('>'+str(len(f))+'f'+str(len(i))+'i8I9f',*f,*i,*t)
def command(player=(0,1800,800),buttons=0,**kw):
    c=dict(player=list(player),floor=player[1],yaw=0,under=-9000,dt=F(1/60).value,vi=1,stable=True,buttons=buttons,enabled=35);c.update(kw);return c
def schedules():
    out=[]
    def add(name,cmds,**kw):out.append(dict(name=name,commands=cmds,world='real',**kw))
    add('R-hold-release',[command(buttons=1 if i<50 else 0) for i in range(240)])
    add('C-left-hold-release',[command(buttons=2 if i<120 else 0) for i in range(200)])
    add('C-right-hold-release',[command(buttons=4 if i<120 else 0) for i in range(200)])
    add('C-retarget',[command(buttons={0:2,12:4,30:2,40:4}.get(i,0)) for i in range(200)])
    add('zoom-cooldown',[command(buttons=8 if i in (0,29,31,33,60,90,120,150) else 0) for i in range(180)])
    add('zone-priority',[command((0,1800,0) if i<40 or i>=120 else (0,1800,800),buttons=1|2|8 if i<60 else 0) for i in range(180)])
    add('R-zone-interruption',[command((0,1800,800) if i<10 or i>=40 else (0,1800,0),buttons=1) for i in range(120)])
    add('C-zone-interruption',[command((0,1800,800) if i<10 or i>=40 else (0,1800,0),buttons=2 if i in (0,35,41) else 0) for i in range(120)])
    add('node38-zoom',[command((-2089,332,687),buttons=8 if i in (31,60,90) else 0) for i in range(120)])
    # Changing visible yaw while held, then releasing before convergence.
    for yaw in (90,180,270,359,1):
        add('R-turn-'+str(yaw),[command(buttons=1 if i<25 else 0,yaw=yaw) for i in range(240)])
    add('R-tracking',[command(buttons=1 if i<100 else 0,yaw=(i*5)%360,vi=2 if i%3==0 else 1) for i in range(240)])
    add('R-to-C-to-R',[command(buttons=(1 if i<120 else 0)|({15:2,30:4,45:2}.get(i,0)),yaw=90) for i in range(240)])
    add('disabled-C-inputs',[command(buttons=(2 if i%4==0 else 4 if i%4==2 else 8),enabled=0) for i in range(80)])
    add('zoom-hold-no-repeat',[command(buttons=8 if i>=31 else 0) for i in range(160)])
    add('jump-stable-zone',[command((0,1800,0) if i<10 or i>=70 else (0,2100,800),stable=i<10 or i>=40,buttons=1) for i in range(120)])
    add('overlap-history',[command(p,buttons=1|2|8) for p in ([(-820,400,-75)]*20+[(-737,445,-316)]*20+[(-640,400,-531)]*20)])
    for button in (2,4):
        # Initial camera near orbit wrap; retain source trig residuals.
        add('C-wrap-'+str(button),[command(buttons=button if i in (0,10,60) else 0) for i in range(180)],eye=[-15,2175,1649],rotation=[340,359,0])
    for world in ('opa','xlu','shared'):
        for button in (1,2,4):
            c=[command((-400,-375,0),buttons=button if (button==1 and i<120) or (button!=1 and i%30==0) else 0,yaw=90,target=[-400,0,0]) for i in range(240)]
            out.append(dict(name=world+'-manual-'+str(button),world=world,commands=c,disable_zones=True,eye=[100,0,0],rotation=[0,90,0],history=-1,counter=0))
    for button in (1,2,4):
        out.append(dict(name='failed-recovery-'+str(button),world='opa',disable_zones=True,eye=[100,0,0],rotation=[0,90,0],
            commands=[command((-400,-375,0),buttons=button if button==1 or i%20==0 else 0,yaw=90,target=[-20,0,0]) for i in range(120)]))
    for button in (2,4):
        out.append(dict(name='C-failed-18-candidates-'+str(button),world='opa',disable_zones=True,eye=[20,0,0],rotation=[0,90,0],
            commands=[command((-400,-375,0),buttons=button if i%2==0 else 0,dt=.001,yaw=90,target=[-20,0,0]) for i in range(30)]))
    # Failed C gate retains request-side state, and BOTH edges try right after
    # a rejected left. Queries determine outcomes; no injected hit flags.
    for eye in ([1,0,0],[20,0,0],[40,0,0]):
        out.append(dict(name='C-rejected-'+str(eye[0]),world='opa',disable_zones=True,eye=eye,rotation=[0,90,0],
            commands=[command((-400,-375,0),buttons=6 if i%2==0 else 0,yaw=90) for i in range(40)]))
    # Real map wall/bridge locations, using real zone priority unless explicitly
    # disabled as a diagnostic world-node enable input.
    for name,p in (('opa-wall',[1682.399268,-251.666667,-3969.790314]),('xlu-bridge',[-507,1267.666667,-1750])):
        for disabled in (False,True):
            add(name+'-'+str(disabled),[command(p,buttons=1 if i<90 else (2 if i==90 else 0),yaw=90) for i in range(160)],disable_zones=disabled)
    return out

def initialize(lib,s):
    zones_reference.configure(lib);contact.load(lib,s['world'])
    c=s['commands'][0];p=c['player'];eye=s.get('eye',[p[0],p[1]+375,p[2]-850]);rot=s.get('rotation',[340,180,0])
    lib.manual_init((F*3)(*p),c['floor'],(F*3)(*eye),(F*3)(*rot))
    if s.get('disable_zones'):
        C.memset((C.c_uint8*80).in_dll(lib,'D_80381FE8'),0,80)
    C.c_float.in_dll(lib,'original_rollback_history').value=s.get('history',0)
    C.c_uint8.in_dll(lib,'D_8037D9F6').value=s.get('counter',0)

def step(lib,c):
    target=c.get('target',[c['player'][0],c['player'][1]+80,c['player'][2]])
    ok=lib.manual_step((F*3)(*c['player']),c['floor'],c['yaw'],c['under'],c['dt'],c['vi'],c['stable'],c['buttons'],c['enabled'],(F*3)(*target))
    if ok!=1:raise AssertionError(('unsupported original query overflow',c))
    return snapshot(lib)

def golden(opt):
    lib=ref.library(opt);out={};all_frames=[]
    for s in schedules():
        initialize(lib,s);stream=[];changes=[];counts=[0]*8;checkpoints={}
        for i,c in enumerate(s['commands']):
            row=step(lib,c);stream.append(packed(row));ids=row[1]
            if not changes or changes[-1][1:]!=ids:changes.append([i+1,*ids])
            for j,n in enumerate(row[2][:8]):counts[j]+=n
            if i in (0,1,5,14,29,30,59,len(s['commands'])-1):checkpoints[str(i+1)]=list(row)
        all_frames.extend(stream)
        out[s['name']]=dict(frames=len(stream),sha256=hashlib.sha256(b''.join(stream)).hexdigest(),ids=changes,counts=counts,checkpoints=checkpoints)
    sources=('src/core2/nc/dynamicCam13.c','src/core2/nc/dynamicCamA.c','src/core2/nc/dynamicCamera.c',
             'src/core2/code_9BD0.c','src/core2/code_3B2C0.c','src/core2/bainput.c','src/core2/bakey.c','src/core2/batimer.c')
    return dict(frames=len(all_frames),sha256=hashlib.sha256(b''.join(all_frames)).hexdigest(),input_sha256=hashlib.sha256(json.dumps(schedules(),sort_keys=True,separators=(',',':')).encode()).hexdigest(),packing='>53f13i8I9f per update, no padding',fields=ref.FIELDS,ids=ref.IDS,
                source_sha256={p:hashlib.sha256((ref.ROOT/p).read_bytes()).hexdigest() for p in sources},cases=out)
