# Newtribe-SX – Documentation

Central index of all technical documentation in this repository:

| Document | Contents |
|---|---|
| [`DSP_DECOMPILE_AND_TAPE_DELAY.md`](DSP_DECOMPILE_AND_TAPE_DELAY.md) | **DSP Decompilation (`uPD77213` / `ESX0102D.BDS`) & Tape Delay PoC:** Full 16-FX dispatch table, lossless assembler toolchain (`dsp-src/`), Vintage Tape Delay in the RingMod slot, real-silicon pipeline rules, audio verification & `DSPVerUp` flashing |
| [`ESX1SD_DEBRICKING_PI.md`](ESX1SD_DEBRICKING_PI.md) | **Debricking & Recovery Guide (ESX-1 SD, Raspberry Pi):** Stage 1 SD-card recovery (`PATTERN + STEP EDIT + Power`), Stage 2 JTAG NOR flash recovery (`pi-jtag-sd/esx_nor_recover.c`) preserving `TUBECALIBDATA` |
| [`ESX1SD_JTAG_DUMP.md`](ESX1SD_JTAG_DUMP.md) | 14-pin H-UDI JTAG pinout, Raspberry Pi wiring guide, read-only dump procedure & verified SHA-256 hashes |
| [`ESX1SD_BOOTLOADER_DIFF.md`](ESX1SD_BOOTLOADER_DIFF.md) | Bootloader analysis (`BFS 01.03.01`), Korg's `UP + DOWN` Product-ID bug, `ND VerUp` / `DSPVerUp` procedures & `01.02.00` → `01.03.01` symbol diff |
| [`../fw-src-sm/SETTINGS_FORMAT.md`](../fw-src-sm/SETTINGS_FORMAT.md) | Global settings memory layout (NVRAM / NAND / SDRAM / `.esx`), persistence routines & checksums |
| [`../fw-src-sm/README.md`](../fw-src-sm/README.md) | Architecture of the reassemblable SH-3 firmware toolchain (`shdis`, `shasm`, `bsspack`, Newtribe overlay system) |
| [`../dsp-src/README.md`](../dsp-src/README.md) | Quick-start guide for the NEC uPD77213 DSP toolchain (`dspasm`, `bdspack`, Tape Delay PoC) |
