"""Externally prescribed post-horizontal-response velocities, no physics tuning.
Real static geometry; initial floor history is established by six stationary
original queries. No volume-contact response, water controller or slide states.
"""
import ctypes as C
import hashlib
import struct
F=C.c_float
class State(C.Structure):
    _fields_=[('position',F*3),('vy',F),('height',F),('grounded',C.c_uint32),('falling',C.c_uint32)]
class Frame(C.Structure):
    _fields_=[('previous',F*3),('candidate',F*3),('requested',F*3),('normal',F*3),('grounded',C.c_uint32)]

def schedules():
    return {
      'plateau_ledge':((0,1800,391.666779),-1,True,[(0,500,1/60)]*90,0x9db1),
      'flat_walk':((0,1800,0),-1,True,[(0,100,1/60)]*30,0x9db1),
      'slope_down':((-2094,133.333344,-383.666656),-1,True,[(353.55339,-353.55339,.05)]*4,0x9db1),
      'slope_up':((-2076.322266,99.449371,-401.34433),-1,True,[(-353.55339,353.55339,.05)]*4,0x9db1),
      'floor_reacquisition':((0,1850,0),-100,False,[(0,0,1/60)]*25,0x9db1),
      'complete_void':((9000,100,9000),-1,True,[(0,100,.05)]*10,0x9db1),
      'bridge_tutorial':((0,1576,-1800),-1,True,[(0,-100,1/60)]*30,0),
      'bridge_full':((0,1576,-1800),-1,True,[(0,-100,1/60)]*30,0x9db1),
      'steep_no_body_LIMITATION':((-3833.333252,2024.666626,-3166.666748),-600,False,[(0,0,.05)]*2,0x9db1),
      'wall_no_body_LIMITATION':((-37.666668,1784,-3751),-1,True,[(0,-500,.05)]*1,0x9db1),
    }

def neighbors(value):
    n=struct.unpack('=I',struct.pack('=f',value))[0]
    return [struct.unpack('=f',struct.pack('=I',n+d))[0] for d in (-1,0,1)]

def boundaries():
    rows=[]
    for ny in (*neighbors(.432),*neighbors(.9),1.0):
        for gap in (*neighbors(5.),*neighbors(30.),0.,-1.):
            for grounded,dy in ((1,-1.),(0,-1.),(1,0.),(1,1.)):
                rows.append((ny,gap,grounded,dy))
    return rows

def packed(s,f,floor):
    # Big endian scalar fields only; no padding or host pointers.
    return struct.pack('>5f2I12fI',*s.position,s.vy,s.height,s.grounded,s.falling,
                       *f.previous,*f.candidate,*f.requested,*f.normal,f.grounded)+floor

def digest(blobs):return hashlib.sha256(b''.join(blobs)).hexdigest()
