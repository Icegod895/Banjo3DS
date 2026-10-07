"""E.2A: read-only observers around E.2's compiled ORIGINAL functions.
No production body/frame/ground algorithm is used. Physics/state queries use
separately compiled E.1 original snippets, not the production candidate helper.
"""
import ctypes as C
import functools
from pathlib import Path
import subprocess
import tempfile
import body_reference
import horizontal_reference
from segment_reference import ROOT, FLAGS, function
F=C.c_float

@functools.lru_cache(None)
def library(opt):
    original=body_reference.library(opt)
    text=(Path(original._tmp.name)/'ref.c').read_text()
    fn=function('src/core2/code_C4B0.c','func_8029350C')
    assert text.count(fn)==1
    observed=fn.replace('{','{\n unsigned observation_index=fo.floors++;\n fo.parity[observation_index]=parity;\n memcpy(fo.candidate[observation_index],arg0,12);\n floor_ref_snapshot(fo.before[observation_index]);',1)
    observed=observed[:observed.rfind('}')]+ '\n floor_ref_snapshot(fo.after[observation_index]);\n}\n'
    # Count the STATIC map line supplier, including floor's direct special query,
    # not only the world-line wrapper (which legitimately omits that call).
    begin=text.index('BKCollisionTriangle *func_80309B48(')
    brace=text.index('{',begin)
    text=text[:brace+1]+'\n ++frame_map_lines;'+text[brace+1:]
    text='static unsigned frame_map_lines;\n'+text
    text=text.replace(fn,'#include "body_frame_observer.h"\nstatic BodyFrameObservation fo;\n'+observed)
    text+='''
void frame_ref_reset(void){memset(&fo,0,sizeof(fo));memset(&trace,0,sizeof(trace));frame_map_lines=0;}
void frame_ref_observation(BodyFrameObservation*out){
 fo.spheres=trace.sphere_calls;fo.moving=trace.moving_calls;fo.lines=frame_map_lines;*out=fo;
}
'''
    tmp=tempfile.TemporaryDirectory(prefix='body-frame-original-');p=Path(tmp.name)
    (p/'ref.c').write_text(text)
    trig=horizontal_reference.library(opt);td=Path(trig.temporary.name)
    subprocess.run(['cc',*FLAGS,opt,'-shared','-fPIC','-I'+str(Path(__file__).parent),str(p/'ref.c'),
        str(td/'sinf.c'),str(td/'cosf.c'),'-lm','-o',str(p/'ref.so')],check=True)
    lib=C.CDLL(str(p/'ref.so'));lib._tmp=tmp
    lib.ref_load.argtypes=[C.c_int,C.c_void_p];lib.body_ref_vertex.argtypes=[C.c_uint,C.c_uint,C.c_void_p]
    lib.floor_ref_step.argtypes=[C.POINTER(F),F,C.c_uint32,C.c_uint]
    lib.floor_ref_snapshot.argtypes=[C.c_void_p]
    lib.body_ref_step.argtypes=[C.POINTER(F),C.POINTER(F),C.POINTER(F),C.c_uint,C.c_void_p,C.c_void_p,C.c_void_p]
    return lib
