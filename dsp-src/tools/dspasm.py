#!/usr/bin/env python3
"""Lossless uPD77213 (uPD77016 family) DSP disassembler and assembler for Korg ESX-1.

Verified against emu-sx/core/src/dsp.rs and 100% roundtrip-tested on ESX0102D.BDS.
"""
from __future__ import annotations
import re
import sys
from typing import Dict, List, Optional, Tuple

OPS3 = ["lt", "mul", "madd", "msub", "suma", "uuma", "mas1", "mas16",
        "add", "sub", "and", "or", "xor", "sra", "srl", "sll"]
OPS2 = ["nop", "clr", "inc", "dec", "abs", "not", "neg", "clip",
        "round", "exp", "put", "div", "acc+", "acc-"]
IMMOPS = ["add", "sub", "and", "or", "xor", "sra", "srl", "sll"]
MODI = ["nop", "", "++", "--", "##", "%%", "!##"]
COND = ["ever", "?1", "==0", "!=0", ">0", "<=0", ">=0", "<0", "==ex", "!=ex"]
SUFNAME = {0: "?0", 1: "l", 2: "h", 3: "?3", 4: "e", 5: "?5", 6: "eh", 7: ""}
SUFVAL = {"l": 1, "h": 2, "e": 4, "eh": 6, "": 7, "?0": 0, "?3": 3, "?5": 5}
XREG = [f"dp{i}" for i in range(8)] + [f"dn{i}" for i in range(8)] + ["dmx", "dmy"]
YREG = ["sr", "eir", "stack", "sp", "lc", "lsp", "lsr1", "lsr2", "lsr3", "esr"]

OPS3_MAP = {n: i for i, n in enumerate(OPS3)}
OPS2_MAP = {n: i for i, n in enumerate(OPS2)}
IMMOPS_MAP = {n: i + 8 for i, n in enumerate(IMMOPS)}
COND_MAP = {n: i for i, n in enumerate(COND) if not n.startswith("?")}
XREG_MAP = {n: i for i, n in enumerate(XREG)}
YREG_MAP = {n: i + 32 for i, n in enumerate(YREG)}
XYREG_MAP = {**XREG_MAP, **YREG_MAP}


def _mem_str(dp: int, modi: int) -> Optional[str]:
    if modi == 0:
        return None
    if modi == 1:
        return f"*dp{dp}"
    if modi == 6:
        return f"*!dp{dp}##"
    if modi < len(MODI):
        return f"*dp{dp}{MODI[modi]}"
    return f"*dp{dp}?{modi}"


def _ldst_par_str(w: int) -> str:
    out = []
    for (dxb, dpb, mb, rb, dpbase) in ((17, 14, 11, 8, 0), (16, 6, 3, 0, 4)):
        dx = (w >> dxb) & 1
        dp = ((w >> dpb) & 3) + dpbase
        modi = (w >> mb) & 7
        r = (w >> rb) & 7
        mem = _mem_str(dp, modi)
        if mem is None:
            continue
        out.append(f"r{r} = {mem}" if dx else f"{mem} = r{r}h")
    return " ".join(out)


