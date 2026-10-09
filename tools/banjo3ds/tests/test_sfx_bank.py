"""Synthetic VADPCM and ALBankFile tests. No Rare sample bytes."""

import struct
import unittest
from pathlib import Path

from tools.banjo3ds.sfx_bank import (
    AL_BANK_VERSION,
    BUILD_DIR,
    SOUND_FONT_1_RANGES,
    SfxBankError,
    decode_raw16,
    decode_vadpcm,
    extract_sfx,
    main,
    resolve_output_path,
    slice_soundfont,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def _book(order, npredictors, fill):
    """fill(predictor, coefficient, position) -> int coefficient."""
    values = []
    for predictor in range(npredictors):
        for coefficient in range(order):
            for position in range(8):
                values.append(fill(predictor, coefficient, position))
    return values


def _frame(scale, predictor, nibbles):
    if len(nibbles) != 16:
        raise AssertionError("a frame encodes 16 residuals")
    frame = bytearray(9)
    frame[0] = ((scale & 0xF) << 4) | (predictor & 0xF)
    for index in range(8):
        high = nibbles[index * 2] & 0xF
        low = nibbles[index * 2 + 1] & 0xF
        frame[1 + index] = (high << 4) | low
    return bytes(frame)


class VadpcmTests(unittest.TestCase):
    def test_zero_book_returns_signed_scaled_residuals(self):
        # Scale lives in the high nibble. Nibble 0xF is -1 and 0x8 is -8.
        # A zero codebook leaves each residual unchanged after the /2048.
        book = _book(2, 1, lambda _p, _c, _k: 0)
        frame = _frame(0, 0, [1, 0xF, 2, 0x8, 0, 0, 0, 0, 7, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(
            decode_vadpcm(frame, 2, 1, book),
            [1, -1, 2, -8, 0, 0, 0, 0, 7, 0, 0, 0, 0, 0, 0, 0],
        )
        scaled = _frame(1, 0, [1, 0xF, 2, 0x8, 0, 0, 0, 0, 7, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(
            decode_vadpcm(scaled, 2, 1, book)[:4],
            [2, -2, 4, -16],
        )

    def test_predictor_reads_the_previous_frames_last_samples(self):
        # Coefficient 2048 on position 0, column 0 copies the older history
        # sample (previous output[14]) onto the next frame's first sample.
        book = _book(2, 1, lambda _p, coefficient, position: 2048 if coefficient == 0 and position == 0 else 0)
        first = _frame(0, 0, [0] * 14 + [4, 1])
        second = _frame(0, 0, [0] * 16)
        decoded = decode_vadpcm(first + second, 2, 1, book)
        self.assertEqual(decoded[14:16], [4, 1])
        self.assertEqual(decoded[16], 4)
        self.assertEqual(decoded[17:], [0] * 15)

    def test_negative_accumulator_uses_floor_division(self):
        # 3000 * -1 = -3000, and -3000 // 2048 is -2.
        book = _book(2, 1, lambda _p, coefficient, position: 3000 if coefficient == 0 and position == 0 else 0)
        state = [0] * 16
        state[14] = -1
        decoded = decode_vadpcm(_frame(0, 0, [0] * 16), 2, 1, book, state)
        self.assertEqual(decoded[0], -2)

    def test_residual_coupling_follows_the_last_coefficient_column(self):
        # order-2 column 1, position 0 is 1024. That copies into the scale
        # column and then one step into the next residual.
        # Residuals 2, 2 produce samples 2, (1024*2 + 2048*2)//2048 = 3,
        # and (1024*2)//2048 = 1.
        def coefficient(_predictor, column, position):
            if column == 1 and position == 0:
                return 1024
            return 0

        decoded = decode_vadpcm(_frame(0, 0, [2, 2] + [0] * 14), 2, 1, _book(2, 1, coefficient))
        self.assertEqual(decoded[:4], [2, 3, 1, 0])

    def test_predictor_index_selects_the_book_entry(self):
        def coefficient(predictor, column, position):
            if predictor == 0 and column == 0 and position == 0:
                return 2048
            return 0

        book = _book(2, 2, coefficient)
        state = [0] * 16
        state[14] = 3
        chosen = decode_vadpcm(_frame(0, 1, [0] * 16), 2, 2, book, state)
        other = decode_vadpcm(_frame(0, 0, [0] * 16), 2, 2, book, state)
        self.assertEqual(chosen[0], 0)
        self.assertEqual(other[0], 3)

    def test_samples_saturate_to_int16(self):
        book = _book(2, 1, lambda _p, _c, _k: 0)
        frame = _frame(15, 0, [7, 0x8] + [0] * 14)
        self.assertEqual(decode_vadpcm(frame, 2, 1, book)[:2], [32767, -32768])

    def test_frame_predictor_outside_the_book_fails(self):
        book = _book(2, 1, lambda _p, _c, _k: 0)
        with self.assertRaises(SfxBankError):
            decode_vadpcm(_frame(0, 4, [0] * 16), 2, 1, book)

    def test_raw16_is_big_endian(self):
        self.assertEqual(decode_raw16(b"\x12\x34\xff\xfe"), [0x1234, -2])

    def test_odd_raw16_length_fails(self):
        with self.assertRaises(SfxBankError):
            decode_raw16(b"\x00\x01\x02")


def _u32(value):
    return struct.pack(">I", value)


def _s32(value):
    return struct.pack(">i", value)


def _s16(value):
    return struct.pack(">h", value)


def _synthetic_bank(wave, wave_type, book=None, sound_count=0x1A, sample_rate=22050):
    """One bank, one instrument, every sound pointer aimed at one wave."""
    if sound_count != 0x1A:
        raise AssertionError("the fixture layout reserves 0x1a sound pointers")
    instrument_at = 0x18
    pointers_at = 0x28
    sound_at = pointers_at + sound_count * 4
    envelope_at = sound_at + 0x10
    keymap_at = envelope_at + 0x10
    wave_at = keymap_at + 0x10
    loop_at = 0
    if book is None:
        book_at = 0
        book_bytes = b""
    else:
        book_at = (wave_at + 0x20 + 7) & ~7
        order = 2
        npredictors = len(book) // (order * 8)
        book_bytes = _s32(order) + _s32(npredictors) + b"".join(_s16(value) for value in book)
    end = book_at + len(book_bytes) if book is not None else wave_at + 0x20
    ctl = bytearray(end)
    ctl[0:4] = _s16(AL_BANK_VERSION) + _s16(1)
    ctl[4:8] = _u32(0x08)
    ctl[0x08:0x10] = _s16(1) + bytes((0, 0)) + _s32(sample_rate)
    ctl[0x10:0x14] = _u32(0)
    ctl[0x14:0x18] = _u32(instrument_at)
    ctl[instrument_at + 14 : instrument_at + 16] = _s16(sound_count)
    for index in range(sound_count):
        struct.pack_into(">I", ctl, pointers_at + index * 4, sound_at)
    struct.pack_into(">III", ctl, sound_at, envelope_at, keymap_at, wave_at)
    ctl[sound_at + 12] = 64
    ctl[sound_at + 13] = 90
    struct.pack_into(">iii", ctl, envelope_at, 10, 20, 30)
    ctl[envelope_at + 12] = 40
    ctl[envelope_at + 13] = 50
    ctl[keymap_at + 4] = 60
    ctl[keymap_at + 5] = (-2) & 0xFF
    struct.pack_into(">IIBB", ctl, wave_at, 0, len(wave), wave_type, 0)
    struct.pack_into(">II", ctl, wave_at + 12, loop_at, book_at)
    if book is not None:
        ctl[book_at : book_at + len(book_bytes)] = book_bytes
    return bytes(ctl), wave


class BankTests(unittest.TestCase):
    def test_extracts_sfx_18_metadata_and_pcm_from_a_synthetic_bank(self):
        book = _book(2, 1, lambda _p, _c, _k: 0)
        frame = _frame(0, 0, [1, 0] + [0] * 14)
        ctl, tbl = _synthetic_bank(frame, 0, book)
        info, pcm = extract_sfx(ctl, tbl, 0x18)
        self.assertEqual(info.sound_index, 0x19)
        self.assertEqual(info.wave_type, "ADPCM")
        self.assertEqual(info.wave_bytes, 9)
        self.assertEqual(info.pcm_samples, 16)
        self.assertEqual(info.sample_volume, 90)
        self.assertEqual((info.attack_time, info.decay_time, info.release_time), (10, 20, 30))
        self.assertEqual((info.attack_volume, info.decay_volume), (40, 50))
        self.assertEqual(info.key_base, 60)
        self.assertEqual(info.detune, -2)
        self.assertEqual(info.bank_sample_rate, 22050)
        self.assertEqual(pcm, [1, 0] + [0] * 14)

    def test_extracts_raw16(self):
        ctl, tbl = _synthetic_bank(b"\x00\x04\xff\xfc", 1)
        info, pcm = extract_sfx(ctl, tbl, 0x18)
        self.assertEqual(info.wave_type, "RAW16")
        self.assertEqual(pcm, [4, -4])
        self.assertIsNone(info.order)

    def test_wrong_revision_fails(self):
        ctl, tbl = _synthetic_bank(b"\x00\x01", 1)
        broken = bytearray(ctl)
        broken[0:2] = _s16(0x4230)
        with self.assertRaises(SfxBankError) as caught:
            extract_sfx(bytes(broken), tbl, 0x18)
        self.assertIn("0x4230", str(caught.exception))

    def test_sound_index_past_the_instrument_fails(self):
        ctl, tbl = _synthetic_bank(b"\x00\x01", 1)
        with self.assertRaises(SfxBankError) as caught:
            extract_sfx(ctl, tbl, 0x1A)
        self.assertIn("0x1b", str(caught.exception))

    def test_wave_past_the_table_fails(self):
        ctl, tbl = _synthetic_bank(b"\x00\x01", 1)
        moved = bytearray(ctl)
        # Wave base sits at the start of the wavetable object.
        wave_at = 0x28 + 0x1A * 4 + 0x30
        struct.pack_into(">I", moved, wave_at, 4)
        with self.assertRaises(SfxBankError) as caught:
            extract_sfx(bytes(moved), tbl, 0x18)
        self.assertIn("extends past", str(caught.exception))

    def test_relocated_bank_flags_fail(self):
        ctl, tbl = _synthetic_bank(b"\x00\x01", 1)
        moved = bytearray(ctl)
        moved[0x0A] = 1
        with self.assertRaises(SfxBankError) as caught:
            extract_sfx(bytes(moved), tbl, 0x18)
        self.assertIn("raw ROM bank", str(caught.exception))

    def test_unknown_wave_type_fails(self):
        ctl, tbl = _synthetic_bank(b"\x00\x01\x00\x02", 7)
        with self.assertRaises(SfxBankError) as caught:
            extract_sfx(ctl, tbl, 0x18)
        self.assertIn("type 7", str(caught.exception))

    def test_missing_input_fails(self):
        self.assertEqual(
            main(["--ctl", "build/does-not-exist-ctl.bin", "--tbl", "build/does-not-exist-tbl.bin"]),
            1,
        )

    def test_output_outside_build_fails(self):
        with self.assertRaises(SfxBankError):
            resolve_output_path(Path("/tmp/sfx_0018.pcm16"))
        with self.assertRaises(SfxBankError):
            resolve_output_path(Path("assets/sfx_0018.pcm16"))
        allowed = resolve_output_path(Path("build/sfx/sfx_0018.pcm16"))
        self.assertEqual(allowed, (BUILD_DIR / "sfx" / "sfx_0018.pcm16").resolve())

    def test_unknown_rom_version_fails(self):
        with self.assertRaises(SfxBankError) as caught:
            slice_soundfont(b"", "us.v11")
        self.assertIn("us.v10", str(caught.exception))
        with self.assertRaises(SfxBankError):
            slice_soundfont(b"\x00" * 16, "jp")

    def test_short_rom_fails_before_reading_a_bank(self):
        _ctl_at, _tbl_at, tbl_end = SOUND_FONT_1_RANGES["us.v10"]
        with self.assertRaises(SfxBankError) as caught:
            slice_soundfont(b"\x00" * 32, "us.v10")
        self.assertIn(f"{tbl_end:#x}", str(caught.exception))

    def test_published_offsets_match_the_yaml(self):
        for version, (ctl_at, tbl_at, tbl_end) in SOUND_FONT_1_RANGES.items():
            text = (REPO_ROOT / f"decompressed.{version}.yaml").read_text(encoding="utf-8")
            self.assertEqual(_yaml_start(text, "soundfont1ctl"), ctl_at)
            self.assertEqual(_yaml_start(text, "soundfont1tbl"), tbl_at)
            self.assertEqual(_yaml_start(text, "soundfont2ctl"), tbl_end)
            self.assertLess(ctl_at, tbl_at)
            self.assertLess(tbl_at, tbl_end)


def _yaml_start(text, name):
    marker = f"- name: {name}\n"
    at = text.find(marker)
    if at < 0:
        raise AssertionError(f"missing {name}")
    window = text[at : at + 160]
    start = window.find("start: 0x")
    if start < 0:
        raise AssertionError(f"missing start for {name}")
    hex_at = start + len("start: ")
    return int(window[hex_at : hex_at + 8], 16)


if __name__ == "__main__":
    unittest.main()
