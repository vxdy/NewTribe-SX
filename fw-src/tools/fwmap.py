#!/usr/bin/env python3
"""fwmap - classify every byte of the ESX main firmware payload (code / data / strings / pad) and write layout.txt.

Inputs : the payload (BSS file minus its 0x20 byte header), dynamic coverage bitmaps from covrun.py (cov/*.cov),
         hand written overrides (fw-src/overrides.txt, same line format as layout.txt, applied first)
Output : fw-src/layout.txt with one item run per line:  <addr> <size> <kind> [extra]
         kinds:  code   instructions (size = bytes of consecutive instructions, delay slots included)
                 llit   32-bit literal (target of mov.l @(disp,pc) / mova)     wlit  16-bit literal
                 long / word / byte   plain data of that width (a run of N items)
                 ptr    run of 32-bit values that are addresses inside the image (emitted as `.long label`)
                 jt16   switch table of 16-bit offsets, extra = base address of the offsets (address after braf's slot)
                 str    NUL terminated string (size includes the NUL)   ascii  string without NUL
                 zero   run of zero bytes
         and function entry lines:   func <addr> <source>
Rules: items tile [BASE, BASE+IMG_END) without gaps/overlaps (checked at the end).
"""
import os
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shisa

BASE = 0x0C080000
PAYLOAD_SIZE = 0x1FFFE0
IMG_END = 0x6D9F0          # end of the real code/data; the rest of the payload is RAM filler (random bytes)
VEC_ENTRY = 0x1000

DELAYED = ("bra", "bsr", "braf", "bsrf", "jmp", "jsr", "rts", "rte", "bt/s", "bf/s")


def load_payload(path):
    return open(path, "rb").read()[0x20:]


def to_off(a):
    """Address (any mirror 0x0C.. 0x8C.. 0xAC..) -> payload offset or None if outside the image."""
    o = (a & 0x1FFFFFFF) - BASE
    return o if 0 <= o < IMG_END else None


