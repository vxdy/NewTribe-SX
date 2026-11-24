#!/usr/bin/env python3
"""shdis - emit re-assemblable SH-3 assembly sources for the ESX main firmware from layout.txt + symbols.txt.

usage: shdis.py [--bss ESX0102N.BSS] [--layout layout.txt] [--symbols symbols.txt] [--out src/] [--data data/]

Output (all under --out, existing generated files are replaced):
    00_defs.s            equates for everything outside the image (RAM variables, on-chip registers, BFS library entry points)
    part_<addr>.s        the image, split at function boundaries; every file starts with an absolute .org
    zz_pad.s             .incbin of the RAM-filler tail of the payload  (data/ram_pad.bin)
Every referenced address inside the image becomes a label (func_/loc_/lit_/str_/dat_/jt_ + address, or the name
from symbols.txt) and every 32-bit datum holding an image address is written as `.long label` so that the code can grow.
symbols.txt:  addr,name[,comment[,kind]]   (kind: func data str var reg ...; blank lines and # comments allowed)
"""
import argparse
import bisect
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shisa
import fwmap
from fwmap import BASE, IMG_END, PAYLOAD_SIZE

MIRRORS = (0x00000000, 0x80000000, 0xA0000000)
RAM_LO = BASE + IMG_END
VALID_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$]*$")


class Item:
    __slots__ = ("a", "b", "kind", "extra")

    def __init__(self, a, b, kind, extra):
        self.a, self.b, self.kind, self.extra = a, b, kind, extra


def parse_layout(path):
    items, funcs, ext = [], {}, {}
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        f = line.split()
        if f[0] == "func":
            funcs[int(f[1], 16)] = f[2] if len(f) > 2 else ""
        elif f[0] == "ext":
            ext[int(f[1], 16)] = f[2]
        else:
            a = int(f[0], 16)
            items.append(Item(a, a + int(f[1]), f[2], int(f[3], 16) if len(f) > 3 and f[2] == "jt16" else (f[3] if len(f) > 3 else None)))
    return items, funcs, ext


def parse_symbols(path):
    syms = {}
    if path and os.path.exists(path):
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            f = [x.strip() for x in line.split(",", 2)]
            if len(f) < 2:
                raise SystemExit("%s:%d: bad symbol line" % (path, n))
            addr = int(f[0], 16)
            if not VALID_NAME.match(f[1]):
                raise SystemExit("%s:%d: bad symbol name %r" % (path, n, f[1]))
            comment, kind = (f[2] if len(f) > 2 else ""), ""
            if "," in comment:
                c2, k2 = comment.rsplit(",", 1)
                if k2.strip() in ("func", "data", "str", "var", "reg", "ptr", ""):
                    comment, kind = c2.strip(), k2.strip()
            elif comment in ("func", "data", "str", "var", "reg"):
                comment, kind = "", comment
            syms[addr] = (f[1], comment, kind)
    return syms


def esc_str(b):
    out = ""
    for c in b:
        ch = chr(c)
        if ch == '"':
            out += '\\"'
        elif ch == "\\":
            out += "\\\\"
        elif 0x20 <= c < 0x7F:
            out += ch
        elif c == 10:
            out += "\\n"
        elif c == 9:
            out += "\\t"
        elif c == 13:
            out += "\\r"
        else:
            out += "\\x%02X" % c
    return out


