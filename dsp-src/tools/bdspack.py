#!/usr/bin/env python3
"""Extract, disassemble, patch, and pack Korg ESX-1 uPD77213 DSP firmware (.BDS).

Container layout of ESX0102D.BDS (983,040 bytes = 0xF0000):
  Copy 0: 0x00000..0x6FFFF (448 KiB) + Gap 0x70000..0x7FFFF (64 KiB)
    - 80-byte header at 0x00000 (KORG, pid=0x00000071, "BDS\0", ver="01020000")
    - IRAM: 0x00050..0x05737 (0x56E8 bytes = 5,562 32-bit words, (lo16_BE, hi16_BE))
            Loaded at DSP IRAM base 0x0200..0x17B9 (free cave 0x0A94..0x0FFF = 1,388 words!)
    - XRAM: 0x05738..0x0C737 (0x7000 bytes = 14,336 u16 words, 0x0000..0x37FF)
    - YRAM: 0x0C738..0x13737 (0x7000 bytes = 14,336 u16 words, 0x0000..0x37FF)
    - Checksum fixup word at 0x6FFFC so 32-bit BE word sum of 0x00000..0x7FFFF == 0x00000000
  Copy 1: 0x80000..0xEFFFF (448 KiB)
    - Same layout; differs from Copy 0 only at IRAM 0x029F..0x02A0 (*x:0x38d0 = 0xb333)
    - Checksum fixup word at 0xEFFFC so 32-bit BE word sum of 0x80000..0xEFFFF == 0x00000000
  Full file (0x00000..0xEFFFF) 32-bit BE word sum == 0x00000000.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import struct
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dspasm

BDS_SIZE = 0xF0000
HDR_SIZE = 0x50
IRAM_BYTES = 0x56E8
IRAM_WORDS = IRAM_BYTES // 4
IRAM_BASE = 0x0200
COPY1_OFF = 0x80000
FIXUP0_OFF = 0x6FFFC
FIXUP1_OFF = 0xEFFFC

FX_TABLE = [
    (0x1000, 0x1034, "fx_clear_ext",  "Clear FX state & external delay RAM"),
    (0x1034, 0x1039, "fx_bypass",     "FX Bypass (outL=inL, outR=inR)"),
    (0x1039, 0x10F5, "fx_filter",     "LPF / HPF Resonant Filter (FX 14/15)"),
    (0x10F5, 0x1182, "fx_reverb",     "Reverb (FX 0, extRAM)"),
    (0x1182, 0x1232, "fx_dist",       "Distortion (FX 11)"),
    (0x1232, 0x1280, "fx_comp",       "Compressor (FX 10)"),
    (0x1280, 0x1296, "fx_delay_io",   "BPM Delay helper / bus I/O"),
    (0x1296, 0x1344, "fx_talkmod",    "Talking Modulator (FX 8)"),
    (0x1344, 0x1362, "fx_bpmdelay",   "BPM Delay (FX 1)"),
    (0x1362, 0x13DA, "fx_shortdly",   "Short Delay (FX 2, extRAM)"),
    (0x13DA, 0x1446, "fx_eq",         "Parametric EQ (FX 13)"),
    (0x1446, 0x1484, "fx_ringmod",    "Ring Modulator (FX 7)"),
    (0x1484, 0x1538, "fx_phaser",     "Phaser (FX 6)"),
    (0x1538, 0x15CD, "fx_choflg",     "Chorus / Flanger (FX 5, extRAM)"),
    (0x15CD, 0x165D, "fx_moddelay",   "Modulation Delay (FX 3, extRAM)"),
    (0x165D, 0x16EC, "fx_grainsft",   "Grain Shifter (FX 4, extRAM)"),
    (0x16EC, 0x177D, "fx_pitchsft",   "Pitch Shifter (FX 9, extRAM)"),
    (0x177D, 0x17BA, "fx_deci",       "Decimator (FX 12)"),
]


def read_iram(bds: bytes, base_off: int = 0) -> List[int]:
    off = base_off + HDR_SIZE
    out = []
    for i in range(IRAM_WORDS):
        lo, hi = struct.unpack_from(">HH", bds, off + 4 * i)
        out.append((hi << 16) | lo)
    return out


def write_iram(buf: bytearray, words: List[int], base_off: int = 0) -> None:
    assert len(words) == IRAM_WORDS
    off = base_off + HDR_SIZE
    for i, w in enumerate(words):
        struct.pack_into(">HH", buf, off + 4 * i, w & 0xFFFF, (w >> 16) & 0xFFFF)


def word_sum(data: bytes | bytearray) -> int:
    s = 0
    for (v,) in struct.iter_unpack(">I", data):
        s = (s + v) & 0xFFFFFFFF
    return s


def fix_checksums(buf: bytearray) -> None:
    """Adjust 0x6FFFC and 0xEFFFC so Half 0 (0..0x80000), Copy 1 (0x80000..0xF0000), and full file all sum to 0."""
    # Half 0: 0x00000..0x7FFFF
    struct.pack_into(">I", buf, FIXUP0_OFF, 0)
    s0 = word_sum(buf[0x00000:0x80000])
    struct.pack_into(">I", buf, FIXUP0_OFF, (-s0) & 0xFFFFFFFF)
    # Copy 1: 0x80000..0xEFFFF
    struct.pack_into(">I", buf, FIXUP1_OFF, 0)
    s1 = word_sum(buf[0x80000:0xF0000])
    struct.pack_into(">I", buf, FIXUP1_OFF, (-s1) & 0xFFFFFFFF)
    assert word_sum(buf[0x00000:0x80000]) == 0
    assert word_sum(buf[0x80000:0xF0000]) == 0
    assert word_sum(buf) == 0


def cmd_extract(bds_path: Path, out_dir: Path) -> None:
    bds = bds_path.read_bytes()
    assert len(bds) == BDS_SIZE, f"Expected {BDS_SIZE} bytes, got {len(bds)}"
    src_dir = out_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    words0 = read_iram(bds, 0)
    words1 = read_iram(bds, COPY1_OFF)

    # Write engine disassembly (0x0200..0x0A93)
    with open(src_dir / "engine.dsp", "w", encoding="utf-8") as f:
        f.write("; Korg ESX-1 uPD77213 DSP Engine (IRAM 0x0200..0x0A93)\n")
        f.write("; Auto-extracted from ESX0102D.BDS. Free IRAM cave: 0x0A94..0x0FFF (1,388 words).\n\n")
        f.write(".org 0x0200\n")
        for pc in range(0x0200, 0x0A94):
            w = words0[pc - IRAM_BASE]
            note = ""
            if words1[pc - IRAM_BASE] != w:
                note = f"  ; Copy1: {dspasm.dis(words1[pc - IRAM_BASE], pc)}"
            f.write(f"    {dspasm.dis(w, pc):<42s} ; {pc:04X}: {w:08X}{note}\n")

    # Write each FX subroutine cleanly
    for a, b, name, desc in FX_TABLE:
        with open(src_dir / f"{name}.dsp", "w", encoding="utf-8") as f:
            f.write(f"; {desc}\n")
            f.write(f"; IRAM 0x{a:04X}..0x{b-1:04X} ({b - a} words)\n\n")
            f.write(f".org 0x{a:04X}\n")
            f.write(f"{name}:\n")
            for pc in range(a, b):
                w = words0[pc - IRAM_BASE]
                f.write(f"    {dspasm.dis(w, pc):<42s} ; {pc:04X}: {w:08X}\n")

    # Verify cave is 100% zeros
    cave = words0[0x0A94 - IRAM_BASE : 0x1000 - IRAM_BASE]
    assert all(w == 0 for w in cave), "Non-zero word in IRAM cave 0x0A94..0x0FFF!"
    print(f"Extracted engine.dsp + {len(FX_TABLE)} FX files into {src_dir}")
    print(f"Verified free IRAM cave: 0x0A94..0x0FFF ({len(cave)} zero words)")


def cmd_build(base_bds: Path, patches: List[Path], out_bds: Path, full_src_dir: Path | None = None) -> None:
    bds = bytearray(base_bds.read_bytes())
    assert len(bds) == BDS_SIZE

    words0 = read_iram(bds, 0)
    words1 = read_iram(bds, COPY1_OFF)

    # Pre-seed standard FX symbols so patches can reference them
    base_labels: Dict[str, int] = {name: a for a, _, name, _ in FX_TABLE}
    base_labels["IRAM_CAVE"] = 0x0A94

    if full_src_dir is not None:
        # Rebuild ALL IRAM from extracted .dsp files (roundtrip verification mode)
        all_files = [full_src_dir / "engine.dsp"] + [full_src_dir / f"{name}.dsp" for _, _, name, _ in FX_TABLE]
        rebuilt: Dict[int, int] = {}
        for p in all_files:
            assembled, _ = dspasm.assemble_source(p.read_text(encoding="utf-8"), base_labels=base_labels)
            rebuilt.update(assembled)
        for pc, w in rebuilt.items():
            idx = pc - IRAM_BASE
            if not (0 <= idx < IRAM_WORDS):
                raise ValueError(f"Address 0x{pc:04X} out of IRAM bounds")
            # Preserve Copy 1's 2-word difference at 0x029F..0x02A0
            if pc not in (0x029F, 0x02A0):
                words1[idx] = w
            words0[idx] = w

    # Apply patch .dsp overlays to BOTH Copy 0 and Copy 1
    total_patched = 0
    for p in patches:
        assembled, labels = dspasm.assemble_source(p.read_text(encoding="utf-8"), base_labels=base_labels)
        base_labels.update(labels)
        for pc, w in sorted(assembled.items()):
            idx = pc - IRAM_BASE
            if not (0 <= idx < IRAM_WORDS):
                raise ValueError(f"Patch {p}: address 0x{pc:04X} outside IRAM (0x0200..0x17B9)")
            words0[idx] = w
            words1[idx] = w
            total_patched += 1
        print(f"Applied patch {p.name}: {len(assembled)} words ({min(assembled):#06x}..{max(assembled):#06x})")

    write_iram(bds, words0, 0)
    write_iram(bds, words1, COPY1_OFF)
    fix_checksums(bds)

    out_bds.parent.mkdir(parents=True, exist_ok=True)
    out_bds.write_bytes(bds)
    sha = hashlib.sha256(bds).hexdigest()
    print(f"Wrote {out_bds} ({len(bds)} B, {total_patched} patched words, wsum=0x00000000, sha256={sha})")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ext = sub.add_parser("extract")
    p_ext.add_argument("--bds", type=Path, required=True)
    p_ext.add_argument("--out", type=Path, required=True)

    p_bld = sub.add_parser("build")
    p_bld.add_argument("--base", type=Path, required=True)
    p_bld.add_argument("--src", type=Path, default=None, help="Optional full src/ dir to reassemble before patching")
    p_bld.add_argument("--patch", type=Path, action="append", default=[])
    p_bld.add_argument("--out", type=Path, required=True)

    args = ap.parse_args()
    if args.cmd == "extract":
        cmd_extract(args.bds, args.out)
    elif args.cmd == "build":
        cmd_build(args.base, args.patch, args.out, args.src)


if __name__ == "__main__":
    main()
