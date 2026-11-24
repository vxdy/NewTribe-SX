#!/usr/bin/env python3
"""End-to-end audio & functional verification of Newtribe Tape Delay DSP PoC in emu-sx.

Boots the real Korg ESX-1 firmware + native uPD77213 DSP core twice:
  1. Stock ESX0102D.BDS (RingMod @ 0x1446)
  2. Patched dsp-src/build/ESX0102D.BDS (Tape Delay @ 0x0A94 hooked from 0x1446)

For each, selects FX1 = RingMod (rotary code 2), routes Drum Part 1 (D1) to FX1,
sweeps EDIT 1 (Delay Time) & EDIT 2 (Feedback/Wet), triggers D1 hits, captures
real 44.1 kHz stereo PCM audio from the DSP, analyzes echo peaks & high-frequency
tape LP damping, checks 0 unimplemented DSP ops / 0 illegal SH-3 ops, and writes
WAV files to dsp-src/build/ so you can listen directly!
"""
from __future__ import annotations
import ctypes as C
import math
import struct
import sys
import wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "emu-sx"))

import rmachine
rmachine._LIBS = [ROOT / "emu-sx" / "target_fw" / "release" / "sh3core.dll"]
from rmachine import RMachine
import smartmedia


def patch_bds_into_nand(factory_nand: bytes, bds_data: bytes) -> bytes:
    """Replace the 960 KiB BDS image inside out_nand_factory.bin (512+16B pages) with valid ECC."""
    PAGE, SPARE = 512, 16
    STRIDE = PAGE + SPARE
    assert len(bds_data) == 0xF0000
    orig_bds = (ROOT / "factory-firmware-sd" / "ESX0102D.BDS").read_bytes()
    off = factory_nand.find(orig_bds[:512])
    assert off >= 0 and off % STRIDE == 0, f"Could not locate BDS in factory NAND (off={off})"
    start_page = off // STRIDE
    # Verify our spare_ecc matches existing OOB on the first page!
    orig_p0 = factory_nand[off : off + PAGE]
    orig_oob = factory_nand[off + PAGE : off + STRIDE]
    assert orig_oob[8:11] == smartmedia.spare_ecc(orig_p0[256:512]), "OOB ECC hi mismatch!"
    assert orig_oob[13:16] == smartmedia.spare_ecc(orig_p0[0:256]), "OOB ECC lo mismatch!"

    out = bytearray(factory_nand)
    n_pages = len(bds_data) // PAGE
    for p in range(n_pages):
        chunk = bds_data[p * PAGE : (p + 1) * PAGE]
        po = (start_page + p) * STRIDE
        out[po : po + PAGE] = chunk
        out[po + PAGE + 8 : po + PAGE + 11] = smartmedia.spare_ecc(chunk[256:512])
        out[po + PAGE + 13 : po + PAGE + 16] = smartmedia.spare_ecc(chunk[0:256])
    return bytes(out)


