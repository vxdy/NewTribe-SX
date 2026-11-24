# Newtribe-SX DSP Toolchain & Tape Delay PoC (`dsp-src/`)

Lossless disassembler/assembler toolchain for the **NEC uPD77213** DSP firmware (`ESX0102D.BDS`) of the Korg Electribe SX-1 / SX-1 SD, including a **Vintage Tape Delay** proof of concept in the **RingMod** FX slot.

## Directory Layout

- `tools/dspasm.py` — 100% lossless uPD77213 disassembler & 2-pass assembler (`5,562/5,562` exact matches against `ESX0102D.BDS`)
- `tools/bdspack.py` — Extracts `ESX0102D.BDS` into `src/*.dsp` and packs patched `.BDS` containers (Copy 0 + Copy 1, automatic 32-bit BE word-sum fixups at `0x6FFFC` & `0xEFFFC` to `0x00000000`)
- `src/` — Complete decompilation of the DSP engine (`engine.dsp`) and all 18 FX subroutines (`fx_*.dsp`)
- `patches/tape_delay.dsp` — **Vintage Tape Delay** PoC in the RingMod slot (`0x1446` → IRAM cave `0x0A94`, 187 words, real-silicon pipeline compliant)
- `test_tape_delay.py` — End-to-end audio verification in the native `emu-sx` uPD77213 emulator (with stereo WAV export)
- `build/ESX0102D.BDS` — Built flashable DSP firmware with Tape Delay in the RingMod slot

## Quick Start (Build & Test)

```powershell
# 1. Self-test the uPD77213 disassembler/assembler roundtrip (5,562/5,562 exact)
python dsp-src/tools/dspasm.py --selftest factory-firmware-sd/ESX0102D.BDS

# 2. Build the Tape Delay DSP firmware
python dsp-src/tools/bdspack.py build `
  --base factory-firmware-sd/ESX0102D.BDS `
  --patch dsp-src/patches/tape_delay.dsp `
  --out dsp-src/build/ESX0102D.BDS

# 3. Run end-to-end audio verification in the emulator (also exports build/demo_*.wav)
python dsp-src/test_tape_delay.py
```

## Flashing on a Real ESX-1 SD (`DSPVerUp`)

> **Note:** `ESX0102D.BDS` is identical across both SmartMedia and SD models and is stored separately from `ESX0103N.BSS` in the NAND DSP region (`0x200000..0x2EFFFF`). The NOR bootloader (`BFS`) and main OS (`BSS`) are never modified.

1. Copy `release/esx1-sd/ESX0102D.BDS` (or `dsp-src/build/ESX0102D.BDS`) to the root of a FAT16/FAT32 SD card (keep only one `*.BDS` file in the root).
2. Hold **`PATTERN + GLOBAL`** while powering on (`BFS 01.03.01` Case 5 → **`DSPVerUp`**).
3. Wait for `Complete` / `Turn OFF / Please`, then reboot.
4. Turn the FX selector to **RingMod** (or **`TapeDly`** with Newtribe `ESX0103N.BSS`) → `EDIT 1` = delay time (`5.8..563 ms` with analog pitch glide), `EDIT 2` = feedback (`0..87.5%`) & wet mix.
5. **Revert to Factory:** Copy `factory-firmware-sd/ESX0102D.BDS` to the SD card root and power on holding **`PATTERN + GLOBAL`** (no version lock).

Detailed technical documentation: [`../docs/DSP_DECOMPILE_AND_TAPE_DELAY.md`](../docs/DSP_DECOMPILE_AND_TAPE_DELAY.md).
