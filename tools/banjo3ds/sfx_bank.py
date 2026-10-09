"""Read a Banjo-Kazooie soundfont1 bank and decode one SFX wave to PCM16.

The ctl and tbl blobs are the segments already described by
decompressed.us.v10.yaml and decompressed.pal.yaml. This module does not
split a ROM and does not touch tools/n64splat.

Decoded PCM belongs in the repository build/ directory. The bytes of a
real wave are not logged.
"""

from __future__ import annotations

import argparse
import array
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = REPO_ROOT / "build"

AL_BANK_VERSION = 0x4231
AL_ADPCM_WAVE = 0
AL_RAW16_WAVE = 1
ADPCM_FRAME_BYTES = 9
ADPCM_FRAME_SAMPLES = 16
ADPCM_ORDER_VECTOR = 8
ADPCM_STATE_SAMPLES = 16
ADPCM_PREDICTOR_SCALE = 1 << 11

# soundfont1ctl, soundfont1tbl, and the following soundfont2ctl.
# Those three starts are the only SFX-bank bounds published in this repo.
SOUND_FONT_1_RANGES = {
    "us.v10": (0xD846C0, 0xD954B0, 0xEA3EB0),
    "pal": (0xDA8DF0, 0xDB9BE0, 0xEC85E0),
}

# The runtime id is the soundArray index. sfxInstruments_func_8033531C passes
# sfx_id + 1 to func_80244608, which reads soundArray[arg1 - 1]
# (code_AE290.c:40, code_5650.c:593).
SFX_18_BIGBUTT_SLIDE = 0x18
SFX_19_BANJO_LANDING_08 = 0x19


class SfxBankError(Exception):
    """The ctl, tbl, or requested wave is missing or not a supported bank."""


@dataclass(frozen=True)
class SfxInfo:
    sfx_id: int
    sound_index: int
    wave_type: str
    wave_bytes: int
    aligned_wave_bytes: int
    pcm_samples: int
    sample_volume: int
    sample_pan: int
    attack_time: int
    decay_time: int
    release_time: int
    attack_volume: int
    decay_volume: int
    key_base: int
    detune: int
    bank_sample_rate: int
    order: int | None
    npredictors: int | None
    loop_start: int | None
    loop_end: int | None
    loop_count: int | None
    peak_abs: int
    clipped_samples: int


def supported_versions() -> tuple[str, ...]:
    return tuple(SOUND_FONT_1_RANGES)


def slice_soundfont(rom: bytes, version: str) -> tuple[bytes, bytes]:
    """Cut soundfont1 ctl and tbl out of a decompressed ROM."""
    try:
        ctl_at, tbl_at, tbl_end = SOUND_FONT_1_RANGES[version]
    except KeyError:
        supported = ", ".join(supported_versions())
        raise SfxBankError(
            f"unsupported ROM version {version!r}; this repo publishes "
            f"soundfont1 offsets for: {supported}"
        ) from None
    if len(rom) < tbl_end:
        raise SfxBankError(
            f"decompressed {version} ROM is {len(rom)} bytes; "
            f"soundfont1tbl ends at {tbl_end:#x}"
        )
    return rom[ctl_at:tbl_at], rom[tbl_at:tbl_end]


def resolve_output_path(path: Path) -> Path:
    """Keep decoded PCM inside the gitignored repository build directory."""
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (REPO_ROOT / path).resolve()
    build = BUILD_DIR.resolve()
    if resolved != build and build not in resolved.parents:
        raise SfxBankError(
            "PCM output must stay inside the repository build/ directory"
        )
    return resolved


def decode_vadpcm(
    wave: bytes,
    order: int,
    npredictors: int,
    book: list[int],
    state: list[int] | None = None,
) -> list[int]:
    """Decode a VADPCM bitstream to saturated PCM16 samples.

    Each 9-byte frame holds a scale in the high nibble, a predictor index
    in the low nibble, and 16 signed 4-bit residuals. The book stores
    ``order`` vectors of 8 coefficients per predictor. Samples are saturated
    to int16 before they become history, matching ADPCM_STATE.
    """
    if not 1 <= order <= ADPCM_ORDER_VECTOR:
        raise SfxBankError(f"ADPCM order {order} is outside 1..{ADPCM_ORDER_VECTOR}")
    if not 1 <= npredictors <= 16:
        raise SfxBankError(f"ADPCM predictor count {npredictors} is outside 1..16")
    expected = order * npredictors * ADPCM_ORDER_VECTOR
    if len(book) != expected:
        raise SfxBankError(
            f"ADPCM book has {len(book)} coefficients; "
            f"order {order} and {npredictors} predictors require {expected}"
        )
    if len(wave) % ADPCM_FRAME_BYTES != 0:
        raise SfxBankError(
            f"ADPCM wave length {len(wave)} is not a multiple of {ADPCM_FRAME_BYTES}"
        )
    predictors = _expand_book(book, order, npredictors)
    history = _checked_state(state)
    pcm: list[int] = []
    for frame_at in range(0, len(wave), ADPCM_FRAME_BYTES):
        frame = wave[frame_at : frame_at + ADPCM_FRAME_BYTES]
        decoded, history = _decode_frame(frame, history, predictors, order)
        pcm.extend(decoded)
    return pcm


