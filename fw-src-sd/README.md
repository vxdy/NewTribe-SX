# fw-src-sd – Reassemblable Source & Newtribe Port for Korg ESX-1 SD (`01.03.01`)

Dedicated lossless source and build environment for the **Korg Electribe SX-1 SD** (`KLM-302x`, Product ID `0xF1`, based on `factory-firmware-sd/ESX0103N.BSS`), sharing the Python SH-3 toolchain from [`../fw-src-sm/tools/`](../fw-src-sm/tools/).

The original SmartMedia `01.02` build tree in [`../fw-src-sm/`](../fw-src-sm/) remains untouched.

## Building

**1. Vanilla roundtrip (must be `IDENTICAL` to `factory-firmware-sd/ESX0103N.BSS`):**
```powershell
python fw-src-sm/tools/build.py `
  --src fw-src-sd/src `
  --header fw-src-sd/header.json `
  --out fw-src-sd/build/ESX0103N_vanilla.BSS `
  --map fw-src-sd/build/fw_vanilla.map `
  --no-newtribe `
  --ref factory-firmware-sd/ESX0103N.BSS
```

**2. Newtribe Custom Firmware (`01.03.02`, Product ID `0xF1`, word sum `0x00000000`):**
```powershell
python build.py sd
```

## Emulator Test (Real `BFS 01.03.01` + `ESX0103N.BSS` + `BDS 01.02.00`)

```powershell
python fw-src-sd/emutest_sd.py release/esx1-sd/ESX0103N.BSS
```

Automatically verifies:
1. Container header (`KORG`, Product ID `0xF1`, `BSS `, 32-bit BE word sum `0x00000000`)
2. Real boot from `BFS 01.03.01` (`esx1sd_bfs_512k.bin`) → loads `ESX0103N.BSS` to `0x0C080000` → starts `0x0C081000`
3. Newtribe splash screen (bold 8-char `Newtribe` CGRAM logo on line 1 + smooth 6-char progress bar `..  0%` → `##100%` on line 2, icon cells `14..15` blank)
4. SDRAM integrity & `0` illegal SH-3 instructions
5. `GLOBAL` menu: Page 8 `Newtrb I` / `0.0.1` and Page 9 `ShiftMut` / `Off` ↔ `On` via the `VALUE` encoder
6. **Persistence test (`settings.s` @ `0x0C2D0058..0x0C2D005F`):** `GLOBAL -> WRITE` (`GloblWr? -> Yes`) → NAND write → **cold reboot** → `ShiftMut` remains `On` and the live mute hook on `0x0C17BB6A` takes effect immediately!

## Flashing on a Real ESX-1 SD

See [`../docs/ESX1SD_DEBRICKING_PI.md`](../docs/ESX1SD_DEBRICKING_PI.md): place `release/esx1-sd/ESX0103N.BSS` alone in the root of a FAT SD card and power on while holding **`PATTERN` + `STEP EDIT`** (`ND VerUp`).
