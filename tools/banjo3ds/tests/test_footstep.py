"""Host tests for Rare grounded footsteps. No Rare sample bytes."""

import ctypes as C
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.banjo3ds.footstep_asset import (
    FOOT_SFX_IDS,
    FootClip,
    decode_clip,
    main,
    render_header,
)
from tools.banjo3ds.sfx_bank import SfxBankError
from tools.banjo3ds.sfx_probe_asset import resolve_header_path
from tools.banjo3ds.tests.test_sfx_bank import _book, _frame as _adpcm_frame, _synthetic_bank


ROOT = Path(__file__).resolve().parents[3]
F = C.c_float
IDLE, CREEP, SLOW, WALK, FAST = 0, 1, 2, 3, 4
SM = 1
GAMEPLAY = (
    "camera_runtime.c",
    "movement.c",
    "player_crouch.c",
    "player_ground.c",
    "player_input.c",
    "player_runtime.c",
    "walk_animation.c",
)
FRAME_COMMENT = (
    "C3D_FrameEnd(0);\n"
    "        /* The crouch-coast latch sustains looped SFX_18. "
    "The first frame without it plays SFX_19 once. */\n"
    "        sfxProbe3dsFrame(playerCrouchSlideSfx());"
)


class State(C.Structure):
    _fields_ = [("rng", C.c_uint), ("unk1E", C.c_int), ("ready", C.c_int)]


class Frame(C.Structure):
    _fields_ = [
        ("gait_before", C.c_int),
        ("phase_before", F),
        ("initialized_before", C.c_int),
        ("gait_after", C.c_int),
        ("phase_after", F),
        ("initialized_after", C.c_int),
        ("animated", C.c_int),
        ("grounded", C.c_int),
        ("crouch", C.c_int),
        ("jumping", C.c_int),
        ("map_id", C.c_int),
        ("flags", C.c_uint32),
        ("floor_y", F),
        ("player_y", F),
        ("floor_valid", C.c_int),
    ]


class Play(C.Structure):
    _fields_ = [
        ("sfx_id", C.c_int),
        ("type", C.c_int),
        ("foot", C.c_int),
        ("source", C.c_int),
        ("loudness", C.c_int),
        ("pitch", F),
        ("rate", F),
    ]


class Row(C.Structure):
    _fields_ = [
        ("type", C.c_int),
        ("sfx_id", C.c_int),
        ("pitch_a", F),
        ("pitch_b", F),
        ("jitter", F),
        ("loudness", C.c_int),
    ]


def _bind(lib):
    lib.banjo_foot_reset.argtypes = [C.POINTER(State)]
    lib.banjo_foot_surface.argtypes = [C.c_int, C.c_uint32, F, F]
    lib.banjo_foot_surface.restype = C.c_int
    lib.banjo_foot_row.argtypes = [C.c_int, C.POINTER(Row)]
    lib.banjo_foot_row.restype = C.c_int
    lib.banjo_foot_gait_marks.argtypes = [C.c_int, C.POINTER(F), C.POINTER(C.c_int)]
    lib.banjo_foot_gait_marks.restype = C.c_int
    lib.banjo_foot_unit.argtypes = [C.POINTER(C.c_uint)]
    lib.banjo_foot_unit.restype = F
    lib.banjo_foot_vary.argtypes = [F, F, F]
    lib.banjo_foot_vary.restype = F
    lib.banjo_foot_cents_ratio.argtypes = [C.c_int]
    lib.banjo_foot_cents_ratio.restype = F
    lib.banjo_foot_key_ratio.argtypes = [C.c_int, C.c_int, C.c_int]
    lib.banjo_foot_key_ratio.restype = F
    lib.banjo_foot_output_rate.argtypes = [F, C.c_int, C.c_int, C.c_int]
    lib.banjo_foot_output_rate.restype = F
    lib.banjo_foot_source.argtypes = [C.POINTER(State)]
    lib.banjo_foot_source.restype = C.c_int
    lib.banjo_foot_observe.argtypes = [C.POINTER(State), C.POINTER(Frame), C.POINTER(Play), C.c_int]
    lib.banjo_foot_observe.restype = C.c_int