def decode_raw16(wave: bytes) -> list[int]:
    """Decode a big-endian RAW16 wave to host PCM16 samples."""
    if len(wave) < 2 or len(wave) % 2 != 0:
        raise SfxBankError(f"RAW16 wave length {len(wave)} is not a positive even size")
    count = len(wave) // 2
    return list(struct.unpack(f">{count}h", wave))


def extract_sfx(ctl: bytes, tbl: bytes, sfx_id: int) -> tuple[SfxInfo, list[int]]:
    """Decode one SFX from a raw soundfont1 ctl/tbl pair."""
    if sfx_id < 0 or sfx_id > 0x7FFF:
        raise SfxBankError(f"SFX id {sfx_id} is outside the signed 16-bit id range")
    sound_index = sfx_id
    bank = _parse_bank(ctl)
    instrument = _parse_instrument(ctl)
    if sound_index >= instrument.sound_count:
        raise SfxBankError(
            f"SFX {sfx_id:#x} selects soundArray index {sound_index:#x}, "
            f"but the instrument has {instrument.sound_count} sounds"
        )
    sound_offset = _read_u32(
        ctl, instrument.array_at + sound_index * 4, "sound pointer"
    )
    sound = _parse_sound(ctl, sound_offset)
    wave = _parse_wave(ctl, tbl, sound.wave_offset)
    pcm = _decode_wave(wave)
    peak = 0
    clipped = 0
    for sample in pcm:
        magnitude = abs(sample)
        if magnitude > peak:
            peak = magnitude
        if sample in (32767, -32768):
            clipped += 1
    info = SfxInfo(
        sfx_id=sfx_id,
        sound_index=sound_index,
        wave_type=wave.wave_type,
        wave_bytes=wave.stored_bytes,
        aligned_wave_bytes=wave.aligned_bytes,
        pcm_samples=len(pcm),
        sample_volume=sound.sample_volume,
        sample_pan=sound.sample_pan,
        attack_time=sound.attack_time,
        decay_time=sound.decay_time,
        release_time=sound.release_time,
        attack_volume=sound.attack_volume,
        decay_volume=sound.decay_volume,
        key_base=sound.key_base,
        detune=sound.detune,
        bank_sample_rate=bank.sample_rate,
        order=wave.order,
        npredictors=wave.npredictors,
        loop_start=wave.loop_start,
        loop_end=wave.loop_end,
        loop_count=wave.loop_count,
        peak_abs=peak,
        clipped_samples=clipped,
    )
    return info, pcm


def format_report(info: SfxInfo, pcm_path: Path) -> str:
    """Metadata only. Sample bytes stay out of the report."""
    loop = "no"
    if info.loop_start is not None:
        loop = f"start {info.loop_start} end {info.loop_end} count {info.loop_count}"
    order = "none" if info.order is None else str(info.order)
    predictors = "none" if info.npredictors is None else str(info.npredictors)
    rows = [
        f"sfx: {info.sfx_id:#x}",
        f"sound_index: {info.sound_index:#x}",
        f"type: {info.wave_type}",
        f"wave_bytes: {info.wave_bytes}",
        f"aligned_wave_bytes: {info.aligned_wave_bytes}",
        f"pcm_samples: {info.pcm_samples}",
        f"pcm_format: s16le",
        f"sample_volume: {info.sample_volume}",
        f"sample_pan: {info.sample_pan}",
        f"attack_time: {info.attack_time}",
        f"decay_time: {info.decay_time}",
        f"release_time: {info.release_time}",
        f"attack_volume: {info.attack_volume}",
        f"decay_volume: {info.decay_volume}",
        f"key_base: {info.key_base}",
        f"detune: {info.detune}",
        f"bank_sample_rate: {info.bank_sample_rate}",
        f"order: {order}",
        f"npredictors: {predictors}",
        f"loop: {loop}",
        f"peak_abs: {info.peak_abs}",
        f"clipped_samples: {info.clipped_samples}",
        f"pcm: {pcm_path}",
    ]
    return "\n".join(rows) + "\n"


