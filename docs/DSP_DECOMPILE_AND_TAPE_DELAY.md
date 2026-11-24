# Korg ESX-1 / ESX-1 SD – DSP Decompilation (`uPD77213`) & Tape Delay Proof of Concept

Technical documentation for the complete decompilation of the DSP firmware ([`ESX0102D.BDS`](../factory-firmware-sd/ESX0102D.BDS)), the lossless uPD77213 assembler toolchain ([`dsp-src/`](../dsp-src/)), real-silicon pipeline rules, and the **Vintage Tape Delay** proof of concept in the **RingMod** FX slot.

---

## 1. Container Layout of `ESX0102D.BDS` (960 KiB = `0xF0000` bytes)

The DSP firmware is **bit-for-bit identical** between the original SmartMedia ESX-1 and the ESX-1 SD (`01.03.01`) (SHA-256: `16976c73a8e0fe3b9f5bbf9591297355184751d7928d09c0c7487f6e92f6ab86`).

| Region | Offset | Size | Description |
|---|---|---:|---|
| **Copy 0** | `0x00000..0x6FFFF` | 448 KiB | 80-byte header (`KORG`, PID `0x71`, `"BDS\0"`, `"01020000"`), IRAM, XRAM, YRAM, checksum fixup at `0x6FFFC` |
| **Gap** | `0x70000..0x7FFFF` | 64 KiB | Random padding; combined with Copy 0: `wsum(0x00000..0x7FFFF) == 0x00000000` |
| **Copy 1** | `0x80000..0xEFFFF` | 448 KiB | Copy loaded by the ESX-1 at boot (differs from Copy 0 only at IRAM `0x029F..0x02A0`: `*x:0x38d0 = 0xb333`), fixup at `0xEFFFC` so `wsum(0x80000..0xEFFFF) == 0x00000000` |

### NEC uPD77213 Memory Map (44.1 kHz, ~2,177 cycles/sample)

- **IRAM (32-bit instructions stored as `(lo16_BE, hi16_BE)`):**
  - Loaded at **IRAM base `0x0200`** (`5,562` words = `0x0200..0x17B9`)
  - **Engine & voice/mixer pipeline:** `0x0200..0x0A93` (`2,196` words)
  - **Free IRAM code cave (100% zeros):** **`0x0A94..0x0FFF`** (**`1,388` free 32-bit instructions**)
  - **All 18 FX subroutines:** `0x1000..0x17B9` (`1,978` words)
- **XRAM (`0x0000..0x37FF`) & YRAM (`0x0000..0x37FF`):** `14,336` words each, initialized from `.BDS` payload (`+0x56E8` and `+0xC6E8`)
- **External Delay SRAM (128 Kwords = `0x00000..0x1FFFF`, 256 KiB):**
  - Accessed via `DPR = 0x3F` (`*x:0x38c1 = 0x3f`), bank register `*x:0x3844 = ((addr >> 12) + 0x18) & 0x18`, and Y-bus window `dp6 = 0x8000 + (addr & 0x7FFF)`.
  - **Exclusive per-slot allocation (pre-initialized in `X[dp0+61..62]`):**
    - **FX1 (`dp0 = 0x2500`):** `0x00000..0x09FFF` (`40,960` words ≈ `928 ms` @ 44.1 kHz)
    - **FX2 (`dp0 = 0x2540`):** `0x0A000..0x13FFF` (`40,960` words)
    - **FX3 (`dp0 = 0x2580`):** `0x14000..0x1DFFF` (`40,960` words)

---

## 2. Complete FX Dispatch Table (Verified Live in `emu-sx`)

Each audio sample, the DSP calls `FX1`, `FX2`, and `FX3` sequentially via IRAM function pointers in `*x:0x2600..0x2602` (`engine.dsp @ 0x05BF..0x05D7`):

| Slot | Func Pointer | Parameter Block (`dp0`) | 32-bit State (`dp3`/`dp7`) | Audio I/O (`dp4`, YRAM) |
|---|---|---|---|---|
| **FX1** | `*x:0x2600` | `X:0x2500..0x253F` | `X/Y:0x4027..0x4066` | `Y:0x2610..0x2613` (`inL, inR, outL, outR`) |
| **FX2** | `*x:0x2601` | `X:0x2540..0x257F` | `X/Y:0x4067..0x40A6` | `Y:0x2614..0x2617` (`inL, inR, outL, outR`) |
| **FX3** | `*x:0x2602` | `X:0x2580..0x25BF` | `X/Y:0x40A7..0x40E6` | `Y:0x2618..0x261B` (`inL, inR, outL, outR`) |

All 18 decompiled subroutines in [`dsp-src/src/`](../dsp-src/src/):