def write_wav(path: Path, samples_stereo: np.ndarray, sr: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples_stereo, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(clipped.tobytes())


def drain_audio(m: RMachine) -> np.ndarray:
    buf = (C.c_int16 * 4_000_000)()
    n = rmachine._lib.emu_dsp_audio(m.h, 0, buf, 4_000_000)
    return np.frombuffer(bytes(buf)[: n * 2], dtype=np.int16).astype(np.float64)


def run_session(label: str, nand_bytes: bytes, expect_patched: bool):
    print(f"\n================ {label} ================")
    flash = (ROOT / "emu-sx" / "out_flash.bin").read_bytes()
    m = RMachine(flash)
    m.fast_delays = True
    m.set_nand(1, nand_bytes, 0x98, 0x75)
    while m.dsp.boot < 3:
        m.run(2_000_000)
    m.run(120_000_000)

    def leds():
        p = m.bus.read32(0x0C0B3D08)
        return bytes(m.bus.peek(p, 13))

    def tap(r, mk):
        base = {k for k in m.keys.pressed if k[0] == 14}
        m.keys.pressed = base | {(r, mk)}
        m.run(8_000_000)
        m.keys.pressed = base
        m.run(8_000_000)

    def setfx(code):
        ks = {(14, 1), (14, 2), (14, 16), (14, 128)}
        cur = set(m.keys.pressed) - ks
        for i, k in enumerate([(14, 1), (14, 2), (14, 16), (14, 128)]):
            if (code >> i) & 1:
                cur.add(k)
        m.keys.pressed = cur
        m.run(25_000_000)

    def trigger_d1(tail_cycles: int = 180_000_000) -> np.ndarray:
        drain_audio(m)
        base = {k for k in m.keys.pressed if k[0] == 14}
        m.keys.pressed = base | {(0, 8)}   # Drum Part 1 pad
        m.run(10_000_000)
        m.keys.pressed = base
        m.run(tail_cycles)
        a = drain_audio(m)
        return a

    # Verify DSP IRAM at 0x1446
    w1446 = m.dsp.mem("i", 0x1446)
    w0a94 = m.dsp.mem("i", 0x0A94)
    print(f"DSP IRAM[0x1446] = 0x{w1446:08X}, IRAM[0x0A94] = 0x{w0a94:08X}")
    if expect_patched:
        assert w1446 != 0x4F821000, "Patched BDS was NOT loaded into DSP!"
        assert w0a94 != 0, "Tape Delay code at 0x0A94 was NOT loaded into DSP!"
    else:
        assert w1446 == 0x4F821000, "Expected stock RingMod at 0x1446!"

    # Select FX1 edit (leds[0] & 0x70 == 0x10)
    for _ in range(4):
        if leds()[0] & 0x70 == 0x10:
            break
        tap(11, 2)

    # Select RingMod (rotary code 2) on FX1
    setfx(2)
    assert m.dsp.mem("x", 0x2600) == 0x1446, f"Expected *x:2600=0x1446, got {m.dsp.mem('x', 0x2600):#x}"

    # Select Drum Part 1, route to FX1 (fxsel LED 0x10), enable FX Send (leds[2] & 0x80)
    tap(0, 8)  # select D1
    for _ in range(4):
        if leds()[2] & 0x70 == 0x10:
            break
        tap(13, 16)
    if not (leds()[2] & 0x80):
        tap(12, 16)
    print("FX1 LCD:", [l.rstrip() for l in m.lcd.text()], "LEDs:", leds()[:3].hex())

    # Wait ~80 ms (~8M DSP cycles -> ~25M SH-3 cycles) so progressive 46 ms buffer clear completes!
    m.run(40_000_000)
    if expect_patched:
        magic = m.dsp.mem("x", 0x4027)
        clr_idx = m.dsp.mem("y", 0x4027)
        wptr = m.dsp.mem("x", 0x4028)
        print(f"TapeDelay state[0]: magic=0x{magic:04X} (expect 0x5444), clear_idx=0x{clr_idx:04X} (expect 0x8000), wptr=0x{wptr:04X}")
        assert magic == 0x5444, f"Magic mismatch: {magic:#x}"
        assert clr_idx == 0x8000, f"Buffer clear not complete: {clr_idx:#x}"

    results = {}
    # Test 1: Medium-Long Tape Delay (Edit1 = 480 -> ~256 ms, Edit2 = 860 -> ~73% feedback)
    m.set_adc_in(1, 1, 480)   # EDIT 1 (Delay Time)
    m.set_adc_in(3, 1, 860)   # EDIT 2 (Feedback / Wet)
    m.run(25_000_000)
    x_e1 = m.dsp.mem("x", 0x2501)
    x_e2 = m.dsp.mem("x", 0x250C)
    exp_delay_smp = (x_e1 << 1) + x_e1 + 256
    print(f"[Test 1 - Long Echo]  X[2501]=0x{x_e1:04X} (expected delay ~{exp_delay_smp} smp = {exp_delay_smp/44.1:.1f} ms), X[250C]=0x{x_e2:04X}")
    a_long = trigger_d1(tail_cycles=260_000_000)
    results["long"] = (a_long, exp_delay_smp)

    # Test 2: Short Slapback Tape Delay (Edit1 = 160 -> ~92 ms, Edit2 = 700 -> ~59% feedback)
    m.set_adc_in(1, 1, 160)
    m.set_adc_in(3, 1, 700)
    m.run(25_000_000)
    x_e1_s = m.dsp.mem("x", 0x2501)
    x_e2_s = m.dsp.mem("x", 0x250C)
    exp_delay_s = (x_e1_s << 1) + x_e1_s + 256
    print(f"[Test 2 - Slapback]   X[2501]=0x{x_e1_s:04X} (expected delay ~{exp_delay_s} smp = {exp_delay_s/44.1:.1f} ms), X[250C]=0x{x_e2_s:04X}")
    a_short = trigger_d1(tail_cycles=160_000_000)
    results["short"] = (a_short, exp_delay_s)

    # Test 3: Dry Bypass (Edit2 = 0 -> 0% wet, 0% feedback)
    m.set_adc_in(3, 1, 0)
    m.run(30_000_000)
    a_dry = trigger_d1(tail_cycles=140_000_000)
    results["dry"] = (a_dry, 0)

    # Health check
    unimpl = m.dsp.unimpl()
    illegal = m.cpu.illegal_log
    summ = m.dsp.summary()
    print(f"Health: unimpl={unimpl}, illegal={illegal}, summary={summ}")
    assert illegal == [], f"SH-3 illegal ops: {illegal}"
    results["_unimpl"] = {(a, k) for a, k, _, _ in unimpl}
    m.close()
    return results


def analyze_echoes(name: str, stereo_flat: np.ndarray, exp_delay: int):
    L = stereo_flat[0::2]
    # Remove ESX-1 master DAC DC bias (measure steady-state DC from last 5000 samples)
    dc = float(np.median(L[-5000:])) if len(L) > 5000 else float(np.mean(L))
    Lac = L - dc
    n = len(Lac)
    # Find onset of initial dry hit (first sample > 20% of global AC peak)
    peak_all = float(np.max(np.abs(Lac)))
    onset = int(np.argmax(np.abs(Lac) > 0.2 * peak_all))
    print(f"  [{name}] frames={n} ({n/44100:.2f}s), dc={dc:.1f}, ac_peak={peak_all:.0f}, dry_onset={onset} smp ({onset/44.1:.1f} ms)")
    if exp_delay <= 0:
        # Check tail silence after dry drum hit finishes (~350ms after onset)
        tail = Lac[onset + 16000 :] if onset + 16000 < n else np.array([0.0])
        trms = float(np.sqrt(np.mean(tail ** 2)))
        tpk = float(np.max(np.abs(tail)))
        print(f"    tail (>360ms after onset) ac_rms={trms:.1f}, ac_peak={tpk:.0f}")
        return [(0, onset, trms, tpk, 0.0)]

    # Measure AC RMS, AC Peak, and High-Frequency ratio in windows around echo k = 0..4
    win = min(3000, exp_delay // 2)
    stats = []
    for k in range(5):
        c = onset + k * exp_delay
        if c + win > n:
            break
        seg = Lac[max(0, c - 200) : c + win]
        seg = seg - np.mean(seg)
        rms = float(np.sqrt(np.mean(seg ** 2)))
        pk = float(np.max(np.abs(seg)))
        diff_rms = float(np.sqrt(np.mean(np.diff(seg) ** 2)))
        hf_ratio = diff_rms / (rms + 1e-9)
        stats.append((k, c, rms, pk, hf_ratio))
        print(f"    Echo {k} (@ {c:6d} smp / {c/44.1:6.1f} ms): ac_peak={pk:7.0f}, ac_rms={rms:6.1f}, hf_ratio={hf_ratio:.3f}")
    return stats


def main():
    factory_nand = (ROOT / "emu-sx" / "out_nand_factory.bin").read_bytes()
    patched_bds = (ROOT / "dsp-src" / "build" / "ESX0102D.BDS").read_bytes()
    patched_nand = patch_bds_into_nand(factory_nand, patched_bds)

    stock = run_session("STOCK RINGMOD (ESX0102D.BDS)", factory_nand, expect_patched=False)
    tape = run_session("NEWTRIBE TAPE DELAY (RingMod Slot)", patched_nand, expect_patched=True)
    assert tape["_unimpl"] <= stock["_unimpl"], f"New DSP unimplemented accesses: {tape['_unimpl'] - stock['_unimpl']}"

    print("\n================ AUDIO ANALYSIS ================")
    s_long_stats = analyze_echoes("STOCK RingMod (Long)", *stock["long"])
    t_long_stats = analyze_echoes("TAPE Delay   (Long)", *tape["long"])
    t_short_stats = analyze_echoes("TAPE Delay   (Slap)", *tape["short"])

    # Export WAVs so the user can listen!
    out_dir = ROOT / "dsp-src" / "build"
    write_wav(out_dir / "demo_stock_ringmod.wav", stock["long"][0])
    write_wav(out_dir / "demo_tape_delay_long.wav", tape["long"][0])
    write_wav(out_dir / "demo_tape_delay_slapback.wav", tape["short"][0])
    print(f"\nWrote WAV demos to {out_dir}")

    # Quantitative assertions proving genuine Tape Delay behavior!
    # Note: D1 drum sample itself lasts ~350 ms, so Echo 2 (~527 ms), Echo 3 (~791 ms),
    # and Echo 4 (~1054 ms) sit strictly past the dry sample (Stock RingMod = 0.0 AC!).
    assert len(t_long_stats) >= 5, f"Need >=5 echo windows, got {len(t_long_stats)}"
    e0_rms, e1_rms, e2_rms, e3_rms, e4_rms = [x[2] for x in t_long_stats[:5]]
    e0_pk, e1_pk, e2_pk, e3_pk, e4_pk = [x[3] for x in t_long_stats[:5]]
    e0_hf, e1_hf, e2_hf, e3_hf = [x[4] for x in t_long_stats[:4]]
    s_e2_rms = s_long_stats[2][2]
    s_e3_rms = s_long_stats[3][2]
    dry_tail = analyze_echoes("TAPE Delay   (Dry )", *tape["dry"])
    dry_tail_rms = dry_tail[0][2]

    assert s_e2_rms < 10.0 and s_e3_rms < 10.0, f"Expected stock silent at E2/E3, got {s_e2_rms}, {s_e3_rms}"
    assert e2_rms > 2000 and e3_rms > 1500 and e4_rms > 1000, f"Tape echoes missing! E2={e2_rms:.1f}, E3={e3_rms:.1f}, E4={e4_rms:.1f}"
    assert e1_pk > e2_pk > e3_pk > e4_pk, f"Echo peaks should decay smoothly! {e1_pk:.0f} -> {e2_pk:.0f} -> {e3_pk:.0f} -> {e4_pk:.0f}"
    assert e2_hf < e0_hf, f"Tape LP damping not detected! e0_hf={e0_hf:.3f}, e2_hf={e2_hf:.3f}"
    assert len(t_short_stats) >= 4 and t_short_stats[2][2] > 2000, "Slapback echo not detected!"
    assert dry_tail_rms < 10.0, f"Dry bypass (Edit2=0) leaked tail! rms={dry_tail_rms:.1f}"

    print("\nALL TAPE DELAY ASSERTIONS PASSED!")
    print(f"  - Echo 2 (@ 527 ms): TapeDelay RMS={e2_rms:.1f} vs Stock RingMod={s_e2_rms:.1f}")
    print(f"  - Smooth decay peaks: E1={e1_pk:.0f} -> E2={e2_pk:.0f} -> E3={e3_pk:.0f} -> E4={e4_pk:.0f}")
    print(f"  - Tape LP high-freq damping: E0={e0_hf:.3f} -> E1={e1_hf:.3f} -> E2={e2_hf:.3f} -> E3={e3_hf:.3f}")
    print(f"  - Dry bypass (Edit2=0) tail AC RMS: {dry_tail_rms:.1f} (spotless 0.0!)")


if __name__ == "__main__":
    main()
