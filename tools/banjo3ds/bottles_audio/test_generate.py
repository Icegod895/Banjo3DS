"""Focused local-ROM reproducibility tests; no ROM or PCM fixtures are shipped."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.banjo3ds.bottles_audio.generate import HEADER_SHA256, ROM_SHA256, generate


class BottlesGeneratorTests(unittest.TestCase):
    rom: Path
    root: Path

    @classmethod
    def setUpClass(cls) -> None:
        if not cls.rom.is_file():
            raise RuntimeError("verified local ROM is required")
        if hashlib.sha256(cls.rom.read_bytes()).hexdigest() not in ROM_SHA256.values():
            raise RuntimeError("test ROM differs from verified US v1.0 ROM")

    def test_two_clean_directories_and_repeated_generation(self) -> None:
        with tempfile.TemporaryDirectory() as area:
            first, second = Path(area) / "first", Path(area) / "second"
            generate(self.rom, first)
            generate(self.rom, second)
            for name, expected in HEADER_SHA256.items():
                a, b = (first / name).read_bytes(), (second / name).read_bytes()
                self.assertEqual(a, b)
                self.assertEqual(hashlib.sha256(a).hexdigest(), expected)
            generate(self.rom, first)
            for name in HEADER_SHA256:
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_missing_rom_no_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as area:
            target = Path(area) / "missing-output-dir"
            with self.assertRaises(FileNotFoundError):
                generate(Path(area) / "missing.z64", target)
            self.assertFalse(target.exists())

    def test_unsupported_and_truncated_rom_no_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as area:
            for name, data in (("unsupported.z64", bytes.fromhex("80371240") + b"\0" * 64),
                               ("truncated.z64", self.rom.read_bytes()[:1024])):
                path, target = Path(area) / name, Path(area) / (name + ".out")
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "unsupported ROM"):
                    generate(path, target)
                self.assertFalse(target.exists())

    def test_cli_failure_is_clear(self) -> None:
        with tempfile.TemporaryDirectory() as area:
            proc = subprocess.run(
                [sys.executable, "-B", "-m", "tools.banjo3ds.bottles_audio.generate",
                 "--rom", str(Path(area) / "absent.z64"), "--output-dir", str(Path(area) / "out")],
                cwd=self.root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("Bottles audio generation failed", proc.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, required=True)
    args, unittest_args = parser.parse_known_args()
    BottlesGeneratorTests.rom = args.rom
    BottlesGeneratorTests.root = Path(__file__).resolve().parents[3]
    unittest.main(argv=[sys.argv[0], *unittest_args])
