# Korg Electribe SX (ESX-1, OS 1.02) Settings Format

This document describes the exact memory layout, fields, load/save paths, integrity checks, and unused bytes of the **Global Settings** on the Korg Electribe SX (OS 1.02; the same `0x0C2D0000..0x0C2D01FF` layout is used on the ESX-1 SD OS 1.03.01).

All findings come directly from:
- the disassembly of the factory firmware (`fw-src-sm/src/part_*.s`, `factory-firmware-sm/ESX0102N.BSS`),
- the factory data images (`test-data/factory.esx` and `emu-sx/out_nand_factory.bin`),
- direct measurements in the emulator (`emu-sx/rmachine.py` with `out_flash.bin`, `out_nand.bin`, and `out_nand_factory.bin`).

---

## 1. Overview and Memory Map

The ESX-1 keeps all user data in SDRAM starting at **`0x0C2D0000`**. The first **512 bytes (`0x000..0x1FF`)** contain the file header, all persistent Global parameters, the Pattern Set, and trailing sector padding.

This 512-byte layout is **1:1 identical** in three places:

1. **SDRAM (runtime):** `0x0C2D0000 .. 0x0C2D01FF` (512 bytes)
2. **Internal NAND (32 MiB, SmartMedia format):** **Logical Block (LBA) 191**, sector `0x17E0` (6112), logical byte offset `0x002FC000`, page 0 of a 16 KiB block (32 pages × 512 bytes + 16 bytes spare each)
3. **SmartMedia / SD Card (`.ESX` / `.PSG`):** file offset `0x000000 .. 0x0001FF` (only difference during normal operation: the 8-byte filename at `0x18..0x1F` is zeroed when saving to a card)

### Position in the Overall ESX-1 Memory Map

| Region | SDRAM Address | Size | `.ESX` Offset | Internal NAND (LBA / Sector / Byte Offset) |
|---|---|---|---|---|
| System firmware (`ESX0102N.BSS`) | `0x0C080000 .. 0x0C27FFFF` | 2 MiB | – | LBA 0..127 (sector `0x0000..0x0FFF`) |
| DSP firmware (`ESX0102D.BDS`) | loaded via host port | 960 KiB | – | LBA 128..190 (sector `0x1000..0x17DF`) |
| **Header + Global + Pattern Set + Padding** | **`0x0C2D0000 .. 0x0C2D01FF`** | **512 B (`0x200`)** | **`0x000000`** | **LBA 191 (sector `0x17E0`, `0x2FC000`, 16 KiB block)** |
| 256 Patterns (4,280 B = `0x10B8` each) | `0x0C2D0200 .. 0x0C3DB9FF` | 1,095,680 B | `0x000200` | LBA 192..319 (sector `0x1800..0x27FF`, `0x300000`; 2 patterns per 16 KiB block at `+0x0000` and `+0x2000`) |
| 64 Song Headers (528 B = `0x210` each) | `0x0C400000 .. 0x0C4083FF` | 33,792 B (`0x8400`) | `0x130000` | LBA 320..323 (sector `0x2800..0x287F`, `0x500000`) |
| Song Events (20,000 × 8 B) | `0x0C408400 .. 0x0C42F4FF` | 160,000 B (`0x27100`) | `0x138400` | LBA 324.. (sector `0x2880..`, `0x510000`) |
| Sample Headers (`"BPS "`, Mono/Stereo) | `0x0C480000 ..` | `0x4200`+ | `0x1B0000` | LBA 384.. (sector `0x3000`, `0x600000`) |
| Sample PCM Data | via `func_0C095D5E` | up to 24 MiB | `0x250000` | LBA 448.. (sector `0x3800`, `0x700000`) |

---

## 2. Complete Byte-by-Byte Layout (`0x0C2D0000 .. 0x0C2D01FF`)

### High-Level Partitioning of the 512 Bytes

| Offset | SDRAM Address | Size | Contents | In SysEx Global Dump (192 B)? | In Card-Save Backup (224 B)? |
|---|---|---|---|---|---|
| `0x000 .. 0x01F` | `0x0C2D0000 .. 0x0C2D001F` | 32 B | File header & active filename | No | Yes |
| `0x020 .. 0x05F` | `0x0C2D0020 .. 0x0C2D005F` | 64 B | Global parameters (incl. MIDI tables) | **Yes** | **Yes** |
| `0x060 .. 0x0DF` | `0x0C2D0060 .. 0x0C2D00DF` | 128 B | Pattern Set (8 banks × 16 step keys) | **Yes** | **Yes** |
| `0x0E0 .. 0x1FF` | `0x0C2D00E0 .. 0x0C2D01FF` | 288 B | Unused sector padding (`0x00`) | No | No |

---

### 2.1 Header (`0x0C2D0000 .. 0x0C2D001F`, 32 Bytes)

