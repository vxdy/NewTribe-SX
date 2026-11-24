# SPDX-License-Identifier: GPL-2.0-only
"""Container of the ESX-1 update files (ESX0101F.BFS boot flash, ESX0102N.BSS system, ESX0102D.BDS DSP).

Measured on the three factory files of OS 1.02 (docs: README.md, "Gemessen"):

    0x00  "KORG"
    0x04  u32 0x00000071 (the same in all three files; meaning unknown)
    0x08  type, 4 bytes: "BFS ", "BSS ", "BDS\0"
    0x0C  version, 4 ASCII digits ("0101" for the boot flash, "0102" for system and DSP) + "0000"
    0x20  payload (BFS: raw image of the boot flash, first instruction at payload 0 = reset vector 0xA0000000)

All three files have the 32-bit big-endian word sum of the *whole file* equal to 0. Which word carries the correction
is not known from the files alone: in the BSS and BDS the last word of the file is data-like, in the BFS the last
non-zero word is at 0x7BFFC (the 16 KiB after it are zero). `fix_sum` therefore takes the word to adjust explicitly.
"""
import struct
from dataclasses import dataclass, field

KNOWN = {b"BFS ": 0x80000, b"BSS ": 0x200000, b"BDS\x00": 0xF0000}
FIXUP_GUESS = {b"BFS ": 0x7BFFC, b"BSS ": 0x200000 - 4, b"BDS\x00": 0xF0000 - 4}


@dataclass
class Report:
    name: str
    ok: bool = True
    kind: str = "?"
    version: str = "?"
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def word_sum(data):
    n = len(data) // 4
    return sum(struct.unpack(f">{n}I", data[:n * 4])) & 0xFFFFFFFF


def check(data, name=""):
    r = Report(name)
    if len(data) < 0x40 or data[:4] != b"KORG":
        r.ok = False
        r.problems.append("keine KORG-Kopfzeile")
        return r
    kind = bytes(data[8:12])
    r.kind = kind.decode("latin-1").strip("\x00 ")
    r.version = bytes(data[12:16]).decode("latin-1")
    if kind not in KNOWN:
        r.ok = False
        r.problems.append(f"unbekannter Typ {kind!r}")
    elif len(data) != KNOWN[kind]:
        r.ok = False
        r.problems.append(f"Größe 0x{len(data):X}, erwartet 0x{KNOWN[kind]:X}")
    if len(data) % 4:
        r.ok = False
        r.problems.append("Länge nicht durch 4 teilbar")
    s = word_sum(data)
    if s:
        r.ok = False
        r.problems.append(f"Wortsumme 0x{s:08X} statt 0 (der Updater meldet dann vermutlich CkSumErr)")
    return r


def fix_sum(data, offset):
    """Return a copy whose word sum is 0 again, by changing the 32-bit word at `offset`."""
    out = bytearray(data)
    old = struct.unpack_from(">I", out, offset)[0]
    s = word_sum(bytes(out))
    struct.pack_into(">I", out, offset, (old - s) & 0xFFFFFFFF)
    return bytes(out)


def payload(data):
    return bytes(data[0x20:])
