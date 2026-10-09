"""Generate the gitignored slide-lifecycle header for the 3DS probe.

The header lands in platform/3ds/build or the repository build directory.
PCM bytes stay out of Git. A missing ROM or soundfont writes a zero-length
asset and exits 0, so the 3DS build still runs.

SFX_18 is split into a one-shot intro and a looping body only when
verified_adpcm_loop accepts the bank's ADPCM loop state. Otherwise the full
wave is embedded once and the probe does not loop it. SFX_19 is the one-shot
closer. Both waves stay 22000 Hz PCM16.
"""

from __future__ import annotations

import argparse
import array
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.banjo3ds.sfx_bank import (
    SFX_18_BIGBUTT_SLIDE,
    SFX_19_BANJO_LANDING_08,
    SfxBankError,
    SfxInfo,
    extract_sfx,
    resolve_output_path,
    slice_soundfont,
    supported_versions,
    verified_adpcm_loop,
)

# Must match tools/banjo3ds/sfx_probe/sfx_probe.h.
# 22000 Hz is the N64 AI output clock, not the bank field 22050 or loudness 28000.
SFX_PROBE_RATE = 22000
SFX_PROBE_SLIDE_MS = 2000
SFX_SLIDE_SOURCE_VOLUME = 28000
SFX_CLOSER_SOURCE_VOLUME = 22000
SFX_LEVEL_TABLE = 32767
# us.v10 SFX_18 loop, checked only when a verified split has these bounds.
RARE_SFX18_LOOP_START = 2391
RARE_SFX18_LOOP_END = 12154
_PROBE_HEADER = Path(__file__).resolve().parent / "sfx_probe" / "sfx_probe.h"
_PROBE_HEADER_TEXT = _PROBE_HEADER.read_text(encoding="utf-8")
for _name, _value in (
    ("SFX_PROBE_RATE", SFX_PROBE_RATE),
    ("SFX_PROBE_SLIDE_MS", SFX_PROBE_SLIDE_MS),
    ("SFX_SLIDE_SOURCE_VOLUME", SFX_SLIDE_SOURCE_VOLUME),
    ("SFX_CLOSER_SOURCE_VOLUME", SFX_CLOSER_SOURCE_VOLUME),
    ("SFX_LEVEL_TABLE", SFX_LEVEL_TABLE),
):
    if f"#define {_name} {_value}" not in _PROBE_HEADER_TEXT:
        raise RuntimeError(f"{_name} does not match tools/banjo3ds/sfx_probe/sfx_probe.h")

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADER_ROOTS = (
    REPO_ROOT / "build",
    REPO_ROOT / "platform" / "3ds" / "build",
)
PCM19_NAME = Path("build") / "sfx" / "sfx_0019.pcm16"
PCM18_NAME = Path("build") / "sfx" / "sfx_0018.pcm16"


@dataclass(frozen=True)
class ProbeClip:
    sfx_id: int
    blob: bytes
    source: str
    sound_index: int | None
    attack_volume: int | None = None
    sample_volume: int | None = None
    intro: bytes = b""
    loop: bytes = b""
    loop_start: int = 0
    loop_end: int = 0
    loop_verified: bool = False