class Map:
    def __init__(self, payload, covs=()):
        self.p = payload
        self.n = IMG_END
        self.cov = bytearray(PAYLOAD_SIZE)
        for c in covs:
            d = open(c, "rb").read()
            for i in range(min(len(d), PAYLOAD_SIZE)):
                self.cov[i] |= d[i]
        self.owner = [None] * self.n      # offset -> item start offset
        self.items = {}                   # start offset -> [end, kind, extra]
        self.funcs = {}                   # offset -> source
        self.labels = set()               # branch targets (offsets)
        self.issues = []
        self.lit_refs = defaultdict(set)  # (literal offset,size) -> referencing instruction offsets
        self.brtab = []                   # offsets of braf instructions
        self.slots = set()
        self.term_next = set()            # offsets following the delay slot of an unconditional branch / return
        self.jr = None                    # journal for trial analysis
        self.longs = {}                   # literal offset -> value (for placed llit)
        self.data_refs = set()            # offsets referenced by mova (strings / tables / switch tables)
        self.mem_addrs = defaultdict(int) # literal value used as memory base register -> count
        self.ext_calls = defaultdict(int) # jsr/jmp targets outside the image (BFS library) -> count
        self.jts = {}                     # table offset -> (base address, [target offsets])

    # ---------------------------------------------------------------- primitives (journaled)
    def w16(self, off):
        return (self.p[off] << 8) | self.p[off + 1]

    def w32(self, off):
        return struct.unpack_from(">I", self.p, off)[0]

    def issue(self, msg):
        self.issues.append(msg)

    def free(self, a, b):
        return a >= 0 and b <= self.n and all(self.owner[i] is None for i in range(a, b))

    def place(self, a, b, kind, extra=None):
        if a < 0 or b > self.n:
            self.issue("place out of image %x-%x %s" % (a, b, kind))
            return False
        if not self.free(a, b):
            o = sorted({self.owner[i] for i in range(a, b) if self.owner[i] is not None})
            self.issue("conflict placing %s at %x-%x with %s" % (kind, a, b, [(hex(x), self.items[x][1]) for x in o]))
            return False
        self.items[a] = [b, kind, extra]
        for i in range(a, b):
            self.owner[i] = a
        if self.jr is not None:
            self.jr.append(("place", a, b))
        return True

    def unplace(self, a, b):
        del self.items[a]
        for i in range(a, b):
            self.owner[i] = None

    def add_func(self, off, source):
        if 0 <= off < self.n and off not in self.funcs:
            self.funcs[off] = source
            if self.jr is not None:
                self.jr.append(("func", off))

    def add_label(self, off):
        if off not in self.labels:
            self.labels.add(off)
            if self.jr is not None:
                self.jr.append(("label", off))

    def add_litref(self, key, pc):
        s = self.lit_refs[key]
        if pc not in s:
            s.add(pc)
            if self.jr is not None:
                self.jr.append(("lit", key, pc))

    def rollback(self, jr):
        for e in reversed(jr):
            if e[0] == "place":
                self.unplace(e[1], e[2])
            elif e[0] == "func":
                del self.funcs[e[1]]
            elif e[0] == "label":
                self.labels.discard(e[1])
            elif e[0] == "lit":
                self.lit_refs[e[1]].discard(e[2])
                if not self.lit_refs[e[1]]:
                    del self.lit_refs[e[1]]
            elif e[0] == "slot":
                self.slots.discard(e[1])
            elif e[0] == "long":
                self.longs.pop(e[1], None)
            elif e[0] == "jt":
                self.jts.pop(e[1], None)

    # ---------------------------------------------------------------- code discovery
    def seeds_from_cov(self):
        """Executed instruction starts, except delay slots of executed delayed branches (placed with their branch)."""
        s = []
        for off in range(0, self.n, 2):
            if self.cov[off] & 1:
                if off >= 2 and self.cov[off - 2] & 1:
                    d = shisa.decode(self.w16(off - 2))
                    if d and d[0].mn in DELAYED:
                        continue
                s.append(off)
        return s

    def cov_calls(self):
        return [o for o in range(0, self.n, 2) if self.cov[o] & 0xC0]

    def descend(self, seeds, source):
        work = list(seeds)
        while work:
            self.follow(work.pop(), work, source)

    def follow(self, off, work, source):
        regs = {}
        if off & 1:
            self.issue("odd code address %x (%s)" % (off, source))
            return
        while True:
            if off < 0 or off + 2 > self.n:
                self.issue("code flow leaves the image at %x (%s)" % (off, source))
                return
            if self.owner[off] is not None:
                if self.items[self.owner[off]][1] != "i" or self.owner[off] != off:
                    self.issue("code flow at %x hits %s item %x (%s)" % (off, self.items[self.owner[off]][1], self.owner[off], source))
                return
            op = self.w16(off)
            d = shisa.decode(op)
            if d is None:
                self.issue("illegal opcode %04x at %x (%s)" % (op, off, source))
                return
            ins, v = d
            self.place(off, off + 2, "i", op)
            mn = ins.mn
            t = shisa.targets(ins, v, BASE + off)
            nxt = off + 2
            self.note_mem(ins, v, regs)
            if t is not None and t[0] in ("wlit", "llit"):
                self.track_lit(ins, v, t, off, regs)
            elif ins.syntax.startswith("mov #"):
                regs[v["n"]] = ("w", shisa.sext(v["i"], 8))
            else:
                self.kill_dest(ins, v, regs)
            if mn in DELAYED:
                so = off + 2
                if so + 2 > self.n:
                    self.issue("delay slot outside image at %x" % off)
                    return
                if self.owner[so] is None:
                    sop = self.w16(so)
                    sd = shisa.decode(sop)
                    if sd is None:
                        self.issue("illegal delay slot %04x at %x" % (sop, so))
                        return
                    self.place(so, so + 2, "i", sop)
                    self.slots.add(so)
                    if self.jr is not None:
                        self.jr.append(("slot", so))
                    sins, sv = sd
                    if sins.mn in DELAYED or sins.mn in ("trapa", "rte", "ldc", "ldc.l", "sleep") and False:
                        self.issue("branch in delay slot at %x" % so)
                        return
                    self.note_mem(sins, sv, regs)
                    st = shisa.targets(sins, sv, BASE + so)
                    if st is not None and st[0] in ("wlit", "llit"):
                        self.track_lit(sins, sv, st, so, regs)
                    else:
                        self.kill_dest(sins, sv, regs)
                elif self.owner[so] != so or self.items[so][1] != "i":
                    self.issue("delay slot of %x overlaps %s item" % (off, self.items[self.owner[so]][1]))
                    return
                nxt = so + 2
                if mn in ("bra", "jmp", "rts", "rte", "braf"):
                    self.term_next.add(nxt)
                if mn in ("bra", "bsr"):
                    tgt = t[1] - BASE
                    if 0 <= tgt < self.n:
                        work.append(tgt)
                        if mn == "bsr":
                            self.add_func(tgt, "bsr")
                        else:
                            self.add_label(tgt)
                    else:
                        self.issue("%s target outside image %x at %x" % (mn, t[1], off))
                        return
                    if mn == "bra":
                        return
                    regs = {}
                elif mn in ("jsr", "jmp"):
                    r = regs.get(v["m"])
                    tgt = to_off(r[1]) if r and r[0] in ("l", "a") else None
                    if tgt is None and r and r[0] == "l":
                        self.ext_calls[r[1]] += 1
                    if tgt is not None and not tgt & 1:
                        work.append(tgt)
                        if mn == "jsr":
                            self.add_func(tgt, "jsr")
                        else:
                            self.add_label(tgt)
                    if mn == "jmp":
                        return
                    regs = {}
                elif mn == "braf":
                    self.brtab.append(off)
                    return
                elif mn == "bsrf":
                    regs = {}
                elif mn in ("rts", "rte"):
                    return
                else:   # bt/s bf/s
                    tgt = t[1] - BASE
                    if 0 <= tgt < self.n:
                        work.append(tgt)
                        self.add_label(tgt)
                    else:
                        self.issue("%s target outside image at %x" % (mn, off))
                        return
                off = nxt
                continue
            if mn in ("bt", "bf"):
                tgt = t[1] - BASE
                if 0 <= tgt < self.n:
                    work.append(tgt)
                    self.add_label(tgt)
                else:
                    self.issue("%s target outside image at %x" % (mn, off))
                    return
            off = nxt

    def note_mem(self, ins, v, regs):
        if ins.mn in ("jmp", "jsr"):
            return
        for op in ins.ops:
            if op.startswith("@") and ("r{m}" in op or "r{n}" in op):
                b = "m" if "r{m}" in op else "n"
                r = regs.get(v[b])
                if r and r[0] == "l":
                    self.mem_addrs[r[1]] += 1

    def track_lit(self, ins, v, t, off, regs):
        loff = to_off(t[1])
        mn = ins.mn
        size = 2 if t[0] == "wlit" else 4
        if loff is None or loff + size > self.n:
            self.issue("literal address %x outside image at %x" % (t[1], off))
            regs.pop(0 if mn == "mova" else v["n"], None)
            return
        if mn == "mova":
            self.data_refs.add(loff)
            regs[0] = ("a", t[1])
            return
        self.add_litref((loff, size), off)
        if False:
            pass
        elif t[0] == "llit":
            regs[v["n"]] = ("l", self.w32(loff))
        else:
            regs[v["n"]] = ("w", shisa.sext(self.w16(loff), 16))

    @staticmethod
    def kill_dest(ins, v, regs):
        syn = ins.syntax
        ops = ins.ops
        n = v.get("n")
        if n is not None and ops:
            last = ops[-1]
            if last in ("r{n}", "@-r{n}") or syn.startswith(("dt ", "movt", "sts ", "stc ")):
                if last == "r{n}" and syn.startswith("add #"):
                    r = regs.get(n)
                    if r and r[0] == "w":
                        regs[n] = ("w", r[1] + shisa.sext(v["i"], 8))
                        return
                regs.pop(n, None)
        if "m" in v and "@r{m}+" in syn:
            regs.pop(v["m"], None)
        if syn.startswith("mov.") and syn.endswith(",r0"):
            regs.pop(0, None)
        if syn.startswith(("and #", "or #", "xor #")):
            regs.pop(0, None)

    # ---------------------------------------------------------------- literals
    def place_literals(self):
        """Place llit/wlit items for every referenced literal that is not yet placed."""
        for (loff, size), refs in sorted(self.lit_refs.items()):
            if not refs:
                continue
            k = "llit" if size == 4 else "wlit"
            o = self.owner[loff]
            if o is not None:
                if self.items[o][1] in (k, "ptr", "long", "word") and o == loff:
                    continue
                if self.items[o][1] in ("llit", "wlit") and o == loff:
                    continue
            if size == 4 and loff % 4:
                self.issue("misaligned long literal %x refs %s" % (loff, [hex(r) for r in sorted(refs)[:3]]))
                continue
            if self.place(loff, loff + size, k) and size == 4:
                self.longs[loff] = self.w32(loff)
                if self.jr is not None:
                    self.jr.append(("long", loff))

    # ---------------------------------------------------------------- switch tables (mova + mov.w @(r0,rn) + braf)
    def process_jump_tables(self, pend, work):
        for boff in pend:
            tab = None
            cnt = None
            for k in range(1, 16):
                po = boff - 2 * k
                if po < 0:
                    break
                d = shisa.decode(self.w16(po))
                if d and d[0].mn == "mova" and tab is None:
                    t = shisa.targets(d[0], d[1], BASE + po)
                    tab = to_off(t[1])
            if tab is None:
                self.issue("braf at %x without mova table" % boff)
                continue
            base_off = boff + 4
            ents = []
            o = tab
            lo = None
            while o + 2 <= self.n and o not in self.items and (self.owner[o] is None):
                tgt = base_off + shisa.sext(self.w16(o), 16)
                if not (0 <= tgt < self.n) or tgt & 1:
                    break
                if lo is not None and o >= lo:
                    break
                ents.append(tgt)
                lo = tgt if lo is None else min(lo, tgt)
                o += 2
            if not ents:
                self.issue("empty switch table at %x for braf %x" % (tab, boff))
                continue
            if self.place(tab, tab + 2 * len(ents), "jt16", BASE + base_off):
                self.jts[tab] = (BASE + base_off, ents)
                if self.jr is not None:
                    self.jr.append(("jt", tab))
                for e in ents:
                    work.append(e)
                    self.add_label(e)

    def run_flow(self, seeds, source):
        """descend + literal placement + switch tables until nothing new appears."""
        work = list(seeds)
        while True:
            while work:
                self.follow(work.pop(), work, source)
            self.place_literals()
            if not self.brtab:
                break
            pend, self.brtab = self.brtab, []
            self.process_jump_tables(pend, work)
            if not work:
                break

    def trial(self, off, source, min_insns=2):
        """Try to see `off` as a function start.  Accepted only if the whole reachable flow is clean."""
        self.jr = []
        ni = len(self.issues)
        self.brtab = []
        self.run_flow([off], source)
        cnt = sum(1 for e in self.jr if e[0] == "place" and self.items[e[1]][1] == "i")
        ok = len(self.issues) == ni and cnt >= min_insns
        if not ok:
            self.rollback(self.jr)
            del self.issues[ni:]
        self.brtab = []
        self.jr = None
        if ok:
            self.add_func(off, source)
        return ok

    # ---------------------------------------------------------------- gaps
    def unknown_runs(self):
        runs = []
        i = 0
        while i < self.n:
            if self.owner[i] is None:
                j = i
                while j < self.n and self.owner[j] is None:
                    j += 1
                runs.append((i, j))
                i = j
            else:
                i += 1
        return runs

    def addr_like(self, v):
        return to_off(v) is not None

    def func_like(self, t):
        """Is offset t (an instruction start) plausible as a function entry?"""
        if t in self.funcs or t in self.term_next:
            return True
        # first instruction of a code run: nothing can fall into it
        return t >= 2 and self.owner[t] == t and self.items[t][1] == "i" and \
            (self.owner[t - 2] is None or self.items[self.owner[t - 2]][1] != "i")

    def pointer_runs(self):
        """Runs (>=2) of aligned longs in unowned bytes that look like pointer tables: (start, [(offset, target)])."""
        out = []
        for a, b in self.unknown_runs():
            s = (a + 3) & ~3
            cur = []
            while s + 4 <= b:
                v = self.w32(s)
                t = to_off(v)
                ok = t is not None and not t & 1 and not suspicious(v)
                if ok and self.owner[t] is not None:
                    # target is placed: must be a function entry or non code
                    k = self.items[self.owner[t]][1]
                    ok = (k != "i") or self.func_like(t)
                if ok:
                    cur.append((s, t))
                else:
                    if len(cur) >= 2:
                        out.append(list(cur))
                    cur = []
                s += 4
            if len(cur) >= 2:
                out.append(list(cur))
        return out

    def prologue_scan(self, lo, hi):
        """Offsets in unowned [lo,hi) that look like function prologues."""
        pro = {0x4F22, 0x2FE6, 0x2FD6, 0x2FC6, 0x2FB6, 0x2FA6, 0x2F96, 0x2F86, 0x7FF0}
        res = []
        for o in range(lo & ~1, hi - 2, 2):
            if self.owner[o] is None and self.w16(o) in pro:
                res.append(o)
        return res


