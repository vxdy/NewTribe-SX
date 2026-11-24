#!/usr/bin/env python3
"""Dynamic coverage of the main firmware (BSS payload at SDRAM 0x0C080000) in the emulator.

Uses a private build of the emulator core with a coverage bitmap (tools/cov_core, see README) and the Python harness
emu-sx/rmachine.py.  Flags per payload byte (see cov_core/src/lib.rs):
  0x01 instruction start  0x02 instruction 2nd byte  0x04 read8  0x08 read16  0x10 read32  0x20 written
  0x40 jsr/bsr/bsrf target  0x80 jmp target / exception entry
usage: covrun.py SCENARIO [out.cov]       scenarios: boot, keys, play, menus, knobs, all
"""
import ctypes as C
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EMU = ROOT / "emu-sx"
sys.path.insert(0, str(EMU))
import rmachine  # noqa: E402

DLL = EMU / "target_fw/release/sh3core.dll"
rmachine._LIBS.insert(0, DLL)
from rmachine import RMachine  # noqa: E402

PAYLOAD_PHYS = 0x0C080000
PAYLOAD_LEN = 0x1FFFE0
KEYS = json.loads((EMU / "keymap.json").read_text())


def kk(name):
    r, m = KEYS[name].split(",")
    return int(r), int(m)


class Run:
    def __init__(self, nand_name="out_nand_factory.bin"):
        flash = (EMU / "out_flash.bin").read_bytes()
        nand = (EMU / nand_name).read_bytes()
        m = RMachine(flash)
        m.fast_delays = True
        m.set_nand(1, nand, 0x98, 0x75)
        m.tmu.scale = 1
        L = rmachine._lib
        L.emu_cov_enable.argtypes = [C.c_void_p, C.c_uint32, C.c_size_t]
        L.emu_cov_ptr.restype, L.emu_cov_ptr.argtypes = C.c_void_p, [C.c_void_p]
        L.emu_cov_pause.argtypes = [C.c_void_p, C.c_uint32]
        L.emu_cov_enable(m.h, PAYLOAD_PHYS, PAYLOAD_LEN)
        L.emu_cov_pause(m.h, 0)      # off until the boot flash has copied the image and jumped into it
        self.m = m
        self.L = L
        self.lcd_seen = []
        self.instr = 0

    def cov(self):
        return C.string_at(self.L.emu_cov_ptr(self.m.h), PAYLOAD_LEN)

    def run(self, n):
        m = self.m
        left = n
        while left > 0:
            k = min(left, 2_000_000)
            m.run(k)
            left -= k
            self.instr += k
        self.note_lcd()

    def lcd(self):
        return tuple(x.rstrip().replace("\x08", "").replace("\x09", "") for x in self.m.lcd.text())

    def note_lcd(self):
        t = self.lcd()
        if not self.lcd_seen or self.lcd_seen[-1] != t:
            self.lcd_seen.append(t)

    def boot(self):
        self.m.tmu.scale = 1
        L = self.L
        inpay = lambda: PAYLOAD_PHYS <= (self.m.cpu.pc & 0x1FFFFFFF) < PAYLOAD_PHYS + PAYLOAD_LEN
        while True:
            snap = L.emu_snapshot(self.m.h)
            n0 = self.instr
            self.run(20_000)
            if inpay():
                L.emu_restore(self.m.h, snap)
                self.instr = n0
                while not inpay():
                    self.m.cpu.run(1)
                    self.instr += 1
                L.emu_free(snap)
                break
            L.emu_free(snap)
        self.entry_pc = self.m.cpu.pc
        C.memset(self.L.emu_cov_ptr(self.m.h), 0, PAYLOAD_LEN)
        self.L.emu_cov_pause(self.m.h, 1)
        print("first pc in payload: 0x%08X after %d instr" % (self.entry_pc, self.instr), flush=True)
        while self.instr < 600_000_000:
            self.run(1_000_000)
            if self.lcd()[0].startswith("House1") or self.lcd()[0][:3].strip() and "A.01" in self.lcd()[1]:
                break
        self.run(30_000_000)

    def tap(self, name, hold=4_000_000, after=4_000_000):
        self.m.keys.pressed = {kk(name)}
        self.run(hold)
        self.m.keys.pressed = set()
        self.run(after)

    def chord(self, names, hold=4_000_000, after=4_000_000):
        self.m.keys.pressed = {kk(n) for n in names}
        self.run(hold)
        self.m.keys.pressed = set()
        self.run(after)

    def turn(self, n, step=1_500_000):
        self.m.turn(n, step)
        self.run(2_000_000)


