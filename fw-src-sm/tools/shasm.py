#!/usr/bin/env python3
"""shasm - a small two-pass SH-3 (SH7709) assembler producing a flat binary image at absolute addresses.

Usage:  shasm.py [-o out.bin] [--map out.map] [-I dir] [--strict] [--base ADDR] [--list out.lst] file.s [file2.s ...]

Source syntax (one statement per line, ';' starts a comment):
    label:                      defines a label (address of the next byte); several per line are fine
    name = expr                 symbol assignment      (also  .equ name, expr / .set name, expr)
    mnemonic operands           SH-3 instruction, operand order source,destination (see shisa.py for the full set)
    .org  addr[, fill]          continue at absolute address addr (gap filled with `fill`, or --fill; --strict forbids gaps without explicit fill)
    .align n[,fill[,unit]]      pad to a multiple of n bytes; fill value of unit 1 (default) or 2 bytes (big endian pattern, phase = address)
    .byte / .word / .long       comma separated expressions (big-endian)
    .ascii / .asciz / .string   string data (C escapes \\n \\t \\r \\0 \\\\ \\" \\xHH \\ooo)
    .space n[,fill] / .fill n[,fill]
    .incbin "file"[,offset[,length]]
    .include "file"
    .pool / .ltorg              emit the pending literal pool (see below) here, aligned to 4
    .assert expr[,"message"]    assembly error if expr is zero
    .copylong src, n            emit n 32-bit words copied from the finished main image at address `src` (overlay only; pass 2)
    .patchlong addr, new, old   (overlay only) replace the 32-bit word at `addr` of the main image by `new`; `old` is the value the word
                                must have in the factory image (build.py checks it) - retargets ONE pointer word (e.g. a single literal
                                pool entry) where .redirect would change all references of a symbol
    .redirect old, new          every reference to symbol `old` evaluates to `new` instead; the real address of `old` stays
                                available as `old__vanilla` (used by the Newtribe overlay to retarget pointers, see README)
    .global/.text/.data/.section/.type/.size   accepted and ignored
Operands:  r0..r15  #imm  @rN  @rN+  @-rN  @(disp,rN)  @(r0,rN)  @(disp,gbr)  @(r0,gbr)  @(addr,pc)  sr gbr vbr ssr spc mach macl pr  rN_bank
           branch targets are plain expressions (absolute addresses / labels).
PC relative literals: `mov.l @(label,pc),r1` names the ADDRESS of the literal (the assembler computes the displacement and
reports a clear error when it is out of range or misaligned).  `mov.l =expr,r1` / `mov.w =expr,r1` put expr in the next
`.pool` automatically (entries with identical text are shared).
Expressions: + - * / % << >> & | ^ ~ ( ) decimal 0x.. 0b.. 'c'  symbols  `.` (current address)
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shisa

REG_RE = re.compile(r"^r(\d{1,2})$", re.I)
IDENT = r"[A-Za-z_.$][A-Za-z0-9_.$]*"
CTRL = {"sr", "gbr", "vbr", "ssr", "spc", "mach", "macl", "pr"}


class AsmError(Exception):
    pass


# ---------------------------------------------------------------------------------------------- expressions
_TOK = re.compile(r"\s*(?:(0[xX][0-9A-Fa-f_]+|0[bB][01_]+|\d+)|('(?:\\.|[^'\\])')|(%s)|(<<|>>|[-+*/%%&|^~()]))" % IDENT)


class Expr:
    """Parsed expression; evaluate with a symbol lookup function."""
    __slots__ = ("ast", "text")

    def __init__(self, text):
        self.text = text.strip()
        toks = []
        pos = 0
        s = self.text
        while pos < len(s):
            if s[pos:].strip() == "":
                break
            m = _TOK.match(s, pos)
            if not m:
                raise AsmError("bad expression %r near %r" % (s, s[pos:pos + 10]))
            pos = m.end()
            if m.group(1) is not None:
                t = m.group(1).replace("_", "").lower()
                toks.append(("n", int(t, 0)))
            elif m.group(2) is not None:
                c = m.group(2)[1:-1]
                if c.startswith("\\"):
                    c = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", "'": "'"}.get(c[1], c[1])
                toks.append(("n", ord(c)))
            elif m.group(3) is not None:
                toks.append(("s", m.group(3)))
            else:
                toks.append(("o", m.group(4)))
        self.ast = self._parse(toks)

    def _parse(self, toks):
        pos = [0]

        def peek():
            return toks[pos[0]] if pos[0] < len(toks) else (None, None)

        def take():
            t = toks[pos[0]]
            pos[0] += 1
            return t

        levels = [["|"], ["^"], ["&"], ["<<", ">>"], ["+", "-"], ["*", "/", "%"]]

        def binary(lv):
            if lv == len(levels):
                return unary()
            left = binary(lv + 1)
            while True:
                k, v = peek()
                if k == "o" and v in levels[lv]:
                    take()
                    right = binary(lv + 1)
                    left = ("b", v, left, right)
                else:
                    return left

        def unary():
            k, v = peek()
            if k == "o" and v in ("-", "+", "~"):
                take()
                return ("u", v, unary())
            return atom()

        def atom():
            if pos[0] >= len(toks):
                raise AsmError("unexpected end of expression %r" % self.text)
            k, v = take()
            if k == "n":
                return ("n", v)
            if k == "s":
                return ("s", v)
            if k == "o" and v == "(":
                e = binary(0)
                k2, v2 = peek()
                if (k2, v2) != ("o", ")"):
                    raise AsmError("missing ) in %r" % self.text)
                take()
                return e
            raise AsmError("unexpected %r in expression %r" % (v, self.text))

        e = binary(0)
        if pos[0] != len(toks):
            raise AsmError("trailing junk in expression %r" % self.text)
        return e

    def eval(self, lookup):
        return self._ev(self.ast, lookup)

    def _ev(self, a, lookup):
        t = a[0]
        if t == "n":
            return a[1]
        if t == "s":
            return lookup(a[1])
        if t == "u":
            v = self._ev(a[2], lookup)
            return -v if a[1] == "-" else (~v if a[1] == "~" else v)
        op = a[1]
        x = self._ev(a[2], lookup)
        y = self._ev(a[3], lookup)
        if op == "+":
            return x + y
        if op == "-":
            return x - y
        if op == "*":
            return x * y
        if op == "/":
            if y == 0:
                raise AsmError("division by zero in %r" % self.text)
            return int(x / y) if (x < 0) != (y < 0) else x // y
        if op == "%":
            return x % y
        if op == "<<":
            return x << y
        if op == ">>":
            return x >> y
        if op == "&":
            return x & y
        if op == "|":
            return x | y
        if op == "^":
            return x ^ y
        raise AsmError("bad operator")


# ---------------------------------------------------------------------------------------------- instruction templates
def _tmpl_regex(op):
    """Compile an operand template (e.g. '@({d4},r{m})') into (regex, [placeholder names])."""
    names = []
    out = ""
    i = 0
    while i < len(op):
        ch = op[i]
        if ch == "{":
            j = op.index("}", i)
            nm = op[i + 1:j]
            names.append(nm)
            if nm in ("n", "m", "b"):
                out += r"(\d{1,2})"
            else:
                out += r"(.+?)"
            i = j + 1
        else:
            out += re.escape(ch)
            i += 1
    return re.compile("^" + out + "$", re.I), names


_TEMPLATES = {}
for _ins in shisa.INSNS:
    _TEMPLATES.setdefault((_ins.mn, len(_ins.ops)), []).append(
        (_ins, [_tmpl_regex(o) for o in _ins.ops]))


_MNEMONICS = {k[0] for k in _TEMPLATES}


def norm_operand(s):
    s = s.strip()
    s = re.sub(r"\s+", "", s) if not s.startswith("=") and "'" not in s else s
    return s


def split_operands(s):
    return [norm_operand(x) for x in shisa.split_ops(s)] if s.strip() else []


# ---------------------------------------------------------------------------------------------- the assembler
_CUR_SECT = [0]      # section of the statements being parsed: 0 = main image, 1 = overlay (own location counter / pool)


class Stmt:
    __slots__ = ("kind", "addr", "size", "a", "file", "line", "extra", "sect")

    def __init__(self, kind, file, line, a=None):
        self.kind = kind
        self.file = file
        self.line = line
        self.a = a
        self.addr = 0
        self.size = 0
        self.extra = None
        self.sect = _CUR_SECT[0]


class Assembler:
    def __init__(self, incdirs=(), strict=False, fill=0):
        self.stmts = []
        self.syms = {}          # name -> int or Expr (lazy)
        self.symsrc = {}
        self.incdirs = list(incdirs)
        self.strict = strict
        self.fill = fill
        self.base = None
        self.end = None
        self._resolving = set()
        self.pools = []         # list of pool blocks: dict(word=[exprs], long=[exprs], addr)
        self._open_pool = None
        self.warnings = []
        self.redirects = []     # (old, new) from .redirect
        self.patches = []       # (addr, new, expected_old) from .patchlong (pass2)
        self.overlay = []       # [(address, bytes)] result of pass2 for the overlay section
        self.ovl_base = None
        self.ovl_end = None

    # --- parsing
    def error(self, st, msg):
        raise AsmError("%s:%d: %s" % (st.file, st.line, msg))

    def add_file(self, path, overlay=False):
        """Parse a source file.  overlay=True: the statements form the OVERLAY section - it has its own location counter and
        literal pool, is assembled in the same symbol space (labels of both sections see each other) and is returned
        separately by pass2 (self.overlay) so that the caller can lay it over a gap of the main image."""
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().split("\n")
        old = _CUR_SECT[0]
        _CUR_SECT[0] = 1 if overlay else old
        try:
            self.parse_lines(lines, path)
        finally:
            _CUR_SECT[0] = old

    @staticmethod
    def strip_comment(line):
        inq = None
        i = 0
        while i < len(line):
            c = line[i]
            if inq:
                if c == "\\":
                    i += 1
                elif c == inq:
                    inq = None
            else:
                if c == '"':
                    inq = c
                elif c == "'" and i + 2 < len(line) and (line[i + 2] == "'" or line[i + 1] == "\\"):
                    inq = c
                elif c == ";":
                    return line[:i]
            i += 1
        return line

    def parse_lines(self, lines, fname):
        label_re = re.compile(r"^\s*(%s)\s*:" % IDENT)
        for ln, raw in enumerate(lines, 1):
            line = self.strip_comment(raw).rstrip()
            while True:
                m = label_re.match(line)
                if not m:
                    break
                st = Stmt("label", fname, ln, m.group(1))
                self.stmts.append(st)
                line = line[m.end():]
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(%s)\s*=\s*(.+)$" % IDENT, line)
            if m and not line.startswith(".") and m.group(1).lower() not in _MNEMONICS:
                st = Stmt("equ", fname, ln, (m.group(1), Expr(m.group(2))))
                self.stmts.append(st)
                continue
            parts = line.split(None, 1)
            mn = parts[0].lower()
            rest = parts[1] if len(parts) > 1 else ""
            if mn.startswith("."):
                self.parse_directive(mn, rest, fname, ln)
            else:
                st = Stmt("insn", fname, ln, (mn, split_operands(rest)))
                st.size = 2
                self.stmts.append(st)

    def parse_directive(self, d, rest, fname, ln):
        S = lambda k, a=None: self.stmts.append(Stmt(k, fname, ln, a))
        if d in (".global", ".globl", ".text", ".data", ".section", ".type", ".size", ".file", ".ident", ".weak", ".extern"):
            return
        if d == ".org":
            a_ = self.split_commas(rest)
            S("org", (Expr(a_[0]), Expr(a_[1]) if len(a_) > 1 else None))
        elif d in (".align", ".balign"):
            a_ = self.split_commas(rest)
            S("align", (Expr(a_[0]), Expr(a_[1]) if len(a_) > 1 else None, Expr(a_[2]) if len(a_) > 2 else None))
        elif d in (".byte", ".word", ".long", ".short", ".int"):
            sz = {".byte": 1, ".word": 2, ".short": 2, ".long": 4, ".int": 4}[d]
            S("data", (sz, [Expr(x) for x in self.split_commas(rest)]))
        elif d in (".ascii", ".asciz", ".string"):
            data = b""
            for s in self.split_commas(rest):
                data += self.parse_string(s, fname, ln)
                if d != ".ascii":
                    data += b"\0"
            S("bytes", data)
        elif d in (".space", ".fill", ".skip", ".zero"):
            a = self.split_commas(rest)
            S("space", (Expr(a[0]), Expr(a[1]) if len(a) > 1 else None))
        elif d == ".incbin":
            a = self.split_commas(rest)
            S("incbin", (self.parse_string(a[0], fname, ln).decode(), Expr(a[1]) if len(a) > 1 else None,
                         Expr(a[2]) if len(a) > 2 else None))
        elif d == ".include":
            p = self.parse_string(rest.strip(), fname, ln).decode()
            for base in [os.path.dirname(fname)] + self.incdirs:
                q = os.path.join(base, p)
                if os.path.exists(q):
                    self.add_file(q)
                    return
            raise AsmError("%s:%d: include file %r not found" % (fname, ln, p))
        elif d in (".pool", ".ltorg"):
            S("pool")
        elif d in (".equ", ".set"):
            a = self.split_commas(rest)
            S("equ", (a[0].strip(), Expr(a[1])))
        elif d == ".assert":
            a = self.split_commas(rest)
            S("assert", (Expr(a[0]), a[1] if len(a) > 1 else ""))
        elif d == ".print":
            S("print", rest)
        elif d == ".copylong":
            a = self.split_commas(rest)
            S("copylong", (Expr(a[0]), Expr(a[1])))
        elif d == ".patchlong":
            a = self.split_commas(rest)
            if len(a) != 3:
                raise AsmError("%s:%d: .patchlong addr, new, expected_old" % (fname, ln))
            S("patchlong", (Expr(a[0]), Expr(a[1]), Expr(a[2])))
        elif d == ".redirect":
            a = self.split_commas(rest)
            if len(a) != 2:
                raise AsmError("%s:%d: .redirect old, new" % (fname, ln))
            S("redirect", (a[0].strip(), a[1].strip()))
        else:
            raise AsmError("%s:%d: unknown directive %s" % (fname, ln, d))

    @staticmethod
    def split_commas(s):
        out, cur, inq, i = [], "", None, 0
        while i < len(s):
            c = s[i]
            if inq:
                cur += c
                if c == "\\":
                    i += 1
                    cur += s[i]
                elif c == inq:
                    inq = None
            elif c in "\"'":
                inq = c
                cur += c
            elif c == ",":
                out.append(cur.strip())
                cur = ""
            else:
                cur += c
            i += 1
        if cur.strip() or out:
            out.append(cur.strip())
        return out

    def parse_string(self, s, fname, ln):
        s = s.strip()
        if len(s) < 2 or s[0] != '"' or s[-1] != '"':
            raise AsmError("%s:%d: expected a quoted string, got %r" % (fname, ln, s))
        s = s[1:-1]
        out = bytearray()
        i = 0
        while i < len(s):
            c = s[i]
            if c == "\\":
                i += 1
                e = s[i]
                if e == "x":
                    out.append(int(s[i + 1:i + 3], 16))
                    i += 2
                elif e in "01234567":
                    j = i
                    while j < len(s) and j < i + 3 and s[j] in "01234567":
                        j += 1
                    out.append(int(s[i:j], 8) & 0xFF)
                    i = j - 1
                else:
                    out.append({"n": 10, "t": 9, "r": 13, "a": 7, "b": 8, "f": 12, "v": 11, "\\": 92, '"': 34, "'": 39}.get(e, ord(e)))
            else:
                out.extend(c.encode("latin-1"))
            i += 1
        return bytes(out)

    # --- symbol lookup
    def lookup(self, name):
        if name == ".":
            return self._cur
        v = self.syms.get(name)
        if v is None:
            raise AsmError("undefined symbol %s" % name)
        if isinstance(v, Expr):
            if name in self._resolving:
                raise AsmError("circular definition of %s" % name)
            self._resolving.add(name)
            try:
                r = v.eval(self.lookup)
            finally:
                self._resolving.discard(name)
            self.syms[name] = r
            return r
        return v

    def ev(self, st, expr, addr=None):
        self._cur = st.addr if addr is None else addr
        try:
            return expr.eval(self.lookup)
        except AsmError as e:
            self.error(st, str(e))

    # --- pass 1
    def pass1(self):
        pc = None
        self._cur = 0
        pending_w, pending_l = {}, {}
        pools = []
        new_pool = lambda: {"word": [], "long": [], "wkeys": {}, "lkeys": {}}
        cur_pool = new_pool()
        sect_state = {0: [None, cur_pool], 1: [None, new_pool()]}    # section -> [pc, pool]
        cur_sect = 0
        self.ovl_base = None
        self.ovl_end = None
        self.redirects = []

        for st in self.stmts:
            k = st.kind
            if st.sect != cur_sect:                 # switch location counter / literal pool between main image and overlay
                sect_state[cur_sect] = [pc, cur_pool]
                cur_sect = st.sect
                pc, cur_pool = sect_state[cur_sect]
            if k != "org" and pc is None and k not in ("equ", "assert", "print"):
                self.error(st, "no .org before the first item")
            if k == "org":
                self._cur = pc if pc is not None else 0
                st.addr = pc if pc is not None else 0
                v = self.ev(st, st.a[0])
                if pc is None:
                    if cur_sect == 0:
                        self.base = v
                    else:
                        self.ovl_base = v
                elif v < pc:
                    self.error(st, ".org 0x%X goes backwards: the code before it ends at 0x%X, %d bytes too far" % (v, pc, pc - v))
                elif v > pc and self.strict and st.a[1] is None:
                    self.error(st, "gap of %d bytes before .org 0x%X in strict mode (use `.org addr, fill` to allow it)" % (v - pc, v))
                st.size = v - pc if pc is not None else 0
                st.addr = pc if pc is not None else v
                pc = v
                continue
            st.addr = pc if pc is not None else 0
            if k == "label":
                if st.a in self.syms:
                    self.error(st, "symbol %s redefined" % st.a)
                self.syms[st.a] = st.addr
                self.symsrc[st.a] = (st.file, st.line)
            elif k == "equ":
                name, ex = st.a
                if name in self.syms:
                    self.error(st, "symbol %s redefined" % name)
                if REG_RE.match(name) or name.lower() in CTRL:
                    self.error(st, "symbol name %s collides with a register" % name)
                self.syms[name] = ex
                self.symsrc[name] = (st.file, st.line)
            elif k == "insn":
                mn, ops = st.a
                if any(o.startswith("=") for o in ops):
                    which = "word" if mn == "mov.w" else "long" if mn == "mov.l" else None
                    if which is None:
                        self.error(st, "'=expr' literal only allowed with mov.w / mov.l")
                    key = ops[0][1:].strip()
                    keys = cur_pool["wkeys" if which == "word" else "lkeys"]
                    if key not in keys:
                        keys[key] = len(cur_pool[which])
                        cur_pool[which].append(Expr(key))
                    st.extra = (cur_pool, which, key)
                pc += 2
            elif k == "data":
                sz, lst = st.a
                st.size = sz * len(lst)
                pc += st.size
            elif k == "bytes":
                st.size = len(st.a)
                pc += st.size
            elif k == "space":
                n = self.ev(st, st.a[0])
                st.size = n
                pc += n
            elif k == "incbin":
                path = None
                for base in [os.path.dirname(st.file)] + self.incdirs:
                    q = os.path.join(base, st.a[0])
                    if os.path.exists(q):
                        path = q
                        break
                if path is None:
                    self.error(st, "incbin file %r not found" % st.a[0])
                data = open(path, "rb").read()
                off = self.ev(st, st.a[1]) if st.a[1] else 0
                ln = self.ev(st, st.a[2]) if st.a[2] else len(data) - off
                st.extra = data[off:off + ln]
                if len(st.extra) != ln:
                    self.error(st, "incbin: file too short")
                st.size = ln
                pc += ln
            elif k == "align":
                n = self.ev(st, st.a[0])
                new = (pc + n - 1) // n * n
                st.size = new - pc
                pc = new
            elif k == "pool":
                p = cur_pool
                start = pc
                words = len(p["word"])
                n = start
                n += 2 * words
                if p["long"]:
                    n = (n + 3) // 4 * 4
                p["addr"] = start
                p["waddr"] = start
                p["laddr"] = n
                st.extra = p
                st.size = (n + 4 * len(p["long"])) - start
                pc = n + 4 * len(p["long"])
                pools.append(p)
                cur_pool = {"word": [], "long": [], "wkeys": {}, "lkeys": {}}
            elif k == "copylong":
                st.size = 4 * self.ev(st, st.a[1])
                pc += st.size
            elif k == "redirect":
                self.redirects.append(st.a)
            elif k in ("assert", "print", "patchlong"):
                pass
        sect_state[cur_sect] = [pc, cur_pool]
        pc, cur_pool = sect_state[0]
        if sect_state[1][1]["word"] or sect_state[1][1]["long"]:
            raise AsmError("overlay: literal pool pending at end of input (add an explicit .pool)")
        self.ovl_end = sect_state[1][0]
        for old, new in self.redirects:
            if old not in self.syms:
                raise AsmError(".redirect: undefined symbol %s" % old)
            if new not in self.syms:
                raise AsmError(".redirect: undefined target symbol %s" % new)
            self.syms[old + "__vanilla"] = self.syms[old]
            self.syms[old] = Expr(new)
        if cur_pool["word"] or cur_pool["long"]:
            # implicit pool at the end
            st = Stmt("pool", "<end>", 0)
            st.addr = pc
            p = cur_pool
            words = len(p["word"])
            n = pc + 2 * words
            if p["long"]:
                n = (n + 3) // 4 * 4
            p["waddr"], p["laddr"] = pc, n
            st.extra = p
            st.size = n + 4 * len(p["long"]) - pc
            self.stmts.append(st)
            pc = n + 4 * len(p["long"])
            self.warnings.append("literal pool at end of input (add an explicit .pool)")
        self.end = pc

    # --- pass 2
    def pass2(self, listing=None):
        base = self.base
        main = [s for s in self.stmts if s.sect == 0]
        ovl = [s for s in self.stmts if s.sect == 1]
        self.overlay = []
        self.patches = []
        data = self._pass2_section(main, base, self.end, None)
        if ovl:
            ob = self._pass2_section(ovl, self.ovl_base, self.ovl_end, (base, data))
            self.overlay = [(self.ovl_base, ob)]
        return data

    def _pass2_section(self, stmts, base, end, image):
        out = bytearray()
        for st in stmts:
            k = st.kind
            if k in ("label", "equ", "redirect"):
                continue
            if k == "org":
                if st.size:
                    fv = self.ev(st, st.a[1]) if st.a[1] is not None else self.fill
                    out += bytes([fv & 0xFF]) * st.size
                continue
            self._cur = st.addr
            if k == "insn":
                w = self.encode(st)
                out += struct.pack(">H", w)
            elif k == "data":
                sz, lst = st.a
                for ei, ex in enumerate(lst):
                    v = self.ev(st, ex, st.addr + ei * sz)
                    lim = 1 << (8 * sz)
                    if not (-(lim >> 1) <= v < lim):
                        self.error(st, "value 0x%X does not fit in %d byte(s)" % (v, sz))
                    out += (v & (lim - 1)).to_bytes(sz, "big")
            elif k == "bytes":
                out += st.a
            elif k == "space":
                fv = self.ev(st, st.a[1]) if st.a[1] else self.fill
                out += bytes([fv & 0xFF]) * st.size
            elif k == "incbin":
                out += st.extra
            elif k == "copylong":
                if image is None:
                    self.error(st, ".copylong is only allowed in an overlay")
                src = self.ev(st, st.a[0]) - image[0]
                if src < 0 or src + st.size > len(image[1]):
                    self.error(st, ".copylong source outside the image")
                out += image[1][src:src + st.size]
            elif k == "align":
                if st.a[1] is not None:
                    fv = self.ev(st, st.a[1])
                    unit = self.ev(st, st.a[2]) if st.a[2] is not None else 1
                    pat = fv.to_bytes(2, "big") if unit == 2 else bytes([fv & 0xFF])
                    out += bytes(pat[(st.addr + i) % len(pat)] for i in range(st.size))
                else:
                    out += bytes([self.fill]) * st.size
            elif k == "pool":
                p = st.extra
                cnt = 0
                for ex in p["word"]:
                    v = self.ev(st, ex)
                    if not (-0x8000 <= v <= 0xFFFF):
                        self.error(st, "word literal %s out of range" % ex.text)
                    out += (v & 0xFFFF).to_bytes(2, "big")
                if p["long"]:
                    pad = p["laddr"] - (p["waddr"] + 2 * len(p["word"]))
                    out += bytes(pad)
                for ex in p["long"]:
                    v = self.ev(st, ex)
                    if not (-0x80000000 <= v <= 0xFFFFFFFF):
                        self.error(st, "long literal %s out of range" % ex.text)
                    out += (v & 0xFFFFFFFF).to_bytes(4, "big")
            elif k == "patchlong":
                if image is None:
                    self.error(st, ".patchlong is only allowed in an overlay")
                a = self.ev(st, st.a[0])
                if a % 4 or not (image[0] <= a <= image[0] + len(image[1]) - 4):
                    self.error(st, ".patchlong address 0x%X not an aligned word of the image" % a)
                self.patches.append((a, self.ev(st, st.a[1]) & 0xFFFFFFFF, self.ev(st, st.a[2]) & 0xFFFFFFFF))
            elif k == "assert":
                if not self.ev(st, st.a[0]):
                    self.error(st, "assertion failed %s" % st.a[1])
            elif k == "print":
                print(st.a)
            if len(out) != st.addr - base + st.size and k != "insn" and k != "data":
                pass
            # consistency check
        if len(out) != end - base:
            raise AsmError("internal size mismatch: %d vs %d" % (len(out), end - base))
        return bytes(out)

    # --- instruction encoding
    def encode(self, st):
        mn, ops = st.a
        cands = _TEMPLATES.get((mn, len(ops)))
        if not cands:
            self.error(st, "unknown instruction or wrong operand count: %s %s" % (mn, ",".join(ops)))
        errs = []
        for ins, regs in cands:
            r = self.try_encode(st, ins, regs, ops)
            if isinstance(r, int):
                return r
            if r:
                errs.append(r)
        if errs:
            self.error(st, errs[0])
        self.error(st, "no matching form for: %s %s" % (mn, ",".join(ops)))

    def try_encode(self, st, ins, regs, ops):
        vals = {}
        pend = []   # (placeholder, text)
        for (rx, names), op in zip(regs, ops):
            if op.startswith("=") and not ins.ops:
                return None
            lit = None
            if op.startswith("="):
                # pooled literal: mov.l =x,rN  -> template @({pcl},pc)
                # only the first operand of mov.w/mov.l pc forms
                if ins.ops[0] not in ("@({pcl},pc)", "@({pcw},pc)"):
                    return None
                pool, which, key = st.extra
                if which == "long" and ins.ops[0] != "@({pcl},pc)" or which == "word" and ins.ops[0] != "@({pcw},pc)":
                    return None
                pend.append((("pcl" if which == "long" else "pcw"), ("pool", pool, which, key)))
                continue
            m = rx.match(op)
            if not m:
                return None
            for nm, g in zip(names, m.groups()):
                if nm in ("n", "m", "b"):
                    v = int(g)
                    if nm == "b" and v > 7 or nm != "b" and v > 15:
                        return None
                    if nm in vals and vals[nm] != v:
                        return None
                    vals[nm] = v
                else:
                    if REG_RE.match(g.strip()):
                        return None        # looks like a register, not an expression
                    pend.append((nm, g))
        word = ins.val
        f = ins.fields
        for nm in ("n", "m", "b"):
            if nm in vals:
                lo, w = f[nm]
                word |= vals[nm] << lo
        for nm, text in pend:
            if isinstance(text, tuple):
                _, pool, which, key = text
                idx = pool[which].index(next(e for e in pool[which] if e.text == key))
                target = pool["waddr"] + 2 * idx if which == "word" else pool["laddr"] + 4 * idx
                nm_ = nm
                v = target
            else:
                try:
                    v = self.ev(st, Expr(text))
                except AsmError as e:
                    raise
            try:
                word |= self.field(st, ins, nm, v, f)
            except AsmError as e:
                return str(e)
        return word

    def field(self, st, ins, nm, v, f):
        pc = st.addr
        if nm in ("is", "iu"):
            lo, w = f["i"]
            if nm == "is" and not (-128 <= v <= 255) or nm == "iu" and not (0 <= v <= 255):
                raise AsmError("immediate %d out of range for %s" % (v, ins.syntax))
            return (v & 0xFF) << lo
        if nm in ("d1", "d2", "d4", "d1g", "d2g", "d4g"):
            sc = int(nm[1])
            lo, w = f["d"]
            if v % sc or not (0 <= v // sc < (1 << w)):
                raise AsmError("displacement %d not valid for %s (multiple of %d, 0..%d)" % (v, ins.syntax, sc, ((1 << w) - 1) * sc))
            return (v // sc) << lo
        if nm == "pcw":
            lo, w = f["d"]
            d = v - (pc + 4)
            if d < 0 or d % 2 or d // 2 >= 256:
                raise AsmError("word literal at 0x%X is %s from instruction at 0x%X (pc-relative range 0..510 bytes after pc+4, even)" %
                               (v, "behind" if d < 0 else ("too far (+%d)" % d if d // 2 >= 256 else "misaligned"), pc))
            return (d // 2) << lo
        if nm == "pcl":
            lo, w = f["d"]
            d = v - ((pc + 4) & ~3)
            if d < 0 or d % 4 or d // 4 >= 256:
                raise AsmError("long literal at 0x%X is %s from instruction at 0x%X (pc-relative range 0..1020 bytes after (pc+4)&~3, 4-aligned); "
                               "place a .pool nearer or fix alignment" %
                               (v, "behind it" if d < 0 else ("too far (+%d bytes)" % d if d // 4 >= 256 else "misaligned"), pc))
            return (d // 4) << lo
        if nm in ("br8", "br12"):
            lo, w = f["d"]
            d = v - (pc + 4)
            if d % 2:
                raise AsmError("branch target 0x%X is odd" % v)
            d //= 2
            lim = 1 << (w - 1)
            if not (-lim <= d < lim):
                raise AsmError("branch target 0x%X out of range from 0x%X (%d bytes, max +-%d)" % (v, pc, d * 2, lim * 2))
            return (d & ((1 << w) - 1)) << lo
        raise AsmError("internal: unknown placeholder " + nm)


def main(argv=None):
    ap = argparse.ArgumentParser(description="SH-3 assembler")
    ap.add_argument("files", nargs="+")
    ap.add_argument("-o", "--output")
    ap.add_argument("--map")
    ap.add_argument("-I", dest="inc", action="append", default=[])
    ap.add_argument("--strict", action="store_true", help="forbid gaps created by .org")
    ap.add_argument("--fill", type=lambda x: int(x, 0), default=0)
    a = ap.parse_args(argv)
    asm = Assembler(a.inc, a.strict, a.fill)
    try:
        for f in a.files:
            asm.add_file(f)
        asm.pass1()
        data = asm.pass2()
    except AsmError as e:
        print("shasm: error:", e, file=sys.stderr)
        return 1
    for w in asm.warnings:
        print("shasm: warning:", w, file=sys.stderr)
    if a.output:
        with open(a.output, "wb") as f:
            f.write(data)
    if a.map:
        with open(a.map, "w") as f:
            for n, v in sorted(((n, asm.lookup(n)) for n in asm.syms), key=lambda x: (x[1], x[0])):
                f.write("%08X %s\n" % (v & 0xFFFFFFFF, n))
    print("shasm: %d bytes at 0x%08X..0x%08X" % (len(data), asm.base, asm.end), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