def suspicious(v):
    """Values that merely look like in-image addresses: repeated bytes / repeated halfwords."""
    b = v.to_bytes(4, "big")
    return len(set(b)) == 1 or (b[0:2] == b[2:4] and len(set(b)) <= 2)


def is_text(b):
    return 0x20 <= b < 0x7F


def split_data(m, a, b):
    """Split the unowned range [a,b) into data items using static evidence."""
    p = m.p
    out = []
    i = a
    while i < b:
        j = i
        while j < b and p[j] == 0:
            j += 1
        if j - i >= 8 or (j - i >= 2 and (j == b or i == a) and False):
            out.append((i, j, "zero", None))
            i = j
            continue
        j = i
        while j < b and is_text(p[j]):
            j += 1
        if j - i >= 5 or (j - i >= 4 and j < b and p[j] == 0):
            if j < b and p[j] == 0:
                out.append((i, j + 1, "str", None))
                i = j + 1
            else:
                out.append((i, j, "ascii", None))
                i = j
            continue
        j = i
        while j < b:
            if p[j] == 0:
                k = j
                while k < b and p[k] == 0:
                    k += 1
                if k - j >= 8:
                    break
            if is_text(p[j]):
                k = j
                while k < b and is_text(p[k]):
                    k += 1
                if k - j >= 5 or (k - j >= 4 and k < b and p[k] == 0):
                    break
            j += 1
        if j == i:
            j = i + 1
        out.append((i, j, "raw", None))
        i = j
    return out


