#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Electribe SX (ESX-1) emulator, early stage.

    python esxemu.py check ESX0101F.BFS ESX0102N.BSS ESX0102D.BDS     # container checks
    python esxemu.py boot  ESX0101F.BFS [--ph4 0|1] [--steps 8000000]  # run the boot flash, show the display
"""
import argparse
import sys
from pathlib import Path

import container


def cmd_check(a):
    bad = 0
    for f in a.files:
        r = container.check(Path(f).read_bytes(), f)
        print(f"{'OK  ' if r.ok else 'FAIL'} {Path(f).name}: {r.kind} {r.version}")
        for p in r.problems:
            print("     -", p)
        bad += not r.ok
    return 1 if bad else 0


def cmd_boot(a):
    from machine import Machine
    img = container.payload(Path(a.bfs).read_bytes())
    m = Machine(img)
    ph4 = a.ph4
    m.ports.inputs[0x0400012E] = lambda: (m.ports.v.get(0x0400012E, 0) & ~0x10) | (0x10 if ph4 else 0)
    done = 0
    while done < a.steps and not m.cpu.sleeping:
        done += m.cpu.run(min(500_000, a.steps - done))
    print(f"{done} Instruktionen, pc=0x{m.cpu.pc:08x}")
    print("LCD:")
    for line in m.lcd.text():
        print("  |" + line + "|")
    if m.cpu.illegal_log:
        print("ungültige Opcodes:", [(hex(p), hex(o)) for p, o in m.cpu.illegal_log[:5]])
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("files", nargs="+"); c.set_defaults(fn=cmd_check)
    b = sub.add_parser("boot"); b.add_argument("bfs"); b.add_argument("--ph4", type=int, default=0)
    b.add_argument("--steps", type=int, default=8_000_000); b.set_defaults(fn=cmd_boot)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
