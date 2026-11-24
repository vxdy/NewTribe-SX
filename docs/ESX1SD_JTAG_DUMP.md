# Korg ESX-1 SD (`01.03.01`) – JTAG Pinout & Read-Only Firmware Dumps

Documentation of the verified **read-only JTAG dump** (no desoldering required) of a **Korg Electribe SX-1 SD** (`KLM-302x` mainboard, Product ID `0xF1`, OS `01.03.01`) using a **Raspberry Pi 4**.

---

## 1. Hardware Overview (ESX-1 SD, `KLM-302x` Mainboard)

| Component | Chip / Part | Details |
|---|---|---|
| **CPU (`IC14`)** | Hitachi/Renesas `HD6417709S` (SH-3, 100 MHz, 208-pin QFP) | Big-Endian, H-UDI / IEEE 1149.1 JTAG (`IDCODE = 0x0000100F`, 16-bit IR, 339-bit BSR identical to `sh7729`) |
| **NOR Boot Flash (`IC15`)** | ST/Numonyx `M29W160EB` (TSOP-48, 16-bit `/CS0`, 2 MiB) | `BFS 01.03.01` in `0x00000..0x6FFFF` (header @ `0x6FFE0`), unit-specific `TUBECALIBDATA` @ `0x70000` |
| **Internal NAND Flash** | Hynix `HY27UF081G2A` (`ID = AD F1 00 1D`), 128 MiB, 8-bit (`/CS5`) | Large-page `2048 + 64 B`, 64 pages/block (`128 KiB`), 1,024 blocks. **Quirk:** OOB sits at column `0x0000..0x003F`, payload at `0x0040..0x083F`; write strobe is `WE1` |

---

## 2. Location & Pinout of the 14-Pin H-UDI / JTAG Header

On the `KLM-302x` mainboard, **above and left of the CPU (`IC14`)**, sits an unpopulated **2×7-pin solder header** (standard Renesas 14-pin H-UDI header).

Top-down view of the PCB (`IC14` lies below/right of the header; column `L` on the left, column `R` on the right, row `1` top to row `7` bottom):

```text
          Left (L)               Right (R)
        +-----------+          +-----------+
 Row 1  | L1  GND   |          | R1  TCK   |  -> CPU Pin 139
 Row 2  | L2  GND   |          | R2  TRST# |  -> CPU Pin 136
 Row 3  | L3  GND   |          | R3  TDO   |  -> CPU Pin 120
 Row 4  | L4  UVCC* |          | R4  ASEB* |  -> CPU Pin 128 (ASEBRKAK#)
 Row 5  | L5  GND   |          | R5  TMS   |  -> CPU Pin 137
 Row 6  | L6  GND   |          | R6  TDI   |  -> CPU Pin 138
 Row 7  | L7  GND   |          | R7  RST#* |  -> RESET#
        +-----------+          +-----------+
```

> `*` **Do not connect:** Leave `L4` (`UVCC` = 3.3 V), `R4` (`ASEBRKAK#`), and `R7` (`RESET#`) **unconnected**.

---

## 3. Raspberry Pi Wiring (6 Wires)

Only **6 wires** are needed (`GND` + 5 JTAG signals). Logic levels match directly (**3.3 V CMOS** on both sides).

| ESX-1 SD (H-UDI Header) | Signal | CPU Pin (`IC14`) | Direction (from Pi) | Raspberry Pi **BCM GPIO** | Raspberry Pi **Physical Pin** (40-pin header) |
|---|---|---|---|---|---|
| `L1` *(or `L2/L3/L5/L6/L7`)* | **`GND`** | GND | Ground | `GND` | **Pin 6** *(or 9, 14, 20, 25, 30, 34, 39)* |
| `R1` | **`TCK`** | Pin 139 | Output (`OUT`) | **GPIO 25** | **Pin 22** |
| `R2` | **`TRST#`** | Pin 136 | Output (`OUT`) | **GPIO 24** | **Pin 18** |
| `R3` | **`TDO`** | Pin 120 | **Input (`IN`)** | **GPIO 9** | **Pin 21** |
| `R5` | **`TMS`** | Pin 137 | Output (`OUT`) | **GPIO 23** | **Pin 16** |
| `R6` | **`TDI`** | Pin 138 | Output (`OUT`) | **GPIO 10** | **Pin 19** |

**Leave unconnected:** `L4` (`UVCC`), `R4` (`ASEBRKAK#`), `R7` (`RESET#`). Never connect 3.3 V or 5 V power rails between the Pi and the ESX-1 SD.

### Raspberry Pi 40-Pin Header Excerpt (Pins 15–22)

```text
  Pin 15 (GPIO 22)  [ ] [●]  Pin 16 (GPIO 23)  --> R5 (TMS)
  Pin 17 (3.3V)     [ ] [●]  Pin 18 (GPIO 24)  --> R2 (TRST#)
  Pin 19 (GPIO 10)  [●] [●]  Pin 20 (GND)      --> L1 (GND)  (or Pin 6)
  Pin 21 (GPIO  9)  [●] [●]  Pin 22 (GPIO 25)  --> R1 (TCK)
                     ^
                     +--- R3 (TDO)   /   Pin 19 = R6 (TDI)
```

---

## 4. Safety & Operating Notes