def refine_raw(m, a, b, entities=frozenset()):
    """Turn a raw data range into ptr / long / word / byte runs."""
    p = m.p
    out = []
    i = a

    def ent_ptr(o):
        if o % 4 or o + 4 > b:
            return False
        v = m.w32(o)
        t = to_off(v)
        return t is not None and not t & 1 and not suspicious(v) and t in entities

    while i < b:
        if ent_ptr(i):
            j = i
            while ent_ptr(j):
                j += 4
            out.append((i, j, "ptr", None))
            i = j
            continue
        # pointer run (aligned)
        if i % 4 == 0 and i + 4 <= b:
            j = i
            real = 0
            while j + 4 <= b:
                v = m.w32(j)
                t = to_off(v)
                if t is not None and not suspicious(v):
                    if m.owner[t] is not None and m.items[m.owner[t]][1] == "i" and not m.func_like(t):
                        break
                    real += 1
                elif v != 0:
                    break
                j += 4
            # trim trailing zeros
            while j > i and m.w32(j - 4) == 0:
                j -= 4
            if real >= 2 and j - i >= 8:
                out.append((i, j, "ptr", None))
                i = j
                continue
        # 4-aligned long evidence (read as 32-bit at run time)
        if i % 4 == 0 and i + 4 <= b and all(m.cov[i + k] & 0x10 for k in range(4)):
            j = i
            while j + 4 <= b and all(m.cov[j + k] & 0x10 for k in range(4)) and not ent_ptr(j):
                j += 4
            out.append((i, j, "long", None))
            i = j
            continue
        if i % 2 == 0 and i + 2 <= b and all(m.cov[i + k] & 0x08 for k in range(2)):
            j = i
            while j + 2 <= b and all(m.cov[j + k] & 0x08 for k in range(2)):
                j += 2
            out.append((i, j, "word", None))
            i = j
            continue
        # byte run until next structured thing
        j = i + 1
        while j < b:
            if ent_ptr(j):
                break
            if (j % 4 == 0 and j + 8 <= b and to_off(m.w32(j)) is not None and to_off(m.w32(j + 4)) is not None and not suspicious(m.w32(j)) and not suspicious(m.w32(j + 4))) or \
               (j % 4 == 0 and j + 4 <= b and all(m.cov[j + k] & 0x10 for k in range(4))) or \
               (j % 2 == 0 and j + 2 <= b and all(m.cov[j + k] & 0x08 for k in range(2))):
                break
            j += 1
        out.append((i, j, "byte", None))
        i = j
    return out


