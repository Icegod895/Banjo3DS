"""Independent schedules. Deliberate position jumps test camera state selection,
not player physics. Every snapshot includes full original camera/contact state.
"""
import ctypes as C
import hashlib
import struct
import camera_reference as camera
import zones_reference as ref
import free_b_corpus as free
import contact_corpus as contact

F=C.c_float

def schedules():
    records,nodes,_=ref.asset()
    cases=[]
    def case(name,points,seed=0,counter=0):
        cmds=[free.command(p,stable=stable,target=[p[0],p[1]+80,p[2]]) for p,stable in points]
        cases.append(dict(name=name,commands=cmds,history=seed,counter=counter))
    case('spawn-jump-landing', [([0,1800,0],True)]*30+[([0,2100,800],False)]*30+[([0,1800,800],True)]*30+[([0,1800,0],True)]*30)
    case('opa-wall-node11',[([1682.399268,-251.666667,-3969.790314],True)]*90)
    case('zoom-replacement-exit-history', [([0,1800,0],True)]*20+[([1875,-9,-3262],True)]*20+[([0,1800,800],True)]*60, -1,3)
    case('profile1-entry-exit',[([-2089,332,687],True)]*30+[([0,1800,800],True)]*30)
    case('overlap-retain-22',[([-820,400,-75],True)]*5+[([-737,445,-316],True)]*10+[([-640,400,-531],True)]*5)
    case('overlap-retain-21',[([-640,400,-531],True)]*5+[([-737,445,-316],True)]*10+[([-820,400,-75],True)]*5)
    # Every relevant zoom node and every local trigger, in both directions.
    points=[(list(r[1:4]),True) for r in records if (7,1,2,4)[r[-1]]&1]
    case('all-normal-triggers', [v for p in points+points[::-1] for v in [p]*3])
    for name,p in (('free-wall',[-37.666668,1784,-3751]),('bridge109',[-507,1234.333333,-1550]),
                   ('bridge110',[-507,1267.666667,-1750]),('bridge111',[-507,1289,-2100])):
        case(name,[(p,True)]*60,-1,3)
    for preset in (1,3):
        case('profile-preset-'+str(preset),[([-2089,332,687],True)]*20+[([0,1800,0],True)]*20+[([0,1800,800],True)]*20)
        for c in cases[-1]['commands']:c['preset']=preset
    return cases

def initialize(lib,s):
    ref.configure(lib);contact.load(lib,'real')
    p=s['commands'][0]['player'];eye=[p[0],p[1]+375,p[2]-850];rot=[340,180,0]
    lib.composition_init((F*3)(*p),F(p[1]),(F*3)(*eye),(F*3)(*rot))
    lib.composition_seed(F(s['history']),s['counter'])
    return p,eye,rot

def select_state(lib):
    return [C.c_int.in_dll(lib,n).value for n in ('D_8037C010','D_8037C014','selected_profile','last_configured')]

def snapshot(lib,c):
    result=free.step(lib,c)
    return free.packed(*result)+struct.pack('>4i',*select_state(lib)),result

def golden(opt):
    lib=ref.library(opt);out={}
    for s in schedules():
        initialize(lib,s);stream=[];states=[]
        for i,c in enumerate(s['commands']):
            packed,result=snapshot(lib,c);stream.append(packed)
            if not states or states[-1][1:]!=result[1]+select_state(lib):states.append([i+1,*result[1],*select_state(lib)])
        out[s['name']]=dict(updates=len(stream),sha256=hashlib.sha256(b''.join(stream)).hexdigest(),transitions=states)
    ref.configure(lib);buf=(C.c_int*2000)();n=lib.zone_groups(buf)
    return dict(setup_sha256=hashlib.sha256(camera.ASSET.read_bytes()).hexdigest(),
        groups_sha256=hashlib.sha256(struct.pack('>'+str(n)+'i',*buf[:n])).hexdigest(),groups=27,cases=out)
