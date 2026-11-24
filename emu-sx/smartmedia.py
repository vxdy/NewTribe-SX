# SPDX-License-Identifier: GPL-2.0-only
"""Builds a 16 MB SmartMedia card image (NAND chip EC 73) with an MBR, a FAT12 volume and files in the root directory.

Physical layout (standard SSFDC): block 0 holds the CIS, logical block n of zone 0 sits in physical block n + 1.
Spare (16 bytes per 512-byte page): [4] data status, [5] block status, [6:8] and [11:13] logical block address
field `0x1000 | lba << 1 | parity`, [8:11] ECC of the second 256 bytes, [13:16] ECC of the first 256 bytes.
"""
import struct

from nand import PAGE, SPARE, PAGES_PER_BLOCK

CIS = bytes.fromhex(
    "0103d901ff1802df0120040000000021020401220201012203020407"
    "1a050103000 20f1b08c0c0a10155080020".replace(" ", "") +
    "1b0ac1419901556 4f0ffff20".replace(" ", "") +
    "1b0c8241 18ea61f00107f60301ee".replace(" ", "") +
    "1b0c8341 18ea61700107f60301ee".replace(" ", "") +
    "15140500202020202020002020202020200000ff1400ff00")


def lba_field(lba):
    v = 0x1000 | (lba << 1)
    if bin(v).count("1") % 2:
        v |= 1
    return v


def _col_pairs(k):
    """Column-parity contribution of a set bit k (0..7) of a byte: three bit-address pairs in the third ECC byte."""
    return sum(((2 if (k >> n) & 1 else 1) << (2 + 2 * n)) for n in range(3))


_COLBYTE = []
for _v in range(256):
    _c = 0
    for _k in range(8):
        if (_v >> _k) & 1:
            _c ^= _col_pairs(_k)
    _COLBYTE.append(_c)
_PAR = [bin(i).count("1") & 1 for i in range(256)]
_LINE = [0] * 256
for _i in range(256):
    _l = 0
    for _j in range(8):
        _l |= (2 if (_i >> _j) & 1 else 1) << (2 * _j)
    _LINE[_i] = _l


def spare_ecc(chunk):
    """ECC as stored in the spare area: the first two bytes swapped (as the boot flash compares them)."""
    e = ecc256(chunk)
    return bytes([e[1], e[0], e[2]])


def ecc256(chunk):
    """The 3-byte ECC the boot flash computes over 256 bytes (measured against its own routine, see ecc_matrix.py):
    ~(line parity pairs of the byte address as bytes [hi, lo], column parity pairs of the bit address)."""
    lp = 0
    cp = 0
    for i, v in enumerate(chunk):
        cp ^= _COLBYTE[v]
        if _PAR[v]:
            lp ^= _LINE[i]
    return bytes([~(lp >> 8) & 0xFF, ~lp & 0xFF, ~cp & 0xFF])


def fat12_volume(files, total_sectors):
    spc = 16
    reserved, nfats, root_entries = 1, 2, 512
    root_sectors = root_entries * 32 // 512
    clusters_guess = total_sectors // spc
    fat_sectors = (clusters_guess * 3 // 2 + 511) // 512 + 1
    data_start = reserved + nfats * fat_sectors + root_sectors
    clusters = (total_sectors - data_start) // spc
    assert clusters < 4085, "not FAT12"
    vol = bytearray(total_sectors * 512)
    bpb = struct.pack("<3s8sHBHBHHBHHHIIBBBI11s8s", bytes([0xEB, 0x3C, 0x90]), b"MSDOS5.0", 512, spc, reserved, nfats, root_entries,
                      0, 0xF8, fat_sectors, 16, 4, 16, total_sectors, 0x80, 0, 0x29, 0x12345678, b"NO NAME    ", b"FAT12   ")
    vol[:len(bpb)] = bpb
    vol[510:512] = bytes([0x55, 0xAA])
    entries = [0xFF8, 0xFFF] + [0] * (clusters + 2)

    root = bytearray(root_sectors * 512)
    nxt = 2
    data = {}
    for idx, (name, content) in enumerate(files):
        base, _, ext = name.partition(".")
        n = (len(content) + spc * 512 - 1) // (spc * 512) or 1
        first = nxt
        for c in range(n):
            entries[first + c] = first + c + 1 if c < n - 1 else 0xFFF
        nxt += n
        root[idx * 32:(idx + 1) * 32] = (base.upper().ljust(8).encode() + ext.upper().ljust(3).encode() + bytes([0x20]) +
                                         bytes(10) + struct.pack("<HHHI", 0, 0x2021, first, len(content)))
        data[first] = content
    fat = bytearray(fat_sectors * 512)
    for i in range(0, len(entries) - 1, 2):
        v = entries[i] | (entries[i + 1] << 12)
        o = i * 3 // 2
        if o + 2 < len(fat):
            fat[o:o + 3] = bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF])
    for f in (0, 1):
        o = (reserved + f * fat_sectors) * 512
        vol[o:o + len(fat)] = fat
    ro = (reserved + nfats * fat_sectors) * 512
    vol[ro:ro + len(root)] = root
    for first, content in data.items():
        o = (data_start + (first - 2) * spc) * 512
        vol[o:o + len(content)] = content
    return bytes(vol)