def analyze(payload, covs, overrides=None, log=print):
    m = Map(payload, covs)
    # 0. overrides
    if overrides:
        for line in open(overrides):
            line = line.split("#")[0].split()
            if len(line) >= 3 and line[0] != "func":
                a = int(line[0], 16) - BASE
                sz = int(line[1], 0)
                kind = line[2]
                if kind != "code":
                    m.place(a, a + sz, kind, line[3] if len(line) > 3 else None)
    # 1. dynamic + vector seeds
    seeds = m.seeds_from_cov() + [0x1000, 0x100, 0x400, 0x600]
    m.run_flow(seeds, "dyn")
    for o in m.cov_calls():
        m.add_func(o, "cov")
    log("dynamic+static flow: %d instructions, %d funcs, %d issues" % (sum(1 for v in m.items.values() if v[1] == "i"), len(m.funcs), len(m.issues)))
    # 2. pointer tables -> trial code; iterate
    rounds = 0
    while True:
        rounds += 1
        newfn = 0
        for run in m.pointer_runs():
            for s_, t in run:
                if m.owner[t] is None:
                    if m.trial(t, "ptr", 3):
                        newfn += 1
                elif m.owner[t] == t and m.items[m.owner[t]][1] == "i" and m.func_like(t):
                    m.add_func(t, "ptr")
        log("pointer round %d: %d new functions" % (rounds, newfn))
        if not newfn:
            break
    # 3. prologue scan
    for rnd in range(3):
        newfn = 0
        for a, b in m.unknown_runs():
            for o in m.prologue_scan(a, b):
                if m.owner[o] is None and m.trial(o, "prologue", 6):
                    newfn += 1
        log("prologue round %d: %d new functions" % (rnd, newfn))
        for run in m.pointer_runs():
            for s_, t in run:
                if m.owner[t] is None and m.trial(t, "ptr", 3):
                    newfn += 1
        if not newfn:
            break
    # 3b. function-call targets inside unknown (bsr/jsr from trials already added); mark pointers into code as funcs
    for off, (end, kind, ex) in list(m.items.items()):
        if kind == "llit":
            t = to_off(m.longs.get(off, 0))
            if t is not None and m.owner[t] == t and m.items[t][1] == "i" and not t & 1 and t not in m.funcs \
                    and not suspicious(m.longs.get(off, 0)) and m.func_like(t):
                m.add_func(t, "litptr")
    # 3c. alignment nops (0x0009) right behind code are code
    for a, b in m.unknown_runs():
        o = a
        if o >= 2 and m.owner[o - 2] is not None and m.items[m.owner[o - 2]][1] == "i":
            while o + 2 <= b and m.w16(o) == 0x0009:
                m.place(o, o + 2, "i", 0x0009)
                o += 2
    # 4. data classification of what is left
    pieces = []
    for a, b in m.unknown_runs():
        pieces.extend(split_data(m, a, b))
    entities = set(m.funcs) | set(m.data_refs) | set(m.term_next)
    entities |= {a for a, (b, k, e) in m.items.items() if k == "i" and m.func_like(a)}
    entities |= {to_off(v) for v in m.longs.values() if to_off(v) is not None}
    entities |= {x for x, y, k, e in pieces if k in ("str", "ascii")}
    for x, y, k, e in pieces:
        if k == "raw":
            for (x2, y2, k2, e2) in refine_raw(m, x, y, entities):
                m.place(x2, y2, k2, e2)
        else:
            m.place(x, y, k, e)
    # 5. code targets of data pointers are function entries too
    for a, (b, k, e) in list(m.items.items()):
        if k == "ptr":
            for o in range(a, b, 4):
                t = to_off(m.w32(o))
                if t is not None and m.owner[t] == t and m.items[t][1] == "i":
                    m.add_func(t, "dataptr")
    return m


