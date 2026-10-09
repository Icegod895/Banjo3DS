"""Host tests for the SFX_18 slide lifecycle and the SFX_19 closer. No Rare sample bytes."""

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
from tools.banjo3ds.sfx_bank import extract_sfx, slice_soundfont, verified_adpcm_loop
from tools.banjo3ds.sfx_probe_asset import (
    SFX_PROBE_RATE,
    SFX_PROBE_SLIDE_MS,
    ProbeClip,
    main,
    render_header,
)
from tools.banjo3ds.tests.test_sfx_bank import _synthetic_bank


ROOT = Path(__file__).resolve().parents[3]
IDLE, SLIDE, CLOSER, DONE, SKIPPED = 0, 1, 2, 3, 4
SLIDE_NONE, SLIDE_LOOP, SLIDE_ONCE = 0, 1, 2
QUEUE_SLIDE, SET_RATE, STOP_SLIDE, QUEUE_CLOSER = 1, 2, 4, 8
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
    "The voice stays silent until a crouch coast raises the sustain latch. "
    "Sustained frames keep looped SFX_18 and step pitch with Rare's formula. "
    "The first unsustained frame stops that voice and plays SFX_19 once. "
    "No new button, and this call does not enter crouch, gait, input, physics, or camera."
)
FRAME_COMMENT = (
    "C3D_FrameEnd(0);\n"
    "        /* The crouch-coast latch sustains looped SFX_18. "
    "The first frame without it plays SFX_19 once. */\n"
    "        sfxProbe3dsFrame(playerCrouchSlideSfx());"
)
ORDER_LINE = "sfx 0x18 for the slide hold, then one sfx 0x19"


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


def header_assets(text: str) -> tuple[bytes, bytes, bytes, bytes]:
    rate = int(re.search(r"\* rate_hz: (\d+)", text).group(1))
    slide = int(re.search(r"\* slide_ms: (\d+)", text).group(1))
    if rate != SFX_PROBE_RATE or slide != SFX_PROBE_SLIDE_MS:
        raise AssertionError((rate, slide))
    if ORDER_LINE not in text:
        raise AssertionError("missing slide order")
    if "#define BANJO_SFX19_INDEX 0x19" not in text or "#define BANJO_SFX18_INDEX 0x18" not in text:
        raise AssertionError("missing sound index")
    closer = _array_bytes(text, "banjo_sfx19_pcm", "BANJO_SFX19_PRESENT", "BANJO_SFX19_PCM_BYTES")
    intro = _array_bytes(text, "banjo_sfx18_intro_pcm", "BANJO_SFX18_INTRO_PRESENT", "BANJO_SFX18_INTRO_PCM_BYTES")
    loop = _array_bytes(text, "banjo_sfx18_loop_pcm", "BANJO_SFX18_LOOP_PRESENT", "BANJO_SFX18_LOOP_PCM_BYTES")
    once = _array_bytes(text, "banjo_sfx18_once_pcm", "BANJO_SFX18_ONCE_PRESENT", "BANJO_SFX18_ONCE_PCM_BYTES")
    return closer, intro, loop, once


def compile_header(text: str, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    header = directory / "generated_sfx_probe.h"
    source = directory / "probe_header.c"
    header.write_text(text, encoding="utf-8")
    source.write_text(
        '#include "generated_sfx_probe.h"\n'
        "int probe_bytes(void) {\n"
        "    return BANJO_SFX19_PCM_BYTES + BANJO_SFX18_INTRO_PCM_BYTES\n"
        "        + BANJO_SFX18_LOOP_PCM_BYTES + BANJO_SFX18_ONCE_PCM_BYTES\n"
        "        + (int)banjo_sfx19_pcm[0] + (int)banjo_sfx18_intro_pcm[0]\n"
        "        + (int)banjo_sfx18_loop_pcm[0] + (int)banjo_sfx18_once_pcm[0];\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["cc", "-Wall", "-Wextra", "-Werror", "-c", str(source),
         "-I", str(directory), "-o", str(directory / "probe_header.o")],
        check=True,
    )


class Voice(C.Structure):
    _fields_ = [
        ("ndsp_ready", C.c_int),
        ("slide_ready", C.c_int),
        ("closer_ready", C.c_int),
        ("sample_rate", C.c_int),
        ("slide_ms", C.c_int),
        ("phase", C.c_int),
        ("armed", C.c_int),
        ("started_ms", C.c_int),
        ("pitch_steps", C.c_int),
        ("queue_slide_count", C.c_int),
        ("queue_closer_count", C.c_int),
        ("release_count", C.c_int),
        ("rng", C.c_uint),
        ("pitch", C.c_float),
    ]


