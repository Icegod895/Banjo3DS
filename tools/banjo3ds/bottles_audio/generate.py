"""Generate the three Bottles PCM headers from a local US v1.0 ROM.

No ROM or decoded audio is shipped with this tool. The exact input digest and
output digests bind the extraction to the P34 hardware-tested inputs.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import os
import sys
import tempfile
from pathlib import Path

from tools.banjo3ds.sfx_bank import extract_sfx, slice_soundfont, verified_adpcm_loop

ROM_SHA256 = {
    "US v1.0 cartridge image": "59875835b9a5128bb0054315a7f929e2071c2001e528d70bf543e1d6680e6eff",
    "US v1.0 decompressed image": "8b7289cf26bf64035fccff51df17a43a8dca02e03264186cca069099454caec9",
}
HEADER_SHA256 = {
    "generated_sfx_bottles.h": "710fa39fe803afe5770f59bce42335a63e2ffa792e92befd1ce17c64458b5b91",
    "generated_sfx_bottles_remaining.h": "3fae41ec462f03b852753a17a35ac487824e5385867fd8454aebf4a7588badca",
    "generated_sfx_bottles_retreat.h": "ea93da89c41de8b0450392b972e84b94f7b7f979c5bd156e82485fc13331eea2",
}
INTRO_SHA256 = "27bd2859ea173fd0f04b6ac81626e3958cb47b89428038f6d543b02cd0ffcbb9"
LOOP_SHA256 = "559732ec112402187667462bdefd74452ec49010a19a084502f00fcbb7dd540e"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pcm_bytes(samples: list[int]) -> bytes:
    values = array.array("h", samples)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def render(rom: bytes) -> dict[str, bytes]:
    if digest(rom) not in ROM_SHA256.values():
        raise ValueError("unsupported ROM: expected a verified US v1.0 cartridge or decompressed image SHA-256")
    ctl, tbl = slice_soundfont(rom, "us.v10")
    c6, c6_samples = extract_sfx(ctl, tbl, 0xC6)
    if c6.sound_index != 0xC6 or c6.loop_start is not None or len(c6_samples) != 4880 or c6.peak_abs == 0:
        raise ValueError("SFX_C6 metadata mismatch")
    c6_pcm = pcm_bytes(c6_samples)
    lines = [
        "/* Isolated P30 extraction from original us.v10 soundfont1 via sfx_bank.py.",
        " * SFX_C6_SHAKING_MOUTH; source: smbottles.c state 2 at anim progress .14.",
        " * Test-only generated input; not an original repository asset. */",
        "#ifndef GENERATED_SFX_BOTTLES_H", "#define GENERATED_SFX_BOTTLES_H",
        "#define BANJO_BOTTLES_C6_INDEX 0xC6",
        f"#define BANJO_BOTTLES_C6_PCM_BYTES {len(c6_pcm)}",
        f"#define BANJO_BOTTLES_C6_PCM_SAMPLES {len(c6_samples)}",
        f"#define BANJO_BOTTLES_C6_ATTACK_VOLUME {c6.attack_volume}",
        f"#define BANJO_BOTTLES_C6_SAMPLE_VOLUME {c6.sample_volume}",
        "static const unsigned char banjo_bottles_c6_pcm[BANJO_BOTTLES_C6_PCM_BYTES] = {",
    ]
    for at in range(0, len(c6_pcm), 16):
        lines.append("    " + ", ".join(f"0x{x:02x}" for x in c6_pcm[at:at + 16]) + ",")
    lines.extend(["};", "#endif", ""])
    result = {"generated_sfx_bottles.h": "\n".join(lines).encode("ascii")}

    lines = [
        "/* P32 isolated extraction from original us.v10 soundfont1.",
        " * SFX_2C and SFX_C5 are smbottles.c state-2 events at .40 and .75.",
        " * Not an original-repository generated asset. */",
        "#ifndef GENERATED_SFX_BOTTLES_REMAINING_H", "#define GENERATED_SFX_BOTTLES_REMAINING_H",
    ]
    for sound_id, label, expected_key in ((0x2C, "SFX2C", 42), (0xC5, "SFXC5", 60)):
        info, samples = extract_sfx(ctl, tbl, sound_id)
        if (info.sound_index != sound_id or info.wave_type != "ADPCM" or
                info.loop_start is not None or info.key_base != expected_key or
                info.detune != 0 or info.peak_abs == 0 or len(samples) != info.pcm_samples):
            raise ValueError(f"SFX_{sound_id:02X} metadata mismatch")
        pcm = pcm_bytes(samples)
        prefix = f"BANJO_BOTTLES_{label}"
        lines.extend((
            f"#define {prefix}_INDEX 0x{sound_id:X}",
            f"#define {prefix}_PCM_BYTES {len(pcm)}",
            f"#define {prefix}_PCM_SAMPLES {len(samples)}",
            f"#define {prefix}_KEY_BASE {info.key_base}",
            f"#define {prefix}_DETUNE {info.detune}",
            f"static const unsigned char banjo_bottles_{label.lower()}_pcm[{prefix}_PCM_BYTES] = {{",
        ))
        for at in range(0, len(pcm), 16):
            lines.append("    " + ", ".join(f"0x{x:02x}" for x in pcm[at:at + 16]) + ",")
        lines.append("};")
    lines.extend(("#endif", ""))
    result["generated_sfx_bottles_remaining.h"] = "\n".join(lines).encode("ascii")

    ctl2, tbl2 = rom[0xEA3EB0:0xEADE60], rom[0xEADE60:0xF19250]
    retreat, samples = extract_sfx(ctl2, tbl2, 0x10)
    if (retreat.sound_index != 0x10 or retreat.wave_type != "ADPCM" or
            (retreat.loop_start, retreat.loop_end, retreat.loop_count) != (108, 3324, 0xFFFFFFFF) or
            (retreat.key_base, retreat.detune, retreat.bank_sample_rate) != (32, 0, 22050) or
            len(samples) != 3344):
        raise ValueError("SFX_3F9 metadata mismatch")
    parts = verified_adpcm_loop(samples, retreat.loop_start, retreat.loop_end,
                                retreat.loop_count, retreat.loop_state)
    if parts is None:
        raise ValueError("SFX_3F9 ADPCM loop state mismatch")
    intro, loop = parts
    if len(intro) != 108 or len(loop) != 3216 or intro + loop != samples[:3324]:
        raise ValueError("SFX_3F9 loop boundary mismatch")
    if digest(pcm_bytes(intro)) != INTRO_SHA256 or digest(pcm_bytes(loop)) != LOOP_SHA256:
        raise ValueError("SFX_3F9 PCM mismatch")
    lines = [
        "/* P33 isolated US v1.0 soundfont2 item 0x10 (SFX_3F9).",
        " * Original ADPCM loop state verified against the linear decoded frame.",
        " * Intro 0..107, loop 108..3323; no original-repository regeneration. */",
        "#ifndef GENERATED_SFX_BOTTLES_RETREAT_H", "#define GENERATED_SFX_BOTTLES_RETREAT_H",
        "#define BANJO_BOTTLES_RETREAT_SFX_ID 0x3F9",
        "#define BANJO_BOTTLES_RETREAT_SOUNDFONT_INDEX 0x10",
        "#define BANJO_BOTTLES_RETREAT_KEY_BASE 32", "#define BANJO_BOTTLES_RETREAT_DETUNE 0",
        "#define BANJO_BOTTLES_RETREAT_LOOP_START 108", "#define BANJO_BOTTLES_RETREAT_LOOP_END 3324",
        "#define BANJO_BOTTLES_RETREAT_LOOP_COUNT 0xffffffffu",
    ]
    for name, part in (("INTRO", intro), ("LOOP", loop)):
        pcm = pcm_bytes(part)
        prefix = f"BANJO_BOTTLES_RETREAT_{name}"
        lines.extend((
            f"#define {prefix}_PCM_SAMPLES {len(part)}",
            f"#define {prefix}_PCM_BYTES {len(pcm)}",
            f"static const unsigned char banjo_bottles_retreat_{name.lower()}_pcm[{prefix}_PCM_BYTES] = {{",
        ))
        for at in range(0, len(pcm), 16):
            lines.append("    " + ", ".join(f"0x{x:02x}" for x in pcm[at:at + 16]) + ",")
        lines.append("};")
    lines.extend(("#endif", ""))
    result["generated_sfx_bottles_retreat.h"] = "\n".join(lines).encode("ascii")
    for name, data in result.items():
        if digest(data) != HEADER_SHA256[name]:
            raise ValueError(f"{name}: generated bytes differ from P34 reference")
    return result


def generate(rom_path: Path, output_dir: Path) -> dict[str, bytes]:
    outputs = render(rom_path.read_bytes())  # Validate everything before any output write.
    output_dir.mkdir(parents=True, exist_ok=True)
    pending: list[tuple[Path, Path]] = []
    try:
        for name, data in outputs.items():
            with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{name}.", dir=output_dir,
                                             delete=False) as handle:
                handle.write(data)
                pending.append((Path(handle.name), output_dir / name))
        for temporary, destination in pending:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in pending:
            temporary.unlink(missing_ok=True)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True, help="local verified US v1.0 cartridge or decompressed ROM")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        outputs = generate(args.rom, args.output_dir)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Bottles audio generation failed: {error}\n")
    for name, data in outputs.items():
        print(f"{name} {digest(data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