def write_layout(m, path):
    lines = []
    # merge adjacent instruction items into code runs; merge adjacent same-kind runs
    offs = sorted(m.items)
    prev_end = 0
    run = None
    out = []
    for a in offs:
        b, k, e = m.items[a]
        if a != prev_end:
            raise SystemExit("layout gap/overlap at %x (prev end %x)" % (a, prev_end))
        prev_end = b
        k2 = "code" if k == "i" else k
        if run and run[2] == k2 and k2 in ("code", "zero", "byte", "word", "long", "ptr") and run[1] == a:
            run[1] = b
        else:
            run = [a, b, k2, None if k2 == "code" else e]
            out.append(run)
    if prev_end != m.n:
        raise SystemExit("layout does not reach the image end")
    with open(path, "w") as f:
        f.write("# generated by fwmap.py - do not edit (use overrides.txt)\n# addr size kind [extra]\n")
        for a, b, k, e in out:
            f.write("%08X %d %s%s\n" % (BASE + a, b - a, k, (" " + (("%08X" % e) if isinstance(e, int) else str(e))) if e is not None else ""))
        for off, src in sorted(m.funcs.items()):
            f.write("func %08X %s\n" % (BASE + off, src))
        for v, c in sorted(m.mem_addrs.items()):
            f.write("ext %08X %s %d\n" % (v, "var" if to_off(v) is None else "ref", c))
        for v, c in sorted(m.ext_calls.items()):
            f.write("ext %08X call %d\n" % (v, c))
    return out