| IRAM Address | Size | File | Effect (Rotary Code) | Ext. SRAM |
|---|---:|---|---|---|
| `0x1000..0x1033` | 52w | [`fx_clear_ext.dsp`](../dsp-src/src/fx_clear_ext.dsp) | Clear FX state & external delay SRAM helper | Yes |
| `0x1034..0x1038` | 5w | [`fx_bypass.dsp`](../dsp-src/src/fx_bypass.dsp) | Bypass (`outL = inL, outR = inR`) | No |
| `0x1039..0x10F4` | 188w | [`fx_filter.dsp`](../dsp-src/src/fx_filter.dsp) | **HPF / LPF** Resonant Filter (Code `1` / `9`) | No |
| `0x10F5..0x1181` | 141w | [`fx_reverb.dsp`](../dsp-src/src/fx_reverb.dsp) | **Reverb** (Code `0`) | Yes |
| `0x1182..0x1231` | 176w | [`fx_dist.dsp`](../dsp-src/src/fx_dist.dsp) | **Dist** / Distortion (Code `7`) | No |
| `0x1232..0x127F` | 78w | [`fx_comp.dsp`](../dsp-src/src/fx_comp.dsp) | **Comp** / Compressor (Code `15`) | No |
| `0x1280..0x1295` | 22w | [`fx_delay_io.dsp`](../dsp-src/src/fx_delay_io.dsp) | Delay bus I/O helper | No |
| `0x1296..0x1343` | 174w | [`fx_talkmod.dsp`](../dsp-src/src/fx_talkmod.dsp) | **TalkMod** (Code `3`) | No |
| `0x1344..0x1361` | 30w | [`fx_bpmdelay.dsp`](../dsp-src/src/fx_bpmdelay.dsp) | **BPMDelay** (Code `8`) | No* |
| `0x1362..0x13D9` | 120w | [`fx_shortdly.dsp`](../dsp-src/src/fx_shortdly.dsp) | **ShortDly** (Code `12`) | Yes |
| `0x13DA..0x1445` | 108w | [`fx_eq.dsp`](../dsp-src/src/fx_eq.dsp) | **EQ** (Code `13`) | No |
| **`0x1446..0x1483`** | **62w** | [`fx_ringmod.dsp`](../dsp-src/src/fx_ringmod.dsp) | **RingMod** (Code `2`) → **replaced by Tape Delay** | No → **Yes** |
| `0x1484..0x1537` | 180w | [`fx_phaser.dsp`](../dsp-src/src/fx_phaser.dsp) | **Phaser** (Code `10`) | No |
| `0x1538..0x15CC` | 149w | [`fx_choflg.dsp`](../dsp-src/src/fx_choflg.dsp) | **Cho/Flg** (Code `14`) | Yes |
| `0x15CD..0x165C` | 144w | [`fx_moddelay.dsp`](../dsp-src/src/fx_moddelay.dsp) | **ModDelay** (Code `4`) | Yes |
| `0x165D..0x16EB` | 143w | [`fx_grainsft.dsp`](../dsp-src/src/fx_grainsft.dsp) | **GrainSft** (Code `6`) | Yes |
| `0x16EC..0x177C` | 145w | [`fx_pitchsft.dsp`](../dsp-src/src/fx_pitchsft.dsp) | **PitchSft** (Code `11`) | Yes |
| `0x177D..0x17B9` | 61w | [`fx_deci.dsp`](../dsp-src/src/fx_deci.dsp) | **Deci** / Decimator (Code `5`) | No |

---

## 3. Real-Silicon NEC uPD77213 Pipeline Rules (Critical for Hardware!)

Auditing all 5,562 factory instructions in `ESX0102D.BDS` (and testing on real ESX-1 SD silicon, unlike the zero-latency emulator) revealed strict hardware rules that custom DSP code **must** obey:

1. **Pointer Load Latency (`dpN = ...` → `*dpN`):** Minimum gap **`>= 2`** (at least 1 instruction or `nop` between loading `dpN` and dereferencing `*dpN`).
2. **External SRAM Bank Settle (`*x:0x3844 = ...` → `*dp6`):** Minimum gap **`>= 5`**.
3. **External Window Enable (`*x:0x38c1 = 0x3f` → `*dp6`):** Minimum gap **`>= 9`**.
4. **Factory-Verified Opcodes & Shift Immediates Only:**
   - Avoid unverified opcodes absent from factory firmware (such as `OPS2` opcode 10 `put`; use `rD = rA add 0x0000`).
   - Only use shift immediates verified on real silicon: `sll {1, 2, 3, 4, 5, 7, 8, 15, 16}`, `sra {1, 16}`, `srl {12}` (shifts `> 16` overflow the 5-bit immediate shift field!).
5. **External SRAM Write & Hardware `loop` End:** Write to external SRAM via `*dp6 = rXl` (matching factory `fx_clear_ext @ 0x102C`) and place a pure ALU instruction — never `*dp6` — on the last instruction of a hardware `loop`.

---

## 4. Tape Delay Proof of Concept ([`tape_delay.dsp`](../dsp-src/patches/tape_delay.dsp))

The Tape Delay runs independently of `ESX0103N.BSS` by reusing the SH-3 parameter block already sent for RingMod (and `fw-src-sd/newtribe/fxnames.s` optionally renames the LCD labels to `TapeDly` / `TapeTime`):