def bind_voice(lib):
    lib.sfxVoiceReset.argtypes = [C.POINTER(Voice)]
    lib.sfxVoiceBind.argtypes = [
        C.POINTER(Voice), C.c_int, C.c_int, C.c_int, C.c_int, C.c_int,
    ]
    lib.sfxVoiceBind.restype = C.c_int
    lib.sfxVoicePoll.argtypes = [C.POINTER(Voice), C.c_int]
    lib.sfxVoicePoll.restype = C.c_int
    lib.sfxVoiceSustain.argtypes = [C.POINTER(Voice), C.c_int]
    lib.sfxVoiceSustain.restype = C.c_int
    lib.sfxVoiceSlideFinished.argtypes = [C.POINTER(Voice), C.c_int]
    lib.sfxVoiceSlideFinished.restype = C.c_int
    lib.sfxVoiceComplete.argtypes = [C.POINTER(Voice)]
    lib.sfxVoiceShutdown.argtypes = [C.POINTER(Voice)]
    lib.sfxVoiceShutdown.restype = C.c_int
    lib.sfxVoicePitch.argtypes = [C.POINTER(Voice)]
    lib.sfxVoicePitch.restype = C.c_float
    lib.sfxVoiceRate.argtypes = [C.POINTER(Voice)]
    lib.sfxVoiceRate.restype = C.c_float
    lib.sfxSlidePitchMin.restype = C.c_float
    lib.sfxSlidePitchMax.restype = C.c_float
    lib.sfxSlidePitchStep.argtypes = [C.c_float, C.c_float]
    lib.sfxSlidePitchStep.restype = C.c_float
    lib.sfxSynthVolume.argtypes = [C.c_int, C.c_int, C.c_int, C.c_int]
    lib.sfxSynthVolume.restype = C.c_int


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

    def test_synthetic_raw16_header_is_an_unlooped_slide(self):
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
        self.assertIn("loop 0", stdout)
        self.assertIn("rate 22000", stdout)
        self.assertIn("slide 2000", stdout)
        self.assertNotIn("gap", stdout)
        self.assertNotIn("0x34", stdout)
        self.assertNotIn("0xfe", stdout)
        self.assertNotIn("index 0x1a", stdout)
        text = header.read_text(encoding="utf-8")
        self.assertEqual(header_assets(text), (RAW16_LE, b"", b"", RAW16_LE))
        self.assertIn("#define BANJO_SFX18_LOOP_VERIFIED 0", text)
        self.assertIn("#define BANJO_SFX18_VOLUME_KNOWN 1", text)
        self.assertIn("#define BANJO_SFX18_ATTACK_VOLUME 40", text)
        self.assertIn("#define BANJO_SFX18_SAMPLE_VOLUME 90", text)
        self.assertIn("#define BANJO_SFX19_ATTACK_VOLUME 40", text)
        self.assertIn("#define BANJO_SFX19_SAMPLE_VOLUME 90", text)
        self.assertNotIn("LOOP_START == 2391", text)
        self.assertEqual(pcm18.read_bytes(), RAW16_LE)
        self.assertEqual(pcm19.read_bytes(), RAW16_LE)
        compile_header(text, self.root)

    def test_matching_loop_state_embeds_intro_and_body(self):
        real = sfx_probe_asset.extract_sfx

        def matched(ctl, tbl, sfx_id):
            info, pcm = real(ctl, tbl, sfx_id)
            if sfx_id != 0x18:
                return info, pcm
            pcm = [1000, -1000] * 24
            info = replace(
                info,
                loop_start=20,
                loop_end=40,
                loop_count=-1,
                loop_state=tuple(pcm[16:32]),
                peak_abs=1000,
                pcm_samples=len(pcm),
            )
            return info, pcm

        header = self.root / "loop.h"
        pcm18 = self.root / "full.pcm16"
        with patch("tools.banjo3ds.sfx_probe_asset.extract_sfx", matched):
            code, stdout, stderr = self.invoke([
                "--root", str(self.root),
                "--ctl", str(self.ctl),
                "--tbl", str(self.tbl),
                "--out", str(header),
                "--pcm18", str(pcm18),
                "--no-fallback",
            ])
        self.assertEqual(code, 0, stderr)
        self.assertIn("loop 1", stdout)
        self.assertIn("intro 40", stdout)
        self.assertIn("body 40", stdout)
        text = header.read_text(encoding="utf-8")
        closer, intro, loop, once = header_assets(text)
        self.assertEqual(closer, RAW16_LE)
        self.assertEqual(len(intro), 40)
        self.assertEqual(len(loop), 40)
        self.assertEqual(once, b"")
        self.assertIn("#define BANJO_SFX18_LOOP_VERIFIED 1", text)
        self.assertIn("#define BANJO_SFX18_LOOP_START 20", text)
        self.assertIn("#define BANJO_SFX18_LOOP_END 40", text)
        self.assertNotIn("LOOP_START == 2391", text)
        self.assertEqual(pcm18.read_bytes(), sfx_probe_asset.pcm_bytes([1000, -1000] * 24))
        compile_header(text, self.root / "loop-compile")

    def test_mismatched_or_silent_loop_body_stays_one_shot(self):
        real = sfx_probe_asset.extract_sfx

        def mismatched(ctl, tbl, sfx_id):
            info, pcm = real(ctl, tbl, sfx_id)
            if sfx_id != 0x18:
                return info, pcm
            pcm = [1000, -1000] * 24
            info = replace(
                info,
                loop_start=20,
                loop_end=40,
                loop_count=0xFFFFFFFF,
                loop_state=tuple(1 for _ in range(16)),
                peak_abs=1000,
                pcm_samples=len(pcm),
            )
            return info, pcm

        header = self.root / "mismatch.h"
        with patch("tools.banjo3ds.sfx_probe_asset.extract_sfx", mismatched):
            code, _stdout, stderr = self.invoke([
                "--root", str(self.root),
                "--ctl", str(self.ctl),
                "--tbl", str(self.tbl),
                "--out", str(header),
                "--no-fallback",
            ])
        self.assertEqual(code, 0, stderr)
        text = header.read_text(encoding="utf-8")
        closer, intro, loop, once = header_assets(text)
        self.assertEqual(closer, RAW16_LE)
        self.assertEqual(intro, b"")
        self.assertEqual(loop, b"")
        self.assertEqual(once, sfx_probe_asset.pcm_bytes([1000, -1000] * 24))
        self.assertIn("#define BANJO_SFX18_LOOP_VERIFIED 0", text)

        def silent_body(ctl, tbl, sfx_id):
            info, pcm = real(ctl, tbl, sfx_id)
            if sfx_id != 0x18:
                return info, pcm
            pcm = [50] + [0] * 47
            info = replace(
                info,
                loop_start=16,
                loop_end=32,
                loop_count=-1,
                loop_state=tuple(pcm[16:32]),
                peak_abs=50,
                pcm_samples=len(pcm),
            )
            return info, pcm

        silent = self.root / "silent-body.h"
        with patch("tools.banjo3ds.sfx_probe_asset.extract_sfx", silent_body):
            code, _stdout, stderr = self.invoke([
                "--root", str(self.root),
                "--ctl", str(self.ctl),
                "--tbl", str(self.tbl),
                "--out", str(silent),
                "--no-fallback",
            ])
        self.assertEqual(code, 0, stderr)
        text = silent.read_text(encoding="utf-8")
        _closer, intro, loop, once = header_assets(text)
        self.assertEqual((intro, loop), (b"", b""))
        self.assertEqual(once, sfx_probe_asset.pcm_bytes([50] + [0] * 47))
        self.assertIn("#define BANJO_SFX18_LOOP_VERIFIED 0", text)

    def test_rare_bounds_are_asserted_only_for_that_verified_split(self):
        intro = sfx_probe_asset.pcm_bytes([1] * 2391)
        body = sfx_probe_asset.pcm_bytes([1] * (12154 - 2391))
        full = sfx_probe_asset.pcm_bytes([1] * 12154)
        closer = sfx_probe_asset.pcm_bytes([2, -2])
        slide = ProbeClip(0x18, full, "synthetic", 0x18, 127, 127, intro, body, 2391, 12154, True)
        landing = ProbeClip(0x19, closer, "synthetic", 0x19, 127, 127)
        text = render_header((landing, slide), "synthetic")
        self.assertIn("#define BANJO_SFX18_LOOP_VERIFIED 1", text)
        self.assertIn('_Static_assert(BANJO_SFX18_LOOP_START == 2391, "SFX_18 loop start");', text)
        self.assertIn('_Static_assert(BANJO_SFX18_LOOP_END == 12154, "SFX_18 loop end");', text)
        self.assertIn("#define BANJO_SFX18_ATTACK_VOLUME 127", text)
        self.assertIn("#define BANJO_SFX19_SAMPLE_VOLUME 127", text)
        assets = header_assets(text)
        self.assertEqual(len(assets[1]), 2391 * 2)
        self.assertEqual(len(assets[2]), (12154 - 2391) * 2)
        self.assertEqual(assets[3], b"")
        compile_header(text, self.root / "rare-bounds")

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
        self.assertEqual(header_assets(header.read_text(encoding="utf-8")), (b"", b"", b"", b""))

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
        self.assertEqual(header_assets(text), (b"", b"", b"", b""))
        self.assertIn("BANJO_SFX19_PRESENT 0", text)
        self.assertIn("BANJO_SFX18_ONCE_PRESENT 0", text)
        self.assertIn("BANJO_SFX18_LOOP_VERIFIED 0", text)
        self.assertIn("BANJO_SFX18_VOLUME_KNOWN 0", text)
        self.assertIn("BANJO_SFX19_VOLUME_KNOWN 0", text)
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
            self.assertEqual(header_assets(header.read_text(encoding="utf-8")), (b"", b"", b"", b""))

    def test_usable_pcm_fallback_has_no_loop_or_volume(self):
        fallback = self.root / "build" / "sfx" / "sfx_0018.pcm16"
        fallback.parent.mkdir(parents=True)
        fallback.write_bytes(RAW16_LE)
        header = self.root / "fallback.h"
        code, stdout, stderr = self.invoke(["--root", str(self.root), "--out", str(header)])
        self.assertEqual(code, 0, stderr)
        self.assertIn("bytes 4", stdout)
        self.assertIn("sfx 0x18", stdout)
        self.assertIn("fallback", stdout)
        self.assertIn("loop 0", stdout)
        text = header.read_text(encoding="utf-8")
        self.assertEqual(header_assets(text), (b"", b"", b"", RAW16_LE))
        self.assertIn("BANJO_SFX19_PRESENT 0", text)
        self.assertIn("#define BANJO_SFX18_VOLUME_KNOWN 0", text)
        self.assertIn("#define BANJO_SFX18_ATTACK_VOLUME 0", text)
        self.assertIn("#define BANJO_SFX19_VOLUME_KNOWN 0", text)
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
        self.assertEqual(header_assets(text), (b"\x01\x00", b"", b"", RAW16_LE))
        compile_header(text, self.root / "split-compile")

    def test_failed_decode_does_not_overwrite_a_pcm_file(self):
        kept = self.root / "kept.pcm16"
        kept.write_bytes(RAW16_LE)
        self.ctl.write_bytes(b"not a bank")
        header = self.root / "kept-header.h"
        code, _stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--ctl", str(self.ctl),
            "--tbl", str(self.tbl),
            "--out", str(header),
            "--pcm18", str(kept),
            "--no-fallback",
        ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(kept.read_bytes(), RAW16_LE)
        self.assertEqual(header_assets(header.read_text(encoding="utf-8")), (b"", b"", b"", b""))

    def test_short_rom_does_not_fail_the_build(self):
        (self.root / "decompressed.us.v10.z64").write_bytes(b"short")
        header = self.root / "short.h"
        code, _stdout, stderr = self.invoke([
            "--root", str(self.root),
            "--out", str(header),
            "--no-fallback",
        ])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(header_assets(header.read_text(encoding="utf-8")), (b"", b"", b"", b""))
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

    def test_corrupt_us_v10_does_not_use_pal_or_the_pcm_fallback(self):
        (self.root / "decompressed.us.v10.z64").write_bytes(b"short")
        (self.root / "decompressed.pal.z64").write_bytes(b"also short")
        fallback = self.root / "build" / "sfx" / "sfx_0018.pcm16"
        fallback.parent.mkdir(parents=True)
        fallback.write_bytes(RAW16_LE)
        header = self.root / "corrupt-first.h"
        code, stdout, stderr = self.invoke(["--root", str(self.root), "--out", str(header)])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "")
        self.assertIn("without the probe", stderr)
        self.assertEqual(header_assets(header.read_text(encoding="utf-8")), (b"", b"", b"", b""))
        self.assertEqual(fallback.read_bytes(), RAW16_LE)

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
        self.assertEqual(header_assets(optional.read_text(encoding="utf-8")), (b"", b"", b"", b""))
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
        self.assertEqual(header_assets(header.read_text(encoding="utf-8")), (b"", b"", b"", b""))
        self.assertFalse(outside.exists())
        self.assertFalse(inside.exists())