def sc_keys(r):
    for name in KEYS:
        r.tap(name)
        r.turn(3)
        r.turn(-3)
        r.tap("stop")
        r.tap("back")
    r.tap("stop")


def sc_menus(r):
    for name in ("global", "option", "write", "partedit", "editsel", "fxselect", "fxchain", "pattern", "song", "sample",
                 "stepedit", "padnote", "motionseq", "arrange", "slice", "dest", "bpmsync", "modtype", "filtertype", "ampeg",
                 "fxsend", "roll", "reverse", "tap", "autobpm", "tempolock", "solo"):
        r.tap(name)
        for _ in range(12):
            r.tap("down", 2_000_000, 2_000_000)
            r.turn(2)
        for _ in range(4):
            r.tap("up", 2_000_000, 2_000_000)
            r.turn(-2)
        for _ in range(3):
            r.tap("right", 2_000_000, 2_000_000)
            r.turn(1)
        for _ in range(3):
            r.tap("left", 2_000_000, 2_000_000)
            r.turn(-1)
        r.tap("back")
        r.tap("stop")


def sc_play(r):
    r.tap("play")
    r.run(120_000_000)
    for i in range(1, 17):
        r.tap("step%d" % i, 1_000_000, 1_000_000)
    r.tap("rec")
    r.run(60_000_000)
    for n in ("d1", "d2", "d3", "k1", "s1", "accent", "slice"):
        r.chord([n], 3_000_000, 6_000_000)
    r.tap("rec")
    r.tap("stop")
    r.tap("stop")
    r.tap("pattern")
    for i in range(1, 8):
        r.tap("step%d" % i)
        r.turn(2)
    r.tap("back")
    r.tap("play")
    r.run(80_000_000)
    r.tap("stop")


def sc_knobs(r):
    import itertools
    L = rmachine._lib
    for col in range(8):
        for ch in range(8):
            for v in (0, 1023, 512, 300, 900):
                try:
                    r.m.set_adc_in(col, ch, v)
                except Exception:
                    pass
                r.run(1_500_000)
            r.m.set_adc_in(col, ch, 512 if (col, ch) != (2, 2) else 1023)
    r.run(5_000_000)


def sc_shift(r):
    for name in KEYS:
        if name in ("shift",):
            continue
        r.chord(["shift", name], 4_000_000, 4_000_000)
        r.tap("back")
        r.tap("stop")
    for name in ("step1", "step5", "d1", "k1", "s1", "up", "down", "left", "right", "play", "rec", "pattern", "write", "global", "partedit"):
        r.chord(["patset", name], 4_000_000, 4_000_000)
        r.tap("back")
    r.chord(["up", "down"], 4_000_000, 4_000_000)


SCEN = {"boot": lambda r: None, "keys": sc_keys, "menus": sc_menus, "play": sc_play, "knobs": sc_knobs, "shift": sc_shift}


def main():
    names = sys.argv[1].split(",")
    outp = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "fw-src/cov" / (sys.argv[1].replace(",", "_") + ".cov"))
    t0 = time.time()
    r = Run()
    r.boot()
    print("booted", r.instr, r.lcd(), round(time.time() - t0, 1), "s", flush=True)
    for nme in names:
        if nme == "all":
            for k in ("keys", "menus", "play", "knobs", "shift"):
                SCEN[k](r)
        else:
            SCEN[nme](r)
        print(nme, "done", r.instr, r.lcd(), round(time.time() - t0, 1), "s", flush=True)
    cov = r.cov()
    Path(outp).write_bytes(cov)
    ex = sum(1 for b in cov if b & 1)
    print("instructions executed (distinct):", ex, "bytes data-read:", sum(1 for b in cov if b & 0x1C), "written:", sum(1 for b in cov if b & 0x20))
    (Path(outp).with_suffix(".lcd.txt")).write_text("\n".join(" | ".join(x) for x in r.lcd_seen))
    sys.stdout.flush(); os._exit(0)


if __name__ == "__main__":
    main()