def dis(w: int, pc: int = 0) -> str:
    """Disassemble one 32-bit uPD77213 instruction word at address `pc`."""
    top = w >> 28
    if top == 0:
        return {0: "nop", 1: "halt", 2: "lpop", 4: "fint", 9: "stop"}.get(w, f".word 0x{w:08x}")
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
        c = "" if cond == 0 else f"if (r{t} {COND[cond] if cond < len(COND) else f'?{cond}'}) "
        k = (w >> 26) & 3
        jc = (w >> 25) & 1
        if k == 3:
            rel = (w >> 7) & 0xFFFF
            rel = rel - 0x10000 if rel & 0x8000 else rel
            return f"{c}{'call' if jc else 'jmp'} {(pc + rel) & 0xFFFF:#x}"
        if k == 2:
            return f"{c}{'callr' if jc else 'jp'} dp{(w >> 17) & 7}"
        if k == 1:
            return f"{c}{'reti' if jc else 'ret'}"
        return f".word 0x{w:08x}"
    if top == 3:
        cond, t = (w >> 3) & 15, w & 7
        c = "" if cond == 0 else f"if (r{t} {COND[cond] if cond < len(COND) else f'?{cond}'}) "
        k = (w >> 26) & 3
        d = (w >> 16) & 1
        if k == 2:
            imm = w & 0xFFFF
            if d == 0:
                i = (w >> 17) & 0x3F
                nm = XREG[i] if i < len(XREG) else f"xreg{i}"
                return f"{nm} = {imm:#x}"
            return f"r{(w >> 23) & 7}l = {imm:#x}"
        if k == 3:
            a = (w >> 23) & 7
            b6 = (w >> 17) & 0x3F
            sel = (w >> 22) & 1
            idx = (b6 & 0x1F) | (sel << 5)
            name = XREG[idx] if idx < len(XREG) else (YREG[idx - 32] if 32 <= idx < 32 + len(YREG) else f"xreg{idx}")
            return f"{c}{name} = r{a}l" if d == 0 else f"{c}r{a}l = {name}"
        return f".word 0x{w:08x}"
    if top == 4:
        k = (w >> 26) & 3
        if k == 3:
            out = []
            for (sb, db, dpb, mb, rb, dpbase) in ((23, 17, 14, 11, 8, 0), (20, 16, 6, 3, 0, 4)):
                suf = (w >> sb) & 7
                d = (w >> db) & 1
                dp = ((w >> dpb) & 3) + dpbase
                modi = (w >> mb) & 7
                r = (w >> rb) & 7
                mem = _mem_str(dp, modi)
                if mem is None:
                    continue
                s = SUFNAME[suf]
                out.append(f"{mem} = r{r}{s}" if d == 0 else f"r{r}{s} = {mem}")
            return " ".join(out) or "pnop"
        d = (w >> 16) & 1
        suf = (w >> 20) & 7
        r = (w >> 23) & 7
        s = SUFNAME[suf]
        if k == 2:
            xy = "xy"[(w >> 19) & 1]
            a = w & 0xFFFF
            return f"*{xy}:{a:#06x} = r{r}{s}" if d == 0 else f"r{r}{s} = *{xy}:{a:#06x}"
        if k == 1:
            dp = (w >> 17) & 7
            imm = w & 0xFFFF
            imm = imm - 0x10000 if imm & 0x8000 else imm
            return f"*dp{dp}##{imm} = r{r}{s}" if d == 0 else f"r{r}{s} = *dp{dp}##{imm}"
        return f".word 0x{w:08x}"
    if top == 5:
        op = (w >> 24) & 15
        nm = IMMOPS[op - 8] if 8 <= op < 16 else f"?{op}"
        return f"r{(w >> 18) & 7} = r{(w >> 21) & 7} {nm} {w & 0xFFFF:#x}"
    if top == 6:
        op = (w >> 24) & 15
        cond, t = (w >> 3) & 15, w & 7
        c = "" if cond == 0 else f"if (r{t} {COND[cond] if cond < len(COND) else f'?{cond}'}) "
        nm = OPS2[op] if op < len(OPS2) else f"?{op}"
        return f"{c}{nm} r{(w >> 18) & 7} <- r{(w >> 21) & 7}"
    if top == 7:
        op = (w >> 24) & 15
        nm = OPS2[op] if op < len(OPS2) else f"?{op}"
        s = f"{nm} r{(w >> 18) & 7} <- r{(w >> 21) & 7}"
        par = _ldst_par_str(w)
        return f"{s} {par}" if par else s
    op1 = (w >> 28) & 7
    op = (w >> 24) & 15
    op2 = (w >> 21) & 7
    op3 = (w >> 18) & 7
    s = f"r{op3} = {OPS3[op]} r{op1}, r{op2}"
    par = _ldst_par_str(w)
    return f"{s} {par}" if par else s


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

_RE_COND = re.compile(r"^if\s*\(\s*r([0-7])\s*(==0|!=0|>=0|<=0|>0|<0|==ex|!=ex)\s*\)\s*(.*)$")
_RE_MEM = re.compile(r"^\*(!)?dp([0-7])(\+\+|--|##|%%)?$")
_RE_REG_SUF = re.compile(r"^r([0-7])(eh|l|h|e)?$")