class Dis:
    def __init__(self, payload, items, funcs, ext, syms):
        self.p = payload
        self.items = items
        self.funcs = funcs
        self.ext = ext
        self.syms = syms
        self.starts = [it.a for it in items]
        self.labels = {}           # address -> name (only addresses that must/may carry a label)
        self.need = set()          # addresses to label
        self.extnames = {}         # absolute value -> name (outside image)
        self.ramvars = set()       # physical addresses in the RAM behind the image

    # ----- helpers
    def item_at(self, addr):
        i = bisect.bisect_right(self.starts, addr) - 1
        if i < 0:
            return None
        it = self.items[i]
        return it if it.a <= addr < it.b else None

    def w32(self, a):
        o = a - BASE
        return int.from_bytes(self.p[o:o + 4], "big")

    def w16(self, a):
        o = a - BASE
        return int.from_bytes(self.p[o:o + 2], "big")

    @staticmethod
    def in_image(v):
        return BASE <= (v & 0x1FFFFFFF) < BASE + IMG_END

    @staticmethod
    def in_ram(v):
        """address in the RAM that starts right behind the image (inside the file's RAM filler)"""
        p = v & 0x1FFFFFFF
        return BASE + IMG_END <= p < BASE + PAYLOAD_SIZE and (v >> 29) in (0, 4, 5)

    def ram_name(self, v):
        p = v & 0x1FFFFFFF
        return self.syms[p][0] if p in self.syms else "var_%08X" % p

    def labelable(self, addr):
        it = self.item_at(addr)
        if it is None:
            return False
        if it.kind == "code":
            return (addr - it.a) % 2 == 0
        if it.kind in ("llit", "wlit"):
            return addr == it.a
        if it.kind in ("jt16", "word"):
            return (addr - it.a) % 2 == 0 or it.kind == "word"
        if it.kind in ("long", "ptr"):
            return True
        return True

    def want(self, addr):
        if self.labelable(addr):
            self.need.add(addr)
            return True
        return False

    # ----- naming
    def name(self, addr):
        n = self.labels.get(addr)
        if n:
            return n
        if addr in self.syms and self.labelable(addr):
            n = self.syms[addr][0]
        else:
            it = self.item_at(addr)
            k = it.kind if it else "?"
            if k == "code":
                pre = "func" if addr in self.funcs else "loc"
            elif k in ("llit", "wlit"):
                pre = "lit"
            elif k in ("str", "ascii"):
                pre = "str"
            elif k == "jt16":
                pre = "jt"
            else:
                pre = "dat"
            n = "%s_%08X" % (pre, addr)
        self.labels[addr] = n
        return n

    def ref_expr(self, v):
        """Expression for a 32-bit value: label (+mirror bit), external name, or hex."""
        if self.plausible_ptr(v):
            phys = BASE + ((v & 0x1FFFFFFF) - BASE)
            if phys in self.need and self.labelable(phys):
                n = self.name(phys)
                hi = v & 0xE0000000
                if hi == 0:
                    return n
                return "%s + 0x%08X" % (n, hi)
        if self.in_ram(v) and not fwmap.suspicious(v) and (v & 0x1FFFFFFF) in self.ramvars:
            hi = v & 0xE0000000
            n = self.ram_name(v)
            return n if hi == 0 else "%s + 0x%08X" % (n, hi)
        nm = self.extnames.get(v)
        if nm:
            return nm
        return "0x%08X" % v

    # ----- pass 1: find all references
    def collect(self):
        for a in self.syms:
            if BASE <= a < BASE + IMG_END:
                self.want(a)
        for a in self.funcs:
            self.want(a)
        for it in self.items:
            if it.kind == "code":
                self.scan_code(it)
            elif it.kind == "llit":
                for o in range(it.a, it.b, 4):
                    self.note_value(self.w32(o))
            elif it.kind == "ptr":
                for o in range(it.a, it.b, 4):
                    self.note_value(self.w32(o))
            elif it.kind == "jt16":
                base = it.extra
                self.want(base)
                for o in range(it.a, it.b, 2):
                    t = base + shisa.sext(self.w16(o), 16)
                    self.want(t)
        # external names
        for v, kind in self.ext.items():
            pass

    def plausible_ptr(self, v):
        """32-bit value that is an address inside the image at a place that can carry a label."""
        if not self.in_image(v) or fwmap.suspicious(v):
            return False
        a = BASE + ((v & 0x1FFFFFFF) - BASE)
        it = self.item_at(a)
        if it is None or not self.labelable(a):
            return False
        if it.kind == "code":
            return a in self.funcs or a in self.syms
        return True

    def note_value(self, v):
        if self.in_image(v):
            if self.plausible_ptr(v):
                self.want(BASE + ((v & 0x1FFFFFFF) - BASE))
        else:
            self.note_ext(v)

    def note_ext(self, v):
        if self.in_ram(v) and not fwmap.suspicious(v):
            self.ramvars.add(v & 0x1FFFFFFF)
            return
        if v in self.extnames:
            return
        kind = self.ext.get(v)
        if v in self.syms:
            self.extnames[v] = self.syms[v][0]
        elif kind == "call":
            self.extnames[v] = "bfs_func_%08X" % v
        elif kind == "var":
            self.extnames[v] = ("io_%08X" if v >= 0xA0000000 or v >= 0xFFFFE000 else "var_%08X") % v

    def scan_code(self, it):
        for a in range(it.a, it.b, 2):
            op = self.w16(a)
            d = shisa.decode(op)
            if d is None:
                raise SystemExit("illegal opcode %04X in code run at %08X" % (op, a))
            t = shisa.targets(d[0], d[1], a)
            if t is None:
                continue
            kind, tgt = t
            if kind == "br":
                if self.in_image(tgt):
                    if not self.want(tgt):
                        raise SystemExit("branch at %08X to unlabelable %08X" % (a, tgt))
                continue
            if not self.in_image(tgt):
                raise SystemExit("literal ref outside image at %08X" % a)
            if not self.want(tgt):
                raise SystemExit("literal at %08X for %08X unlabelable" % (tgt, a))
            if kind == "llit" and d[0].mn != "mova":
                self.note_value(self.w32(tgt))

    def assign_ext(self):
        for v, kind in self.ext.items():
            self.note_ext(v)

    # ----- instruction text
    def insn_text(self, a):
        op = self.w16(a)
        d = shisa.decode(op)

        def sym(kind, tgt):
            if self.in_image(tgt):
                p = BASE + ((tgt & 0x1FFFFFFF) - BASE)
                if p in self.need and self.labelable(p):
                    return self.name(p)
            nm = self.extnames.get(tgt)
            if nm:
                return nm
            return "0x%08X" % tgt
        return shisa.format_insn(op, a, sym, d)

    # ----- emission
    def emit(self, split_size=0x8000):
        """Yield (start address, lines) for each output file."""
        files = []
        cur_lines = []
        cur_start = None
        cur_size = 0
        emitted_end = BASE
        label_addrs = sorted(self.need | {a for a in self.syms if self.labelable(a) and BASE <= a < BASE + IMG_END})
        self.need |= set(label_addrs)
        li = 0

        def labels_in(lo, hi):
            i = bisect.bisect_left(label_addrs, lo)
            out = []
            while i < len(label_addrs) and label_addrs[i] < hi:
                out.append(label_addrs[i])
                i += 1
            return out

        def lab_lines(a):
            ls = []
            if a in self.syms and self.syms[a][1]:
                for c in self.syms[a][1].split("|"):
                    ls.append("; " + c.strip())
            if a in self.funcs and self.item_at(a).kind == "code":
                ls.insert(0, "")
            ls.append("%s:" % self.name(a))
            return ls

        prev_kind = None
        nxt_a = {self.items[i].a: self.items[i + 1].a for i in range(len(self.items) - 1)}
        nxt_kind = {self.items[i].a: self.items[i + 1].kind for i in range(len(self.items) - 1)}
        prev_it = None
        for it in self.items:
            prev_kind = prev_it.kind if prev_it is not None else None
            prev_it = it
            if cur_start is None:
                cur_start = it.a
                cur_lines = ["\t.org\t0x%08X\t\t; image start = VBR; the sources are assembled in manifest order, only vectors/entry are pinned" % it.a]
            # new file at a function boundary once big enough
            if (cur_size >= split_size and it.kind == "code" and it.a in self.funcs) or \
               (cur_size >= 3 * split_size and (it.kind != "code" or it.a in self.funcs)):
                files.append((cur_start, cur_lines))
                cur_start = it.a
                cur_lines = ["; continues at 0x%08X in the original image (no .org: the image may grow)" % it.a]
                cur_size = 0
            cur_size += it.b - it.a
            L = cur_lines
            if it.a in (BASE + 0x100, BASE + 0x400, BASE + 0x600, BASE + 0x1000):
                L.append("\t.org\t0x%08X\t\t; fixed position (exception vector / entry point)" % it.a)
            if it.kind == "byte" and it.b - it.a == 2 and it.a % 4 == 2 and self.p[it.a - BASE:it.b - BASE] == b"\0\0" \
                    and it.a not in self.need and nxt_a.get(it.a, 1) % 4 == 0:
                L.append("\t.align\t4")
                continue
            if it.kind == "code":
                a = it.a
                while a < it.b:
                    if a in self.need:
                        L.extend(lab_lines(a))
                    prev = shisa.decode(self.w16(a - 2)) if a > it.a else None
                    if a + 2 == it.b and a % 4 == 2 and self.w16(a) == 0x0009 and a not in self.need and \
                            nxt_kind.get(it.a) in ("llit", "ptr", "long", "jt16", "word", "byte", "str", "ascii") and it.b % 4 == 0 \
                            and prev is not None and prev[0].mn not in fwmap.DELAYED and self.w16(a - 2) != 0x0009:
                        L.append("\t.align\t4, 0x0009, 2")
                    else:
                        L.append("\t%s" % self.insn_text(a))
                    a += 2
                continue
            # data items: split at label addresses
            cuts = [x for x in labels_in(it.a + 1, it.b)]
            bounds = [it.a] + cuts + [it.b]
            if it.kind in ("llit", "ptr", "long", "jt16") and it.a % 4 == 0 and prev_kind not in ("llit", "ptr", "long", "jt16"):
                L.append("\t.align\t4")
            for lo, hi in zip(bounds[:-1], bounds[1:]):
                if lo in self.need:
                    L.extend(lab_lines(lo))
                self.emit_data(L, it, lo, hi)
        files.append((cur_start, cur_lines))
        return files

    def emit_data(self, L, it, lo, hi):
        p = self.p
        k = it.kind
        n = hi - lo
        if k in ("llit", "ptr", "long"):
            if k == "long":
                pass
            for o in range(lo, hi, 4):
                if o + 4 > hi:
                    self.emit_bytes(L, o, hi)
                    break
                v = self.w32(o)
                if k == "long":
                    L.append("\t.long\t0x%08X" % v)
                else:
                    L.append("\t.long\t%s" % self.ref_expr(v))
        elif k == "wlit":
            L.append("\t.word\t0x%04X" % self.w16(lo))
        elif k == "word":
            vals = []
            o = lo
            while o + 2 <= hi:
                vals.append("0x%04X" % self.w16(o))
                o += 2
            for i in range(0, len(vals), 8):
                L.append("\t.word\t" + ", ".join(vals[i:i + 8]))
            if o < hi:
                self.emit_bytes(L, o, hi)
        elif k == "jt16":
            base = it.extra
            o = lo
            while o + 2 <= hi:
                t = base + shisa.sext(self.w16(o), 16)
                L.append("\t.word\t%s - %s" % (self.name(t) if t in self.need else "0x%08X" % t, self.name(base) if base in self.need else "0x%08X" % base))
                o += 2
            if o < hi:
                self.emit_bytes(L, o, hi)
        elif k == "zero":
            L.append("\t.space\t%d, 0" % n)
        elif k in ("str", "ascii"):
            b = p[lo - BASE:hi - BASE]
            nul = k == "str" and hi == it.b
            txt = b[:-1] if nul else b
            L.append('\t%s\t"%s"' % (".asciz" if nul else ".ascii", esc_str(txt)))
        else:
            self.emit_bytes(L, lo, hi)

    def emit_bytes(self, L, lo, hi):
        p = self.p
        for o in range(lo, hi, 16):
            e = min(hi, o + 16)
            L.append("\t.byte\t" + ", ".join("0x%02X" % c for c in p[o - BASE:e - BASE]))


