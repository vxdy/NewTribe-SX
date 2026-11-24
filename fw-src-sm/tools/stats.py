#!/usr/bin/env python3
"""stats.py - statistics and consistency checks of layout.txt against the dynamic coverage (cov/*.cov)."""
import glob
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shdis
import fwmap
from fwmap import BASE, IMG_END

root = os.path.normpath(os.path.join(HERE, ".."))
items, funcs, ext = shdis.parse_layout(os.path.join(root, "layout.txt"))
cov = bytearray(fwmap.PAYLOAD_SIZE)
for c in glob.glob(os.path.join(root, "cov", "*.cov")):
    d = open(c, "rb").read()
    for i in range(min(len(d), len(cov))):
        cov[i] |= d[i]
kind = {}
owner = [None] * IMG_END
for it in items:
    for o in range(it.a - BASE, it.b - BASE):
        owner[o] = it
tot = defaultdict(int)
for it in items:
    tot[it.kind] += it.b - it.a
print("image bytes 0x%X (%d)" % (IMG_END, IMG_END))
for k, v in sorted(tot.items(), key=lambda x: -x[1]):
    print("  %-6s %8d  %5.1f%%" % (k, v, 100.0 * v / IMG_END))
code = tot["code"]
data = IMG_END - code
print("code %d bytes (%d instructions), data/pool/pad %d bytes, functions %d, items(runs) %d" % (code, code // 2, data, len(funcs), len(items)))
xe = sum(1 for i in range(IMG_END) if cov[i] & 1)
print("dynamically executed instruction starts: %d (%.1f%% of all instructions)" % (xe, 100.0 * xe / (code // 2)))
bad = 0
for i in range(IMG_END):
    if cov[i] & 1 and (owner[i].kind != "code" or (i + BASE - owner[i].a) % 2):
        bad += 1
print("executed bytes outside code items: %d" % bad)
rd = [i for i in range(IMG_END) if cov[i] & 0x1C and owner[i].kind == "code"]
print("data-read bytes inside code items: %d (should be only reads of in-code constants: %s)" % (len(rd), [hex(BASE + x) for x in rd[:6]]))
lab = sum(1 for k in ("code",))
