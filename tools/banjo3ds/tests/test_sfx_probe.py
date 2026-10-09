"""Host tests for the SFX_19 then unlooped SFX_18 listening probe. No Rare sample bytes."""

import ctypes as C
import io
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tools.banjo3ds import sfx_probe_asset
from tools.banjo3ds.sfx_probe_asset import SFX_PROBE_GAP_MS, SFX_PROBE_RATE, main
from tools.banjo3ds.tests.test_sfx_bank import _synthetic_bank


ROOT = Path(__file__).resolve().parents[3]
IDLE, QUEUED, GAP, DONE, SKIPPED = 0, 1, 2, 3, 4
LANDING, SLIDE = 0, 1
GAMEPLAY = (
    "camera_runtime.c",
    "movement.c",
    "player_crouch.c",
    "player_ground.c",
    "player_input.c",
    "player_runtime.c",
    "walk_animation.c",
)
RAW16 = b"\x12\x34\xff\xfe"
RAW16_LE = b"\x34\x12\xfe\xff"
INIT_COMMENT = (
    "After the first presented frame the probe plays SFX_19 once, waits 400 ms, "
    "then plays unlooped SFX_18 once. No new button, and this call does not enter "
    "crouch, gait, input, physics, or camera."
)


def _array_bytes(text: str, symbol: str, present_macro: str, bytes_macro: str) -> bytes:
    present = int(re.search(rf"#define {present_macro} (\d+)", text).group(1))
    size = int(re.search(rf"#define {bytes_macro} (\d+)", text).group(1))
    if present == 0:
        placeholder = f"static const unsigned char {symbol}[1] = {{0}};"
        if size != 0 or placeholder not in text:
            raise AssertionError((symbol, present, size))
        return b""
    marker = f"static const unsigned char {symbol}[{bytes_macro}] = {{"
    start = text.index(marker) + len(marker)
    body = text[start:text.index("};", start)]
    values = [int(token, 16) for token in re.findall(r"0x([0-9a-fA-F]{2})", body)]
    if present != 1 or len(values) != size:
        raise AssertionError((symbol, present, size, len(values)))
    return bytes(values)


def header_pcm(text: str) -> tuple[bytes, bytes]:
    rate = int(re.search(r"\* rate_hz: (\d+)", text).group(1))
    gap = int(re.search(r"\* gap_ms: (\d+)", text).group(1))
    if rate != SFX_PROBE_RATE or gap != SFX_PROBE_GAP_MS:
        raise AssertionError((rate, gap))
    if "sfx 0x19, silence, unlooped sfx 0x18" not in text:
        raise AssertionError(text)
    if "#define BANJO_SFX19_INDEX 0x19" not in text or "#define BANJO_SFX18_INDEX 0x18" not in text:
        raise AssertionError(text)
    landing = _array_bytes(text, "banjo_sfx19_pcm", "BANJO_SFX19_PRESENT", "BANJO_SFX19_PCM_BYTES")
    slide = _array_bytes(text, "banjo_sfx18_pcm", "BANJO_SFX18_PRESENT", "BANJO_SFX18_PCM_BYTES")
    return landing, slide


def compile_header(text: str, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    header = directory / "generated_sfx_probe.h"
    source = directory / "probe_header.c"
    header.write_text(text, encoding="utf-8")
    source.write_text(
        '#include "generated_sfx_probe.h"\n'
        "int probe_bytes(void) {\n"
        "    return BANJO_SFX19_PCM_BYTES + BANJO_SFX18_PCM_BYTES\n"
        "        + (int)banjo_sfx19_pcm[0] + (int)banjo_sfx18_pcm[0];\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["cc", "-Wall", "-Wextra", "-Werror", "-c", str(source),
         "-I", str(directory), "-o", str(directory / "probe_header.o")],
        check=True,
    )


class Probe(C.Structure):
    _fields_ = [
        ("ndsp_ready", C.c_int),
        ("landing_bytes", C.c_int),
        ("slide_bytes", C.c_int),
        ("sample_rate", C.c_int),
        ("phase", C.c_int),
        ("clip", C.c_int),
        ("armed", C.c_int),
        ("queue_count", C.c_int),
        ("release_count", C.c_int),
        ("gap_start_ms", C.c_int),
    ]


