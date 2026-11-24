# SPDX-License-Identifier: GPL-2.0-only
"""Disassembler for the uPD77213 (uPD77016 family instruction set, 32-bit words).

Field layouts come from "uPD77016 Family User's Manual - Instructions" (U13116E), appendix A. The opcode numbers of the
tables are the row order of the figures there (the manual lists them without numbers), so every table here is a guess
that has to be confirmed by running real code.
"""

OPS3 = ["lt", "mul", "madd", "msub", "suma", "uuma", "mas1", "mas16", "add", "sub", "and", "or", "xor", "sra", "srl", "sll"]
OPS2 = ["nop", "clr", "inc", "dec", "abs", "not", "neg", "clip", "round", "exp", "put", "div", "acc+", "acc-"]
IMMOPS = ["add", "sub", "and", "or", "xor", "sra", "srl", "sll"]
MODI = ["nop", "", "++", "--", "##", "%%", "!##"]      # modix field value 1 means plain *dp (no modification)
COND = ["ever", "?1", "==0", "!=0", ">0", "<=0", ">=0", "<0", "==ex", "!=ex"]
# suf is a part mask: bit0 = L (15:0), bit1 = H (31:16), bit2 = E (39:32); 6 = EH, 7 = whole register (confirmed by the boot code:
# "r0l = imm; store" and "load; inc; store" only make sense when suf=1 is the low half)
SUFNAME = {1: "l", 2: "h", 4: "e", 6: "eh", 7: ""}
XREG = [f"dp{i}" for i in range(8)] + [f"dn{i}" for i in range(8)] + ["dmx", "dmy"]
YREG = ["sr", "eir", "stack", "sp", "lc", "lsp", "lsr1", "lsr2", "lsr3", "esr"]


def _mem(dp, modi, ydir):
    m = MODI[modi] if modi < len(MODI) else f"?{modi}"
    if m == "nop":
        return None
    if modi == 1:
        return f"*dp{dp}"
    if modi == 6:
        return f"*!dp{dp}##"
    return f"*dp{dp}{m}"


def _ldst(w):
    """XY parallel load/store part of a three-/two-operand word."""
    out = []
    for (dxb, dpb, mb, rb, dpbase, nm) in ((17, 14, 11, 8, 0, "x"), (16, 6, 3, 0, 4, "y")):
        dx = (w >> dxb) & 1
        dp = ((w >> dpb) & 3) + dpbase
        modi = (w >> mb) & 7
        r = (w >> rb) & 7
        mem = _mem(dp, modi, nm)
        if mem is None:
            continue
        out.append(f"r{r} = {mem}" if dx else f"{mem} = r{r}h")
    return " ".join(out)