| Offset | SDRAM | Size | Value in `factory.esx` | Value in `out_nand_factory.bin` | Meaning |
|---|---|---|---|---|---|
| `0x00..0x03` | `0x0C2D0000` | 4 B | `4B 4F 52 47` (`"KORG"`) | identical | Manufacturer ID |
| `0x04..0x07` | `0x0C2D0004` | 4 B | `00 00 00 71` | identical | ESX-1 device/product ID (`0x71`, big-endian) |
| `0x08..0x0B` | `0x0C2D0008` | 4 B | `45 53 58 00` (`"ESX\0"`) | identical | File type |
| `0x0C..0x0F` | `0x0C2D000C` | 4 B | `05 26 79 A4` | identical | Factory build tag/timestamp (not evaluated by firmware) |
| `0x10..0x17` | `0x0C2D0010` | 8 B | `00 01 00 00 00 00 00 00` | identical | Format version (`0x0001` at `0x10`) + zeros |
| `0x18..0x1F` | `0x0C2D0018` | 8 B | `00 00 00 00 00 00 00 00` | `46 41 43 54 4F 52 59 20` (`"FACTORY "`) | **Active filename** (ASCII, right-padded with spaces `0x20`) |

**Behavior of `0x0C2D0018..0x0C2D001F` (filename):**
- When loading an `.ESX` or `.PSG` file from card (`func_0C0A816A`), the 8-character filename is stored here (otherwise e.g. `"USER    "` from `str_0C0D7864` / `str_0C0D0C3C`).
- `func_0C0850BE` reads this field for display.
- When saving to card (`func_0C0A7FA8` / `func_0C0A808E`), `0x0C2D0018..0x0C2D001F` is temporarily zeroed so saved `.ESX`/`.PSG` files always contain 8 zero bytes, and then restored in RAM.
- During a full memory initialize (`func_0C0BCB8A`), the firmware saves these 32 bytes onto the stack, zeroes `0x0C2D0000..0x0C47FFFF` (`0x1B0000` bytes), and writes the 32 bytes back.

---

### 2.2 Global Parameters (`0x0C2D0020 .. 0x0C2D005F`, 64 Bytes)

All 64 bytes were audited against all 172 instruction accesses to `var_0C2D0020`, `var_0C2D0027`, `var_0C2D0029`, `var_0C2D002A`, `var_0C2D0036`, and `var_0C2D0037` in `fw-src-sm/src/part_*.s`.

| Offset (ESX) | Offset from `0x20` | SDRAM | Size | Name | Type / Range | ROM `0x0C0DADAC` | `factory.esx` | `out_nand_factory.bin` | Menu / Main Functions |
|---|---|---|---|---|---|---|---|---|---|
| `0x20` | `+0x00` | `0x0C2D0020` | 1 B | **Memory Protect** | `u8`: `0` = Off, `1` = On | `0x00` | `0x01` | `0x00` | GLOBAL page 6 (`Protect `): `func_0C0942A0`, `func_0C09C72E` |
| `0x21` | `+0x01` | `0x0C2D0021` | 1 B | **Unused / Reserved** | – (**0 references**) | `0x00` | `0x00` | `0x00` | never directly read/written |
| `0x22` | `+0x02` | `0x0C2D0022` | 1 B | **Arp Control** | `u8`: `0` = Normal, `1` = Revers | `0x00` | `0x00` | `0x00` | GLOBAL page 2 (`ArpCntrl`): `func_0C094130`, `func_0C09C5DA`, `func_0C081CF6` |
| `0x23` | `+0x03` | `0x0C2D0023` | 1 B | **Audio In Mode** | `u8`: `0` = L/Mono, `1` = Stereo | `0x00` | `0x01` | `0x01` | GLOBAL page 1 (`AudioIn `): `func_0C0940F4`, `func_0C09C596`, `func_0C0B1340` |
| `0x24` | `+0x04` | `0x0C2D0024` | 1 B | **MIDI Clock** | `u8`: `0` = Int, `1` = Ext, `2` = Auto | `0x00` | `0x00` | `0x00` | GLOBAL page 3 (`Clock   `): `func_0C09415E`, `func_0C09C61A`, `func_0C0B5C40` |
| `0x25` | `+0x05` | `0x0C2D0025` | 1 B | **MIDI Filter** | `u8` bitmask `0x00..0x0F` (see below) | `0x0F` | `0x0F` | `0x0F` | MIDI Util -> `Filter`: `func_0C0BF930` (subpage 0) |
| `0x26` | `+0x06` | `0x0C2D0026` | 1 B | **Pitch Bend Range** | `u8`: `0..24` (`-12..+12` semitones, see below) | `0x02` (`-10`) | `0x0E` (`+2`) | `0x0E` (`+2`) | MIDI Util -> `BndRng`: `func_0C0BF930` (subpage 3), `func_0C09329E` |
| `0x27` | `+0x07` | `0x0C2D0027` | 1 B | **MIDI Ch: Keyboard 1** | `u8`: `0..15` (Ch 1..16; also SysEx ID & PC) | `0x00` (Ch 1) | `0x00` (Ch 1) | `0x00` (Ch 1) | GLOBAL page 4 (`MIDI Ch `): `func_0C0941B2`, `func_0C09C674` |
| `0x28` | `+0x08` | `0x0C2D0028` | 1 B | **MIDI Ch: Keyboard 2** | `u8`: `0..15` (Ch 1..16) | `0x01` (Ch 2) | `0x01` (Ch 2) | `0x01` (Ch 2) | GLOBAL page 4 (`MIDI Ch `) |
| `0x29` | `+0x09` | `0x0C2D0029` | 1 B | **MIDI Ch: Drum / Stretch / Slice / Audio** | `u8`: `0..15` (Ch 1..16) | `0x09` (Ch 10) | `0x09` (Ch 10) | `0x09` (Ch 10) | GLOBAL page 4 (`MIDI Ch `) |
| `0x2A..0x36` | `+0x0A..+0x16` | `0x0C2D002A..0x0C2D0036` | 13 B | **MIDI Note Numbers** | 13 × 7-bit note number (`& 0x7F`, see below) | see Table 2.2.3 | see Table 2.2.3 | identical to `factory.esx` | MIDI Util -> `DrNote`: `func_0C0BF930` (subpage 1), `func_0C083DE6` |
| `0x37..0x57` | `+0x17..+0x37` | `0x0C2D0037..0x0C2D0057` | 33 B | **MIDI Control Change Map** | 33 × CC number (see below) | see Table 2.2.4 | identical to ROM | identical to ROM | MIDI Util -> `CCAsin`: `func_0C0BF930` (subpage 2), `func_0C0B53E2`, `func_0C0B5B18` |
| `0x58..0x5F` | `+0x38..+0x3F` | `0x0C2D0058..0x0C2D005F` | 8 B | **Unused / Reserved** (used by Newtribe persistent settings) | – (**0 stock references**) | `00 × 8` | `00 × 8` | `00 × 8` | never read/written by stock firmware; used by `newtribe/settings.s` |

