#!/usr/bin/env python3
"""bsspack - pack / unpack / verify the ESX-1 system update file ESX0102N.BSS.

File format (all measured on the factory file, see ../README.md):
    0x00  'KORG'                      magic
    0x04  u32 BE 0x00000071           format id (identical in BFS/BSS/BDS; not validated by anything we found)
    0x08  'BSS '                      file type (BFS , BSS , 'BDS\0')
    0x0C  '0102'                      version string (ASCII), followed by '0000'  (0x10..0x13)
    0x14  zeros up to 0x20            reserved
    0x20  payload, exactly 0x1FFFE0 bytes  = system image, loaded by the boot flash to SDRAM 0x0C080000
          (no compression, no encryption); the whole file is exactly 2 MiB
Checksum: the 32-bit big-endian word sum of the *entire file* (header included) is 0 mod 2^32.  The boot-flash updater
rejects other files (CkSumErr).  There is no dedicated checksum field: the factory file has the correction in its last
word (inside the RAM filler at the end, which the firmware overwrites), so `pack` recomputes exactly that word:
    last_word = -(sum of all other words)
For the unmodified payload this reproduces the original byte for byte.
The boot flash stores the file in the internal NAND as payload followed by the 32 byte header, and copies it to SDRAM
0x0C080000 (payload) / 0x0C27FFE0 (header); the entry point is 0x0C081000 (payload offset 0x1000), VBR = 0x0C080000.

usage:  bsspack.py unpack FILE.BSS OUT_DIR       -> OUT_DIR/payload.bin + header.json
        bsspack.py pack PAYLOAD.bin OUT.BSS [--header header.json] [--version 0102]
        bsspack.py check FILE.BSS
"""
import argparse
import json
import struct
import sys

MAGIC = b"KORG"
FORMAT_ID = 0x71
TYPE = b"BSS "
FILE_SIZE = 0x200000
HDR = 0x20
PAYLOAD_SIZE = FILE_SIZE - HDR


def word_sum(data):
    n = len(data) // 4
    return sum(struct.unpack(">%dI" % n, data[:n * 4])) & 0xFFFFFFFF


def make_header(version=b"0102", fmt=FORMAT_ID, typ=TYPE, extra=b"0000"):
    h = bytearray(HDR)
    h[0:4] = MAGIC
    struct.pack_into(">I", h, 4, fmt)
    h[8:12] = typ
    h[12:16] = version
    h[16:20] = extra
    return bytes(h)


def fix_last_word(data):
    d = bytearray(data)
    struct.pack_into(">I", d, len(d) - 4, 0)
    s = word_sum(bytes(d))
    struct.pack_into(">I", d, len(d) - 4, (-s) & 0xFFFFFFFF)
    return bytes(d)


def pack(payload, header=None):
    if len(payload) != PAYLOAD_SIZE:
        raise ValueError("payload must be 0x%X bytes, got 0x%X" % (PAYLOAD_SIZE, len(payload)))
    h = header if header is not None else make_header()
    if len(h) != HDR:
        raise ValueError("header must be 0x20 bytes")
    return fix_last_word(h + payload)


def unpack(data):
    if len(data) != FILE_SIZE:
        raise ValueError("unexpected size 0x%X" % len(data))
    if data[:4] != MAGIC or data[8:12] != TYPE:
        raise ValueError("not an ESX BSS file")
    return data[:HDR], data[HDR:]


def check(data):
    probs = []
    if len(data) != FILE_SIZE:
        probs.append("size 0x%X != 0x%X" % (len(data), FILE_SIZE))
    if data[:4] != MAGIC:
        probs.append("bad magic")
    if data[8:12] != TYPE:
        probs.append("type is %r" % data[8:12])
    if word_sum(data):
        probs.append("word sum 0x%08X (must be 0)" % word_sum(data))
    return probs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("unpack")
    u.add_argument("file")
    u.add_argument("outdir")
    p = sub.add_parser("pack")
    p.add_argument("payload")
    p.add_argument("out")
    p.add_argument("--header")
    p.add_argument("--version", default="0102")
    c = sub.add_parser("check")
    c.add_argument("file")
    a = ap.parse_args(argv)
    if a.cmd == "unpack":
        import os
        data = open(a.file, "rb").read()
        h, pl = unpack(data)
        os.makedirs(a.outdir, exist_ok=True)
        open(os.path.join(a.outdir, "payload.bin"), "wb").write(pl)
        json.dump({"header_hex": h.hex(), "version": h[12:16].decode(), "last_word": data[-4:].hex()},
                  open(os.path.join(a.outdir, "header.json"), "w"), indent=1)
        print("payload 0x%X bytes, header %s, word sum %08X" % (len(pl), h[:16], word_sum(data)))
    elif a.cmd == "pack":
        pl = open(a.payload, "rb").read()
        hdr = bytes.fromhex(json.load(open(a.header))["header_hex"]) if a.header else make_header(a.version.encode())
        out = pack(pl, hdr)
        open(a.out, "wb").write(out)
        print("wrote %s (%d bytes), word sum %08X" % (a.out, len(out), word_sum(out)))
    else:
        data = open(a.file, "rb").read()
        probs = check(data)
        for x in probs:
            print("FAIL:", x)
        if not probs:
            print("OK: size, magic, type, word sum")
        return 1 if probs else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
