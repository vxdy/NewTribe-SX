#!/usr/bin/env python3
"""emutest_sd.py - End-to-end emulator test for ESX-1 SD (OS 01.03.01) + Newtribe overlay.

Runs the REAL dumped ESX-1 SD NOR Boot Flash (BFS 01.03.01) + the built ESX0103N.BSS + real DSP (BDS 01.02.00)
on the emu-sx Rust core (sh3core.dll), using lightweight in-SDRAM stubs for the large-page Hynix NAND HAL
(0x0C007488 nand_is_present, 0x0C007534 nand_read_pages, 0x0C007678 nand_write_pages) backed by a 4 MiB
logical NAND image at 0x0D800000.

Verifies:
  1. Real BFS 01.03.01 boot -> loads BSS to 0x0C080000 -> jumps to 0x0C081000
  2. Newtribe Splash screen: bold 8-char "Newtribe" + 6-char progress bar ("..  0%".."##100%") + dark icon cells 14..15
  3. Boot to main pattern screen with 0 illegal instructions + SDRAM == payload verification
  4. GLOBAL menu walk: page 8 "Newtrb I" / "0.0.1", page 9 "ShiftMut" / "Off" -> encoder -> "On"
  5. Persistence via GLOBAL -> WRITE (GloblWr? -> Yes) -> NAND write -> COLD REBOOT -> ShiftMut still "On"
  6. ShiftMut live hook AFTER cold reboot: SHIFT + muted part keeps mute bit=1, plain part clears mute bit=0

Usage:
  python fw-src-sd/emutest_sd.py fw-src-sd/build/ESX0103N.BSS [--vanilla]
"""
import argparse
import ctypes as C
import json
import os
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EMU = ROOT / "emu-sx"
FW_SD = ROOT / "factory-firmware-sd"

sys.path.insert(0, str(EMU))
import rmachine  # noqa: E402

rmachine._LIBS.insert(0, EMU / "target_fw/release/sh3core.dll")
from rmachine import RMachine  # noqa: E402

NAND_BUF_ADDR = 0x0F000000  # Above the ESX-1's 32 MiB SDRAM (requires sdram_mb=64) so sample RAM never touches it!
NAND_BUF_SIZE = 0x00400000  # 4 MiB (0..2M BSS, 2M..3M BDS+SET3_2, 3M..4M FF)

BFS_PRE_NAND_PC    = 0xA000215A
BFS_NAND_PRESENT   = 0x0C007488
BFS_NAND_READ_PGS  = 0x0C007534
BFS_NAND_WRITE_PGS = 0x0C007678
BFS_DELAY_FN       = 0x0C00C720
BFS_KEY_TABLE      = 0x0C00CE00

NT_CFG_BASE        = 0x0C2D0058
MUTE_MASK_ADDR     = 0x0C17BB6A


def assemble_nand_read_stub():
    """SH-3 stub for BFS 0x0C007534: nand_read_pages(r4=page, r5=count, r6=dst, r7=chip) -> 0."""
    words = [
        0x4418, 0x4408, 0x4400,         # r4 = page * 2048
        0x635D, 0x4318, 0x4308, 0x4300, # r3 = count * 2048
        0x2338, 0x890F,                 # if r3 == 0 -> done (0x30)
        0xD109, 0xD209,                 # r1 = NAND_BUF_ADDR (@0x38), r2 = NAND_BUF_SIZE (@0x3C)
        0x3422, 0x8903,                 # loop @0x16: cmp/hs r2,r4 ; bt fill_ff (0x22)
        0x6043, 0x001C, 0xA001, 0x0009, # mov r4,r0 ; mov.b @(r0,r1),r0 ; bra store ; nop
        0xE0FF,                         # fill_ff @0x22: mov #-1,r0
        0x2600, 0x7601, 0x7401, 0x4310, 0x8BF3, # store @0x24: @r6=r0; r6++; r4++; dt r3; bf loop
        0x0009,
        0x000B, 0xE000,                 # done @0x30: rts ; mov #0,r0
        0x0009, 0x0009,
    ]
    code = b"".join(struct.pack(">H", w) for w in words)
    assert len(code) == 0x38
    return code + struct.pack(">II", NAND_BUF_ADDR, NAND_BUF_SIZE)