---

#### 2.2.1 Detail: MIDI Filter (`0x0C2D0025`, Offset `0x25`)

Bitmask in the lower 4 bits (`0x00..0x0F`, clamped in `func_0C0BF930`). A set bit (`1`) means **enabled / passed through (`o`)**, a cleared bit (`0`) means **filtered (`x`)**. The LCD shows `"PCEN    "` (`str_0C0DFEB0`) on the top row and the 4-character string from `dat_0C0DB0F0` (`"xxxx"` through `"oooo"`) on the bottom row:

| Bit | Mask | Display Column (`PCEN`) | Meaning | Checked in Firmware Routines |
|---|---|---|---|---|
| Bit 3 | `0x08` | `P` (column 0, left) | Program Change & Song Select | `func_0C0B4440`, `func_0C0B4518`, `func_0C0B4568`, `loc_0C0B46F8`, `func_0C0B3DC8`, `func_0C0B405A` |
| Bit 2 | `0x04` | `C` (column 1) | Control Change, NRPN & Pitch Bend | `func_0C0B45A0`, `func_0C0B468C`, `func_0C0B5202`, `func_0C0B5260`, `func_0C0B5338`, `func_0C0B53E2` |
| Bit 1 | `0x02` | `E` (column 2) | System Exclusive (SysEx) | `func_0C0A4A54` |
| Bit 0 | `0x01` | `N` (column 3, right) | Note On / Note Off | `func_0C0B43FA` (TX), `func_0C0B4806`, `func_0C0B4846` (RX) |

Default value: `0x0F` (`oooo`, all message types enabled).

---

#### 2.2.2 Detail: Pitch Bend Range (`0x0C2D0026`, Offset `0x26`)

- Stored as an unsigned byte `val` in the range **`0 .. 24`** (`-12 .. +12` semitones via `semitones = val - 12`).
- Values `> 24` are automatically reset to `12` (`0` semitones) in the menu (`loc_0C0BF990`).
- Evaluated in `func_0C09329E`: `(bend14 - 8192) * (val - 12) / 32`.
- `factory.esx` / `out_nand_factory.bin`: `0x0E` = `14` (`+2` semitones). The unused ROM table `0x0C0DADAC` has `0x02` (`-10`).

---

#### 2.2.3 Detail: MIDI Note Numbers (`0x0C2D002A .. 0x0C2D0036`, 13 Bytes)

All 13 bytes apply to the Drum MIDI channel (`0x0C2D0029`). The firmware always masks reads with `and #0x7F` (bit 7 is ignored). The mapping to internal part numbers (`0..8` = Drum 1..7B, `9..10` = Keyboard 1..2 skipped, `11..12` = Stretch 1..2, `13` = Slice, `14` = Audio In) is hardcoded in `func_0C083DE6`, `func_0C083F08`, and `func_0C0BAE42`; the editor (`func_0C0BF930`) copies the 13 bytes into scratch RAM `var_0C15069C`.

