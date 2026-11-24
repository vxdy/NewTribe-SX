# Korg ESX-1 SD (`01.03.01`) – Bootloader Analysis, SD Update Rules & Diff vs. `01.02.00`

Analysis of the verified JTAG dumps ([`esx1sd_bfs_512k.bin`](../factory-firmware-sd/raw/esx1sd_bfs_512k.bin) and [`ESX0103N.BSS`](../factory-firmware-sd/ESX0103N.BSS)) for porting **Newtribe** to the **Korg Electribe SX-1 SD** (`KLM-302x`, Product ID `0xF1`).

---

## 1. Bootloader Memory Map (`BFS 01.03.01`)

The startup copy routine in NOR flash (`0xA0002008`) relocates the bootloader into SDRAM at power-on:

| Source (NOR Flash) | Destination (SDRAM) | Size | Contents |
|---|---|---|---|
| `0xA0002684..0xA000F08B` | `0x0C000004..0x0C00CA0B` | `0xCA08` | Main bootloader (`BFS` library & updaters) — offset delta: `NOR = SDRAM - 0x0C000000 + 0x2680` |
| `0xA000F08C..0xA000F83B` | `0x0C00CA0C..0x0C00D1BB` | `0x07B0` | Constants / LCD strings (`SysVerUp`, `ND VerUp`, `DSPVerUp`, `SameVer.`, `CkSumErr`, …) |
| *(zero-filled)* | `0x0C00D1BC..0x0C04C896` | `0x3F6DB` | Bootloader BSS / work RAM |
| `0xA000F83C..0xA000F84F` | `0x0C04C898..0x0C04C8AB` | `0x0014` | Initialized data |
| `0xA000F850..0xA001DB3B` | `0x0C04C8AC..0x0C05AB97` | `0xE2EC` | Additional library routines (e.g., `memcmp @ 0x0C058F28`, `memcpy @ 0x0C058F68`) |
| `0xA001DB3C..0xA001EAE3` | `0x0C05AB98..0x0C05BB3F` | `0x0FA8` | Additional data tables |

**Normal Boot (`0xA0002330` → `0x0C00B24C`):**
1. `0x0C00B20A` reads NAND page `0x3FF` (`0x1FF800`) and checks only the 3 ASCII bytes `"BSS"` at offset `+0x7E8` (`0x1FFFE8`).
2. `0x0C00B24C` loads all `0x400` pages (`2,097,152` B) from NAND to **`0x0C080000`** (payload `0x0C080000..0x0C27FFDF`, 32-byte header at `0x0C27FFE0..0x0C27FFFF`).
3. `0xA0002348` jumps to **`0x0C081000`** (`main_entry`) — identical to the older SmartMedia ESX-1.

---

## 2. SD Card Update Rules & Korg's Bug in `UP + DOWN`

### File Discovery (`0x0C00AC8A`)
- Scans the **root directory** of a `FAT12` / `FAT16` / `FAT32` SD card.
- Matches **only the 3-character extension** and **exact file size** (base filename is ignored; place only one file of each type in root):
  - `*.BFS` → `524,288` B (`0x080000`)
  - `*.BSS` → `2,097,152` B (`0x200000`)
  - `*.BDS` → `983,040` B (`0x0F0000`)

### Why `UP + DOWN + Power` (`SysVerUp`) Fails for `0xF1` `.BSS` Files
`BFS 01.03.01` contains a Korg firmware bug between its pre-scan and main loader:
- **Pre-scan (`0x0C00C35A`, called by `SysVerUp @ 0x0C00C446`):**
  ```asm
  0x0C00C37C: mov.b   @(7,r14),r0      ; Header byte 7 (Product ID)
  0x0C00C37E: cmp/eq  #113,r0          ; 0x71! Korg forgot "and #0x7F,r0" here!
  ```
  *(The internal version readers `0x0C00A2EC` and `0x0C00A31E` do mask with `and #0x7F,r0`, accepting both `0x71` and `0xF1` — `0x0C00C37C` is missing it.)*
- **Actual BSS loader (`0x0C00AF08`, called by `VerUp N` and `ND VerUp`):**
  ```asm
  0x0C00AF3E: mov.b   @(7,r11),r0
  0x0C00AF40: extu.b  r0,r2
  0x0C00AF42: extu.b  r12,r0           ; Stack param = 0x80 (for ESX-1 SD)
  0x0C00AF44: or      #0x71,r0         ; 0x80 | 0x71 = 0xF1!
  0x0C00AF46: cmp/eq  r0,r2            ; Strictly requires Product ID 0xF1!
  ```
