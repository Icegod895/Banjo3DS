"""Physical input -> accepted runtime -> original-decomp manual camera parity."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import unittest
import manual_reference as original
import manual_corpus as corpus
import test_camera_manual_runtime as manual
import test_player_input as inputs
import test_camera_runtime as runtime
F=C.c_float
ROOT=original.ROOT

class PhysicalAdapter:
    def __init__(self,source):self.source=source;self.reset()
    def reset(self):self.state=inputs.State()
    def translate(self,lib,buttons):
        k=inputs.X if buttons&1 else 0;x=y=0
        # N64 R + C is possible via X + D-pad/C-stick, never X + shoulder R.
        if self.source=='combo' and not buttons&1:
            if buttons&14:k|=inputs.R
            for bit,face in ((2,inputs.Y),(4,inputs.A),(8,inputs.B)):
                if buttons&bit:k|=face
        elif self.source=='cstick':
            if buttons&2:x=-60
            if buttons&4:
                if x:k|=inputs.RIGHT # independent opposing sources stay distinct
                else:x=60
            if buttons&8:y=-60
        else:
            for bit,key in ((2,inputs.LEFT),(4,inputs.RIGHT),(8,inputs.DOWN)):
                if buttons&bit:k|=key
        return inputs.read(lib,self.state,k,x,y).manual

class PhysicalRuntimeTests(unittest.TestCase):
    manual_observer=True
    start=runtime.CameraRuntimeTests.start
    move=runtime.CameraRuntimeTests.move
    run_history=manual.ManualRuntimeTests.run_history
    @classmethod
    def setUpClass(cls):
        manual.ManualRuntimeTests.setUpClass.__func__(cls)
        for lib in cls.libs:inputs.bind(lib)

    def test_every_frozen_camera_history_through_all_physical_sources_O0_O2(self):
        frozen=json.loads((Path(__file__).parent/'fixtures/camera_manual_golden.json').read_text())
        for opt,lib in zip(('-O0','-O2'),self.libs):
            ref=original.library(opt)
            for source in ('dpad','cstick','combo'):
                self.physical_adapter=PhysicalAdapter(source);streams=[]
                for spec in corpus.schedules():
                    stream,_=self.run_history(lib,ref,spec);streams.append(stream)
                self.assertEqual(hashlib.sha256(b''.join(streams)).hexdigest(),frozen['sha256'],(opt,source))
        del self.physical_adapter

    def test_neutral_translation_preserves_player_floor_body_bridge_and_camera(self):
        for lib in self.libs:
            for bits in (0,0x9db1):
                for start in ((0,1800,0),(0,1576,-1800),(-37.666668,1784,-3751),(-2094,133.333344,-383.666656)):
                    a,p=self.start(lib,start);b,q=self.start(lib,start);physical=inputs.State();previous=0
                    for s in (a,b):lib.cameraRuntimeSetLearnedAbilities(C.byref(s),bits)
                    for i in range(180):
                        keys=(inputs.A if 20<=i<30 else 0)|(inputs.Y if 60<=i<75 else 0)
                        # These logical inputs have no active gameplay consumer.
                        if i%7==0:keys|=inputs.L|inputs.B|inputs.UP
                        frame=inputs.read(lib,physical,keys,i%51-25,25-i%51)
                        self.assertEqual(frame.manual,0)
                        down=keys&~previous;previous=keys
                        for s,player,jump,suppressed in ((a,p,frame.jump,frame.suppress),
                                (b,q,bool(down&inputs.A),bool(keys&inputs.Y))):
                            lib.cameraRuntimeManualInput(C.byref(s),0,35)
                            out=(F*3)();lib.cameraRuntimeMovementInput(C.byref(s),False,0,0,156 if i<100 else 0,out)
                            self.assertEqual(self.move(lib,s,player,*out,jump=jump,orbit=suppressed),1)
                        self.assertEqual(bytes(p),bytes(q),(bits,start,i))
                        for field in ('manual','bridge','body','player_ground','world_bridge','view'):
                            self.assertEqual(bytes(getattr(a,field)),bytes(getattr(b,field)),(bits,start,i,field))

    def test_modifier_prevents_real_jump_and_Y_suppression_until_rearmed(self):
        for lib in self.libs:
            s,p=self.start(lib);state=inputs.State()
            for keys,want_jump in ((inputs.R|inputs.A,False),(inputs.A,False),(inputs.A,False),(0,False),(inputs.A,True)):
                f=inputs.read(lib,state,keys)
                lib.cameraRuntimeManualInput(C.byref(s),f.manual,35)
                self.assertEqual(self.move(lib,s,p,jump=f.jump,orbit=f.suppress),1)
                self.assertEqual(not p.motion.grounded,want_jump)
            for keys,suppressed in ((inputs.Y,True),(inputs.R|inputs.Y,False)):
                a,p=self.start(lib);b,q=self.start(lib);f=inputs.read(lib,inputs.State(),keys)
                self.assertEqual(f.suppress,suppressed)
                for _ in range(30):
                    # Camera request cannot alter physics; same accepted input
                    # and explicit suppression on comparison runtime.
                    lib.cameraRuntimeManualInput(C.byref(a),f.manual,35)
                    self.assertEqual(self.move(lib,a,p,y=156,jump=False,orbit=f.suppress),1)
                    self.assertEqual(self.move(lib,b,q,y=156,jump=False,orbit=suppressed),1)
                    self.assertEqual(bytes(p),bytes(q))
                self.assertEqual((p.motion.actor.x,p.motion.actor.z)==(0,0),suppressed)

    def test_live_viewer_boundary_preserves_debug_and_uses_raw_cstick(self):
        source=(ROOT/'platform/3ds/source/main.c').read_text()
        self.assertIn('if (BANJO_DEBUG_CAMERA)\n            cameraUpdate(down, held, &pad, dt);',source)
        self.assertIn('if (down & KEY_START)',source)
        self.assertIn('hidCstickRead(&cstick)',source)
        self.assertIn('playerInputUpdate(&playerInput, held, cstick.dx, cstick.dy)',source)
        self.assertIn('BANJO_DEBUG_CAMERA ? (down & KEY_A) != 0 : (controls.jump_pressed && !firstPersonBlocks)',source)
        self.assertIn('BANJO_DEBUG_CAMERA ? (held & KEY_Y) != 0 : (controls.suppress_movement || firstPersonBlocks)',source)
        self.assertIn('BANJO_DEBUG_CAMERA ? 0 : controls.manual',source)
        self.assertLess(source.index('hidScanInput();'),source.index('hidCstickRead(&cstick)'))
        self.assertLess(source.index('cameraRuntimeMovementInput(&rareCamera'),source.index('cameraRuntimeMove(&rareCamera'))
        self.assertNotIn('hidKeysDownRepeat',source)
        self.assertNotIn('irrstInit(',source)