def _parse_int(tok: str, labels: Dict[str, int]) -> int:
    tok = tok.strip()
    if tok in labels:
        return labels[tok]
    # Support simple label+offset / label-offset
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*([+-])\s*(0x[0-9a-fA-F]+|\d+)$", tok)
    if m and m.group(1) in labels:
        v = labels[m.group(1)]
        o = int(m.group(3), 0)
        return v + o if m.group(2) == "+" else v - o
    return int(tok, 0)


def _parse_mem(tok: str) -> Tuple[int, int]:
    """Parse *dpN[++|--|##|%%] or *!dpN## -> (dp, modi)."""
    m = _RE_MEM.match(tok.strip())
    if not m:
        raise ValueError(f"Bad memory operand: {tok!r}")
    bang, dp_s, mod_s = m.groups()
    dp = int(dp_s)
    if bang:
        if mod_s != "##":
            raise ValueError(f"Bit-reverse requires ##: {tok!r}")
        return dp, 6
    if mod_s is None:
        return dp, 1
    return dp, {"++": 2, "--": 3, "##": 4, "%%": 5}[mod_s]


def _parse_xy_moves(text: str, allow_suf: bool) -> Tuple[Optional[Tuple[int, int, int, int, int]], Optional[Tuple[int, int, int, int, int]]]:
    """Parse 0, 1, or 2 XY memory moves separated by whitespace.
    Returns (x_move, y_move) where each move is (dir, dp_off, modi, reg, suf).
    dir: 1 = load (r = *dp), 0 = store (*dp = r).
    """
    text = text.strip()
    if not text:
        return None, None
    # Match individual moves: either `rN[suf] = *...` or `*... = rN[suf]`
    pat = re.compile(
        r"(?:r([0-7])(eh|l|h|e)?\s*=\s*(\*!?dp[0-7](?:\+\+|--|##|%%)?))"
        r"|(?:(\*!?dp[0-7](?:\+\+|--|##|%%)?)\s*=\s*r([0-7])(eh|l|h|e)?)"
    )
    pos = 0
    xm = ym = None
    for m in pat.finditer(text):
        if text[pos:m.start()].strip():
            raise ValueError(f"Unexpected tokens in parallel moves: {text[pos:m.start()]!r} in {text!r}")
        pos = m.end()
        if m.group(1) is not None:
            d = 1
            reg = int(m.group(1))
            suf_s = m.group(2) or ""
            dp, modi = _parse_mem(m.group(3))
        else:
            d = 0
            dp, modi = _parse_mem(m.group(4))
            reg = int(m.group(5))
            suf_s = m.group(6) or ""
        if not allow_suf:
            if d == 1 and suf_s != "":
                raise ValueError(f"Parallel load cannot have suffix {suf_s!r}: {text!r}")
            if d == 0 and suf_s not in ("h", ""):
                raise ValueError(f"Parallel store uses rNh: {text!r}")
            suf = 0
        else:
            suf = SUFVAL[suf_s]
        if dp < 4:
            if xm is not None:
                raise ValueError(f"Duplicate X-bus move: {text!r}")
            xm = (d, dp, modi, reg, suf)
        else:
            if ym is not None:
                raise ValueError(f"Duplicate Y-bus move: {text!r}")
            ym = (d, dp - 4, modi, reg, suf)
    if text[pos:].strip():
        raise ValueError(f"Trailing tokens in parallel moves: {text[pos:]!r} in {text!r}")
    return xm, ym


def _encode_par(xm, ym) -> int:
    w = 0
    if xm is not None:
        d, dp, modi, reg, _ = xm
        w |= (d << 17) | (dp << 14) | (modi << 11) | (reg << 8)
    if ym is not None:
        d, dp, modi, reg, _ = ym
        w |= (d << 16) | (dp << 6) | (modi << 3) | reg
    return w