- **Result:** Under `UP + DOWN + Power`, a `0xF1` `.BSS` is silently skipped during pre-scan, while a `0x71` `.BSS` passes pre-scan and then fails loading with `FileLdEr`.

### Working SD Flash Modes (`ND VerUp` & `DSPVerUp`)
- **System Firmware (`*.BSS`) — `PATTERN + STEP EDIT + Power` (`Case 2` → `0x0C00B298`, `ND VerUp`):**
  Bypasses the buggy `0x71` pre-scan completely, verifies `header[7] == 0xF1` and 32-bit BE word sum `== 0x00000000` (`0x0C00AC26`), enforces **no version lock** (free upgrades & downgrades), writes 2 MiB to NAND, reads it back, and re-verifies `0x00000000`.
- **DSP Firmware (`*.BDS`) — `PATTERN + GLOBAL + Power` (`Case 5` → `0x0C00B8B2`, `DSPVerUp`):**
  Loads `983,040` B (`0x0F0000`) to `0x0C800000`, verifies 32-bit BE word sum `== 0x00000000`, enforces **no version lock**, writes 480 pages to NAND `0x200000..0x2EFFFF`, and verifies them back.
- **Safety:** Neither mode ever touches the NOR boot flash (`BFS` in `IC15`) or `TUBECALIBDATA`.

### Boot Key Combinations (`BFS 01.03.01`, `0xA00024C6`)

| Case | Keys Held at Power-On | Target | Function |
|---:|---|---|---|
| `1` | `PATTERN` + `SAMPLE` | `0x0C00B060` | `FlsVerUp` (NOR Boot Flash `*.BFS` — **do not use!**) |
| **`2`** | **`PATTERN` + `STEP EDIT`** | **`0x0C00B298`** | **`ND VerUp` (NAND System `*.BSS`, ID `0xF1`, no version lock)** |
| `3` | `PATTERN` + `SONG` | `0x0C00B570` | `USRVerUp` (User data `*.BUS`) |
| **`5`** | **`PATTERN` + `GLOBAL`** | **`0x0C00B8B2`** | **`DSPVerUp` (DSP firmware `*.BDS`, 960 KiB, no version lock)** |
| `16` | `WRITE` + `SOLO` | `0x0C00C310` | `All Init` (Factory reset) |
| `17` | `UP` + `DOWN` | `0x0C00C446` | `SysVerUp` *(broken for `0xF1` `.BSS` due to missing `and #0x7F` at `0x0C00C37C`)* |
| `20` | `SHIFT` + `D7B` | `0x0C00C7EA` | `TUBECALIBDATA` viewer |

---

## 3. Emergency JTAG Recovery (Worst-Case NOR Brick)

- During normal Newtribe development (`.BSS` / `.BDS` updates), NOR flash is never written and SD recovery always works.
- In the worst case of a corrupted NOR bootloader (`IC15`, ST `M29W160EB`), the 14-pin H-UDI JTAG port allows full external NOR reprogramming via SH7709S boundary scan (`EXTEST`) using [`../pi-jtag-sd/esx_nor_recover.c`](../pi-jtag-sd/esx_nor_recover.c) without desoldering any chip (see [`ESX1SD_DEBRICKING_PI.md`](ESX1SD_DEBRICKING_PI.md)).

---

## 4. Diff: `ESX0102N.BSS` (`01.02.00`) vs. `ESX0103N.BSS` (`01.03.01`)

### Structural Comparison
- **Container:** Same 2 MiB layout (32-byte header + `0x1FFFE0` payload, 32-bit BE word sum `0x00000000`), with Product ID **`0x000000F1`** (instead of `0x00000071`) and version **`01030001`** (instead of `01020000`).
- **Payload header (`0x0C080000`):** `00010003 00000001 00010002 00000000` (was `00010002 00000000 00010002 00000000`).
- **Newtribe overlay gap:** Identical **2,488-byte zero gap** at **`0x0C080648..0x0C080FFF`** immediately before `main_entry` (**`0x0C081000`**).
- **Similarity:** **88.1%** of the first 1 MiB matches verbatim in 32-byte chunks.
- **Image growth:** From `0x0C0ED9F0` (`01.02.00`) to **`0x0C0EE98C`** (`01.03.01`, **`+0xF9C` = +3,996 bytes**), primarily from SD card and large-page NAND drivers in `0x0C0B9xxx..0x0C0C9xxx`.