1. **Connection order:** Wire `GND` first, then the 5 JTAG signals while the ESX-1 SD is **powered off**. Ensure SPI is disabled on the Pi (default) and no power pins are connected. Power on the ESX-1 SD via its own adapter afterward.
2. **Blank LCD during dumping is normal:** Once JTAG `EXTEST` (Boundary Scan) takes control of the external CPU pins, the SH-3 core is temporarily isolated from the bus/LCD (backlight stays on, text disappears). Simply power-cycle the ESX-1 SD after dumping to resume normal operation.
3. **Read-only protection in the dump tools:**
   - `esx_nor_dump.c`: Preloads a safe idle state via `SAMPLE/PRELOAD` before entering `EXTEST`; `/WE0..3` and `RDWR` are locked `HIGH`, `D0..D31` locked `Hi-Z`.
   - `esx_nand_dump.c`: Locks `/CS0` (NOR) `HIGH` and enforces a strict read-only NAND command whitelist (`0xFF`, `0x90`, `0x00`, `0x30`, `0x05`, `0xE0`, `0x70`).
   - Both tools return all Pi GPIOs to high-impedance inputs (`Hi-Z`) on exit.

---

## 5. Building & Running on Raspberry Pi 4

Tools live in [`../pi-jtag/`](../pi-jtag/):

```bash
# 1. Connection test (expect IDCODE = 0x0000100F, BYPASS = OK)
python3 jtag_probe.py

# 2. Dump NOR boot flash (IC15, 512 KiB BFS) twice & compare
gcc -O2 -Wall -o esx_nor_dump esx_nor_dump.c
./esx_nor_dump --probe
./esx_nor_dump --dump bfs_pass1.bin 524288 --delay 15
./esx_nor_dump --dump bfs_pass2.bin 524288 --delay 15
sha256sum bfs_pass1.bin bfs_pass2.bin

# 3. Dump internal Hynix NAND (AD F1 00 1D): OOB scan, BSS (2 MiB), BDS (1 MiB) & CIS (Block 0)
gcc -O3 -Wall -o esx_nand_dump esx_nand_dump.c
./esx_nand_dump --probe --delay 15
./esx_nand_dump --scan-oob nand_oob_all.bin --delay 6
./esx_nand_dump --dump-blocks 1-16 bss_pass1.bin --delay 6
./esx_nand_dump --dump-blocks 1-16 bss_pass2.bin --delay 6
./esx_nand_dump --dump-blocks 17-23,31 bds_pass1.bin --delay 6
./esx_nand_dump --dump-blocks 0 nand_cis_blk0.bin --delay 6
sha256sum bss_pass1.bin bss_pass2.bin bds_pass1.bin nand_cis_blk0.bin
```

> Note: On Raspberry Pi 4, `esx_nor_dump` and `esx_nand_dump` use `/dev/gpiomem` directly (~31.5 KiB/s for 16-bit NOR, ~11.8 KiB/s for 8-bit NAND).

---

## 6. Verified Dump Inventory (`../factory-firmware-sd/`)

| File | Size | Contents | Verification | SHA-256 |
|---|---|---|---|---|
| `raw/esx1sd_bfs_512k.bin` | 512 KiB | NOR boot flash (`BFS 01030001`, ID `0xF1`) + `TUBECALIBDATA` @ `0x70000` | 2× bit-identical, 32-bit BE word sum (`0x00000..0x6FFFF`) = `0x00000000` | `58ac6b8296c3651412d03554583304394bb05ee60651691931680b01faf3c594` |
| `raw/esx1sd_bss_010301_raw.bin` | 2 MiB | Raw NAND `N-Sys` (`BSS 01030001`, ID `0xF1`, blocks 1–16, header @ `0x1FFFE0`) | 2× bit-identical, word sum = `0x00000000` | `6e3be6a4ee95649703e9c3d13aeed4a5442130af6c2ecd5bae25122a03fa6e10` |
| `ESX0103N.BSS` | 2 MiB | SD update container (32-byte `KORG` header at `0x000000` + payload) | Word sum = `0x00000000` | `729d6cdfdfb28c8f958ddd0f1a4f3c55bc24df4d0f9a5d1e1cced4562ec97a88` |
| `raw/esx1sd_bds_1m_raw.bin` | 1 MiB | NAND blocks 17–23 + 31 (`BDS 01020000` 960 KiB + `SET3_2` @ `0x0FC000`) | First 960 KiB bit-identical to `ESX0102D.BDS`, word sum = `0x00000000` | `96bee4cfa8a2e03a371810fc5f2663fd18e95076013d096e6305258567abbe86` |
| `raw/esx1sd_nand_cis_blk0.bin` | 128 KiB | NAND CIS / Block 0 | – | `13782b5474bb26b320c183424b50b4614de5ca18208b643df71bfe6ccb80b6a3` |
| `raw/esx1sd_nand_oob_all.bin` | 64 KiB | 64-byte OOB/LBA spare data for all 1,024 NAND blocks | – | `636f7789424c8a0ac1e02a8ed17d7578e07cb54f0445b1a64be60434fd8d04cc` |

---

## 7. Related Documentation & Backups

- **Bootloader analysis, SD update rules (`PATTERN + STEP EDIT` / `ND VerUp`), & `01.02` → `01.03.01` diff:** [`ESX1SD_BOOTLOADER_DIFF.md`](ESX1SD_BOOTLOADER_DIFF.md)
- **Permanent unmodified factory backup (with `SHA256SUMS.txt`):** [`../factory-firmware-sd/`](../factory-firmware-sd/)