def main():
    global IMG_END
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--bss", default=os.path.join(os.path.dirname(__file__), "../../factory-firmware/ESX0102N.BSS"))
    ap.add_argument("--cov", nargs="*", default=None)
    ap.add_argument("--overrides", default=os.path.join(os.path.dirname(__file__), "../overrides.txt"))
    ap.add_argument("-o", "--out", default=os.path.join(os.path.dirname(__file__), "../layout.txt"))
    ap.add_argument("--img-end", type=lambda x: int(x, 0), default=IMG_END)
    ap.add_argument("--issues", action="store_true")
    a = ap.parse_args()
    IMG_END = a.img_end
    covs = a.cov
    if covs is None:
        covs = sorted(glob_cov())
    payload = load_payload(a.bss)
    m = analyze(payload, covs, a.overrides if os.path.exists(a.overrides) else None)
    out = write_layout(m, a.out)
    kinds = defaultdict(int)
    for a_, b_, k, e in out:
        kinds[k] += b_ - a_
    print("bytes by kind:", dict(kinds))
    print("functions:", len(m.funcs), " issues:", len(m.issues))
    if a.issues:
        for i in m.issues[:200]:
            print(i)


def glob_cov():
    import glob
    here = os.path.dirname(os.path.abspath(__file__))
    return glob.glob(os.path.join(here, "../cov/*.cov"))


if __name__ == "__main__":
    main()