def dis(w, pc=0):
    top = w >> 28
    if top == 0:
        return {0: "nop", 1: "halt", 2: "lpop", 4: "fint", 9: "stop"}.get(w, f".word {w:08x}")
    if top == 1:
        cnt = w & 0x7FFF
        k = (w >> 26) & 3
        if k == 3:
            return f"repeat {cnt}"
        if k == 2:
            return f"repeat r{w & 7}l"
        end = (w >> 16) & 0xFF
        if k == 1:
            return f"loop {cnt} {{ end=+{end}"
        return f"loop r{w & 7}l {{ end=+{end}"
    if top == 2:
        cond, t = (w >> 3) & 15, w & 7
        c = "" if cond == 0 else f"if (r{t} {COND[cond] if cond < len(COND) else cond}) "
        k = (w >> 26) & 3
        jc = (w >> 25) & 1
        if k == 3:
            rel = (w >> 7) & 0xFFFF
            rel = rel - 0x10000 if rel & 0x8000 else rel
            return f"{c}{'call' if jc else 'jmp'} {pc + rel:#x}"
        if k == 2:
            return f"{c}{'callr' if jc else 'jp'} dp{(w >> 17) & 7}"
        if k == 1:
            return f"{c}{'reti' if jc else 'ret'}"
        return f".word {w:08x}"
    if top == 3:
        cond, t = (w >> 3) & 15, w & 7
        c = "" if cond == 0 else f"if (r{t} {COND[cond] if cond < len(COND) else cond}) "
        k = (w >> 26) & 3
        d = (w >> 16) & 1
        if k == 2:           # immediate set
            imm = w & 0xFFFF
            if d == 0:
                i = (w >> 17) & 0x3F
                return f"{XREG[i] if i < 18 else f'?{i}'} = {imm:#x}"
            return f"r{(w >> 23) & 7}l = {imm:#x}"
        if k == 3:           # inter-register transfer
            a = (w >> 23) & 7
            b6 = (w >> 17) & 0x3F
            sel = (w >> 22) & 1
            idx = (b6 & 0x1F) | (sel << 5)
            name = XREG[idx] if idx < 18 else (YREG[idx - 32] if 32 <= idx < 42 else f"?{idx}")
            return f"{c}{name} = r{a}l" if d == 0 else f"{c}r{a}l = {name}"
        return f".word {w:08x}"
    if top == 4:
        k = (w >> 26) & 3
        if k == 3:           # partial load/store
            out = []
            for (sb, db, dpb, mb, rb, dpbase) in ((23, 17, 14, 11, 8, 0), (20, 16, 6, 3, 0, 4)):
                suf = (w >> sb) & 7
                d = (w >> db) & 1
                dp = ((w >> dpb) & 3) + dpbase
                modi = (w >> mb) & 7
                r = (w >> rb) & 7
                mem = _mem(dp, modi, 0)
                if mem is None:
                    continue
                s = SUFNAME.get(suf, f"?{suf}")
                out.append(f"{mem} = r{r}{s}" if d == 0 else f"r{r}{s} = {mem}")
            return " ".join(out) or "pnop"
        d = (w >> 16) & 1
        suf = (w >> 20) & 7
        r = (w >> 23) & 7
        s = SUFNAME.get(suf, f"?{suf}")
        if k == 2:           # direct
            xy = "xy"[(w >> 19) & 1]
            a = w & 0xFFFF
            return f"*{xy}:{a:#06x} = r{r}{s}" if d == 0 else f"r{r}{s} = *{xy}:{a:#06x}"
        if k == 1:           # immediate modify
            dp = (w >> 17) & 7
            imm = w & 0xFFFF
            imm = imm - 0x10000 if imm & 0x8000 else imm
            return f"*dp{dp}##{imm} = r{r}{s}" if d == 0 else f"r{r}{s} = *dp{dp}##{imm}"
        return f".word {w:08x}"
    if top == 5:
        op = (w >> 24) & 15
        nm = IMMOPS[op - 8] if 8 <= op < 16 else f"?{op}"
        return f"r{(w >> 18) & 7} = r{(w >> 21) & 7} {nm} {w & 0xFFFF:#x}"
    if top == 6:
        op = (w >> 24) & 15
        cond, t = (w >> 3) & 15, w & 7
        c = "" if cond == 0 else f"if (r{t} {COND[cond] if cond < len(COND) else cond}) "
        nm = OPS2[op] if op < len(OPS2) else f"?{op}"
        return f"{c}{nm} r{(w >> 18) & 7} <- r{(w >> 21) & 7}"
    if top == 7:
        op = (w >> 24) & 15
        nm = OPS2[op] if op < len(OPS2) else f"?{op}"
        s = f"{nm} r{(w >> 18) & 7} <- r{(w >> 21) & 7}"
        return (s + " " + _ldst(w)).strip()
    # top >= 8: three operand, bit 31 = 1
    op1 = (w >> 28) & 7
    op = (w >> 24) & 15
    op2 = (w >> 21) & 7
    op3 = (w >> 18) & 7
    s = f"r{op3} = {OPS3[op]} r{op1}, r{op2}"
    return (s + " " + _ldst(w)).strip()


def load_bds(path, base=80):
    """BDS payload = 32-bit instruction words stored as (low 16, high 16), both big endian."""
    d = open(path, "rb").read()
    n = (len(d) - base) // 4
    return [(int.from_bytes(d[base + 4 * i + 2:base + 4 * i + 4], "big") << 16) | int.from_bytes(d[base + 4 * i:base + 4 * i + 2], "big") for i in range(n)]


if __name__ == "__main__":
    import sys
    words = load_bds(sys.argv[1] if len(sys.argv) > 1 else "../factory-firmware-sm/ESX0102D.BDS")
    start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
    n = int(sys.argv[3], 0) if len(sys.argv) > 3 else 80
    for i in range(start, start + n):
        print(f"{i:05x}: {words[i]:08x}  {dis(words[i], i)}")
