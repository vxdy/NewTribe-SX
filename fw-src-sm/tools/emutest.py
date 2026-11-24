#!/usr/bin/env python3
"""emutest.py - end-to-end check of a BSS file in the emulator: card update (BFS updater) -> normal boot -> compare.

    python tools/emutest.py build/ESX0102N.BSS [--fast]

1. builds a SmartMedia card image holding the factory BFS + DSP file and the BSS under test (emu-sx/smartmedia.py)
2. boots the factory boot flash in update mode (cursor up+down), presses START at 'SysVerUp / Sure?' and waits for 'Turn OFF'
3. boots the freshly written internal NAND normally until the main display, then compares SDRAM 0x0C080000.. with the
   BSS payload (up to the first RAM variable at payload offset 0x608E8) and presses PLAY for a few seconds.
Uses the private emulator core (emu-sx/target_fw, see tools/cov_core).  Prints PASS/FAIL.
"""
import ctypes as C
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EMU = ROOT / "emu-sx"
sys.path.insert(0, str(EMU))
import rmachine  # noqa: E402

rmachine._LIBS.insert(0, EMU / "target_fw/release/sh3core.dll")
from rmachine import RMachine  # noqa: E402
import smartmedia  # noqa: E402

FW = ROOT / "factory-firmware-sm"


def payload_of(path):
    return Path(path).read_bytes()[0x20:]


def sdram(m):
    return C.string_at(rmachine._lib.emu_sdram_ptr(m.h), m._sdram_len)


def main():
    bss = Path(sys.argv[1])
    t0 = time.time()
    files = [("ESX0101F.BFS", (FW / "ESX0101F.BFS").read_bytes()), ("ESX0102N.BSS", bss.read_bytes()),
             ("ESX0102D.BDS", (FW / "ESX0102D.BDS").read_bytes())]
    card = smartmedia.build_card(files)
    flash = (FW / "ESX0101F.BFS").read_bytes()[0x20:]
    m = RMachine(flash, card_present=True)
    m.set_nand(0, card, 0xEC, 0x73)
    m.set_nand(1, smartmedia.formatted_blank(32), 0x98, 0x75)
    m.keys.pressed = {(8, 0x10), (8, 0x80)}
    m.fast_delays = True
    d, stage, last = 0, 0, None
    while d < 8_000_000_000:
        d += m.run(500_000)
        tx = tuple(x.strip().replace("\x08", "") for x in m.lcd.text())
        if tx != last:
            print("  update: %s" % (tx,), flush=True)
            last = tx
        if tx == ("SysVerUp", "Sure?") and stage == 0:
            m.keys.pressed = {(9, 4)}
            stage = 1
        if tx[0].startswith("Turn OFF"):
            break
    ok_update = last is not None and last[0].startswith("Turn OFF")
    print("update finished: %s after %d instr (%.0fs)" % (ok_update, d, time.time() - t0))
    if not ok_update:
        print("FAIL: update did not complete")
        return 1
    new_flash = bytes(m.flash_bytes(0x80000))
    nand1 = m.nand_data(1)
    # normal boot
    m2 = RMachine(new_flash)
    m2.set_nand(1, nand1, 0x98, 0x75)
    m2.fast_delays = True
    m2.tmu.scale = 1
    d, last, ok = 0, None, False
    while d < 700_000_000:
        d += m2.run(1_000_000)
        tx = tuple(x.rstrip().replace("\x08", "").replace("\x09", "") for x in m2.lcd.text())
        if tx != last and d > 150_000_000:
            last = tx
        if tx[0].startswith("House1") or (tx[0] and "A.01" in tx[1]):
            ok = True
            break
    print("main display reached: %s %s after %d instr" % (ok, last, d))
    if not ok:
        print("FAIL: system did not boot")
        return 1
    m2.run(30_000_000)
    s = sdram(m2)
    pay = payload_of(bss)
    n = 0x608E8
    same = s[0x80000:0x80000 + n] == pay[:n]
    print("SDRAM image == payload[0:0x%X]: %s" % (n, same))
    m2.keys.pressed = {(9, 4)}      # PLAY
    m2.run(4_000_000)
    m2.keys.pressed = set()
    m2.run(150_000_000)
    aud = m2.dsp.audio(1 << 18)
    nz = sum(1 for x in aud if x)
    print("PLAY pressed: LCD %s, audio samples %d (non-zero %d)" % (tuple(x.rstrip() for x in m2.lcd.text()), len(aud), nz))
    print("PASS" if same and nz > 1000 else "FAIL")
    sys.stdout.flush()
    return 0 if same else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    import os
    os._exit(rc)
