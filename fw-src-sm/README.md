# fw-src-sm - lossless, re-assemblable source of the Electribe SX (ESX-1) main firmware (OS 1.02)

Phase 1 of the "Newtribe" project: `factory-firmware-sm/ESX0102N.BSS` (SH7709 / SH-3 system firmware) is represented as
assembly sources (`src/*.s`) that **assemble back to the byte-identical file** with our own tool chain (no SH cross
toolchain needed).  Nothing in `factory-firmware-sm/` was touched.

```
python tools/build.py --ref ../factory-firmware-sm/ESX0102N.BSS
-> build: IDENTICAL to ../factory-firmware-sm/ESX0102N.BSS (sha256 68fab1b99c27bfdcf10edca3c3d6511032ab9025bd209ab4b34d1e56424b5326)
```

## 1. Container format of `ESX0102N.BSS` (measured, also in emulator)

| offset | content |
|---|---|
| 0x00 | `KORG` |
| 0x04 | u32 BE `0x00000071` (same value in BFS/BSS/BDS; nothing we found validates it) |
| 0x08 | file type `BSS ` (`BFS `, `BDS\0` for the other two files) |
| 0x0C | version `0102`, then `0000` (0x10..0x13); 0x14..0x1F zero |
| 0x20 | payload, 0x1FFFE0 bytes: the system image, **no compression, no encryption** |

* The file is exactly 2 MiB.  The **word sum of the whole file (32 bit big endian words, header included) is 0**; the
  updater of the boot flash rejects other files (`CkSumErr`).  There is no dedicated checksum field - the factory file
  has the correction in its **last word**, which lies in the RAM filler (see below) that nobody reads.  `bsspack`
  therefore recomputes `last_word = -(sum of the other words)`; for the unmodified payload this reproduces the factory
  bytes.  No other integrity check was found (images with changed code boot and play, see section 6).
* Update: the boot flash (BFS, never changed) reads the three files from the SmartMedia card (FAT12), `VerUp N` writes the
  BSS to the internal NAND as *payload followed by the 32 byte header*.  Normal boot: the BFS copies it into SDRAM:
  **payload -> 0x0C080000, header -> 0x0C27FFE0** (immediately behind the payload) and jumps to **0x0C081000**
  (payload offset 0x1000; first PC in the payload observed in the emulator after 21.8 M instructions).
  **VBR = 0x0C080000**: general exception vector = payload 0x100, TLB miss 0x400, interrupt 0x600 (the stubs are in the
  image).  Offsets 0x000..0x0FF contain two version words `00010002` (at 0 and 8) and zeros.
* The system also calls the boot flash library: the BFS image lives in SDRAM 0x0C000000..0x0C07FFFF (C runtime: memcpy,
  memset, division helpers, LCD/NAND/FAT drivers, key table 0x0C00A170, ...) at fixed addresses.  These calls and
  variables are plain absolute numbers in the image (`bfs_func_*`, `bfs_*` in `src/00_defs.s`).
* Image map (payload offset = address - 0x0C080000):

| address range | content |
|---|---|
| 0x0C080000-0x0C0810xx | version words, vector stubs (0x100 / 0x400 / 0x600), zero fill up to the entry at 0x0C081000 |
| 0x0C081000-0x0C0D06FC | code (main_entry, OS kernel, UI, sequencer, ...) with literal pools |
| 0x0C0D06FC-0x0C0E0F60 | read-only data: tables, strings (menu texts), pointer/function tables, task descriptor tables (0x0C0E0764..) |
| 0x0C0E08E8-0x0C0E0EB7 | initialised RAM-like variables inside the image (the only part of the image written at run time) |
| 0x0C0E0F60-0x0C0EBF58 | more code |
| 0x0C0EBF58-0x0C0ED9F0 | tables (lookup tables, ...) |
| **0x0C0ED9F0**-0x0C27FFE0 | **RAM filler**: 1.6 MB of random bytes that only exist because the BSS is a fixed 2 MiB file.  At run time this is the **RAM of the system** (the variables `var_*` start right at 0x0C0ED9F0; BSS is cleared by the start-up code; the interrupt table at 0x0C15038C, stacks, ... all sit in it, RAM continues beyond the file end) |