def asm_one(line: str, pc: int, labels: Dict[str, int]) -> int:
    """Assemble one uPD77213 instruction string at address `pc`."""
    s = line.strip()
    # Raw .word
    m = re.match(r"^\.word\s+(.+)$", s)
    if m:
        return _parse_int(m.group(1), labels) & 0xFFFFFFFF

    # top == 0
    if s in ("nop", "halt", "lpop", "fint", "stop"):
        return {"nop": 0, "halt": 1, "lpop": 2, "fint": 4, "stop": 9}[s]
    if s == "pnop":
        return 0x4C000000

    # top == 1: repeat / loop
    m = re.match(r"^repeat\s+r([0-7])l$", s)
    if m:
        return 0x18000000 | int(m.group(1))
    m = re.match(r"^repeat\s+(.+)$", s)
    if m:
        cnt = _parse_int(m.group(1), labels)
        if not (0 <= cnt <= 0x7FFF):
            raise ValueError(f"repeat count out of range: {cnt}")
        return 0x1C000000 | cnt
    m = re.match(r"^loop\s+r([0-7])l\s*\{\s*end=\+(.+)$", s)
    if m:
        end = _parse_int(m.group(2), labels)
        return 0x10000000 | ((end & 0xFF) << 16) | int(m.group(1))
    m = re.match(r"^loop\s+r([0-7])l\s*,\s*(.+)$", s)
    if m:
        target = _parse_int(m.group(2), labels)
        end = (target - pc) & 0xFF
        return 0x10000000 | (end << 16) | int(m.group(1))
    m = re.match(r"^loop\s+([^,{]+?)\s*\{\s*end=\+(.+)$", s)
    if m:
        cnt = _parse_int(m.group(1), labels)
        end = _parse_int(m.group(2), labels)
        return 0x14000000 | ((end & 0xFF) << 16) | (cnt & 0x7FFF)
    m = re.match(r"^loop\s+([^,]+?)\s*,\s*(.+)$", s)
    if m:
        cnt = _parse_int(m.group(1), labels)
        target = _parse_int(m.group(2), labels)
        end = (target - pc) & 0xFF
        return 0x14000000 | (end << 16) | (cnt & 0x7FFF)

    # Check optional condition prefix: if (rT COND) ...
    cond_bits = 0
    has_cond = False
    mc = _RE_COND.match(s)
    if mc:
        has_cond = True
        cond_bits = (COND_MAP[mc.group(2)] << 3) | int(mc.group(1))
        body = mc.group(3).strip()
    else:
        body = s

    # top == 2: jmp / call / jp / callr / ret / reti
    if body in ("ret", "reti"):
        jc = 1 if body == "reti" else 0
        return 0x24000000 | (jc << 25) | cond_bits
    m = re.match(r"^(jp|callr)\s+dp([0-7])$", body)
    if m:
        jc = 1 if m.group(1) == "callr" else 0
        return 0x28000000 | (jc << 25) | (int(m.group(2)) << 17) | cond_bits
    m = re.match(r"^(jmp|call)\s+(.+)$", body)
    if m:
        jc = 1 if m.group(1) == "call" else 0
        target = _parse_int(m.group(2), labels)
        rel = (target - pc) & 0xFFFF
        return 0x2C000000 | (jc << 25) | (rel << 7) | cond_bits

    # top == 6 / 7: 2-operand ALU (conditional or with parallel XY moves)
    m = re.match(r"^(nop|clr|inc|dec|abs|not|neg|clip|round|exp|put|div|acc\+|acc-)\s+r([0-7])\s*<-\s*r([0-7])(.*)$", body)
    if m:
        op = OPS2_MAP[m.group(1)]
        d = int(m.group(2))
        a = int(m.group(3))
        rest = m.group(4).strip()
        if has_cond:
            if rest:
                raise ValueError(f"Conditional ALU2 cannot have parallel moves: {s!r}")
            return (6 << 28) | (op << 24) | (a << 21) | (d << 18) | cond_bits
        if rest:
            xm, ym = _parse_xy_moves(rest, allow_suf=False)
            return (7 << 28) | (op << 24) | (a << 21) | (d << 18) | _encode_par(xm, ym)
        return (6 << 28) | (op << 24) | (a << 21) | (d << 18)

    # top == 3 (k=3): conditional or unconditional inter-register transfer
    m = re.match(r"^r([0-7])l\s*=\s*([a-z0-9]+)$", body)
    if m and (m.group(2) in XYREG_MAP or m.group(2).startswith("xreg")):
        a = int(m.group(1))
        nm = m.group(2)
        idx = XYREG_MAP[nm] if nm in XYREG_MAP else int(nm[4:])
        b6 = (idx & 0x1F) | (((idx >> 5) & 1) << 5)
        return 0x3C000000 | (a << 23) | (b6 << 17) | (1 << 16) | cond_bits
    m = re.match(r"^([a-z0-9]+)\s*=\s*r([0-7])l$", body)
    if m and (m.group(1) in XYREG_MAP or m.group(1).startswith("xreg")):
        nm = m.group(1)
        a = int(m.group(2))
        idx = XYREG_MAP[nm] if nm in XYREG_MAP else int(nm[4:])
        b6 = (idx & 0x1F) | (((idx >> 5) & 1) << 5)
        return 0x3C000000 | (a << 23) | (b6 << 17) | cond_bits

    if has_cond:
        raise ValueError(f"Unsupported conditional instruction: {s!r}")

    # top == 8..15: 3-operand ALU with optional parallel XY moves
    m = re.match(r"^r([0-7])\s*=\s*(lt|mul|madd|msub|suma|uuma|mas16|mas1|add|sub|and|or|xor|sra|srl|sll)\s+r([0-7])\s*,\s*r([0-7])(.*)$", s)
    if m:
        d = int(m.group(1))
        op = OPS3_MAP[m.group(2)]
        a = int(m.group(3))
        b = int(m.group(4))
        rest = m.group(5).strip()
        xm, ym = _parse_xy_moves(rest, allow_suf=False)
        return (1 << 31) | (a << 28) | (op << 24) | (b << 21) | (d << 18) | _encode_par(xm, ym)

    # top == 5: ALU immediate: rD = rA OP IMM16
    m = re.match(r"^r([0-7])\s*=\s*r([0-7])\s+(add|sub|and|or|xor|sra|srl|sll)\s+(.+)$", s)
    if m:
        d = int(m.group(1))
        a = int(m.group(2))
        op = IMMOPS_MAP[m.group(3)]
        imm = _parse_int(m.group(4), labels) & 0xFFFF
        return (5 << 28) | (op << 24) | (a << 21) | (d << 18) | imm

    # top == 4 (k=2): direct memory load/store
    m = re.match(r"^r([0-7])(eh|l|h|e)?\s*=\s*\*([xy]):(.+)$", s)
    if m:
        r = int(m.group(1))
        suf = SUFVAL[m.group(2) or ""]
        y = 1 if m.group(3) == "y" else 0
        addr = _parse_int(m.group(4), labels) & 0xFFFF
        return 0x48000000 | (r << 23) | (suf << 20) | (y << 19) | (1 << 16) | addr
    m = re.match(r"^\*([xy]):([^=]+?)\s*=\s*r([0-7])(eh|l|h|e)?$", s)
    if m:
        y = 1 if m.group(1) == "y" else 0
        addr = _parse_int(m.group(2), labels) & 0xFFFF
        r = int(m.group(3))
        suf = SUFVAL[m.group(4) or ""]
        return 0x48000000 | (r << 23) | (suf << 20) | (y << 19) | addr

    # top == 4 (k=1): immediate-modify pointer load/store
    m = re.match(r"^r([0-7])(eh|l|h|e)?\s*=\s*\*dp([0-7])##(\S+)$", s)
    if m:
        r = int(m.group(1))
        suf = SUFVAL[m.group(2) or ""]
        dp = int(m.group(3))
        imm = _parse_int(m.group(4), labels) & 0xFFFF
        return 0x44000000 | (r << 23) | (suf << 20) | (dp << 17) | (1 << 16) | imm
    m = re.match(r"^\*dp([0-7])##(\S+)\s*=\s*r([0-7])(eh|l|h|e)?$", s)
    if m:
        dp = int(m.group(1))
        imm = _parse_int(m.group(2), labels) & 0xFFFF
        r = int(m.group(3))
        suf = SUFVAL[m.group(4) or ""]
        return 0x44000000 | (r << 23) | (suf << 20) | (dp << 17) | imm

    # top == 3 (k=2): immediate set (rNl = IMM16 or dpN/dnN/dmx/dmy = IMM16)
    m = re.match(r"^r([0-7])l\s*=\s*(.+)$", s)
    if m and "*" not in m.group(2):
        r = int(m.group(1))
        imm = _parse_int(m.group(2), labels) & 0xFFFF
        return 0x38000000 | (r << 23) | (1 << 16) | imm
    m = re.match(r"^([a-z0-9]+)\s*=\s*([^=*]+)$", s)
    if m and (m.group(1) in XREG_MAP or m.group(1).startswith("xreg")):
        nm = m.group(1)
        idx = XREG_MAP[nm] if nm in XREG_MAP else int(nm[4:])
        imm = _parse_int(m.group(2), labels) & 0xFFFF
        return 0x38000000 | ((idx & 0x3F) << 17) | imm

    # top == 4 (k=3): single or dual partial load/store via *dpN
    if "*dp" in s or "*!dp" in s:
        xm, ym = _parse_xy_moves(s, allow_suf=True)
        if xm is not None or ym is not None:
            w = 0x4C000000
            if xm is not None:
                d, dp, modi, reg, suf = xm
                w |= (suf << 23) | (d << 17) | (dp << 14) | (modi << 11) | (reg << 8)
            if ym is not None:
                d, dp, modi, reg, suf = ym
                w |= (suf << 20) | (d << 16) | (dp << 6) | (modi << 3) | reg
            return w

    raise ValueError(f"Cannot assemble uPD77213 instruction at 0x{pc:04x}: {s!r}")