def build_card(files, size_mb=16):
    """files: [(name, bytes)]. Returns a NAND chip image of pages (512 + 16 bytes each). One zone = 1024 physical blocks with
    1000 logical blocks; zone 0 keeps its first physical block for the CIS."""
    blocks = size_mb * 1024 * 1024 // (PAGE * PAGES_PER_BLOCK)
    zones = blocks // 1024
    logical_blocks = 1000
    total = zones * logical_blocks * PAGES_PER_BLOCK
    fatvol = fat12_volume(files, total - 16)
    mbr = bytearray(512)
    entry = bytes([0x80, 0x01, 0x01, 0x00, 0x01, 0x03, 0xF0, 0xF3]) + struct.pack("<II", 16, total - 16)
    mbr[0x1BE:0x1BE + 16] = entry
    mbr[510:512] = bytes([0x55, 0xAA])
    sectors = bytes(mbr) + bytes(15 * 512) + fatvol          # partition starts at sector 16
    sectors = sectors.ljust(total * 512, bytes(1))
    pages = bytearray(bytes([0xFF]) * (blocks * PAGES_PER_BLOCK * (PAGE + SPARE)))

    def put(page_no, data, spare):
        o = page_no * (PAGE + SPARE)
        pages[o:o + PAGE] = data
        pages[o + PAGE:o + PAGE + SPARE] = spare

    # the boot flash accepts a card only if the CIS block's block-address fields (spare 6..7 and 11..12) are zero
    cis = CIS.ljust(PAGE, bytes(1))
    put(0, cis, bytes([0xFF] * 6 + [0, 0]) + spare_ecc(cis[256:]) + bytes([0, 0]) + spare_ecc(cis[:256]))
    for z in range(zones):
        for lb in range(logical_blocks):
            phys = z * 1024 + lb + (1 if z == 0 else 0)
            ba = struct.pack(">H", lba_field(lb))
            for p in range(PAGES_PER_BLOCK):
                sidx = (z * logical_blocks + lb) * PAGES_PER_BLOCK + p
                data = sectors[sidx * 512:(sidx + 1) * 512]
                if data == bytes(512) and False:
                    continue
                spare = bytes([0xFF] * 4) + bytes([0xFF, 0xFF]) + ba + spare_ecc(data[256:]) + ba + spare_ecc(data[:256])
                put(phys * PAGES_PER_BLOCK + p, data, spare)
    return bytes(pages)


def formatted_blank(size_mb=16):
    """A chip with only the CIS block written and every other block erased (free)."""
    blocks = size_mb * 1024 * 1024 // (PAGE * PAGES_PER_BLOCK)
    pages = bytearray(b"\xff" * (blocks * PAGES_PER_BLOCK * (PAGE + SPARE)))
    cis = CIS.ljust(PAGE, bytes(1))
    spare = bytes([0xFF] * 6 + [0, 0]) + spare_ecc(cis[256:]) + bytes([0, 0]) + spare_ecc(cis[:256])
    pages[:PAGE] = cis
    pages[PAGE:PAGE + SPARE] = spare
    return bytes(pages)