## 2. Tool chain (`tools/`, Python 3.10, capstone only used for cross checks)

| tool | purpose |
|---|---|
| `bsspack.py` | `unpack` / `pack` / `check` of the BSS container (header from `header.json`, last word checksum fix) |
| `shisa.py` | SH-3 instruction tables (160 encodings, all of SH7709: delay slots, banked ldc/stc, `shad/shld`, `mac`, `ldtlb`, `pref`, `sleep`, `trapa`, ...), checked against capstone for all 65536 opcodes |
| `shasm.py` | two pass assembler -> flat binary at absolute addresses |
| `shdis.py` | `layout.txt` + `symbols.txt` -> `src/*.s` (labels for every branch/call/literal/pointer target, `.long label` for in-image addresses) |
| `fwmap.py` | the code/data classifier -> `layout.txt` (static recursive descent + dynamic coverage, see 3) |
| `covrun.py`, `cov_core/` | dynamic coverage in the emulator (private copy of the Rust core with a coverage bitmap), writes `cov/*.cov` |
| `build.py` | `src/` -> payload -> `bsspack` -> `build/ESX0102N.BSS` (+ map, optional comparison with the factory file) |
| `emutest.py` | end-to-end emulator check: SmartMedia card with the BSS -> BFS updater (up+down, START) -> internal NAND -> normal boot -> SDRAM compared with the payload -> PLAY (audio) |
| `splashtest.py` | emulator proof of the Newtribe start-up screen: card update, LCD/CGRAM sampling during boot, frame list, PNG, checks (section 9.2) |
| `selftest.py`, `stats.py` | unit/consistency checks, statistics |
| `growtest.py`, `bootcheck.py`, `lockstep.py` | growth experiments (see 6) |

Regenerating everything (about 2 minutes, coverage files are kept in `cov/`):
```
python tools/fwmap.py            # cov/*.cov + overrides.txt (optional) -> layout.txt
python tools/shdis.py            # layout.txt + symbols.txt -> src/*.s, src/manifest.txt, src/00_defs.s, data/ram_pad.bin
python tools/build.py --ref ../factory-firmware-sm/ESX0102N.BSS
python tools/emutest.py build/ESX0102N.BSS     # needs emu-sx/target_fw (see below)
```
`symbols.txt` (`addr,name,comment[,kind]`) names functions, variables and on-chip registers; it survives regeneration.
`overrides.txt` (same line format as `layout.txt`, applied first) pins hand decisions (not needed so far).
To rebuild the coverage emulator core: `cd tools/cov_core; $env:CARGO_TARGET_DIR="..\..\..\emu-sx\target_fw";
cargo +1.98.1-x86_64-pc-windows-gnu build --release` (a copy of `emu-sx/core` plus `emu_cov_*`; the shared core was not modified).
`python tools/covrun.py boot|keys|menus|play|knobs|shift` records one scenario (boot to the pattern display; every key with
encoder turns; menu tours with cursor keys; play/record/step buttons/pattern change; all ADC channels; SHIFT/PATTERN-SET
combinations).

### Assembler syntax (shasm.py)
`label:`, `name = expr`, instructions as in the Hitachi manuals (`mov.l @(4,r1),r2`, `bt/s loc_X`, `ldc r0,r3_bank`, ...),
directives `.org addr[,fill]` `.align n[,fill[,unit]]` `.byte/.word/.long` `.ascii/.asciz` `.space n[,fill]`
`.incbin "f"[,off,len]` `.include` `.pool/.ltorg` `.assert` `.equ`, and for the Newtribe overlay (section 9) `.redirect old,new` and
`.copylong src,n` and `.patchlong addr,new,old` (section 9.3).  PC relative operands name the **address** of the
literal (`mov.l @(lit_0C081040,pc),r1`; the assembler computes the displacement); `mov.l =expr,r1` / `mov.w =expr,r1` collect
literals automatically into the next `.pool` (identical entries shared, word entries first, long entries aligned).
Errors are explicit, e.g. `long literal at 0x17D2 is too far (+1998 bytes) from instruction at 0x1000 (pc-relative range
0..1020 bytes ...); place a .pool nearer or fix alignment`, `branch target ... out of range`, `.org ... goes backwards`.
Expressions: `+ - * / % << >> & | ^ ~`, labels, `.`.

