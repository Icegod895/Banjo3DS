import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import segment_reference as ref
import segment_corpus as corpus
from world_query_reference import original

F=C.c_float
class Model(C.Structure):
    _fields_=[('vertices',C.c_void_p),('collision',C.c_void_p),('grid',C.c_int16*11),('nv',C.c_uint16),('radius',C.c_int16),('role',C.c_uint16)]
class Hit(C.Structure):
    _fields_=[('position',F*3),('normal',F*3),('role',C.c_int32),('occurrence',C.c_int32),('cell',C.c_int32),('surface',C.c_int32),('flags',C.c_uint32),('indices',C.c_uint16*3)]

class WorldSegmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='world-segment-tests-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs=[];cls.refs=[]
        for opt in ('-O0','-O2'):
            so=Path(cls.tmp.name)/(opt+'.so')
            subprocess.run(['cc',*ref.FLAGS,opt,'-Wall','-Wextra','-Werror','-shared','-fPIC',str(ref.ROOT/'tools/banjo3ds/world_query/segment.c'),'-lm','-o',str(so)],check=True)
            lib=C.CDLL(str(so));mp=C.POINTER(Model);fp=C.POINTER(F)
            lib.bq_open.argtypes=[mp,C.c_void_p,C.c_size_t];lib.bq_open.restype=C.c_int
            lib.bq_segment.argtypes=[mp,mp,fp,fp,C.c_uint32,C.POINTER(Hit)];lib.bq_segment.restype=C.c_int
            lib.bq_camera_terrain.argtypes=[mp,mp,fp,fp];lib.bq_camera_terrain.restype=C.c_int
            cls.libs.append(lib);cls.refs.append(ref.library(opt))
        cls.packet=[original(a,r)['packet'] for r,a in enumerate((0x14cf,0x14d0))]

    def models(self,lib,packets=None):
        buffers=[C.create_string_buffer(p) for p in (packets or self.packet)];models=[Model(),Model()]
        for m,b in zip(models,buffers):self.assertEqual(lib.bq_open(C.byref(m),b,len(b)-1),1)
        return models,buffers

    def production(self,lib,models,a,b,mask):
        end=(F*3)(*b);out=Hit();C.memset(C.byref(out),0xa5,C.sizeof(out));old=bytes(out)
        h=lib.bq_segment(C.byref(models[0]),C.byref(models[1]),(F*3)(*a),end,mask,C.byref(out))
        if h==1:
            self.assertEqual(bytes(out.position),bytes(end))
            ids=[out.role,out.occurrence,out.cell,out.surface,C.c_int32(out.flags).value,*out.indices]
            return h,list(end),list(out.normal),ids
        self.assertEqual(bytes(out),old)
        self.assertEqual(bytes(end),bytes((F*3)(*b)))
        return h,list(end),[101.,102.,103.],[-1]*8

    def test_real_corpus_bit_exact_O0_O2_and_frozen_reference(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/world_segment_golden.json').read_text())
        for lib,oracle in zip(self.libs,self.refs):
            ref.load_real(oracle);models,buffers=self.models(lib)
            self.assertEqual(corpus.extended_golden(oracle),frozen)
            for i,(name,a,b,mask) in enumerate(corpus.corpus()):
                want=corpus.query(oracle,a,b,mask);got=self.production(lib,models,a,b,mask)
                self.assertEqual(corpus.packed(got),corpus.packed(want),(i,name,a,b,mask,got,want))

    def test_camera_adapter_original_callchain_bit_exact(self):
        for lib,oracle in zip(self.libs,self.refs):
            ref.load_real(oracle);models,buffers=self.models(lib)
            for p in corpus.cameras():
                h=C.c_int32();want=oracle.ref_terrain((F*3)(*p),C.byref(h));got=F(999)
                result=lib.bq_camera_terrain(C.byref(models[0]),C.byref(models[1]),(F*3)(*p),C.byref(got))
                self.assertEqual((result,struct.pack('>f',got.value)),(h.value,struct.pack('>f',want)),p)

    def test_invalid_packets_and_defined_query_domain(self):
        lib=self.libs[1];models,buffers=self.models(lib)
        self.assertEqual(lib.bq_open(C.byref(Model()),buffers[0],64),0)
        self.assertEqual(self.production(lib,models,(float('inf'),0,0),(0,0,0),0)[0],-1)
        # Original global array has 100 entries; don't execute UB in reference.
        self.assertEqual(self.production(lib,models,(-9000,-500,-8000),(9000,7000,8000),0)[0],-1)

    def test_explicit_wrapper_endpoint_and_normal_cases(self):
        for lib,oracle in zip(self.libs,self.refs):
            for label,o,x,a,b,mask,expected in corpus.wrapper_cases():
                packets=[]
                for role,spec in enumerate((o,x)):
                    raw,packet=corpus.synthetic(role,*spec);packets.append(packet)
                    oracle.ref_load(role,C.create_string_buffer(raw))
                models,buffers=self.models(lib,packets)
                want=corpus.query(oracle,a,b,mask);got=self.production(lib,models,a,b,mask)
                self.assertEqual(corpus.packed(got),corpus.packed(want),label)
                self.assertEqual(got[3][0] if got[0] else -1,expected,label)
                if label=='backface-keeps-down-normal':self.assertEqual(got[2][1],-1)
                if label=='two-sided-flips-normal':self.assertEqual(got[2][1],1)
            ref.load_real(oracle)

    def test_cell102_order_observable_in_normal_and_triangle(self):
        a=(772.25,2868.,-5206.);b=(772.25,2568.,-5206.)
        frozen=json.loads((Path(__file__).parent/'fixtures/world_segment_golden.json').read_text())
        for lib,oracle in zip(self.libs,self.refs):
            ref.load_real(oracle);models,buffers=self.models(lib)
            original=corpus.query(oracle,a,b,0)
            self.assertEqual(corpus.packed(original),corpus.packed(frozen['cell102_witness_original']))
            self.assertEqual(corpus.packed(self.production(lib,models,a,b,0)),corpus.packed(original))
            oracle.ref_load(0,C.create_string_buffer(corpus.cell102_variant()))
            reordered=corpus.query(oracle,a,b,0)
            self.assertEqual(corpus.packed(reordered),corpus.packed(frozen['cell102_witness_reordered']))
            self.assertEqual(original[1],reordered[1])
            self.assertNotEqual(original[2],reordered[2])
            self.assertNotEqual(original[3][5:],reordered[3][5:])
            self.assertEqual(original[3][2],102)
            ref.load_real(oracle)

    def test_unaligned_packet_and_atomic_errors(self):
        for lib in self.libs:
            padded=[C.create_string_buffer(b'x'+p) for p in self.packet]
            models=[Model(),Model()]
            for m,b,p in zip(models,padded,self.packet):
                self.assertEqual(lib.bq_open(C.byref(m),C.byref(b,1),len(p)),1)
            ref.load_real(self.refs[0])
            a=(0,1900,0);b=(0,1700,0)
            self.assertEqual(corpus.packed(self.production(lib,models,a,b,0)),corpus.packed(corpus.query(self.refs[0],a,b,0)))
            out=F(123)
            self.assertEqual(lib.bq_camera_terrain(C.byref(models[0]),C.byref(models[1]),(F*3)(float('nan'),0,0),C.byref(out)),-1)
            self.assertEqual(out.value,123)