def main():
    global IMG_END, RAM_LO
    ap = argparse.ArgumentParser()
    root = os.path.normpath(os.path.join(HERE, ".."))
    ap.add_argument("--bss", default=os.path.join(root, "..", "factory-firmware", "ESX0102N.BSS"))
    ap.add_argument("--layout", default=os.path.join(root, "layout.txt"))
    ap.add_argument("--symbols", default=os.path.join(root, "symbols.txt"))
    ap.add_argument("--out", default=os.path.join(root, "src"))
    ap.add_argument("--data", default=os.path.join(root, "data"))
    ap.add_argument("--img-end", type=lambda x: int(x, 0), default=IMG_END)
    ap.add_argument("--split", type=lambda x: int(x, 0), default=0x8000)
    a = ap.parse_args()
    IMG_END = a.img_end
    fwmap.IMG_END = a.img_end
    RAM_LO = BASE + IMG_END
    payload = fwmap.load_payload(a.bss)
    items, funcs, ext = parse_layout(a.layout)
    syms = parse_symbols(a.symbols)
    # sanity: layout tiles the image
    pos = BASE
    for it in items:
        if it.a != pos:
            raise SystemExit("layout gap/overlap at %08X" % pos)
        pos = it.b
    if pos != BASE + IMG_END:
        raise SystemExit("layout ends at %08X, expected %08X" % (pos, BASE + IMG_END))
    d = Dis(payload, items, funcs, ext, syms)
    d.collect()
    d.assign_ext()
    files = d.emit(a.split)
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.data, exist_ok=True)
    for f in os.listdir(a.out):
        if f.endswith(".s") and (f.startswith("part_") or f in ("00_defs.s", "zz_pad.s")):
            os.remove(os.path.join(a.out, f))
    # defs
    defs = ["; Names for addresses outside the image (generated by shdis.py from the code and symbols.txt)",
            "; RAM variables live in the SDRAM above the image (0x0C0ED9F0..), io_ = SH7709 on-chip / external registers,",
            "; bfs_func_ = entry points of the boot-flash library that is copied to SDRAM 0x0C000000."]
    names = {}
    for v, n in d.extnames.items():
        names.setdefault(n, v)
    for v, (n, c, k) in syms.items():
        if not (BASE <= v < BASE + IMG_END):
            names[n] = v
    for v in sorted(d.ramvars):
        names[d.ram_name(v)] = v
    for n, v in sorted(names.items(), key=lambda x: (x[1], x[0])):
        cm = ""
        if v in syms and syms[v][1]:
            cm = "\t; " + syms[v][1]
        defs.append("%s = 0x%08X%s" % (n, v, cm))
    with open(os.path.join(a.out, "00_defs.s"), "w", newline="\n") as f:
        f.write("\n".join(defs) + "\n")
    hdr = "; ESX-1 main firmware (BSS 'ESX0102N'), generated by tools/shdis.py - see ../README.md\n"
    for start, lines in files:
        with open(os.path.join(a.out, "part_%08X.s" % start), "w", newline="\n") as f:
            f.write(hdr + "\n".join(lines) + "\n")
    with open(os.path.join(a.out, "manifest.txt"), "w", newline="\n") as f:
        f.write("# assembly order (generated by shdis.py; add your own files before zz_pad.s)\n00_defs.s\n")
        for start, lines in files:
            f.write("part_%08X.s\n" % start)
        f.write("zz_pad.s\n")
    padname = "ram_pad.bin"
    open(os.path.join(a.data, padname), "wb").write(payload[IMG_END:])
    with open(os.path.join(a.out, "zz_pad.s"), "w", newline="\n") as f:
        f.write("; RAM filler: random bytes that the boot flash copies together with the image (SDRAM 0x%08X..), used as RAM at run time\n" % (BASE + IMG_END))
        f.write("; The RAM variables (var_*) start right behind the image at FIXED addresses that the boot flash code shares, so the\n")
        f.write("; image may shrink (gap is zero filled) but must not grow past 0x%08X.\n" % (BASE + IMG_END))
        f.write("\t.org\t0x%08X, 0\n" % (BASE + IMG_END))
        f.write("\t.incbin\t\"../data/%s\"\n" % padname)
    n_lab = len(d.need)
    print("wrote %d part files, %d labels, %d external names" % (len(files), n_lab, len(names)))


if __name__ == "__main__":
    main()