def assemble_nand_write_stub():
    """SH-3 stub for BFS 0x0C007678: nand_write_pages(r4=page, r5=count, r6=src, r7=chip) -> 0."""
    words = [
        0x4418, 0x4408, 0x4400,         # 0x00: r4 = page * 2048
        0x635D, 0x4318, 0x4308, 0x4300, # 0x06: r3 = count * 2048
        0x2338, 0x890D,                 # 0x0E: tst r3,r3 ; bt done (0x2C: (0x2C-0x12)/2=13=0x0D)
        0xD108, 0xD208,                 # 0x12: r1 = @0x34, r2 = @0x38 ((0x12+4)&~3=0x14, +32=0x34; 0x18+32=0x38)
        0x3422, 0x8904,                 # 0x16: loop: cmp/hs r2,r4 ; bt skip (0x22: (0x22-0x1A)/2=4)
        0x6043,                         # 0x1A: mov r4,r0
        0x6760,                         # 0x1C: mov.b @r6,r7
        0x0174,                         # 0x1E: mov.b r7,@(r0,r1)
        0x0009,                         # 0x20: nop
        0x7601, 0x7401, 0x4310, 0x8BF5, # 0x22: skip: add #1,r6; add #1,r4; dt r3; bf loop (0x16: (0x16-0x2C)/2=-11=0xF5)
        0x0009,                         # 0x2A: nop
        0x000B, 0xE000,                 # 0x2C: done: rts ; mov #0,r0
        0x0009, 0x0009,                 # 0x30: pad
    ]
    code = b"".join(struct.pack(">H", w) for w in words)
    assert len(code) == 0x34
    return code + struct.pack(">II", NAND_BUF_ADDR, NAND_BUF_SIZE)


def load_sdram_bytes(m, addr, data):
    off = (addr & 0x1FFFFFFF) - 0x0C000000
    C.memmove(rmachine._lib.emu_sdram_ptr(m.h) + off, data, len(data))


def sdram_slice(m, addr, n):
    off = (addr & 0x1FFFFFFF) - 0x0C000000
    return C.string_at(rmachine._lib.emu_sdram_ptr(m.h) + off, n)


def lcd_lines(m):
    return tuple(x[:8].rstrip(" ") for x in m.lcd.text())


def lcd_raw8(m):
    return tuple(x[:8] for x in m.lcd.text())


def press_key(m, key_tuple, hold_instr=6_000_000, wait_instr=8_000_000):
    m.keys.pressed = {key_tuple}
    m.run(hold_instr)
    m.keys.pressed = set()
    m.run(wait_instr)