class SfxLoopSplitTests(unittest.TestCase):
    def test_verified_body_is_the_half_open_interval(self):
        pcm = list(range(80))
        start, end = 20, 40
        state = tuple(pcm[16:32])
        split = verified_adpcm_loop(pcm, start, end, -1, state)
        self.assertIsNotNone(split)
        intro, body = split
        self.assertEqual(intro, pcm[:start])
        self.assertEqual(body, pcm[start:end])
        self.assertEqual(body[0], pcm[start])
        self.assertEqual(body[-1], pcm[end - 1])
        self.assertEqual(len(body), end - start)
        again = verified_adpcm_loop(pcm, start, end, 0xFFFFFFFF, state)
        self.assertEqual(again, (intro, body))

    def test_only_the_frame_containing_start_selects_the_loop(self):
        pcm = list(range(80))
        start, end = 2391, 12154
        wide = list(range(end + 8))
        frame = (start // 16) * 16
        self.assertEqual(frame, 2384)
        state = tuple(wide[frame:frame + 16])
        split = verified_adpcm_loop(wide, start, end, -1, state)
        self.assertIsNotNone(split)
        intro, body = split
        self.assertEqual(len(intro), start)
        self.assertEqual(len(body), end - start)
        self.assertEqual(intro[-1], wide[start - 1])
        self.assertEqual(body[0], wide[start])
        self.assertEqual(body[-1], wide[end - 1])
        self.assertIsNone(verified_adpcm_loop(wide, start, end, -1, tuple(wide[start:start + 16])))
        self.assertIsNone(verified_adpcm_loop(wide, start, end, -1, tuple(wide[frame + 16:frame + 32])))
        self.assertIsNone(verified_adpcm_loop(pcm, 20, 40, 0, tuple(pcm[16:32])))
        self.assertIsNone(verified_adpcm_loop(pcm, 20, 40, 2, tuple(pcm[16:32])))
        self.assertIsNone(verified_adpcm_loop(pcm, None, 40, -1, tuple(pcm[16:32])))
        self.assertIsNone(verified_adpcm_loop(pcm, 20, 20, -1, tuple(pcm[16:32])))
        self.assertIsNone(verified_adpcm_loop(pcm, 20, 90, -1, tuple(pcm[16:32])))
        self.assertIsNone(verified_adpcm_loop(pcm, 20, 40, -1, tuple(pcm[16:31])))
        short = list(range(30))
        self.assertIsNone(verified_adpcm_loop(short, 20, 30, -1, tuple(range(16))))

    def test_a_loop_that_starts_on_a_frame_has_an_empty_intro(self):
        pcm = [3, -3] * 16
        state = tuple(pcm[:16])
        split = verified_adpcm_loop(pcm, 0, 32, -1, state)
        self.assertEqual(split, ([], pcm))


class SfxProbeTriggerTests(unittest.TestCase):
    def test_probe_holds_sfx18_then_plays_sfx19_once(self):
        text = (ROOT / "platform/3ds/source/main.c").read_text(encoding="utf-8")
        body = text[text.index("int main(void)"):]
        self.assertLess(body.index("return 1;"), body.index("sfxProbe3dsInit();"))
        self.assertLess(body.index("sfxProbe3dsInit();"), body.index("while (aptMainLoop())"))
        self.assertEqual(body.count("sfxProbe3dsInit();"), 1)
        self.assertEqual(body.count("sfxProbe3dsFrame("), 1)
        self.assertNotIn("sfxProbe3dsFrame();", body)
        self.assertNotIn("holds looped SFX_18 for 2000 ms", body)
        self.assertNotIn("holds it for 2000 ms", body)
        self.assertEqual(body.count("sfxProbe3dsExit();"), 1)
        self.assertIn(INIT_COMMENT, body)
        self.assertIn(FRAME_COMMENT, body)
        self.assertIn("C3D_FrameEnd(0);\n            break;", body)
        self.assertIn("sceneExit();\n    sfxProbe3dsExit();", body)
        self.assertIn("if (down & KEY_START)\n            break;", body)
        self.assertNotIn("SFX_PROBE_GAP", body)
        audio = (ROOT / "platform/3ds/source/sfx_probe_3ds.c").read_text(encoding="utf-8")
        for banned in ("playerCrouch", "cameraRuntime", "playerInput", "movementDelta", "CSND"):
            self.assertNotIn(banned, audio)
        for symbol in (
            "banjo_sfx19_pcm",
            "banjo_sfx18_intro_pcm",
            "banjo_sfx18_loop_pcm",
            "banjo_sfx18_once_pcm",
            "SFX_PROBE_SLIDE_MS",
            "SFX_SLIDE_SOURCE_VOLUME",
            "SFX_CLOSER_SOURCE_VOLUME",
            "sfxVoiceSustain",
            "sfxVoiceSlideFinished",
            "sfxSynthVolume",
            "NDSP_FORMAT_MONO_PCM16",
            "flush_size == 0",
        ):
            self.assertIn(symbol, audio)
        self.assertNotIn("SFX_PROBE_GAP", audio)
        self.assertIn("configure_channel((float)SFX_PROBE_RATE, 0.0f)", audio)
        self.assertIn("ndspChnSetRate(0, rate)", audio)
        self.assertEqual(audio.count("looping = false"), 3)
        self.assertEqual(audio.count("looping = true"), 1)
        self.assertEqual(audio.count("ndspInit("), 1)
        self.assertEqual(audio.count("ndspExit("), 1)
        self.assertNotIn("DSP_FlushDataCache(buffer, 0)", audio)
        self.assertNotIn("DSP_FlushDataCache(linear_pcm, 0)", audio)
        self.assertLess(audio.index("SFX_VOICE_STOP_SLIDE"), audio.index("SFX_VOICE_QUEUE_SLIDE"))
        self.assertLess(audio.index("SFX_VOICE_QUEUE_SLIDE"), audio.index("SFX_VOICE_QUEUE_CLOSER"))
        self.assertIn("once_done && sustain", audio)
        self.assertNotIn("sfxVoicePoll", audio)
        self.assertIn(
            "action = sfxVoiceSlideFinished(&voice, 0);\n"
            "    else\n"
            "        action = sfxVoiceSustain(&voice, sustain);",
            audio,
        )
        crouch = (ROOT / "platform/3ds/source/player_crouch.c").read_text(encoding="utf-8")
        frame = crouch[crouch.index("void playerCrouchFrame"):]
        self.assertLess(frame.index("sfx_latched = 0;"), frame.index("note("))
        self.assertNotIn("140.0f", crouch)
        self.assertNotIn("160.0f", crouch)
        channels = set(re.findall(r"ndspChn\w+\((\d+)", audio))
        self.assertEqual(channels, {"0"})
        voice_c = (ROOT / "tools/banjo3ds/sfx_probe/sfx_voice.c").read_text(encoding="utf-8")
        self.assertNotIn("ndspChn", voice_c)
        self.assertNotIn("ndspInit", voice_c)
        self.assertNotIn("3ds.h", voice_c)
        for name in GAMEPLAY:
            gameplay = (ROOT / "platform/3ds/source" / name).read_text(encoding="utf-8")
            self.assertNotIn("sfxProbe", gameplay)
            self.assertNotIn("sfxVoice", gameplay)
            self.assertNotIn("ndsp", gameplay)


class SfxVoiceLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="sfx-voice-life-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.libs = []
        source = ROOT / "tools/banjo3ds/sfx_probe/sfx_voice.c"
        include = ROOT / "tools/banjo3ds/sfx_probe"
        probe_header = (include / "sfx_probe.h").read_text(encoding="utf-8")
        voice_header = (include / "sfx_voice.h").read_text(encoding="utf-8")
        for token in (
            "#define SFX_PROBE_RATE 22000",
            "#define SFX_PROBE_SLIDE_MS 2000",
            "#define SFX_SLIDE_SOURCE_VOLUME 28000",
            "#define SFX_CLOSER_SOURCE_VOLUME 22000",
            "#define SFX_LEVEL_TABLE 32767",
            "#define SFX_SLIDE_LOOP 1",
            "#define SFX_SLIDE_ONCE 2",
            "#define SFX_VOICE_QUEUE_SLIDE 1",
            "#define SFX_VOICE_SET_RATE 2",
            "#define SFX_VOICE_STOP_SLIDE 4",
            "#define SFX_VOICE_QUEUE_CLOSER 8",
            "#define SFX_PITCH_RNG_SEED 0x4D343133u",
        ):
            if token not in probe_header and token not in voice_header:
                raise AssertionError(token)
        if "SFX_PROBE_GAP" in probe_header or "SFX_PROBE_GAP" in voice_header:
            raise AssertionError("the gap probe is still in the voice headers")
        for opt in ("-O0", "-O2"):
            out = Path(cls.tmp.name) / f"{opt}.so"
            subprocess.run(
                ["cc", opt, "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                 "-I", str(include), str(source), "-o", str(out)],
                check=True,
            )
            lib = C.CDLL(str(out))
            bind_voice(lib)
            cls.libs.append(lib)

    def fresh(self, lib):
        voice = Voice()
        lib.sfxVoiceReset(C.byref(voice))
        return voice

    def assert_pitch_in_range(self, lib, voice):
        pitch = lib.sfxVoicePitch(C.byref(voice))
        self.assertGreaterEqual(pitch, lib.sfxSlidePitchMin())
        self.assertLessEqual(pitch, lib.sfxSlidePitchMax())
        rate = lib.sfxVoiceRate(C.byref(voice))
        self.assertAlmostEqual(rate / pitch, 22000.0, delta=0.05)
        return pitch

    def test_synth_volume_matches_the_note_on_integers(self):
        for lib in self.libs:
            self.assertEqual(lib.sfxSynthVolume(32767, 127, 28000, 127), 27999)
            self.assertEqual(lib.sfxSynthVolume(32767, 127, 22000, 127), 21999)
            self.assertEqual(lib.sfxSynthVolume(32767, 40, 28000, 90), 6248)
            self.assertEqual(lib.sfxSynthVolume(40000, 127, 28000, 127), 32767)
            self.assertEqual(lib.sfxSynthVolume(32767, 0, 28000, 127), 0)
            self.assertEqual(lib.sfxSynthVolume(32767, -1, 28000, 127), 0)
            self.assertEqual(lib.sfxSynthVolume(-1, 127, 28000, 127), 0)

    def test_pitch_step_stays_inside_the_rare_clamp(self):
        for lib in self.libs:
            low = lib.sfxSlidePitchMin()
            high = lib.sfxSlidePitchMax()
            self.assertAlmostEqual(low, 0.9, places=5)
            self.assertAlmostEqual(high, 1.5, places=5)
            self.assertAlmostEqual(lib.sfxSlidePitchStep(1.0, 0.0), 0.95, places=4)
            self.assertGreater(lib.sfxSlidePitchStep(1.0, 0.999), 1.0)
            self.assertLess(lib.sfxSlidePitchStep(1.0, 0.999), 1.05)
            self.assertEqual(lib.sfxSlidePitchStep(1.0, -5.0), lib.sfxSlidePitchStep(1.0, 0.0))
            self.assertGreater(lib.sfxSlidePitchStep(1.0, 4.0), 1.0)
            self.assertLessEqual(lib.sfxSlidePitchStep(1.0, 4.0), high)
            self.assertEqual(lib.sfxSlidePitchStep(0.9, 0.0), low)
            self.assertEqual(lib.sfxSlidePitchStep(1.5, 1.0), high)
            pitch = 1.0
            for unit in (0.0, 0.25, 0.5, 0.75, 0.999):
                pitch = lib.sfxSlidePitchStep(pitch, unit)
                self.assertGreaterEqual(pitch, low)
                self.assertLessEqual(pitch, high)

    def test_loop_hold_then_one_closer_at_the_last_pitch(self):
        for lib in self.libs:
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 0), 0)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 0)
            other = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(other), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 1000), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(lib.sfxVoicePoll(C.byref(other), 1000), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(voice.pitch, other.pitch)
            self.assertEqual((voice.phase, voice.queue_slide_count, voice.pitch_steps, voice.started_ms),
                             (SLIDE, 1, 1, 1000))
            pitch = self.assert_pitch_in_range(lib, voice)
            self.assertGreater(pitch, 0.94)
            self.assertLess(pitch, 1.06)
            for now in range(1001, 3000):
                self.assertEqual(lib.sfxVoicePoll(C.byref(voice), now), SET_RATE)
                self.assert_pitch_in_range(lib, voice)
            self.assertEqual(voice.pitch_steps, 2000)
            self.assertEqual(voice.queue_slide_count, 1)
            self.assertEqual(lib.sfxVoiceSlideFinished(C.byref(voice), 2999), 0)
            self.assertEqual(voice.phase, SLIDE)
            self.assertEqual(voice.queue_closer_count, 0)
            before = voice.pitch
            steps = voice.pitch_steps
            action = lib.sfxVoicePoll(C.byref(voice), 3000)
            self.assertEqual(action, STOP_SLIDE | QUEUE_CLOSER | SET_RATE)
            self.assertEqual(voice.phase, CLOSER)
            self.assertEqual(voice.queue_closer_count, 1)
            self.assertEqual(voice.queue_slide_count, 1)
            self.assertEqual(voice.pitch_steps, steps)
            self.assertEqual(voice.pitch, before)
            self.assertAlmostEqual(lib.sfxVoiceRate(C.byref(voice)) / voice.pitch, 22000.0, delta=0.05)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 4000), 0)
            self.assertEqual(voice.queue_closer_count, 1)
            self.assertEqual(lib.sfxVoiceSlideFinished(C.byref(voice), 4000), 0)
            lib.sfxVoiceComplete(C.byref(voice))
            self.assertEqual((voice.phase, voice.release_count), (DONE, 0))
            lib.sfxVoiceComplete(C.byref(voice))
            self.assertEqual(voice.release_count, 0)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 4001), 0)
            self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 0)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 0)
            lib.sfxVoiceReset(C.byref(voice))
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)

    def test_once_buffer_finished_does_not_take_another_pitch_step(self):
        for lib in self.libs:
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_ONCE, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 10), QUEUE_SLIDE | SET_RATE)
            pitch = voice.pitch
            action = lib.sfxVoiceSlideFinished(C.byref(voice), 11)
            self.assertEqual(action, STOP_SLIDE | QUEUE_CLOSER | SET_RATE)
            self.assertEqual((voice.phase, voice.pitch_steps, voice.pitch, voice.queue_closer_count),
                             (CLOSER, 1, pitch, 1))
            self.assertEqual(lib.sfxVoiceSlideFinished(C.byref(voice), 12), 0)
            self.assertEqual(voice.queue_closer_count, 1)

    def test_hold_survives_the_signed_millisecond_boundary(self):
        start = 2147483000
        early = start + 1999 - 2**32
        ready = start + 2000 - 2**32
        for lib in self.libs:
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), start), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(voice.started_ms, start)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), early), SET_RATE)
            self.assertEqual(voice.phase, SLIDE)
            action = lib.sfxVoicePoll(C.byref(voice), ready)
            self.assertEqual(action, STOP_SLIDE | QUEUE_CLOSER | SET_RATE)
            self.assertEqual(voice.phase, CLOSER)
            wrapped = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(wrapped), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoicePoll(C.byref(wrapped), -100), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(lib.sfxVoicePoll(C.byref(wrapped), 1899), SET_RATE)
            self.assertEqual(lib.sfxVoicePoll(C.byref(wrapped), 1900), STOP_SLIDE | QUEUE_CLOSER | SET_RATE)

    def test_shutdown_during_the_slide_does_not_play_the_closer(self):
        for lib in self.libs:
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 0)
            self.assertEqual(voice.phase, IDLE)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 0)
            self.assertEqual((voice.phase, voice.armed, voice.queue_slide_count), (DONE, 0, 0))
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 10), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 1)
            self.assertEqual((voice.phase, voice.release_count, voice.queue_closer_count), (DONE, 1, 0))
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 5000), 0)
            self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 0)
            self.assertEqual(voice.release_count, 1)

    def test_shutdown_during_the_closer_releases_once(self):
        for lib in self.libs:
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 0), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 2000), STOP_SLIDE | QUEUE_CLOSER | SET_RATE)
            self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 2)
            self.assertEqual((voice.phase, voice.release_count, voice.queue_closer_count), (DONE, 1, 1))
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 3000), 0)
            self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 0)

    def test_missing_closer_stops_without_queueing_one(self):
        for lib in self.libs:
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 0, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 0), QUEUE_SLIDE | SET_RATE)
            steps = voice.pitch_steps
            action = lib.sfxVoicePoll(C.byref(voice), 2000)
            self.assertEqual(action, STOP_SLIDE)
            self.assertEqual((voice.phase, voice.queue_closer_count, voice.pitch_steps), (DONE, 0, steps))
            self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 2001), 0)

    def test_missing_ndsp_asset_or_rate_never_queues(self):
        for lib in self.libs:
            for ready, slide, _closer, rate, hold in (
                (0, SLIDE_LOOP, 1, 22000, 2000),
                (1, SLIDE_NONE, 1, 22000, 2000),
                (1, 3, 1, 22000, 2000),
                (1, SLIDE_LOOP, 1, 22050, 2000),
                (1, SLIDE_LOOP, 1, 28000, 2000),
                (1, SLIDE_ONCE, 1, 22000, 0),
                (1, SLIDE_ONCE, 1, 22000, -5),
            ):
                voice = self.fresh(lib)
                self.assertEqual(lib.sfxVoiceBind(C.byref(voice), ready, slide, 1, rate, hold), 0)
                self.assertEqual(voice.phase, SKIPPED)
                self.assertEqual(voice.armed, 0)
                self.assertEqual(voice.slide_ready, SLIDE_NONE)
                self.assertEqual(lib.sfxVoicePoll(C.byref(voice), 0), 0)
                self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 1), 0)
                self.assertEqual(voice.queue_slide_count, 0)
                self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 0)
                self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 0)

    def test_null_pointers_are_safe(self):
        for lib in self.libs:
            self.assertEqual(lib.sfxVoiceBind(None, 1, SLIDE_LOOP, 1, 22000, 2000), 0)
            self.assertEqual(lib.sfxVoicePoll(None, 0), 0)
            self.assertEqual(lib.sfxVoiceSustain(None, 1), 0)
            self.assertEqual(lib.sfxVoiceSlideFinished(None, 0), 0)
            self.assertEqual(lib.sfxVoiceShutdown(None), 0)
            self.assertEqual(lib.sfxVoicePitch(None), 1.0)
            self.assertEqual(lib.sfxVoiceRate(None), 0.0)
            lib.sfxVoiceReset(None)
            lib.sfxVoiceComplete(None)

    def test_sustain_holds_past_the_old_probe_and_closes_once(self):
        for lib in self.libs:
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 0), 0)
            self.assertEqual((voice.phase, voice.pitch_steps, voice.queue_slide_count, voice.pitch),
                             (IDLE, 0, 0, 1.0))
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 1), QUEUE_SLIDE | SET_RATE)
            self.assertEqual((voice.phase, voice.queue_slide_count, voice.pitch_steps), (SLIDE, 1, 1))
            self.assert_pitch_in_range(lib, voice)
            for _ in range(3000):
                self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 1), SET_RATE)
                self.assert_pitch_in_range(lib, voice)
            self.assertEqual((voice.phase, voice.pitch_steps, voice.queue_slide_count, voice.queue_closer_count),
                             (SLIDE, 3001, 1, 0))
            held = voice.pitch
            steps = voice.pitch_steps
            action = lib.sfxVoiceSustain(C.byref(voice), 0)
            self.assertEqual(action, STOP_SLIDE | QUEUE_CLOSER | SET_RATE)
            self.assertEqual((voice.phase, voice.pitch, voice.pitch_steps, voice.queue_closer_count),
                             (CLOSER, held, steps, 1))
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 0), 0)
            self.assertEqual(voice.queue_closer_count, 1)
            lib.sfxVoiceComplete(C.byref(voice))
            self.assertEqual(voice.phase, DONE)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 0), 0)
            self.assertEqual(voice.phase, DONE)

    def test_sustain_pitch_continues_across_a_second_crouch(self):
        for lib in self.libs:
            coast = self.fresh(lib)
            straight = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(coast), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoiceBind(C.byref(straight), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            for _ in range(4):
                lib.sfxVoiceSustain(C.byref(coast), 1)
                lib.sfxVoiceSustain(C.byref(straight), 1)
            self.assertEqual(coast.pitch, straight.pitch)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(coast), 0), STOP_SLIDE | QUEUE_CLOSER | SET_RATE)
            self.assertEqual(coast.pitch, straight.pitch)
            lib.sfxVoiceComplete(C.byref(coast))
            self.assertEqual(lib.sfxVoiceSustain(C.byref(coast), 1), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(straight), 1), SET_RATE)
            self.assertEqual(coast.pitch, straight.pitch)
            self.assertEqual((coast.pitch_steps, coast.queue_slide_count, coast.queue_closer_count), (5, 2, 1))
            self.assertEqual(straight.queue_slide_count, 1)
            self.assert_pitch_in_range(lib, coast)

    def test_sustain_during_the_closer_restarts_the_slide(self):
        for lib in self.libs:
            voice = self.fresh(lib)
            twin = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoiceBind(C.byref(twin), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 1), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(twin), 1), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 0), STOP_SLIDE | QUEUE_CLOSER | SET_RATE)
            action = lib.sfxVoiceSustain(C.byref(voice), 1)
            self.assertEqual(action, STOP_SLIDE | QUEUE_SLIDE | SET_RATE)
            self.assertEqual(action & QUEUE_CLOSER, 0)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(twin), 1), SET_RATE)
            self.assertEqual(voice.pitch, twin.pitch)
            self.assertEqual((voice.phase, voice.pitch_steps, voice.queue_slide_count, voice.queue_closer_count),
                             (SLIDE, 2, 2, 1))
            self.assert_pitch_in_range(lib, voice)

    def test_missing_closer_can_start_again_after_the_stop(self):
        for lib in self.libs:
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 0, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 1), QUEUE_SLIDE | SET_RATE)
            steps = voice.pitch_steps
            pitch = voice.pitch
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 0), STOP_SLIDE)
            self.assertEqual((voice.phase, voice.queue_closer_count, voice.pitch_steps, voice.pitch),
                             (DONE, 0, steps, pitch))
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 1), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(voice.phase, SLIDE)
            self.assertEqual(voice.queue_slide_count, 2)
            self.assertGreater(voice.pitch_steps, steps)
            self.assert_pitch_in_range(lib, voice)

    def test_shutdown_disarms_sustain(self):
        for lib in self.libs:
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 1), QUEUE_SLIDE | SET_RATE)
            self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 1)
            self.assertEqual((voice.phase, voice.armed, voice.queue_closer_count, voice.release_count),
                             (DONE, 0, 0, 1))
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 1), 0)
            voice = self.fresh(lib)
            self.assertEqual(lib.sfxVoiceBind(C.byref(voice), 1, SLIDE_LOOP, 1, 22000, 2000), 1)
            lib.sfxVoiceSustain(C.byref(voice), 1)
            lib.sfxVoiceSustain(C.byref(voice), 0)
            self.assertEqual(voice.phase, CLOSER)
            self.assertEqual(lib.sfxVoiceShutdown(C.byref(voice)), 2)
            self.assertEqual((voice.armed, voice.queue_closer_count, voice.release_count), (0, 1, 1))
            self.assertEqual(lib.sfxVoiceSustain(C.byref(voice), 1), 0)


