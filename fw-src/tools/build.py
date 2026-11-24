#!/usr/bin/env python3
"""build.py - sources -> payload -> ESX0102N.BSS (and optional equality check against the factory file).

    python tools/build.py                       # builds build/ESX0102N.BSS from src/ (order: src/manifest.txt, else sorted *.s)
    python tools/build.py --ref ../factory-firmware/ESX0102N.BSS    # also compare (cmp + sha256)
    python tools/build.py --strict-sum         # fail if the factory last word would have to change (unmodified rebuild check)
    python tools/build.py --no-newtribe --ref ../factory-firmware/ESX0102N.BSS   # vanilla image only (must be IDENTICAL)

The default build = generated src/*.s (factory image, never edited by hand) + the hand-maintained OVERLAY in newtribe/
(see newtribe/manifest.txt and README section 9): the overlay is assembled in the same symbol space, laid over a zero gap
of the image (every destination byte must be 0 in the factory image) and may retarget pointers with `.redirect`.

Steps: shasm (all sources, strict: no gaps) -> payload.bin (0x1FFFE0 bytes at 0x0C080000) -> bsspack.pack (KORG header
from header.json, word-sum correction in the last word).
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bsspack
import shasm


def source_files(src):
    man = os.path.join(src, "manifest.txt")
    if os.path.exists(man):
        out = []
        for line in open(man):
            line = line.split("#")[0].strip()
            if line:
                out.append(os.path.join(src, line))
        return out
    return [os.path.join(src, f) for f in sorted(os.listdir(src)) if f.endswith(".s")]


NEWTRIBE_HEADER_VERSION = b"0103"       # KORG header version of the Newtribe build (factory = 0102)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROOT, "src"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "ESX0102N.BSS"))
    ap.add_argument("--header", default=os.path.join(ROOT, "header.json"))
    ap.add_argument("--ref")
    ap.add_argument("--map", default=os.path.join(ROOT, "build", "fw.map"))
    ap.add_argument("--strict-sum", action="store_true")
    ap.add_argument("--newtribe", default=os.path.join(ROOT, "newtribe"), help="overlay directory (manifest.txt)")
    ap.add_argument("--no-newtribe", action="store_true", help="build the vanilla factory image (no overlay)")
    ap.add_argument("--header-version", default=None, help="override 4- or 8-byte ASCII version in KORG header (default: 0103)")
    a = ap.parse_args(argv)

    files = source_files(a.src)
    asm = shasm.Assembler(strict=True)
    try:
        for f in files:
            asm.add_file(f)
        ovl_files = [] if a.no_newtribe else source_files(a.newtribe)
        for f in ovl_files:
            asm.add_file(f, overlay=True)
        asm.pass1()
        payload = bytearray(asm.pass2())
    except shasm.AsmError as e:
        print("build: assembler error:", e, file=sys.stderr)
        return 1
    for w in asm.warnings:
        print("build: warning:", w)
    if asm.base != 0x0C080000:
        print("build: image must start at 0x0C080000, starts at 0x%08X" % asm.base, file=sys.stderr)
        return 1
    if len(payload) != bsspack.PAYLOAD_SIZE:
        print("build: payload is 0x%X bytes, must be 0x%X (the BSS is a fixed 2 MiB file; shrink or enlarge the RAM filler)" %
              (len(payload), bsspack.PAYLOAD_SIZE), file=sys.stderr)
        return 1
    for addr, data in asm.overlay:
        o = addr - asm.base
        if o < 0 or o + len(data) > len(payload):
            print("build: overlay at 0x%08X (+%d) is outside the image" % (addr, len(data)), file=sys.stderr)
            return 1
        if any(payload[o:o + len(data)]):
            bad = next(i for i in range(len(data)) if payload[o + i])
            print("build: overlay at 0x%08X (+%d bytes) overlaps non-zero image bytes (first at 0x%08X); the overlay may only use "
                  "zero gaps" % (addr, len(data), addr + bad), file=sys.stderr)
            return 1
        payload[o:o + len(data)] = data
        print("build: overlay 0x%08X..0x%08X (%d bytes) laid into the zero gap (%d files)" % (addr, addr + len(data), len(data), len(ovl_files)))
    for addr, new, old in asm.patches:
        o = addr - asm.base
        cur = int.from_bytes(payload[o:o + 4], "big")
        if cur != old:
            print("build: .patchlong at 0x%08X: image holds 0x%08X, expected 0x%08X" % (addr, cur, old), file=sys.stderr)
            return 1
        payload[o:o + 4] = new.to_bytes(4, "big")
        print("build: patched word 0x%08X: 0x%08X -> 0x%08X" % (addr, old, new))
    payload = bytes(payload)
    if not a.no_newtribe and "NEWTRIBE_VERSION" in asm.syms:
        o = asm.lookup("NEWTRIBE_VERSION") - asm.base
        print("build: Newtribe version %r" % payload[o:payload.index(0, o)].decode("latin-1"))
    hdr = bytes.fromhex(json.load(open(a.header))["header_hex"]) if os.path.exists(a.header) else None
    if hdr is not None and not a.no_newtribe:
        # the boot flash updater refuses a file whose header version equals the installed one ("NoUp / SameVer.")
        hv = a.header_version.encode("ascii") if a.header_version else NEWTRIBE_HEADER_VERSION
        if len(hv) not in (4, 8):
            print("build: --header-version must be 4 or 8 ASCII chars, got %r" % a.header_version, file=sys.stderr)
            return 1
        hdr = hdr[:12] + hv + hdr[12 + len(hv):]
        print("build: header version %r" % hv.decode())
    out = bsspack.pack(payload, hdr)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "wb").write(out)
    if a.map:
        with open(a.map, "w") as f:
            for n, v in sorted(((n, asm.lookup(n)) for n in asm.syms), key=lambda x: (x[1], x[0])):
                f.write("%08X %s\n" % (v & 0xFFFFFFFF, n))
    sha = hashlib.sha256(out).hexdigest()
    print("build: %d source files -> %s (%d bytes) sha256 %s" % (len(files), a.out, len(out), sha))
    problems = bsspack.check(out)
    if problems:
        print("build: FAILED container check:", problems)
        return 1
    if a.ref:
        ref = open(a.ref, "rb").read()
        if ref == out:
            print("build: IDENTICAL to %s (sha256 %s)" % (a.ref, hashlib.sha256(ref).hexdigest()))
        else:
            d = [i for i in range(min(len(ref), len(out))) if ref[i] != out[i]]
            print("build: DIFFERS from %s: %d bytes, first at 0x%X" % (a.ref, len(d), d[0] if d else -1))
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
