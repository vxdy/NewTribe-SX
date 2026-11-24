#!/usr/bin/env python3
"""SH-3 (SH7709) instruction set tables shared by the assembler (shasm.py) and disassembler (shdis.py).

Every instruction is one 16-bit word.  Each table row is (bit-pattern, syntax):

  bit pattern   16 chars of 0/1 and the field letters
                  n = Rn (bits 8..11)   m = Rm (bits 4..7)   b = bank number (3 bits, 4..6)
                  i = 8-bit immediate (bits 0..7)   d = displacement field (4, 8 or 12 bits, right aligned)
  syntax        mnemonic and operands as printed/accepted; placeholders:
                  {n} {m} {b}      register / bank number (printed as decimal)
                  {is} {iu}        8-bit immediate, signed / unsigned
                  {d1} {d2} {d4}   4 or 8 bit displacement, scaled by 1/2/4 (printed in bytes)
                  {pcw} {pcl}      PC relative word / long literal  (@(disp,pc)); mova uses {pcl}
                  {br8} {br12}     branch displacement (target address)
Only the operand *kinds* matter for matching in the assembler, see classify() in shasm.py.
"""
import re

ROWS = [
    # --- data transfer
    ("1110nnnniiiiiiii", "mov #{is},r{n}"),
    ("1001nnnndddddddd", "mov.w @({pcw},pc),r{n}"),
    ("1101nnnndddddddd", "mov.l @({pcl},pc),r{n}"),
    ("0110nnnnmmmm0011", "mov r{m},r{n}"),
    ("0010nnnnmmmm0000", "mov.b r{m},@r{n}"),
    ("0010nnnnmmmm0001", "mov.w r{m},@r{n}"),
    ("0010nnnnmmmm0010", "mov.l r{m},@r{n}"),
    ("0110nnnnmmmm0000", "mov.b @r{m},r{n}"),
    ("0110nnnnmmmm0001", "mov.w @r{m},r{n}"),
    ("0110nnnnmmmm0010", "mov.l @r{m},r{n}"),
    ("0010nnnnmmmm0100", "mov.b r{m},@-r{n}"),
    ("0010nnnnmmmm0101", "mov.w r{m},@-r{n}"),
    ("0010nnnnmmmm0110", "mov.l r{m},@-r{n}"),
    ("0110nnnnmmmm0100", "mov.b @r{m}+,r{n}"),
    ("0110nnnnmmmm0101", "mov.w @r{m}+,r{n}"),
    ("0110nnnnmmmm0110", "mov.l @r{m}+,r{n}"),
    ("10000000nnnndddd", "mov.b r0,@({d1},r{n})"),
    ("10000001nnnndddd", "mov.w r0,@({d2},r{n})"),
    ("0001nnnnmmmmdddd", "mov.l r{m},@({d4},r{n})"),
    ("10000100mmmmdddd", "mov.b @({d1},r{m}),r0"),
    ("10000101mmmmdddd", "mov.w @({d2},r{m}),r0"),
    ("0101nnnnmmmmdddd", "mov.l @({d4},r{m}),r{n}"),
    ("0000nnnnmmmm0100", "mov.b r{m},@(r0,r{n})"),
    ("0000nnnnmmmm0101", "mov.w r{m},@(r0,r{n})"),
    ("0000nnnnmmmm0110", "mov.l r{m},@(r0,r{n})"),
    ("0000nnnnmmmm1100", "mov.b @(r0,r{m}),r{n}"),
    ("0000nnnnmmmm1101", "mov.w @(r0,r{m}),r{n}"),
    ("0000nnnnmmmm1110", "mov.l @(r0,r{m}),r{n}"),
    ("11000000dddddddd", "mov.b r0,@({d1g},gbr)"),
    ("11000001dddddddd", "mov.w r0,@({d2g},gbr)"),
    ("11000010dddddddd", "mov.l r0,@({d4g},gbr)"),
    ("11000100dddddddd", "mov.b @({d1g},gbr),r0"),
    ("11000101dddddddd", "mov.w @({d2g},gbr),r0"),
    ("11000110dddddddd", "mov.l @({d4g},gbr),r0"),
    ("11000111dddddddd", "mova @({pcl},pc),r0"),
    ("0000nnnn00101001", "movt r{n}"),
    ("0110nnnnmmmm1000", "swap.b r{m},r{n}"),
    ("0110nnnnmmmm1001", "swap.w r{m},r{n}"),
    ("0010nnnnmmmm1101", "xtrct r{m},r{n}"),
    # --- arithmetic
    ("0011nnnnmmmm1100", "add r{m},r{n}"),
    ("0111nnnniiiiiiii", "add #{is},r{n}"),
    ("0011nnnnmmmm1110", "addc r{m},r{n}"),
    ("0011nnnnmmmm1111", "addv r{m},r{n}"),
    ("10001000iiiiiiii", "cmp/eq #{is},r0"),
    ("0011nnnnmmmm0000", "cmp/eq r{m},r{n}"),
    ("0011nnnnmmmm0010", "cmp/hs r{m},r{n}"),
    ("0011nnnnmmmm0011", "cmp/ge r{m},r{n}"),
    ("0011nnnnmmmm0110", "cmp/hi r{m},r{n}"),
    ("0011nnnnmmmm0111", "cmp/gt r{m},r{n}"),
    ("0100nnnn00010101", "cmp/pl r{n}"),
    ("0100nnnn00010001", "cmp/pz r{n}"),
    ("0010nnnnmmmm1100", "cmp/str r{m},r{n}"),
    ("0011nnnnmmmm0100", "div1 r{m},r{n}"),
    ("0010nnnnmmmm0111", "div0s r{m},r{n}"),
    ("0000000000011001", "div0u"),
    ("0011nnnnmmmm1101", "dmuls.l r{m},r{n}"),
    ("0011nnnnmmmm0101", "dmulu.l r{m},r{n}"),
    ("0100nnnn00010000", "dt r{n}"),
    ("0110nnnnmmmm1110", "exts.b r{m},r{n}"),
    ("0110nnnnmmmm1111", "exts.w r{m},r{n}"),
    ("0110nnnnmmmm1100", "extu.b r{m},r{n}"),
    ("0110nnnnmmmm1101", "extu.w r{m},r{n}"),
    ("0000nnnnmmmm1111", "mac.l @r{m}+,@r{n}+"),
    ("0100nnnnmmmm1111", "mac.w @r{m}+,@r{n}+"),
    ("0000nnnnmmmm0111", "mul.l r{m},r{n}"),
    ("0010nnnnmmmm1111", "muls.w r{m},r{n}"),
    ("0010nnnnmmmm1110", "mulu.w r{m},r{n}"),
    ("0110nnnnmmmm1011", "neg r{m},r{n}"),
    ("0110nnnnmmmm1010", "negc r{m},r{n}"),
    ("0011nnnnmmmm1000", "sub r{m},r{n}"),
    ("0011nnnnmmmm1010", "subc r{m},r{n}"),
    ("0011nnnnmmmm1011", "subv r{m},r{n}"),
    # --- logic
    ("0010nnnnmmmm1001", "and r{m},r{n}"),
    ("11001001iiiiiiii", "and #{iu},r0"),
    ("11001101iiiiiiii", "and.b #{iu},@(r0,gbr)"),
    ("0110nnnnmmmm0111", "not r{m},r{n}"),
    ("0010nnnnmmmm1011", "or r{m},r{n}"),
    ("11001011iiiiiiii", "or #{iu},r0"),
    ("11001111iiiiiiii", "or.b #{iu},@(r0,gbr)"),
    ("0100nnnn00011011", "tas.b @r{n}"),
    ("0010nnnnmmmm1000", "tst r{m},r{n}"),
    ("11001000iiiiiiii", "tst #{iu},r0"),
    ("11001100iiiiiiii", "tst.b #{iu},@(r0,gbr)"),
    ("0010nnnnmmmm1010", "xor r{m},r{n}"),
    ("11001010iiiiiiii", "xor #{iu},r0"),
    ("11001110iiiiiiii", "xor.b #{iu},@(r0,gbr)"),
    # --- shift
    ("0100nnnn00100100", "rotcl r{n}"),
    ("0100nnnn00100101", "rotcr r{n}"),
    ("0100nnnn00000100", "rotl r{n}"),
    ("0100nnnn00000101", "rotr r{n}"),
    ("0100nnnn00100000", "shal r{n}"),
    ("0100nnnn00100001", "shar r{n}"),
    ("0100nnnn00000000", "shll r{n}"),
    ("0100nnnn00000001", "shlr r{n}"),
    ("0100nnnn00001000", "shll2 r{n}"),
    ("0100nnnn00001001", "shlr2 r{n}"),
    ("0100nnnn00011000", "shll8 r{n}"),
    ("0100nnnn00011001", "shlr8 r{n}"),
    ("0100nnnn00101000", "shll16 r{n}"),
    ("0100nnnn00101001", "shlr16 r{n}"),
    ("0100nnnnmmmm1100", "shad r{m},r{n}"),
    ("0100nnnnmmmm1101", "shld r{m},r{n}"),
    # --- branch
    ("10001011dddddddd", "bf {br8}"),
    ("10001111dddddddd", "bf/s {br8}"),
    ("10001001dddddddd", "bt {br8}"),
    ("10001101dddddddd", "bt/s {br8}"),
    ("1010dddddddddddd", "bra {br12}"),
    ("1011dddddddddddd", "bsr {br12}"),
    ("0000mmmm00100011", "braf r{m}"),
    ("0000mmmm00000011", "bsrf r{m}"),
    ("0100mmmm00101011", "jmp @r{m}"),
    ("0100mmmm00001011", "jsr @r{m}"),
    ("0000000000001011", "rts"),
    ("0000000000101011", "rte"),
    # --- system control
    ("0000000000101000", "clrmac"),
    ("0000000001001000", "clrs"),
    ("0000000000001000", "clrt"),
    ("0000000001011000", "sets"),
    ("0000000000011000", "sett"),
    ("0000000000001001", "nop"),
    ("0000000000011011", "sleep"),
    ("0000000000111000", "ldtlb"),
    ("11000011iiiiiiii", "trapa #{iu}"),
    ("0100mmmm00001110", "ldc r{m},sr"),
    ("0100mmmm00011110", "ldc r{m},gbr"),
    ("0100mmmm00101110", "ldc r{m},vbr"),
    ("0100mmmm00111110", "ldc r{m},ssr"),
    ("0100mmmm01001110", "ldc r{m},spc"),
    ("0100mmmm1bbb1110", "ldc r{m},r{b}_bank"),
    ("0100mmmm00000111", "ldc.l @r{m}+,sr"),
    ("0100mmmm00010111", "ldc.l @r{m}+,gbr"),
    ("0100mmmm00100111", "ldc.l @r{m}+,vbr"),
    ("0100mmmm00110111", "ldc.l @r{m}+,ssr"),
    ("0100mmmm01000111", "ldc.l @r{m}+,spc"),
    ("0100mmmm1bbb0111", "ldc.l @r{m}+,r{b}_bank"),
    ("0100mmmm00001010", "lds r{m},mach"),
    ("0100mmmm00011010", "lds r{m},macl"),
    ("0100mmmm00101010", "lds r{m},pr"),
    ("0100mmmm00000110", "lds.l @r{m}+,mach"),
    ("0100mmmm00010110", "lds.l @r{m}+,macl"),
    ("0100mmmm00100110", "lds.l @r{m}+,pr"),
    ("0000nnnn00000010", "stc sr,r{n}"),
    ("0000nnnn00010010", "stc gbr,r{n}"),
    ("0000nnnn00100010", "stc vbr,r{n}"),
    ("0000nnnn00110010", "stc ssr,r{n}"),
    ("0000nnnn01000010", "stc spc,r{n}"),
    ("0000nnnn1bbb0010", "stc r{b}_bank,r{n}"),
    ("0100nnnn00000011", "stc.l sr,@-r{n}"),
    ("0100nnnn00010011", "stc.l gbr,@-r{n}"),
    ("0100nnnn00100011", "stc.l vbr,@-r{n}"),
    ("0100nnnn00110011", "stc.l ssr,@-r{n}"),
    ("0100nnnn01000011", "stc.l spc,@-r{n}"),
    ("0100nnnn1bbb0011", "stc.l r{b}_bank,@-r{n}"),
    ("0000nnnn00001010", "sts mach,r{n}"),
    ("0000nnnn00011010", "sts macl,r{n}"),
    ("0000nnnn00101010", "sts pr,r{n}"),
    ("0100nnnn00000010", "sts.l mach,@-r{n}"),
    ("0100nnnn00010010", "sts.l macl,@-r{n}"),
    ("0100nnnn00100010", "sts.l pr,@-r{n}"),
    ("0000nnnn10000011", "pref @r{n}"),
]