## 3. How the code/data map was made (fwmap.py)
1. **Dynamic**: 6 emulator scenarios (boot, all keys, menus, play, knobs, shift) mark executed instruction starts, 8/16/32 bit
   data reads, writes, jsr/bsr/bsrf and jmp targets: 71180 distinct instructions (43.7 % of all code) were really executed,
   784 functions seen as call targets.  Delay slots of executed branches are kept with their branch.
2. **Static**: recursive descent from all executed instructions and the exception vectors/entry, following branches, delay
   slots, `jsr/jmp @Rn` with the register loaded from a literal pool in the same block, `mova + mov.w @(r0,Rn) + braf` switch
   tables (5 found, bounded by the first target), literal pools from `mov.l/mov.w @(disp,pc)` (placed as `llit`/`wlit`).
3. **Pointer tables**: runs of in-image addresses in unclassified bytes are tried as function tables ("trial descent": accepted only if the
   whole reachable flow is clean - no illegal opcode, no overlap with data/literals, no branch out of the image); 90 more
   functions were found by function prologue scans with the same trial.
4. **Data**: strings (NUL terminated or fixed width), zero runs, pointer runs, 32/16 bit data from read evidence, bytes.
   Isolated 32 bit values that point exactly to a function entry / string / referenced table (task descriptors, handler
   structs) are converted to `.long label` too - found by a growth test, see 6.
Result (`python tools/stats.py`): image 449 008 bytes = code 325 570 (72.5 %, 162 785 instructions), literal pool longs 44 524,
byte data 45 269, pointer runs 11 096, zero fill 9 756, strings 7 689, long data 3 952, word data 760, switch tables 200, word literals 192;
3 458 functions (jsr 1241, bsr 909, run time 784, pointer tables 410, prologue scan 90, literal/data pointers 24), 25 288 labels, 17 406 layout runs.  Consistency:
0 executed bytes outside code items, 0 data reads inside code items.  `shdis` aborts if a code run contains an illegal opcode, a
branch/literal target that cannot carry a label, or if the layout does not tile the image.

## 4. Acceptance evidence
* `python tools/build.py --ref ../factory-firmware-sm/ESX0102N.BSS`: sha256 of the rebuilt file and the factory file are both
  `68fab1b99c27bfdcf10edca3c3d6511032ab9025bd209ab4b34d1e56424b5326` (cmp identical, 2097152 bytes).
* `python tools/bsspack.py unpack` + `pack` round trip is byte identical, `bsspack check` OK (size, magic, type, word sum 0).
* `python tools/selftest.py`: all 54 923 legal opcodes disassemble -> assemble -> same word; pool/alignment/range error tests.
* `python tools/emutest.py build/ESX0102N.BSS`: in the emulator the rebuilt file is written by the real BFS updater from a card
  (`SysVerUp / Sure?` -> `VerUp F/N/D` -> `Complete CkStep` -> `Turn OFF`), the system boots to the pattern display, SDRAM equals the
  payload, PLAY produces audio (174 446 samples, identical count to the factory file).  PASS.

## 5. Source layout
* `src/00_defs.s` equates (BFS entry points, RAM variables `var_xxxxxxxx`, on-chip registers from `symbols.txt`)
* `src/part_<addr>.s` the image in ~32 KB pieces split at function boundaries; only the first file has `.org` (and the pinned vector /
  entry positions), the others continue seamlessly so that code can grow.  Names: `func_/loc_/lit_/str_/dat_/jt_<address>` or the name
  from `symbols.txt`.  Literal pools are `lit_` labels with `.long label`; `.align 4` precedes every pool group (alignment padding that the
  compiler had inserted is expressed as `.align`, so the pools realign when code moves).
