#!/usr/bin/env python3
"""splashtest.py - emulator proof for the Newtribe start-up screen (newtribe/splash.s).

    python tools/splashtest.py [BSS] [--mode recovery|normal] [--realtime] [--out DIR] [--step N]

1. genuine card update in the emulator (factory BFS/BDS + the BSS under test), as emu-sx/make_custom.py does
2. boots the written flash/NAND from power on to the pattern screen and samples the LCD (DDRAM text, all 64 CGRAM bytes, display on)
   every --step instructions (default 100 000); a frame is recorded whenever anything visible changed
3. the same boot is done with the FACTORY BSS for comparison (hand-over state must be identical: text and CGRAM)
4. checks (printed as PASS/FAIL): glyph rows of N,e,w,t,r,i,b + solid block, line 1 = Newtribe codes, percent 0..100 monotonic and
   100 % shown, hand-over text/CGRAM == factory, no illegal instruction
5. writes DIR/frames_<mode>.txt (frame list), DIR/glyphs.txt (ASCII art of the glyphs) and DIR/frames_<mode>.png (contact sheet
   drawn with the same 5x7 font table / CGRAM logic as emu-sx/app/src/panel.rs)

--mode recovery  = the emulator's normal behaviour (fresh sample memory -> the factory runs its 125 M instruction "Recovery" scan)
--mode normal    = func_0C0C7168 (recovery decision) is patched to return 1 in SDRAM, i.e. the boot of a unit with valid sample memory
--realtime       = do NOT patch the BFS busy-wait delay (fast_delays off): the delays (e.g. the 100 % hold) really take their time
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EMU = ROOT / "emu-sx"
FW = ROOT / "factory-firmware-sm"
sys.path.insert(0, str(EMU))
import container  # noqa: E402
import smartmedia  # noqa: E402
from rmachine import RMachine  # noqa: E402

GLYPHS = {  # expected CGRAM rows of the splash (slot: name, 8 rows)
    0: ("N", [0x19, 0x1D, 0x1D, 0x1F, 0x17, 0x17, 0x13, 0x00]),
    1: ("e", [0x00, 0x00, 0x0E, 0x1B, 0x1F, 0x18, 0x0E, 0x00]),
    2: ("w", [0x00, 0x00, 0x1B, 0x1B, 0x15, 0x1F, 0x0A, 0x00]),
    3: ("t", [0x0C, 0x0C, 0x1F, 0x0C, 0x0C, 0x0C, 0x07, 0x00]),
    4: ("r", [0x00, 0x00, 0x1B, 0x1D, 0x18, 0x18, 0x18, 0x00]),
    5: ("i", [0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x0C, 0x0C, 0x00]),
    6: ("b", [0x18, 0x18, 0x1E, 0x1B, 0x1B, 0x1B, 0x1E, 0x00]),
    7: ("block", [0x1F] * 7 + [0x00]),
}
LINE1 = bytes([8, 9, 10, 11, 12, 13, 14, 9])


def update(bss_path):
    """genuine BFS card update -> (flash, nand)"""
    files = [("ESX0101F.BFS", (FW / "ESX0101F.BFS").read_bytes()), ("ESX0102N.BSS", Path(bss_path).read_bytes()),
             ("ESX0102D.BDS", (FW / "ESX0102D.BDS").read_bytes())]
    card = smartmedia.build_card(files)
    m = RMachine(container.payload(files[0][1]), card_present=True)
    m.set_nand(0, card, 0xEC, 0x73)
    m.set_nand(1, smartmedia.formatted_blank(32), 0x98, 0x75)
    m.keys.pressed = {(8, 0x10), (8, 0x80)}
    m.fast_delays = True
    d, stage, last = 0, 0, None
    while d < 8_000_000_000:
        d += m.run(500_000)
        tx = tuple(x.strip() for x in m.lcd.text())
        if tx == ("SysVerUp", "Sure?") and stage == 0:
            m.keys.pressed = {(9, 4)}
            stage = 1
        if tx[0].startswith("Turn OFF") or tx[0].startswith("CkSum"):
            last = tx
            break
    if not (last and last[0].startswith("Turn OFF")):
        raise SystemExit("card update failed: %s" % (last,))
    return m.flash_bytes(), m.nand_data(1)


def boot(flash, nand, mode, realtime, step, limit=900_000_000):
    card = (EMU / "card_factory.cache").read_bytes()
    m = RMachine(bytes(flash), card_present=True)
    m.fast_delays = not realtime
    m.set_nand(1, nand, 0x98, 0x75)
    m.set_nand(0, card, 0xEC, 0x75)
    m.tmu.scale = 1
    frames, last, d, patched = [], None, 0, False
    while d < limit:
        d += m.run(step)
        if mode == "normal" and not patched and d > 20_000_000:
            for a, w in ((0x0C0C7168, 0xE001), (0x0C0C716A, 0x000B), (0x0C0C716C, 0x0009)):
                m.bus.write16(a, w)       # func_0C0C7168 (recovery decision) -> return 1
            patched = True
        l = m.lcd
        st = (bytes(l.ddram), bytes(l.cgram), l.display_on)
        if st != last:
            last = st
            frames.append(dict(t=d, pc=m.cpu.pc, on=l.display_on, dd=bytes(l.ddram), cg=bytes(l.cgram)))
        t0 = bytes(l.ddram[:8])
        if d > 25_000_000 and t0[0] > 0x20 and t0[0] != 0x52 and t0[0] < 0x7F:     # pattern screen ('--------', 'House1', ...), not 'Recovery'
            m.run(2_000_000)                 # let the screen settle
            l = m.lcd
            frames.append(dict(t=d + 2_000_000, pc=m.cpu.pc, on=l.display_on, dd=bytes(l.ddram), cg=bytes(l.cgram)))
            break
    return frames, m


def pct(frame):
    s = frame["dd"][40:48]
    mt = re.match(rb"[\x0f=. ]{4}\s*(\d+)%", s)
    return int(mt.group(1)) if mt else None


def txt(b):
    return "".join(chr(c) if 32 <= c < 127 else "\\x%02x" % c for c in b)


def font_table():
    src = (EMU / "app/src/panel.rs").read_text(encoding="utf-8", errors="replace")
    h = re.search(r'FONT5X7: &str = "([0-9A-Fa-f]+)"', src).group(1)
    return bytes(int(h[i:i + 2], 16) for i in range(0, len(h), 2))


def lcd_png(frames_sel, font, path, scale=5):
    from PIL import Image, ImageDraw
    bg, ink = (255, 154, 28), (46, 21, 0)

    def rows(f, code):
        if code < 16:
            i = (code & 7) * 8
            return [f["cg"][i + y] & 31 for y in range(8)]
        if 32 < code < 127:
            r = [0] * 8
            for y in range(7):
                for x in range(5):
                    if (font[(code - 32) * 5 + x] >> y) & 1:
                        r[y] |= 1 << (4 - x)
            return r
        return [0] * 8
    cw, ch = 16 * 6 + 1, 2 * 9 + 1
    lab = 12
    img = Image.new("RGB", (cw * scale * 2 + 30, len(frames_sel) // 2 * ((ch + lab) * scale + 10) + 20 if len(frames_sel) > 1 else 200), (30, 30, 34))
    dr = ImageDraw.Draw(img)
    for k, (label, f) in enumerate(frames_sel):
        ox, oy = 10 + (k % 2) * (cw * scale + 10), 10 + (k // 2) * ((ch + lab) * scale + 10)
        dr.text((ox, oy), label, fill=(220, 220, 220))
        oy += lab * scale // 2
        dr.rectangle([ox, oy, ox + cw * scale, oy + ch * scale], fill=bg)
        for row in range(2):
            for col in range(16):
                code = f["dd"][row * 40 + col]
                g = rows(f, code) if f["on"] else [0] * 8
                for yy, bits in enumerate(g):
                    for xx in range(5):
                        if (bits >> (4 - xx)) & 1:
                            x = ox + ((col * 6 + xx + 0.6)) * scale
                            y = oy + (row * 9 + yy + row * 0.6 + 0.5) * scale
                            dr.rectangle([x, y, x + scale * 0.8, y + scale * 0.8], fill=ink)
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bss", nargs="?", default=str(ROOT / "fw-src-sm/build/ESX0102N.BSS"))
    ap.add_argument("--mode", choices=("recovery", "normal"), default="recovery")
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "fw-src-sm/build/splash"))
    ap.add_argument("--step", type=int, default=100_000)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = a.mode + ("_realtime" if a.realtime else "")

    print("update with", a.bss)
    flash, nand = update(a.bss)
    fl_f, na_f = update(FW / "ESX0102N.BSS")
    print("boot (new) ...", flush=True)
    fr, m = boot(flash, nand, a.mode, a.realtime, a.step)
    illegal = m.cpu.illegal_log
    print("boot (factory) ...", flush=True)
    fr0, m0 = boot(fl_f, na_f, a.mode, a.realtime, a.step)

    lines = []
    for f in fr:
        p = pct(f)
        lines.append("%11d pc=%08X %s L1=[%s] L2=[%s] cg=%s" % (f["t"], f["pc"], "on " if f["on"] else "off", txt(f["dd"][:8]), txt(f["dd"][40:48]), f["cg"].hex()))
    (out / ("frames_%s.txt" % tag)).write_text("\n".join(lines) + "\n")
    lines0 = ["%11d pc=%08X L1=[%s] L2=[%s] cg=%s" % (f["t"], f["pc"], txt(f["dd"][:8]), txt(f["dd"][40:48]), f["cg"].hex()) for f in fr0]
    (out / ("frames_factory_%s.txt" % tag)).write_text("\n".join(lines0) + "\n")

    art = []
    for slot, (n, r) in GLYPHS.items():
        art.append("slot %d '%s': " % (slot, n) + " ".join("%02X" % x for x in r))
    for y in range(8):
        art.append(" ".join("".join("#" if (GLYPHS[s][1][y] >> (4 - x)) & 1 else "." for x in range(5)) for s in (0, 1, 2, 3, 4, 5, 6, 1)))
    (out / "glyphs.txt").write_text("\n".join(art) + "\n")

    # ---- checks
    ok = True

    def chk(name, cond, info=""):
        nonlocal ok
        ok &= bool(cond)
        print("%-4s %s %s" % ("PASS" if cond else "FAIL", name, info))

    splash = [f for f in fr if f["dd"][:8] == LINE1]
    chk("line 1 shows Newtribe codes 08 09 0A 0B 0C 0D 0E 09", len(splash) > 0, "(%d frames)" % len(splash))
    if splash:
        f = splash[0]
        glyph_ok = all(list(f["cg"][s * 8:s * 8 + 8]) == r for s, (n, r) in GLYPHS.items())
        chk("CGRAM slots 0..7 = bold N e w t r i b + block", glyph_ok)
        chk("first splash frame earlier than the factory logo", f["t"] < fr0[[i for i, x in enumerate(fr0) if x["dd"][:1] == b"\n"][0]]["t"] if any(x["dd"][:1] == b"\n" for x in fr0) else True,
            "t=%d (factory KORG logo at %s)" % (f["t"], next((x["t"] for x in fr0 if x["dd"][:1] == b"\n"), "-")))
    ps = [pct(f) for f in splash]
    ps = [p for p in ps if p is not None]
    chk("progress starts at 0 %", ps and ps[0] == 0, str(ps[:3]))
    chk("progress reaches 100 %", ps and ps[-1] == 100, str(ps[-3:]))
    chk("progress monotonic", all(x <= y for x, y in zip(ps, ps[1:])), "%d distinct values, %d updates" % (len(set(ps)), len(ps)))
    fin, fin0 = fr[-1], fr0[-1]
    chk("hand-over: LCD text equals the factory pattern screen", fin["dd"] == fin0["dd"], "[%s|%s]" % (txt(fin["dd"][:8]), txt(fin["dd"][40:48])))
    chk("hand-over: all 64 CGRAM bytes equal factory", fin["cg"] == fin0["cg"], fin["cg"][:16].hex())
    chk("no illegal instruction", not illegal, str(illegal))
    tw = [f["t"] for f in splash]
    if tw:
        chk("splash window", True, "from %d to %d instr; factory boot reaches the pattern at %d, new at %d (%+.1f %%)" % (
            tw[0], tw[-1], fr0[-1]["t"], fr[-1]["t"], 100.0 * (fr[-1]["t"] - fr0[-1]["t"]) / fr0[-1]["t"]))

    # contact sheet
    sel, seen = [], set()
    want = [0, 6, 20, 41, 63, 88, 94, 100]
    for f in splash:
        p = pct(f)
        if p in want and p not in seen:
            seen.add(p)
            sel.append(("%d%%  t=%d" % (p, f["t"]), f))
    sel.append(("hand-over  t=%d" % fin["t"], fin))
    if len(sel) % 2:
        sel.append(("factory pattern screen", fin0))
    try:
        lcd_png(sel, font_table(), out / ("frames_%s.png" % tag))
    except Exception as e:  # PIL missing
        print("png skipped:", e)
    print("PASS" if ok else "FAIL", " frames:", len(fr), "->", out)
    sys.stdout.flush()
    import os
    os._exit(0 if ok else 1)


if __name__ == "__main__":
    main()
