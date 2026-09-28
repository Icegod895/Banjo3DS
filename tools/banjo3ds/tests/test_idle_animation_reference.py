"""006F unblended time-zero golden contract, independent of production."""
from collections import Counter
import hashlib
import shutil
import struct
import unittest

from idle_animation_reference import (
    ROOT, ANIMATION_SHA, CANONICAL_TIME, F, f32, idle_reference, transform_hash,
)
from banjo_pose_reference import canonical_reference


@unittest.skipUnless(shutil.which('cc') and (ROOT/'assets/anim/006F.anim.bin').exists(),
                     'Requires host C compiler and extracted 006F asset')
class TestIdleAnimationReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.animation,cls.bones,cls.channels,cls.pose=idle_reference()

    def test_real_animation_layout(self):
        animation=self.animation
        data=(ROOT/'assets/anim/006F.anim.bin').read_bytes()
        self.assertEqual(len(data),12316)
        self.assertEqual(hashlib.sha256(data).hexdigest(),ANIMATION_SHA)
        self.assertEqual((animation.first,animation.last),(0,110))
        self.assertEqual(len(animation.channels),81)
        self.assertEqual(sum(len(keys) for b,c,keys in animation.channels),2996)
        self.assertEqual(len({b for b,c,k in animation.channels}),26)
        self.assertEqual(Counter(c for b,c,k in animation.channels),
                         {0:18,1:26,2:20,3:2,4:2,5:2,6:4,7:4,8:3})
        self.assertEqual(Counter(word>>14 for b,c,keys in animation.channels for word,v in keys),
                         {0:2464,1:52,2:34,3:446})
        self.assertTrue(all((keys[0][0]&0x3fff)==0 and (keys[-1][0]&0x3fff)==110
                            for b,c,keys in animation.channels))

    def test_exact_keys_linear_and_catmull_rom(self):
        value=self.animation.channel_value
        self.assertEqual(value(1,1,5),857/64)
        # Actual cubic segment: values [0,0,857/64,-1472/64], local t=0.5.
        self.assertEqual(value(1,1,2.5),8.9697265625)
        self.assertNotEqual(value(1,1,2.5),(857/64)*0.5)
        self.assertEqual(value(6,0,1),-218/64)
        self.assertEqual(value(6,0,1.5),(-218-175)/128)
        self.assertEqual(value(3,7,55),-1/64)  # Constant two-key channel.

    def test_start_end_and_controller_wrap(self):
        animation=self.animation
        self.assertEqual(CANONICAL_TIME,0.0)
        self.assertEqual(animation.library.frame(0),0)
        self.assertEqual(animation.library.frame(1),110)
        self.assertEqual(animation.channel_value(1,1,0),0)
        self.assertEqual(animation.channel_value(1,1,110),0)
        self.assertEqual(animation.library.normalized(110),f32(0.999999))
        self.assertEqual(animation.library.frame(animation.library.normalized(110)),
                         109.99988555908203)
        # Original looping controller, not interpolation from last to first key.
        wrapped=animation.library.loop_time(0.5,2.75,5.5)
        self.assertEqual(wrapped,0)
        self.assertEqual(animation.transforms(wrapped)[0],self.bones)
        self.assertNotEqual(animation.transforms(1)[0][107],self.bones[107])
        # Tail spline clamps its parameter. It can overshoot immediately after
        # the final key, but the normal controller never evaluates time > 1.
        self.assertEqual(animation.channel_value(1,1,110.5),2)
        self.assertEqual(animation.channel_value(1,1,111),0)

    def test_defaults_and_real_quaternion_edge(self):
        identity=(0.,0.,0.,1.,1.,1.,1.,0.,0.,0.)
        self.assertEqual(len(self.bones),109)
        self.assertEqual(self.bones[2],identity)  # Entirely absent bone.
        self.assertEqual(self.channels[1],[0.,0.,0.,1.,1.,1.,0.,0.,0.])
        self.assertEqual(self.bones[3],(0.,0.,0.,1.,1.,1.,1.,0.,-0.015625,0.))
        self.assertEqual(sum(b!=identity for b in self.bones),21)
        # 180-degree yaw forces matrix-to-quaternion's nonpositive trace branch.
        self.assertEqual(self.bones[107][:4],(0.,1.,0.,-4.371138828673793e-08))
        self.assertEqual(self.bones[107][4:],(0.140625,)*3+(0.,-1.25,0.015625))
        self.assertEqual(self.animation.channel_value(107,1,9),180)
        self.assertEqual(self.animation.channel_value(107,1,9.5),90)
        self.assertEqual(self.animation.channel_value(107,1,10),0)
        self.assertEqual(self.bones[6][:4],
                         (-0.0348924845457077,0.0006994791910983622,
                          -0.020030464977025986,0.9991900324821472))

    def test_bone_transform_golden(self):
        self.assertEqual(transform_hash(self.bones),
                         '2cf3dfb9c5ebe3517ed63cda2f7b445a0cc60840870be668d16ca7c90c35b87b')
        matrices=self.animation.matrices(self.bones)
        self.assertEqual(len(matrices),60)
        # Matrix IDs are not animation bone IDs: each matrix record maps them.
        data=(ROOT/'assets/model/034D.model.bin').read_bytes()
        start=struct.unpack_from('>I',data,24)[0]
        self.assertEqual(struct.unpack_from('>f',data,start)[0],10)
        self.assertEqual(struct.unpack_from('>hh',data,start+8+9*16+12),(7,8))
        self.assertEqual(struct.unpack_from('>hh',data,start+8+31*16+12),(19,30))

    def test_posed_geometry_golden_and_reference_difference(self):
        pose=self.pose; summary=pose.summary(); boneless=canonical_reference()
        self.assertEqual(pose.calls,boneless.calls)
        self.assertEqual((len(pose.calls),summary['triangles'],summary['loads'],summary['used_loads']),
                         (49,695,723,723))
        self.assertEqual(summary['triangle_xyz_be_f32_sha256'],
                         '7536cd507d67f2de4e3ab1bec2beb707fd902b361995b8c6ce5d208e16e2cc6c')
        self.assertEqual(summary['bounds'],[(-47.63481140136719,47.64100646972656),
                                          (0.11383056640625,121.84375),(-24.,54.613525390625)])
        self.assertEqual(sum(a['xyz']!=b['xyz'] for a,b in zip(pose.loads,boneless.loads)),723)
        self.assertEqual(pose.triangles,boneless.triangles)
        self.assertEqual(summary['final_cache'],boneless.summary()['final_cache'])
        self.assertEqual(len(pose.rsp),1)
        self.assertEqual(len(pose.cpu),1)
        samples={e['vertex']:e['xyz'] for e in pose.loads}
        expected={0:(7.2082061767578125,16.11517333984375,-10.6373291015625),
                  120:(-26.947433471679688,10.1202392578125,14.070999145507812),
                  240:(29.744400024414062,41.09027099609375,12.296249389648438),
                  360:(-29.796356201171875,62.13224792480469,-11.524093627929688),
                  627:(9.740325927734375,113.84375,21.04571533203125),
                  894:(12.,86.84375,-23.)}
        self.assertEqual({i:samples[i] for i in expected},expected)

    def test_existing_exports_remain_byte_identical(self):
        # Production imported only here for regression comparison, never by
        # the independent animation/pose helper or to construct golden values.
        from tools.banjo3ds.export_3ds_model import export_canonical_banjo,export_models,export_scene
        opa,xlu,banjo=[ROOT/f'assets/model/{name}.model.bin' for name in ('14CF','14D0','034D')]
        outputs=[(export_canonical_banjo(banjo),
                  '34476fadcd623564674ce815635076058dc8d71dd012775b522e9b80e8859c52'),
                 (export_models(opa,xlu),
                  'fbcf9cf77aba9779db18049990204c921d0012de83c2312d36b288ec5f087057'),
                 (export_scene(opa,xlu,banjo,runtime_actor=False),
                  'fbcafd19d2f57c6b0ca5abd9132f0173f3a044d12d2e9b14d038eb1267659f43')]
        for output,expected in outputs:
            self.assertEqual(hashlib.sha256(output.encode()).hexdigest(),expected)
        # The viewer now opts into the idle bake. The explicit boneless scene
        # above remains byte-identical; serialized idle output is tested in
        # test_static_idle, without depending on a pre-existing build artifact.


if __name__=='__main__':
    unittest.main()