| Index | Offset (ESX) | SDRAM | Part (Display Label) | Internal Part Index | ROM `0x0C0DADAC` | `factory.esx` / NAND |
|---|---|---|---|---|---|---|
| 0 | `0x2A` | `0x0C2D002A` | `Drum1 ` | 0 | `0x3C` (60, C4) | `0x24` (36, C2) |
| 1 | `0x2B` | `0x0C2D002B` | `Drum2 ` | 1 | `0x3E` (62, D4) | `0x26` (38, D2) |
| 2 | `0x2C` | `0x0C2D002C` | `Drum3 ` | 2 | `0x40` (64, E4) | `0x28` (40, E2) |
| 3 | `0x2D` | `0x0C2D002D` | `Drum4 ` | 3 | `0x41` (65, F4) | `0x29` (41, F2) |
| 4 | `0x2E` | `0x0C2D002E` | `Drum5 ` | 4 | `0x43` (67, G4) | `0x2B` (43, G2) |
| 5 | `0x2F` | `0x0C2D002F` | `Drum6A` | 5 | `0x42` (66, F#4) | `0x2A` (42, F#2) |
| 6 | `0x30` | `0x0C2D0030` | `Drum6B` | 6 | `0x46` (70, A#4) | `0x2E` (46, A#2) |
| 7 | `0x31` | `0x0C2D0031` | `Drum7A` | 7 | `0x49` (73, C#5) | `0x31` (49, C#3) |
| 8 | `0x32` | `0x0C2D0032` | `Drum7B` | 8 | `0x4B` (75, D#5) | `0x33` (51, D#3) |
| 9 | `0x33` | `0x0C2D0033` | `Strch1` | 11 | `0x45` (69, A4) | `0x09` (9, A-1) |
| 10 | `0x34` | `0x0C2D0034` | `Strch2` | 12 | `0x47` (71, B4) | `0x0A` (10, A#-1) |
| 11 | `0x35` | `0x0C2D0035` | `Slice ` | 13 | `0x48` (72, C5) | `0x0B` (11, B-1) |
| 12 | `0x36` | `0x0C2D0036` | `Audio ` | 14 | `0x5A` (90, F#6) | `0x0C` (12, C0) |

---

#### 2.2.4 Detail: MIDI Control Change Map (`0x0C2D0037 .. 0x0C2D0057`, 33 Bytes)

The 33 display labels come in this exact order from pointer table `dat_0C0DB130` (displayed by `func_0C0B2836`, edited via scratch RAM `var_0C1506A9` in `func_0C0BF930`).

- **Indices `0..19`:** Part parameters, evaluated on both Keyboard channels (`0x0C2D0027` and `0x0C2D0028`, mapped via `dat_0C0DBA92` in `func_0C0B5B18`).
- **Indices `20..32`:** Global FX/Chain parameters, evaluated exclusively on Keyboard channel 1 (`0x0C2D0027`).
- **Allowed CC numbers in the menu (`func_0C0B5BD0` / `dat_0C0DBACE`):** `1..5`, `7..31`, `33..37`, `39..95` (92 valid values; reserved MIDI CCs `0` Bank Select MSB, `6` Data Entry MSB, `32` Bank Select LSB, `38` Data Entry LSB, and `96..127` RPN/NRPN/Channel Mode are excluded).
- Default values are **identical** across ROM `0x0C0DADAC`, `factory.esx`, and `out_nand_factory.bin`.

| Index | Offset (ESX) | SDRAM | Display Label (`dat_0C0DB130`) | Scope | Default CC (Hex / Dec) |
|---|---|---|---|---|---|
| 0 | `0x37` | `0x0C2D0037` | `ModSpd` | Part (Kbd1/2) | `0x59` (CC 89) |
| 1 | `0x38` | `0x0C2D0038` | `ModDpt` | Part (Kbd1/2) | `0x5A` (CC 90) |
| 2 | `0x39` | `0x0C2D0039` | `ModTyp` | Part (Kbd1/2) | `0x57` (CC 87) |
| 3 | `0x3A` | `0x0C2D003A` | `ModDst` | Part (Kbd1/2) | `0x58` (CC 88) |
| 4 | `0x3B` | `0x0C2D003B` | `ModBPM` | Part (Kbd1/2) | `0x52` (CC 82) |
| 5 | `0x3C` | `0x0C2D003C` | `Cutoff` | Part (Kbd1/2) | `0x4A` (CC 74) |
| 6 | `0x3D` | `0x0C2D003D` | `Reso  ` | Part (Kbd1/2) | `0x47` (CC 71) |
| 7 | `0x3E` | `0x0C2D003E` | `EGInt ` | Part (Kbd1/2) | `0x4F` (CC 79) |
| 8 | `0x3F` | `0x0C2D003F` | `FltTyp` | Part (Kbd1/2) | `0x53` (CC 83) |
| 9 | `0x40` | `0x0C2D0040` | `Pch/Gl` | Part (Kbd1/2) | `0x05` (CC 5) |
| 10 | `0x41` | `0x0C2D0041` | `Pan   ` | Part (Kbd1/2) | `0x0A` (CC 10) |
| 11 | `0x42` | `0x0C2D0042` | `EGTime` | Part (Kbd1/2) | `0x4B` (CC 75) |
| 12 | `0x43` | `0x0C2D0043` | `Level ` | Part (Kbd1/2) | `0x07` (CC 7) |
| 13 | `0x44` | `0x0C2D0044` | `Start ` | Part (Kbd1/2) | `0x12` (CC 18) |
| 14 | `0x45` | `0x0C2D0045` | `AmpEG ` | Part (Kbd1/2) | `0x56` (CC 86) |
| 15 | `0x46` | `0x0C2D0046` | `Roll  ` | Part (Kbd1/2) | `0x55` (CC 85) |
| 16 | `0x47` | `0x0C2D0047` | `Revers` | Part (Kbd1/2) | `0x13` (CC 19) |
| 17 | `0x48` | `0x0C2D0048` | `FxSend` | Part (Kbd1/2) | `0x5B` (CC 91) |
| 18 | `0x49` | `0x0C2D0049` | `FxSel ` | Part (Kbd1/2) | `0x51` (CC 81) |
| 19 | `0x4A` | `0x0C2D004A` | `PrtMot` | Part (Kbd1/2) | `0x50` (CC 80) |
| 20 | `0x4B` | `0x0C2D004B` | `Fx1Typ` | Global (Kbd1) | `0x0C` (CC 12) |
| 21 | `0x4C` | `0x0C2D004C` | `Fx1Ed1` | Global (Kbd1) | `0x5C` (CC 92) |
| 22 | `0x4D` | `0x0C2D004D` | `Fx1Ed2` | Global (Kbd1) | `0x5D` (CC 93) |
| 23 | `0x4E` | `0x0C2D004E` | `Fx1Mot` | Global (Kbd1) | `0x14` (CC 20) |
| 24 | `0x4F` | `0x0C2D004F` | `Fx2Typ` | Global (Kbd1) | `0x0D` (CC 13) |
| 25 | `0x50` | `0x0C2D0050` | `Fx2Ed1` | Global (Kbd1) | `0x5E` (CC 94) |
| 26 | `0x51` | `0x0C2D0051` | `Fx2Ed2` | Global (Kbd1) | `0x5F` (CC 95) |
| 27 | `0x52` | `0x0C2D0052` | `Fx2Mot` | Global (Kbd1) | `0x15` (CC 21) |
| 28 | `0x53` | `0x0C2D0053` | `Fx3Typ` | Global (Kbd1) | `0x18` (CC 24) |
| 29 | `0x54` | `0x0C2D0054` | `Fx3Ed1` | Global (Kbd1) | `0x19` (CC 25) |
| 30 | `0x55` | `0x0C2D0055` | `Fx3Ed2` | Global (Kbd1) | `0x1A` (CC 26) |
| 31 | `0x56` | `0x0C2D0056` | `Fx3Mot` | Global (Kbd1) | `0x16` (CC 22) |
| 32 | `0x57` | `0x0C2D0057` | `Chain ` | Global (Kbd1) | `0x17` (CC 23) |

---

### 2.3 Pattern Set (`0x0C2D0060 .. 0x0C2D00DF`, 128 Bytes)

- Symbol: `var_0C2D0060`
- Structure: **8 banks × 16 step keys = 128 bytes** (`index = bank * 16 + key`).
- Value per byte: pattern number `0x00..0xFF` (`0..255`, corresponding to `A.01 .. D.64`; in `factory.esx` slot `0x13` holds `0xFF`, all other slots hold factory pattern numbers).
- Can be saved to NAND either standalone via `PtSetWr?` (`func_0C0B91EE`) or together with Global parameters via `GloblWr?` (`func_0C0B9184`).

---

### 2.4 Sector Padding (`0x0C2D00E0 .. 0x0C2D01FF`, 288 Bytes)

- **0 direct references** in the entire stock firmware.
- Consistently `0x00` in `factory.esx` and `out_nand_factory.bin`.
- Loaded at boot (sector `0x17E0` = 512 bytes) and written back on `GloblWr?` as well as when saving `.ESX`/`.PSG` files.
- Lies **outside** the 192-byte SysEx Global Dump (`0x0C2D0020..0x0C2D00DF`) and **outside** the 224-byte temporary backup buffer during Card Save (see Section 3.4).

---

### 2.5 GLOBAL Menu Pages **Not** Stored in `0x0C2D0000..0x0C2D01FF`

| GLOBAL Page | Display | Storage Location | Persistence |
|---|---|---|---|
| Page 0 | `Metronom` | `var_0C150600` (`func_0C0B9760` / `func_0C0B9766`) | **Volatile** (resets to `Off` on every reboot) |
| Page 5 | `Memory  ` | computed at runtime | Display only (free sample/memory space) |
| Page 7 (Custom) | `Newtrb I` | static (`newtribe/globalpage.s`) | Display only (custom firmware version) |

*(Note: Custom page 8 `ShiftMut` was initially volatile, and is now persisted in the reserved `0x0C2D0058..0x0C2D005F` block via `newtribe/settings.s`!)*

---

## 3. Load, Save, and Transfer Paths

### 3.1 System Boot

Call chain: `func_0C0CBB12` -> `func_0C0B1320` -> `func_0C0B91D4`

1. `func_0C0B91D4` calls the BFS NAND driver:
   ```text
   bfs_func_0C004960(sector = 0x17E0, count = 1, buf = 0x0C2D0000, dev = 1)
   ```
   Exactly **1 sector (512 bytes)** is read from internal NAND (LBA 191, page 0) into `0x0C2D0000..0x0C2D01FF`.
2. Next, `func_0C0B1360` applies the loaded hardware/engine parameters:
   - `MIDI Clock` (`0x0C2D0024`) via `func_0C0B5C40`
   - `Audio In Mode` (`0x0C2D0023`) via `func_0C0B1340`
3. **Behavior on empty/uninitialized NAND (LBA 191 absent):**
   The BFS driver returns **512 × `0xFF`** into `0x0C2D0000..0x0C2D01FF`. The firmware does **not** fall back to ROM defaults (directly verified in the emulator with `out_nand.bin`; see Section 5).

---

### 3.2 GLOBAL WRITE (`GloblWr? -> Yes`)

Call chain: `func_0C08BF4A` -> `func_0C0B9184`

```text
bfs_func_0C004AA4(sector = 0x17E0, count = 32, buf = 0x0C2D0000, dev = 1)
```

- Writes the entire **16 KiB erase block (32 sectors)** starting at SDRAM `0x0C2D0000` (`0x0C2D0000 .. 0x0C2D3FFF`) into internal NAND as **LBA 191**.
- **Important quirk:** Because the firmware passes `count = 32` starting at `0x0C2D0000`, pages `1..31` of block 191 in NAND end up holding the first 15.5 KiB of the immediately following Pattern memory (`0x0C2D0200 .. 0x0C2D3FFF`, starting with Pattern 0 `"House1  "`). Pages `1..31` of block 191 are **never** read back (`func_0C0B91D4` always reads `count = 1`, i.e., page 0 only; patterns themselves live in LBA 192..319).
- The BFS driver allocates a free physical NAND block, writes all 32 pages including SmartMedia spare bytes (LBA tag + ECC), and only then erases the previous physical block for LBA 191 (atomic update).

---

### 3.3 Pattern Set WRITE (`PtSetWr? -> Yes`)

Call chain: `func_0C08BFCC` -> `func_0C0B91EE` -> `func_0C0B8C1C(nand_off = 0x2FC060, len = 128, src = 0x0C2D0060)`

- `func_0C0B8C1C` performs a **Read-Modify-Write** on the affected 16 KiB block:
  1. Allocates a 16 KiB buffer and reads block 191 from NAND.
  2. Overwrites exclusively the **128 bytes at offset `+0x60`** (`0x2FC060..0x2FC0DF`) from `0x0C2D0060`.
  3. Writes the entire block back via `bfs_func_0C004AA4`.
- Unsaved RAM edits in `0x0C2D0020..0x0C2D005F` or `0x0C2D00E0..0x0C2D01FF` are **not** committed to NAND by `PtSetWr?`.

---

### 3.4 SmartMedia / SD Card Save & Load (`.ESX` / `.PSG`)

- **Save (`func_0C0A7FA8` for `.ESX`, `func_0C0A808E` for `.PSG`):**
  1. Saves **only the first 224 bytes (`0x0C2D0000 .. 0x0C2D00DF`)** into a temporary buffer.
  2. Reloads sector `0x17E0` (512 bytes) **fresh from NAND** via `func_0C0B91D4` into `0x0C2D0000` (so unsaved RAM edits in Global settings do not accidentally end up on the card).
  3. Zeroes `0x0C2D0018..0x0C2D001F` (filename).
  4. Writes the 512-byte block `0x0C2D0000..0x0C2D01FF` as the start of the `.ESX`/`.PSG` file.
  5. Restores **only the 224 saved bytes (`0x0C2D0000 .. 0x0C2D00DF`)** back into RAM.
  > **Warning (224-Byte Quirk):** Unsaved RAM values in `0x0C2D00E0 .. 0x0C2D01FF` are lost during a Card Save because step 2 overwrites them from NAND and step 5 does not restore them!

- **Load (`func_0C0A816A`, `func_0C0A8274`, `func_0C0A8316`):**
  1. Preserves the local `Memory Protect` byte (`0x0C2D0020`).
  2. Loads `0x000..0x1FF` from the file into `0x0C2D0000..0x0C2D01FF`.
  3. Writes the loaded 8-character filename into `0x0C2D0018..0x0C2D001F`.
  4. Restores the local `Memory Protect` byte (`0x0C2D0020`).
  5. Commits the loaded block into internal NAND (LBA 191) via `func_0C0B9184`.

---

### 3.5 MIDI SysEx Global Data Dump

- **Transmit (`loc_0C0A52A8`):**
  - Header: `F0 42 3g 71 51` (`g` = Keyboard 1 MIDI channel `0x0C2D0027 & 0x0F`, `0x71` = ESX-1, `0x51` = Global Data Dump).
  - Payload: exactly **192 bytes** (`0x0C2D0020 .. 0x0C2D00DF`, i.e., Global parameters + Pattern Set, **excluding** the 32-byte header and the 288-byte padding), packed in Korg 7-bit format (each 7 data bytes -> 1 MSB byte + 7 data bytes = 220 MIDI bytes, terminated by `F7`).
- **Receive (`func_0C0A54DC` -> `func_0C08B18A`):**
  - Unpacks 192 bytes.
  - Overwrites `0x0C2D0020 .. 0x0C2D00DF` **except** for the following locally protected fields, which are saved before overwriting and restored afterward:
    - `0x0C2D0020` (`Memory Protect`)
    - `0x0C2D0025` (`MIDI Filter`)
    - `0x0C2D0027 .. 0x0C2D0029` (all 3 `MIDI Channels`)
  - Unused bytes `0x0C2D0021` and `0x0C2D0058 .. 0x0C2D005F` are inside the 192-byte dump and **are overwritten** on SysEx receive.

---

### 3.6 Factory Init and Unused ROM Defaults

- **`func_0C0BCB8A`:** Saves the 32-byte header (`0x0C2D0000..0x0C2D001F`), zeroes `0x0C2D0000..0x0C47FFFF`, and writes the header back.
- **ROM default table `0x0C0DADAC` (192 bytes) & routine `0x0C0B1354`:**
  A 12-byte routine `bfs_memcpy(0x0C2D0020, 0x0C0DADAC, 192)` exists at `0x0C0B1354` (unreferenced code block in `fw-src-sm/src/part_0C0B11B4.s`). It has **no callers** anywhere in the BSS firmware (dead code from development; actual factory defaults are loaded into NAND via `factory.esx`).

---

## 4. Checksums and Integrity Protection

### Key Finding: No Application-Level Checksum

A complete audit of all read, write, card, and SysEx routines (`func_0C0B91D4`, `func_0C0B9184`, `func_0C0B91EE`, `func_0C0B8C1C`, `func_0C0A7FA8`, `func_0C0A808E`, `func_0C0A816A`, `loc_0C0A52A8`, `func_0C0A54DC`, `func_0C08B18A`) and live emulator write tests confirm:

- There is **no checksum, no CRC, and no word-sum** anywhere within the 512 bytes `0x0C2D0000 .. 0x0C2D01FF`.
- There is likewise **no checksum** over the 192-byte Global region in `.ESX`/`.PSG` files or in the SysEx Global Dump.
- *(Do not confuse this with the 32-bit word-sum `== 0` used exclusively by the firmware containers `ESX0101F.BFS`, `ESX0102N.BSS`, and `ESX0102D.BDS`.)*

### Hardware / Driver Integrity in NAND (SmartMedia SSFDC Spare Area)

The only integrity protection for stored settings is handled **automatically by the BFS NAND driver** (`bfs_func_0C004AA4` on write, `bfs_func_0C004960` on read) in the 16-byte spare area of each 512-byte page (verified against `emu-sx/smartmedia.py` and `emu-sx/out_nand_factory.bin`):

| Spare Byte(s) | Size | Contents | Example Block 191 Page 0 (`out_nand_factory.bin`) |
|---|---|---|---|
| `0 .. 3` | 4 B | Reserved (`0xFF`) | `FF FF FF FF` |
| `4` | 1 B | Data Status Flag (`0xFF` = valid) | `FF` |
| `5` | 1 B | Block Status Flag (`0xFF` = good) | `FF` |
| `6 .. 7` | 2 B | Logical Block Address (copy 1): `0x1000 \| (lba << 1) \| parity` | `11 7E` (LBA 191 = `0x0BF`) |
| `8 .. 10` | 3 B | SmartMedia ECC over **second 256 bytes** (`0x100..0x1FF`, byte 0/1 swapped) | `FF FF FF` (256 × `0x00`) |
| `11 .. 12` | 2 B | Logical Block Address (copy 2) | `11 7E` (LBA 191 = `0x0BF`) |
| `13 .. 15` | 3 B | SmartMedia ECC over **first 256 bytes** (`0x000..0x0FF`, byte 0/1 swapped) | `33 C0 33` (after changing `AudioIn`: `69 99 67`) |

---

## 5. Verification Against Factory Data and in the Emulator

### 5.1 Comparison: `test-data/factory.esx` vs. `emu-sx/out_nand_factory.bin` (LBA 191, Page 0)

Across all 512 bytes (`0x000..0x1FF`) there are exactly **9 byte differences**:
- `0x018 .. 0x01F`: `00 00 00 00 00 00 00 00` in `factory.esx` vs. `"FACTORY "` (`46 41 43 54 4F 52 59 20`) in NAND.
- `0x020` (`Memory Protect`): `0x01` in `factory.esx` vs. `0x00` in NAND (locally preserved on load).

All remaining 503 bytes are bit-identical.

### 5.2 Emulator Test A: Empty NAND (`out_nand.bin`, LBA 191 Absent)

- `out_nand.bin` contains no physical block with LBA 191 (`0x117E`).
- After booting in the emulator, the entire 512-byte window `0x0C2D0000 .. 0x0C2D01FF` in SDRAM is filled with **`0xFF`** (`512 × 0xFF`).

### 5.3 Emulator Test B: Factory NAND (`out_nand_factory.bin`) + `GLOBAL WRITE` + Cold Reboot

Run with `emu-sx/rmachine.py` (`out_flash.bin` + `out_nand_factory.bin`, `tmu.scale = 1`, purely in memory):

1. **Boot to main screen (`House1 / A.01`):** 256M instructions (2.7 s), 0 illegal instructions.
   - `SDRAM 0x0C2D0000..0x0C2D01FF` is 100 % identical to LBA 191 page 0 (physical block 230, spare `ffffffffffff117effffff117e33c033`).
   - `AudioIn` (`0x0C2D0023`) = `0x01` (`Stereo`).
2. **Edit & Save:** `GLOBAL` -> `DOWN` (`AudioIn / Stereo`) -> Encoder `-1` (`AudioIn / L/Mono`, RAM `0x0C2D0023 = 0x00`) -> `WRITE` (`GloblWr? / Yes`) -> `WRITE` (confirm).
3. **Inspect modified NAND image:**
   - LBA 191 (`0x117E`) was atomically moved from **physical block 230** to **physical block 189**; old block 230 was erased to `0xFF`.
   - Inside the 512-byte payload of page 0, **only a single byte** changed: `+0x023: 0x01 -> 0x00` (no checksum byte changed).
   - Inside the 16-byte spare area, the BFS driver automatically updated the lower-256-byte ECC (`33 c0 33` -> `69 99 67`).
4. **Cold boot of a fresh emulator instance using the modified NAND image:**
   - Boots to `House1 / A.01` in 256M instructions (2.9 s), 0 illegal instructions.
   - `AudioIn` (`0x0C2D0023`) reads back as `0x00` (`L/Mono`), and `SDRAM 0x0C2D0000..0x0C2D01FF` is again 100 % identical to LBA 191 page 0.

---

## 6. Suitability for Persistent Custom Firmware Settings (e.g., `ShiftMut`)

Three verified unused regions inside `0x0C2D0000 .. 0x0C2D01FF` are available for persistent Newtribe options:

| Candidate | Size | NAND Global Save/Load | `.ESX`/`.PSG` Save/Load | Survives 224-B Card-Save Backup (unsaved)? | SysEx Global Dump TX/RX | Assessment |
|---|---|---|---|---|---|---|
| **`0x0C2D0058 .. 0x0C2D005F`** | **8 bytes** | Yes | Yes | **Yes** | **Yes** (transmitted & overwritten on RX) | **Recommended** for compact custom settings with magic header |
| `0x0C2D0021` | 1 byte | Yes | Yes | Yes | Yes | Same properties, but only 1 byte available |
| `0x0C2D00E0 .. 0x0C2D01FF` | 288 bytes | Yes | Yes | **No** (overwritten from NAND on Card Save) | No (untouched by SysEx RX) | Suitable for larger data if saved explicitly via `GloblWr?`; check strict PC `.ESX` editors |

### Recommended Pattern for Safe Persistence (Implemented in `newtribe/settings.s`)

1. **Choose storage slot:** `0x0C2D0058 .. 0x0C2D005F` (8 unused bytes at the end of Global parameters).
   - Store a magic/version header (e.g., `0x58..0x59 = "NT"` (`0x4E, 0x54`), `0x5A = version`, `0x5B = flags` with bit 0 = `ShiftMut`).
2. **Enforce strict `0xFF` protection:**
   - On an empty/uninitialized NAND (`out_nand.bin`) or a device that has never run custom firmware, these bytes are `0xFF` or `0x00`.
   - Never treat `val != 0` as "On"! Require the exact magic header and valid version/flags; treat all other values (especially `0x00` and `0xFF`) as `Off`.
   - Normalize cleanly when modifying or writing.
3. **Save via standard firmware (`GloblWr?` / `func_0C0B9184`):**
   - Because `0x0C2D0058 .. 0x0C2D005F` lives inside the Global SDRAM block, standard **`GLOBAL -> WRITE -> GloblWr? Yes`** automatically persists it into NAND (LBA 191, with atomic block reallocation and automatic ECC by the BFS driver) with zero changes to the stock save path.
   - This avoids unnecessary flash wear on every encoder turn and matches the exact UX of all stock GLOBAL settings (`AudioIn`, `ArpCntrl`, `Clock`, `MIDI Ch`, `Protect`).
   - This persistence scheme is now implemented in `fw-src-sm/newtribe/settings.s` and `fw-src-sd/newtribe/settings.s` and verified across cold reboots in both `emutest.py` and `emutest_sd.py`.
