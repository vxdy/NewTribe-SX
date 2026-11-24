# ESX-1 (Electribe SX) Emulator (`emu-sx/`)

Native Hitachi SH7709 (SH-3, Big-Endian) + NEC uPD77213 DSP emulator built to verify custom ESX-1 system (`.BSS`) and DSP (`.BDS`) firmwares before flashing real hardware.

```sh
python esxemu.py check ESX0101F.BFS ESX0102N.BSS ESX0102D.BDS   # Container & checksum check
python esxemu.py boot  ESX0101F.BFS --ph4 0                     # Boot flash startup & LCD output
python test_basic.py                                            # CPU core & container unit tests
```

Python 3.10+ only (`capstone` optional for `shdis.py`).

## Why a Custom SH-3 + uPD77213 Core

Unlike the ARM-based Electribe 2, the Electribe SX-1 runs on a **Hitachi SH7709 (SH-3, Big-Endian)** paired with a **NEC uPD77213** audio DSP. Because Unicorn does not support SH-3, this project provides both a readable Python reference core (`sh3.py`) and a high-speed Rust core (`core/`) achieving ~100–160 MIPS (roughly real-time 96 MHz hardware speed) plus a full uPD77213 DSP interpreter/AOT engine with 44.1 kHz stereo audio output.

## Measured Hardware Architecture (OS 1.02 / 1.03)

| File | Size | Contents |
|---|---:|---|
| `ESX0101F.BFS` | 512 KiB | NOR boot flash (`0xA0000000`, 8-bit AMD on SM, 16-bit ST `M29W160EB` on SD). |
| `ESX0102N.BSS` / `ESX0103N.BSS` | 2 MiB | Main system firmware (N-Sys, loaded to `0x0C080000`, entry `0x0C081000`). |
| `ESX0102D.BDS` | 960 KiB | NEC uPD77213 DSP firmware (`IRAM`, `XRAM`, `YRAM`, two copies with `0x00000000` word sums). |

- **Header & Checksum:** `"KORG"`, Product ID (`0x00000071` on SmartMedia & `.BDS`, `0x000000F1` on SD `.BSS`), type (`BFS `/`BSS `/`BDS\0`), version. Every container requires a **32-bit big-endian word sum of `0x00000000`**.
- **Display & Controls:** 4-bit HD44780-compatible LCD (`E` = Port E bit 2, data = `SCPDR` bits 0..3, `RS` = bit 5, `RW` = bit 6); key matrix (`PJ[7:4]` selects row, `PG` reads active-low keys; row 6 mask 1 is held low on real hardware); 10-bit ADC pots (`ADCSR` @ `0xA4000090`); Gray-code `VALUE` encoder on `PH[6:5]`.
- **NAND Flash:** Behind `0x14000000`, steered by Port E (`CLE`, `ALE`, `/CE0` SmartMedia card, `/CE1` internal NAND) with SmartMedia SSFDC ECC verified against the bootloader's own ECC routine.
- **DSP Host Port (`0x08000000`):** Uploads ~39,800 16-bit words at boot and runs a full native NEC uPD77213 core (`core/src/dsp.rs`) synced via `IRQ3` (audio frame block) with live stereo audio capture (`emu_dsp_audio`).

## Building & Running the Rust Core

```sh
cd core && cargo build --release     # builds sh3core.dll / libsh3core.so / libsh3core.dylib
python rtest.py 2000000000 1         # boot system from out_flash.bin / out_nand.bin
python server.py                     # browser UI on http://127.0.0.1:8765/
```

`rmachine.py` wraps `sh3core` via `ctypes` (used by `fw-src/tools/emutest.py`, `fw-src-sd/emutest_sd.py`, and `dsp-src/test_tape_delay.py`). A native Rust desktop UI is also in `app/` (see [`app/SPEC.md`](app/SPEC.md)).

## License

Licensed under **GPL-2.0-only** (see `SPDX-License-Identifier` headers and root [`../LICENSE`](../LICENSE)).