def resolve_header_path(path: Path, root: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not any(resolved == allowed or allowed in resolved.parents for allowed in HEADER_ROOTS):
        raise SfxBankError(
            "SFX probe header must stay inside build/ or platform/3ds/build/"
        )
    return resolved


def pcm_bytes(samples: list[int]) -> bytes:
    encoded = array.array("h", samples)
    if sys.byteorder != "little":
        encoded.byteswap()
    return encoded.tobytes()


def usable_pcm(blob: bytes) -> bool:
    if len(blob) < 2 or len(blob) % 2 != 0:
        return False
    return any(blob[index : index + 2] != b"\x00\x00" for index in range(0, len(blob), 2))


def _slide_parts(info: SfxInfo, samples: list[int]) -> tuple[bytes, bytes, int, int, bool]:
    """Return the intro, the loop body, and whether the ADPCM state matched."""
    split = verified_adpcm_loop(
        samples, info.loop_start, info.loop_end, info.loop_count, info.loop_state
    )
    if split is None or info.loop_start is None or info.loop_end is None:
        return b"", b"", 0, 0, False
    intro_samples, loop_samples = split
    loop_blob = pcm_bytes(loop_samples)
    intro_blob = pcm_bytes(intro_samples) if intro_samples else b""
    if not usable_pcm(loop_blob) or len(intro_blob) % 2 != 0:
        return b"", b"", 0, 0, False
    return intro_blob, loop_blob, info.loop_start, info.loop_end, True


def _decode_clip(ctl: bytes, tbl: bytes, sfx_id: int, label: str) -> ProbeClip:
    info, samples = extract_sfx(ctl, tbl, sfx_id)
    if info.sound_index != sfx_id:
        raise SfxBankError(
            f"SFX {sfx_id:#x} selected soundArray index {info.sound_index:#x}"
        )
    if info.peak_abs == 0:
        raise SfxBankError(f"decoded SFX {sfx_id:#x} PCM is silent")
    blob = pcm_bytes(samples)
    if not usable_pcm(blob):
        raise SfxBankError(f"decoded SFX {sfx_id:#x} PCM is not a usable PCM16 buffer")
    intro, loop, start, end, verified = (b"", b"", 0, 0, False)
    if sfx_id == SFX_18_BIGBUTT_SLIDE:
        intro, loop, start, end, verified = _slide_parts(info, samples)
    return ProbeClip(
        sfx_id,
        blob,
        label,
        info.sound_index,
        info.attack_volume,
        info.sample_volume,
        intro,
        loop,
        start,
        end,
        verified,
    )


def _decode_pair(ctl: bytes, tbl: bytes, label: str) -> tuple[ProbeClip, ...]:
    return (
        _decode_clip(ctl, tbl, SFX_19_BANJO_LANDING_08, label),
        _decode_clip(ctl, tbl, SFX_18_BIGBUTT_SLIDE, label),
    )


def _fallback_clips(root: Path) -> tuple[ProbeClip, ...]:
    clips = []
    for sfx_id, pcm_name in (
        (SFX_19_BANJO_LANDING_08, PCM19_NAME),
        (SFX_18_BIGBUTT_SLIDE, PCM18_NAME),
    ):
        path = root / pcm_name
        if not path.is_file():
            continue
        blob = path.read_bytes()
        if usable_pcm(blob):
            clips.append(ProbeClip(sfx_id, blob, path.as_posix(), None))
    return tuple(clips)


def _emit_clip(lines: list[str], macro: str, symbol: str, blob: bytes) -> None:
    if not blob:
        lines.extend(
            [
                f"#define {macro}_PRESENT 0",
                f"#define {macro}_PCM_BYTES 0",
                f"static const unsigned char {symbol}[1] = {{0}};",
            ]
        )
        return
    lines.append(f"#define {macro}_PRESENT 1")
    lines.append(f"#define {macro}_PCM_BYTES {len(blob)}")
    lines.append(f"static const unsigned char {symbol}[{macro}_PCM_BYTES] = {{")
    for offset in range(0, len(blob), 16):
        chunk = ", ".join(f"0x{byte:02x}" for byte in blob[offset : offset + 16])
        lines.append(f"    {chunk},")
    lines.append("};")


def _volume_lines(macro: str, clip: ProbeClip | None) -> list[str]:
    if clip is None or clip.attack_volume is None or clip.sample_volume is None:
        return [
            f"#define {macro}_VOLUME_KNOWN 0",
            f"#define {macro}_ATTACK_VOLUME 0",
            f"#define {macro}_SAMPLE_VOLUME 0",
        ]
    return [
        f"#define {macro}_VOLUME_KNOWN 1",
        f"#define {macro}_ATTACK_VOLUME {clip.attack_volume}",
        f"#define {macro}_SAMPLE_VOLUME {clip.sample_volume}",
    ]


def render_header(clips: tuple[ProbeClip, ...], source: str) -> str:
    by_id = {clip.sfx_id: clip for clip in clips}
    closer = by_id.get(SFX_19_BANJO_LANDING_08)
    slide = by_id.get(SFX_18_BIGBUTT_SLIDE)
    verified = bool(slide and slide.loop_verified)
    intro = slide.intro if verified and slide is not None else b""
    loop = slide.loop if verified and slide is not None else b""
    once = b"" if verified or slide is None else slide.blob
    start = slide.loop_start if verified and slide is not None else 0
    end = slide.loop_end if verified and slide is not None else 0
    lines = [
        "/* Generated by tools/banjo3ds/sfx_probe_asset.py.",
        " * Local build output. Do not commit.",
        f" * source: {source}",
        f" * sfx_0019_bytes: {0 if closer is None else len(closer.blob)}",
        f" * sfx_0018_bytes: {0 if slide is None else len(slide.blob)}",
        f" * sfx_0018_intro_bytes: {len(intro)}",
        f" * sfx_0018_loop_bytes: {len(loop)}",
        f" * rate_hz: {SFX_PROBE_RATE}",
        f" * slide_ms: {SFX_PROBE_SLIDE_MS}",
        f" * loop_verified: {1 if verified else 0}",
        " * order: sfx 0x18 for the slide hold, then one sfx 0x19",
        " */",
        "#ifndef GENERATED_SFX_PROBE_H",
        "#define GENERATED_SFX_PROBE_H",
        "#define BANJO_SFX19_INDEX 0x19",
        "#define BANJO_SFX18_INDEX 0x18",
        "#define BANJO_SFX_PROBE_RATE_HZ 22000",
        "#define BANJO_SFX_PROBE_SLIDE_MS 2000",
        f"#define BANJO_SFX18_LOOP_VERIFIED {1 if verified else 0}",
        f"#define BANJO_SFX18_LOOP_START {start}",
        f"#define BANJO_SFX18_LOOP_END {end}",
    ]
    lines.extend(_volume_lines("BANJO_SFX18", slide))
    lines.extend(_volume_lines("BANJO_SFX19", closer))
    _emit_clip(lines, "BANJO_SFX19", "banjo_sfx19_pcm", b"" if closer is None else closer.blob)
    _emit_clip(lines, "BANJO_SFX18_INTRO", "banjo_sfx18_intro_pcm", intro)
    _emit_clip(lines, "BANJO_SFX18_LOOP", "banjo_sfx18_loop_pcm", loop)
    _emit_clip(lines, "BANJO_SFX18_ONCE", "banjo_sfx18_once_pcm", once)
    lines.extend(
        [
            '_Static_assert(BANJO_SFX19_INDEX == 0x19, "SFX_19 selects soundArray index 0x19");',
            '_Static_assert(BANJO_SFX18_INDEX == 0x18, "SFX_18 selects soundArray index 0x18");',
            '_Static_assert(BANJO_SFX_PROBE_RATE_HZ == 22000, "the probe plays at the N64 AI rate");',
            '_Static_assert(BANJO_SFX_PROBE_SLIDE_MS == 2000, "the slide hold is 2000 ms");',
            '_Static_assert(BANJO_SFX19_PCM_BYTES == 0 || (BANJO_SFX19_PCM_BYTES % 2) == 0, "SFX_19 PCM16");',
            '_Static_assert(BANJO_SFX18_INTRO_PCM_BYTES == 0 || (BANJO_SFX18_INTRO_PCM_BYTES % 2) == 0, "SFX_18 intro PCM16");',
            '_Static_assert(BANJO_SFX18_LOOP_PCM_BYTES == 0 || (BANJO_SFX18_LOOP_PCM_BYTES % 2) == 0, "SFX_18 loop PCM16");',
            '_Static_assert(BANJO_SFX18_ONCE_PCM_BYTES == 0 || (BANJO_SFX18_ONCE_PCM_BYTES % 2) == 0, "SFX_18 one-shot PCM16");',
            '_Static_assert(BANJO_SFX18_LOOP_VERIFIED == 0 || BANJO_SFX18_INTRO_PCM_BYTES / 2 == BANJO_SFX18_LOOP_START, "intro is [0, start)");',
            '_Static_assert(BANJO_SFX18_LOOP_VERIFIED == 0 || BANJO_SFX18_INTRO_PCM_BYTES / 2 + BANJO_SFX18_LOOP_PCM_BYTES / 2 == BANJO_SFX18_LOOP_END, "body is [start, end)");',
            '_Static_assert(BANJO_SFX18_LOOP_VERIFIED == 0 || BANJO_SFX18_LOOP_PRESENT == 1, "verified loop has a body");',
            '_Static_assert(BANJO_SFX18_LOOP_VERIFIED == 1 || BANJO_SFX18_LOOP_PRESENT == 0, "unverified slide does not loop a slice");',
            '_Static_assert(BANJO_SFX18_LOOP_VERIFIED == 1 || BANJO_SFX18_INTRO_PRESENT == 0, "unverified slide has no intro slice");',
            '_Static_assert(BANJO_SFX18_LOOP_VERIFIED == 0 || BANJO_SFX18_ONCE_PRESENT == 0, "verified loop is not also a one-shot");',
        ]
    )
    if verified and start == RARE_SFX18_LOOP_START and end == RARE_SFX18_LOOP_END:
        lines.extend(
            [
                '_Static_assert(BANJO_SFX18_LOOP_START == 2391, "SFX_18 loop start");',
                '_Static_assert(BANJO_SFX18_LOOP_END == 12154, "SFX_18 loop end");',
            ]
        )
    lines.extend(["#endif", ""])
    return "\n".join(lines)


def describe_clips(clips: tuple[ProbeClip, ...]) -> str:
    parts = []
    for clip in clips:
        index = "fallback" if clip.sound_index is None else f"index {clip.sound_index:#x}"
        extra = ""
        if clip.sfx_id == SFX_18_BIGBUTT_SLIDE:
            extra = (
                f" loop {1 if clip.loop_verified else 0}"
                f" intro {len(clip.intro)} body {len(clip.loop)}"
            )
        parts.append(f"sfx {clip.sfx_id:#x} {index} bytes {len(clip.blob)}{extra}")
    return "; ".join(parts)


def load_pcm(root: Path, rom: Path | None, version: str | None,
             ctl_path: Path | None, tbl_path: Path | None,
             allow_fallback: bool) -> tuple[tuple[ProbeClip, ...], str]:
    if ctl_path is not None or tbl_path is not None:
        if ctl_path is None or tbl_path is None:
            raise SfxBankError("ctl and tbl are required together")
        if not ctl_path.is_file() or not tbl_path.is_file():
            raise SfxBankError("missing soundfont ctl or tbl")
        clips = _decode_pair(
            ctl_path.read_bytes(), tbl_path.read_bytes(), f"ctl {ctl_path.name}"
        )
        return clips, clips[0].source
    if rom is not None:
        if version is None:
            raise SfxBankError("a ROM requires a version")
        if not rom.is_file():
            raise SfxBankError(f"missing decompressed ROM: {rom}")
        label = f"decompressed.{version}.z64"
        clips = _decode_pair(*slice_soundfont(rom.read_bytes(), version), label)
        return clips, label
    # us.v10 is listed before pal. The first ROM that exists wins.
    # A corrupt first ROM raises before a later ROM or the PCM fallback.
    for candidate in supported_versions():
        path = root / f"decompressed.{candidate}.z64"
        if path.is_file():
            clips = _decode_pair(*slice_soundfont(path.read_bytes(), candidate), path.name)
            return clips, path.name
    if allow_fallback:
        clips = _fallback_clips(root)
        if clips:
            return clips, "fallback"
    return (), "none"


def write_header(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_pcm(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(blob)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the local SFX_18 slide then SFX_19 closer 3DS probe header."
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--version", choices=supported_versions())
    parser.add_argument("--ctl", type=Path)
    parser.add_argument("--tbl", type=Path)
    parser.add_argument("--pcm18", type=Path, help="Also write full SFX_18 PCM16 inside build/")
    parser.add_argument("--pcm19", type=Path, help="Also write SFX_19 PCM16 inside build/")
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--require", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    # Absolute --out is the 3DS makefile path. Relative --out is anchored at --root.
    anchor = REPO_ROOT if args.out.is_absolute() else root
    try:
        header_path = resolve_header_path(args.out, anchor)
    except SfxBankError as error:
        print(f"sfx-probe: {error}", file=sys.stderr)
        return 1
    try:
        pcm_paths = {
            SFX_18_BIGBUTT_SLIDE: resolve_output_path(args.pcm18) if args.pcm18 is not None else None,
            SFX_19_BANJO_LANDING_08: resolve_output_path(args.pcm19) if args.pcm19 is not None else None,
        }
        clips, source = load_pcm(
            root, args.rom, args.version, args.ctl, args.tbl, not args.no_fallback
        )
        if not clips:
            raise SfxBankError("no usable SFX_18 or SFX_19 asset")
        write_header(header_path, render_header(clips, source))
        for clip in clips:
            pcm_path = pcm_paths[clip.sfx_id]
            if pcm_path is not None:
                _write_pcm(pcm_path, clip.blob)
    except SfxBankError as error:
        if args.require:
            print(f"sfx-probe: {error}", file=sys.stderr)
            return 1
        write_header(header_path, render_header((), "none"))
        print(f"sfx-probe: {error}; the 3DS build will run without the probe", file=sys.stderr)
        return 0
    print(
        f"sfx-probe: {source} {describe_clips(clips)} "
        f"rate {SFX_PROBE_RATE} slide {SFX_PROBE_SLIDE_MS}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