def assemble_source(text: str, start_pc: int = 0x0200, base_labels: Optional[Dict[str, int]] = None) -> Tuple[Dict[int, int], Dict[str, int]]:
    """Two-pass assembler supporting `.org ADDR`, `.equ NAME, VAL`, `label:`, `;` / `//` comments.
    Returns ({pc: word32}, labels).
    """
    labels: Dict[str, int] = dict(base_labels or {})
    items: List[Tuple[int, int, str]] = []  # (line_no, pc, insn_str)
    pc = start_pc

    # Pass 1: collect labels, .equ, .org, and instruction PCs
    for line_no, raw in enumerate(text.splitlines(), 1):
        # Strip comments (; or // or # when not ##)
        line = re.sub(r"(;|//).*$", "", raw).strip()
        if not line:
            continue
        # .equ NAME, VALUE
        m = re.match(r"^\.equ\s+([A-Za-z_][A-Za-z0-9_]*)\s*,?\s*(.+)$", line)
        if m:
            labels[m.group(1)] = _parse_int(m.group(2), labels)
            continue
        # .org ADDR
        m = re.match(r"^\.org\s+(.+)$", line)
        if m:
            pc = _parse_int(m.group(1), labels)
            continue
        # Labels (one or more `name:`)
        while True:
            ml = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if not ml:
                break
            labels[ml.group(1)] = pc
            line = ml.group(2).strip()
        if not line:
            continue
        items.append((line_no, pc, line))
        pc += 1

    # Pass 2: assemble every instruction
    out: Dict[int, int] = {}
    for line_no, ipc, insn in items:
        try:
            out[ipc] = asm_one(insn, ipc, labels)
        except Exception as e:
            raise ValueError(f"Line {line_no} (0x{ipc:04X}): {e}") from e
    return out, labels


def self_test_bds(bds_path: str) -> None:
    d = open(bds_path, "rb").read()
    n = 0x56E8 // 4
    mismatches = 0
    for i in range(n):
        pc = i + 0x200
        lo = int.from_bytes(d[0x50 + 4 * i: 0x50 + 4 * i + 2], "big")
        hi = int.from_bytes(d[0x50 + 4 * i + 2: 0x50 + 4 * i + 4], "big")
        w = (hi << 16) | lo
        s = dis(w, pc)
        w2 = asm_one(s, pc, {})
        if w2 != w:
            mismatches += 1
            if mismatches <= 25:
                print(f"MISMATCH {pc:04X}: orig={w:08X} reasm={w2:08X} diff={w^w2:08X}  {s}")
    print(f"Self-test on {bds_path}: {n - mismatches}/{n} exact matches ({mismatches} mismatches)")
    if mismatches:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        self_test_bds(sys.argv[2])
    else:
        print("Usage: dspasm.py --selftest <ESX0102D.BDS>")