def boot_sd(bfs_raw, nand_img, sample_splash=True):
    m = RMachine(bfs_raw, sdram_mb=64, card_present=False)
    m.DELAY_FN = BFS_DELAY_FN
    m.keys.table = BFS_KEY_TABLE
    m.fast_delays = True
    m.tmu.scale = 1

    m.cpu.run(2_000_000, stop_pc=BFS_PRE_NAND_PC)
    assert m.cpu.pc == BFS_PRE_NAND_PC, f"BFS stopped at 0x{m.cpu.pc:08X}"

    load_sdram_bytes(m, NAND_BUF_ADDR, bytes(nand_img))
    load_sdram_bytes(m, BFS_NAND_PRESENT, struct.pack(">HH", 0x000B, 0xE001))
    load_sdram_bytes(m, BFS_NAND_READ_PGS, assemble_nand_read_stub())
    load_sdram_bytes(m, BFS_NAND_WRITE_PGS, assemble_nand_write_stub())

    d = 0
    last_tx = None
    splash_frames = []
    booted = False
    while d < 700_000_000:
        d += m.run(1_000_000)
        tx = lcd_raw8(m)
        if tx != last_tx:
            last_tx = tx
            if sample_splash and len(splash_frames) < 60:
                splash_frames.append((d, tx, bytes(m.lcd.cgram[:8]).hex()))
        l0, l1 = tx[0].rstrip(" "), tx[1].rstrip(" ")
        if l0 and ("A.01" in l1 or l0.startswith("House1") or (len(l1) >= 4 and l1[0] in "ABCD" and l1[1] == ".")):
            booted = True
            break
    if booted:
        m.run(20_000_000)
    return m, booted, d, splash_frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bss", help="Path to ESX0103N.BSS to test")
    ap.add_argument("--vanilla", action="store_true", help="Vanilla stock 01.03.01 (skip Newtribe-specific checks)")
    a = ap.parse_args()

    bss_path = Path(a.bss)
    bss_data = bss_path.read_bytes()
    assert len(bss_data) == 0x200000
    ws = sum(struct.unpack(f">{len(bss_data)//4}I", bss_data)) & 0xFFFFFFFF
    assert ws == 0, f"Bad BSS word sum 0x{ws:08X}"
    assert bss_data[:4] == b"KORG" and bss_data[7] == 0xF1 and bss_data[8:12] == b"BSS "
    print(f"[1/6] Container OK: {bss_path.name}, ProductID=0x{bss_data[7]:02X}, ver={bss_data[12:20].decode()!r}, sum=0x00000000")

    bfs_raw = (FW_SD / "raw" / "esx1sd_bfs_512k.bin").read_bytes()
    bds_1m  = (FW_SD / "raw" / "esx1sd_bds_1m_raw.bin").read_bytes()
    km = json.loads((EMU / "keymap.json").read_text())
    def K(name):
        r, mask = km[name].split(",")
        return (int(r), int(mask))

    nand_img = bytearray(b"\xFF" * NAND_BUF_SIZE)
    nand_img[0:0x200000] = bss_data[0x20:] + bss_data[:0x20]
    nand_img[0x200000:0x300000] = bds_1m

    t0 = time.time()
    m, booted, d, splash_frames = boot_sd(bfs_raw, nand_img)
    print(f"[2/6] Boot #1: booted={booted}, LCD={lcd_lines(m)}, instr={d:,}, illegal={m.cpu.illegal_log}, {time.time()-t0:.1f}s")
    if not booted or m.cpu.illegal_log:
        print("FAIL: Boot #1 failed")
        return 1

    pay = bss_data[0x20:]
    check_len = 0x61884
    same = (sdram_slice(m, 0x0C080000, check_len) == pay[:check_len])
    print(f"[3/6] SDRAM[0x0C080000..+0x{check_len:X}] == payload: {same}")
    if not same:
        print("FAIL: SDRAM mismatch")
        return 1

    if not a.vanilla:
        # Verify 6-char line 2 progress bar + blank icon cells 14..15!
        pct_frames = [(fi, ftx[0], ftx[1], cg) for fi, ftx, cg in splash_frames if "%" in ftx[1]]
        saw_glyph = any(cg.startswith("191d1d1f") for _, _, _, cg in pct_frames)
        saw_line1 = all(l0 == "\x08\x09\x0a\x0b\x0c\x0d\x0e\x09" for _, l0, _, _ in pct_frames)
        # Cells 14..15 (ftx[1][6:8]) MUST be "  " (blank) so custom icons stay off, and '%' MUST be at index 5 (pos 13)!
        all_6char = all(l1[5] == "%" and l1[6:8] == "  " for _, _, l1, _ in pct_frames)
        print(f"[4/6] Splash (6-char line 2): frames={len(pct_frames)}, bold={saw_glyph}, line1_ok={saw_line1}, 6char_icons_blank={all_6char}")
        for fi, l0, l1, _ in pct_frames[:4] + pct_frames[-3:]:
            print(f"       @{fi:>11,d}: line2={l1!r} (visible6={l1[:6]!r}, icons={l1[6:8]!r})")
        if not (pct_frames and saw_glyph and saw_line1 and all_6char):
            print("FAIL: Splash 6-char format check failed!")
            return 1

        # GLOBAL walk -> page 8 "Newtrb I"/"0.0.1", page 9 "ShiftMut"/"Off"
        press_key(m, K("global"), 8_000_000, 8_000_000)
        pages = [lcd_lines(m)]
        for _ in range(10):
            press_key(m, K("down"), 8_000_000, 8_000_000)
            cur = lcd_lines(m)
            if cur == pages[-1]:
                break
            pages.append(cur)
        print(f"[5/6] GLOBAL pages ({len(pages)}): {pages[-2:]}")
        if not (pages[-2][0].startswith("Newtrb I") and "0.0.1" in pages[-2][1] and
                pages[-1][0].startswith("ShiftMut") and "Off" in pages[-1][1]):
            print(f"FAIL: Unexpected GLOBAL pages: {pages}")
            return 1

        # Toggle ShiftMut -> On, check NT_CFG_BASE, then GLOBAL WRITE -> Yes!
        m.turn(1)
        m.run(5_000_000)
        sm_on = lcd_lines(m)
        cfg_ram = sdram_slice(m, NT_CFG_BASE, 8)
        print(f"      After encoder +1: LCD={sm_on}, SDRAM[0x0C2D0058..5F]={cfg_ram.hex()}")
        if not ("On" in sm_on[1] and cfg_ram == b"NT\x01\x01\x00\x00\x00\x00"):
            print("FAIL: NT_CFG_BASE not updated properly!")
            return 1

        # Press WRITE on ShiftMut page -> should prompt GloblWr? -> press WRITE again to save to NAND!
        press_key(m, K("write"), 8_000_000, 8_000_000)
        wr_prompt = lcd_lines(m)
        press_key(m, K("write"), 8_000_000, 20_000_000)
        wr_after = lcd_lines(m)
        saved_nand = sdram_slice(m, NAND_BUF_ADDR, NAND_BUF_SIZE)
        cfg_nand = saved_nand[0x2FC058:0x2FC060]
        print(f"      GLOBAL WRITE: prompt={wr_prompt}, after={wr_after}, NAND[0x2FC058..5F]={cfg_nand.hex()}")
        if cfg_nand != b"NT\x01\x01\x00\x00\x00\x00":
            print("FAIL: GLOBAL WRITE did not persist NT_CFG_BASE to NAND!")
            return 1
        m.close()

        # COLD REBOOT with saved NAND!
        t1 = time.time()
        m2, booted2, d2, _ = boot_sd(bfs_raw, saved_nand, sample_splash=False)
        cfg_reboot = sdram_slice(m2, NT_CFG_BASE, 8)
        print(f"[6/6] COLD REBOOT: booted={booted2}, instr={d2:,}, SDRAM[0x0C2D0058..5F]={cfg_reboot.hex()}, illegal={m2.cpu.illegal_log}, {time.time()-t1:.1f}s")
        if not booted2 or m2.cpu.illegal_log or cfg_reboot != b"NT\x01\x01\x00\x00\x00\x00":
            print("FAIL: Cold reboot did not restore persistent Newtribe settings!")
            return 1

        # Verify GLOBAL -> ShiftMut shows "On" right after cold reboot!
        press_key(m2, K("global"), 8_000_000, 8_000_000)
        for _ in range(8):
            press_key(m2, K("down"), 8_000_000, 8_000_000)
        sm_reboot = lcd_lines(m2)
        print(f"      After reboot GLOBAL page 9: {sm_reboot}")
        if not (sm_reboot[0].startswith("ShiftMut") and "On" in sm_reboot[1]):
            print("FAIL: ShiftMut did not show On after cold reboot!")
            return 1

        # Verify ShiftMut hook works immediately after cold reboot WITHOUT toggling!
        press_key(m2, K("pattern"), 6_000_000, 8_000_000)
        press_key(m2, K("d1"), 6_000_000, 8_000_000)
        press_key(m2, K("d2"), 6_000_000, 8_000_000)
        mask_before = m2.bus.read16(MUTE_MASK_ADDR)
        for pname in ("d3", "d4", "d5"):
            m2.keys.pressed = {K("shift")}
            m2.run(4_000_000)
            m2.keys.pressed = {K("shift"), K(pname)}
            m2.run(6_000_000)
            m2.keys.pressed = set()
            m2.run(8_000_000)
        mask_after_shift = m2.bus.read16(MUTE_MASK_ADDR)
        press_key(m2, K("d3"), 6_000_000, 8_000_000)
        mask_after_plain = m2.bus.read16(MUTE_MASK_ADDR)
        print(f"      ShiftMut post-reboot: before=0x{mask_before:04X}, SHIFT+d3/d4/d5=0x{mask_after_shift:04X}, plain d3=0x{mask_after_plain:04X} (bit2={(mask_after_plain>>2)&1})")
        if not (mask_after_shift == mask_before and ((mask_after_plain >> 2) & 1) == 0 and not m2.cpu.illegal_log):
            print("FAIL: ShiftMut hook mismatch after cold reboot!")
            return 1
        m2.close()
    else:
        m.close()

    print("PASS")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
