#!/usr/bin/env python3
"""selftest.py - checks of the ISA tables and the assembler (python tools/selftest.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shasm
import shisa


def asm(lines, strict=False):
    a = shasm.Assembler(strict=strict)
    a.parse_lines(lines, "<t>")
    a.pass1()
    return a, a.pass2()


def main():
    # 1. every legal opcode: disassemble -> assemble -> same opcode
    bad = 0
    n = 0
    for op in range(0x10000):
        d = shisa.decode(op)
        if not d:
            continue
        n += 1
        txt = shisa.format_insn(op, 0x0C081000)
        _, b = asm([" .org 0x0C081000", " " + txt])
        if int.from_bytes(b, "big") != op:
            print("MISMATCH %04X %s" % (op, txt))
            bad += 1
    print("opcode round trip: %d opcodes, %d mismatches" % (n, bad))
    # 2. pool: mov.l =expr / mov.w =expr, shared entries, alignment
    a, b = asm([" .org 0x1000", " mov.l =0x12345678,r1", " mov.w =0x1234,r2", " mov.l =0x12345678,r3", " rts", " nop", " .pool"])
    exp = bytes.fromhex("d102" "9203" "d301" "000b" "0009") + bytes.fromhex("1234") + bytes.fromhex("12345678")
    # layout: 5 insns = 0x100A, word pool @0x100A (1234), align -> long @0x100C
    exp = bytes.fromhex("d102") + bytes.fromhex("9202") + bytes.fromhex("d301") + bytes.fromhex("000b0009") + bytes.fromhex("1234") + bytes.fromhex("12345678")
    print("pool test:", "ok" if b == exp else "FAIL %s vs %s" % (b.hex(), exp.hex()))
    bad += b != exp
    # 3. clear errors
    for name, src in (("literal too far", [" .org 0x1000", " mov.l @(far,pc),r1", " .space 2000", "far: .long 1"]),
                      ("misaligned literal", [" .org 0x1000", " mov.l @(lit,pc),r1", " nop", " nop", "lit: .long 1"]),
                      ("branch too far", [" .org 0x1000", " bt far", " .space 400", "far: nop"]),
                      ("org backwards", [" .org 0x1000", " .space 8", " .org 0x1004"])):
        try:
            asm(src)
            print("error test %-18s FAIL (no error)" % name)
            bad += 1
        except shasm.AsmError as e:
            print("error test %-18s ok: %s" % (name, str(e)[:100]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