# SH7709 (SH-3) has no shlr16/shll16?  They exist on SH-1+.  The fix for the row clash below: "shlr16" pattern
# 0100nnnn00101001 vs "movt" 0000nnnn00101001 differ in the top nibble, so no clash.


class Insn:
    __slots__ = ("mask", "val", "fields", "syntax", "mn", "ops", "kinds")


def _compile():
    out = []
    for bits, syn in ROWS:
        assert len(bits) == 16, bits
        mask = val = 0
        fields = {}
        for k, ch in enumerate(bits):
            sh = 15 - k
            if ch in "01":
                mask |= 1 << sh
                val |= (ch == "1") << sh
            else:
                fields.setdefault(ch, []).append(sh)
        ins = Insn()
        ins.mask, ins.val, ins.syntax = mask, val, syn
        ins.fields = {c: (min(s), len(s)) for c, s in fields.items()}  # (lowest bit, width)
        parts = syn.split(None, 1)
        ins.mn = parts[0]
        ins.ops = split_ops(parts[1]) if len(parts) > 1 else []
        out.append(ins)
    return out


def split_ops(s):
    """Split an operand string on commas that are not inside parentheses."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


INSNS = _compile()
# detect duplicates (a word matching two rows)
_BY_TOP = {}
for _i in INSNS:
    for _t in range(16):
        if (_t & (_i.mask >> 12)) == (_i.val >> 12):
            _BY_TOP.setdefault(_t, []).append(_i)


def lookup(op):
    """Return the Insn matching a 16-bit opcode or None."""
    for i in _BY_TOP.get(op >> 12, ()):
        if op & i.mask == i.val:
            return i
    return None


def fld(ins, c, op):
    lo, w = ins.fields[c]
    return (op >> lo) & ((1 << w) - 1)


def decode(op):
    """Decode a word into (Insn, values dict) with raw field values; None for an illegal opcode."""
    i = lookup(op)
    if i is None:
        return None
    return i, {c: fld(i, c, op) for c in i.fields}


def sext(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def targets(ins, vals, pc):
    """Return (kind, address) for pc relative operands of a decoded instruction, else None.
    kind: 'wlit' word literal, 'llit' long literal / mova target, 'br' branch/call target."""
    d = vals.get("d")
    if d is None:
        return None
    s = ins.syntax
    if "{pcw}" in s:
        return "wlit", pc + 4 + d * 2
    if "{pcl}" in s:
        return "llit", ((pc + 4) & ~3) + d * 4
    if "{br8}" in s:
        return "br", (pc + 4 + sext(d, 8) * 2) & 0xFFFFFFFF
    if "{br12}" in s:
        return "br", (pc + 4 + sext(d, 12) * 2) & 0xFFFFFFFF
    return None


def format_insn(op, pc, symfn=None, ins_vals=None):
    """Text of the instruction `op` at address pc.  symfn(kind, addr) -> str renders pc-relative targets
    (default: hex address).  Returns None for illegal opcodes."""
    r = ins_vals or decode(op)
    if r is None:
        return None
    ins, v = r
    t = targets(ins, v, pc)
    syn = ins.syntax
    out = syn
    rep = {}
    for k in ("n", "m", "b"):
        if k in v:
            rep["{%s}" % k] = str(v[k])
    if "i" in v:
        rep["{is}"] = str(sext(v["i"], 8))
        rep["{iu}"] = "0x%02X" % v["i"] if v["i"] > 9 else str(v["i"])
    if "d" in v and t is None:
        d = v["d"]
        for sc in (1, 2, 4):
            rep["{d%d}" % sc] = str(d * sc)
            rep["{d%dg}" % sc] = str(d * sc)
    if t is not None:
        txt = symfn(t[0], t[1]) if symfn else "0x%08X" % t[1]
        for k in ("{pcw}", "{pcl}", "{br8}", "{br12}"):
            rep[k] = txt
    for k, val in rep.items():
        out = out.replace(k, val)
    mn, _, rest = out.partition(" ")
    return mn.ljust(7) + " " + rest if rest else mn


def self_test():
    seen = {}
    for op in range(0x10000):
        hits = [i for i in INSNS if op & i.mask == i.val]
        if len(hits) > 1:
            raise SystemExit("ambiguous opcode %04x: %s" % (op, [h.syntax for h in hits]))
    return True


if __name__ == "__main__":
    self_test()
    n = sum(1 for op in range(0x10000) if lookup(op))
    print("rows", len(INSNS), "valid opcodes", n)