### Verified Newtribe Symbol Mapping (`01.02.00` → `01.03.01`)

| Module | Symbol / Purpose | `01.02.00` (`ESX-1`) | `01.03.01` (`ESX-1 SD`) | Delta |
|---|---|---:|---:|---:|
| **Global Menu** | `lcd_set_cursor` | `0x0C0B1B1C` | `0x0C0B1BB0` | `+0x94` |
| (`globalpage.s`) | `lcd_print_str` | `0x0C0B1D86` | `0x0C0B1E1A` | `+0x94` |
| | `nop_stub_leave` / `nop_stub_enter` | `0x0C093224` | `0x0C0932FC` | `+0xD8` |
| | `nop_stub_edit` | `0x0C093228` | `0x0C093300` | `+0xD8` |
| | `tbl_edit` (42 entries) | `0x0C0D23D0` | `0x0C0D333C` | `+0xF6C` |
| | `tbl_leave` (42 entries) | `0x0C0D25F0` | `0x0C0D355C` | `+0xF6C` |
| | `tbl_enter` (42 entries) | `0x0C0D2698` | `0x0C0D3604` | `+0xF6C` |
| | `tbl_display` (42 entries) | `0x0C0D2740` | `0x0C0D36AC` | `+0xF6C` |
| | `tbl_maxpage` (`{6,4,4,6,6,6}`) | `0x0C0DBAF8` | `0x0C0DCA58` | `+0xF60` |
| **Splash** | `bss_clear_entry` (1st call in `main_entry`) | `0x0C0CC4EC` | `0x0C0CD3C8` | `+0xEDC` |
| (`splash.s`) | `factory_korg_logo` | `0x0C0B2A5C` | `0x0C0B2AF0` | `+0x94` |
| | `factory_anim_mode` | `0x0C0B2A04` | `0x0C0B2A98` | `+0x94` |
| | `sample_mem_check` | `0x0C0C71C8` | `0x0C0C8054` | `+0xE8C` |
| | `task3_marquee_tick` | `0x0C0B2AA2` | `0x0C0B2B36` | `+0x94` |
| | `task3_handler_wrap` | `0x0C0CC4E6` | `0x0C0CD3C2` | `+0xEDC` |
| | `tick_desc` (`{0,0,wrap,300,1}`) | `0x0C0E0894` | `0x0C0E1830` | `+0xF9C` |
| | `dsp_err_screen` | `0x0C0B2B18` | `0x0C0B2BAC` | `+0x94` |
| | `str_Recovery` (`"Recovery"`) | `0x0C0E034C` | `0x0C0E12E8` | `+0xF9C` |
| | `splash_finish` | `0x0C0B2B86` | `0x0C0B2C1A` | `+0x94` |
| | `NT_VARS` (5 B splash RAM, 8 B free) | `0x0C14F6E8` | `0x0C150A94` | `+0x13AC` |
| | `bfs_lcd_cgram` (BFS library) | `0x0C002BB0` | `0x0C003160` | `+0x5B0` |
| | `bfs_lcd_puts` (BFS library, full 8 chars/line) | `0x0C002B72` | `0x0C003122` | `+0x5B0` |
| | `bfs_delay_us` (BFS library) | `0x0C009B96` | `0x0C00C766` | `+0x2BD0` |
| **ShiftMut** | `lcd_clamp` | `0x0C09B734` | `0x0C09B818` | `+0xE4` |
| (`shiftmute.s`) | `lcd_print_onoff` | `0x0C0B24EC` | `0x0C0B2580` | `+0x94` |
| | `lcd_blank` | `0x0C0B1C5E` | `0x0C0B1CF2` | `+0x94` |
| | `set_param` (`0x1F7` = PART MUTE) | `0x0C0BA992` | `0x0C0BAA46` | `+0xB4` |
| | `part_unmute_helper` | `0x0C0BB0C8` | `0x0C0BB17C` | `+0xB4` |
| | Patch literal (`lit_0C0BB274` → `set_param`) | `0x0C0BB274` | `0x0C0BB328` | `+0xB4` |
| | `shift_row0` (key matrix row 0, bit 1) | `0x0C178694` | `0x0C179E58` | `+0x17C4` |