* `src/zz_pad.s` `.org 0x0C0ED9F0, 0` + `.incbin ../data/ram_pad.bin` (the random RAM filler, kept verbatim).  `.org` makes the build fail with
  "goes backwards" when the image grows into the fixed RAM variables; shrinking is allowed (zero filled).
* `src/manifest.txt` assembly order, `layout.txt` item map (generated), `header.json` KORG header, `build/` output.

## 6. Growth experiment (is the source really relocatable?)
`tools/growtest.py` inserts nops in front of a function in the middle of the image and rebuilds (the build sizes the RAM filler
accordingly), then runs the full update + boot in the emulator.  This found and fixed three classes of missed absolute pointers
(task descriptor tables, structs with pointers between byte fields, values inside runs of read-as-long data).  Current state:
with the final sources, inserting 2..8 bytes (1..4 nops) in front of a function in each of the 12 part files (12 builds,
`part_0C080000` .. `part_0C0E8F28`, sizes 2/4/6/8 mixed, so pools, switch tables and `.align` padding really move) -> all 12 boot to the
pattern display after the BFS updater accepted them (checksum fixed by `bsspack`); an earlier +2 byte build in the middle of the image
(0x0C0A8ACA) also passed the SDRAM-compare and audio check (174 446 samples, same as the factory image).
**Limit**: the RAM variables start immediately behind the image at **fixed** addresses (0x0C0ED9F0..) that the unchangeable boot flash
library shares, so the image may not grow in place beyond 0x0C0ED9F0 - the tail of the image (0x0C0EBF58..) holds the only free
bytes only if something else is shrunk.  Phase 2 has to find room another way (see 8).

## 7. Known limitations / honesty
* Static-only code (56 % of the instructions) was not executed; it is classified by flow analysis and trials.  Classification
  can only affect readability and relocation completeness, never the byte-exactness (any ambiguity falls back to `.byte/.word/.long`
  with identical bytes - proven by the hash) - but a data table mis-read as code/pointers would be re-assembled symbolically and could change
  meaning when code moves.  Dynamic evidence plus the growth tests make that unlikely for everything the boot/UI paths touch.
* Pointers that are not stored as aligned 32 bit values (split 16 bit constants, `mov #imm`+shifts building addresses, pointer
  arithmetic on tables, offsets in byte/word tables) are not recognised; only the 5 mova/braf switch tables use relative words.
* RAM variable addresses and BFS library addresses are plain numbers (`var_*`, `bfs_*`): they must not change.
* Peripheral register names come from the Hitachi manual; `DMAOR` at 0xA4000060 and the `isr_entry_hooks`/`midi_scif2_init` names are
  guesses marked as such in `symbols.txt`.  Only ~25 functions have real names so far; the rest are `func_<addr>`.
* The coverage emulator build copies `emu-sx/core` (state of 24.11.2026); `cov/*.cov` are the recorded results so regeneration of the
  map does not need the emulator.  The emulator does not model MIDI input, the SmartMedia card in normal operation, or DSP internals beyond
  what boot needs, so code for those is only reached statically.
* DSP firmware (`ESX0102D.BDS`) and the BFS are out of scope.