- **EDIT 1 (`TapeTime` / `OSCFreq.` → `X[dp0+1]`, `0x0000..0x1FFF`):** Delay time `256..24,829` samples (**`5.8 ms .. 563 ms`** @ 44.1 kHz) smoothed via `msub`/`madd` (`~5.8 ms` capstan inertia for smooth analog pitch glide).
- **EDIT 2 (`Balance` → `X[dp0+12]`, `0x0000..0x7FFF`):** Feedback (`0% .. 87.5%`) & wet mix (`0% .. 87.5%`). `EDIT 2 = 0` gives clean dry bypass.

### DSP Signal Flow (187 words in IRAM cave `0x0A94..0x0B4D`, hook `0x1446: jmp tape_delay`)

1. **Auto-Init & Click-Free Buffer Clear:** On first entry or after an FX switch (`X[state+0] != 0x5444`), clears its own `32,768`-sample (`0x8000`) circular buffer in progressive 16-word chunks (`~46 ms` dry pass-through) so zero stale reverb/delay audio leaks in.
2. **Fractional Interpolation + Wow/Flutter LFO:** A signed 32-bit triangle LFO (`~1.35 Hz`, `±8.0` samples, matching factory `fx_moddelay @ 0x15E8..0x15E9`) modulates the `Q16.16` read delay; two adjacent external SRAM samples are linearly interpolated via `msub`/`madd`.
3. **Warm Magnetic Tape Feedback Path:**
   - **1-pole LP damping filter (`~2.85 kHz`, `alpha = 0x3400`):** Progressive high-frequency warmth on every repeat.
   - **1-pole DC blocker (`~13.7 Hz`, `alpha = 0x0040`):** Prevents any DC offset accumulation at high feedback.
   - **Unity-gain soft cubic saturation (`sat(x) = x - 0.125 * x^3`):** Gentle odd-harmonic compression on peaks without runaway self-oscillation.
4. **Stereo Output:** Preserves dry stereo (`inL`, `inR`) and adds the warm tape delay return cleanly to both channels.

---

## 5. Emulator Verification ([`test_tape_delay.py`](../dsp-src/test_tape_delay.py))

Verified on the native `emu-sx` SH-3 + uPD77213 core (Drum Part 1 `D1` routed to `FX1`):

| Measurement (`D1` kick, `EDIT1=480` ≈ `269.1 ms`, `EDIT2=860` ≈ `73%`) | Stock RingMod | Newtribe Tape Delay |
|---|---:|---:|
| **Echo 0 (`0 ms`, dry hit)** AC peak / HF ratio | `10,991` / `0.411` | `27,728` / `0.519` |
| **Echo 1 (`269.1 ms`)** AC peak / HF ratio | `9,454` *(D1 tail)* / `0.419` | `33,586` / `0.341` |
| **Echo 2 (`549.0 ms`)** AC peak / AC RMS / HF ratio | **`0` / `0.0`** *(silent)* | **`27,980` / `7,812.1` / `0.125`** |
| **Echo 3 (`818.0 ms`)** AC peak / AC RMS / HF ratio | **`0` / `0.0`** | **`19,770` / `5,794.8` / `0.108`** |
| **Echo 4 (`1087.1 ms`)** AC peak / AC RMS | **`0` / `0.0`** | **`14,867` / `4,467.3`** |
| **Dry Bypass (`EDIT2 = 0`, tail >360 ms)** AC RMS / peak | — | **`0.0` / `0`** |
| **New unimpl DSP accesses / SH-3 illegal ops / silicon audit** | `0` / `0` / — | **`0` / `0` / `PASS`** |

---

## 6. Safe `.BDS` Flashing on a Real ESX-1 SD

Verified from `BFS 01.03.01` disassembly (`Case 5 @ 0xA0002552` → `0x0C00B8B2` → loader `0x0C002B6C`):

- **Key combination:** Hold **`PATTERN + GLOBAL`** while powering on → LCD displays **`DSPVerUp`**.
- **Bootloader checks:**
  1. Finds a single `*.BDS` file in the SD card root of exact size **`983,040` bytes (`0x0F0000`)**.
  2. Loads it to `0x0C800000` and verifies 32-bit big-endian word sum **`== 0x00000000`** (`0x0C00AC26`).
  3. **No version lock (`SameVer.`):** Stock and custom `.BDS` images can be flashed back and forth freely.
  4. Writes 480 pages (960 KiB) into NAND `0x200000..0x2EFFFF`, reads them back (`0x0C002BE6`), and re-verifies word sum `0x00000000`.
- **Safety:** Neither the NOR bootloader (`BFS`, `IC15`), nor N-Sys (`ESX0103N.BSS`), nor `TUBECALIBDATA` is modified. Revert anytime with [`factory-firmware-sd/ESX0102D.BDS`](../factory-firmware-sd/ESX0102D.BDS) using **`PATTERN + GLOBAL`**.