def _frame(**overrides):
    frame = Frame(
        gait_before=WALK,
        phase_before=0.3,
        initialized_before=1,
        gait_after=WALK,
        phase_after=0.5,
        initialized_after=1,
        animated=1,
        grounded=1,
        crouch=0,
        jumping=0,
        map_id=SM,
        flags=0x100,
        floor_y=100.0,
        player_y=100.0,
        floor_valid=1,
    )
    for name, value in overrides.items():
        setattr(frame, name, value)
    return frame


def _observe(lib, state, **overrides):
    plays = (Play * 2)()
    count = lib.banjo_foot_observe(state, C.byref(_frame(**overrides)), plays, 2)
    return count, plays


def _fresh(lib):
    state = State()
    lib.banjo_foot_reset(C.byref(state))
    return state


class FootstepHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="banjo-foot-host-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs = []
        sources = [
            ROOT / "tools/banjo3ds/pose/pose.c",
            ROOT / "tools/banjo3ds/gait/gait.c",
            ROOT / "tools/banjo3ds/footstep/footstep.c",
        ]
        includes = [
            "-I" + str(ROOT / "tools/banjo3ds/pose"),
            "-I" + str(ROOT / "tools/banjo3ds/gait"),
            "-I" + str(ROOT / "tools/banjo3ds/footstep"),
        ]
        for opt in ("-O0", "-O2"):
            out = Path(cls.tmp.name) / f"{opt}.so"
            subprocess.run(
                ["cc", "-std=c99", opt, "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                 "-ffp-contract=off", "-fno-fast-math", "-fexcess-precision=standard",
                 *includes, *map(str, sources), "-lm", "-o", str(out)],
                check=True,
            )
            lib = C.CDLL(str(out))
            _bind(lib)
            cls.libs.append(lib)

    def test_surface_uses_flags_and_the_spiral_mountain_row(self):
        expected = (
            (SM, 0, 0),
            (SM, 0x100, 1),
            (SM, 0x200, 7),
            (SM, 0x400, 6),
            (SM, 0x800, 5),
            (SM, 0x1000, 1),
            (SM, 0x600, 6),
            (SM, 0x1C00, 1),
            (SM, 0x80000700, 8),
            (SM, 0x80000400, 5),
            (SM, 0x80000300, 6),
            (SM, 0x81010400, 5),
            (SM, 0x80000000, 1),
            (SM, 0x80000100, 10),
            (SM, 0x80000900, 11),
            (SM, 0x80001000, 1),
            (SM, 0x80000F00, 1),
            (0x0D, 0x100, 8),
            (0x0D, 0x200, 11),
            (2, 0x400, 6),
            (0x40, 0x1000, 7),
            (99, 0x400, 1),
            (99, 0x80000700, 8),
        )
        for lib in self.libs:
            for map_id, flags, surface in expected:
                with self.subTest(map_id=map_id, flags=flags):
                    self.assertEqual(lib.banjo_foot_surface(map_id, flags, 10.0, 10.0), surface)
            self.assertEqual(lib.banjo_foot_surface(SM, 0x400, 100.0, 50.0), 4)
            self.assertEqual(lib.banjo_foot_surface(SM, 0x400, 100.0, 40.1), 4)
            self.assertEqual(lib.banjo_foot_surface(SM, 0x400, 100.0, 40.0), 6)
            self.assertEqual(lib.banjo_foot_surface(SM, 0x400, 100.0, 100.0), 6)
            self.assertEqual(lib.banjo_foot_surface(SM, 0x400, 100.0, 101.0), 6)
            self.assertEqual(lib.banjo_foot_surface(SM, 0, 100.0, 50.0), 0)

    def test_sound_rows_match_the_walk_table(self):
        rows = {
            8: (0x5, 0.7, 0.8, 0.05, 17000),
            5: (0x26, 1.0, 1.2, 0.05, 9000),
            6: (0x6, 1.0, 1.2, 0.05, 7000),
            1: (0x8, 1.0, 1.2, 0.05, 9000),
            4: (0x10, 1.0, 1.2, 0.05, 13000),
            7: (0x28, 1.0, 1.0, 0.05, 10000),
            10: (0x99, 1.0, 1.1, 0.05, 21000),
            11: (0x10, 0.5, 0.55, 0.01, 16000),
        }
        for lib in self.libs:
            for surface, (sfx, pitch_a, pitch_b, jitter, loudness) in rows.items():
                row = Row()
                self.assertEqual(lib.banjo_foot_row(surface, C.byref(row)), 1)
                self.assertEqual(row.sfx_id, sfx)
                self.assertEqual(row.pitch_a, F(pitch_a).value)
                self.assertEqual(row.pitch_b, F(pitch_b).value)
                self.assertEqual(row.jitter, F(jitter).value)
                self.assertEqual(row.loudness, loudness)
            for missing in (0, 16):
                self.assertEqual(lib.banjo_foot_row(missing, C.byref(Row())), 0)

    def test_marks_follow_the_walk_updates(self):
        for lib in self.libs:
            marks = (F * 2)()
            feet = (C.c_int * 2)()
            self.assertEqual(lib.banjo_foot_gait_marks(IDLE, marks, feet), 0)
            self.assertEqual(lib.banjo_foot_gait_marks(CREEP, marks, feet), 2)
            self.assertEqual((feet[0], feet[1]), (4, 3))
            self.assertEqual((marks[0], marks[1]), (F(0.47).value, F(0.97).value))
            for gait in (SLOW, WALK, FAST):
                self.assertEqual(lib.banjo_foot_gait_marks(gait, marks, feet), 2)
                self.assertEqual((marks[0], marks[1]), (F(0.4).value, F(0.9).value))
                self.assertEqual((feet[0], feet[1]), (4, 3))

    def test_crossings_handle_wrap_skip_and_exact_marks(self):
        for lib in self.libs:
            marks = (F * 2)()
            feet = (C.c_int * 2)()
            lib.banjo_foot_gait_marks(WALK, marks, feet)
            state = _fresh(lib)
            count, plays = _observe(lib, C.byref(state), phase_before=0.3, phase_after=marks[0])
            self.assertEqual(count, 0)
            self.assertEqual(lib.banjo_foot_source(C.byref(state)), 0)
            count, plays = _observe(lib, C.byref(state), phase_before=marks[0], phase_after=0.6)
            self.assertEqual(count, 1)
            self.assertEqual(plays[0].foot, 4)
            self.assertEqual(plays[0].sfx_id, 0x8)
            count, _plays = _observe(lib, C.byref(_fresh(lib)), phase_before=0.5, phase_after=0.5)
            self.assertEqual(count, 0)
            count, plays = _observe(lib, C.byref(_fresh(lib)), phase_before=0.85, phase_after=0.10)
            self.assertEqual(count, 1)
            self.assertEqual(plays[0].foot, 3)
            count, plays = _observe(lib, C.byref(_fresh(lib)), phase_before=0.2, phase_after=0.95)
            self.assertEqual(count, 2)
            self.assertEqual((plays[0].foot, plays[1].foot), (4, 3))
            self.assertEqual((plays[0].source, plays[1].source), (0, 1))
            creep = (F * 2)()
            lib.banjo_foot_gait_marks(CREEP, creep, feet)
            count, plays = _observe(
                lib, C.byref(_fresh(lib)), gait_before=CREEP, gait_after=CREEP,
                phase_before=0.46, phase_after=0.48,
            )
            self.assertEqual(count, 1)
            self.assertEqual(plays[0].foot, 4)
            count, plays = _observe(
                lib, C.byref(_fresh(lib)), gait_before=CREEP, gait_after=CREEP,
                phase_before=0.96, phase_after=0.99,
            )
            self.assertEqual(count, 1)
            self.assertEqual(plays[0].foot, 3)
            self.assertEqual(creep[0], F(0.47).value)

    def test_gait_changes_do_not_invent_a_wrap(self):
        for lib in self.libs:
            count, plays = _observe(
                lib, C.byref(_fresh(lib)), gait_before=CREEP, gait_after=SLOW,
                phase_before=0.5, phase_after=0.5,
            )
            self.assertEqual(count, 1)
            self.assertEqual(plays[0].foot, 4)
            count, _plays = _observe(
                lib, C.byref(_fresh(lib)), gait_before=CREEP, gait_after=SLOW,
                phase_before=0.5, phase_after=0.3,
            )
            self.assertEqual(count, 0)
            count, _plays = _observe(
                lib, C.byref(_fresh(lib)), gait_before=WALK, gait_after=FAST,
                phase_before=0.50, phase_after=0.55,
            )
            self.assertEqual(count, 0)
            count, _plays = _observe(
                lib, C.byref(_fresh(lib)), gait_before=IDLE, gait_after=WALK,
                phase_before=0.8, phase_after=0.2,
            )
            self.assertEqual(count, 0)
            count, _plays = _observe(
                lib, C.byref(_fresh(lib)), gait_before=WALK, gait_after=IDLE,
                phase_before=0.3, phase_after=0.1,
            )
            self.assertEqual(count, 0)
            count, _plays = _observe(
                lib, C.byref(_fresh(lib)), initialized_before=0, phase_before=0.9,
                phase_after=0.2,
            )
            self.assertEqual(count, 0)

    def test_idle_air_crouch_and_a_missing_floor_stay_silent(self):
        silent = (
            {"gait_before": IDLE, "gait_after": IDLE, "phase_before": 0.2, "phase_after": 0.8},
            {"grounded": 0},
            {"jumping": 1},
            {"crouch": 1},
            {"animated": 0},
            {"floor_valid": 0},
            {"initialized_after": 0},
            {"flags": 0},
        )
        for lib in self.libs:
            for overrides in silent:
                state = _fresh(lib)
                count, _plays = _observe(lib, C.byref(state), **overrides)
                self.assertEqual(count, 0, overrides)
                self.assertEqual(lib.banjo_foot_source(C.byref(state)), 0)

    def test_pitch_alternates_and_silence_does_not_draw(self):
        for lib in self.libs:
            rng = C.c_uint(0x4D343135)
            first = lib.banjo_foot_unit(C.byref(rng))
            second = lib.banjo_foot_unit(C.byref(rng))
            state = _fresh(lib)
            count, plays = _observe(lib, C.byref(state), flags=0x80000700, phase_before=0.2, phase_after=0.95)
            self.assertEqual(count, 2)
            self.assertEqual(plays[0].sfx_id, 0x5)
            self.assertEqual(plays[0].loudness, 17000)
            self.assertEqual(plays[0].pitch, lib.banjo_foot_vary(0.8, 0.05, first))
            self.assertEqual(plays[1].pitch, lib.banjo_foot_vary(0.7, 0.05, second))
            self.assertEqual(plays[0].rate, lib.banjo_foot_output_rate(plays[0].pitch, 60, 0, 0))
            self.assertGreaterEqual(plays[0].pitch, 0.8 - 0.025)
            self.assertLess(plays[0].pitch, 0.8 + 0.025)
            self.assertGreaterEqual(plays[1].pitch, 0.7 - 0.025)
            self.assertLess(plays[1].pitch, 0.7 + 0.025)
            self.assertEqual(lib.banjo_foot_source(C.byref(state)), 0)
            held = _fresh(lib)
            other = _fresh(lib)
            count, _plays = _observe(lib, C.byref(held), crouch=1)
            self.assertEqual(count, 0)
            count, played = _observe(lib, C.byref(held), flags=0x80000400)
            count_b, fresh = _observe(lib, C.byref(other), flags=0x80000400)
            self.assertEqual(count, 1)
            self.assertEqual(count_b, 1)
            self.assertEqual(played[0].sfx_id, 0x26)
            self.assertEqual(played[0].loudness, 9000)
            self.assertEqual(played[0].pitch, fresh[0].pitch)
            self.assertEqual(played[0].source, 0)
            skipped = _fresh(lib)
            count, played = _observe(lib, C.byref(skipped), flags=0x80000100)
            self.assertEqual(count, 1)
            self.assertEqual(played[0].type, 10)
            self.assertEqual(played[0].sfx_id, 0x99)
            self.assertEqual(played[0].loudness, 21000)
            self.assertEqual(played[0].source, 0)
            self.assertEqual(lib.banjo_foot_source(C.byref(skipped)), 1)
            count, played = _observe(lib, C.byref(skipped), flags=0x400)
            self.assertEqual(count, 1)
            self.assertEqual(played[0].type, 6)
            self.assertEqual(played[0].sfx_id, 0x6)
            self.assertEqual(played[0].loudness, 7000)
            self.assertEqual(played[0].source, 1)
            self.assertEqual(played[0].pitch, lib.banjo_foot_vary(1.0, 0.05, second))
            raised = _fresh(lib)
            count, played = _observe(
                lib, C.byref(raised), flags=0x100, floor_y=100.0, player_y=50.0,
            )
            self.assertEqual(count, 1)
            self.assertEqual(played[0].type, 4)
            self.assertEqual(played[0].sfx_id, 0x10)
            self.assertEqual(played[0].loudness, 13000)

    def test_keybase_ratio_uses_al_cents(self):
        for lib in self.libs:
            self.assertEqual(lib.banjo_foot_cents_ratio(0), 1.0)
            self.assertEqual(lib.banjo_foot_key_ratio(60, 0, 0), 1.0)
            self.assertEqual(lib.banjo_foot_key_ratio(60, -2, 1), 1.0)
            self.assertNotEqual(lib.banjo_foot_key_ratio(60, -2, 0), 1.0)
            self.assertGreater(lib.banjo_foot_key_ratio(62, 0, 0), 1.0)
            self.assertLess(lib.banjo_foot_key_ratio(48, 0, 0), 1.0)
            shaped = lib.banjo_foot_output_rate(0.8, 62, 0, 0)
            plain = lib.banjo_foot_output_rate(0.8, 60, 0, 0)
            self.assertGreater(shaped, plain)
            self.assertEqual(plain, F(22000.0 * 0.8).value)


