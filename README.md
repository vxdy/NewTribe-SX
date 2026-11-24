# Newtribe-SX

Open-source custom firmware toolchain, lossless SH-3 & NEC uPD77213 DSP disassembly/assembly SDK, native emulator, custom DSP effects, and Raspberry Pi JTAG recovery tools for the **Korg Electribe SX-1 SD (`01.03.01`)** and **Korg Electribe SX-1 SmartMedia (`01.02.00`)**.

> **Disclaimer:** This is an unofficial community project and is not affiliated with or endorsed by KORG Inc. (`KORG` and `Electribe` are registered trademarks of KORG Inc.). Flashing custom firmware is done **at your own risk**. Never power off the unit while flashing, and never flash a `.BFS` boot flash file unless you have a verified JTAG recovery setup.

---

## How to Install

> **Safety Note:** The Boot Flash (`BFS` in NOR flash) is **never modified** by Newtribe. Only the main system firmware (`.BSS`) and DSP firmware (`.BDS`) in internal NAND are updated, so you can always revert to stock firmware from [`factory-firmware-sd/`](factory-firmware-sd/) or [`factory-firmware-sm/`](factory-firmware-sm/).

### Korg ESX-1 SD (`01.03.01`)

1. **Build the flashable images** (requires Python 3.10+):
   ```powershell
   python build.py all
   ```
   This generates `release/esx1-sd/` containing:
   - `ESX0103N.BSS` — Newtribe custom system firmware (`01.03.02`)
   - `ESX0102D.BDS` — Custom DSP firmware with Vintage Tape Delay replacing Ring Mod *(optional)*
2. **Prepare an SD card:** Format as `FAT16` / `FAT32` and copy `ESX0103N.BSS` and/or `ESX0102D.BDS` to the **root directory** (keep only one `*.BSS` and one `*.BDS` in root; **do not** place any `*.BFS` file on the card).
3. **Flash System Firmware (`ESX0103N.BSS`):**
   - Insert the SD card and power on while holding **`PATTERN + STEP EDIT`** (`ND VerUp`).
   - Wait until the display confirms completion (`Turn OFF / Please`), then power cycle.
4. **Flash Custom DSP Firmware (`ESX0102D.BDS`, optional):**
   - Power on while holding **`PATTERN + GLOBAL`** (`DSPVerUp`).
   - Wait until completion, then power cycle.
5. **Revert to Stock:** Repeat steps 3–4 using the original files from [`factory-firmware-sd/`](factory-firmware-sd/) (neither updater has a version lock).

