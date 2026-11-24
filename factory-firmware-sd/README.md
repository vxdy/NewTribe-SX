# Factory Firmware Backup – Korg ESX-1 SD (`01.03.01`)

Unmodified, double-verified factory backup from a real **Korg Electribe SX-1 SD** (`KLM-302x`, Product ID `0xF1`, `Flash 01.03.01`, `N-Sys 01.03.01`, `DSP 01.02.00`), dumped via read-only H-UDI JTAG (see [`../docs/ESX1SD_JTAG_DUMP.md`](../docs/ESX1SD_JTAG_DUMP.md)).

> **Do not modify this directory.** It serves as the permanent golden-master backup and build reference for ESX-1 SD firmware builds (analogous to `../factory-firmware-sm/` for the older SmartMedia ESX-1).

## Contents

| File | Size | Purpose | Checksum |
|---|---:|---|---|
| `ESX0103N.BSS` | 2 MiB | **SD-card recovery image** (`BSS 01030001`, ID `0xF1`) — directly flashable via SD card | 32-bit BE word sum = `0x00000000` |
| `ESX0102D.BDS` | 960 KiB | Factory DSP firmware (`BDS 01020000`, bit-identical to `factory-firmware-sm/ESX0102D.BDS`) | 32-bit BE word sum = `0x00000000` |
| `raw/esx1sd_bfs_512k.bin` | 512 KiB | Raw NOR boot flash dump (`BFS 01030001` + **unit-specific `TUBECALIBDATA`** @ `0x70000`) | Word sum (`0x00000..0x6FFFF`) = `0x00000000` |
| `raw/esx1sd_bss_010301_raw.bin` | 2 MiB | Raw NAND dump of `N-Sys` (blocks 1–16, header at tail `0x1FFFE0`) | Word sum = `0x00000000` |
| `raw/esx1sd_bds_1m_raw.bin` | 1 MiB | Raw NAND dump blocks 17–23 + 31 (`BDS` + global header `SET3_2` @ `0x0FC000`) | First 960 KiB = `0x00000000` |
| `raw/esx1sd_nand_cis_blk0.bin` | 128 KiB | NAND Block 0 (CIS) | – |
| `raw/esx1sd_nand_oob_all.bin` | 64 KiB | 64-byte OOB/LBA spare data for all 1,024 NAND blocks | – |
| `SHA256SUMS.txt` | – | SHA-256 verification hashes for all files in this directory | – |

## Restoring Stock `01.03.01` via SD Card (Recovery)

1. Copy `ESX0103N.BSS` alone (only one `.BSS` file in root) to a FAT12/FAT16/FAT32 SD card.
2. Insert the SD card into the powered-off ESX-1 SD.
3. Hold **`PATTERN` + `STEP EDIT`** and power on (`ND VerUp` appears).
4. Wait for `Complete / UpDate` → `Turn OFF / Please`, then reboot.

*(Background on `PATTERN + STEP EDIT` vs. `UP + DOWN`: see [`../docs/ESX1SD_BOOTLOADER_DIFF.md`](../docs/ESX1SD_BOOTLOADER_DIFF.md).)*