class FootstepIntegrationTests(unittest.TestCase):
    def test_footsteps_use_two_channels_and_leave_the_slide_alone(self):
        audio = (ROOT / "platform/3ds/source/footstep_3ds.c").read_text(encoding="utf-8")
        logic = (ROOT / "tools/banjo3ds/footstep/footstep.c").read_text(encoding="utf-8")
        probe = (ROOT / "platform/3ds/source/sfx_probe_3ds.c").read_text(encoding="utf-8")
        main = (ROOT / "platform/3ds/source/main.c").read_text(encoding="utf-8")
        body = main[main.index("int main(void)"):]
        self.assertIn("ndspChnReset(1)", audio)
        self.assertIn("ndspChnReset(2)", audio)
        self.assertIn("ndspChnWaveBufClear(1)", audio)
        self.assertIn("ndspChnWaveBufClear(2)", audio)
        self.assertIsNone(re.search(r"ndspChn\w+\(\s*0", audio))
        for banned in ("ndspInit", "ndspExit", "sfxVoiceSustain", "sfxProbe3dsFrame", "playerCrouch"):
            self.assertNotIn(banned, audio)
        self.assertIn("sfxSynthVolume(SFX_LEVEL_TABLE", audio)
        self.assertIn("banjo_foot_output_rate", audio)
        self.assertIn("looping = false", audio)
        self.assertNotIn("looping = true", audio)
        self.assertNotIn("ndsp", logic)
        self.assertNotIn("sfxVoiceSustain", logic)
        self.assertEqual(set(re.findall(r"ndspChn\w+\((\d+)", probe)), {"0"})
        self.assertEqual(probe.count("ndspInit("), 1)
        self.assertEqual(probe.count("ndspExit("), 1)
        self.assertEqual(probe.count("sfxVoiceSustain"), 1)
        self.assertIn("int sfxProbe3dsReady(void)", probe)
        self.assertIn(FRAME_COMMENT, body)
        self.assertEqual(body.count("sfxProbe3dsFrame("), 1)
        self.assertLess(
            body.index("sfxProbe3dsFrame(playerCrouchSlideSfx());"),
            body.index("footstep3dsSubmit("),
        )
        self.assertLess(body.index("sfxProbe3dsInit();"), body.index("footstep3dsInit();"))
        self.assertLess(body.index("footstep3dsExit();"), body.index("sfxProbe3dsExit();"))
        self.assertIn("sceneExit();\n    sfxProbe3dsExit();", body)
        for name in GAMEPLAY:
            gameplay = (ROOT / "platform/3ds/source" / name).read_text(encoding="utf-8")
            self.assertNotIn("footstep", gameplay)
            self.assertNotIn("sfxProbe", gameplay)
            self.assertNotIn("ndsp", gameplay)

    def test_header_slots_stay_in_build_and_skip_missing_sounds(self):
        text = render_header((), "none")
        self.assertIn("#define BANJO_FOOT_PCM_COUNT 13", text)
        self.assertEqual(text.count("_PRESENT 0"), len(FOOT_SFX_IDS))
        self.assertNotIn("sfx 0x18 for the slide hold", text)
        clip = FootClip(0x5, b"\x01\x00\x00\x00", 127, 120, 62, 0, 0)
        rendered = render_header((clip,), "synthetic")
        self.assertIn("#define BANJO_FOOT_SFX_0_ID 0x5", rendered)
        self.assertIn("#define BANJO_FOOT_SFX_0_PRESENT 1", rendered)
        self.assertIn("#define BANJO_FOOT_SFX_0_KEY_BASE 62", rendered)
        self.assertIn("#define BANJO_FOOT_SFX_0_PCM_BYTES 4", rendered)
        self.assertIn("#define BANJO_FOOT_SFX_12_PRESENT 0", rendered)
        with self.assertRaises(SfxBankError):
            resolve_header_path(Path("/tmp/generated_sfx_foot.h"), ROOT)
        out = ROOT / "platform/3ds/build/footstep-host-test.h"
        out.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(out.unlink, missing_ok=True)
        empty_root = Path(self.id().replace(".", "_"))
        code = main(["--out", str(out), "--root", str(ROOT / "build" / "no-such-foot-rom")])
        self.assertEqual(code, 0)
        written = out.read_text(encoding="utf-8")
        self.assertIn("#define BANJO_FOOT_SFX_0_PRESENT 0", written)
        self.assertEqual(main(["--out", str(out), "--root", str(empty_root), "--require"]), 1)
        book = _book(2, 1, lambda _p, _c, _k: 0)
        frame = _adpcm_frame(0, 0, [1, 0] + [0] * 14)
        ctl, tbl = _synthetic_bank(frame, 0, book)
        decoded = decode_clip(ctl, tbl, 0x5)
        self.assertEqual(decoded.sfx_id, 0x5)
        self.assertEqual(decoded.key_base, 60)
        self.assertEqual(decoded.detune, -2)
        self.assertGreater(len(decoded.blob), 0)

    def test_us_v10_embeds_the_spiral_mountain_steps(self):
        rom = ROOT / "decompressed.us.v10.z64"
        if not rom.is_file():
            self.skipTest("decompressed us.v10 ROM is not present")
        out = ROOT / "platform/3ds/build/footstep-rom-test.h"
        out.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(out.unlink, missing_ok=True)
        code = main(["--out", str(out), "--rom", str(rom), "--version", "us.v10"])
        self.assertEqual(code, 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("#define BANJO_FOOT_SFX_0_ID 0x5", text)
        self.assertIn("#define BANJO_FOOT_SFX_0_PRESENT 1", text)
        self.assertIn("#define BANJO_FOOT_SFX_0_KEY_BASE 62", text)
        self.assertIn("#define BANJO_FOOT_SFX_1_ID 0x6", text)
        self.assertIn("#define BANJO_FOOT_SFX_1_PRESENT 1", text)
        self.assertIn("#define BANJO_FOOT_SFX_3_ID 0x8", text)
        self.assertIn("#define BANJO_FOOT_SFX_3_PRESENT 1", text)
        self.assertIn("#define BANJO_FOOT_SFX_6_ID 0x26", text)
        self.assertIn("#define BANJO_FOOT_SFX_6_PRESENT 1", text)
        self.assertIn("#define BANJO_FOOT_SFX_12_ID 0x3f2", text)
        self.assertIn("#define BANJO_FOOT_SFX_12_PRESENT 0", text)
        self.assertNotIn("sfx 0x18 for the slide hold", text)
        for present in ("BANJO_FOOT_SFX_0_PCM_BYTES", "BANJO_FOOT_SFX_1_PCM_BYTES",
                        "BANJO_FOOT_SFX_3_PCM_BYTES", "BANJO_FOOT_SFX_6_PCM_BYTES"):
            size = int(re.search(rf"#define {present} (\d+)", text).group(1))
            self.assertGreater(size, 1000)
            self.assertEqual(size % 2, 0)


if __name__ == "__main__":
    unittest.main()