*(Why not `UP + DOWN` on ESX-1 SD? Korg's `BFS 01.03.01` contains a pre-scan bug that skips `0xF1` `.BSS` files under `SysVerUp` — see [`docs/ESX1SD_BOOTLOADER_DIFF.md`](docs/ESX1SD_BOOTLOADER_DIFF.md) for details.)*

### Korg ESX-1 SmartMedia (`01.02.00`)

> **Status:** The SmartMedia (`01.02.00`) build and DSP firmware are verified in the emulator; real-hardware testing so far has focused on the ESX-1 SD.

1. **Build the flashable images:**
   ```powershell
   cd fw-src-sm && python tools/build.py     # -> fw-src-sm/build/ESX0102N.BSS
   cd .. && python build.py dsp              # -> dsp-src/build/ESX0102D.BDS (identical for SM & SD)
   ```
2. **Prepare a SmartMedia card:** Copy `ESX0102N.BSS` (and optionally `ESX0102D.BDS`) to the **root directory** of a SmartMedia card (**do not** copy `ESX0101F.BFS`).
3. **Flash via Bootloader Update:**
   - Insert the SmartMedia card and power on while holding **`UP + DOWN`** (`SysVerUp` → `Sure?`).
   - Press **`PLAY/PAUSE`** to start flashing, wait for `Turn OFF / Please`, then power cycle.
4. **Revert to Stock:** Copy the factory `ESX0102N.BSS` / `ESX0102D.BDS` from [`factory-firmware-sm/`](factory-firmware-sm/) and flash using the same procedure (or `PATTERN + STEP EDIT` / `PATTERN + GLOBAL` to force-flash without version checks).

---

## Features

- **Newtribe OS ([`fw-src-sd/`](fw-src-sd/) for ESX-1 SD `01.03.01`, [`fw-src-sm/`](fw-src-sm/) for ESX-1 SM `01.02.00`):**
  - Custom boot splash (`Newtribe` bold CGRAM logo + smooth 6-character `0..100%` progress bar tailored to the physical ESX-1 LCD)
  - Extended `GLOBAL` menu pages:
    - **Page 8 (`Newtrb I`):** Displays installed Newtribe firmware version
    - **Page 9 (`ShiftMut`):** Holding `SHIFT` + pressing a part key selects the part without un-muting or toggling its mute state
  - **Persistent Custom Settings:** Stored in reserved Global NVRAM bytes (`0x0C2D0058..0x0C2D005F`) via standard `GLOBAL -> WRITE` — survives cold reboots
  - **LCD FX Label Rename:** Renames `RingMod` → `TapeDly` and `OSCFreq.` → `TapeTime` to match the custom DSP Tape Delay
- **Custom NEC uPD77213 DSP Effects ([`dsp-src/`](dsp-src/)):**
  - **Proof of Concept — Vintage Tape Delay** (replaces the Ring Mod FX slot; bit-identical DSP base for both SM & SD):
    - `EDIT 1` (`TapeTime`): Delay time `5.8..563 ms` with smooth capstan pitch glide
    - `EDIT 2`: Feedback (`0..87.5%`) & wet mix
    - 1-pole tape low-pass damping filter, 13.7 Hz DC blocker, soft cubic tape saturation, and subtle wow/flutter LFO
    - Verified for real NEC uPD77213 silicon pipeline latency and instruction compliance
- **Lossless Reverse-Engineering SDKs:**
  - 100% byte-identical SH-3 disassembly/reassembly (`fw-src-sm/tools/`) for both `01.02.00` and `01.03.01`
  - 100% instruction-exact NEC uPD77213 DSP disassembly/reassembly (`5,562/5,562` words) with `1,388` free IRAM words (`0x0A94..0x0FFF`) and `40,960` words of exclusive external delay SRAM per FX slot

---

## Emulator

[`emu-sx/`](emu-sx/) provides a native **Hitachi SH7709 (SH-3, Big-Endian) + NEC uPD77213 DSP** emulator written in Rust (`emu-sx/core/`) with Python and browser/desktop frontends so every firmware and DSP change can be tested safely before touching real hardware.

- **Hardware modeled:** SH-3 CPU (~100–160 MIPS), NEC uPD77213 DSP with live 44.1 kHz stereo audio capture, 4-bit HD44780 LCD (DDRAM + CGRAM), front-panel key matrix, 10-bit ADC pots, Gray-code `VALUE` encoder, NOR flash, and SmartMedia/internal NAND with SSFDC ECC.
- **Quick start:**
  ```powershell
  cd emu-sx/core && cargo build --release    # Build sh3core.dll / libsh3core.so
  cd .. && python server.py                  # Launch interactive Web UI on http://127.0.0.1:8765/
  ```
- **Automated firmware & DSP test suites:**
  ```powershell
  python fw-src-sd/emutest_sd.py release/esx1-sd/ESX0103N.BSS   # Boots real BFS 01.03.01 + tests splash, ShiftMut & persistence
  python dsp-src/test_tape_delay.py                             # Boots real DSP engine & verifies Tape Delay audio output
  ```

See [`emu-sx/README.md`](emu-sx/README.md) and [`emu-sx/app/SPEC.md`](emu-sx/app/SPEC.md) for architecture details and the native desktop UI.

---

## Development

### Repository Structure

```text
newtribe-sx/
├── build.py                  # Unified build & repository audit CLI
├── LICENSE                   # GNU GPL v2.0 (GPL-2.0-only)
├── README.md                 # Project overview
├── .gitignore                # Excludes build outputs, Cargo targets, and caches
├── docs/                     # Central technical documentation (SM & SD)
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

### Build & Audit Commands

```powershell
python build.py all           # Build ESX-1 SD system firmware + DSP Tape Delay PoC -> release/esx1-sd/
python build.py sd            # Build ESX-1 SD system firmware (ESX0103N.BSS) only
python build.py dsp           # Build DSP Tape Delay PoC (ESX0102D.BDS) only
python build.py audit-git     # Verify repository cleanliness and GitHub file-size limits
```

### Technical Documentation

- **[Documentation Index](docs/README.md)** — Full map of all technical notes
- **[SH-3 Firmware Toolchain (`fw-src-sm/README.md`)](fw-src-sm/README.md)** — Overlay architecture (`.redirect`, `.patchlong`, `.copylong`), zero-gap layout, and lossless roundtrip
- **[ESX-1 SD Build & Testing (`fw-src-sd/README.md`)](fw-src-sd/README.md)** — SD `01.03.01` port and emulator verification
- **[DSP Decompilation & Tape Delay Guide (`docs/DSP_DECOMPILE_AND_TAPE_DELAY.md`)](docs/DSP_DECOMPILE_AND_TAPE_DELAY.md)** — NEC uPD77213 ISA, silicon pipeline rules, FX dispatch table, and custom FX authoring ([`dsp-src/README.md`](dsp-src/README.md))
- **[Global Settings & NVRAM Format (`fw-src-sm/SETTINGS_FORMAT.md`)](fw-src-sm/SETTINGS_FORMAT.md)** — Complete byte-by-byte layout of `0x0C2D0000..0x0C2D01FF`
- **[ESX-1 SD Bootloader Analysis (`docs/ESX1SD_BOOTLOADER_DIFF.md`)](docs/ESX1SD_BOOTLOADER_DIFF.md)** — `BFS 01.03.01` memory map, boot key table, and `01.02` vs `01.03` symbol diff

---

## Debricking & JTAG Recovery

If a unit fails to boot after an interrupted update or even a corrupted NOR boot flash (`IC15`), full software and hardware recovery procedures are documented and included:

- **[Raspberry Pi Debricking & Recovery Guide (`docs/ESX1SD_DEBRICKING_PI.md`)](docs/ESX1SD_DEBRICKING_PI.md)** — Step-by-step recovery stages (SD card re-flash for NAND/BSS bricks, and full external NOR flash reprogramming via Raspberry Pi GPIO without desoldering, preserving unit-specific `TUBECALIBDATA` at `0x70000`)
- **[JTAG Hardware Pinout & Dump Log (`docs/ESX1SD_JTAG_DUMP.md`)](docs/ESX1SD_JTAG_DUMP.md)** — 14-pin H-UDI JTAG header wiring, Raspberry Pi pin mapping, and verified SHA-256 reference hashes
- **[Raspberry Pi JTAG Tools (`pi-jtag-sd/`)](pi-jtag-sd/)** — Read-only NOR/NAND dumpers (`esx_nor_dump.c`, `esx_nand_dump.c`, `jtag_probe.py`) and CFI NOR recovery flasher (`esx_nor_recover.c`)

---

## License

This project (toolchain, emulator, JTAG tools, custom firmware overlays, and DSP patches) is licensed under the **GNU General Public License v2.0 (`GPL-2.0-only`)** — see [`LICENSE`](LICENSE), matching the `SPDX-License-Identifier: GPL-2.0-only` headers in `emu-sx/`.

*(Third-party factory files under `factory-firmware-sm/` and `factory-firmware-sd/` remain the intellectual property of their respective copyright holders and are not covered by this open-source license.)*