def write_extraction(info: SfxInfo, pcm: list[int], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = array.array("h", pcm)
    if sys.byteorder != "little":
        encoded.byteswap()
    output.write_bytes(encoded.tobytes())
    output.with_suffix(".meta.txt").write_text(format_report(info, output), encoding="utf-8")
    return output


def _expand_book(book: list[int], order: int, npredictors: int) -> list[list[list[int]]]:
    predictors: list[list[list[int]]] = []
    cursor = 0
    width = order + ADPCM_ORDER_VECTOR
    for _predictor in range(npredictors):
        raw = [[0] * order for _position in range(ADPCM_ORDER_VECTOR)]
        for coefficient in range(order):
            for position in range(ADPCM_ORDER_VECTOR):
                raw[position][coefficient] = book[cursor]
                cursor += 1
        table = [[0] * width for _position in range(ADPCM_ORDER_VECTOR)]
        for coefficient in range(order):
            for position in range(ADPCM_ORDER_VECTOR):
                table[position][coefficient] = raw[position][coefficient]
        for position in range(1, ADPCM_ORDER_VECTOR):
            table[position][order] = table[position - 1][order - 1]
        table[0][order] = ADPCM_PREDICTOR_SCALE
        for residual in range(1, ADPCM_ORDER_VECTOR):
            for position in range(residual):
                table[position][order + residual] = 0
            for position in range(residual, ADPCM_ORDER_VECTOR):
                table[position][order + residual] = table[position - residual][order]
        predictors.append(table)
    return predictors


def _checked_state(state: list[int] | None) -> list[int]:
    if state is None:
        return [0] * ADPCM_STATE_SAMPLES
    if len(state) != ADPCM_STATE_SAMPLES:
        raise SfxBankError(
            f"ADPCM state has {len(state)} samples; expected {ADPCM_STATE_SAMPLES}"
        )
    checked: list[int] = []
    for sample in state:
        if sample < -32768 or sample > 32767:
            raise SfxBankError(f"ADPCM state sample {sample} is outside int16")
        checked.append(sample)
    return checked


def _decode_frame(
    frame: bytes,
    history: list[int],
    predictors: list[list[list[int]]],
    order: int,
) -> tuple[list[int], list[int]]:
    scale = 1 << (frame[0] >> 4)
    predictor = frame[0] & 0xF
    if predictor >= len(predictors):
        raise SfxBankError(
            f"ADPCM frame predictor {predictor} is outside the book of {len(predictors)}"
        )
    residuals: list[int] = []
    for byte in frame[1:]:
        for nibble in (byte >> 4, byte & 0xF):
            signed = nibble if nibble <= 7 else nibble - 16
            residuals.append(signed * scale)
    rows = predictors[predictor]
    output = [0] * ADPCM_FRAME_SAMPLES
    for group in range(2):
        if group == 0:
            previous = history[ADPCM_FRAME_SAMPLES - order :]
        else:
            previous = output[ADPCM_ORDER_VECTOR - order : ADPCM_ORDER_VECTOR]
        vector = previous + residuals[group * 8 : group * 8 + 8]
        for position in range(ADPCM_ORDER_VECTOR):
            row = rows[position]
            accumulated = 0
            for coefficient, value in zip(row, vector, strict=True):
                accumulated += coefficient * value
            output[group * 8 + position] = _saturate(accumulated // ADPCM_PREDICTOR_SCALE)
    return output, output


def _saturate(sample: int) -> int:
    if sample > 32767:
        return 32767
    if sample < -32768:
        return -32768
    return sample


@dataclass(frozen=True)
class _Bank:
    sample_rate: int


@dataclass(frozen=True)
class _Instrument:
    sound_count: int
    array_at: int


@dataclass(frozen=True)
class _Sound:
    wave_offset: int
    sample_pan: int
    sample_volume: int
    attack_time: int
    decay_time: int
    release_time: int
    attack_volume: int
    decay_volume: int
    key_base: int
    detune: int


@dataclass(frozen=True)
class _Wave:
    wave_type: str
    stored_bytes: int
    aligned_bytes: int
    payload: bytes
    order: int | None
    npredictors: int | None
    book: list[int] | None
    loop_start: int | None
    loop_end: int | None
    loop_count: int | None


def _parse_bank(ctl: bytes) -> _Bank:
    if len(ctl) < 8:
        raise SfxBankError(f"soundfont ctl is {len(ctl)} bytes")
    revision, bank_count = struct.unpack_from(">hh", ctl, 0)
    if revision != AL_BANK_VERSION:
        raise SfxBankError(
            f"ALBankFile revision {revision & 0xFFFF:#x} is not {AL_BANK_VERSION:#x}"
        )
    if bank_count < 1:
        raise SfxBankError("ALBankFile has no banks")
    bank_offset = _read_u32(ctl, 4, "bank pointer")
    _need(ctl, bank_offset, 16, "bank")
    inst_count, flags, _pad, sample_rate = struct.unpack_from(">hBBi", ctl, bank_offset)
    if flags != 0:
        raise SfxBankError(
            "soundfont ctl bank flags are already set; the file is not a raw ROM bank"
        )
    if inst_count < 1:
        raise SfxBankError("soundfont bank has no instruments")
    if sample_rate <= 0:
        raise SfxBankError(f"soundfont bank sample rate {sample_rate} is not positive")
    return _Bank(sample_rate=sample_rate)


def _parse_instrument(ctl: bytes) -> _Instrument:
    bank_offset = _read_u32(ctl, 4, "bank pointer")
    instrument_offset = _read_u32(ctl, bank_offset + 12, "instrument pointer")
    _need(ctl, instrument_offset, 16, "instrument")
    flags = ctl[instrument_offset + 3]
    if flags != 0:
        raise SfxBankError(
            "soundfont instrument flags are already set; the file is not a raw ROM bank"
        )
    sound_count = struct.unpack_from(">h", ctl, instrument_offset + 14)[0]
    if sound_count < 1:
        raise SfxBankError("soundfont instrument has no sounds")
    array_at = instrument_offset + 16
    _need(ctl, array_at, sound_count * 4, "sound array")
    # Only the selected slot is read, matching func_80244608. A zero pointer
    # in another slot must not reject SFX_18 or SFX_19.
    return _Instrument(sound_count=sound_count, array_at=array_at)


def _parse_sound(ctl: bytes, offset: int) -> _Sound:
    _need(ctl, offset, 16, "sound")
    envelope_offset, keymap_offset, wave_offset = struct.unpack_from(">III", ctl, offset)
    sample_pan = ctl[offset + 12]
    sample_volume = ctl[offset + 13]
    flags = ctl[offset + 14]
    if flags != 0:
        raise SfxBankError(
            "sound flags are already set; the file is not a raw ROM sound"
        )
    _need(ctl, envelope_offset, 14, "envelope")
    attack_time, decay_time, release_time = struct.unpack_from(">iii", ctl, envelope_offset)
    attack_volume = ctl[envelope_offset + 12]
    decay_volume = ctl[envelope_offset + 13]
    _need(ctl, keymap_offset, 6, "keymap")
    key_base = ctl[keymap_offset + 4]
    detune = struct.unpack_from(">b", ctl, keymap_offset + 5)[0]
    if wave_offset == 0:
        raise SfxBankError("sound wave offset is zero")
    return _Sound(
        wave_offset=wave_offset,
        sample_pan=sample_pan,
        sample_volume=sample_volume,
        attack_time=attack_time,
        decay_time=decay_time,
        release_time=release_time,
        attack_volume=attack_volume,
        decay_volume=decay_volume,
        key_base=key_base,
        detune=detune,
    )


def _parse_wave(ctl: bytes, tbl: bytes, offset: int) -> _Wave:
    _need(ctl, offset, 20, "wavetable")
    base, length, wave_type, flags = struct.unpack_from(">IIBB", ctl, offset)
    if flags != 0:
        raise SfxBankError(
            "wavetable flags are already set; the file is not a raw ROM wave"
        )
    if length < 0:
        raise SfxBankError(f"wavetable length {length} is negative")
    if base > len(tbl) or length > len(tbl) - base:
        raise SfxBankError(
            f"wave base {base:#x} length {length} extends past the "
            f"{len(tbl)}-byte sample table"
        )
    loop_offset, book_offset = struct.unpack_from(">II", ctl, offset + 12)
    loop_start = loop_end = loop_count = None
    if loop_offset != 0:
        _need(ctl, loop_offset, 12, "loop")
        loop_start, loop_end, loop_count = struct.unpack_from(">III", ctl, loop_offset)
    if wave_type == AL_ADPCM_WAVE:
        if book_offset == 0:
            raise SfxBankError("ADPCM wave has no codebook")
        if book_offset % 8 != 0:
            raise SfxBankError(f"ADPCM book offset {book_offset:#x} is not 8-byte aligned")
        _need(ctl, book_offset, 8, "codebook")
        order, npredictors = struct.unpack_from(">ii", ctl, book_offset)
        if not 1 <= order <= ADPCM_ORDER_VECTOR or not 1 <= npredictors <= 16:
            raise SfxBankError(
                f"ADPCM book order {order} predictors {npredictors} is not supported"
            )
        coefficient_bytes = 2 * order * npredictors * ADPCM_ORDER_VECTOR
        _need(ctl, book_offset + 8, coefficient_bytes, "codebook coefficients")
        book = list(
            struct.unpack_from(
                f">{coefficient_bytes // 2}h",
                ctl,
                book_offset + 8,
            )
        )
        aligned = length - (length % ADPCM_FRAME_BYTES)
        if aligned == 0:
            raise SfxBankError(f"ADPCM wave length {length} contains no complete frame")
        return _Wave(
            "ADPCM",
            length,
            aligned,
            tbl[base : base + aligned],
            order,
            npredictors,
            book,
            loop_start,
            loop_end,
            loop_count,
        )
    if wave_type == AL_RAW16_WAVE:
        if length < 2 or length % 2 != 0:
            raise SfxBankError(f"RAW16 wave length {length} is not a positive even size")
        return _Wave(
            "RAW16",
            length,
            length,
            tbl[base : base + length],
            None,
            None,
            None,
            loop_start,
            loop_end,
            loop_count,
        )
    raise SfxBankError(f"wavetable type {wave_type} is not ADPCM or RAW16")


def _decode_wave(wave: _Wave) -> list[int]:
    if wave.wave_type == "ADPCM":
        assert wave.order is not None
        assert wave.npredictors is not None
        assert wave.book is not None
        return decode_vadpcm(wave.payload, wave.order, wave.npredictors, wave.book)
    return decode_raw16(wave.payload)


def _read_u32(blob: bytes, offset: int, label: str) -> int:
    _need(blob, offset, 4, label)
    value = struct.unpack_from(">I", blob, offset)[0]
    if value == 0:
        raise SfxBankError(f"{label} offset is zero")
    if value % 4 != 0 or value >= len(blob):
        raise SfxBankError(f"{label} offset {value:#x} is outside the ctl")
    return value


def _need(blob: bytes, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset > len(blob) or size > len(blob) - offset:
        raise SfxBankError(
            f"{label} at {offset:#x} size {size} extends past {len(blob)} ctl bytes"
        )


def _read_input(path: Path, label: str) -> bytes:
    if not path.is_file():
        raise SfxBankError(f"missing {label}: {path}")
    return path.read_bytes()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decode one Banjo-Kazooie SFX wave from soundfont1 to local PCM16."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rom", type=Path, help="decompressed ROM")
    source.add_argument("--ctl", type=Path, help="soundfont1ctl.bin")
    parser.add_argument("--version", choices=supported_versions(), help="ROM version")
    parser.add_argument("--tbl", type=Path, help="soundfont1tbl.bin")
    parser.add_argument("--sfx", type=lambda value: int(value, 0), default=SFX_18_BIGBUTT_SLIDE)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("build/sfx/sfx_0018.pcm16"),
        help="PCM16 path inside build/",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.rom is not None:
            if args.version is None:
                parser.error("--rom requires --version")
            rom = _read_input(args.rom, "decompressed ROM")
            ctl, tbl = slice_soundfont(rom, args.version)
        else:
            if args.tbl is None:
                parser.error("--ctl requires --tbl")
            ctl = _read_input(args.ctl, "soundfont1ctl")
            tbl = _read_input(args.tbl, "soundfont1tbl")
        output = resolve_output_path(args.out)
        info, pcm = extract_sfx(ctl, tbl, args.sfx)
        if info.peak_abs == 0:
            raise SfxBankError("decoded PCM is silent")
        write_extraction(info, pcm, output)
    except SfxBankError as error:
        print(f"sfx-bank: {error}", file=sys.stderr)
        return 1
    print(format_report(info, output), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