def bind_probe(lib):
    lib.sfxProbeReset.argtypes = [C.POINTER(Probe)]
    lib.sfxProbeBind.argtypes = [C.POINTER(Probe), C.c_int, C.c_int, C.c_int, C.c_int]
    lib.sfxProbeBind.restype = C.c_int
    lib.sfxProbePoll.argtypes = [C.POINTER(Probe), C.c_int]
    lib.sfxProbePoll.restype = C.c_int
    lib.sfxProbeComplete.argtypes = [C.POINTER(Probe), C.c_int]
    lib.sfxProbeShutdown.argtypes = [C.POINTER(Probe)]
    lib.sfxProbeShutdown.restype = C.c_int


class SfxProbeAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sfx-probe-", dir=ROOT / "build")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        ctl, tbl = _synthetic_bank(RAW16, 1)
        self.ctl = self.root / "soundfont1ctl.bin"
        self.tbl = self.root / "soundfont1tbl.bin"
        self.ctl.write_bytes(ctl)
        self.tbl.write_bytes(tbl)

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_synthetic_raw16_header_is_little_endian_pcm(self):
        header = self.root / "probe.h"
        pcm18 = self.root / "slide.pcm16"
        pcm19 = self.root / "landing.pcm16"
        code, stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--ctl", str(self.ctl),
            "--tbl", str(self.tbl),
            "--out", str(header),
            "--pcm18", str(pcm18),
            "--pcm19", str(pcm19),
            "--no-fallback",
        ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        self.assertIn("sfx 0x19 index 0x19", stdout)
        self.assertIn("sfx 0x18 index 0x18", stdout)
        self.assertIn("bytes 4", stdout)
        self.assertIn("rate 22000", stdout)
        self.assertIn("gap 400", stdout)
        self.assertNotIn("0x34", stdout)
        self.assertNotIn("0xfe", stdout)
        self.assertNotIn("index 0x1a", stdout)
        text = header.read_text(encoding="utf-8")
        self.assertEqual(header_pcm(text), (RAW16_LE, RAW16_LE))
        self.assertEqual(pcm18.read_bytes(), RAW16_LE)
        self.assertEqual(pcm19.read_bytes(), RAW16_LE)
        compile_header(text, self.root)

    def test_generator_refuses_a_mismatched_sound_index(self):
        real = sfx_probe_asset.extract_sfx

        def mismatched(ctl, tbl, sfx_id):
            info, pcm = real(ctl, tbl, sfx_id)
            return replace(info, sound_index=sfx_id + 1), pcm

        header = self.root / "shifted.h"
        with patch("tools.banjo3ds.sfx_probe_asset.extract_sfx", mismatched):
            code, stdout, stderr = self.invoke([
                "--root", str(self.root),
                "--ctl", str(self.ctl),
                "--tbl", str(self.tbl),
                "--out", str(header),
                "--no-fallback",
            ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "")
        self.assertIn("soundArray index", stderr)
        self.assertIn("without the probe", stderr)
        self.assertEqual(header_pcm(header.read_text(encoding="utf-8")), (b"", b""))

    def test_missing_inputs_write_an_empty_header(self):
        header = self.root / "missing.h"
        code, stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--out", str(header),
            "--no-fallback",
        ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "")
        self.assertIn("without the probe", stderr)
        text = header.read_text(encoding="utf-8")
        self.assertEqual(header_pcm(text), (b"", b""))
        self.assertIn("BANJO_SFX19_PRESENT 0", text)
        self.assertIn("BANJO_SFX18_PRESENT 0", text)
        compile_header(text, self.root / "empty-compile")

    def test_odd_or_silent_fallback_is_missing(self):
        fallback = self.root / "build" / "sfx" / "sfx_0018.pcm16"
        fallback.parent.mkdir(parents=True)
        for blob in (b"\x01\x02\x03", b"\x00\x00\x00\x00"):
            fallback.write_bytes(blob)
            header = self.root / f"fallback-{len(blob)}-{blob[0]}.h"
            code, _stdout, stderr = self.invoke([
                "--root", str(self.root),
                "--out", str(header),
            ])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(header_pcm(header.read_text(encoding="utf-8")), (b"", b""))

    def test_usable_pcm_fallback(self):
        fallback = self.root / "build" / "sfx" / "sfx_0018.pcm16"
        fallback.parent.mkdir(parents=True)
        fallback.write_bytes(RAW16_LE)
        header = self.root / "fallback.h"
        code, stdout, stderr = self.invoke(["--root", str(self.root), "--out", str(header)])
        self.assertEqual(code, 0, stderr)
        self.assertIn("bytes 4", stdout)
        self.assertIn("sfx 0x18", stdout)
        text = header.read_text(encoding="utf-8")
        self.assertEqual(header_pcm(text), (b"", RAW16_LE))
        self.assertIn("BANJO_SFX19_PRESENT 0", text)
        compile_header(text, self.root / "slide-only-compile")

    def test_distinct_fallbacks_embed_each_clip(self):
        directory = self.root / "build" / "sfx"
        directory.mkdir(parents=True)
        landing = directory / "sfx_0019.pcm16"
        slide = directory / "sfx_0018.pcm16"
        landing.write_bytes(b"\x01\x00")
        slide.write_bytes(RAW16_LE)
        header = self.root / "split.h"
        code, stdout, stderr = self.invoke(["--root", str(self.root), "--out", str(header)])
        self.assertEqual(code, 0, stderr)
        self.assertIn("sfx 0x19", stdout)
        self.assertIn("sfx 0x18", stdout)
        text = header.read_text(encoding="utf-8")
        self.assertEqual(header_pcm(text), (b"\x01\x00", RAW16_LE))
        compile_header(text, self.root / "split-compile")

    def test_short_rom_does_not_fail_the_build(self):
        (self.root / "decompressed.us.v10.z64").write_bytes(b"short")
        header = self.root / "short.h"
        code, _stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--out", str(header),
            "--no-fallback",
        ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(header_pcm(header.read_text(encoding="utf-8")), (b"", b""))
        required = self.root / "required.h"
        code, _stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--out", str(required),
            "--no-fallback",
            "--require",
        ])
        self.assertEqual(code, 1)
        self.assertIn("sfx-probe:", stderr)
        self.assertFalse(required.exists())

    def test_bad_ctl_is_optional_unless_required(self):
        self.ctl.write_bytes(b"not a bank")
        optional = self.root / "bad.h"
        code, _stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--ctl", str(self.ctl),
            "--tbl", str(self.tbl),
            "--out", str(optional),
            "--no-fallback",
        ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(header_pcm(optional.read_text(encoding="utf-8")), (b"", b""))
        required = self.root / "bad-required.h"
        code, _stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--ctl", str(self.ctl),
            "--tbl", str(self.tbl),
            "--out", str(required),
            "--require",
        ])
        self.assertEqual(code, 1)
        self.assertFalse(required.exists())

    def test_header_outside_build_directories_is_refused(self):
        illegal = ROOT / "assets" / "banjo3ds-sfx-probe-should-not-exist.h"
        self.addCleanup(illegal.unlink, missing_ok=True)
        code, _stdout, stderr = self.invoke([
            "--root", str(ROOT),
            "--out", "assets/banjo3ds-sfx-probe-should-not-exist.h",
            "--no-fallback",
        ])
        self.assertEqual(code, 1)
        self.assertIn("build/", stderr)
        self.assertFalse(illegal.exists())
        outside = Path("/tmp/banjo3ds-sfx-probe-illegal.h")
        self.addCleanup(outside.unlink, missing_ok=True)
        code, _stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--out", str(outside),
            "--no-fallback",
        ])
        self.assertEqual(code, 1)
        self.assertFalse(outside.exists())

    def test_pcm_outside_build_does_not_embed_samples(self):
        outside = Path("/tmp/banjo3ds-sfx-probe-illegal.pcm16")
        self.addCleanup(outside.unlink, missing_ok=True)
        inside = self.root / "build" / "sfx" / "kept-unwritten.pcm16"
        header = self.root / "rejected-pcm.h"
        code, _stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--ctl", str(self.ctl),
            "--tbl", str(self.tbl),
            "--out", str(header),
            "--pcm18", str(outside),
            "--pcm19", str(inside),
        ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(header_pcm(header.read_text(encoding="utf-8")), (b"", b""))
        self.assertFalse(outside.exists())
        self.assertFalse(inside.exists())