## 8. What Phase 2 (C level decompilation, function by function) needs
1. A way to grow: (a) a code cave check - RAM 0x0C1AA3B0..0x0C27FFE0 (875 KB) was never touched in all scenarios but sample memory
   probably lives beyond (var refs reach 0x0C484200) - verify with watchpoints before using it; or (b) relocate the RAM variables
   (impossible while the BFS shares addresses; need the BFS's list of shared variables) ; or (c) shrink code by compiler quality.
2. An SH-3 C compiler flow: either gcc (sh-elf, `-m3 -mb`, not installed here) or our own mini compiler; `shasm.py` already supports
   `.pool` placement and reports out-of-range literals, the build links C output into the layout by symbol names.
3. Function by function replacement with the emulator as oracle: the existing harnesses (`emutest.py`, `covrun.py` bitmaps, port logs, LCD
   text, audio hash in `sh_bench`) + per function differential tests (run original and replacement from snapshots, compare registers /
   RAM / port writes).  `lockstep.py` is the template (two machines, first divergence).
4. More names: `symbols.txt` is the place; the first things to name are the OS kernel (`main_entry` creates tasks from the tables at
   0x0C0E0764.., entry `os_create_task` = 0x0C0CDDA8 (guess)), the LCD/menu code (strings at 0x0C0E1xxx), key handlers.
5. Known RAM structures (interrupt table at 0x0C15038C, task table, key table) should become `struct` definitions.

## 9. Newtribe: permanent modifications = the OVERLAY (`newtribe/`)

**Decision.**  `src/*.s` are *generated* (fwmap.py + shdis.py) and must keep assembling to the factory image, so nothing is ever edited
in them by hand.  Modifications live in `newtribe/` (hand-maintained assembly, listed in `newtribe/manifest.txt`) and are applied by the build
as an **overlay**; they survive any regeneration of `src/` as long as the symbols they use (`func_0C0B1B1C`, `dat_0C0D2740`, ...,
named after addresses) still exist (the assembler stops with "undefined symbol" otherwise).  When Phase 2 starts replacing whole functions
the overlay is where they go; if one day the generator is retired, `src/` can simply be frozen and `newtribe/` merged into it.

How it works (`shasm.py` + `build.py`):
* `build.py` assembles `src/*.s` (main section) and `newtribe/*.s` (overlay section: its own location counter and literal pool, same symbol
  space, so overlay code calls `func_0C0B1B1C` by name and the generated sources can reference overlay labels).  The overlay bytes are laid
  over a **zero gap** of the factory image - the build refuses the overlay if any destination byte is not 0 - so the image does not grow
  (RAM variables from 0x0C0ED9F0 are untouched) and the overlay's own `.assert` checks that it ends before `main_entry` (0x0C081000).
  The gap used: 0x0C080648..0x0C080FFF (2488 bytes, currently 1632 used: Global pages + tables, start-up screen, Shift Mute; ends at `newtribe_overlay_end` 0x0C080CA8, see build/fw.map).
* `.redirect old, new` makes **every reference** to the symbol `old` (e.g. the `.long dat_0C0D2740` words in the literal pools of the generated
  code) evaluate to `new`; `old` itself keeps its address as `old__vanilla`.  So tables can be relocated without byte patching.
* `.patchlong addr, new, old` (overlay only) replaces ONE 32 bit word of the finished image (typically one literal pool entry); `old` is the value the factory image must hold there - `build.py` aborts if it differs.  Used where `.redirect` is too coarse (the same function is referenced from many places, section 9.3).
* `.copylong src, n` copies n words from the finished factory image (used to clone the 42 entry menu tables, then append entry 43).
* `python tools/build.py` = Newtribe image; `python tools/build.py --no-newtribe --ref ../factory-firmware-sm/ESX0102N.BSS` = vanilla image, must print
  IDENTICAL (sha256 68fab1b9...5326).  Both write `build/ESX0102N.BSS` (file name fixed by the BFS updater); the container word sum is fixed by
  `bsspack` as before.  Build prints the version string.
* **Version** of the custom firmware: `NEWTRIBE_VERSION` in `newtribe/version.s` (single definition, shown on the new page; max 8 chars).

### 9.1 Overlay 1: 8th GLOBAL page "Newtrb I" / version (read-only)
Menu pages are `idx = mode*7 + page` (6 modes x 7 pages = 42; Global = mode 5, idx 35..41).  Four 42 entry function pointer tables (display
`dat_0C0D2740`, leave `dat_0C0D25F0`, enter `dat_0C0D2698`, value edit `dat_0C0D23D0`) are indexed by idx and packed back to back, so
`newtribe/globalpage.s` copies each into the gap with one extra entry (idx 42): display = new routine `newtribe_page_display`
(set cursor 0, print title, set cursor 8, tail-call print of `NEWTRIBE_VERSION`), edit/leave/enter = the factory `rts; nop` stubs.  The table
`dat_0C0DBAF8` (highest page per mode `{6,4,4,6,6,6}`) is cloned with Global = 7.  Seven pointer words (6 literal pool entries for the four tables and
one for the page limit) are retargeted by `.redirect`.  The page has no edit handler (encoder does nothing, nothing is stored) and does not touch the
settings structure in NVRAM (0xC2D0000), so the factory settings layout is unchanged.  Title is "Newtrb I" because the Global title area is 8 characters.
Difference to the factory image (checked): the gap, the 7 pointer words and the last (checksum) word - nothing else.
Not modified: BFS (boot) and BDS (DSP) - use the factory files.  Installation: `release/README.txt`.

### 9.1b GLOBAL menu now has 9 pages
Since 9.3 the menu tables have 44 entries (idx 42 = "Newtrb I", idx 43 = "ShiftMut") and `dat_0C0DBAF8` has Global = 8 (highest page index); `newtribe/globalpage.s` holds the tables, the page code of 9.3 is in `newtribe/shiftmute.s`.

### 9.2 Overlay 2: start-up / loading screen (`newtribe/splash.s`)
**What the factory firmware shows** (measured in the emulator: LCD DDRAM/CGRAM sampled every 0.1..1 M instructions from reset, plus PC/caller tracing; the emulator
executes the real BFS from flash).  The boot flash (BFS) shows **nothing** in a normal boot: it only initialises the HD44780 (4 bit, display on, cursor off) and
loads the BSS (instruction 2.2 M .. 21.8 M, blank display; its LCD strings - `SysVerUp`, `Complete`, `Turn OFF`, ... - belong to the update mode).  Everything
visible comes from the BSS and was therefore changeable:
`main_entry` 21.8 M -> boot task `func_0C0CBB12` (24.16 M) -> `func_0C0B2A5C` (24.17 M): four big KORG letters on line 1 (CGRAM slots 2..5 with glyphs
`dat_0C0DAF8C..`, DDRAM codes 0x0A..0x0D), 2 spare cells 8/9 (CGRAM 0/1) on line 2; a cyclic handler "task 3" (`func_0C0B2AA2`, descriptor `dat_0C0E0894`, 300 ms)
scrolls the marquee "ELECTRIBE SX" (strings `0x0C0DB460..`) / "Wait.." on line 2; init functions run (`func_0C09EB5C .. func_0C0ADC8A`, then the sample memory check
`func_0C0C71C8`); if the sample memory has no valid signature (always in the emulator: fresh RAM) the *recovery* runs: "Recovery" on line 1 (`str_0C0E034C`)
for 125 M instructions (about 1.3 s); then `func_0C0B2B86` blanks the display and reloads CGRAM slots 2..7 (arrows) and 0/1 (0x80), the remaining init
(11 M instr) follows and the pattern screen appears.  Total: 173 M instructions in the emulator with recovery, 48 M without (patched decision).
The LCD is **8 characters x 2 lines** (the BSS only ever writes DDRAM 0x00..0x07 and 0x40..0x47).

**New behaviour.**  Line 1: bold `Newtribe` = CGRAM slots 0..6 hold thick (2 pixel stroke) glyphs N e w t r i b (5x7 + empty row, the 2nd `e` reuses its glyph), shown as the
codes 0x08..0x0E,0x09 (the controller mirrors CGRAM at 8..15; 0 would end a string).  Line 2: 4 cell bar (solid block = CGRAM slot 7, `=` half cell, `.` empty; 12.5 % per
half cell) + right aligned `  0%` .. `100%`: `....  0%`, `#=.. 41%`, `###= 88%`, `####100%` (`#` = the solid CGRAM block). Glyph art: `build/splash/glyphs.txt`.
Hooks (all `.redirect`, only literal pool words change): `func_0C0CC4EC` (first call of `main_entry`, i.e. as early as the BSS runs: 21.8 M instead of 24.0 M) draws the screen; `func_0C0B2A5C`
(KORG logo) is removed; `func_0C0B2A04` (animation mode -1/0/1/2 = boot stage) and a wrapper of `func_0C0C71C8` (check finished) are the **stage events** that raise the progress
to a floor and set a cap; `func_0C0B2AA2` + descriptor copy (period 300 -> 20 ms) is the **tick** (+1 % per tick up to the cap, every 4th tick in the last 12 % below the cap, redraw only on change);
`str_0C0E034C` ("Recovery") is redirected to the same bold `Newtribe` string so that line 1 is never overwritten; `func_0C0B2B86` (end of the factory splash) is wrapped: 100 %, hold
`NEWTRIBE_HOLD_US` (60 ms, the only added delay), then the factory routine runs unchanged (it blanks the display and reloads **all eight** CGRAM slots with the factory glyphs, so
nothing needs restoring: the splash owns CGRAM only between `main_entry` and that call).  `func_0C0B2B18` (DSP error screen) is wrapped so that the factory error text stays
(CGRAM cleared, progress stopped).  Stages (floor/cap): start 0/0, anim(-1) 1/4, anim(0) 5/24, check finished 30/39, anim(2) = recovery 40/94, end 100.  State: 5 bytes at `var_0C14F6E8`
(only the replaced factory animation used them).  LCD access only through the BFS routines the factory splash uses (`0x0C002BB0` CGRAM slot, `0x0C002B72` string at position, `0x0C009B96` delay);
only the tick draws while the OS runs (entry draw is before the OS, the final draw after the tick was stopped and flagged) so LCD transfers never interleave.
Tunables at the top of `splash.s`: `NEWTRIBE_TICK_MS`, `NEWTRIBE_HOLD_US`.
**Proof** (`python tools/splashtest.py [--mode recovery|normal]`, outputs in `build/splash/`): after the genuine card update the first splash frame is at 21.8 M instr (0 %), the
bar passes 56 distinct values up to 100 % (recovery path; 8 values in the normal path), the hand-over frame (text and all 64 CGRAM bytes) equals the factory pattern screen, no
illegal instruction; `tools/emutest.py` PASS (SDRAM == payload, audio), `fw-analysis-sm/verify_global.py` shows the 8th Global page unchanged.  Costs: +60 ms in a normal boot
(+3 % with recovery, +12 % of the 0.5 s emulator boot without).
Caveats: real hardware untested (LCD busy-flag timing is not modelled by the emulator; the BFS routines poll it); the real sample memory recovery duration is unknown (the bar then waits at <= 94 % and slows down
instead of showing 100 % early); a real "Recovery" is no longer announced by text (line 1 stays `Newtribe`).

### 9.3 Overlay 3: "Shift Mute" (`newtribe/shiftmute.s`)
**Feature.**  GLOBAL page 9 (after "Newtrb I"): title `ShiftMut`, value line `Off` / `On`, changed with the VALUE encoder (clamped, like the factory On/Off pages).  Default **Off**.
With **On**: pressing a PART key (the 16 part keys d1..arrange) while **SHIFT is held** only *selects* the part - its mute state is not touched.  Without SHIFT or with Off everything is the factory
behaviour (same code path, arguments untouched).  Works for all 16 parts.  Typical use: jump to a muted part to turn its volume/parameters without un-muting it.

**What the factory does (measured in the emulator, `symbols.txt` block "part keys / PART MUTE").**  Part key -> `dat_0C0D2174[16+part]` -> `func_0C0BBDCC` (part_key_event; r4 = part, r5 = press) ->
per-mode handler table `dat_0C0DFACC` (mode = `var_0C150604`; 0 = normal `func_0C0BB182`, 13 = PART MUTE key held `func_0C0BB816`).  The normal handler selects the part (LED, parameter page, `var_0C0F09AF` = selected part)
and calls `func_0C0BB0C8(part)` (10 call sites in the mode handlers), which rewrites the **mute mask word `var_0C17A3A6`** (bit n = part n, bits 0..14; 1 = muted, 0 = audible / LED lit): normally it clears the part's bit
(**= un-mutes the selected part**), with the solo-like flag `var_0C17A3AA` set (state after start-up until the first mask write) it writes "all other parts muted".  The write is the generic
parameter call `func_0C0BA992(0x1F7, mask, 0, 0, stack 1)` (0x1F7 = PART MUTE), reached through ONE literal pool word (`lit_0C0BB274`, used only by `func_0C0BB0C8`).  The mute mode itself (PART MUTE key held + part key) uses another
literal (`lit_0C0BB97C`) and is not touched.

**Hook.**  `.patchlong lit_0C0BB274, newtribe_mutemask_hook, func_0C0BA992`: a single pointer word in the pool of `func_0C0BB0C8` (0x0C0BB274) now points to `newtribe_mutemask_hook` (0x0C080BF4).  The hook returns
immediately (mask not written, selection etc. already done by the caller) if `r4 == 0x1F7 && option != 0 && SHIFT pressed`; in every other case it `jmp`s to `func_0C0BA992` with r4..r7, the stack and `pr` unchanged
(r0/r1 are the only registers it uses).  Nothing else in the image changes (vanilla build still IDENTICAL; difference of the Newtribe image to the factory file, checked: the gap, 17 pointer words (7 menu tables/limit, 9 start-up screen, 1 hook) and the checksum word).
**SHIFT** = key matrix row 0 bit 1 (keymap.json `shift` 0,2): `scan_panel_keys` keeps the active-low port level of the rows in `var_0C178694[row]` (0x9F idle, 0x9D SHIFT held), the hook tests `(byte & 2) == 0`.
This is the raw (not debounced) scan value, i.e. it is current as soon as the scan saw the key.

**Option storage.**  One byte `newtribe_opt_shiftmute` (0x0C080C9C) inside the overlay (SDRAM, written at run time like the factory's own variables inside the image at 0x0C0E08E8..).  It is **not persistent**: the BSS
is copied from NAND at every boot, so the option is Off after power-on.  Reason: the global settings live in the NVRAM block at 0xC2D0000 (`var_0C2D0020` ...), copied/saved by routines whose size, layout and checksum
are not fully understood (the emulator's block is empty/0xFF), and a wrong write could damage patterns/settings - deliberately not touched.  (Possible later: a free byte in the global struct, plus its save routine.)

**Limits / notes.**  (1) Which mute state is "the" state: only the mask `var_0C17A3A6` (what PART MUTE mode and the LEDs show); song-mode "MuteHold" or other copies were not examined.  (2) With the solo-like flag set
(start-up state) a SHIFT+part press also leaves the solo selection unchanged (the part is selected, the sounding part stays).  (3) SHIFT must be down before the part key (a human always does that; if both are pressed in the very
same few ms the raw row 0 may not be scanned yet and the part is un-muted as in the factory firmware - measured in the emulator for simultaneous presses).  (4) Real hardware untested; audio/sequencer effect of the mask was
verified through the mask variable, PART MUTE mode display and LEDs, not by listening (the emulator has no pattern data in the recovery state).
**Tests** (emulator, custom image): GLOBAL walk shows `Newtrb I`/`0.0.1` then `ShiftMut`/`Off`, encoder toggles Off<->On (clamped), no illegal instruction (`fw-analysis-sm/verify_global.py emu-sx/custom`);
all 16 parts with SHIFT+On leave the mask unchanged and select the part (`var_0C0F09AF` = 0..15, LED of the part lit), without SHIFT or with Off the mask bit is cleared as in the factory;
`tools/emutest.py` PASS.
