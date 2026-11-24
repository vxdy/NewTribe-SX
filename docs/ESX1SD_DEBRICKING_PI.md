# Korg ESX-1 SD (`01.03.01`) – Debricking & Recovery Guide (Raspberry Pi)

This guide covers **both recovery stages** for the **Korg Electribe SX-1 SD** (`KLM-302x`, Product ID `0xF1`):

1. **Stage 1 – Soft Brick (system firmware `.BSS` hangs or fails to boot, bootloader intact):** Recover in under 1 minute **via SD card** without opening the unit.
2. **Stage 2 – Hard Brick (NOR boot flash `IC15` corrupted or erased):** Recover via the internal 14-pin H-UDI JTAG header using a **Raspberry Pi 4** — **without desoldering any chips**.

> **Prerequisite:** The verified factory backup in [`../factory-firmware-sd/`](../factory-firmware-sd/) (`ESX0103N.BSS` for Stage 1, `raw/esx1sd_bfs_512k.bin` for Stage 2).

---

## Stage 1: Soft-Brick Recovery via SD Card (No Disassembly)

**When does Stage 1 apply?**
- After flashing an experimental or broken `.BSS` firmware, the ESX-1 SD fails to boot, hangs on the splash screen, or shows `NLoadEr` / `SysBrk`.
- As long as a `.BFS` file was **never** flashed, the NOR bootloader (`IC15`, `BFS 01.03.01`) remains 100% intact — Stage 1 **always** works.

### Procedure (SD Card)
1. Empty a FAT12 / FAT16 / FAT32 SD card and copy **only** the stock system firmware to its root directory:
   - [`../factory-firmware-sd/ESX0103N.BSS`](../factory-firmware-sd/ESX0103N.BSS) (exact size `2,097,152` bytes, Product ID `0xF1`, word sum `0x00000000`).
   - *Important:* Do not keep a second `.BSS` file in the root directory.
2. Insert the SD card into the **powered-off** ESX-1 SD.
3. Hold **`PATTERN`** + **`STEP EDIT`** and power on.
   - The LCD displays **`ND VerUp`** *(do NOT use `UP + DOWN` — `BFS 01.03.01` has a Korg Product-ID bug for `0xF1` under `UP + DOWN`, see [`ESX1SD_BOOTLOADER_DIFF.md`](ESX1SD_BOOTLOADER_DIFF.md))*.
4. Release the buttons and wait:
   - The bootloader reads `ESX0103N.BSS`, checks Product ID (`0xF1`) and word sum (`0x00000000`), programs NAND, reads everything back for verification, and displays **`Complete / UpDate`** → **`Turn OFF / Please`**.
   - **No version lock:** `ND VerUp` overwrites any installed version, including downgrading back to stock `01.03.01`.
5. Power off, remove the SD card, and power on normally.

---

## Stage 2: Hard-Brick Recovery via JTAG (Raspberry Pi 4)

**When is Stage 2 needed?**
- Only if the **NOR boot flash (`IC15`, ST `M29W160EB`)** itself was corrupted or erased (e.g., interrupted `.BFS` flash / power loss during bootloader update) so that even `PATTERN + STEP EDIT + Power` shows nothing.
- Using SH7709S **JTAG Boundary Scan (`EXTEST`)**, the Raspberry Pi drives every bus pin (`/CS0`, `/RD`, `/WE0`, `/WE1`, `A0..A22`, `D0..D15`) externally — the SH-3 CPU does **not** need to execute a single instruction.

### Required Hardware & Software
- **Raspberry Pi 4** running Raspberry Pi OS *(note: `esx_nor_recover.c` uses `/dev/gpiomem` for BCM2711; Pi 5 would require RP1 GPIO mapping)*.
- **6 jumper wires** (short, ≤ 15–20 cm) + pin header or test clips for the 14-pin H-UDI header.
- Tool: [`../pi-jtag/esx_nor_recover.c`](../pi-jtag/esx_nor_recover.c) (and optional read-only dumper [`../pi-jtag/esx_nor_dump.c`](../pi-jtag/esx_nor_dump.c)).
- Backup image: [`../factory-firmware-sd/raw/esx1sd_bfs_512k.bin`](../factory-firmware-sd/raw/esx1sd_bfs_512k.bin) (exact size `524,288` bytes).

---

### Step 2.1 – Wiring (14-Pin H-UDI Header → Raspberry Pi 4)

On the `KLM-302x` mainboard, directly **above and left of the CPU (`IC14`, `HD6417709S`)**, sits the unpopulated 2×7-pin header:

```text
          Left (L)               Right (R)
        +-----------+          +-----------+
 Row 1  | L1  GND   |          | R1  TCK   |  -> CPU Pin 139
 Row 2  | L2  GND   |          | R2  TRST# |  -> CPU Pin 136
 Row 3  | L3  GND   |          | R3  TDO   |  -> CPU Pin 120
 Row 4  | L4  UVCC* |          | R4  ASEB* |  -> CPU Pin 128
 Row 5  | L5  GND   |          | R5  TMS   |  -> CPU Pin 137
 Row 6  | L6  GND   |          | R6  TDI   |  -> CPU Pin 138
 Row 7  | L7  GND   |          | R7  RST#* |  -> RESET#
        +-----------+          +-----------+
```

#### Exact 6-Wire Mapping (3.3 V logic on both sides)