@unittest.skipUnless((ROOT / "decompressed.us.v10.z64").is_file(), "us.v10 ROM is not in the workspace")
class SfxRomLoopTests(unittest.TestCase):
    def test_us_v10_sfx18_loop_state_matches_the_linear_frame(self):
        rom = (ROOT / "decompressed.us.v10.z64").read_bytes()
        ctl, tbl = slice_soundfont(rom, "us.v10")
        info, pcm = extract_sfx(ctl, tbl, 0x18)
        self.assertEqual(info.sound_index, 0x18)
        self.assertEqual((info.loop_start, info.loop_end), (2391, 12154))
        self.assertIn(info.loop_count, (-1, 0xFFFFFFFF))
        self.assertEqual(len(info.loop_state), 16)
        frame = (info.loop_start // 16) * 16
        self.assertEqual(frame, 2384)
        diff = max(abs(left - right) for left, right in zip(pcm[frame:frame + 16], info.loop_state))
        self.assertEqual(diff, 0)
        before = max(
            abs(left - right)
            for left, right in zip(pcm[info.loop_start - 16:info.loop_start], info.loop_state)
        )
        self.assertGreater(before, 0)
        split = verified_adpcm_loop(pcm, info.loop_start, info.loop_end, info.loop_count, info.loop_state)
        self.assertIsNotNone(split)
        intro, body = split
        self.assertEqual(len(intro), 2391)
        self.assertEqual(len(body), 12154 - 2391)
        self.assertEqual(len(intro) + len(body), info.loop_end)
        landing, landing_pcm = extract_sfx(ctl, tbl, 0x19)
        self.assertEqual(landing.sound_index, 0x19)
        self.assertIsNone(landing.loop_start)
        self.assertIsNone(landing.loop_state)
        self.assertIsNone(verified_adpcm_loop(
            landing_pcm, landing.loop_start, landing.loop_end, landing.loop_count, landing.loop_state
        ))
        self.assertEqual((info.attack_volume, info.sample_volume), (127, 127))
        self.assertEqual((landing.attack_volume, landing.sample_volume), (127, 127))
        self.assertEqual(info.decay_time, -1)
        self.assertEqual((info.release_time, landing.release_time), (3200, 3200))