class SfxProbeTriggerTests(unittest.TestCase):
    def test_probe_plays_sfx19_then_gap_then_unlooped_sfx18(self):
        text = (ROOT / "platform/3ds/source/main.c").read_text(encoding="utf-8")
        body = text[text.index("int main(void)"):]
        self.assertLess(body.index("return 1;"), body.index("sfxProbe3dsInit();"))
        self.assertLess(body.index("sfxProbe3dsInit();"), body.index("while (aptMainLoop())"))
        self.assertEqual(body.count("sfxProbe3dsInit();"), 1)
        self.assertEqual(body.count("sfxProbe3dsFrame();"), 1)
        self.assertEqual(body.count("sfxProbe3dsExit();"), 1)
        self.assertIn(INIT_COMMENT, body)
        self.assertIn(
            "C3D_FrameEnd(0);\n"
            "        /* First presented frame starts SFX_19, then 400 ms of silence, then unlooped SFX_18. */\n"
            "        sfxProbe3dsFrame();",
            body,
        )
        self.assertIn("C3D_FrameEnd(0);\n            break;", body)
        self.assertIn("sceneExit();\n    sfxProbe3dsExit();", body)
        self.assertIn("if (down & KEY_START)\n            break;", body)
        audio = (ROOT / "platform/3ds/source/sfx_probe_3ds.c").read_text(encoding="utf-8")
        for banned in ("playerCrouch", "cameraRuntime", "playerInput", "movementDelta"):
            self.assertNotIn(banned, audio)
        self.assertIn("banjo_sfx19_pcm", audio)
        self.assertIn("banjo_sfx18_pcm", audio)
        self.assertIn("SFX_PROBE_GAP_MS", audio)
        self.assertIn("NDSP_FORMAT_MONO_PCM16", audio)
        self.assertIn("ndspChnSetRate(0, (float)SFX_PROBE_RATE)", audio)
        self.assertEqual(audio.count("wave.looping = false"), 1)
        self.assertNotIn("looping = true", audio)
        self.assertEqual(audio.count("ndspInit("), 1)
        self.assertEqual(audio.count("ndspExit("), 1)
        self.assertNotIn("DSP_FlushDataCache(linear_pcm, 0)", audio)
        for name in GAMEPLAY:
            gameplay = (ROOT / "platform/3ds/source" / name).read_text(encoding="utf-8")
            self.assertNotIn("sfxProbe", gameplay)
            self.assertNotIn("ndsp", gameplay)


class SfxProbeLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="sfx-probe-life-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs = []
        source = ROOT / "tools/banjo3ds/sfx_probe/sfx_probe.c"
        include = ROOT / "tools/banjo3ds/sfx_probe"
        header = (include / "sfx_probe.h").read_text(encoding="utf-8")
        for token in (
            "#define SFX_PROBE_RATE 22000",
            "#define SFX_PROBE_GAP_MS 400",
            "#define SFX_PROBE_CLIP_LANDING 0",
            "#define SFX_PROBE_CLIP_SLIDE 1",
            "#define SFX_PROBE_GAP 2",
            "#define SFX_PROBE_DONE 3",
            "#define SFX_PROBE_SKIPPED 4",
        ):
            if token not in header:
                raise AssertionError(token)
        for opt in ("-O0", "-O2"):
            out = Path(cls.tmp.name) / f"{opt}.so"
            subprocess.run(
                ["cc", opt, "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                 "-I", str(include), str(source), "-o", str(out)],
                check=True,
            )
            lib = C.CDLL(str(out))
            bind_probe(lib)
            cls.libs.append(lib)

    def fresh(self, lib):
        probe = Probe()
        lib.sfxProbeReset(C.byref(probe))
        return probe

    def test_landing_gap_then_one_unlooped_slide(self):
        for lib in self.libs:
            probe = self.fresh(lib)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 0), 0)
            self.assertEqual(lib.sfxProbeBind(C.byref(probe), 1, 19008, 24352, 22000), 1)
            self.assertEqual(lib.sfxProbeBind(C.byref(probe), 1, 19008, 24352, 22000), 0)
            self.assertEqual((probe.phase, probe.armed, probe.clip), (IDLE, 1, LANDING))
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 0), 1)
            self.assertEqual((probe.phase, probe.clip, probe.queue_count), (QUEUED, LANDING, 1))
            for _ in range(8):
                self.assertEqual(lib.sfxProbePoll(C.byref(probe), 500), 0)
            self.assertEqual(probe.queue_count, 1)
            lib.sfxProbeComplete(C.byref(probe), 1000)
            self.assertEqual((probe.phase, probe.release_count, probe.gap_start_ms), (GAP, 0, 1000))
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 1399), 0)
            self.assertEqual(probe.phase, GAP)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 1400), 1)
            self.assertEqual((probe.phase, probe.clip, probe.queue_count), (QUEUED, SLIDE, 2))
            for _ in range(8):
                self.assertEqual(lib.sfxProbePoll(C.byref(probe), 1500), 0)
            self.assertEqual(probe.queue_count, 2)
            lib.sfxProbeComplete(C.byref(probe), 2000)
            self.assertEqual((probe.phase, probe.release_count), (DONE, 0))
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 2001), 0)
            self.assertEqual(lib.sfxProbeShutdown(C.byref(probe)), 0)
            lib.sfxProbeComplete(C.byref(probe), 2002)
            self.assertEqual(probe.release_count, 0)

    def test_gap_survives_the_signed_millisecond_boundary(self):
        start = 2147483500
        early = start + 399 - 2**32
        ready = start + 400 - 2**32
        for lib in self.libs:
            probe = self.fresh(lib)
            self.assertEqual(lib.sfxProbeBind(C.byref(probe), 1, 4, 6, 22000), 1)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 0), 1)
            lib.sfxProbeComplete(C.byref(probe), start)
            self.assertEqual(probe.gap_start_ms, start)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), early), 0)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), ready), 1)
            self.assertEqual(probe.clip, SLIDE)

    def test_shutdown_while_landing_is_queued_does_not_play_the_slide(self):
        for lib in self.libs:
            probe = self.fresh(lib)
            self.assertEqual(lib.sfxProbeShutdown(C.byref(probe)), 0)
            lib.sfxProbeComplete(C.byref(probe), 0)
            self.assertEqual(probe.phase, IDLE)
            self.assertEqual(lib.sfxProbeBind(C.byref(probe), 1, 19008, 24352, 22000), 1)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 10), 1)
            self.assertEqual(lib.sfxProbeShutdown(C.byref(probe)), 1)
            self.assertEqual((probe.phase, probe.release_count, probe.queue_count), (DONE, 1, 1))
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 5000), 0)
            self.assertEqual(probe.clip, LANDING)
            self.assertEqual(lib.sfxProbeShutdown(C.byref(probe)), 0)
            self.assertEqual(probe.release_count, 1)

    def test_shutdown_during_the_gap_does_not_release_again(self):
        for lib in self.libs:
            probe = self.fresh(lib)
            self.assertEqual(lib.sfxProbeBind(C.byref(probe), 1, 8, 8, 22000), 1)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 0), 1)
            lib.sfxProbeComplete(C.byref(probe), 1000)
            self.assertEqual(probe.phase, GAP)
            self.assertEqual(lib.sfxProbeShutdown(C.byref(probe)), 0)
            self.assertEqual((probe.phase, probe.release_count, probe.queue_count), (DONE, 0, 1))
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 1400), 0)
            self.assertEqual(lib.sfxProbeShutdown(C.byref(probe)), 0)

    def test_landing_only_finishes_without_a_gap(self):
        for lib in self.libs:
            probe = self.fresh(lib)
            self.assertEqual(lib.sfxProbeBind(C.byref(probe), 1, 19008, 0, 22000), 1)
            self.assertEqual(probe.clip, LANDING)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 0), 1)
            lib.sfxProbeComplete(C.byref(probe), 1000)
            self.assertEqual((probe.phase, probe.release_count), (DONE, 0))
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 1400), 0)

    def test_slide_only_plays_immediately(self):
        for lib in self.libs:
            probe = self.fresh(lib)
            self.assertEqual(lib.sfxProbeBind(C.byref(probe), 1, 3, 24352, 22000), 1)
            self.assertEqual(probe.clip, SLIDE)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 0), 1)
            self.assertEqual((probe.phase, probe.clip, probe.queue_count), (QUEUED, SLIDE, 1))
            lib.sfxProbeComplete(C.byref(probe), 1000)
            self.assertEqual(probe.phase, DONE)
            self.assertEqual(lib.sfxProbePoll(C.byref(probe), 1400), 0)

    def test_missing_ndsp_asset_or_rate_never_queues(self):
        for lib in self.libs:
            for ready, landing, slide, rate in (
                (1, 0, 0, 22000),
                (0, 100, 100, 22000),
                (1, 3, 3, 22000),
                (1, 100, 100, 22050),
                (1, 100, 100, 28000),
                (1, -2, -2, 22000),
                (1, 1, 0, 22000),
            ):
                probe = self.fresh(lib)
                self.assertEqual(lib.sfxProbeBind(C.byref(probe), ready, landing, slide, rate), 0)
                self.assertEqual(probe.phase, SKIPPED)
                self.assertEqual(probe.armed, 0)
                self.assertEqual(lib.sfxProbePoll(C.byref(probe), 0), 0)
                self.assertEqual(lib.sfxProbeShutdown(C.byref(probe)), 0)
                self.assertEqual(lib.sfxProbeBind(C.byref(probe), 1, 4, 4, 22000), 0)

    def test_null_pointers_are_safe(self):
        for lib in self.libs:
            self.assertEqual(lib.sfxProbeBind(None, 1, 4, 4, 22000), 0)
            self.assertEqual(lib.sfxProbePoll(None, 0), 0)
            self.assertEqual(lib.sfxProbeShutdown(None), 0)
            lib.sfxProbeReset(None)
            lib.sfxProbeComplete(None, 0)