| ESX-1 SD Header | Signal | Raspberry Pi **BCM GPIO** | Raspberry Pi **Physical Pin** (40-pin header) |
|---|---|---|---|
| `L1` *(or `L2/L3/L5/L6/L7`)* | **`GND`** | `GND` | **Pin 6** *(or 20)* |
| `R1` | **`TCK`** | **GPIO 25** | **Pin 22** |
| `R2` | **`TRST#`** | **GPIO 24** | **Pin 18** |
| `R3` | **`TDO`** | **GPIO 9** | **Pin 21** |
| `R5` | **`TMS`** | **GPIO 23** | **Pin 16** |
| `R6` | **`TDI`** | **GPIO 10** | **Pin 19** |

> **IMPORTANT — Do NOT connect:**
> - Leave **`L4` (`UVCC`)** **unconnected** — never tie 3.3 V or 5 V power rails between the Pi and the ESX-1 SD.
> - Leave **`R4` (`ASEBRKAK#`)** and **`R7` (`RESET#`)** unconnected.
> - Keep **SPI disabled** on the Raspberry Pi (default) so GPIO 9/10 remain free.
> - **Order:** Wire everything (`GND` first) while the ESX-1 SD is **powered off** — only power on the ESX-1 SD via its own adapter afterward.

---

### Step 2.2 – Compile the Recovery Tool on the Raspberry Pi

Copy `pi-jtag/esx_nor_recover.c` and `factory-firmware-sd/raw/esx1sd_bfs_512k.bin` to the Pi (e.g., `~/recovery/`) and compile:

```bash
cd ~/recovery
gcc -O2 -Wall -Wextra -o esx_nor_recover esx_nor_recover.c
```

Verify the backup checksum first:

```bash
sha256sum esx1sd_bfs_512k.bin
# Expected: 58ac6b8296c3651412d03554583304394bb05ee60651691931680b01faf3c594
```

---

### Step 2.3 – Probe Connection & Flash Chip (Read-Only)

Power on the ESX-1 SD (a blank LCD is normal on a hard brick), then run:

```bash
./esx_nor_recover --probe
```

Expected output:
```text
SH7709S IDCODE = 0x0000100F, BYPASS = OK
NOR Flash Autoselect ID: Manufacturer=0x0020, Device=0x2249 (ST M29W160EB - MATCH!)
Header @ 0x6FFE0: ...
Calib  @ 0x70000: 'TUBECALIBDATA'
```

*(If `TUBECALIBDATA` @ `0x70000` is still intact in flash, back up Sector 10 first for safety:)*

```bash
./esx_nor_recover --backup-calib tubecalib_current_64k.bin
```

---

### Step 2.4 – Reflash the Bootloader (`BFS 01.03.01`)

**Standard recovery (recommended — leaves `TUBECALIBDATA` at `0x70000` untouched!):**

```bash
./esx_nor_recover --flash esx1sd_bfs_512k.bin --i-understand-risk --unlock-bypass
```

What `esx_nor_recover` does automatically:
1. Validates the input file before issuing any erase (`524,288` B, `KORG` + `BFS ` @ `0x6FFE0`, Product ID `0xF1`, 32-bit BE word sum `0x00000..0x6FFFF` == `0x00000000`).
2. Keeps internal NAND strictly deselected (`/CS5 = 1`, `PTE1 = 1`, `PTE6 = 0`).
3. Verifies `IDCODE = 0x0000100F`, `BYPASS`, and NOR chip ID (`0x0020:0x2249`).
4. Erases and programs **only Sectors 0–9 (`0x00000..0x6FFFF`, 448 KiB)**:
   - Sector 0: `0x00000` (16 KiB), Sector 1: `0x04000` (8 KiB), Sector 2: `0x06000` (8 KiB), Sector 3: `0x08000` (32 KiB), Sectors 4–9: `0x10000..0x60000` (64 KiB each).
   - Skips `0xFFFF` words automatically and uses the `M29W160EB` fast 2-cycle Unlock Bypass mode (~2–4 minutes total; omit `--unlock-bypass` for standard 4-cycle mode, ~5–7 minutes).
5. **Verifies every sector byte-for-byte immediately after programming.**

> **Only if Sector 10 (`0x70000`, `TUBECALIBDATA`) was also erased:** Add `--include-calib` to restore the factory tube calibration sector from the backup.

---

### Step 2.5 – Final Verification & Reboot

Verify the entire bootloader region once more:

```bash
./esx_nor_recover --verify esx1sd_bfs_512k.bin
```

Expected: `VERIFY PASS: 0x00000..0x6FFFF (458752 bytes) 100% IDENTICAL!`

Then:
1. **Power off the ESX-1 SD** (unplug power).
2. Disconnect all **6 JTAG wires**.
3. Power on the ESX-1 SD normally:
   - If the NAND OS is still intact, it boots directly.
   - If NAND was also corrupted, **Stage 1** (`PATTERN + STEP EDIT + Power` with `ESX0103N.BSS` on SD card) now works again.

---

## Troubleshooting (JTAG / Pi 4)

| Symptom | Cause / Solution |
|---|---|
| `IDCODE = 0x00000000` or `0xFFFFFFFF` | ESX-1 SD is off, `GND` missing, or header pin shifted by one row. Recheck wiring (`R1/R2/R3/R5/R6`). |
| `BYPASS check failed` | Wires too long / signal noise → slow down the clock with `--delay 40` (or `--delay 80`). |
| `NOR Flash ID: 0xFFFF:0xFFFF` or unexpected | Try slower clock (`--delay 40`), or verify datasheet if a different compatible NOR chip is fitted (use `--force-id` without `--unlock-bypass` only after confirming sector layout). |
| `open(/dev/gpiomem): Permission denied` | Add user to the `gpio` group or run with `sudo ./esx_nor_recover ...`. |
| Power loss / abort during `--flash` | **Safe to retry:** Once power is stable, simply re-run `--flash` — JTAG `EXTEST` does not depend on a working bootloader. |
