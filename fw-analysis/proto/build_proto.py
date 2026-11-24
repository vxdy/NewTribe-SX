#!/usr/bin/env python3
"""Byte-patch ESX0102N.BSS: add a 8th read-only Global page ("Newtribe", value "0.0.1").
Usage: python build_proto.py [title] [value]   -> writes ESX0102N_proto.BSS next to this file."""
import struct, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent.parent / "factory-firmware" / "ESX0102N.BSS"
BASE = 0x0C080000          # payload (file offset 0x20) is loaded here
TITLE = (sys.argv[1] if len(sys.argv) > 1 else "Newtribe")
VALUE = (sys.argv[2] if len(sys.argv) > 2 else "0.0.1")

f = bytearray(SRC.read_bytes())
def off(a): return a - BASE + 0x20
def r32(a): return struct.unpack_from(">I", f, off(a))[0]
def w32(a, v): struct.pack_into(">I", f, off(a), v)
def w16(a, v): struct.pack_into(">H", f, off(a), v)

# --- existing tables (42 entries = 6 modes x 7 pages; Global = mode 5 = entries 35..41)
T_EDIT, T_LEAVE, T_ENTER, T_DISP = 0x0C0D23D0, 0x0C0D25F0, 0x0C0D2698, 0x0C0D2740
NOP_EDIT, NOP_LEAVE = 0x0C093228, 0x0C093224      # existing "rts; nop" stubs
FN_SETPOS, FN_PRINT = 0x0C0B1B1C, 0x0C0B1D86       # set cursor (0 = title, 8 = value) / print C string

CAVE = 0x0C080650          # zero gap 0x0C080645..0x0C080FFF in the factory image
assert all(b == 0 for b in f[off(CAVE):off(0x0C081000)])

# --- tiny SH assembler for the new function
code = []; fixups = []
def ins(w): code.append(w)
def ldl(rn, label): fixups.append((len(code), rn, label)); code.append(None)
ins(0x4F22)                 # sts.l pr,@-r15
ldl(2, 'setpos'); ins(0x420B); ins(0xE400)      # jsr @r2 ; mov #0,r4
ldl(4, 'title');  ldl(2, 'print'); ins(0x420B); ins(0x0009)   # jsr @r2 ; nop
ldl(2, 'setpos'); ins(0x420B); ins(0xE408)      # jsr @r2 ; mov #8,r4
ldl(4, 'value');  ldl(2, 'print'); ins(0x422B); ins(0x4F26)   # jmp @r2 ; lds.l @r15+,pr
nwords = len(code)
if nwords % 2: code.append(0x0009); nwords += 1   # keep the literal pool 4-aligned
pool_at = CAVE + 2 * nwords
labels = {}
strings = TITLE.encode() + b"\0" ; strings += b"\0" * (-len(strings) % 4)
strings_at = pool_at + 4 * 4
labels['title'] = strings_at
vstr = VALUE.encode() + b"\0"; vstr += b"\0" * (-len(vstr) % 4)
labels['value'] = strings_at + len(strings)
labels['setpos'], labels['print'] = FN_SETPOS, FN_PRINT
pool_order = ['setpos', 'print', 'title', 'value']
pool = {k: pool_at + 4 * i for i, k in enumerate(pool_order)}
for idx, rn, lab in fixups:
    pc = CAVE + 2 * idx
    d = (pool[lab] - ((pc + 4) & ~3)) // 4
    assert 0 <= d < 256
    code[idx] = 0xD000 | (rn << 8) | d
blob = b"".join(struct.pack(">H", w) for w in code)
blob += b"".join(struct.pack(">I", labels[k]) for k in pool_order) + strings + vstr
func_addr = CAVE
cur = CAVE + len(blob); cur = (cur + 3) & ~3

def copy_table(base, extra):
    global cur
    tbl = b"".join(struct.pack(">I", r32(base + 4 * i)) for i in range(42)) + struct.pack(">I", extra)
    a = cur; f[off(a):off(a) + len(tbl)] = tbl; cur += len(tbl); return a
f[off(CAVE):off(CAVE) + len(blob)] = blob
n_edit  = copy_table(T_EDIT,  NOP_EDIT)
n_leave = copy_table(T_LEAVE, NOP_LEAVE)
n_enter = copy_table(T_ENTER, NOP_LEAVE)
n_disp  = copy_table(T_DISP,  func_addr)
assert cur < 0x0C081000 - 8, hex(cur)

# --- redirect the six literal-pool words that point at the old tables
for a, old, new in ((0x0C0B5F84, T_DISP, n_disp), (0x0C0B5FA0, T_LEAVE, n_leave), (0x0C0B614C, T_LEAVE, n_leave),
                    (0x0C0B5FA4, T_ENTER, n_enter), (0x0C0B6150, T_ENTER, n_enter), (0x0C089350, T_EDIT, n_edit)):
    assert r32(a) == old, hex(a); w32(a, new)
# --- highest page index of mode 5 (Global): 6 -> 7
assert r32(0x0C0DBB0C) == 6; w32(0x0C0DBB0C, 7)

# --- container: whole-file 32-bit word sum must stay 0 -> correct a spare word at the end of the cave
FIX = 0x0C080FF8
assert r32(FIX) == 0
s = sum(struct.unpack(">%dI" % (len(f) // 4), f)) & 0xFFFFFFFF
w32(FIX, (-s) & 0xFFFFFFFF)
assert sum(struct.unpack(">%dI" % (len(f) // 4), f)) & 0xFFFFFFFF == 0
out = HERE / "ESX0102N_proto.BSS"; out.write_bytes(bytes(f))
print("wrote", out, "func", hex(func_addr), "tables", [hex(x) for x in (n_edit, n_leave, n_enter, n_disp)], "cave end", hex(cur))
