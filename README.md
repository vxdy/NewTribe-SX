# Newtribe-SX

Open-source custom firmware toolchain, lossless SH-3 & NEC uPD77213 DSP disassembly/assembly SDK, native emulator, custom DSP effects, and Raspberry Pi JTAG recovery tools for the **Korg Electribe SX-1 (SmartMedia `01.02.00`)** and **Korg Electribe SX-1 SD (`01.03.01`)**.

> **Disclaimer:** This is an unofficial community project and is not affiliated with or endorsed by KORG Inc. (`KORG` and `Electribe` are registered trademarks of KORG Inc.). Use at your own risk.

---

## Features

- **Newtribe OS (`fw-src-sd/` for ESX-1 SD `01.03.01`, `fw-src-sm/` for ESX-1 SmartMedia `01.02.00`):**
  - Lossless SH-3 disassembler, assembler, and `.BSS` container packer (`100%` byte-identical vanilla roundtrip)
  - Custom boot splash (`Newtribe` bold logo + smooth 6-character `0..100%` progress bar tailored to the physical ESX-1 LCD)
  - Extended `GLOBAL` menu pages: Page 8 `Newtrb I` (version) and Page 9 `ShiftMut` (`SHIFT + Part` selects a part without toggling its mute state)
  - **Persistent custom settings** stored via standard `GLOBAL -> WRITE` (survives cold reboots)
  - LCD FX label rename (`RingMod` → `TapeDly`, `OSCFreq.` → `TapeTime`)
- **NEC uPD77213 DSP Toolchain & Custom FX (`dsp-src/`):**
  - Lossless uPD77213 disassembler, 2-pass assembler, and `.BDS` packer (`5,562/5,562` exact instructions)
  - Complete decompilation of the DSP engine and all 18 FX subroutines (`dsp-src/src/`), `1,388` free IRAM instruction words (`0x0A94..0x0FFF`), and `40,960` words of exclusive external delay SRAM per FX slot
  - **Proof of Concept:** **Vintage Tape Delay** replacing the Ring Mod FX slot (`EDIT 1` = delay time `5.8..563 ms` with capstan pitch glide, `EDIT 2` = feedback `0..87.5%` & wet mix, 1-pole tape low-pass filter, 13.7 Hz DC blocker, soft cubic tape saturation, and wow/flutter LFO — verified for real uPD77213 silicon pipeline compliance)
- **Native Emulator (`emu-sx/`):**
  - Hitachi SH7709 (SH-3) + NEC uPD77213 DSP core written in Rust (`core/`) with Python frontend, HD44780 LCD emulation, key matrix, ADC pots, and live 44.1 kHz stereo audio output
- **Raspberry Pi JTAG Dump & Debricking Tools (`pi-jtag-sd/`):**
  - Read-only NOR/NAND dumpers and CFI NOR flash recovery tool (`esx_nor_recover.c`) via the 14-pin H-UDI JTAG header (automatically preserves unit-specific `TUBECALIBDATA` at `0x70000`)

---

## Repository Structure

```text
newtribe-sx/
├── build.py                  # Unified build & repository audit CLI
├── LICENSE                   # GNU GPL v2.0 (GPL-2.0-only)
├── README.md                 # Project overview
├── .gitignore                # Excludes build outputs, Cargo targets, and caches
├── docs/                     # Central technical documentation
│   ├── README.md             # Documentation index
│   ├── DSP_DECOMPILE_AND_TAPE_DELAY.md
│   ├── ESX1SD_BOOTLOADER_DIFF.md
│   ├── ESX1SD_DEBRICKING_PI.md
│   └── ESX1SD_JTAG_DUMP.md
├── factory-firmware-sm/      # Factory firmware for ESX-1 SmartMedia (01.02.00)
├── factory-firmware-sd/      # Factory firmware & raw JTAG backups for ESX-1 SD (01.03.01)
├── fw-src-sm/                # SH-3 toolchain, disassembled 01.02 SM source & Newtribe overlay
├── fw-src-sd/                # Disassembled 01.03.01 SD source, Newtribe overlay & emulator test
├── dsp-src/                  # Shared uPD77213 DSP toolchain, FX, Tape Delay PoC & audio test (SM & SD)
├── emu-sx/                   # Shared SH-3 + uPD77213 emulator (Rust core + Python/Web UI, SM & SD)
├── pi-jtag-sd/               # Raspberry Pi H-UDI JTAG dump & NOR recovery tools for ESX-1 SD (C/Python)
├── fw-analysis-sm/           # Early SmartMedia 01.02 analysis helper scripts (Global pages / NAND)
└── release/                  # [local, .gitignored] Built flashable images (`python build.py all`)
```

---

## Quick Start

1. **Build flashable images (`release/esx1-sd/ESX0103N.BSS` & `ESX0102D.BDS`):**
   ```powershell
   python build.py all           # Build ESX-1 SD system firmware + DSP Tape Delay PoC
   python build.py sd            # Build ESX-1 SD system firmware (ESX0103N.BSS) only
   python build.py dsp           # Build DSP Tape Delay PoC (ESX0102D.BDS) only
   python build.py audit-git     # Verify repository cleanliness and file sizes
   ```
2. **Test in the emulator (recommended before flashing real hardware):**
   ```powershell
   python fw-src-sd/emutest_sd.py release/esx1-sd/ESX0103N.BSS
   python dsp-src/test_tape_delay.py
   ```
3. **Flash on a real ESX-1 SD (Boot Flash `BFS` is never touched):**
   - **System (`ESX0103N.BSS`):** Copy to SD card root → hold **`PATTERN + STEP EDIT`** while powering on (`ND VerUp`).
   - **DSP (`ESX0102D.BDS`):** Copy to SD card root → hold **`PATTERN + GLOBAL`** while powering on (`DSPVerUp`).
   - **Revert to Stock:** Flash the original `ESX0103N.BSS` / `ESX0102D.BDS` from `factory-firmware-sd/` using the same key combinations (no version lock).

---

## Documentation

See [`docs/README.md`](docs/README.md) for the complete technical documentation index (JTAG pinout, bootloader analysis & diff, Pi debricking guide, DSP architecture & Tape Delay PoC).

## License

This project (toolchain, emulator, JTAG tools, custom firmware overlays, and DSP patches) is licensed under the **GNU General Public License v2.0 (`GPL-2.0-only`)** — see [`LICENSE`](LICENSE), matching the `SPDX-License-Identifier: GPL-2.0-only` headers in `emu-sx/`.

*(Third-party factory files under `factory-firmware-sm/` and `factory-firmware-sd/` remain the intellectual property of their respective copyright holders and are not covered by this open-source license.)*
